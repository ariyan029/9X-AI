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

    # Inspect the timer element HTML
    el = await page.query_selector(".TimeLeft__C-time, .TimeLeft__C-num, .TimeLeft__C")
    if el:
        html = await el.inner_html()
        print("TIMER INNER HTML:")
        print(html.encode('ascii', errors='replace').decode('ascii'))
        text = await el.inner_text()
        print("TIMER INNER TEXT:", repr(text))
    
    # Also inspect history row child items
    rows = await page.query_selector_all(".GameRecord__C-body")
    print(f"Found {len(rows)} GameRecord__C-body elements")
    if rows:
        row_html = await rows[0].inner_html()
        print("ROW 0 HTML:")
        print(row_html[:500].encode('ascii', errors='replace').decode('ascii'))

    await ctx_manager.close()

if __name__ == "__main__":
    asyncio.run(main())
