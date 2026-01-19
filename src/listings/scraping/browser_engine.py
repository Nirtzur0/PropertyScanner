from __future__ import annotations

import asyncio
import base64
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional, Sequence

import structlog


logger = structlog.get_logger(__name__)


BrowserTask = Callable[["Tab"], Awaitable[Any]]
BrowserPreflight = Callable[[str], Awaitable[bool]]


@dataclass(frozen=True)
class BrowserApiRequest:
    method: str
    url: str
    params: Optional[dict[str, str]] = None
    data: Optional[object] = None
    json: Optional[dict[str, Any]] = None
    headers: Optional[dict[str, str]] = None


@dataclass(frozen=True)
class BrowserMockResponse:
    url_contains: str
    status_code: int = 200
    body: object = ""
    headers: dict[str, str] = field(default_factory=dict)
    response_phrase: Optional[str] = None
    body_is_base64: bool = False


@dataclass(frozen=True)
class BrowserNetworkConfig:
    block_resource_types: Sequence[str] = ()
    block_url_keywords: Sequence[str] = ()
    extra_headers: dict[str, str] = field(default_factory=dict)
    mock_responses: Sequence[BrowserMockResponse] = ()
    monitor_network: bool = False
    network_log_limit: int = 2000


@dataclass(frozen=True)
class BrowserEngineConfig:
    user_agent: str
    headless: bool = True
    wait_s: float = 8.0
    max_concurrency: int = 4
    cloudflare_bypass: bool = True
    browser_preferences: dict[str, Any] = field(default_factory=dict)
    accept_languages: Optional[str] = None
    remote_ws_address: Optional[str] = None
    use_contexts: bool = False
    context_proxy: Optional[str] = None
    context_proxy_bypass: Optional[str] = None
    retry_max: int = 2
    retry_delay_s: float = 1.0
    retry_exponential_backoff: bool = True
    maximize_stealth: bool = True
    maximize_speed: bool = True
    network: BrowserNetworkConfig = field(default_factory=BrowserNetworkConfig)

    @classmethod
    def from_dict(
        cls,
        data: Optional[dict[str, Any]],
        *,
        user_agent: str,
        headless: bool,
        wait_s: float,
        max_concurrency: int,
    ) -> "BrowserEngineConfig":
        payload = data or {}
        network_payload = payload.get("network", {}) if isinstance(payload.get("network"), dict) else {}
        resolved_max_concurrency = int(payload.get("max_concurrency", max_concurrency))
        if resolved_max_concurrency < 1:
            resolved_max_concurrency = 1
        resolved_retry_max = int(payload.get("retry_max", 2))
        if resolved_retry_max < 0:
            resolved_retry_max = 0
        resolved_network_log_limit = int(
            network_payload.get("network_log_limit", payload.get("network_log_limit", 2000))
        )
        if resolved_network_log_limit < 1:
            resolved_network_log_limit = 1
        return cls(
            user_agent=str(payload.get("user_agent", user_agent)),
            headless=bool(payload.get("headless", headless)),
            wait_s=float(payload.get("wait_s", wait_s)),
            max_concurrency=resolved_max_concurrency,
            cloudflare_bypass=bool(payload.get("cloudflare_bypass", True)),
            browser_preferences=dict(payload.get("browser_preferences", {})),
            accept_languages=payload.get("accept_languages"),
            remote_ws_address=payload.get("remote_ws_address"),
            use_contexts=bool(payload.get("use_contexts", False)),
            context_proxy=payload.get("context_proxy"),
            context_proxy_bypass=payload.get("context_proxy_bypass"),
            retry_max=resolved_retry_max,
            retry_delay_s=float(payload.get("retry_delay_s", 1.0)),
            retry_exponential_backoff=bool(payload.get("retry_exponential_backoff", True)),
            maximize_stealth=bool(payload.get("maximize_stealth", True)),
            maximize_speed=bool(payload.get("maximize_speed", True)),
            network=BrowserNetworkConfig(
                block_resource_types=tuple(
                    network_payload.get(
                        "block_resource_types", payload.get("block_resource_types", ())
                    )
                ),
                block_url_keywords=tuple(
                    network_payload.get(
                        "block_url_keywords", payload.get("block_url_keywords", ())
                    )
                ),
                extra_headers=dict(
                    network_payload.get("extra_headers", payload.get("extra_headers", {}))
                ),
                mock_responses=tuple(
                    BrowserMockResponse(**item)
                    for item in network_payload.get(
                        "mock_responses", payload.get("mock_responses", ())
                    )
                    if isinstance(item, dict)
                ),
                monitor_network=bool(
                    network_payload.get(
                        "monitor_network", payload.get("monitor_network", False)
                    )
                ),
                network_log_limit=resolved_network_log_limit,
            ),
        )


