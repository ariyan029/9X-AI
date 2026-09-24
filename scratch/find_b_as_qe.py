with open("scratch/wingo_module.js", encoding="utf-8") as f:
    text = f.read()

pos = text.find('B as qe')
if pos != -1:
    print(text[max(0, pos-100):min(len(text), pos+100)].encode('ascii', errors='replace').decode('ascii'))
