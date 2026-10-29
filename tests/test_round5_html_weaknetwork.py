"""Round 5 Chromium-only regression: no HTTP access required.

Checks the standalone WebP attempt + JPEG failure fallback, and the parent
iframe startup race under delayed initialization. These are behavioral local
checks, NOT live site or real packet-loss measurements.
"""
from pathlib import Path
import re
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT/'scripts/prepare_html_lazy.py').read_text()
# Reuse EXACT bootstrap emitted by build script, not a separate approximation.
import sys
sys.path.insert(0, str(ROOT/'scripts'))
from prepare_html_lazy import BOOTSTRAP
G='data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'
IMGS=''.join('<img style="display:block;width:200px;height:90px" '
             f'src="{G}" data-khtao-src="images/p{i}.jpg" alt="photo{i}">' for i in range(5))
BODY='<div style="height:80px">文章正文</div>'+IMGS

def check(cond,msg):
    if not cond: raise AssertionError(msg)

def main():
    with sync_playwright() as pw:
        b=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
        p=b.new_page(viewport={'width':375,'height':750})
        errors=[];p.on('pageerror',lambda e: errors.append(str(e)))
        obs='''<script>window.__srcMutations=[];new MutationObserver(rs=>rs.forEach(r=>window.__srcMutations.push(r.target.getAttribute('src')))).observe(document.documentElement,{subtree:true,attributes:true,attributeFilter:['src']});</script>'''
        p.set_content('<html><body>'+BODY+obs+BOOTSTRAP+'</body></html>')
        p.wait_for_timeout(1100)
        changes=p.evaluate('window.__srcMutations')
        check(any('p0.webp' in x for x in changes if x),f'Standalone should attempt WebP, saw {changes}')
        # This restricted Chromium cannot fetch images; ensure JPEG fallback is attempted.
        check(any('p0.jpg' in x for x in changes if x),f'WebP failure must fall back to original JPEG, saw {changes}')
        check(not errors,'standalone JS errors '+repr(errors[:5]))
        print('PASS standalone: WebP attempted and onerror JPEG fallback observed',flush=True)
        p.close()

        # A real same-origin blog iframe (id=rawFrame) must *not* start standalone
        # fallback after only 1.8 s: slow parent initialization is expected on 3G.
        page=b.new_page(viewport={'width':375,'height':750})
        page.set_content('<html><body><iframe id="rawFrame" style="width:340px;height:600px"></iframe></body></html>')
        iframe=page.frame_locator('#rawFrame')
        page.frame(name=None)  # no-op
        fr=page.locator('#rawFrame').element_handle().content_frame()
        fr.set_content('<html><body>'+BODY+BOOTSTRAP+'</body></html>')
        page.wait_for_timeout(2300)
        pending=fr.evaluate('document.querySelectorAll("img[data-khtao-src]").length')
        check(pending==5,f'parent handshake released before 2.3 sec, left={pending}')
        print('PASS embedded: all 5 deferred images still staged at 2.3 s',flush=True)
        # Simulate parent taking over before the six-second fallback.
        fr.evaluate('window.__KHTAO_PARENT_LAZY_READY__=true')
        page.wait_for_timeout(4200)
        pending2=fr.evaluate('document.querySelectorAll("img[data-khtao-src]").length')
        check(pending2==5,'parent ready must cancel standalone fallback')
        print('PASS embedded: parent ready before 6 s avoids competing lazy loaders',flush=True)
        page.close()

        fallback=b.new_page(viewport={'width':375,'height':750})
        fallback.set_content('<html><body><iframe id="rawFrame" style="width:340px;height:600px"></iframe></body></html>')
        ff=fallback.locator('#rawFrame').element_handle().content_frame()
        ff.set_content('<html><body>'+BODY+BOOTSTRAP+'</body></html>')
        fallback.wait_for_timeout(6300)
        pending3=ff.evaluate('document.querySelectorAll("img[data-khtao-src]").length')
        check(pending3<5,f'parent failure must trigger standalone fallback within 6.3s; pending={pending3}')
        print('PASS embedded: absent parent handoff recovers after 6 s',flush=True)
        fallback.close()
        b.close()
    print('RESULT 4/4 round5 HTML loading checks passed (browser DOM, no HTTP)')

if __name__ == '__main__':
    main()
