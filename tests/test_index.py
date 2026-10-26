"""Run locally with: python3 -m unittest discover -s tests -v"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_index import build  # noqa: E402


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'blog').mkdir()
        subprocess.run(['git', 'init', '-q', '-b', 'main'], cwd=self.root, check=True)
        subprocess.run(['git', 'config', 'user.name', 'Blog test'], cwd=self.root, check=True)
        subprocess.run(['git', 'config', 'user.email', 'test@example.com'], cwd=self.root, check=True)

    def tearDown(self):
        self.temp.cleanup()

    def commit(self, date):
        env = os.environ.copy()
        env.update({'GIT_AUTHOR_DATE': f'{date}T12:00:00+00:00',
                    'GIT_COMMITTER_DATE': f'{date}T12:00:00+00:00'})
        subprocess.run(['git', 'add', '-A'], cwd=self.root, env=env, check=True)
        subprocess.run(['git', 'commit', '-qm', 'update article'], cwd=self.root, env=env, check=True)

    def test_markdown_without_frontmatter_tracks_first_and_last_commit(self):
        post = self.root / 'blog' / '我的文章.md'
        post.write_text('# 自动提取标题\n\n这是一段很重要的摘要内容，用来测试元数据自动识别。\n', encoding='utf8')
        self.commit('2025-02-03')
        post.write_text(post.read_text(encoding='utf8') + '\n## 修订\n又写了一段。\n', encoding='utf8')
        self.commit('2025-04-05')
        obj=build(self.root)
        self.assertEqual(obj['count'],1)
        article=obj['files'][0]
        self.assertEqual(article['title'],'自动提取标题')
        self.assertEqual(article['created'],'2025-02-03')
        self.assertEqual(article['updated'],'2025-04-05')
        self.assertIn('很重要的摘要内容',article['summary'])
        self.assertTrue(article['sha'])

    def test_html_without_head_info(self):
        post=self.root / 'blog' / 'html示例.html'
        post.write_text('<html><head><title>文档标题</title><meta name="description" content="自动抓取描述"></head>'
                        '<body><h1>正文标题</h1><p>这是一段长一点的正文介绍内容。</p></body></html>',encoding='utf8')
        self.commit('2025-05-06')
        article=build(self.root)['files'][0]
        self.assertEqual(article['title'],'正文标题')
        self.assertEqual(article['summary'],'自动抓取描述')
        self.assertEqual(article['created'],'2025-05-06')

    def test_deleted_last_article_yields_valid_empty_list(self):
        post=self.root / 'blog' / 'a.md'
        post.write_text('# Test\n\n正文文本足够长用于自动摘要。',encoding='utf8')
        self.commit('2025-06-06')
        self.assertEqual(build(self.root)['count'],1)
        post.unlink()
        self.commit('2025-06-07')
        result=build(self.root)
        self.assertEqual(result['count'],0)
        self.assertEqual(result['files'],[])

    def test_frontmatter_overrides_and_draft(self):
        post=self.root / 'blog' / 'a.md'
        post.write_text('---\ntitle: 手写标题\ndate: 2023-01-01\nupdated: 2023-02-01\n'
                        'summary: 手写摘要\ntags: [技术,随笔]\n---\n# 自动标题\n\n正文内容\n',encoding='utf8')
        draft=self.root / 'blog' / 'draft.md'
        draft.write_text('---\ndraft: true\n---\n# 不公开\n',encoding='utf8')
        self.commit('2025-07-07')
        result=build(self.root)
        self.assertEqual(result['count'],1)
        article=result['files'][0]
        self.assertEqual(article['title'],'手写标题')
        self.assertEqual(article['created'],'2023-01-01')
        self.assertEqual(article['updated'],'2023-02-01')
        self.assertEqual(article['summary'],'手写摘要')
        self.assertEqual(article['tags'],['技术','随笔'])


if __name__ == '__main__':
    unittest.main()
