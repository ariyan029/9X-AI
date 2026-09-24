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
        await big_btn.click()
        await asyncio.sleep(2)

        popup = await page.query_selector(".Betting__Popup, div[class*='Betting__Popup']")
        if popup:
            foot = await popup.query_selector("div[class*='foot']")
            if foot:
                print("FOOT HTML:", (await foot.inner_html())[:500].encode('ascii', errors='replace').decode('ascii'))
                print("FOOT TEXT:", repr(await foot.inner_text()).encode('ascii', errors='replace').decode('ascii'))

    await ctx_manager.close()

if __name__ == "__main__":
    asyncio.run(main())
