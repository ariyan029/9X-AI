"""
main.py — CLI entrypoint for 9X-AI browser automation bot.

Commands:
    python main.py --login          Launch browser for manual authentication
    python main.py --run            Start live automated betting
    python main.py --dry-run        Paper trading mode (no real bets)
    python main.py --test-selectors Verify DOM selectors against live page
"""

import asyncio
import argparse
import signal
import sys
from pathlib import Path
from typing import Optional

from loguru import logger

from config.settings import Settings
from config.selectors import load_selectors_from_json
from browser.context import BrowserContextManager
from engine.runner import OrchestratorRunner
from utils.logger import setup_logger
from utils.circuit_breaker import EmergencyKillSwitch


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# Global kill switch for signal handling
_kill_switch = EmergencyKillSwitch()


def _handle_shutdown_signal(signum, frame):
    """Handle SIGINT/SIGTERM for graceful shutdown."""
    sig_name = signal.Signals(signum).name
    logger.warning(f"Received {sig_name}. Initiating graceful shutdown...")
    _kill_switch.trigger(f"Signal {sig_name} received")


import base64
import json
import time


def _parse_jwt(token: Optional[str]) -> tuple[bool, str, str]:
    """
    Validate JWT token and extract (is_valid, user_name, amount).
    
    Returns:
        tuple of (is_valid, user_name, amount)
    """
    if not token or token == "null" or not isinstance(token, str):
        return False, "User", "0.00"
    try:
        parts = token.split(".")
        if len(parts) >= 2:
            padded = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded))
            user_name = str(payload.get("UserName") or payload.get("UserId") or "User")
            amount = str(payload.get("Amount", "0.00"))
            exp = int(payload.get("exp", 0))
            if exp > time.time():
                return True, user_name, amount
    except Exception:
        pass
    return False, "User", "0.00"


async def cmd_login(settings: Settings):
    """
    Interactive login flow.
    
    Opens a visible browser window for the operator to authenticate
    manually. Session cookies and tokens are saved to user_data/ for reuse.
    """
    logger.info("Starting interactive login flow...")
    
    # Direct to login page so operator can immediately enter credentials
    from urllib.parse import urlparse
    parsed = urlparse(settings.BASE_URL)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    login_url = f"{origin}/#/login"

    # Force visible browser for interactive login
    login_settings = settings.model_copy(update={"HEADLESS": False})
    ctx_manager = BrowserContextManager(login_settings)
    
    try:
        context = await ctx_manager.create_context()
        page = context.pages[0] if context.pages else await context.new_page()
        
        logger.info(f"Navigating to login page: {login_url}...")
        await page.goto(login_url, wait_until="domcontentloaded")
        
        # Check if already authenticated with a valid token
        existing_token = await page.evaluate(
            "() => localStorage.getItem('token') || localStorage.getItem('ar_token')"
        )
        is_valid, user_name, amount = _parse_jwt(existing_token)
        if is_valid:
            logger.success(f"Existing valid session found: User '{user_name}' | Balance: ₹{amount}")
            logger.info(f"Navigating to game page ({settings.BASE_URL}) to confirm live balance...")
            await page.goto(settings.BASE_URL, wait_until="domcontentloaded")
            await asyncio.sleep(2.5)
            balance_el = await page.query_selector(".Wallet__C-balance-l1")
            dom_balance = (await balance_el.text_content()).strip() if balance_el else amount
            logger.success(f"✅ VERIFIED! Live Wallet Balance on game screen: {dom_balance}")
            logger.info("Press [Enter] to exit...")
            await asyncio.get_event_loop().run_in_executor(None, input)
            return

        # Purge stale expired tokens on startup to avoid false-positive detection
        try:
            await page.evaluate("""() => {
                const t = localStorage.getItem('token');
                if (t) {
                    try {
                        const parts = t.split('.');
                        if (parts.length >= 2) {
                            const payload = JSON.parse(atob(parts[1]));
                            if (payload.exp && payload.exp < Date.now() / 1000) {
                                localStorage.removeItem('token');
                                localStorage.removeItem('ar_token');
                                localStorage.removeItem('userInfo');
                            }
                        }
                    } catch (e) {
                        localStorage.removeItem('token');
                    }
                }
            }""")
        except Exception:
            pass

        logger.info("=" * 65)
        logger.info("9X-AI INTERACTIVE AUTHENTICATION")
        logger.info("=" * 65)
        logger.info("Browser window is open at: " + login_url)
        logger.info("1. Enter your mobile number and password.")
        logger.info("2. Click the 'Log in' button (and complete puzzle slider if prompted).")
        logger.info("3. DO NOT press Enter yet! The system will automatically detect")
        logger.info("   when you log in, redirect to the game, and verify your balance.")
        logger.info("=" * 65)
        logger.info("Waiting for you to log in in the browser window...")

        # Monitor loop: actively polls every 1.0s for fresh JWT
        while True:
            if page.is_closed():
                logger.warning("Browser was closed before login was completed.")
                break

            token = await page.evaluate(
                "() => localStorage.getItem('token') || localStorage.getItem('ar_token')"
            )
            is_valid, user_name, amount = _parse_jwt(token)
            if is_valid:
                logger.success("=" * 65)
                logger.success(f"🎉 LOGIN DETECTED! User: {user_name} | Balance: ₹{amount}")
                logger.info(f"Redirecting to WinGo 30s ({settings.BASE_URL}) to verify live balance...")
                logger.success("=" * 65)
                
                await page.goto(settings.BASE_URL, wait_until="domcontentloaded")
                await asyncio.sleep(3.0)

                # Read live DOM balance
                balance_el = await page.query_selector(".Wallet__C-balance-l1")
                live_balance = (await balance_el.text_content()).strip() if balance_el else amount
                logger.success(f"✅ GAME SCREEN VERIFIED! Live Wallet Balance: '{live_balance}'")
                logger.info("=" * 65)
                logger.info("Session saved to user_data/! You can now press [Enter] to exit.")
                logger.info("=" * 65)
                await asyncio.get_event_loop().run_in_executor(None, input)
                break

            await asyncio.sleep(1.0)

    finally:
        await ctx_manager.close()
        logger.info("Browser closed. You can now run --dry-run or --test-selectors.")


