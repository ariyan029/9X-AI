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
    print("CURRENT URL:", page.url)
    print("PAGE TITLE:", await page.title())
    content = await page.content()
    print("CONTENT LENGTH:", len(content))
    Path("scratch/page_dump.html").write_text(content, encoding="utf-8")
    await ctx_manager.close()

if __name__ == "__main__":
    asyncio.run(main())
