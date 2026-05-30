import asyncio
import json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        responses_log = []
        
        async def handle_response(response):
            url = response.url
            if 'eureka.mf.gov.pl' in url:
                try:
                    content_type = response.headers.get('content-type', '')
                    if 'json' in content_type or 'api' in url:
                        body = await response.text()
                        responses_log.append({
                            'url': url,
                            'status': response.status,
                            'body_preview': body[:800],
                        })
                        print(f"\n=== API RESPONSE ===")
                        print(f"URL: {url}")
                        print(f"Status: {response.status}")
                        print(f"Content-Type: {content_type}")
                        print(f"Body: {body[:500]}")
                except:
                    pass
        
        page.on("response", lambda r: asyncio.create_task(handle_response(r)))
        
        print("Navigating to eureka.mf.gov.pl...")
        try:
            await page.goto("https://eureka.mf.gov.pl", wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"Navigation issue (continuing): {e}")
        
        await asyncio.sleep(5)
        
        # Print page title
        title = await page.title()
        print(f"\nPage title: {title}")
        
        # Try to interact with search
        try:
            inputs = await page.query_selector_all('input')
            print(f"Found {len(inputs)} input fields")
            
            for inp in inputs[:10]:
                placeholder = await inp.get_attribute('placeholder') or ''
                input_type = await inp.get_attribute('type') or 'text'
                name = await inp.get_attribute('name') or ''
                print(f"  Input: type={input_type}, name={name}, placeholder={placeholder}")
            
            # Try first text input
            for inp in inputs:
                input_type = await inp.get_attribute('type') or 'text'
                if input_type in ('text', 'search'):
                    await inp.fill("podatek VAT")
                    await asyncio.sleep(1)
                    await inp.press("Enter")
                    await asyncio.sleep(5)
                    break
        except Exception as e:
            print(f"Error interacting: {e}")
        
        print(f"\n=== TOTAL API RESPONSES: {len(responses_log)} ===")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
