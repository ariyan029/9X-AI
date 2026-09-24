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
    print("Navigating to direct game URL...")
    await page.goto(settings.BASE_URL, wait_until="networkidle", timeout=30000)
    await asyncio.sleep(4)
    print("Current URL:", page.url)

    # Dismiss any announcement dialog if it shows
    try:
        btn = await page.wait_for_selector("button.announcement-dialog__button", timeout=2000)
        if btn:
            await btn.click()
            print("Dismissed announcement dialog")
    except Exception:
        pass

    # Test our selectors
    selectors = {
        "current_round_id": ".TimeLeft__C-id",
        "countdown_timer_seconds": ".TimeLeft__C-time, .TimeLeft__C-num",
        "history_table_rows": ".GameRecord__C-body",
        "bet_button_big": ".Betting__C-foot-b",
        "bet_button_small": ".Betting__C-foot-s",
        "wallet_balance_display": ".Wallet__C-balance-l1, .Wallet__C-balance",
    }

    for name, sel in selectors.items():
        try:
            el = await page.wait_for_selector(sel, timeout=3000)
            if el:
                text = await el.text_content()
                print(f"[SUCCESS] {name}: FOUND -> '{text.strip()}'")
            else:
                print(f"[FAIL] {name}: NOT FOUND")
        except Exception as e:
            print(f"[TIMEOUT] {name}: {e}")

    await ctx_manager.close()

if __name__ == "__main__":
    asyncio.run(main())