@dataclass
class BrowserFetchResult:
    url: str
    html: Optional[str]
    network_log: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class _TabState:
    callback_ids: list[int] = field(default_factory=list)
    fetch_events_enabled: bool = False
    network_events_enabled: bool = False
    network_log: list[dict[str, Any]] = field(default_factory=list)


def ensure_browser_lib_on_path() -> None:
    root_dir = Path(__file__).resolve().parents[3]
    pydoll_dir = root_dir / "third_party" / "pydoll"
    if pydoll_dir.exists() and str(pydoll_dir) not in sys.path:
        sys.path.insert(0, str(pydoll_dir))


class BrowserEngine:
    def __init__(self, config: BrowserEngineConfig) -> None:
        self.config = config

    def is_available(self) -> bool:
        ensure_browser_lib_on_path()
        try:
            import pydoll  # noqa: F401
        except Exception:
            return False
        return True

    async def fetch_html(self, url: str, *, timeout_s: float = 30.0) -> Optional[str]:
        result = await self.fetch_with_meta(url, timeout_s=timeout_s)
        return result.html

    async def fetch_with_meta(
        self, url: str, *, timeout_s: float = 30.0
    ) -> BrowserFetchResult:
        ensure_browser_lib_on_path()
        from pydoll.decorators import retry
        from pydoll.exceptions import (
            ElementNotFound,
            NetworkError,
            PageLoadTimeout,
            WaitElementTimeout,
        )

        state: dict[str, Any] = {"tab": None}

        async def on_retry() -> None:
            tab = state.get("tab")
            if not tab:
                return
            try:
                await tab.refresh(ignore_cache=True)
            except Exception:
                return

        @retry(
            max_retries=self.config.retry_max,
            exceptions=[ElementNotFound, NetworkError, PageLoadTimeout, WaitElementTimeout],
            on_retry=on_retry,
            delay=self.config.retry_delay_s,
            exponential_backoff=self.config.retry_exponential_backoff,
        )
        async def run() -> BrowserFetchResult:
            return await self._fetch_once(url, timeout_s=timeout_s, state=state)

        return await run()

    async def run_hybrid(
        self,
        *,
        login_url: str,
        login_steps: Optional[Callable[["Tab"], Awaitable[None]]],
        api_requests: Sequence[BrowserApiRequest],
        timeout_s: float = 30.0,
    ) -> list["Response"]:
        ensure_browser_lib_on_path()
        from pydoll.decorators import retry
        from pydoll.exceptions import NetworkError, PageLoadTimeout, WaitElementTimeout

        state: dict[str, Any] = {"tab": None}

        async def on_retry() -> None:
            tab = state.get("tab")
            if not tab:
                return
            try:
                await tab.refresh(ignore_cache=True)
            except Exception:
                return

        @retry(
            max_retries=self.config.retry_max,
            exceptions=[NetworkError, PageLoadTimeout, WaitElementTimeout],
            on_retry=on_retry,
            delay=self.config.retry_delay_s,
            exponential_backoff=self.config.retry_exponential_backoff,
        )
        async def run() -> list["Response"]:
            return await self._run_hybrid_once(
                login_url=login_url,
                login_steps=login_steps,
                api_requests=api_requests,
                timeout_s=timeout_s,
                state=state,
            )

        return await run()

    async def run_concurrent(
        self, tasks: Sequence[BrowserTask], *, max_concurrency: Optional[int] = None
    ) -> list[Any]:
        if not tasks:
            return []
        return await self._run_concurrent(tasks, max_concurrency=max_concurrency)

    async def fetch_many(
        self,
        urls: Sequence[str],
        *,
        timeout_s: float = 30.0,
        max_concurrency: Optional[int] = None,
        preflight: Optional[BrowserPreflight] = None,
    ) -> list[BrowserFetchResult]:
        if not urls:
            return []

        def build_task(url: str) -> Callable[["Tab"], Awaitable[BrowserFetchResult]]:
            async def task(tab: "Tab") -> BrowserFetchResult:
                if preflight:
                    allowed = await preflight(url)
                    if not allowed:
                        return BrowserFetchResult(url=url, html=None)
                html = await self._navigate_and_extract(tab, url, timeout_s=timeout_s)
                return BrowserFetchResult(url=url, html=html)

            return task

        tasks = [build_task(url) for url in urls]
        results = await self._run_concurrent(tasks, max_concurrency=max_concurrency)
        return [result for result in results if isinstance(result, BrowserFetchResult)]

    async def _fetch_once(
        self, url: str, *, timeout_s: float, state: dict[str, Any]
    ) -> BrowserFetchResult:
        browser, initial_tab, is_remote = await self._launch_browser()
        tab, context_id, should_close_tab = await self._select_tab(
            browser, initial_tab, is_remote
        )
        state["tab"] = tab
        tab_state = await self._prepare_tab(tab)
        try:
            html = await self._navigate_and_extract(tab, url, timeout_s=timeout_s)
            return BrowserFetchResult(
                url=url,
                html=html,
                network_log=list(tab_state.network_log),
            )
        finally:
            await self._cleanup_tab(tab, tab_state)
            if should_close_tab:
                await tab.close()
            if context_id:
                await browser.delete_browser_context(context_id)
            await self._shutdown_browser(browser, is_remote)

    async def _run_hybrid_once(
        self,
        *,
        login_url: str,
        login_steps: Optional[Callable[["Tab"], Awaitable[None]]],
        api_requests: Sequence[BrowserApiRequest],
        timeout_s: float,
        state: dict[str, Any],
    ) -> list["Response"]:
        browser, initial_tab, is_remote = await self._launch_browser()
        tab, context_id, should_close_tab = await self._select_tab(
            browser, initial_tab, is_remote
        )
        state["tab"] = tab
        tab_state = await self._prepare_tab(tab)
        try:
            await self._login_via_ui(
                tab, login_url=login_url, login_steps=login_steps, timeout_s=timeout_s
            )
            responses: list["Response"] = []
            for request in api_requests:
                responses.append(await self._run_api_request(tab, request))
            return responses
        finally:
            await self._cleanup_tab(tab, tab_state)
            if should_close_tab:
                await tab.close()
            if context_id:
                await browser.delete_browser_context(context_id)
            await self._shutdown_browser(browser, is_remote)

    async def _run_concurrent(
        self, tasks: Sequence[BrowserTask], *, max_concurrency: Optional[int] = None
    ) -> list[Any]:
        browser, initial_tab, is_remote = await self._launch_browser()
        resolved = (
            int(max_concurrency)
            if max_concurrency is not None
            else int(self.config.max_concurrency)
        )
        if resolved < 1:
            resolved = 1
        semaphore = asyncio.Semaphore(resolved)
        results: list[Any] = [None] * len(tasks)
        if initial_tab and not is_remote:
            await initial_tab.close()
            initial_tab = None

        async def run_task(idx: int, task: BrowserTask) -> None:
            await semaphore.acquire()
            tab: Optional["Tab"] = None
            tab_state: Optional[_TabState] = None
            context_id: Optional[str] = None
            should_close_tab = True
            try:
                tab, context_id, should_close_tab = await self._select_tab(
                    browser, initial_tab, is_remote, force_new=True
                )
                tab_state = await self._prepare_tab(tab)
                try:
                    results[idx] = await task(tab)
                except Exception as exc:
                    results[idx] = None
                    logger.warning("browser_task_failed", error=str(exc))
            finally:
                if tab and tab_state:
                    await self._cleanup_tab(tab, tab_state)
                if tab and should_close_tab:
                    await tab.close()
                if context_id:
                    await browser.delete_browser_context(context_id)
                semaphore.release()

        try:
            await asyncio.gather(
                *(run_task(idx, task) for idx, task in enumerate(tasks)),
                return_exceptions=False,
            )
            return results
        finally:
            await self._shutdown_browser(browser, is_remote)

    async def _launch_browser(self):
        ensure_browser_lib_on_path()
        from pydoll.browser import Chrome

        options = self._build_options()
        browser = Chrome(options=options)
        if self.config.remote_ws_address:
            tab = await browser.connect(self.config.remote_ws_address)
            return browser, tab, True
        tab = await browser.start()
        return browser, tab, False

    def _build_options(self):
        from pydoll.browser.options import ChromiumOptions

        options = ChromiumOptions()
        
        # Headless Configuration
        # "new" headless mode is more stealthy than traditional headless
        # Pydoll's .headless property only supports boolean flag for old headless
        options.headless = False 
        if self.config.headless:
            try:
                options.add_argument("--headless=new")
            except Exception:
                pass

        if self.config.user_agent:
            try:
                options.add_argument(f"--user-agent={self.config.user_agent}")
            except Exception:
                pass
        
        if self.config.accept_languages:
            options.set_accept_languages(str(self.config.accept_languages))

        # --- STEALTH OPTIMIZATIONS ---
        if self.config.maximize_stealth:
            # 1. Disable AutomationControlled (essential)
            options.add_argument("--disable-blink-features=AutomationControlled")
            
            # 2. Exclude automation switch to prevent detection via navigator.webdriver
            # Pydoll's ChromiumOptions might handles exclusions, but we add if API supports or use raw args
            # Using raw argument style or if library supports exclude_switches
            if hasattr(options, "exclude_switches"):
                 options.exclude_switches.extend(["enable-automation", "enable-logging"])
            else:
                 # Fallback if specific API not available (try common approach or skip)
                 pass

            # 3. Base Stealth Preferences (look human)
            base_stealth_prefs = {
                "safebrowsing": {"enabled": True}, # Real users have this ON
                "profile": {
                    "password_manager_enabled": False, # But bots don't save passwords
                    "default_content_setting_values": {"notifications": 2} # Block notifications (annoying & detectable behavior if handled poorly)
                },
                "search": {"suggest_enabled": True}, # Real users interpret this
                "translate": {"enabled": False}, # Common bot pattern
            }
            # Merge into options.browser_preferences
            self._merge_prefs(options, base_stealth_prefs)

        # --- SPEED OPTIMIZATIONS ---
        if self.config.maximize_speed:
            speed_prefs = {
                 # Note: We do NOT block images by default anymore as it helps with stealth
                 # and is required for VLM/screenshot workflows.
                 # "profile": {"default_content_setting_values": {"images": 2}},
                 
                 # Disable heavy features
                 "webkit": {"webprefs": {"plugins_enabled": False}},
                 "browser": {"enable_spellchecking": False},
                 # Disable network prediction (saves bandwidth/CPU)
                 "net": {"network_prediction_options": 2}, 
            }
            self._merge_prefs(options, speed_prefs)

        # User overrides apply last
        if self.config.browser_preferences:
            try:
                self._merge_prefs(options, self.config.browser_preferences)
            except Exception:
                pass
        
        return options

    def _merge_prefs(self, options, new_prefs: dict):
        """Helper to deeply merge preferences into options."""
        current = getattr(options, "browser_preferences", {}) or {}
        
        def deep_update(d, u):
            for k, v in u.items():
                if isinstance(v, dict):
                    d[k] = deep_update(d.get(k, {}), v)
                else:
                    d[k] = v
            return d

        merged = deep_update(current, new_prefs)
        options.browser_preferences = merged

    async def _select_tab(
        self,
        browser: "Browser",
        initial_tab: Optional["Tab"],
        is_remote: bool,
        *,
        force_new: bool = False,
    ) -> tuple["Tab", Optional[str], bool]:
        context_id = None
        should_close_tab = True

        if self.config.use_contexts:
            context_id = await browser.create_browser_context(
                proxy_server=self.config.context_proxy,
                proxy_bypass_list=self.config.context_proxy_bypass,
            )
            tab = await browser.new_tab(browser_context_id=context_id)
            if initial_tab and not is_remote:
                await initial_tab.close()
            return tab, context_id, True

        if force_new or is_remote or initial_tab is None:
            tab = await browser.new_tab()
            should_close_tab = True
            return tab, context_id, should_close_tab

        should_close_tab = False
        return initial_tab, context_id, should_close_tab

    async def _prepare_tab(self, tab: "Tab") -> _TabState:
        from pydoll.protocol.fetch.events import FetchEvent
        from pydoll.protocol.network.events import NetworkEvent
        from pydoll.protocol.network.types import ErrorReason

        state = _TabState()
        network_conf = self.config.network
        block_types = {str(t).lower() for t in network_conf.block_resource_types if t}
        block_urls = tuple(str(token) for token in network_conf.block_url_keywords if token)
        extra_headers = {str(key): str(value) for key, value in network_conf.extra_headers.items()}
        mock_responses = tuple(network_conf.mock_responses)
        should_intercept = any([block_types, block_urls, extra_headers, mock_responses])

        def append_log(entry: dict[str, Any]) -> None:
            state.network_log.append(entry)
            if len(state.network_log) > network_conf.network_log_limit:
                state.network_log.pop(0)

        if network_conf.monitor_network:
            await tab.enable_network_events()
            state.network_events_enabled = True

            async def on_request(event: dict) -> None:
                params = event.get("params", {})
                req = params.get("request", {})
                append_log(
                    {
                        "event": "request",
                        "url": req.get("url"),
                        "method": req.get("method"),
                        "resource_type": params.get("type"),
                    }
                )

            async def on_response(event: dict) -> None:
                params = event.get("params", {})
                resp = params.get("response", {})
                append_log(
                    {
                        "event": "response",
                        "url": resp.get("url"),
                        "status": resp.get("status"),
                        "resource_type": params.get("type"),
                    }
                )

            state.callback_ids.append(
                await tab.on(NetworkEvent.REQUEST_WILL_BE_SENT, on_request)
            )
            state.callback_ids.append(
                await tab.on(NetworkEvent.RESPONSE_RECEIVED, on_response)
            )

        if should_intercept:
            await tab.enable_fetch_events()
            state.fetch_events_enabled = True

            async def handle_request(event: dict) -> None:
                params = event.get("params", {})
                request_id = params.get("requestId")
                request = params.get("request", {}) or {}
                url = str(request.get("url", ""))
                resource_type = params.get("resourceType")
                resource_value = (
                    resource_type.value
                    if hasattr(resource_type, "value")
                    else str(resource_type)
                )
                if block_types and resource_value.lower() in block_types:
                    await tab.fail_request(request_id, ErrorReason.BLOCKED_BY_CLIENT)
                    return
                if block_urls and any(token in url for token in block_urls):
                    await tab.fail_request(request_id, ErrorReason.BLOCKED_BY_CLIENT)
                    return
                for mock in mock_responses:
                    if mock.url_contains and mock.url_contains in url:
                        body = mock.body
                        if mock.body_is_base64:
                            if isinstance(body, bytes):
                                encoded_body = body.decode("utf-8")
                            else:
                                encoded_body = str(body)
                        else:
                            if isinstance(body, (dict, list)):
                                body_bytes = json.dumps(body).encode("utf-8")
                            elif isinstance(body, str):
                                body_bytes = body.encode("utf-8")
                            else:
                                body_bytes = bytes(body)
                            encoded_body = base64.b64encode(body_bytes).decode()
                        headers = [
                            {"name": str(key), "value": str(value)}
                            for key, value in mock.headers.items()
                        ]
                        await tab.fulfill_request(
                            request_id=request_id,
                            response_code=mock.status_code,
                            response_headers=headers or None,
                            body=encoded_body,
                            response_phrase=mock.response_phrase,
                        )
                        return
                if extra_headers:
                    merged = dict(request.get("headers") or {})
                    merged.update(extra_headers)
                    headers = [
                        {"name": str(key), "value": str(value)} for key, value in merged.items()
                    ]
                    await tab.continue_request(request_id, headers=headers)
                else:
                    await tab.continue_request(request_id)

            state.callback_ids.append(await tab.on(FetchEvent.REQUEST_PAUSED, handle_request))

        return state

    async def _cleanup_tab(self, tab: "Tab", state: _TabState) -> None:
        for callback_id in state.callback_ids:
            try:
                await tab.remove_callback(callback_id)
            except Exception:
                continue
        if state.fetch_events_enabled:
            try:
                await tab.disable_fetch_events()
            except Exception:
                pass
        if state.network_events_enabled:
            try:
                await tab.disable_network_events()
            except Exception:
                pass

    async def _navigate_and_extract(
        self, tab: "Tab", url: str, *, timeout_s: float
    ) -> Optional[str]:
        if self.config.cloudflare_bypass:
            try:
                async with tab.expect_and_bypass_cloudflare_captcha():
                    await tab.go_to(url, timeout=int(timeout_s))
            except Exception:
                await tab.go_to(url, timeout=int(timeout_s))
        else:
            await tab.go_to(url, timeout=int(timeout_s))
        if self.config.wait_s:
            await asyncio.sleep(self.config.wait_s)
        return await tab.page_source

    async def _login_via_ui(
        self,
        tab: "Tab",
        *,
        login_url: str,
        login_steps: Optional[Callable[["Tab"], Awaitable[None]]],
        timeout_s: float,
    ) -> None:
        if login_url:
            await tab.go_to(login_url, timeout=int(timeout_s))
        if login_steps:
            await login_steps(tab)
        if self.config.wait_s:
            await asyncio.sleep(self.config.wait_s)

    async def _run_api_request(self, tab: "Tab", request: BrowserApiRequest) -> "Response":
        headers = None
        if request.headers:
            headers = [
                {"name": str(key), "value": str(value)} for key, value in request.headers.items()
            ]
        return await tab.request.request(
            request.method,
            request.url,
            params=request.params,
            data=request.data,
            json=request.json,
            headers=headers,
        )

    async def _shutdown_browser(self, browser: "Browser", is_remote: bool) -> None:
        if is_remote:
            await browser.close()
        else:
            await browser.stop()


if TYPE_CHECKING:
    from pydoll.browser.chromium.base import Browser
    from pydoll.browser.requests.response import Response
    from pydoll.browser.tab import Tab
