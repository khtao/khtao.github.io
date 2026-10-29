#!/usr/bin/env python3
"""Real-network HTML article audit, for a machine with browser internet access.

This script DOES NOT provide online results until it actually runs against URLs.
It profiles pages before and after a separate preview deployment.

python3 tests/browser_html_live_audit.py --url https://khtao.github.io/ --repeats 5 --out online.json
python3 tests/browser_html_live_audit.py --url https://PREVIEW.example/ --repeats 5 --out preview.json
"""
from __future__ import annotations
import argparse, json, math, random, statistics, time
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as WaitTimeout

PROFILES={
 'wifi': {'latency':35,'downloadThroughput':10_000_000/8,'uploadThroughput':5_000_000/8},
 'fast3g': {'latency':150,'downloadThroughput':1_600_000/8,'uploadThroughput':750_000/8},
 'slow3g': {'latency':420,'downloadThroughput':750_000/8,'uploadThroughput':300_000/8},
}

def single_run(browser,root,profile,post_name,images_fail,seed):
    context=browser.new_context(viewport={'width':390,'height':844},device_scale_factor=1,
                                is_mobile=True,has_touch=True)
    page=context.new_page();cdp=context.new_cdp_session(page)
    cdp.send('Network.enable')
    cdp.send('Network.emulateNetworkConditions',{'offline':False,**PROFILES[profile]})
    rng=random.Random(seed)
    failed=[];requests=[];errors=[]
    page.on('request',lambda r:requests.append({'url':r.url,'type':r.resource_type,'t':round(time.monotonic()*1000)}))
    page.on('requestfailed',lambda r:failed.append({'url':r.url,'error':r.failure}))
    page.on('pageerror',lambda e:errors.append(str(e)))
    if images_fail>0:
        def perturb(route):
            r=route.request
            if r.resource_type=='image' and rng.random()<images_fail:route.abort('failed')
            else:route.continue_()
        page.route('**/*',perturb)
    result={'profile':profile,'source':root,'post_name':post_name,'seed':seed,
            'image_failure_probability':images_fail,'home_ms':None,'html_reader_ready_ms':None,
            'iframe_height':None,'first_view_img_requests':None,'after_scroll_img_requests':None,
            'residual_lazy_images':None,'responsive_overflow_px':None,'error':None}
    try:
        home_at=time.monotonic()
        response=page.goto(root,wait_until='domcontentloaded',timeout=60000)
        result['http_home_status']=response.status if response else None
        page.wait_for_function('''() => !!document.querySelector('a[href^="#/p/"]') ||
           (document.querySelector('.empty') && /还没有|一片旷野/.test(document.querySelector('.empty').innerText))''',timeout=40000)
        result['home_ms']=round((time.monotonic()-home_at)*1000)
        available=page.evaluate('''() => typeof state==='object' ? state.posts.filter(x=>x.isHtml).map(x=>x.name):[]''')
        if not available:raise RuntimeError('No HTML posts were found in site index')
        current=post_name or available[0]
        if current not in available:raise RuntimeError('Specified HTML article absent from live index: '+current)
        result['post_name']=current
        before_requests=len(requests)
        opened=time.monotonic()
        page.evaluate('(n)=>{location.hash="#/p/"+encodeURIComponent(n)}',current)
        page.wait_for_selector('#rawFrame',timeout=20000)
        page.wait_for_function('''() => {let fr=document.querySelector('#rawFrame');
          return fr && fr.contentDocument && fr.contentDocument.body &&
            fr.contentDocument.body.children.length>0 &&
            !document.getElementById('rawLoadStatus') && parseInt(fr.style.height||0)>700;
        }''',timeout=50000)
        result['html_reader_ready_ms']=round((time.monotonic()-opened)*1000)
        result['iframe_height']=page.evaluate('parseInt(document.querySelector("#rawFrame").style.height)')
        def images_requested():
            return sum(1 for r in requests[before_requests:] if r['type']=='image')
        result['first_view_img_requests']=images_requested()
        result['initial_pending']=page.evaluate('document.querySelector("#rawFrame").contentDocument.querySelectorAll("img[data-lazysrc],img[data-khtao-src]").length')
        result['responsive_overflow_px']=page.evaluate('Math.max(0,document.documentElement.scrollWidth-innerWidth)')
        height=page.evaluate('document.documentElement.scrollHeight')
        for frac in (.2,.5,.8):
            page.evaluate('(f)=>window.scrollTo(0,document.documentElement.scrollHeight*f)',frac)
            page.wait_for_timeout(1600)
        result['after_scroll_img_requests']=images_requested()
        result['residual_lazy_images']=page.evaluate('document.querySelector("#rawFrame").contentDocument.querySelectorAll("img[data-lazysrc],img[data-khtao-src]").length')
        result['resource_entries']=page.evaluate('''() => performance.getEntriesByType('resource').filter(x=>x.name.includes('/blog/')).map(x=>({
           url:x.name,duration_ms:Math.round(x.duration),transfer_bytes:x.transferSize||0,
           encoded_bytes:x.encodedBodySize||0
        })).slice(0,200)''')
    except Exception as ex:
        result['error']=type(ex).__name__+': '+str(ex)[:400]
    result['request_failures']=failed[:100]
    result['script_errors']=errors[:30]
    result['requests']=requests[:350]
    context.close()
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url',required=True,help='Existing site or separate preview deployment root URL')
    p.add_argument('--chromium',default=None,help='Local Chromium executable; defaults to /usr/bin/chromium if available')
    p.add_argument('--post',default='all',help='HTML post filename or all (default; reads local blog/index.json)')
    p.add_argument('--profiles',default='wifi,fast3g,slow3g')
    p.add_argument('--repeats',type=int,default=5)
    p.add_argument('--image-failure-rate',type=float,default=0.0,help='0..1, random image-request failures')
    p.add_argument('--out',default='html_live_audit.json')
    a=p.parse_args()
    if not (0<=a.image_failure_rate<=1):p.error('--image-failure-rate must be 0..1')
    profiles=[s.strip() for s in a.profiles.split(',')]
    for name in profiles:
        if name not in PROFILES:p.error('Unknown profile '+name)
    records=[]
    if a.post=='all':
        idx=json.loads((Path(__file__).resolve().parents[1]/'blog/index.json').read_text(encoding='utf-8'))
        post_names=[x['name'] for x in idx['files'] if x['name'].endswith(('.html','.htm'))]
        if not post_names: p.error('No HTML posts in local blog/index.json')
    else: post_names=[a.post]
    with sync_playwright() as pw:
        exe=a.chromium or ('/usr/bin/chromium' if Path('/usr/bin/chromium').is_file() else None)
        browser=pw.chromium.launch(executable_path=exe,headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            for post in post_names:
                for name in profiles:
                    for repeat in range(1,max(1,a.repeats)+1):
                        r=single_run(browser,a.url.rstrip('/')+'/',name,post,a.image_failure_rate,repeat)
                        r['repeat']=repeat;records.append(r)
                        print(post,name,repeat,'html_ms=',r['html_reader_ready_ms'],'initial_img=',r['first_view_img_requests'],
                              'late_img=',r['after_scroll_img_requests'],'error=',r['error'],flush=True)
        finally:browser.close()
    summary={}
    for post in post_names:
        for name in profiles:
            subset=[r for r in records if r['profile']==name and r['post_name']==post]
            rows=[r for r in subset if r['html_reader_ready_ms'] is not None]
            timings=[r['html_reader_ready_ms'] for r in rows]
            summary[post+' :: '+name]={'successes':len(rows),'runs':len(subset),
                           'median_html_ready_ms':statistics.median(timings) if timings else None,
                           'median_first_view_image_requests':statistics.median([x['first_view_img_requests'] for x in rows]) if rows else None}
    result={'site':a.url,'date_utc':datetime.now(timezone.utc).isoformat(), 'profiles':PROFILES,'summary':summary,'runs':records}
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print('Wrote:',out)
if __name__=='__main__':main()
