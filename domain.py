import time
from datetime import timedelta
from email.utils import parsedate_to_datetime
from core import Problem, require, text, integer, instant, iso, utcnow
from provider import FakeProvider, ProviderError

class Clock:
    def now(self): return utcnow()
    def sleep(self, seconds): time.sleep(seconds)

def retry_delay(value, now, fallback):
    if value is None: return fallback
    try:
        value = str(value)
        if value.isdigit(): return float(value)
        when = parsedate_to_datetime(value)
        if when.tzinfo is None: return fallback
        return max(0, (when - now).total_seconds())
    except (ValueError, TypeError, OverflowError):
        return fallback

def sync(state, connection_id, start, end, provider, clock, max_attempts=3, max_wait=5):
    require(1 <= max_attempts <= 5 and 0 <= max_wait <= 30, 'invalid retry policy')
    start_dt, end_dt = instant(start), instant(end)
    require(start_dt <= end_dt, 'window start must precede end')
    connection = state.setdefault('connections', {}).get(connection_id)
    require(connection is not None, 'connection not found', 404)
    if connection.get('next_allowed_at') and clock.now() < instant(connection['next_allowed_at']):
        return {'status': 'deferred', 'attempts': 0, 'next_allowed_at': connection['next_allowed_at']}
    waited = 0
    for attempt in range(1, max_attempts + 1):
        try:
            posts = provider.fetch(connection, start, end)
            break
        except (TimeoutError, ProviderError) as exc:
            status = exc.status if isinstance(exc, ProviderError) else 'timeout'
            transient = status == 'timeout' or status == 429 or (isinstance(status, int) and 500 <= status < 600)
            require(transient, 'permanent provider error', 502)
            delay = retry_delay(getattr(exc, 'retry_after', None), clock.now(), min(2 ** (attempt - 1), max_wait))
            if status == 429:
                connection['next_allowed_at'] = iso(clock.now() + timedelta(seconds=delay))
            if attempt == max_attempts or delay > max_wait - waited:
                connection['last_error'] = str(status)
                return {'status': 'deferred' if status == 429 else 'failed', 'attempts': attempt,
                        'waited_seconds': waited, 'next_allowed_at': connection.get('next_allowed_at')}
            clock.sleep(delay)
            waited += delay
    require(isinstance(posts, list), 'provider posts must be an array', 502)
    normalized = []
    for post in posts:
        require(isinstance(post, dict), 'invalid provider post', 502)
        captured = instant(text(post, 'captured_at'))
        item = {'id': text(post, 'id'), 'captured_at': iso(captured)}
        for metric in ('views', 'likes', 'comments'):
            item[metric] = integer(post, metric)
        # Window applies to snapshot capture time, inclusive at both ends.
        if start_dt <= captured <= end_dt:
            normalized.append(item)
    snapshots = connection.setdefault('snapshots', {})
    current = connection.setdefault('posts', {})
    inserted = 0
    for post in normalized:
        key = post['id'] + '|' + post['captured_at']
        previous = snapshots.get(key)
        require(previous is None or previous['metrics'] == post, 'conflicting snapshot identity', 409)
        if previous is None:
            snapshots[key] = {'metrics': post, 'fetched_at': iso(clock.now())}
            inserted += 1
        old = current.get(post['id'])
        if old is None or instant(post['captured_at']) > instant(old['captured_at']):
            current[post['id']] = dict(post)
    connection.update(last_sync_at=iso(clock.now()), last_error=None, next_allowed_at=None)
    return {'status': 'synced', 'attempts': attempt, 'waited_seconds': waited, 'inserted_snapshots': inserted,
            'posts': list(current.values()), 'totals': {k: sum(p[k] for p in current.values()) for k in ('views', 'likes', 'comments')},
            'fetched_at': connection['last_sync_at']}

def dispatch(state, method, path, data, now):
    connections = state.setdefault('connections', {})
    if method == 'POST' and path == '/connections':
        ident, platform = text(data, 'id'), text(data, 'platform')
        require(platform in ('instagram', 'tiktok', 'youtube', 'x'), 'unsupported platform')
        require(ident not in connections, 'connection already exists', 409)
        # Authentication is simulated; real credentials are not persisted by this demo.
        text(data, 'token')
        connections[ident] = {'id': ident, 'platform': platform, 'provider': 'fake', 'posts': {}, 'snapshots': {}}
        return {'id': ident, 'platform': platform, 'provider': 'fake'}
    parts = path.strip('/').split('/')
    require(len(parts) in (2, 3) and parts[0] == 'connections', 'route not found', 404)
    if method == 'GET' and len(parts) == 2:
        require(parts[1] in connections, 'connection not found', 404)
        return connections[parts[1]]
    require(method == 'POST' and len(parts) == 3 and parts[2] == 'sync', 'route not found', 404)
    responses = data.get('responses')
    require(isinstance(responses, list) and 0 < len(responses) <= 10 and all(isinstance(r, dict) for r in responses), 'responses must contain 1..10 simulated responses')
    return sync(state, parts[1], text(data, 'start'), text(data, 'end'), FakeProvider(responses), Clock())
