import urllib.request
import re

url = "https://www.veergame41.com/assets/js/audio-D6hVYlBi.js"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
try:
    with urllib.request.urlopen(req) as resp:
        content = resp.read().decode("utf-8", errors="ignore")
    print(f"Downloaded audio file, length: {len(content)}")
    classes = re.findall(r'class[=:]\s*["\']([^"\']+)["\']', content)
    print("Classes in audio-D6hVYlBi:")
    for c in sorted(set(classes))[:40]:
        print(" ", c)
except Exception as e:
    print("Error:", e)
