import urllib.request
import re

url = "https://www.veergame41.com/assets/js/wingo-CbNOwbhj.js"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
try:
    with urllib.request.urlopen(req) as resp:
        content = resp.read().decode("utf-8", errors="ignore")
    print("Wingo file length:", len(content))
    with open("scratch/wingo_bet.js", "w", encoding="utf-8") as f:
        f.write(content)
    
    classes = re.findall(r'class[=:]\s*["\']([^"\']+)["\']', content)
    print("Classes in wingo-CbNOwbhj:")
    for c in sorted(set(classes))[:40]:
        print(" ", c)
except Exception as e:
    print("Error:", e)
