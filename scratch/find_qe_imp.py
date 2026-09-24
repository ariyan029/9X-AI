with open("scratch/wingo_module.js", encoding="utf-8") as f:
    text = f.read()

import re
matches = re.findall(r'\bqe\s*=\s*[^,;()]+', text)
print("qe assignments:", matches)

# Find all imports in wingo_module.js
imports = re.findall(r'import\s*\{[^}]+\}\s*from\s*["\']([^"\']+)["\']', text)
print("Imports from:", imports)
