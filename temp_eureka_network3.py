import asyncio
import json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        request_log = []
        
        async def handle_request(request):
            url = request.url
            if 'wyszukiwarka/informacje' in url:
                post_data = request.post_data
                headers = dict(request.headers)
                request_log.append({
                    'method': request.method,
                    'url': url,
                    'headers': {k: v for k, v in headers.items() if k.lower() in ['content-type', 'accept']},
                    'post_data': post_data,
                })
        
        page.on("request", lambda r: asyncio.create_task(handle_request(r)))
        
        print("Navigating...")
        await page.goto("https://eureka.mf.gov.pl", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(3)
        
        # Click on "Zaawansowane" (Advanced search) if available
        # Look for date inputs or advanced search button
        buttons = await page.query_selector_all('button')
        for btn in buttons[:20]:
            text = await btn.text_content() or ''
            if 'zaawansowane' in text.lower() or 'więcej' in text.lower() or 'filtr' in text.lower():
                print(f"Clicking button: {text.strip()}")
                await btn.click()
                await asyncio.sleep(2)
                break
        
        # Look for date inputs
        inputs = await page.query_selector_all('input')
        for inp in inputs:
            placeholder = await inp.get_attribute('placeholder') or ''
            input_type = await inp.get_attribute('type') or ''
            name = await inp.get_attribute('name') or ''
            if 'data' in placeholder.lower() or 'data' in name.lower() or input_type == 'date':
                print(f"Found date input: type={input_type}, name={name}, placeholder={placeholder}")
        
        # Try to find and click on a date filter or calendar
        # Look for any element with "data" in it
        all_elements = await page.query_selector_all('*')
        for el in all_elements[:100]:
            text = await el.text_content() or ''
            if 'data' in text.lower() and len(text.strip()) < 50:
                print(f"Element with 'data': {text.strip()[:100]}")
        
        print(f"\n=== CAPTURED REQUESTS ({len(request_log)}) ===")
        for req in request_log:
            print(f"\n{req['method']} {req['url']}")
            if req['post_data']:
                try:
                    body = json.loads(req['post_data'])
                    print(json.dumps(body, indent=2, ensure_ascii=False)[:1500])
                except:
                    print(req['post_data'][:500])
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
