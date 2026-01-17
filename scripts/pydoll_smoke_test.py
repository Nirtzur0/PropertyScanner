import asyncio
import re
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
PYDOLL_DIR = ROOT_DIR / "third_party" / "pydoll"
sys.path.insert(0, str(PYDOLL_DIR))

from pydoll.browser import Chrome  # noqa: E402
from pydoll.browser.options import ChromiumOptions  # noqa: E402


DEFAULT_URL = "https://www.zoopla.co.uk/for-sale/property/london/"


def _extract_links(html: str, pattern: str, limit: int) -> list[str]:
    matches = re.findall(pattern, html)
    urls = []
    for match in matches:
        url = match
        if url.startswith("//"):
            url = f"https:{url}"
        if url.startswith("/"):
            url = f"https://www.zoopla.co.uk{url}"
        if url not in urls:
            urls.append(url)
        if len(urls) >= limit:
            break
    return urls


async def smoke_test(url: str, limit: int = 5) -> int:
    options = ChromiumOptions()
    options.headless = True

    browser = Chrome(options=options)
    try:
        tab = await browser.start()
        async with tab.expect_and_bypass_cloudflare_captcha():
            await tab.go_to(url)
        await asyncio.sleep(8)
        html = await tab.page_source
        title_result = await tab.execute_script("return document.title")
    finally:
        await browser.stop()

    title = title_result
    if isinstance(title_result, dict):
        title = (
            title_result.get("result", {})
            .get("result", {})
            .get("value", title_result)
        )
    print(f"Page title: {title}")
    lower_html = html.lower()
    if "cloudflare" in lower_html or "captcha" in lower_html:
        print("Detected challenge page content (cloudflare/captcha).")

    if "zoopla.co.uk" in url:
        links = _extract_links(html, r'href="([^"]*/for-sale/details/[^"]+)"', limit)
        if not links:
            links = _extract_links(html, r'href="([^"]*/details/[^"]+)"', limit)
    else:
        links = _extract_links(html, r'href="([^"]*/inmueble/[^"]+)"', limit)

    print(f"Found {len(links)} listing links")
    for link in links:
        print(link)
    return len(links)


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    asyncio.run(smoke_test(url))


if __name__ == "__main__":
    main()
