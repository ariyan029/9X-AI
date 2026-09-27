import time
import csv
import os
from datetime import datetime
from loguru import logger
from core.models import GameOutcome

class BettingDataTracker:
    """
    Tracks betting data metrics:
    1. Total Big and Total Small per day.
    2. Highest streak of Big and Small per day.
    3. Daily frequency of streaks (1 to 20).
    4. Count of 9+ streaks in a day.
    5. Average rounds between 13+ streaks in a day.
    
    Resets every 24 hours and stores history in a CSV file.
    """
    def __init__(self, filename="user_data/betting_stats.csv"):
        self.filename = filename
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        self.start_time = time.time()
        self.reset_stats()
        
        # Initialize file with headers if it doesn't exist
        if not os.path.exists(self.filename):
            self._write_headers()

    def _write_headers(self):
        with open(self.filename, 'w', newline='') as f:
            writer = csv.writer(f)
            headers = [
                "Timestamp",
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
        self.streak_frequency = {i: 0 for i in range(1, 21)}
        self.nine_plus_streak_count = 0
        self.total_rounds = 0
        self.thirteen_plus_occurrences = 0
        
        self.current_streak_type = None
        self.current_streak_length = 0
        logger.info("BettingDataTracker: Stats have been reset for the new 24-hour cycle.")

    def save_to_file(self):
        # Calculate average rounds per 13+ streak
        avg_13_plus = (self.total_rounds / self.thirteen_plus_occurrences) if self.thirteen_plus_occurrences > 0 else 0.0
        
        with open(self.filename, 'a', newline='') as f:
            writer = csv.writer(f)
            row = [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                self.total_big,
                self.total_small,
                self.highest_streak_big,
                self.highest_streak_small,
                self.nine_plus_streak_count,
                f"{avg_13_plus:.2f}"
            ]
            for i in range(1, 21):
                row.append(self.streak_frequency.get(i, 0))
            writer.writerow(row)
        logger.info(f"BettingDataTracker: 24-hour cycle completed. Data saved to {self.filename}")

    def process_outcome(self, outcome: GameOutcome):
        # Check if 24 hours (86400 seconds) have passed
        if time.time() - self.start_time >= 86400:
            self.record_streak(finalize=True)
            self.save_to_file()
            self.start_time = time.time()
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
                
        # Update frequency array
        capped_length = min(length, 20)
        self.streak_frequency[capped_length] += 1
        
        # Check for 9+ streak
        if length >= 9:
            self.nine_plus_streak_count += 1
            
        # Check for 13+ streak
        if length >= 13:
            self.thirteen_plus_occurrences += 1
            
        if finalize:
            self.current_streak_length = 0
            self.current_streak_type = None

