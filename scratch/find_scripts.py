with open("scratch/page_dump.html", encoding="utf-8") as f:
    text = f.read()

import re
scripts = re.findall(r'src=["\']([^"\']+\.js[^"\']*)["\']', text)
print(f"Found {len(scripts)} scripts")
for s in scripts[:10]:
    print(s)
