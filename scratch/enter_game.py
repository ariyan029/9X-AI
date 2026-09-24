import asyncio
import sys
from pathlib import Path
sys.path.insert(0, ".")
from browser.context import BrowserContextManager
from config.settings import Settings

async def main():
    settings = Settings(
        BASE_URL="https://www.veergame41.com/#/",
        HEADLESS=True,
    )
    ctx_manager = BrowserContextManager(settings)
    context = await ctx_manager.create_context()
    page = context.pages[0] if context.pages else await context.new_page()
    await page.goto(settings.BASE_URL, wait_until="networkidle", timeout=30000)
    await asyncio.sleep(4)
    print("Initial URL:", page.url)

    # Find the element with WinGo 30S or Play Now
    # Let's find images containing WinGo_30S or elements with text Play Now
    wingo_card = await page.query_selector("img[src*='WinGo_30S']")
    if wingo_card:
        print("Found WinGo 30S image! Clicking parent/card...")
        parent = await wingo_card.evaluate_handle("el => el.closest('div.item') || el.parentElement")
        if parent:
            await parent.click()
        else:
            await wingo_card.click()
    else:
        print("WinGo image not found directly, looking for text 'Win Go' or 'Lottery'...")
        lottery_btn = await page.query_selector("text=Lottery")
        if lottery_btn:
            await lottery_btn.click()
            await asyncio.sleep(2)

    await asyncio.sleep(5)
    print("Game Screen URL:", page.url)
    content = await page.content()
    Path("scratch/game_screen.html").write_text(content, encoding="utf-8")
    print("Saved game_screen.html, length:", len(content))
    await ctx_manager.close()

if __name__ == "__main__":
    asyncio.run(main())
