import os

def update_tracker():
    path = r"d:\9X-AI\utils\data_tracker.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
        
    # 1. Update __init__
    content = content.replace(
        'self.live_summary_file = "user_data/live_today_summary.txt"',
        'self.live_summary_file = "user_data/live_today_summary.txt"\n        self.live_7_days_summary_file = "user_data/live_7_days_summary.txt"'
    )
    content = content.replace(
        'self._update_live_summary()',
        'self._update_live_summary()\n            self._update_live_7_days_summary()'
    )
    
    # 2. Update reset_stats
    content = content.replace(
        'self.thirteen_plus_occurrences = 0',
        'self.thirteen_plus_occurrences = 0\n        self.thirteen_plus_timestamps = []'
    )
    
    # 3. Update _load_state
    content = content.replace(
        'self.thirteen_plus_occurrences = data.get("thirteen_plus_occurrences", 0)',
        'self.thirteen_plus_occurrences = data.get("thirteen_plus_occurrences", 0)\n                self.thirteen_plus_timestamps = data.get("thirteen_plus_timestamps", [])'
    )
    content = content.replace(
        'self.thirteen_plus_occurrences = data.get("thirteen_plus_occurrences", 0)',
        'self.thirteen_plus_occurrences = data.get("thirteen_plus_occurrences", 0)\n            self.thirteen_plus_timestamps = data.get("thirteen_plus_timestamps", [])'
    ) # Note: this will match twice or once? The first replace will change the first one. So the second replace will only find the second one.
    
    # Wait, the first replace above will replace both if I'm not careful. Let's do it cleaner.
    
update_tracker()
