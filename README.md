# 9X-AI: Deterministic Event-Driven Browser Automation Bot

> **Target Platform:** Python 3.10+ | Asyncio | Playwright (Async API) | Playwright-Stealth  
> **Status:** Production-Ready Core & Testing Suite Verified

---

## 1. Overview

**9X-AI** is an event-driven, deterministic browser automation bot designed to interface with live 30-second cycle prediction games (Big/Small outcome prediction). The engine enforces a strict separation between **pure domain logic** (finite state machine, risk progression ladder, circuit breakers) and **impure I/O mechanisms** (browser drivers, DOM observers, network listeners, input dispatchers).

### Core Features
- **Deterministic State Machine:** Pure functional state transitions. Decoupled from all browser and network dependencies.
- **3-Streak Trigger Rule:** Waits for 3 consecutive identical outcomes (`Big` or `Small`), then triggers an active betting cycle on the opposite outcome.
- **Fixed 16-Step Risk Ladder:** Martingale-style risk sequence with a hard cycle abort at Step 15 (max 16 consecutive losses) to prevent account blowouts.
- **Strict Timing Gatekeeper:** Enforces a safe betting window $[10\text{s}, 25\text{s}]$ within each 30-second cycle. Automatically suppresses execution during the final 9 seconds to prevent lockout rejections.
- **Anti-Fingerprint Stealth & Session Persistence:** Uses `launch_persistent_context` to retain human login sessions across runs, combined with `playwright-stealth` to evade bot detection.
- **Safety Circuit Breakers:** Real-time wallet balance floor guard, consecutive DOM desync detector with automatic screenshot/DOM dumps, and clean `SIGINT` (Ctrl+C) shutdown.

---

## 2. 16-Step Progression Ladder

$$\text{Ladder} = [1, 3, 7, 15, 30, 35, 75, 150, 350, 750, 1500, 3500, 7000, 15000, 35000, 75000]$$

| Step | Stake (Units) | Cumulative Risk | Payout (2x) | Net Profit on Win | Note |
| :---: | :---: | :---: | :---: | :---: | :--- |
| **0** | **1** | 1 | 2 | +1 | Cycle start |
| **1** | **3** | 4 | 6 | +2 | |
| **2** | **7** | 11 | 14 | +3 | |
| **3** | **15** | 26 | 30 | +4 | |
| **4** | **30** | 56 | 60 | +4 | |
| **5** | **35** | 91 | 70 | -21 | *Recovery mitigation* |
| **6** | **75** | 166 | 150 | -16 | *Recovery mitigation* |
| **7** | **150** | 316 | 300 | -16 | *Recovery mitigation* |
| **8** | **350** | 666 | 700 | +34 | |
| **9** | **750** | 1,416 | 1,500 | +84 | |
| **10** | **1,500** | 2,916 | 3,000 | +84 | |
| **11** | **3,500** | 6,416 | 7,000 | +584 | |
| **12** | **7,000** | 13,416 | 14,000 | +584 | |
| **13** | **15,000** | 28,416 | 30,000 | +1,584 | |
| **14** | **35,000** | 63,416 | 70,000 | +6,584 | |
| **15** | **75,000** | **138,416** | 150,000 | **+11,584** | Final ladder step |

> **Hard Cycle Abort:** If Step 15 loses (16 total consecutive losses), the cycle aborts immediately. Total capital loss of 138,416 is registered to the audit log, the ladder index resets to 0, and the engine drops into `COOLDOWN` for 1 round before returning to `IDLE_OBSERVING`.

---

## 3. Project Architecture

