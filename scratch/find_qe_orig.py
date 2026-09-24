with open("scratch/wingo_module.js", encoding="utf-8") as f:
    text = f.read()

import re
matches = re.findall(r'[a-zA-Z0-9_$]+\s+as\s+qe', text)
print("import as qe:", matches)
matches2 = re.findall(r'\bqe\s*=\s*[^,;]+', text)
print("qe =", matches2)
matches3 = re.findall(r'const\s+[^=]*\bqe\b[^=]*=', text)
print("const qe:", matches3)
