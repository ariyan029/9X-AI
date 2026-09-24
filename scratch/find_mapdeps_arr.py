with open("scratch/bundle.js", encoding="utf-8") as f:
    text = f.read()

pos = text.find('__vite__mapDeps=')
if pos == -1:
    pos = text.find('__vite__mapDeps =')
if pos == -1:
    pos = text.find('__vite__mapDeps')
print(pos)
if pos != -1:
    print(text[pos:pos+1500])
