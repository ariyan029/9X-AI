with open("scratch/page_dump.html", encoding="utf-8") as f:
    text = f.read()

import re
matches = re.findall(r'<div[^>]*class="[^"]*dialog[^"]*"[^>]*>.*?</div\s*>', text, re.DOTALL)
print(f"Found {len(matches)} dialog divs")

# Search for announcement-dialog
pos = text.find("announcement-dialog")
if pos != -1:
    print("Found announcement-dialog:")
    print(text[pos-100:pos+400].encode('ascii', errors='replace').decode('ascii'))

# Search for close button in dialog
pos2 = text.find("dialog-queue-host")
if pos2 != -1:
    print("Found dialog-queue-host:")
    print(text[pos2-50:pos2+500].encode('ascii', errors='replace').decode('ascii'))
