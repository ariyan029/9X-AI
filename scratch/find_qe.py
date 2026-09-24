with open("scratch/wingo_module.js", encoding="utf-8") as f:
    text = f.read()

import re
pos = text.find('Betting:qe')
print(text[pos-400:pos+100].encode('ascii', errors='replace').decode('ascii'))
