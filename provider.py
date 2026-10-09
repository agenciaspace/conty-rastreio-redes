"""Provider boundary. FakeProvider is the only demo implementation."""
from typing import Protocol

class ProviderError(Exception):
    def __init__(self, status, retry_after=None):
        self.status, self.retry_after = status, retry_after

class Provider(Protocol):
    def fetch(self, connection: dict, start: str, end: str) -> list[dict]: ...

class FakeProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
    def fetch(self, connection, start, end):
        self.calls += 1
        response = self.responses[min(self.calls - 1, len(self.responses) - 1)]
        if response.get('status') == 'timeout':
            raise TimeoutError('simulated provider timeout')
        if response.get('status', 200) != 200:
            raise ProviderError(response['status'], response.get('retry_after'))
        return response.get('posts', [])
