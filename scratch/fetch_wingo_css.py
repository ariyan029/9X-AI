import urllib.request
import re

url = "https://www.veergame41.com/assets/css/index-CdLc6FvL.css"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
try:
    with urllib.request.urlopen(req) as resp:
        content = resp.read().decode("utf-8", errors="ignore")
    print(f"Downloaded CSS, length: {len(content)}")
    with open("scratch/wingo.css", "w", encoding="utf-8") as f:
        f.write(content)
    
    classes = re.findall(r'\.([a-zA-Z0-9_-]+)', content)
    print("Total CSS classes:", len(classes))
    unique_classes = sorted(set(classes))
    for c in unique_classes:
        if any(k in c.lower() for k in ["bet", "btn", "time", "clock", "num", "record", "balance", "wallet", "big", "small", "head", "foot", "item"]):
            print(" ", c)
except Exception as e:
    print("Error:", e)
