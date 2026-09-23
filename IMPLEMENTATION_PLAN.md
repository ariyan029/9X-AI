# 9X-AI: Implementation Plan & Engineering Execution Roadmap

- **Author:** SK Ariyan Ali
- **Role:** Senior Systems & Automation Engineer
- **Document Version:** 1.0.0
- **Target Runtime:** Python 3.10+ | Asyncio | Playwright (Async API) | Playwright-Stealth
- **Status:** Execution Roadmap Ready for Implementation

---

## 1. Executive Summary & Objective

This document establishes the step-by-step engineering plan to build, test, and deploy the **9X-AI** deterministic browser automation bot as specified in [`PROJECT_SPEC.md`](file:///d:/9X-AI/PROJECT_SPEC.md) and [`TECHNICAL_APPROACH.md`](file:///d:/9X-AI/TECHNICAL_APPROACH.md).

The implementation strictly follows the **Ports & Adapters (Hexagonal Architecture)** design pattern:
1. **Core Domain First:** Pure Python business logic, data models, 16-step fixed ladder progression, and deterministic state transitions—tested in 100% isolation.
2. **Infrastructure & Adapters Second:** Persistent Playwright browser contexts, stealth evasion, DOM/CDP network ingestion, and humanized action execution.
3. **Orchestration & Operational Hardening Third:** Async event loop, timing window gatekeeper ($25\text{s} \ge T \ge 10\text{s}$), safety circuit breakers, structured audit logging, and CLI interface.

---

## 2. Proposed Component Architecture & File Matrix

```
d:\9X-AI\
├── .env.example                     # Environment template (BASE_URL, HEADLESS, USER_DATA_DIR, etc.)
├── .gitignore                       # Git ignore rules (user_data/, logs/, .env, __pycache__)
├── requirements.txt                 # Pinned dependencies (playwright, playwright-stealth, pydantic, loguru, pytest)
├── README.md                        # Operator guide and deployment manual
├── PROJECT_SPEC.md                  # Approved product & system specification
├── TECHNICAL_APPROACH.md            # Approved engineering strategy
├── IMPLEMENTATION_PLAN.md           # This execution roadmap
│
├── config/
│   ├── __init__.py
│   ├── settings.py                  # Pydantic v2 Settings (timing boundaries, paths, thresholds)
│   └── selectors.py                 # Abstracted UI selector dataclasses & loaders
│   └── selectors.json               # Default CSS/XPath selector definitions with fallbacks
│
├── core/
│   ├── __init__.py
│   ├── models.py                    # Pure typed models: GameOutcome, EngineState, RoundResolution, BetOrder
│   ├── ladder.py                    # Immutable 16-step bet progression manager & risk calculus
│   └── state_machine.py             # Deterministic FSM: 3-streak trigger, win/loss transitions, loss-limit abort
│
├── browser/
│   ├── __init__.py
│   ├── context.py                   # Persistent browser context factory with playwright-stealth & session persistence
│   ├── observer.py                  # Ingestion observer: DOM scraper + CDP network interceptor + round deduper
│   └── executor.py                  # Humanized click dispatcher, chip/input setter, and confirmation verifier
│
├── engine/
│   ├── __init__.py
│   └── runner.py                    # Main async orchestration loop linking observer, FSM, and executor
│
├── utils/
│   ├── __init__.py
│   ├── logger.py                    # Loguru structured JSON/console logger with round tracing
│   └── circuit_breaker.py           # Balance floor guardian, DOM desync watchdog, and error counters
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                  # Mock event generators & fixtures
│   ├── test_models.py               # Unit tests for number-to-outcome mapping & data validation
│   ├── test_ladder.py               # Unit tests for 16-step progression, stakes, and exhaustion limits
│   ├── test_state_machine.py        # 100% coverage unit tests for FSM transitions and streaks
│   └── test_timing_window.py        # Unit tests for [25s .. 10s] timing gatekeeper
│
├── user_data/                       # Persistent Chromium context session directory (gitignored)
├── logs/                            # Audit and execution logs (gitignored)
└── main.py                          # CLI application entrypoint with signal handlers (SIGINT/SIGTERM)
```

---

## 3. Detailed Phased Implementation Breakdown

### Phase 1: Environment Setup & Pure Core Domain (Zero-I/O)
> **Goal:** Create project scaffolding and build the pure domain logic (models, ladder, FSM) with 100% unit test coverage before touching browser libraries.

- **Task 1.1: Project Scaffolding & Dependencies**
  - Create `.gitignore` to protect `user_data/`, `logs/`, `.env`, and virtual environments.
  - Create `requirements.txt` with:
    - `playwright>=1.43.0`
    - `playwright-stealth>=1.0.6`
    - `pydantic-settings>=2.2.1`
    - `loguru>=0.7.2`
    - `pytest>=8.1.1`
    - `pytest-asyncio>=0.23.6`
    - `pytest-cov>=5.0.0`
  - Create `.env.example` with standard defaults.

- **Task 1.2: Core Data Models (`core/models.py`)**
  - Implement `GameOutcome` Enum (`BIG`, `SMALL`).
  - Implement `GameOutcome.from_number(number: int)`:
    - $0..4 \to \text{SMALL}$
    - $5..9 \to \text{BIG}$
  - Implement `GameOutcome.opposite` property (`BIG.opposite == SMALL`, `SMALL.opposite == BIG`).
  - Implement `EngineState` Enum (`IDLE_OBSERVING`, `ACTIVE_BETTING`, `COOLDOWN`, `HALT`).
  - Implement frozen dataclasses: `RoundResolution`, `BetOrder`, `RoundData`, `StreakTracker`.

- **Task 1.3: Progression Ladder Engine (`core/ladder.py`)**
  - Define immutable tuple `BET_LADDER = (1, 3, 7, 15, 30, 35, 75, 150, 350, 750, 1500, 3500, 7000, 15000, 35000, 75000)`.
  - Define `MAX_LADDER_INDEX = 15`.
  - Implement `BetLadder` class:
    - `get_stake(index: int) -> int`
    - `is_exhausted(index: int) -> bool` (returns `True` if `index == MAX_LADDER_INDEX`)
    - `get_cumulative_risk(up_to_index: int) -> int`
    - `get_expected_payout(index: int) -> int`
    - `get_net_profit_on_win(index: int) -> int`

- **Task 1.4: Deterministic State Machine (`core/state_machine.py`)**
  - Implement pure `DeterministicStateMachine` class:
    - Internal state: `current_state`, `active_target`, `ladder_index`, `history_streak`, `last_bet_round_id`.
    - `on_round_resolved(resolution: RoundResolution) -> Optional[BetOrder]`
    - **Streak Trigger Rule:** 3 consecutive identical outcomes $\to$ transition `IDLE_OBSERVING` $\to$ `ACTIVE_BETTING`. Set `target = streak.opposite`, `ladder_index = 0`.
    - **Win Resolution Rule:** Target hit $\to$ reset `ladder_index = 0`, clear target, transition to `IDLE_OBSERVING`.
    - **Loss Resolution Rule (Steps 0–14):** Increment `ladder_index += 1`, maintain original target, maintain `ACTIVE_BETTING`.
    - **Loss Resolution Rule (Step 15 Exhaustion):** Reaching and losing Step 15 (16 consecutive losses) triggers **Hard Cycle Abort**. Reset `ladder_index = 0`, clear target, transition to `COOLDOWN`.
    - **Cooldown Resolution Rule:** Observing 1 full clean round in `COOLDOWN` transitions back to `IDLE_OBSERVING`.
    - **Idempotency Rule:** Prevent generating a bet order if `resolution.round_id <= last_bet_round_id`.

- **Task 1.5: Unit Testing Domain Suite (`tests/`)**
  - `tests/test_models.py`: Verify number-to-outcome mapping ($0-4, 5-9$, error on negative or $>9$).
  - `tests/test_ladder.py`: Verify all 16 stake steps, boundary handling, and cumulative sum ($138,416$ units).
  - `tests/test_state_machine.py`:
    - 3 Bigs trigger Small; 3 Smalls trigger Big.
    - Alternating outcomes never trigger active betting.
    - Consecutive losses increment ladder from 0 up to 15.
    - Loss at Step 15 transitions to `COOLDOWN` and resets index to 0.
    - Win at any step resets index to 0 and returns to `IDLE_OBSERVING`.
  - **Acceptance Criteria:** `pytest tests/ -v` passes 100% with $\ge 95\%$ domain code coverage.

---

### Phase 2: Configuration & Selector Abstraction
> **Goal:** Create typed settings and externalized selector definitions to isolate target website DOM variations.

- **Task 2.1: Typed Settings (`config/settings.py`)**
  - Implement Pydantic `Settings` model loading `.env`:
    - `BASE_URL: str`
    - `HEADLESS: bool = False`
    - `USER_DATA_DIR: Path = Path("./user_data")`
    - `MIN_TIMING_WINDOW_SEC: int = 10`
    - `MAX_TIMING_WINDOW_SEC: int = 25`
    - `POLL_INTERVAL_MS: int = 250`
    - `STOP_LOSS_BALANCE: float = 0.0`
    - `MAX_DESYNC_RETRIES: int = 3`

- **Task 2.2: Selector Registry (`config/selectors.py` & `config/selectors.json`)**
  - Create `SelectorTarget` dataclass (`css: str`, `xpath: Optional[str]`, `description: str`).
  - Create `AppSelectors` container class.
  - Create default `config/selectors.json` with multi-strategy fallbacks for:
    - `current_round_id`, `countdown_timer_seconds`, `history_table_rows`
    - `history_row_round_id`, `history_row_result_number`, `history_row_result_outcome`
    - `bet_button_big`, `bet_button_small`, `amount_input_field`
    - `confirm_bet_button`, `wallet_balance_display`, `bet_success_toast`, `bet_error_toast`
  - Implement JSON loader with validation.

---

### Phase 3: Browser Context & Anti-Detection Setup
> **Goal:** Provide reliable session persistence and anti-bot evasion.

- **Task 3.1: Persistent Browser Context Factory (`browser/context.py`)**
  - Implement `create_persistent_browser_context(settings: Settings) -> BrowserContext`:
    - Uses `async_playwright().chromium.launch_persistent_context()`.
    - Points to persistent `settings.USER_DATA_DIR`.
    - Sets desktop viewport ($1366 \times 768$), realistic User-Agent, locale, and timezone.
    - Disables automation blink features (`--disable-blink-features=AutomationControlled`).
  - Integrate `playwright-stealth` (`stealth_async`) on all newly opened pages.

- **Task 3.2: Interactive Operator Login CLI Command**
  - Implement `--login` workflow in `main.py`:
    - Opens visible browser window to `settings.BASE_URL`.
    - Prompts user in terminal: *"Please complete manual login in the browser window, then press [Enter] to save session..."*
    - Waits for operator input, verifies cookies and local storage are saved to `user_data/`, and closes cleanly.
  - **Acceptance Criteria:** Subsequent runs launch directly into authenticated session without login screens.

---

### Phase 4: Ingestion Pipeline & Timing Gatekeeper
> **Goal:** High-frequency, accurate DOM/network reading with strict timing boundary enforcement.

- **Task 4.1: Timing Gatekeeper (`browser/executor.py` / `core/timing.py`)**
  - Implement `TimingGatekeeper.is_within_window(countdown_sec: int) -> bool`:
    - Validates $10 \le \text{countdown\_sec} \le 25$.
    - Returns `False` if $T < 10$ or $T > 25$.
  - Implement `tests/test_timing_window.py` to assert edge cases ($9, 10, 25, 26$).

- **Task 4.2: Ingestion & Observer (`browser/observer.py`)**
  - Implement `DomObserver`:
    - `get_current_round_id(page: Page) -> Optional[str]`
    - `get_countdown_seconds(page: Page) -> Optional[int]`
    - `get_latest_history(page: Page, limit: int = 10) -> list[RoundResolution]`
  - Implement CDP Network Response Interceptor (where game sends WebSocket or JSON responses):
    - Intercepts outcome payloads to provide zero-latency resolution feeds.
  - Implement deduplication: Ignore events where `round_id <= last_processed_round_id`.
  - Implement clock desync detector: Warn if countdown fails to change over a 2-second sampling interval.

- **Task 4.3: Order Execution Engine (`browser/executor.py`)**
  - Implement `ActionExecutor`:
    - `human_click(page: Page, selector: SelectorTarget)`: Moves mouse along natural curve, adds $80\text{ms}-200\text{ms}$ delay before mousedown/mouseup.
    - `select_target(page: Page, target: GameOutcome)`: Clicks Big or Small button.
    - `set_amount(page: Page, amount: int)`: Handles input field filling or chip button multiplier sequences.
    - `confirm_bet(page: Page)`: Clicks submit/confirm button.
    - `verify_confirmation(page: Page) -> bool`: Waits for success toast or wallet balance deduction.
  - **Acceptance Criteria:** Reliable bet execution within the $[25\text{s}, 10\text{s}]$ window without lockout errors.

---

### Phase 5: Async Orchestration Runner & Circuit Breakers
> **Goal:** Tie all subsystems into a resilient, unattended execution loop.

- **Task 5.1: Safety Circuit Breakers (`utils/circuit_breaker.py`)**
  - `BalanceCircuitBreaker`: Checks wallet balance against `STOP_LOSS_BALANCE` and required stake. Halts if balance is insufficient.
  - `DesyncCircuitBreaker`: Counts consecutive DOM read failures. If count $\ge 3$, captures diagnostic screenshot (`logs/desync_{timestamp}.png`) and transitions to `HALT`.
  - `EmergencyKillSwitch`: Listens for operator abort (SIGINT / Ctrl+C) and terminates cleanly without leaving unconfirmed actions.

- **Task 5.2: Structured Audit Logger (`utils/logger.py`)**
  - Configure Loguru with colored console output and rotating JSON file logs (`logs/audit_{time}.log`).
  - Log format includes: `[Timestamp] [RoundID] [State] [Target] [LadderIndex] [Stake] [Outcome] [PnL]`.

- **Task 5.3: Orchestration Runner (`engine/runner.py`)**
  - Implements the continuous 30-second cycle loop:
    1. Poll `DomObserver` for `RoundID`, `Countdown (T)`, and `History`.
    2. Check for newly finished round $\to$ dispatch `ROUND_RESOLVED` to `DeterministicStateMachine`.
    3. Evaluate FSM output: If active bet required:
       - Check `TimingGatekeeper.is_within_window(T)`.
       - Check `BalanceCircuitBreaker.can_afford(stake)`.
       - If approved, invoke `ActionExecutor.execute_order(...)`.
       - Dispatch `BET_SUBMITTED` event to FSM to guarantee idempotency.
    4. Sleep for `settings.POLL_INTERVAL_MS` (250ms) to prevent CPU thrashing.

- **Task 5.4: Main CLI Entrypoint (`main.py`)**
  - Parse CLI arguments:
    - `python main.py --login`: Interactive session authentication.
    - `python main.py --run`: Live autonomous betting mode.
    - `python main.py --dry-run`: Live observation & state simulation without placing bets.
    - `python main.py --test-selectors`: Verifies DOM selectors on active page.
  - Graceful shutdown handlers for `SIGINT` (Ctrl+C) and `SIGTERM`.

---

### Phase 6: Operational Verification & Resilience Validation
> **Goal:** Verify end-to-end reliability under realistic network and DOM conditions.

- **Task 6.1: Unit Test Validation**
  - Run full test suite with coverage report: `pytest tests/ -v --cov=core --cov=utils`.
  - Assert 100% pass rate.
- **Task 6.2: Selector Calibration**
  - Run `python main.py --test-selectors` against live target site.
  - Adjust `config/selectors.json` if target site has non-standard class names.
- **Task 6.3: 30-Round Dry-Run Simulation**
  - Run `python main.py --dry-run` across 30 live consecutive rounds (15 minutes).
  - Verify zero state desynchronizations, zero double-bets, and accurate streak detection.
- **Task 6.4: Operations Manual (`README.md`)**
  - Write complete user guide: installation, login walkthrough, selector configuration, and live operation commands.

---

## 4. Verification & Testing Matrix

| Component | Target File | Verification Method | Success Criteria |
| :--- | :--- | :--- | :--- |
| **Data Models** | `core/models.py` | `pytest tests/test_models.py` | 100% type safety; $0-4 \to \text{Small}$, $5-9 \to \text{Big}$. |
| **Bet Ladder** | `core/ladder.py` | `pytest tests/test_ladder.py` | All 16 stakes match specification exactly; Step 15 detects exhaustion. |
| **State Machine** | `core/state_machine.py` | `pytest tests/test_state_machine.py` | 3-streak triggers opposite bet; wins reset index to 0; 15-loss aborts to cooldown. |
| **Timing Guard** | `browser/executor.py` | `pytest tests/test_timing_window.py` | Rejects $T < 10\text{s}$ or $T > 25\text{s}$; permits $10\text{s} \le T \le 25\text{s}$. |
| **Persistent Session** | `browser/context.py` | `python main.py --login` | User logs in once; cookies and session persist across restarts. |
| **DOM Ingestion** | `browser/observer.py` | `python main.py --test-selectors` | Successfully locates Round ID, countdown timer, and outcome history. |
| **End-to-End Simulation** | `engine/runner.py` | `python main.py --dry-run` | Runs 30 live rounds with zero exceptions or missed rounds. |

---

## 5. Risk Assessment & Mitigation Strategies

| Identified Risk | Severity | Technical Mitigation |
| :--- | :---: | :--- |
| **Network Latency / Lockout** | High | Hard $10\text{s}$ lower boundary gatekeeper prevents dispatching bets during final lockout countdown. |
| **DOM Re-render / Stale Triggers** | High | Strict `last_bet_round_id` tracking ensures exactly one bet order per unique Round ID. |
| **Rapid Capital Drawdown** | High | Hard cycle abort after Step 15 loss; balance circuit breaker halts execution if balance drops below threshold. |
| **Bot Detection / CAPTCHA** | Medium | `launch_persistent_context` retains legitimate login session; `playwright-stealth` masks automation flags; humanized click delays. |
| **UI Class Name Changes** | Medium | `config/selectors.json` abstracts all selectors with primary CSS and fallback XPath definitions. |

---

## 6. Next Steps & Approval

1. **Review:** Review this implementation plan.
2. **Approval:** Upon your approval, we will execute **Phase 1** (Project Scaffolding, Core Models, Progression Ladder, State Machine, and Unit Tests).
