from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import time

def test_live_crawl():
    url = "https://www.idealista.com/venta-viviendas/madrid/centro/"
    
    print(f"Attempting to crawl: {url}")
    
    with sync_playwright() as p:
        # 1. Launch Headless=False (Headful)
        browser = p.chromium.launch(headless=False)
        
        # 2. Configure Context with Stealth-like Headers
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            extra_http_headers={
                "authority": "www.idealista.com",
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "accept-language": "es-ES,es;q=0.9,en;q=0.8",
                "cache-control": "max-age=0",
                "referer": "https://www.google.com/",
                "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "cross-site",
                "sec-fetch-user": "?1",
                "upgrade-insecure-requests": "1"
            },
            viewport={"width": 1920, "height": 1080},
            timezone_id="Europe/Madrid",
            locale="es-ES"
        )
        
        page = context.new_page()
        
        # 3. Apply Stealth (Modifies JS environment to hide automation)
        stealth = Stealth()
        stealth.apply_stealth_sync(page)

        try:
            # 4. Goto
            response = page.goto(url, timeout=30000, wait_until="domcontentloaded")
            print(f"Response Status: {response.status}")
            
            # 5. Check Content
            title = page.title()
            print(f"Page Title: {title}")
            
            content = page.content()
            
            if "captcha" in content.lower() or "datadome" in content.lower():
                print("BLOCKED: Detected CAPTCHA/DataDome.")
            elif "idealista" not in title.lower():
                print("WARNING: Title does not contain 'idealista'. Possible block or redirect.")
            else:
                print("SUCCESS: Seems to have loaded Idealista content.")
                count = page.locator("article.item").count()
                print(f"Found {count} listings on the page.")
            
            # Save artifact
            timestamp = int(time.time())
            page.screenshot(path=f"data/test_crawl_{timestamp}.png")
            with open(f"data/test_crawl_{timestamp}.html", "w") as f:
                f.write(content)
            print(f"Saved artifacts to data/test_crawl_{timestamp}.*")
            
        except Exception as e:
            print(f"ERROR: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    test_live_crawl()
