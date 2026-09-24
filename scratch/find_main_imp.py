with open("scratch/wingo_module.js", encoding="utf-8") as f:
    text = f.read()

pos = text.find("from'./index-DtsNZcBk.js'")
if pos == -1:
    pos = text.find('from "./index-DtsNZcBk.js"')
if pos == -1:
    pos = text.find("index-DtsNZcBk.js")
print(pos)
if pos != -1:
    start = max(0, pos-200)
    print(text[start:pos+30].encode('ascii', errors='replace').decode('ascii'))
