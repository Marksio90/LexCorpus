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
                    'headers': {k: v for k, v in headers.items() if k.lower() in ['content-type', 'accept', 'x-requested-with']},
                    'post_data': post_data,
                })
        
        page.on("request", lambda r: asyncio.create_task(handle_request(r)))
        
        print("Navigating...")
        await page.goto("https://eureka.mf.gov.pl", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(3)
        
        # Find and fill search
        inputs = await page.query_selector_all('input')
        for inp in inputs:
            placeholder = await inp.get_attribute('placeholder') or ''
            if 'fraz' in placeholder.lower():
                await inp.fill("VAT")
                await asyncio.sleep(1)
                await inp.press("Enter")
                await asyncio.sleep(5)
                break
        
        print(f"\n=== CAPTURED REQUESTS ({len(request_log)}) ===")
        for req in request_log:
            print(f"\n{req['method']} {req['url']}")
            print(f"Headers: {json.dumps(req['headers'], indent=2)}")
            if req['post_data']:
                print(f"Body: {req['post_data'][:1000]}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
