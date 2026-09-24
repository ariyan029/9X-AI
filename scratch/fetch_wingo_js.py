import urllib.request
import re

url = "https://www.veergame41.com/assets/js/index-D7Htd0-t.js"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
try:
    with urllib.request.urlopen(req) as resp:
        content = resp.read().decode("utf-8", errors="ignore")
    print("WinGo module length:", len(content))
    with open("scratch/wingo_module.js", "w", encoding="utf-8") as f:
        f.write(content)
    
    # Search for class names in wingo module
    classes = re.findall(r'class:\s*["\']([^"\']+)["\']', content)
    print("Total classes found:", len(classes))
    print("Sample classes:", list(set(classes))[:30])
    
    # Search for button / bet / time / timer / issue / period
    keywords = ["timer", "period", "issue", "time", "count", "big", "small", "bet", "balance"]
    for kw in keywords:
        matches = re.findall(rf'class:\s*["\'][^"\']*{kw}[^"\']*["\']', content, re.I)
        print(f"Classes with '{kw}':", set(matches[:5]))
except Exception as e:
    print("Error:", e)
