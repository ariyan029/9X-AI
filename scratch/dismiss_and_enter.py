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

    # Dismiss announcement dialog if present
    btn = await page.query_selector("button.announcement-dialog__button")
    if btn:
        print("Dismissing announcement dialog...")
        await btn.click()
        await asyncio.sleep(2)

    # Click WinGo 30S card
    wingo_card = await page.query_selector("img[src*='WinGo_30S']")
    if wingo_card:
        print("Clicking WinGo 30S card...")
        await wingo_card.click()
        await asyncio.sleep(5)
    else:
        print("WinGo card not found.")

    print("CURRENT PAGE URL:", page.url)
    content = await page.content()
    Path("scratch/wingo_screen.html").write_text(content, encoding="utf-8")
    print("Saved wingo_screen.html, length:", len(content))
    await ctx_manager.close()

if __name__ == "__main__":
    asyncio.run(main())
