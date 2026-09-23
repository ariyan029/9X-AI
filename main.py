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

from loguru import logger

from config.settings import Settings
from config.selectors import load_selectors_from_json
from browser.context import BrowserContextManager
from engine.runner import OrchestratorRunner
from utils.logger import setup_logger
from utils.circuit_breaker import EmergencyKillSwitch


# Global kill switch for signal handling
_kill_switch = EmergencyKillSwitch()


def _handle_shutdown_signal(signum, frame):
    """Handle SIGINT/SIGTERM for graceful shutdown."""
    sig_name = signal.Signals(signum).name
    logger.warning(f"Received {sig_name}. Initiating graceful shutdown...")
    _kill_switch.trigger(f"Signal {sig_name} received")


async def cmd_login(settings: Settings):
    """
    Interactive login flow.
    
    Opens a visible browser window for the operator to authenticate
    manually. Session cookies are saved to user_data/ for reuse.
    """
    logger.info("Starting interactive login flow...")
    ctx_manager = BrowserContextManager(settings)
    
    try:
        context = await ctx_manager.create_context()
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(settings.BASE_URL, wait_until="domcontentloaded")
        
        logger.info(
            f"Browser opened at {settings.BASE_URL}.\n"
            "Please complete manual login in the browser window.\n"
            "Press [Enter] here when done to save session and exit..."
        )
        
        # Wait for operator input
        await asyncio.get_event_loop().run_in_executor(None, input)
        
        logger.success(
            f"Session saved to {settings.USER_DATA_DIR}/. "
            "You can now run the bot without re-authenticating."
        )
    finally:
        await ctx_manager.close()


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
        
        # Test each selector
        selector_map = {
            "current_round_id": selectors.current_round_id,
            "countdown_timer_seconds": selectors.countdown_timer_seconds,
            "history_table_rows": selectors.history_table_rows,
            "bet_button_big": selectors.bet_button_big,
            "bet_button_small": selectors.bet_button_small,
            "confirm_bet_button": selectors.confirm_bet_button,
            "wallet_balance_display": selectors.wallet_balance_display,
        }
        
        results = {}
        for name, selector in selector_map.items():
            try:
                element = await page.wait_for_selector(
                    selector.css, timeout=3000, state="attached"
                )
                if element:
                    text = await element.text_content()
                    results[name] = ("✅ FOUND", text.strip() if text else "(empty)")
                    logger.success(f"  {name}: FOUND → '{text.strip() if text else ''}'")
                else:
                    results[name] = ("❌ NOT FOUND", "")
                    logger.error(f"  {name}: NOT FOUND (CSS: {selector.css})")
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
