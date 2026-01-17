import time
import random
import asyncio
from urllib.parse import urlparse, urlunparse
from functools import partialmethod

from .response import StealthResponse

from curl_cffi.requests.session import Session, AsyncSession, HttpMethod


RETRY_DELAY = 2  # Seconds
RETRYABLE_STATUS_CODES = {
    408,  # Request Timeout
    429,  # Too Many Requests
    500,  # Internal Server Error
    502,  # Bad Gateway
    503,  # Service Unavailable
    504,  # Gateway Timeout
    520,  # Cloudflare Unknown Error
    521,  # Cloudflare Web Server Is Down
    522,  # Cloudflare Connection Timed Out
    523,  # Cloudflare Origin Is Unreachable
    524,  # Cloudflare A Timeout Occurred
}


user_agents = [
    "Mozilla/5.0 (Macintosh; Apple M1 Max; macOS 13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.7103.95 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Apple M1 Pro; macOS 13_5_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


class BaseStealthSession:
    def __init__(self, **kwargs):
        timeout = kwargs.pop('timeout', 30)

        headers = kwargs.pop('headers', {})
        headers.setdefault('User-Agent', random.choice(user_agents))

        self.last_request_url = None

        super().__init__(impersonate='chrome', timeout=timeout, headers=headers, **kwargs)


class StealthSession(BaseStealthSession, Session):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def request(self, method: HttpMethod, url: str, *args, retry: int = 0, **kwargs) -> StealthResponse:
        assert retry >= 0

        referer = {'Referer': self.last_request_url} if self.last_request_url else {}
        extra_headers = referer | kwargs.pop('headers', {})

        for attempt in range(retry + 1):
            resp = super().request(method, url, *args, headers=extra_headers, **kwargs)
            response = StealthResponse(resp)

            if resp.status_code not in RETRYABLE_STATUS_CODES or attempt == retry:
                break

            # Retry after delay
            time.sleep(RETRY_DELAY)

        parsed = urlparse(url)
        self.last_request_url = urlunparse(parsed._replace(query='', fragment=''))

        return response

    head = partialmethod(request, 'HEAD')
    get = partialmethod(request, 'GET')
    post = partialmethod(request, 'POST')
    put = partialmethod(request, 'PUT')
    patch = partialmethod(request, 'PATCH')
    delete = partialmethod(request, 'DELETE')
    options = partialmethod(request, 'OPTIONS')


class AsyncStealthSession(BaseStealthSession, AsyncSession):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def request(self, method: HttpMethod, url: str, *args, retry: int = 0, **kwargs) -> StealthResponse:
        assert retry >= 0

        referer = {'Referer': self.last_request_url} if self.last_request_url else {}
        extra_headers = referer | kwargs.pop('headers', {})

        for attempt in range(retry + 1):
            resp = await super().request(method, url, *args, headers=extra_headers, **kwargs)
            response = StealthResponse(resp)

            if resp.status_code not in RETRYABLE_STATUS_CODES or attempt == retry:
                break

            # Retry after delay
            await asyncio.sleep(RETRY_DELAY)

        parsed = urlparse(url)
        self.last_request_url = urlunparse(parsed._replace(query='', fragment=''))

        return response

    head = partialmethod(request, 'HEAD')
    get = partialmethod(request, 'GET')
    post = partialmethod(request, 'POST')
    put = partialmethod(request, 'PUT')
    patch = partialmethod(request, 'PATCH')
    delete = partialmethod(request, 'DELETE')
    options = partialmethod(request, 'OPTIONS')
