#!/usr/bin/env python3
"""真实 Chromium + CDP 弱网测速（需要在允许访问目标 URL 的电脑运行）。
示例: python3 tests/browser_live_performance.py --url https://khtao.github.io/#/ --out live_results.json
仅本脚本访问目标 URL；它不会上传数据或修改线上网站。
"""
import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

PROFILES={
 'fast':{'name':'Fast 3G','latency':150,'downloadThroughput':1_600_000/8,'uploadThroughput':750_000/8},
 'slow':{'name':'Slow 3G','latency':420,'downloadThroughput':750_000/8,'uploadThroughput':300_000/8},
 'wifi':{'name':'Wi-Fi','latency':40,'downloadThroughput':10_000_000/8,'uploadThroughput':5_000_000/8}
}
HOOK="""(() => {
 window.__perfAudit={lcp:0,cls:0,longTasks:0,errors:[]};
 window.addEventListener('error',e=>window.__perfAudit.errors.push(String(e.message||e.error||'error')));
 window.addEventListener('unhandledrejection',e=>window.__perfAudit.errors.push(String(e.reason)));
 try { new PerformanceObserver(list => { for(const x of list.getEntries())window.__perfAudit.lcp=x.startTime; })
     .observe({type:'largest-contentful-paint',buffered:true}); } catch(e){}
 try { new PerformanceObserver(list => { for(const x of list.getEntries())if(!x.hadRecentInput)window.__perfAudit.cls+=x.value; })
     .observe({type:'layout-shift',buffered:true}); } catch(e){}
 try { new PerformanceObserver(list => { window.__perfAudit.longTasks+=list.getEntries().length; })
     .observe({type:'longtask',buffered:true}); } catch(e){}
})();"""

def audit(browser,url,profile):
 context=browser.new_context(viewport={'width':1366,'height':900},device_scale_factor=1)
 context.add_init_script(HOOK)
 page=context.new_page();client=context.new_cdp_session(page)
 client.send('Network.enable')
 client.send('Network.emulateNetworkConditions',{'offline':False,**{k:v for k,v in profile.items() if k!='name'}})
 fail=[]; console=[]
 page.on('requestfailed',lambda req:fail.append({'url':req.url,'failure':req.failure}))
 page.on('console',lambda msg:console.append(msg.text) if msg.type=='error' else None)
 now=time.monotonic();detail={'profile':profile['name'],'url':url,'usable_ms':None,'status':None,'posts':None}
 try:
  response=page.goto(url,wait_until='domcontentloaded',timeout=50000)
  detail['status']=response.status if response else None
  # 只有真实文章链接才算首页可用，骨架屏、错误页均不能算。
  try:
   page.wait_for_function('''() => {
     const hasPost = !!document.querySelector('a[href^="#/p/"]');
     const isEmpty = !!(document.querySelector('.empty') && /还没有|一片旷野/.test(document.querySelector('.empty').innerText));
     return hasPost || isEmpty;
   }''',timeout=22000)
   detail['usable_ms']=round((time.monotonic()-now)*1000)
  except PlaywrightTimeout:detail['result']='CONTENT_TIMEOUT'
  page.wait_for_timeout(1600)
  detail['posts']=page.evaluate("() => document.querySelectorAll('a[href^=\"#/p/\"]').length")
  detail['metrics']=page.evaluate('window.__perfAudit')
  detail['resources']=page.evaluate('''() => {
    const e=performance.getEntriesByType('resource');
    return {count:e.length,transferKB:Math.round(e.reduce((s,x)=>s+(x.transferSize||0),0)/1024),
      articleRequests:e.filter(x=>/\\/blog\\/[^/]+\\.(html?|md)(\\?|$)/i.test(x.name)).length,
      items:e.map(x=>({name:x.name,duration:Math.round(x.duration),bytes:x.transferSize||0})).slice(0,100)};
  }''')
 except Exception as e:detail['result']=type(e).__name__+': '+str(e)[:250]
 detail['request_failures']=fail[:30];detail['console_errors']=console[:30]
 context.close()
 return detail

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--url',default='https://khtao.github.io/#/')
 ap.add_argument('--out',default='live_results.json')
 ap.add_argument('--repeats',type=int,default=3)
 args=ap.parse_args()
 records=[]
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
  for name in ['wifi','fast','slow']:
   for n in range(max(1,args.repeats)):
    row=audit(browser,args.url,PROFILES[name]);row['iteration']=n+1
    records.append(row)
    print(row['profile'],n+1,'usable=',row['usable_ms'],'ms','posts=',row['posts'],'result=',row.get('result','OK'),flush=True)
  browser.close()
 out={'url':args.url,'measured_at_utc':datetime.now(timezone.utc).isoformat(), 'measurements':records}
 out['summary']={}
 for name in ['Wi-Fi','Fast 3G','Slow 3G']:
  valid=[x['usable_ms'] for x in records if x['profile']==name and x['usable_ms'] is not None]
  out['summary'][name]={'samples':len(valid),'median_usable_ms':round(statistics.median(valid)) if valid else None}
 with open(args.out,'w',encoding='utf8') as f:json.dump(out,f,ensure_ascii=False,indent=2)
 print('saved',args.out)

if __name__=='__main__':main()
