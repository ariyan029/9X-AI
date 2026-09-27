import time
import csv
import json
import os
from datetime import datetime
from loguru import logger
from core.models import GameOutcome

class BettingDataTracker:
    """
    Tracks betting data metrics over continuous 24-hour cycles:
    1. Total Big and Total Small per day.
    2. Highest streak of Big and Small per day.
    3. Daily frequency of streaks (1 to 20).
    4. Count of 9+ streaks in a day.
    5. Average rounds between 13+ streaks in a day.
    
    Persistence features:
    - Maintains state in 'user_data/tracker_state.json' on every round.
    - If the computer stops or restarts mid-day, it resumes without losing data.
    - If more than 24h passed while computer was off, it archives the saved progress
      to CSV and starts a new 24h cycle cleanly.
    - Writes live real-time metrics to 'user_data/live_today_summary.txt' for easy viewing.
    """
    def __init__(self, filename="user_data/betting_stats.csv", state_file="user_data/tracker_state.json"):
        self.filename = filename
        self.state_file = state_file
        self.live_summary_file = "user_data/live_today_summary.txt"
        
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        if not os.path.exists(self.filename):
            self._write_headers()

        # Attempt to resume from saved state
        if not self._load_state():
            self.cycle_start_time = time.time()
            self.reset_stats()
            self._save_state()
            self._update_live_summary()

    def _write_headers(self):
        with open(self.filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            headers = [
                "Cycle Start",
                "Cycle End / Archived",
                "Total Big",
                "Total Small",
                "Highest Streak Big",
                "Highest Streak Small",
                "9+ Streaks Count",
                "Avg Rounds per 13+ Streak"
            ]
            for i in range(1, 21):
                headers.append(f"Streak {i} Freq")
            writer.writerow(headers)

    def reset_stats(self):
        self.total_big = 0
        self.total_small = 0
        self.highest_streak_big = 0
        self.highest_streak_small = 0
        self.streak_frequency = {str(i): 0 for i in range(1, 21)}
        self.nine_plus_streak_count = 0
        self.total_rounds = 0
        self.thirteen_plus_occurrences = 0
        
        self.current_streak_type = None
        self.current_streak_length = 0
        logger.info("BettingDataTracker: Initialized fresh 24-hour cycle.")

    def _load_state(self) -> bool:
        """Loads state from JSON. Returns True if successfully resumed."""
        if not os.path.exists(self.state_file):
            return False
        
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            saved_start = data.get("cycle_start_time", time.time())
            elapsed = time.time() - saved_start
            
            # If 24 hours have already elapsed while computer was turned off
            if elapsed >= 86400:
                logger.info(
                    f"BettingDataTracker: Previous cycle started at "
                    f"{data.get('cycle_start_datetime')} has expired ({elapsed/3600:.1f} hrs ago). "
                    "Archiving saved data to CSV and starting new cycle."
                )
                self.cycle_start_time = saved_start
                self.total_big = data.get("total_big", 0)
                self.total_small = data.get("total_small", 0)
                self.highest_streak_big = data.get("highest_streak_big", 0)
                self.highest_streak_small = data.get("highest_streak_small", 0)
                self.streak_frequency = data.get("streak_frequency", {str(i): 0 for i in range(1, 21)})
                self.nine_plus_streak_count = data.get("nine_plus_streak_count", 0)
                self.total_rounds = data.get("total_rounds", 0)
                self.thirteen_plus_occurrences = data.get("thirteen_plus_occurrences", 0)
                self.current_streak_type = None
                self.current_streak_length = 0
                
                # Archive expired cycle
                self.save_to_csv(archive_reason="Cycle completed (while offline or at startup)")
                
                # Reset for new cycle
                self.cycle_start_time = time.time()
                self.reset_stats()
                self._save_state()
                self._update_live_summary()
                return True

            # If still within the 24-hour cycle window, resume!
            self.cycle_start_time = saved_start
            self.total_big = data.get("total_big", 0)
            self.total_small = data.get("total_small", 0)
            self.highest_streak_big = data.get("highest_streak_big", 0)
            self.highest_streak_small = data.get("highest_streak_small", 0)
            self.streak_frequency = data.get("streak_frequency", {str(i): 0 for i in range(1, 21)})
            self.nine_plus_streak_count = data.get("nine_plus_streak_count", 0)
            self.total_rounds = data.get("total_rounds", 0)
            self.thirteen_plus_occurrences = data.get("thirteen_plus_occurrences", 0)
            
            c_type = data.get("current_streak_type")
            self.current_streak_type = GameOutcome(c_type) if c_type else None
            self.current_streak_length = data.get("current_streak_length", 0)
            
            remaining_hrs = (86400 - elapsed) / 3600
            logger.success(
                f"BettingDataTracker: Successfully resumed active cycle! "
                f"Started at {data.get('cycle_start_datetime')}. "
                f"Remaining in this 24h cycle: {remaining_hrs:.2f} hours."
            )
            self._update_live_summary()
            return True
        except Exception as e:
            logger.error(f"BettingDataTracker: Failed to load state ({e}). Starting fresh.")
            return False

    def _save_state(self):
        """Persists current cycle state to JSON after every round."""
        state = {
            "cycle_start_time": self.cycle_start_time,
            "cycle_start_datetime": datetime.fromtimestamp(self.cycle_start_time).strftime("%Y-%m-%d %H:%M:%S"),
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_rounds": self.total_rounds,
            "total_big": self.total_big,
            "total_small": self.total_small,
            "highest_streak_big": self.highest_streak_big,
            "highest_streak_small": self.highest_streak_small,
            "nine_plus_streak_count": self.nine_plus_streak_count,
            "thirteen_plus_occurrences": self.thirteen_plus_occurrences,
            "current_streak_type": self.current_streak_type.value if self.current_streak_type else None,
            "current_streak_length": self.current_streak_length,
            "streak_frequency": self.streak_frequency,
        }
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.warning(f"BettingDataTracker: Could not save state: {e}")

    def _update_live_summary(self):
        """Generates a clean human-readable live summary table file."""
        elapsed = time.time() - self.cycle_start_time
        remaining = max(0, 86400 - elapsed)
        avg_13_plus = (self.total_rounds / self.thirteen_plus_occurrences) if self.thirteen_plus_occurrences > 0 else 0.0

        content = (
            "==========================================================\n"
            "              24-HOUR LIVE BETTING TRACKER                \n"
            "==========================================================\n"
            f"Cycle Started   : {datetime.fromtimestamp(self.cycle_start_time).strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Current Time    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Time Elapsed    : {elapsed / 3600:.2f} hrs (Remaining: {remaining / 3600:.2f} hrs)\n"
            f"Total Rounds    : {self.total_rounds}\n"
            "----------------------------------------------------------\n"
            f"Total BIG       : {self.total_big}\n"
            f"Total SMALL     : {self.total_small}\n"
            f"Highest BIG Streak   : {self.highest_streak_big}\n"
            f"Highest SMALL Streak : {self.highest_streak_small}\n"
            f"Current Active Streak: {self.current_streak_type.value if self.current_streak_type else 'None'} x {self.current_streak_length}\n"
            f"9+ Streaks Count     : {self.nine_plus_streak_count}\n"
            f"13+ Streak Occurred  : {self.thirteen_plus_occurrences} times (Avg every {avg_13_plus:.1f} rounds)\n"
            "----------------------------------------------------------\n"
            "STREAK FREQUENCY DISTRIBUTION (1 to 20):\n"
        )
        for i in range(1, 21):
            count = self.streak_frequency.get(str(i), 0)
            content += f"  Streak of {i:2d} : {count:4d} times\n"
        content += "==========================================================\n"

        try:
            with open(self.live_summary_file, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception:
            pass

    def save_to_csv(self, archive_reason=""):
        avg_13_plus = (self.total_rounds / self.thirteen_plus_occurrences) if self.thirteen_plus_occurrences > 0 else 0.0
        start_dt = datetime.fromtimestamp(self.cycle_start_time).strftime("%Y-%m-%d %H:%M:%S")
        end_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(self.filename, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            row = [
                start_dt,
                end_dt,
                self.total_big,
                self.total_small,
                self.highest_streak_big,
                self.highest_streak_small,
                self.nine_plus_streak_count,
                f"{avg_13_plus:.2f}"
            ]
            for i in range(1, 21):
                row.append(self.streak_frequency.get(str(i), 0))
            writer.writerow(row)
            
        logger.info(f"BettingDataTracker: Cycle saved to {self.filename} ({archive_reason})")

    def process_outcome(self, outcome: GameOutcome):
        # 1. Check if 24 hours have elapsed
        if time.time() - self.cycle_start_time >= 86400:
            self.record_streak(finalize=True)
            self.save_to_csv(archive_reason="24-Hour Timer Expiry")
            self.cycle_start_time = time.time()
            self.reset_stats()

        self.total_rounds += 1
        
        if outcome == GameOutcome.BIG:
            self.total_big += 1
        elif outcome == GameOutcome.SMALL:
            self.total_small += 1
            
        if self.current_streak_type == outcome:
            self.current_streak_length += 1
        else:
            self.record_streak(finalize=False)
            self.current_streak_type = outcome
            self.current_streak_length = 1

        # Real-time state persistence & live readable view update
        self._save_state()
        self._update_live_summary()

    def record_streak(self, finalize=False):
        if self.current_streak_type is None or self.current_streak_length == 0:
            return
            
        length = self.current_streak_length
        otype = self.current_streak_type
        
        # Update highest streak
        if otype == GameOutcome.BIG:
            if length > self.highest_streak_big:
                self.highest_streak_big = length
        elif otype == GameOutcome.SMALL:
            if length > self.highest_streak_small:
                self.highest_streak_small = length
                
        # Update frequency
        capped_length = min(length, 20)
        str_key = str(capped_length)
        self.streak_frequency[str_key] = self.streak_frequency.get(str_key, 0) + 1
        
        # 9+ streak count
        if length >= 9:
            self.nine_plus_streak_count += 1
            
        # 13+ streak occurrences
        if length >= 13:
            self.thirteen_plus_occurrences += 1
            
        if finalize:
            self.current_streak_length = 0
            self.current_streak_type = None
