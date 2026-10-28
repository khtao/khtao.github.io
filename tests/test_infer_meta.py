"""无头信息文章的元信息推断测试。

覆盖：
  1. md / html 两种格式都能推断出分类、标签、摘要
  2. 推断必须"综合全文"——主题词只出现在后半段时也要抓到
  3. 不能出现「未分类」这种死胡同
  4. 作者显式写的值永远优先，不被推断覆盖
  5. 部分缺失（只写了 title）时，只补缺失的字段
  6. 摘要：首段够长就用首段；首段太短才动用全文选句
  7. 退化场景：完全没有可识别主题时也要给出一个可用的分类
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import build_index  # noqa: E402
import infer_meta as im  # noqa: E402


def noisy_jpeg_bytes(size=(32, 32)):
    from PIL import Image as _I
    import io
    import random
    rnd = random.Random(1)
    data = bytes(rnd.randrange(256) for _ in range(size[0] * size[1] * 3))
    buf = io.BytesIO()
    _I.frombytes('RGB', size, data).save(buf, 'JPEG')
    return buf.getvalue()


class AnalyzeTests(unittest.TestCase):
    """直接测推断核心。"""

    def test_travel_article_inferred(self):
        text = ('这次自驾去了三个景区，门票加起来不便宜。' * 2 +
                '景区之间要坐观光车，索道另外收费。高铁到达后租车最方便。' * 3)
        r = im.analyze('', text)
        self.assertEqual(r['category'], '旅行')
        self.assertIn('景区', r['tags'])
        self.assertTrue(r['summary'])

    def test_tech_article_inferred(self):
        text = ('部署到服务器之前要先装依赖，配置好数据库。' * 2 +
                '如果报错就查日志，调试完再提交到仓库的新分支。' * 3)
        r = im.analyze('', text)
        self.assertEqual(r['category'], '技术')
        self.assertTrue(r['summary'])

    def test_topic_only_in_later_part(self):
        """综合全文：主题词只在后半段出现，也要抓到。
        只看开头的话这里会抓成摄影。"""
        # 前半段刻意不含任何领域词典的词（纯日常叙述），主题只在后半段出现。
        # 任何"只看开头 N 字"的实现在这里都抓不到旅行。
        head = '那一天我们聊了很多从前的旧事，也说起了各自近况，时间过得很慢。' * 10
        tail = '这次行程一共跑了四个景区，门票和观光车都不便宜，' \
               '酒店订在景区门口，自驾过去最方便，索道另外收费。' * 12
        self.assertGreater(len(head), 200, 'head 要超过「只看开头」的窗口，否则测不出问题')
        r = im.analyze('', head + tail)
        self.assertEqual(r['category'], '旅行',
                         f'主题词集中在后半段时应抓到旅行，实际 {r["category"]}')

    def test_never_unclassified(self):
        for text in ('今天天气不错。' * 5,
                     '随便写点什么，凑够长度看看会不会有问题。' * 3,
                     ''):
            r = im.analyze('', text)
            self.assertNotEqual(r['category'], '未分类')
            self.assertTrue(r['category'], '分类不能是空字符串')
            self.assertTrue(r['tags'], '至少要有一个标签')

    def test_fallback_uses_frequent_term(self):
        """词典覆盖不到的主题：用全文最高频实词，而不是「未分类」。"""
        text = '雾化玻璃的透光率会随电压变化，调光膜贴在玻璃夹层里。' * 4
        r = im.analyze('', text)
        self.assertNotEqual(r['category'], im.FALLBACK_CATEGORY)
        joined = ' '.join(r['tags'])
        self.assertTrue(any(w in r['category'] or w in joined
                            for w in ('雾化', '玻璃', '调光', '透光')),
                        f'应从正文抓出主题词，实际 {r["category"]} / {r["tags"]}')

    def test_tags_are_reasonable(self):
        text = ('景区门票和观光车的费用要提前算好，自驾停车也要注意。' * 4)
        r = im.analyze('', text)
        self.assertGreaterEqual(len(r['tags']), 1)
        self.assertLessEqual(len(r['tags']), 5)
        for t in r['tags']:
            self.assertLessEqual(len(t), 8, f'标签过长：{t}')
            self.assertNotIn(t, im.STOPWORDS)
        # 不重复
        self.assertEqual(len(r['tags']), len(set(t.lower() for t in r['tags'])))

    def test_summary_prefers_real_sentence(self):
        """摘要不该挑中列表项或表格碎片。"""
        text = ('这次行程里，景区门票和观光车的开销占了大头，提前算清楚能省不少。\n'
                '1. 门票 108 元\n'
                '2. 观光车 35 元 ¥143\n'
                '3. 索道 60 元\n')
        r = im.analyze('', text)
        self.assertIn('开销', r['summary'],
                      f'应选概括句而非价格清单，实际：{r["summary"]}')

    def test_title_hint_skips_meaningless_name(self):
        r = im.analyze('', '这是一段足够长的正文内容，用来测试标题兜底是否生效。', '1.md')
        self.assertTrue(r['title_hint'])
        self.assertNotEqual(r['title_hint'].strip(), '1')

    def test_empty_input_is_safe(self):
        r = im.analyze('', '')
        self.assertTrue(r['category'])
        self.assertIsInstance(r['tags'], list)

    def test_long_article_is_not_slow(self):
        """超长文章必须走扫描上限，不能拖慢构建。"""
        big = ('景区门票和观光车费用需要提前确认，自驾出行的停车问题也要考虑。' * 4000)
        import time
        t = time.time()
        r = im.analyze('', big)
        self.assertLess(time.time() - t, 3.0, '大文件推断不应超过 3 秒')
        self.assertEqual(r['category'], '旅行')


class BuildIntegrationTests(unittest.TestCase):
    """走完整 build()，验证与 front-matter 的优先级关系。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'blog').mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def _commit(self):
        subprocess.run(['git', 'init', '-q', '-b', 'main'], cwd=self.root, check=True,
                       capture_output=True)
        subprocess.run(['git', 'config', 'user.name', 'T'], cwd=self.root, check=True)
        subprocess.run(['git', 'config', 'user.email', 't@t'], cwd=self.root, check=True)
        subprocess.run(['git', 'add', '-A'], cwd=self.root, check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-qm', 'c'], cwd=self.root, check=True,
                       capture_output=True,
                       env={'GIT_AUTHOR_DATE': '2026-01-01T10:00:00+0000',
                            'GIT_COMMITTER_DATE': '2026-01-01T10:00:00+0000',
                            'PATH': '/usr/bin:/bin:/usr/local/bin',
                            'HOME': str(self.root)})

    def _one(self, name, text):
        (self.root / 'blog' / name).write_text(text, encoding='utf-8')
        self._commit()
        data = build_index.build(self.root, 'blog')
        return data['files'][0]

    def test_markdown_without_frontmatter(self):
        post = self._one('无头信息.md',
                         '# 周末去了趟山里\n\n'
                         '这次自驾跑了两个景区，门票和观光车都不便宜，酒店订在景区门口。\n\n'
                         '路上还遇到几处观景台，停车方便，适合拍照。\n')
        self.assertEqual(post['title'], '周末去了趟山里')
        self.assertEqual(post['category'], '旅行')
        self.assertNotEqual(post['category'], '未分类')
        self.assertTrue(post['tags'])
        self.assertTrue(post['summary'])

    def test_html_without_frontmatter(self):
        post = self._one('游记.html',
                         '<html><head><title>山中两日</title></head><body>'
                         '<h1>山中两日</h1>'
                         '<p>这次行程一共三个景区，门票加观光车一共两百多，'
                         '自驾过去停车也方便，酒店就在景区附近。</p>'
                         '<p>第二天还坐了索道。</p>'
                         '</body></html>')
        self.assertEqual(post['category'], '旅行')
        self.assertTrue(post['tags'])
        self.assertIn('景区', post['tags'] + [post['category']])

    def test_explicit_metadata_wins(self):
        """作者写的值不能被推断覆盖。"""
        post = self._one('显式.md',
                         '---\ntitle: 手写标题\ncategory: 摄影\ntags: [胶片, 暗房]\n'
                         'summary: 手写摘要\n---\n'
                         '# 正文标题\n\n景区门票和观光车很贵，自驾也不方便。\n')
        self.assertEqual(post['title'], '手写标题')
        self.assertEqual(post['category'], '摄影')
        self.assertEqual(post['tags'], ['胶片', '暗房'])
        self.assertEqual(post['summary'], '手写摘要')

    def test_partial_metadata_fills_gaps(self):
        """只写了 title：分类和标签要补上，title 保持不动。"""
        post = self._one('半截.md',
                         '---\ntitle: 只写了标题\n---\n'
                         '# 正文\n\n这次部署到服务器，配置数据库，装依赖，'
                         '报错就查日志，调试完提交到仓库分支。\n')
        self.assertEqual(post['title'], '只写了标题')
        self.assertEqual(post['category'], '技术')
        self.assertTrue(post['tags'])

    def test_html_comment_metadata_still_works(self):
        """HTML 的 <!-- title: … | tags: […] --> 约定仍优先于推断。"""
        post = self._one('旧约定.html',
                         '<!-- title: 旧标题 | tags: [甲, 乙] | category: 随笔 -->\n'
                         '<html><body><p>景区门票和观光车都不便宜，自驾也麻烦。</p></body></html>')
        self.assertEqual(post['title'], '旧标题')
        self.assertEqual(post['tags'], ['甲', '乙'])
        self.assertEqual(post['category'], '随笔')

    def test_no_article_ends_up_unclassified(self):
        for i, txt in enumerate([
            '随便写的一段文字，没有明显主题。\n',
            '# 有标题没正文\n',
            '今天看了一部电影，剧情还不错，演员演得也挺好，导演的镜头语言很特别。\n',
        ]):
            (self.root / 'blog' / f'p{i}.md').write_text(txt, encoding='utf-8')
        self._commit()
        data = build_index.build(self.root, 'blog')
        for post in data['files']:
            self.assertNotEqual(post['category'], '未分类',
                                f'{post["name"]} 被归为未分类')
            self.assertTrue(post['category'], f'{post["name"]} 分类为空')

    def test_summary_falls_back_to_full_text_when_lead_is_thin(self):
        """首段太短撑不起摘要时，应从全文挑一句。"""
        # 首段 8 字：md_pick 会收下它（>=8 才算段落），但短到撑不起摘要
        post = self._one('短开头.md',
                         '# 标题\n\n'
                         '出发前要做好准备。\n\n'
                         '这次行程里，景区门票与观光车的开销占了大头，'
                         '提前算清楚能省下不少预算。\n')
        self.assertNotEqual(post['summary'].strip(), '出发前要做好准备。')
        self.assertIn('开销', post['summary'],
                      f'首段过短时应从全文挑一句，实际：{post["summary"]}')


if __name__ == '__main__':
    unittest.main()
