import os
import sys
import random
import time
import math
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

# Fix for M1 OpenMP conflicts if any ML libraries are loaded (good practice)
os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'

def human_sleep(min_seconds=0.5, max_seconds=2.0):
    time.sleep(random.uniform(min_seconds, max_seconds))

def human_mouse_move(page, start_x, start_y, end_x, end_y, steps=20):
    """
    Simulate a human-like mouse movement with some random jitter.
    """
    for i in range(steps + 1):
        t = i / steps
        # Linear interpolation
        x = start_x + (end_x - start_x) * t
        y = start_y + (end_y - start_y) * t
        
        # Add random jitter (sine wave + noise)
        jitter = math.sin(t * math.pi) * random.randint(-5, 5)
        
        page.mouse.move(x + jitter, y + jitter)
        time.sleep(random.uniform(0.01, 0.05))

def test_live_crawl_advanced():
    url = "https://www.idealista.com/venta-viviendas/madrid/centro/"
    
    print(f"🕵️  Advanced Stealth Crawl: {url}")
    
    with sync_playwright() as p:
        # 1. Launch Headful (User suggestion: "disable headless")
        # "slow_mo" adds delays between Playwright operations
        browser = p.chromium.launch(
            headless=False,
            slow_mo=100, 
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
                "--window-size=1920,1080"
            ]
        )
        
        # 2. Context with Fixed User Agent
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="es-ES",
            timezone_id="Europe/Madrid",
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=2,
            has_touch=False,
            is_mobile=False,
            java_script_enabled=True,
            extra_http_headers={
                 "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                 "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
                 "Cache-Control": "max-age=0",
                 "Connection": "keep-alive",
                 "Referer": "https://www.google.es/",
                 "Sec-Fetch-Dest": "document",
                 "Sec-Fetch-Mode": "navigate",
                 "Sec-Fetch-Site": "cross-site",
                 "Upgrade-Insecure-Requests": "1"
            }
        )
        
        # Expose a function to add stealth scripts? 
        # playwright-stealth works on Page creation.
        page = context.new_page()
        stealth_plugin = Stealth()
        stealth_plugin.apply_stealth_sync(page)

        try:
            print("🚀 Navigating...")
            # Random initial delay?
            human_sleep(1, 3)
            
            # Go to Google first to build history? (Referer handles this partly)
            
            response = page.goto(url, timeout=60000, wait_until="domcontentloaded")
            print(f"📡 Status: {response.status}")
            
            # 3. Random interactions
            human_sleep(2, 5)
            
            # Simulated Mouse Move
            print("🐭 Moving mouse...")
            human_mouse_move(page, 100, 100, 500, 500)
            
            # Scroll down
            print("📜 Scrolling...")
            for _ in range(3):
                page.mouse.wheel(0, random.randint(300, 700))
                human_sleep(1, 3)
                human_mouse_move(page, random.randint(0, 500), random.randint(0, 500), random.randint(500, 800), random.randint(500, 800))
            
            title = page.title()
            print(f"📄 Title: {title}")
            
            content = page.content()
            if "captcha" in content.lower() or "datadome" in content.lower():
                 print("❌ BLOCKED: DataDome/Captcha detected.")
            else:
                 print("✅ SUCCESS: Content seems loaded.")
                 count = page.locator("article.item").count()
                 print(f"🏠 Found {count} listings.")

            # Save snapshot
            ts = int(time.time())
            page.screenshot(path=f"data/stealth_{ts}.png")
            with open(f"data/stealth_{ts}.html", "w") as f:
                f.write(content)
                
        except Exception as e:
            print(f"⚠️ Error: {e}")
            page.screenshot(path="data/error_stealth.png")
            
        finally:
            print("🔒 Closing...")
            browser.close()

if __name__ == "__main__":
    test_live_crawl_advanced()
