import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, ".")
from config.settings import Settings
from browser.context import BrowserContextManager

async def main():
    s = Settings(HEADLESS=True)
    m = BrowserContextManager(s)
    ctx = await m.create_context()
    
    cookies = await ctx.cookies()
    print(f"Total cookies: {len(cookies)}")
    for c in cookies:
        print(f"  Cookie: {c['name']} = {c['value'][:20]}... domain={c['domain']}")
        
    p = context_page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await p.goto(s.BASE_URL, wait_until="networkidle")
    await asyncio.sleep(3)
    
    # Check localStorage keys
    ls_keys = await p.evaluate("() => Object.keys(localStorage)")
    print("LocalStorage keys:", ls_keys)
    for k in ls_keys:
        val = await p.evaluate(f"() => localStorage.getItem('{k}')")
        if val:
            print(f"  {k} = {val[:60]}")
            
    # Check wallet balance elements
    wallet_el = await p.query_selector(".Wallet__C-balance")
    if wallet_el:
        print("Wallet container text:", repr(await wallet_el.text_content()))
        
    l1 = await p.query_selector(".Wallet__C-balance-l1")
    if l1:
        print("Wallet l1 text:", repr(await l1.text_content()))
        
    # Check if there is a refresh icon or reload button for balance
    refresh_icon = await p.query_selector(".Wallet__C-balance-l2, div[class*='refresh'], i[class*='refresh']")
    if refresh_icon:
        print("Refresh icon found, class:", await refresh_icon.get_attribute("class"))
        print("Clicking refresh icon...")
        await refresh_icon.click()
        await asyncio.sleep(2)
        print("After refresh click, l1 text:", repr(await l1.text_content() if l1 else None))
        
    # Check if user is logged in
    # Let's inspect token in localStorage
    token = await p.evaluate("() => localStorage.getItem('token') || localStorage.getItem('user') || localStorage.getItem('userInfo')")
    print("Token/User in localStorage:", token)
    
    await m.close()

if __name__ == "__main__":
    asyncio.run(main())