async def cmd_run(settings: Settings, dry_run: bool = False):
    """
    Main execution flow — live betting or dry-run simulation.
    
    Args:
        settings: Application settings.
        dry_run: If True, simulate without placing real bets.
    """
    mode = "DRY-RUN" if dry_run else "LIVE"
    logger.info(f"Starting 9X-AI engine in {mode} mode...")

    # Load selectors
    selectors_path = Path("config/selectors.json")
    selectors = load_selectors_from_json(selectors_path)

    ctx_manager = BrowserContextManager(settings)
    
    try:
        context = await ctx_manager.create_context()
        page = context.pages[0] if context.pages else await context.new_page()
        
        logger.info(f"Navigating to {settings.BASE_URL}...")
        await page.goto(settings.BASE_URL, wait_until="domcontentloaded", timeout=30000)
        
        # Settle delay: allow dynamic single-page web app to mount DOM and network listeners
        logger.info("Waiting 3s for page and dynamic UI components to settle...")
        await asyncio.sleep(3.0)
        
        # Create and run orchestrator
        runner = OrchestratorRunner(
            settings=settings,
            selectors=selectors,
            dry_run=dry_run,
        )
        runner.kill_switch = _kill_switch
        
        await runner.run(page)
        
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        raise
    finally:
        await ctx_manager.close()
        logger.info("Browser context closed. Engine shutdown complete.")


