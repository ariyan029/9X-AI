with open("scratch/bundle.js", encoding="utf-8") as f:
    text = f.read()

import re
pos = text.find('__vite__mapDeps([212')
if pos != -1:
    print("Found mapDeps:")
    print(text[pos-100:pos+300])

# Find the mapDeps array definition
pos2 = text.find('function __vite__mapDeps')
if pos2 != -1:
    print("Found mapDeps def:")
    print(text[pos2:pos2+1000])
else:
    # Look for the array of filenames passed to mapDeps
    matches = re.findall(r'\[(?:\s*"(?:assets/)?(?:js/)?[\w.-]+\.js"\s*,?)+\]', text)
    print("Found dep arrays:", len(matches))
    for m in matches[:5]:
        print(m[:200])
