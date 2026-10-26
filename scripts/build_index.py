#!/usr/bin/env python3
"""Generate blog/index.json without network calls or extra Python packages.

When run in a git checkout with history (GitHub Actions checkout fetch-depth=0),
creation/modified dates come from the first/last commit touching each article.
"""
from __future__ import annotations

import argparse
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
from datetime import datetime, timezone

EXT = {'.md', '.markdown', '.htm', '.html'}
SUMMARY_LIMIT = 160
SKIP_HTML = {'script', 'style', 'nav', 'footer', 'noscript', 'svg'}


def git(root: Path, *args: str) -> str:
    try:
        return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.DEVNULL).decode('utf8', 'replace')
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ''


def clean(s: str) -> str:
    s = html.unescape(str(s))
    s = re.sub(r'```[\s\S]*?```|~~~[\s\S]*?~~~', ' ', s)
    s = re.sub(r'!\[([^]]*)\]\([^)]*\)', ' ', s)
    s = re.sub(r'\[([^]]+)\]\([^)]*\)', r'\1', s)
    s = re.sub(r'<[^>]*>', ' ', s)
    s = re.sub(r'`([^`]*)`', r'\1', s)
    s = re.sub(r'\*\*([^*]+)\*\*|\*([^*]+)\*', lambda m: next(x for x in m.groups() if x is not None), s)
    s = re.sub(r'^[\s>#\-*|]+', ' ', s, flags=re.M)
    return re.sub(r'\s+', ' ', s).strip()


def text_date(v: str) -> str:
    # Date must be a valid YYYY-MM-DD: do not manufacture timestamps.
    s = str(v or '')[:10]
    try:
        return datetime.strptime(s, '%Y-%m-%d').date().isoformat()
    except ValueError:
        return ''


def tags_value(s: str) -> list[str]:
    s = str(s or '').strip().strip('[]')
    return [x.strip().strip('"\'') for x in re.split(r'[,，、]', s) if x.strip()]


def frontmatter(raw: str) -> tuple[dict, str]:
    m = re.match(r'^\ufeff?\s*---\s*\n([\s\S]*?)\n---\s*(?:\n|$)', raw)
    if not m:
        return {}, raw
    meta: dict = {}
    in_tags = False
    for ln in m.group(1).splitlines():
        tag = re.match(r'^\s*-\s+(.+?)\s*$', ln)
        if in_tags and tag:
            meta.setdefault('tags', []).append(tag.group(1).strip().strip('"\''))
            continue
        m2 = re.match(r'^([\w-]+)\s*:\s*(.*)$', ln)
        if not m2:
            continue
        key, value = m2.groups()
        key = key.lower()
        value = value.strip().strip('"\'')
        in_tags = key in ('tags', 'tag', 'categories', 'category') and not value
        if key in ('tags', 'tag', 'categories', 'category'):
            meta['tags'] = tags_value(value)
        else:
            meta[key] = value
    return meta, raw[m.end():]


def md_pick(body: str) -> tuple[str, str, str]:
    # Avoid pulling titles/summaries from fenced code, link lists or table headings.
    s = re.sub(r'^\s*(```|~~~)[\s\S]*?^\s*\1[^\n]*$', '', body, flags=re.M)
    lines = s.splitlines()
    first_title, title_line = '', -1
    first_para, para_line = '', -1
    for i, line in enumerate(lines):
        t = line.strip()
        if not t or t.startswith(('<!--', '<style', '<script')):
            continue
        heading = re.match(r'^#{1,6}\s+(.+?)\s*#*\s*$', t)
        if heading:
            if not first_title:
                first_title, title_line = clean(heading.group(1)), i
            continue
        if first_para != '':
            continue
        if re.match(r'^(?:>|\||[-*+]\s|\d+[.)]\s|!\[|\[!|\s*[-*_]{3,}$|<)', t):
            continue
        para = []
        for nxt in lines[i:]:
            n = nxt.strip()
            if not n or n.startswith(('#', '>', '|', '```', '~~~')):
                break
            para.append(n)
        cand = clean(' '.join(para))
        if len(re.sub(r'\s+', '', cand)) >= 8:
            first_para, para_line = cand, i
    if title_line >= 0 and para_line >= 0 and title_line > para_line:
        first_title = ''
    plain = clean(re.sub(r'^#{1,6}\s+.*$', '', s, flags=re.M))
    return first_title, first_para, plain


class MetadataHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.meta = {}
        self.title = ''
        self.h1 = ''
        self.h2 = ''
        self.p = ''
        self.paragraphs = []
        self._parts = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append(tag)
        if tag == 'meta':
            key = (a.get('name') or a.get('property') or '').lower()
            if key and a.get('content'):
                self.meta[key] = a['content']
        if tag in {'title', 'h1', 'h2', 'p'}:
            self._parts[len(self.tags)] = [tag, []]

    def handle_data(self, data):
        if any(tag in SKIP_HTML for tag in self.tags):
            return
        # append to all open candidates (including nested formatting tags)
        for depth, (tag, buf) in self._parts.items():
            if len(self.tags) >= depth and self.tags[depth - 1] == tag:
                buf.append(data)

    def handle_endtag(self, tag):
        indices = [k for k, v in self._parts.items() if v[0] == tag]
        if indices:
            depth = max(indices)
            _, buf = self._parts.pop(depth)
            t = clean(''.join(buf))
            if tag == 'title' and not self.title: self.title = t
            if tag == 'h1' and not self.h1: self.h1 = t
            if tag == 'h2' and not self.h2: self.h2 = t
            if tag == 'p' and len(t) >= 8: self.paragraphs.append(t)
        if tag in self.tags:
            # HTMLParser allows malformed snippets; recover from mismatch.
            at = len(self.tags) - 1 - self.tags[::-1].index(tag)
            self.tags = self.tags[:at]


def html_pick(raw: str) -> tuple[str, str, str]:
    parser = MetadataHTML()
    parser.feed(raw)
    title = parser.meta.get('og:title') or parser.h1 or parser.title or parser.h2
    desc = parser.meta.get('description') or parser.meta.get('og:description') or (parser.paragraphs[0] if parser.paragraphs else '')
    body = re.sub(r'<(style|script|nav|footer|head|noscript)\b[^>]*>[\s\S]*?</\1>', ' ', raw, flags=re.I)
    return clean(title), clean(desc), clean(body)


def name_title(name: str) -> str:
    stem = Path(name).stem
    stem = re.sub(r'^\d{4}[-_.]?\d{2}[-_.]?\d{2}[\s._-]*', '', stem)
    return re.sub(r'[_-]+', ' ', stem).strip() or Path(name).stem


def file_name_date(name: str) -> str:
    m = re.search(r'(?<!\d)(\d{4})[-_.]?(\d{2})[-_.]?(\d{2})(?!\d)', name)
    return text_date('-'.join(m.groups())) if m else ''


def git_dates(root: Path, path: Path) -> tuple[str, str]:
    rel = path.relative_to(root).as_posix()
    lines = git(root, 'log', '--follow', '--format=%cI', '--', rel).splitlines()
    dates = [text_date(x) for x in lines if text_date(x)]
    return (dates[-1], dates[0]) if dates else ('', '')


def build(root: Path, blogdir: str = 'blog') -> dict:
    folder = root / blogdir
    if not folder.is_dir():
        raise FileNotFoundError(f'blog directory not found: {folder}')
    files = []
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.suffix.lower() not in EXT or path.name.startswith(('_', '.')):
            continue
        raw = path.read_text(encoding='utf-8-sig')
        is_html = path.suffix.lower() in {'.html', '.htm'}
        meta, body = ({}, raw)
        if is_html:
            # The optional old HTML convention is: <!-- title: … | tags: … -->
            m = re.search(r'<!--\s*(.*?)\s*-->', raw, re.S)
            if m and re.search(r'(?:^|\|)\s*(?:title|date|created|updated|summary|tags|tag|cover|draft)\s*:', m.group(1), re.I):
                for bit in m.group(1).split('|'):
                    k, sep, v = bit.partition(':')
                    if sep:
                        k, v = k.strip().lower(), v.strip()
                        if k in ('tags', 'tag'): meta['tags'] = tags_value(v)
                        else: meta[k] = v
                body = raw.replace(m.group(0), '', 1)
            picked_title, picked_summary, plain = html_pick(body)
        else:
            meta, body = frontmatter(raw)
            picked_title, picked_summary, plain = md_pick(body)
        if str(meta.get('draft', '')).lower() in {'true', 'yes', '1'}:
            continue
        title = meta.get('title') or picked_title or name_title(path.name)
        summary = (meta.get('summary') or meta.get('description') or picked_summary or plain)[:SUMMARY_LIMIT]
        created_git, updated_git = git_dates(root, path)
        created = text_date(next((meta[k] for k in ('date','created','published','created_at') if meta.get(k)), '')) or created_git or file_name_date(path.name)
        updated = text_date(next((meta[k] for k in ('updated','modified','last_modified_at','updated_at') if meta.get(k)), '')) or updated_git or created
        if created and updated and updated < created: updated = created
        files.append({
            'name':path.name,'path':path.relative_to(root).as_posix(),
            'sha':hashlib.sha256(path.read_bytes()).hexdigest(),
            'title':str(title).strip(), 'created':created, 'updated':updated,
            'summary':str(summary).strip(), 'tags':meta.get('tags') or [],
            'cover':meta.get('cover') or '', 'words':len(re.sub(r'\s+', '', plain)),
        })
    files.sort(key=lambda p:(p['created'],p['name']), reverse=True)
    return {'version':3,'generated':datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'count':len(files),'files':files}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parent.parent)
    ap.add_argument('--blog-dir',default='blog')
    args=ap.parse_args()
    root=args.root.resolve()
    data=build(root,args.blog_dir)
    out=root / args.blog_dir / 'index.json'
    out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(f'Created {out}: {len(data["files"])} posts')

if __name__=='__main__': main()
