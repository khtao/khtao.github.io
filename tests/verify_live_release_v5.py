#!/usr/bin/env python3
"""Verify *published* GitHub Pages assets and article integrity (standard library).

This checks production response bytes; it does not substitute for browser Web Vitals.
python tests/verify_live_release_v5.py --url https://khtao.github.io/ --expected-root . --out live_release.json
"""
from __future__ import annotations
import argparse, hashlib, json, time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import quote,urljoin
from urllib.request import Request,urlopen

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--url',default='https://khtao.github.io/')
p.add_argument('--expected-root',type=Path,default=None)
p.add_argument('--out',type=Path,default=Path('live_release.json'))
p.add_argument('--timeout',type=int,default=18)
a=p.parse_args();root=a.url.rstrip('/')+'/'
report={'target':root,'checked_utc':datetime.now(timezone.utc).isoformat(), 'requests':{},'checks':{}, 'errors':[]}

def get(name, must_json=False):
    # Filename components may contain literal # and non-ASCII; preserve slash separators.
    path='/'.join(quote(k,safe='') for k in name.lstrip('/').split('/'))
    url=urljoin(root,path)+'?audit='+str(int(time.time()))
    start=time.monotonic()
    try:
        with urlopen(Request(url,headers={'User-Agent':'Khtao-live-release-audit/5'}),timeout=a.timeout) as r:
            raw=r.read(); headers=dict(r.headers.items()); code=r.status
        rec={'url':url,'http_status':code,'bytes':len(raw),'elapsed_ms':round((time.monotonic()-start)*1000),
             'sha256':hashlib.sha256(raw).hexdigest(), 'cache_control':headers.get('Cache-Control',''),
             'content_type':headers.get('Content-Type',''), 'etag':headers.get('ETag',''),
             'content_encoding':headers.get('Content-Encoding','')}
        report['requests'][name]=rec
        if a.expected_root:
            f=a.expected_root/name
            if f.is_file():rec['matches_expected_source_sha256']=rec['sha256']==hashlib.sha256(f.read_bytes()).hexdigest()
        return raw
    except Exception as e:
        report['requests'][name]={'url':url,'error':type(e).__name__+': '+str(e)[:320]}
        report['errors'].append(name+': '+str(e)[:200])
        return None

home=get('index.html'); idx_bytes=get('blog/index.json')
if home:
    h=home.decode('utf8','replace')
    report['checks']['reader_contains_parent_handoff']='__KHTAO_PARENT_LAZY_READY__' in h
    report['checks']['index_loads_directory_first']='async function loadPostBody' in h
    report['checks']['reader_stages_images']='data-khtao-src' in h
    report['checks']['main_has_old_size_map_blocking_comment']='先把图片尺寸表取回来再渲染 iframe' in h
if idx_bytes:
    try:
        j=json.loads(idx_bytes); posts=j['files']
        report['checks']['post_count']=len(posts)
        report['checks']['index_generated']=j.get('generated')
        report['checks']['html_posts']=[x['name'] for x in posts if x['name'].lower().endswith(('.html','.htm'))]
        integrity=[]
        for item in posts:
            name=item['path'];raw=get(name)
            if raw is None:integrity.append({'name':name,'available':False});continue
            sha=hashlib.sha256(raw).hexdigest()
            same=sha==item.get('sha');rec={'name':name,'available':True,'manifest_sha_matches_article':same}
            if name.lower().endswith(('.html','.htm')):
                text=raw.decode('utf8','replace')
                rec['staged_image_count']=text.count('data-khtao-src=')
                rec['has_self_load_fallback']='data-khtao-lazy-bootstrap' in text
                rec['wait_6000ms']='},6000);' in text
                rec['standalone_webp_preference']='img.src=preferred' in text
                rec['legacy_1800ms_fallback']='},1800);' in text
            integrity.append(rec)
        report['checks']['post_integrity']=integrity
        get('blog/image-sizes.json');get('blog/search-index.json')
        # Include first two images from the long HTML posts, if they exist.
        for path in ['blog/images/01.webp','blog/images/02.webp']:
            get(path)
    except Exception as e:report['errors'].append('manifest validation: '+repr(e))
a.out.parent.mkdir(parents=True,exist_ok=True)
a.out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'out':str(a.out),'count':len(report['requests']),'errors':report['errors'],
                  'checks':report['checks']},ensure_ascii=False,indent=2))
