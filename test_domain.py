import unittest
from datetime import timedelta
from core import Store, Problem, instant
from domain import sync
from provider import FakeProvider

class FakeClock:
    def __init__(self): self.value = instant('2026-10-09T15:00:00Z'); self.waits = []
    def now(self): return self.value
    def sleep(self, seconds): self.waits.append(seconds); self.value += timedelta(seconds=seconds)

class SyncTests(unittest.TestCase):
    def setUp(self):
        self.store, self.clock = Store(), FakeClock()
        self.store.transact(lambda s: s.update(connections={'c1': {'id': 'c1', 'platform': 'instagram'}}))
        self.post = {'id': 'p1', 'captured_at': '2026-10-09T14:00:00Z', 'views': 100, 'likes': 10, 'comments': 2}
    def tearDown(self): self.store.close()
    def run_sync(self, responses, start='2026-10-09T00:00:00Z', end='2026-10-10T00:00:00Z'):
        self.provider = FakeProvider(responses)
        return self.store.transact(lambda s: sync(s, 'c1', start, end, self.provider, self.clock))
    def test_duplicate_and_overlapping_windows(self):
        result = self.run_sync([{'posts': [self.post, self.post]}])
        self.assertEqual(result['inserted_snapshots'], 1)
        result = self.run_sync([{'posts': [self.post]}], start='2026-10-09T12:00:00Z')
        self.assertEqual(result['inserted_snapshots'], 0)
        self.assertEqual(result['totals']['views'], 100)
    def test_newer_replaces_not_adds_and_older_cannot_regress(self):
        newer = dict(self.post, captured_at='2026-10-09T15:00:00Z', views=200)
        self.run_sync([{'posts': [newer]}])
        result = self.run_sync([{'posts': [self.post]}])
        self.assertEqual(result['totals']['views'], 200)
    def test_429_waits_retry_after_with_controlled_clock(self):
        result = self.run_sync([{'status': 429, 'retry_after': '3'}, {'posts': [self.post]}])
        self.assertEqual(self.clock.waits, [3])
        self.assertEqual(result['attempts'], 2)
        self.assertEqual(result['fetched_at'], '2026-10-09T15:00:03Z')
    def test_http_date_retry_after(self):
        self.run_sync([{'status': 429, 'retry_after': 'Fri, 09 Oct 2026 15:00:04 GMT'}, {'posts': []}])
        self.assertEqual(self.clock.waits, [4])
    def test_long_wait_defers_without_violating_provider_limit(self):
        result = self.run_sync([{'status': 429, 'retry_after': '60'}])
        self.assertEqual(result['status'], 'deferred')
        self.assertEqual(self.clock.waits, [])
        result = self.run_sync([{'posts': [self.post]}])
        self.assertEqual(result['attempts'], 0)
        self.assertEqual(self.provider.calls, 0)
        self.clock.sleep(60)
        self.assertEqual(self.run_sync([{'posts': []}])['status'], 'synced')
    def test_timeout_retries_are_bounded(self):
        result = self.run_sync([{'status': 'timeout'}])
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(self.provider.calls, 3)
        self.assertEqual(self.clock.waits, [1, 2])
    def test_transient_failure_recovers(self):
        result = self.run_sync([{'status': 503}, {'posts': [self.post]}])
        self.assertEqual(result['status'], 'synced')
    def test_conflicting_snapshot_rolls_back(self):
        self.run_sync([{'posts': [self.post]}])
        with self.assertRaises(Problem):
            self.run_sync([{'posts': [dict(self.post, views=999)]}])
        self.assertEqual(self.run_sync([{'posts': []}])['totals']['views'], 100)
    def test_permanent_error_not_retried(self):
        with self.assertRaises(Problem): self.run_sync([{'status': 401}])
        self.assertEqual(self.provider.calls, 1)
    def test_window_filters_snapshots(self):
        result = self.run_sync([{'posts': [self.post]}], start='2026-10-09T15:00:00Z')
        self.assertEqual(result['totals']['views'], 0)

if __name__ == '__main__': unittest.main()
