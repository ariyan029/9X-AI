with open("scratch/bundle.js", encoding="utf-8") as f:
    text = f.read()

import re
matches = [m.start() for m in re.finditer(r'["\']WinGo["\']', text)]
print(f"Found {len(matches)} occurrences of 'WinGo'")
for idx in matches:
    print("--- CONTEXT ---")
    print(text[max(0, idx-100):min(len(text), idx+150)])
