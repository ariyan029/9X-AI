import urllib.request
import re

url = "https://www.veergame41.com/assets/js/index-DtsNZcBk.js"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
try:
    with urllib.request.urlopen(req) as resp:
        content = resp.read().decode("utf-8", errors="ignore")
    print("Bundle length:", len(content))
    with open("scratch/bundle.js", "w", encoding="utf-8") as f:
        f.write(content)
    
    # Search for wingo routes
    routes = re.findall(r'path:\s*["\'`]([^"\'`]+)["\'`]', content)
    wingo_routes = [r for r in routes if any(k in r.lower() for k in ["win", "lottery", "game", "go"])]
    print("Found routes:", set(wingo_routes[:30]))
    
    # Search for WinGo mentions in bundle
    wingo_mentions = re.findall(r'[\w/?:=_-]{0,30}wingo[\w/?:=_-]{0,30}', content, re.I)
    print("WinGo mentions:", set(wingo_mentions[:20]))
except Exception as e:
    print("Error:", e)
