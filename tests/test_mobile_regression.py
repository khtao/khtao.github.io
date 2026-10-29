#!/usr/bin/env python3
"""UI regression on actual revised index.html using in-memory fetch fixtures.
No real HTTP/CDN measurements; intended to catch layout/interaction regressions.
"""
import importlib.util,json
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parent
memory_script=(ROOT/'optimized/tests/test_browser_offline_memory.py') if (ROOT/'optimized/tests/test_browser_offline_memory.py').exists() else ROOT/'test_browser_offline_memory.py'
s=importlib.util.spec_from_file_location('test_memory',memory_script)
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
OUT=ROOT/'round3_assets';OUT.mkdir(exist_ok=True)
results=[]
def check(ok,msg):
    if not ok:raise AssertionError(msg)
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'],headless=True)
 for w,h in [(320,680),(375,812),(390,844),(768,900),(1366,900)]:
  ctx=b.new_context(viewport={'width':w,'height':h},device_scale_factor=1,reduced_motion='reduce')
  page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.set_content(m.source,wait_until='domcontentloaded',timeout=20000)
  page.wait_for_function('state.posts.length===3',timeout=6000)
  box=page.evaluate('''() => ({viewport:innerWidth, doc:document.documentElement.scrollWidth, body:document.body.scrollWidth, cards:document.querySelectorAll('a.post-item').length, visible:[...document.querySelectorAll('a.post-item')].filter(e=>e.getBoundingClientRect().height>0).length, error:state.error, offline:state.offline, title:document.title})''')
  box['screen']=f'{w}x{h}';box['errors']=errors.copy();box['overflow_px']=max(box['doc'],box['body'])-w
  check(box['overflow_px']<=2,f'horizontal overflow on {w}: {box}')
  check(box['visible']>0,f'no post links on {w}: {box}')
  if w in (375,1366):page.screenshot(path=str(OUT/f'home_{w}.png'),animations='disabled')
  results.append(box)
  # keyboard, theme, archive, topic, search, direct URL read, offline recovery
  page.locator('#theme').click()
  check(page.evaluate('document.documentElement.dataset.theme') in ['light','dark'],'theme click did not toggle')
  page.keyboard.press('Control+k')
  check(page.evaluate('document.activeElement.id')=='q','search shortcut not working')
  page.locator('#q').fill('喀纳斯')
  page.wait_for_function('state.posts.some(p => p.plain.includes("喀纳斯"))',timeout=6000)
  check('中国50个' in page.locator('body').inner_text(),'full text search did not identify article')
  page.locator('#clearQ').click()
  page.evaluate('location.hash="#/archive"');page.wait_for_timeout(100)
  check('归档' in page.locator('body').inner_text(),'archive missing')
  page.evaluate('location.hash="#/topics"');page.wait_for_timeout(100)
  check('话题' in page.locator('body').inner_text(),'topics missing')
  page.evaluate('location.hash="#/about"');page.wait_for_timeout(100)
  check('关于' in page.locator('body').inner_text(),'about missing')
  page.evaluate('window.__failIndex=true');page.evaluate('refresh(true)')
  page.wait_for_function('state.offline===true',timeout=4000)
  check(page.evaluate('state.posts.length')==3,'offline refresh erased cached list')
  page.evaluate('window.__failIndex=false');page.evaluate('refresh(true)')
  page.wait_for_function('state.offline===false',timeout=4000)
  check(page.evaluate('state.posts.length')==3,'refresh failed')
  page.evaluate('location.hash="#/"');page.wait_for_timeout(100)
  check(page.evaluate('document.documentElement.scrollWidth')<=w+2,'overflow after navigation')
  if w==375: page.screenshot(path=str(OUT/'home_mobile_after_interactions.png'),animations='disabled')
  # Inspect Markdown navigation
  post=next(x for x in json.loads(m.manifest)['files'] if x['name'].endswith('.md'))
  page.evaluate('(n)=>location.hash="#/p/"+encodeURIComponent(n)',post['name']);page.wait_for_selector('#mdBody',timeout=6000)
  check(page.locator('#mdBody').inner_text().strip() != '', 'markdown empty')
  page.evaluate('location.hash="#/"');page.wait_for_timeout(120)
  check(not errors,f'page errors {w}: {errors}')
  box['interactive_tests']='PASS';ctx.close()
 b.close()
(OUT/'mobile_interactions.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(results,ensure_ascii=False,indent=2))
