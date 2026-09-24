with open("scratch/wingo_module.js", encoding="utf-8") as f:
    text = f.read()

import re
matches = re.findall(r'["\']([^"\']*(?:big|small|green|red|violet|bet)[^"\']*)["\']', text, re.I)
print("Matches in wingo_module.js:", str(set(matches)).encode('ascii', errors='replace').decode('ascii'))

# Look for sub-components loaded by index-D7Htd0-t.js
sub_components = re.findall(r'import\s*\(\s*["\']([^"\']+)["\']', text)
print("Sub-components:", sub_components)
