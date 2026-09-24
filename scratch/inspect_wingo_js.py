with open("scratch/wingo_module.js", encoding="utf-8") as f:
    text = f.read()

import re
# Print all class="..." strings
classes = re.findall(r'class[=:]\s*["\']([^"\']+)["\']', text)
print("All classes in wingo_module.js:")
for c in sorted(set(classes)):
    print(" ", c)

# Search for any other imported js files
imports = re.findall(r'import\s*\(\s*["\']\./([^"\']+)["\']', text)
print("Other imports:", imports)
