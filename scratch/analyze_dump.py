import re

with open("scratch/page_dump.html", encoding="utf-8") as f:
    text = f.read()

print("Has WinGo:", "wingo" in text.lower())
print("Has lottery:", "lottery" in text.lower())

# Look for router paths or hash links
matches = re.findall(r'["\'](/#/home/[^"\']+)["\']', text)
print("Home matches:", set(matches))

matches_all = re.findall(r'["\'](/#[^"\']+)["\']', text)
print("Sample hash routes:", list(set(matches_all))[:20])

# Look for game names
names = re.findall(r'[\w\s]{2,20}(?:Win Go|Wingo|Lottery|K3|5D)[\w\s]{0,20}', text, re.IGNORECASE)
print("Game names:", set(names[:10]))
