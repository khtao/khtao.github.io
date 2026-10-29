#!/usr/bin/env python3
"""Stage offscreen images before HTML is parsed, preserving standalone HTML use.

Only locally hosted <img src=...> in direct blog/*.html are processed. The first two
keep normal sources; all subsequent images carry their real URL in data-khtao-src.
The reader iframe releases those images according to the *outer* viewport. When
an article is viewed directly, a tiny embedded IntersectionObserver performs
progressive loading instead. Idempotent and does not reserialize article HTML.
"""
from __future__ import annotations
import argparse, html, json, re
from pathlib import Path

BLANK = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'
IMG_TAG = re.compile(r'<img\b[^>]*>', re.I|re.S)
SRC = re.compile(r'(?<![\w:-])src\s*=\s*(["\'])(.*?)\1', re.I|re.S)
STAGED = re.compile(r'\bdata-khtao-src\s*=', re.I)
MARKER = 'data-khtao-lazy-bootstrap'
BOOTSTRAP = r'''<script data-khtao-lazy-bootstrap>
/* Standalone article fallback; parent reader provides outer-viewport loading. */
(function(){
  var images=[].slice.call(document.querySelectorAll('img[data-khtao-src]'));
  if(!images.length)return;
  function reveal(img){
    var src=img.getAttribute('data-khtao-src');
    if(!src)return;
    img.removeAttribute('data-khtao-src');
    img.loading='lazy';img.decoding='async';img.src=src;
  }
  function standalone(){
    images=images.filter(function(img){return !!img.getAttribute('data-khtao-src');});
    if(!images.length)return;
    if(!('IntersectionObserver' in window)){images.forEach(reveal);return;}
    var io=new IntersectionObserver(function(entries){entries.forEach(function(e){
      if(e.isIntersecting){io.unobserve(e.target);reveal(e.target);}
    });},{rootMargin:'850px 0px',threshold:0});
    images.forEach(function(img){io.observe(img);});
  }
  var embedded=false;
  try{embedded=window.parent!==window && window.parent.location.origin===location.origin;}
  catch(e){embedded=false;}
  if(embedded){
    // The reader starts within 100ms; if it fails, never leave pictures blank.
    setTimeout(function(){if(!window.__KHTAO_PARENT_LAZY_READY__)standalone();},1800);
  }else standalone();
})();
</script>'''

def prepare(path:Path, sizes:dict)->int:
    text=path.read_text(encoding='utf-8')
    already_bootstrapped = MARKER in text
    count=[0]; processed=[0]
    def sub(m):
        tag=m.group(0)
        srcm=SRC.search(tag)
        if STAGED.search(tag):
            processed[0]+=1
            return tag
        if not srcm: return tag
        src=html.unescape(srcm.group(2))
        if not src or src.startswith(('data:', 'http:', 'https:', '//', 'blob:')): return tag
        processed[0]+=1
        ind=processed[0]
        wh=sizes.get(src)
        if wh and len(wh)==2 and wh[0]>0 and wh[1]>0:
            if not re.search(r'\bwidth\s*=',tag,re.I): tag=tag[:-1] + f' width="{wh[0]}"'+tag[-1]
            if not re.search(r'\bheight\s*=',tag,re.I): tag=tag[:-1] + f' height="{wh[1]}"'+tag[-1]
            if not re.search(r'\bstyle\s*=',tag,re.I): tag=tag[:-1]+f' style="aspect-ratio:{wh[0]}/{wh[1]}"'+tag[-1]
        if not re.search(r'\bdecoding\s*=',tag,re.I):tag=tag[:-1]+' decoding="async"'+tag[-1]
        if ind<=2:
            tag=re.sub(r'\bloading\s*=\s*(["\']).*?\1','loading="eager"',tag,flags=re.I)
            if not re.search(r'\bloading\s*=',tag,re.I): tag=tag[:-1]+' loading="eager"'+tag[-1]
            if ind==1 and not re.search(r'\bfetchpriority\s*=',tag,re.I): tag=tag[:-1]+' fetchpriority="high"'+tag[-1]
        else:
            # Replace only the original URL, leaving all other HTML intact.
            srcm=SRC.search(tag)
            tag=tag[:srcm.start()]+f'src="{BLANK}"'+tag[srcm.end():]
            tag=tag[:-1]+f' data-khtao-src="{html.escape(src,quote=True)}"'+tag[-1]
            if not re.search(r'\bloading\s*=',tag,re.I):tag=tag[:-1]+' loading="lazy"'+tag[-1]
            if not re.search(r'\bdata-full\s*=',tag,re.I):tag=tag[:-1]+f' data-full="{html.escape(src,quote=True)}"'+tag[-1]
            count[0]+=1
        return tag
    revised=IMG_TAG.sub(sub,text)
    if count[0] and not already_bootstrapped and '</body>' in revised.lower():
        revised=re.sub(r'</body\s*>',BOOTSTRAP+'\n</body>',revised,count=1,flags=re.I)
    if revised!=text:path.write_text(revised,encoding='utf-8')
    return count[0]

def run(root:Path):
    idx=root/'blog/image-sizes.json'
    all_sizes=json.loads(idx.read_text())['articles'] if idx.is_file() else {}
    total=0
    for path in sorted((root/'blog').glob('*.html')):
        n=prepare(path,all_sizes.get(path.name,{}))
        total+=n
        print(path.name,':',n,'images staged')
    print('total images staged:',total)

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parent.parent)
    args=ap.parse_args();run(args.root)
