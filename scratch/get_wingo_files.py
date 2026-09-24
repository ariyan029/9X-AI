with open("scratch/bundle.js", encoding="utf-8") as f:
    text = f.read()

import re
pos = text.find('m.f=[')
if pos != -1:
    end = text.find(']', pos)
    array_str = text[pos+4:end+1]
    import json
    files = json.loads(array_str)
    wingo_indices = [212, 164, 165, 213, 12, 13, 214, 166, 195, 181, 182, 196, 46, 47, 48, 49, 171, 172, 215]
    print("Files for WinGo:")
    for idx in wingo_indices:
        if idx < len(files):
            print(f"  [{idx}]: {files[idx]}")
