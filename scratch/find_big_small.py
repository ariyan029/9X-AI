with open("scratch/bundle.js", encoding="utf-8") as f:
    text = f.read()

import re
# Find mentions of "Big" and "Small" in relation to classes or buttons
big_matches = [m.start() for m in re.finditer(r'["\']Big["\']', text)]
print(f"Found {len(big_matches)} occurrences of 'Big'")
for idx in big_matches[:8]:
    print("--- CONTEXT ---")
    print(text[max(0, idx-80):min(len(text), idx+120)])
