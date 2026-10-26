"""Offline regression tests: python3 -m unittest discover -s tests -v"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_index import build, frontmatter, md_pick, html_pick


class StaticManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'blog').mkdir()
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True)
        subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=self.root, check=True)
        subprocess.run(['git', 'config', 'user.email', 'test@example.com'], cwd=self.root, check=True)

    def tearDown(self):
        self.temp.cleanup()

    def commit(self, date):
        env = dict(os.environ, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
        subprocess.run(['git', 'add', '-A'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'test'], cwd=self.root, check=True, env=env)

    def test_automatic_markdown_and_git_dates(self):
        article = self.root / 'blog' / '随手记录.md'
        article.write_text('# 第一篇没有头信息的文章\n\n这是我写的一段完整摘要，足够在博客列表里正常呈现。\n', encoding='utf8')
        self.commit('2024-01-02T08:30:00+0000')
        article.write_text(article.read_text(encoding='utf8') + '\n## 小结\n这里新增一个章节。\n', encoding='utf8')
        self.commit('2025-02-03T08:30:00+0000')
        post = build(self.root)['files'][0]
        self.assertEqual(post['title'], '第一篇没有头信息的文章')
        self.assertTrue(post['summary'].startswith('这是我写的一段完整摘要'))
        self.assertEqual(post['created'], '2024-01-02')
        self.assertEqual(post['updated'], '2025-02-03')

    def test_yaml_override_and_array_tags(self):
        article = self.root / 'blog' / '标注.md'
        article.write_text('---\ntitle: 手动标题\nsummary: 特别摘要\ntags:\n  - 技术\n  - 随笔\ndate: 2020-05-06\nupdated: 2021-06-07\n---\n# 原标题\n\n另外一段足够长的介绍文字。', encoding='utf8')
        self.commit('2026-10-26T10:00:00+0000')
        post = build(self.root)['files'][0]
        self.assertEqual((post['title'], post['summary']), ('手动标题', '特别摘要'))
        self.assertEqual(post['tags'], ['技术', '随笔'])
        self.assertEqual((post['created'], post['updated']), ('2020-05-06', '2021-06-07'))

    def test_headerless_html_and_empty_after_delete(self):
        article = self.root / 'blog' / '页面.html'
        article.write_text('<html><head><title>后备标题</title><meta name="description" content="来自 SEO 描述的摘要"></head><body><h1>正文标题</h1><p>这是正文中的第一段详细文字。</p></body></html>', encoding='utf8')
        self.commit('2026-01-02T00:00:00+0000')
        post = build(self.root)['files'][0]
        self.assertEqual(post['title'], '正文标题')
        self.assertEqual(post['summary'], '来自 SEO 描述的摘要')
        article.unlink()
        self.commit('2026-01-03T00:00:00+0000')
        result = build(self.root)
        self.assertEqual(result['count'], 0)
        self.assertEqual(result['files'], [])

    def test_filename_fallback_and_draft(self):
        (self.root / 'blog' / '20260101-一篇笔记.md').write_text('这里没有标题但是有一段有意义的介绍内容。', encoding='utf8')
        (self.root / 'blog' / '草稿.md').write_text('---\ndraft: true\n---\n# 不发布', encoding='utf8')
        data = build(self.root)
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['files'][0]['title'], '一篇笔记')
        self.assertEqual(data['files'][0]['created'], '2026-01-01')

    def test_ignore_heading_in_code_block(self):
        title, summary, _ = md_pick('```md\n# 不能是标题\n```\n\n# 真正的标题\n\n这是正文第一段有意义的介绍文字。')
        self.assertEqual(title, '真正的标题')
        self.assertTrue(summary.startswith('这是正文'))


if __name__ == '__main__':
    unittest.main()
