with open("scratch/bundle.js", encoding="utf-8") as f:
    text = f.read()

import re
matches = re.findall(r'["\']assets/js/[^"\']*bet[^"\']*\.js["\']', text, re.I)
print("Bet js files:", set(matches))

matches_lottery = re.findall(r'["\']assets/js/[^"\']*lottery[^"\']*\.js["\']', text, re.I)
print("Lottery js files:", set(matches_lottery))

# Search for AllLotteryGames components
matches_all = re.findall(r'["\']assets/js/[^"\']*AllLottery[^"\']*\.js["\']', text, re.I)
print("AllLottery js files:", set(matches_all))
