"""Offline Chromium tests of staged HTML image loading.
Actual blog article HTML/JS and reader JS are used. Remote image bytes are not
available in this environment. Assertions check request initiation conditions,
not real CDN throughput or live Web Vitals.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import json, sys

ROOT=Path(__file__).resolve().parents[1]
manifest=json.loads((ROOT/'blog/index.json').read_text())
articles=[x for x in manifest['files'] if x['name'].endswith('.html')]
assert len(articles)==2
assert sum((ROOT/'blog'/x['name']).read_text().count('src="data:image/gif;base64,') for x in articles)==58

with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage','--disable-background-networking'])
 for a in articles:
  page=browser.new_page(viewport={'width':390,'height':780})
  errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  article=(ROOT/'blog'/a['name']).read_text()
  # Direct standalone reading. Loading failures of unavailable images do not
  # prevent attributes/timing behavior from being checked.
  page.set_content(article,wait_until='domcontentloaded',timeout=25000)
  page.wait_for_timeout(800)
  before=page.evaluate('''() => ({
    loaded:[...document.images].filter(x=>x.getAttribute('src')&&!x.getAttribute('src').startsWith('data:image/gif')).length,
    pending:document.querySelectorAll('img[data-khtao-src]').length,
    height:document.documentElement.scrollHeight,
    first:[...document.images].slice(0,2).map(x=>x.getAttribute('src'))
  })''')
  assert before['pending']>=3, f'{a["name"]}: too many images requested immediately: {before}'
  assert all(x and not x.startswith('data:') for x in before['first'])
  assert before['height']>3000, f'{a["name"]}: document unexpectedly collapsed {before}'
  page.evaluate('''() => { const el=document.querySelector('img[data-khtao-src]'); if(el)window.scrollTo(0,el.getBoundingClientRect().top+scrollY); }''')
  page.wait_for_timeout(800)
  after=page.evaluate("document.querySelectorAll('img[data-khtao-src]').length")
  assert after<before['pending'], f'no images started after scrolling: {before["pending"]} -> {after}'
  assert not errors,errors[:3]
  print('PASS: standalone',a['name'],'first=2 / lazy_pending_before=',before['pending'],'after=',after,'height=',before['height'],flush=True)
  page.close()

 # Reader iframe in memory, with image-sizes response intentionally held forever
 # to prove there is no optional fetch initialization barrier.
 idx=(ROOT/'blog/index.json').read_text()
 cfg=json.loads((ROOT/'config.json').read_text()); cfg['projects']={'enabled':False}
 src=(ROOT/'index.html').read_text()
 posts={x['name']:(ROOT/'blog'/x['name']).read_text() for x in manifest['files']}
 fx={'cfg':json.dumps(cfg,ensure_ascii=False),'idx':idx,'posts':posts}
 js=json.dumps(fx,ensure_ascii=True).replace('</','<\\/')
 setup='''<script>
window.__fx=__FIXTURE__;window.__fetchCalls=[];
window.fetch=async(s)=>{
 s=String(s);window.__fetchCalls.push({s,t:performance.now()});
 if(s.includes('config.json'))return new Response(window.__fx.cfg,{status:200});
 if(s.includes('image-sizes.json'))return new Promise(()=>{}); // 3.5s+ blocked
 if(s.includes('search-index.json'))return new Response('{}',{status:200});
 if(s.includes('index.json'))return new Response(window.__fx.idx,{status:200});
 for(let [k,v] of Object.entries(window.__fx.posts))if(s.includes(encodeURIComponent(k))||s.includes(k))return new Response(v,{status:200});
 return new Response('',{status:404});
};
</script>'''.replace('__FIXTURE__',js)
 src=src.replace('<script>\n/* =======================================================================',setup+'\n<script>\n/* =======================================================================',1)
 page=browser.new_page(viewport={'width':390,'height':780})
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.set_content(src,wait_until='domcontentloaded',timeout=25000)
 page.wait_for_function('state.posts.length===3',timeout=5000)
 target=articles[0]
 page.evaluate('(n)=>location.hash="#/p/"+encodeURIComponent(n)',target['name'])
 page.wait_for_selector('#rawFrame',timeout=4000)
 iframe_html=(ROOT/'blog'/target['name']).read_text()
 page.evaluate('(html)=>document.getElementById("rawFrame").srcdoc=html',iframe_html)
 page.wait_for_function('''() => { const f=document.getElementById("rawFrame");
   return f&&f.contentWindow&&f.contentWindow.__KHTAO_PARENT_LAZY_READY__===true;
 }''',timeout=1000)
 info=page.evaluate('''() => {
 const f=document.getElementById('rawFrame'),d=f.contentDocument;
 return {pending:d.querySelectorAll('img[data-khtao-src]').length, lazy:d.querySelectorAll('img[data-lazysrc]').length,
 height:parseInt(f.style.height)||0, requests:window.__fetchCalls.map(x=>x.s)};
 }''')
 assert info['pending']>=25,info
 assert info['lazy']>=25,info
 assert info['height']>5000,info
 print('PASS: iframe initialization without image-size response, lazy=',info['lazy'],'height=',info['height'],flush=True)
 # Move parent viewport within the frame and request image content near far locations.
 page.evaluate('''() => { const f=document.querySelector('#rawFrame'),el=f.contentDocument.querySelector('img[data-khtao-src]'); if(f&&el)window.scrollTo(0,f.getBoundingClientRect().top+scrollY+el.getBoundingClientRect().top); }''')
 page.wait_for_timeout(400)
 new_pending=page.evaluate('document.querySelector("#rawFrame").contentDocument.querySelectorAll("img[data-khtao-src]").length')
 assert new_pending < info['pending'],(new_pending,info)
 assert not errors,errors[:5]
 print('PASS: iframe viewport-driven reveal',info['pending'],'->',new_pending,flush=True)
 page.close();browser.close()
print('RESULT: standalone and embedded HTML staged loading PASS (local DOM; not live network).')