async def cmd_test_selectors(settings: Settings):
    """
    Selector verification tool.
    
    Opens the target page and attempts to locate each defined
    selector, reporting success/failure for calibration.
    """
    logger.info("Starting selector verification...")
    
    selectors_path = Path("config/selectors.json")
    selectors = load_selectors_from_json(selectors_path)
    
    ctx_manager = BrowserContextManager(settings)
    
    try:
        context = await ctx_manager.create_context()
        page = context.pages[0] if context.pages else await context.new_page()
        
        logger.info(f"Navigating to {settings.BASE_URL}...")
        await page.goto(settings.BASE_URL, wait_until="domcontentloaded", timeout=30000)
        
        # Wait a moment for dynamic content to load
        await asyncio.sleep(3)
        
        # Dismiss any announcement dialog if present
        try:
            dialog_btn = await page.wait_for_selector(
                "button.announcement-dialog__button, .van-dialog__confirm",
                timeout=1500,
            )
            if dialog_btn:
                await dialog_btn.click()
                await asyncio.sleep(0.5)
        except Exception:
            pass

        # Test each selector
        selector_map = {
            "current_round_id": selectors.current_round_id,
            "countdown_timer_seconds": selectors.countdown_timer_seconds,
            "history_table_rows": selectors.history_table_rows,
            "bet_button_big": selectors.bet_button_big,
            "bet_button_small": selectors.bet_button_small,
            "wallet_balance_display": selectors.wallet_balance_display,
            "confirm_bet_button": selectors.confirm_bet_button,
        }
        
        results = {}
        for name, selector in selector_map.items():
            try:
                # If testing confirm_bet_button, mount betting popup if not yet attached
                if name == "confirm_bet_button":
                    element = await page.query_selector(selector.css)
                    if not element and selectors.bet_button_big:
                        big_btn = await page.query_selector(selectors.bet_button_big.css)
                        if big_btn:
                            await big_btn.click()
                            await asyncio.sleep(0.5)

                element = await page.wait_for_selector(
                    selector.css, timeout=4000, state="attached"
                )
                if element:
                    text = await element.text_content()
                    cleaned_text = text.strip() if text else "(empty)"
                    results[name] = ("✅ FOUND", cleaned_text)
                    if name == "wallet_balance_display" and cleaned_text in ("0.00", "0", "₹0.00", "(empty)"):
                        token = await page.evaluate(
                            "() => localStorage.getItem('token') || localStorage.getItem('ar_token')"
                        )
                        is_valid, user_name, _ = _parse_jwt(token)
                        if not is_valid:
                            logger.warning(
                                f"  {name}: FOUND → '{cleaned_text}' "
                                "(⚠️ Session is NOT logged in! Veergame defaults balance to 0.00 for guests. "
                                "Run 'python main.py --login' to authenticate.)"
                            )
                        else:
                            logger.success(f"  {name}: FOUND → '{cleaned_text}' (✅ User: {user_name})")
                    else:
                        logger.success(f"  {name}: FOUND → '{cleaned_text}'")
                else:
                    results[name] = ("❌ NOT FOUND", "")
                    logger.error(f"  {name}: NOT FOUND (CSS: {selector.css})")

                # If we just tested confirm_bet_button, safely dismiss the popup
                if name == "confirm_bet_button":
                    cancel_btn = await page.query_selector(
                        ".Betting__Popup-foot-c, div:has-text('Cancel')"
                    )
                    if cancel_btn:
                        await cancel_btn.click()
                    else:
                        await page.keyboard.press("Escape")
                    await asyncio.sleep(0.3)

            except Exception:
                results[name] = ("❌ TIMEOUT", "")
                logger.error(f"  {name}: TIMEOUT (CSS: {selector.css})")
        
        # Summary
        found = sum(1 for status, _ in results.values() if "FOUND" in status)
        total = len(results)
        logger.info(f"\nSelector Results: {found}/{total} found successfully.")
        
        if found < total:
            logger.warning(
                "Some selectors failed. Update config/selectors.json "
                "with correct CSS/XPath for your target site."
            )
        
        logger.info("Press [Enter] to close browser...")
        await asyncio.get_event_loop().run_in_executor(None, input)
        
    finally:
        await ctx_manager.close()


def main():
    """CLI argument parser and dispatcher."""
    parser = argparse.ArgumentParser(
        prog="9X-AI",
        description="Deterministic Event-Driven Browser Automation Bot",
    )
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--login",
        action="store_true",
        help="Launch browser for manual authentication",
    )
    group.add_argument(
        "--run",
        action="store_true",
        help="Start live automated betting engine",
    )
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Paper trading mode (observe + simulate, no real bets)",
    )
    group.add_argument(
        "--test-selectors",
        action="store_true",
        help="Verify DOM selectors against the live target page",
    )
    
    args = parser.parse_args()
    
    # Load settings
    settings = Settings()
    
    # Setup logging
    setup_logger()
    
    # Register signal handlers
    signal.signal(signal.SIGINT, _handle_shutdown_signal)
    signal.signal(signal.SIGTERM, _handle_shutdown_signal)
    
    # Dispatch command
    if args.login:
        asyncio.run(cmd_login(settings))
    elif args.run:
        asyncio.run(cmd_run(settings, dry_run=False))
    elif args.dry_run:
        asyncio.run(cmd_run(settings, dry_run=True))
    elif args.test_selectors:
        asyncio.run(cmd_test_selectors(settings))


if __name__ == "__main__":
    main()