```
d:\9X-AI\
├── main.py                     # CLI entrypoint (--login, --run, --dry-run, --test-selectors)
├── config/
│   ├── settings.py             # Pydantic v2 typed settings (.env loader)
│   ├── selectors.py            # SelectorTarget & AppSelectors dataclasses
│   └── selectors.json          # Abstracted CSS/XPath UI element targets
├── core/
│   ├── models.py               # Pure domain models (GameOutcome, RoundResolution, BetOrder)
│   ├── ladder.py               # Immutable 16-step risk sequence & profit calculators
│   └── state_machine.py        # Pure deterministic FSM (streak triggers, win/loss transitions)
├── browser/
│   ├── context.py              # Persistent browser context factory with stealth injection
│   ├── observer.py             # DOM scraper, CDP network interceptor, clock desync detector
│   └── executor.py             # Timing gatekeeper [10s-25s], humanized click & input dispatcher
├── engine/
│   └── runner.py               # Async orchestration loop linking observer, FSM & executor
├── utils/
│   ├── circuit_breaker.py      # Balance floor guardian & desync diagnostics recorder
│   └── logger.py               # Loguru console, JSONL structured, and rotating audit logging
├── tests/                      # Automated unit test suite (200+ tests, 100% domain coverage)
└── user_data/                  # Persistent Chromium session profile (gitignored)
```

---

## 4. Installation & Setup

### Prerequisites
- Python 3.10, 3.11, 3.12, or 3.13
- Node.js / Playwright browser binaries

### Step 1: Create Virtual Environment
```powershell
python -m venv venv
.\venv\Scripts\activate
```

### Step 2: Install Dependencies
```powershell
pip install -r requirements.txt
playwright install chromium
```

### Step 3: Configure Environment
Copy [.env.example](file:///d:/9X-AI/.env.example) to `.env` and set your parameters:
```powershell
Copy-Item .env.example .env
```

| Variable | Default | Description |
| :--- | :--- | :--- |
| `BASE_URL` | `https://example-game.com` | Target web application URL |
| `HEADLESS` | `false` | Run browser headlessly (`false` recommended for calibration) |
| `USER_DATA_DIR` | `./user_data` | Persistent Chromium directory for session cookies |
| `MIN_TIMING_WINDOW_SEC` | `10` | Earliest seconds remaining to lock out bets (lower bound) |
| `MAX_TIMING_WINDOW_SEC` | `25` | Maximum seconds remaining to begin betting (upper bound) |
| `POLL_INTERVAL_MS` | `250` | DOM polling frequency in milliseconds |
| `STOP_LOSS_BALANCE` | `0.0` | Minimum wallet balance threshold before triggering HALT |
| `MAX_DESYNC_RETRIES` | `3` | Maximum consecutive DOM errors before triggering HALT |

---

## 5. Operations & CLI Usage

### 1. Interactive Operator Authentication (`--login`)
Launch a visible browser to log into your account manually. Session cookies, tokens, and local storage will be saved to `user_data/`:
```powershell
python main.py --login
```
*Complete your login in the browser window, then press `[Enter]` in the terminal to save your session.*

### 2. Verify & Calibrate Selectors (`--test-selectors`)
Verify whether all DOM selectors in `config/selectors.json` match your target game page:
```powershell
python main.py --test-selectors
```
*If any elements fail, adjust `config/selectors.json` with the CSS or XPath tags specific to your target site.*

### 3. Dry-Run Paper Trading Simulation (`--dry-run`)
Run the bot in live observation mode without placing real bets. The engine observes live rounds, tracks streaks, evaluates FSM transitions, and logs projected bets:
```powershell
python main.py --dry-run
```

### 4. Autonomous Live Betting (`--run`)
Start autonomous live betting with full circuit breaker enforcement:
```powershell
python main.py --run
```
*To stop the bot at any time, press `Ctrl+C`. The clean signal handler ensures in-flight operations are finalized safely.*

---

## 6. Running Tests & Code Quality

Run the test suite with coverage:
```powershell
pytest --cov=. --cov-report=term-missing
```

All 200+ unit tests across data models, 16-step ladder progression, state machine transitions, timing gatekeeper, selector loaders, settings, and circuit breakers execute in under 2 seconds.

---

## 7. Progress & Audit Logs

For detailed status reports, historical changelogs, architecture diagrams, and next-step guides, refer to [reportand updates.md](file:///d:/9X-AI/reportand%20updates.md).
