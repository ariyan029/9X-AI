import asyncio
import sys
from pathlib import Path
sys.path.insert(0, ".")
from browser.context import BrowserContextManager
from config.settings import Settings

async def main():
    settings = Settings(
        BASE_URL="https://www.veergame41.com/#/home/AllLotteryGames/WinGo?typeId=30",
        HEADLESS=True,
    )
    ctx_manager = BrowserContextManager(settings)
    context = await ctx_manager.create_context()
    page = context.pages[0] if context.pages else await context.new_page()
    await page.goto(settings.BASE_URL, wait_until="networkidle", timeout=30000)
    await asyncio.sleep(4)

    # Click Big button
    big_btn = await page.wait_for_selector(".Betting__C-foot-b", timeout=5000)
    if big_btn:
        print("Clicking Big button...")
        await big_btn.click()
        await asyncio.sleep(2)

        # Inspect the popup that appears
        popup = await page.query_selector(".Betting__Popup, div[class*='Betting__Popup']")
        if popup:
            print("Found Betting popup!")
            html = await popup.inner_html()
            print("POPUP HTML:")
            print(html[:800].encode('ascii', errors='replace').decode('ascii'))
            
            # Find input field
            inp = await page.query_selector("input")
            if inp:
                print("Input field:", await inp.evaluate("el => el.outerHTML"))
            
            # Find buttons
            buttons = await popup.query_selector_all("button, div.btn, div[class*='btn'], div[class*='foot']")
            for b in buttons:
                txt = await b.text_content()
                cls = await b.get_attribute("class")
                print(f"Button: class='{cls}', text='{txt.strip()}'")

    await ctx_manager.close()

if __name__ == "__main__":
    asyncio.run(main())
