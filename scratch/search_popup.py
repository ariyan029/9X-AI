with open("scratch/bundle.js", encoding="utf-8") as f:
    text = f.read()

import re
matches = re.findall(r'["\']assets/js/[^"\']*popup[^"\']*\.js["\']', text, re.I)
print("Popup js files:", set(matches))

matches_game = re.findall(r'["\']assets/js/[^"\']*game[^"\']*\.js["\']', text, re.I)
print("Game js files:", set(matches_game))
