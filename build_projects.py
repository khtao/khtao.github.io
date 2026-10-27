#!/usr/bin/env python3
"""Generate projects.json for the "项目" page — only repos the author created.

Forked repositories are always excluded, so the page never lists somebody
else's work. The snapshot is picked up first by the blog; the browser only
falls back to the live GitHub API when this file is missing.

Standard library only (urllib), no third-party packages, no git required.
Network failures never break the build: the previous snapshot is kept.

Usage:
    python3 scripts/build_projects.py                 # refresh projects.json
    python3 scripts/build_projects.py --dry-run       # print a summary only
    python3 scripts/build_projects.py --strict        # exit 1 on failure
    GITHUB_TOKEN=xxx python3 scripts/build_projects.py  # avoid rate limits
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = 'https://api.github.com'
PER_PAGE = 100
MAX_PAGES = 5
TIMEOUT = 20
KEEP_KEYS = ('name', 'full_name', 'html_url', 'homepage', 'description', 'language',
             'stargazers_count', 'forks_count', 'topics', 'pushed_at', 'updated_at', 'archived')


def load_config(root: Path) -> dict:
    try:
        return json.loads((root / 'config.json').read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def project_settings(cfg: dict) -> tuple[str, list[str]]:
    owner = str(cfg.get('owner') or '').strip()
    if not re.fullmatch(r'[A-Za-z0-9-]+', owner):
        raise ValueError('config.json 缺少合法的 owner，无法确定要读取哪个 GitHub 账号')
    raw = cfg.get('projects')
    block = raw if isinstance(raw, dict) else {}
    exclude = block.get('exclude') or cfg.get('projectExclude') or []
    if isinstance(exclude, str):
        exclude = [exclude]
    return owner, [str(x).strip().lower() for x in exclude if str(x).strip()]


def api_get(url: str, token: str) -> list:
    req = urllib.request.Request(url, headers={
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'khtao-blog-projects',
        **({'Authorization': f'Bearer {token}'} if token else {}),
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode('utf-8', 'replace'))


def fetch_repos(owner: str, token: str = '', pages: int = MAX_PAGES) -> list:
    """Public, non-fork-friendly listing: /users/{owner}/repos?sort=pushed."""
    out: list = []
    for page in range(1, max(1, pages) + 1):
        url = f'{API}/users/{owner}/repos?per_page={PER_PAGE}&page={page}&sort=pushed'
        batch = api_get(url, token)
        if not isinstance(batch, list) or not batch:
            break
        out.extend(batch)
        if len(batch) < PER_PAGE:
            break
    return out


def pick_repos(repos: list, exclude: list[str] | None = None) -> list:
    """Drop forks, private repos and anything explicitly excluded."""
    excluded = {str(x).lower() for x in (exclude or [])}
    kept = []
    for r in repos or []:
        if not isinstance(r, dict):
            continue
        if r.get('fork'):          # fork 的仓库一律不计入
            continue
        if r.get('private'):
            continue
        name = str(r.get('name') or '')
        full = str(r.get('full_name') or '')
        if not (name or full):
            continue
        if name.lower() in excluded or full.lower() in excluded:
            continue
        kept.append(r)
    return kept


def sort_repos(repos: list) -> list:
    """Star 多的在前，同星数时最近推送的在前。"""
    return sorted(repos, key=lambda r: (int(r.get('stargazers_count') or 0),
                                        str(r.get('pushed_at') or r.get('updated_at') or '')),
                  reverse=True)


def slim(r: dict) -> dict:
    out = {k: r.get(k) for k in KEEP_KEYS}
    out['name'] = str(out.get('name') or str(out.get('full_name') or '').split('/')[-1])
    out['full_name'] = str(out.get('full_name') or out['name'])
    out['html_url'] = out.get('html_url') or f"https://github.com/{out['full_name']}"
    out['homepage'] = out.get('homepage') or ''
    out['description'] = out.get('description') or ''
    out['language'] = out.get('language') or ''
    out['stargazers_count'] = int(out.get('stargazers_count') or 0)
    out['forks_count'] = int(out.get('forks_count') or 0)
    out['topics'] = list(out.get('topics') or [])[:6]
    out['pushed_at'] = str(out.get('pushed_at') or out.get('updated_at') or '')[:10]
    out['updated_at'] = str(out.get('updated_at') or '')[:10]
    out['archived'] = bool(out.get('archived'))
    out['fork'] = False
    return out


def build(root: Path, dry_run: bool = False) -> dict:
    cfg = load_config(root)
    owner, exclude = project_settings(cfg)
    repos = sort_repos(pick_repos(fetch_repos(owner, os.environ.get('GITHUB_TOKEN', '')), exclude))
    payload = {
        'version': 1,
        'owner': owner,
        'generated': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'count': len(repos),
        'repos': [slim(r) for r in repos],
    }
    if dry_run:
        return payload
    target = root / 'projects.json'
    text = json.dumps(payload, ensure_ascii=False, indent=2) + '\n'
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            fh.write(text)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--strict', action='store_true', help='失败时以非 0 退出')
    args = ap.parse_args()
    root = args.root.resolve()
    try:
        data = build(root, args.dry_run)
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        # 保留上一次的快照，避免一次网络抖动就把项目页清空
        print(f'[projects] 未更新：{exc}', file=sys.stderr)
        return 1 if args.strict else 0
    stars = sum(r['stargazers_count'] for r in data['repos'])
    where = '（dry-run，未写入）' if args.dry_run else root / 'projects.json'
    print(f"[projects] {data['count']} 个自建仓库 · 累计 {stars} star · {where}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
