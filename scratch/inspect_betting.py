with open("scratch/wingo_module.js", encoding="utf-8") as f:
    text = f.read()

pos = text.find('Betting:qe')
if pos != -1:
    print("Found Betting:qe at", pos)
    # Search for qe= or function qe
    import re
    matches = re.findall(r'qe\s*=\s*[^,;]+', text)
    print("qe definitions:", matches[:3])

# Search for where "Big" or "Small" buttons are created
pos_b = text.find('"big"')
if pos_b != -1:
    print("Context of 'big':")
    print(text[pos_b-200:pos_b+300].encode('ascii', errors='replace').decode('ascii'))
