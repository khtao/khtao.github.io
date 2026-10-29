"""In-memory Chromium smoke tests for environments that block all local/remote HTTP.
Run: python3 tests/test_browser_offline_memory.py
Requires: pip install playwright; python -m playwright install chromium
All fetches are stubbed; this does NOT replace real-network/production testing.
"""
from pathlib import Path
import json,sys
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
manifest=(ROOT/'blog/index.json').read_text(encoding='utf8')
config=json.loads((ROOT/'config.json').read_text(encoding='utf8'))
config['projects']={'enabled':False}
raw={post['name']:(ROOT/'blog'/post['name']).read_text(encoding='utf8') for post in json.loads(manifest)['files']}
raw['image-sizes.json']=(ROOT/'blog/image-sizes.json').read_text(encoding='utf8')
raw['search-index.json']=(ROOT/'blog/search-index.json').read_text(encoding='utf8')
fixture={'cfg':json.dumps(config,ensure_ascii=False),'index':manifest,'posts':raw}
j=json.dumps(fixture,ensure_ascii=True).replace('</','<\\/')
setup="""<script>
window.__fixture=__FIXTURE__;
window.__failIndex=false;window.__requests=[];
window.fetch=async(s)=>{s=String(s);window.__requests.push(s);let f=window.__fixture;
if(s.includes('config.json'))return new Response(f.cfg,{status:200});
if(s.includes('search-index.json'))return new Response(f.posts['search-index.json'],{status:200});
if(s.includes('index.json'))return new Response(window.__failIndex?'':f.index,{status:window.__failIndex?503:200});
if(s.includes('image-sizes.json'))return new Response(f.posts['image-sizes.json'],{status:200});
for(let [k,v] of Object.entries(f.posts)){
if(s.includes(encodeURIComponent(k))||s.includes(k.replaceAll('#','%23'))||s.includes(k))return new Response(v,{status:200});}
return new Response('',{status:404});
};
</script>""".replace('__FIXTURE__',j)
source=(ROOT/'index.html').read_text(encoding='utf8')
source=source.replace('<script>\n/* =======================================================================',setup+'\n<script>\n/* =======================================================================',1)

def assert_true(condition,message):
    if not condition:raise AssertionError(message)

def run():
 with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.set_content(source,wait_until='domcontentloaded',timeout=20000)
    page.wait_for_function('state.posts.length===3',timeout=5000)
    requests=page.evaluate('window.__requests')
    assert_true(not any('.md?' in s or '.html?' in s for s in requests),'首页不应下载任何文章正文')
    print('PASS: 首页仅加载目录，3篇文章可见')
    markdown=next(x for x in json.loads(manifest)['files'] if x['name'].endswith('.md'))
    page.evaluate('(n)=>location.hash="#/p/"+encodeURIComponent(n)',markdown['name'])
    page.wait_for_selector('#mdBody',timeout=4000)
    assert_true('从零部署' in page.locator('#mdBody').inner_text(),'Markdown 内容不完整')
    print('PASS: Markdown 按需加载并渲染')
    page.evaluate('location.hash="#/"')
    page.wait_for_timeout(250)
    page.locator('#q').fill('喀纳斯')
    page.wait_for_function('state.posts.some(p=>p.plain.includes("喀纳斯"))',timeout=5000)
    assert_true('中国50个一生必去的地方' in page.locator('body').inner_text(), 'HTML 正文全文搜索失效')
    print('PASS: HTML 全文搜索按需加载 search-index.json，且不拉取 HTML 文件')
    page.locator('#clearQ').click()
    for article in [x for x in json.loads(manifest)['files'] if x['name'].endswith('.html')]:
      page.evaluate('(n)=>location.hash="#/p/"+encodeURIComponent(n)',article['name'])
      page.wait_for_selector('#rawFrame',timeout=3000)
      href=page.locator('#rawFrame').get_attribute('src')
      assert_true('%23' in href and href.startswith('./blog/'),'含#号的HTML路径未正确编码')
      page.evaluate('(html)=>document.getElementById("rawFrame").srcdoc=html',raw[article['name']])
      page.wait_for_function('!document.getElementById("rawLoadStatus")',timeout=10000)
      count=page.evaluate('document.getElementById("rawFrame").contentDocument.images.length')
      expected=51 if '中国50' in article['title'] else 12
      assert_true(count==expected,f'{article["title"]}: images {count} != {expected}')
      height=page.evaluate('parseInt(document.getElementById("rawFrame").style.height,10)')
      assert_true(height>5000,'长 HTML 的 iframe 高度没有正确伸展')
      print(f'PASS: {article["title"]}: 图片{count}张，iframe 高度{height}px')
      page.evaluate('location.hash="#/"')
      page.wait_for_timeout(250)
    assert_true(not errors,'页面 JS 异常: '+str(errors[:3]))
    page.close()
    failpage=browser.new_page();issues=[];failpage.on('pageerror',lambda e:issues.append(str(e)))
    offline_source=source.replace('window.__failIndex=false','window.__failIndex=true',1)
    failpage.set_content(offline_source,wait_until='domcontentloaded',timeout=20000)
    failpage.wait_for_function('state.error==="INDEX_UNAVAILABLE"',timeout=4000)
    assert_true('网络' in failpage.locator('body').inner_text(),'离线提示应指出网络故障')
    failpage.evaluate('window.__failIndex=false')
    failpage.locator('button').filter(has_text='重新加载').first.click()
    failpage.wait_for_function('state.posts.length===3',timeout=5000)
    assert_true(not issues,'恢复过程脚本异常: '+str(issues[:3]))
    print('PASS: 索引不可用 → 明确提示 → 手动重试恢复3篇文章')
    failpage.close();browser.close()
    print('RESULT: 6 browser scenario groups PASS (in-memory mocked network)')
if __name__=='__main__':run()
