with open("scratch/page_dump.html", encoding="utf-8") as f:
    text = f.read()

import re
indices = [m.start() for m in re.finditer(r'wingo', text, re.I)]
print(f"Found {len(indices)} occurrences of wingo")
for idx in indices[:5]:
    start = max(0, idx - 100)
    end = min(len(text), idx + 200)
    print("--- CONTEXT ---")
    print(text[start:end])
