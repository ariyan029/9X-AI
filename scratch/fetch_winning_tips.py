import urllib.request
import re

url = "https://www.veergame41.com/assets/js/WinningTips-iqUy0PvK.js"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
try:
    with urllib.request.urlopen(req) as resp:
        content = resp.read().decode("utf-8", errors="ignore")
    print(f"Downloaded WinningTips file, length: {len(content)}")
    with open("scratch/winning_tips.js", "w", encoding="utf-8") as f:
        f.write(content)
    
    classes = re.findall(r'class[=:]\s*["\']([^"\']+)["\']', content)
    print("Classes in WinningTips:")
    for c in sorted(set(classes))[:60]:
        print(" ", c)
except Exception as e:
    print("Error:", e)
