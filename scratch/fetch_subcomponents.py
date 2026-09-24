import urllib.request
import re

for filename in ["assets/js/index-BVp5fOMo.js", "assets/js/index-O2Pfy0KS.js"]:
    url = f"https://www.veergame41.com/{filename}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
        print(f"Downloaded {filename}, length: {len(content)}")
        classes = re.findall(r'class[=:]\s*["\']([^"\']+)["\']', content)
        print(f"Classes in {filename}:")
        for c in sorted(set(classes))[:30]:
            print(" ", c)
    except Exception as e:
        print("Error for", filename, e)
