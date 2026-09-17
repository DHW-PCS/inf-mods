"""Offline HTTP doubles shared by catalogue tests."""

import requests


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError(f"Unexpected request: {url}")
        return self.responses.pop(0)


class RoutedSession:
    def __init__(self, responses):
        self.responses = responses

    def get(self, url, **kwargs):
        for url_part, response in self.responses:
            if url_part in url:
                return response
        raise AssertionError(f"Unexpected request: {url}")
