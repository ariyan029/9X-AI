with open("scratch/page_dump.html", encoding="utf-8") as f:
    text = f.read()

pos = text.find('dialog-id="home-announcement"')
if pos != -1:
    end_pos = text.find('</div></div></div>', pos)
    snippet = text[pos:pos+1500] if end_pos == -1 else text[pos:end_pos+100]
    print(snippet.encode('ascii', errors='replace').decode('ascii'))
