"""构建流水线回归测试（Python 侧）。

覆盖问题：
  #9   文章里 base64 内联图片（2.76MB，99% 体积），WebP/懒加载完全管不到
  #15  索引脚本每篇文章一次 `git log --follow`（50 篇 = 19 秒）
  #16  manifest 命中但 WebP 文件已丢 → 永远补不回来
  #2   workflow 的 paths 不含 assets/** → 只提交 assets 不触发构建
  #3   ubuntu-24.04 的 PEP 668 让裸 pip install 失败 → 图片优化被静默跳过
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import build_index  # noqa: E402
import extract_inline_images as ex  # noqa: E402
import optimize_images as oi  # noqa: E402

WORKFLOW = ROOT / '.github' / 'workflows' / 'blog-index.yml'

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def tiny_jpeg_bytes(color=(200, 60, 60), size=(8, 8)):
    """小图：低于 extract_inline_images.MIN_BYTES，用于验证「不值得抽」的分支。"""
    from PIL import Image as _I
    import io
    buf = io.BytesIO()
    _I.new('RGB', size, color).save(buf, 'JPEG')
    return buf.getvalue()


def noisy_jpeg_bytes(size=(240, 240)):
    """噪声图：体积远超 2KB 阈值，确保真的会被抽出（JPEG 压不动随机噪声）。"""
    from PIL import Image as _I
    import io
    import random
    rnd = random.Random(42)
    data = bytes(rnd.randrange(256) for _ in range(size[0] * size[1] * 3))
    img = _I.frombytes('RGB', size, data)
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=85)
    return buf.getvalue()


class InlineImageTests(unittest.TestCase):
    """#9 把 base64 内联图抽成真正的文件。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'blog').mkdir()

    def tearDown(self):
        self.temp.cleanup()

    @unittest.skipIf(not HAS_PIL, '需要 Pillow 构造测试图片')
    def test_extracts_and_rewrites_source(self):
        import base64
        raw = noisy_jpeg_bytes()
        b64 = base64.b64encode(raw).decode()
        art = self.root / 'blog' / '游记.html'
        art.write_text(f'<p>前面</p><img src="data:image/jpeg;base64,{b64}"><p>后面</p>',
                       encoding='utf-8')
        before = art.stat().st_size
        ex.scan(self.root, 'blog')
        text = art.read_text(encoding='utf-8')

        self.assertLess(art.stat().st_size, before, '#9 源码应变小')
        self.assertNotIn('base64', text, '#9 不应残留 base64')
        # 引用必须是 images/inline/...，否则相对文章目录解析不到
        self.assertIn('src="images/inline/', text, f'#9 引用路径错误：{text}')
        self.assertTrue((self.root / 'blog' / 'images' / 'inline').is_dir())

    @unittest.skipIf(not HAS_PIL, '需要 Pillow')
    def test_idempotent(self):
        import base64
        b64 = base64.b64encode(noisy_jpeg_bytes()).decode()
        art = self.root / 'blog' / 'a.html'
        art.write_text(f'<img src="data:image/jpeg;base64,{b64}">', encoding='utf-8')
        ex.scan(self.root, 'blog')
        after_first = art.read_text(encoding='utf-8')
        stats = ex.scan(self.root, 'blog')       # 第二次
        self.assertEqual(stats['images'], 0, '#9 第二次应无操作')
        self.assertEqual(art.read_text(encoding='utf-8'), after_first)

    @unittest.skipIf(not HAS_PIL, '需要 Pillow')
    def test_same_image_deduplicated(self):
        """同一张图在多篇文章里出现，只应落一份文件（内容 hash 命名）。"""
        import base64
        b64 = base64.b64encode(noisy_jpeg_bytes()).decode()
        for name in ('a.html', 'b.html'):
            (self.root / 'blog' / name).write_text(
                f'<img src="data:image/jpeg;base64,{b64}">', encoding='utf-8')
        ex.scan(self.root, 'blog')
        files = list((self.root / 'blog' / 'images' / 'inline').iterdir())
        self.assertEqual(len(files), 1, f'#9 应去重为 1 份，实际 {len(files)}')

    def test_tiny_images_left_alone(self):
        """小于阈值的内联图不值得多一次请求，应原样保留。"""
        import base64
        small = base64.b64encode(b'x' * 64).decode()
        art = self.root / 'blog' / 'c.html'
        art.write_text(f'<img src="data:image/png;base64,{small}">', encoding='utf-8')
        ex.scan(self.root, 'blog')
        self.assertIn('base64', art.read_text(encoding='utf-8'), '过小的图不应被抽出')

    def test_articles_without_images_untouched(self):
        art = self.root / 'blog' / 'd.md'
        original = '# 标题\n\n正文没有图片。\n'
        art.write_text(original, encoding='utf-8')
        ex.scan(self.root, 'blog')
        self.assertEqual(art.read_text(encoding='utf-8'), original)


@unittest.skipIf(not HAS_PIL, '需要 Pillow')
class OptimizerTests(unittest.TestCase):
    """#16 WebP 丢了必须能补回来。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'blog' / 'images').mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def _one(self):
        p = self.root / 'blog' / 'images' / 'p.jpg'
        p.write_bytes(tiny_jpeg_bytes())
        return p

    def test_webp_regenerated_when_missing(self):
        p = self._one()
        oi.scan(self.root, 'blog')
        self.assertTrue(p.with_suffix('.webp').is_file(), '首次应生成 WebP')

        p.with_suffix('.webp').unlink()          # 模拟误删 / 被 .gitignore 排除
        stats = oi.scan(self.root, 'blog')
        self.assertTrue(p.with_suffix('.webp').is_file(),
                        '#16 WebP 丢失后必须重新生成（否则前端永远回退原图）')
        self.assertGreaterEqual(stats['compressed'], 1,
                                '#16 不能因为 manifest 命中就跳过（会永远补不回来）')

    def test_second_run_is_noop(self):
        p = self._one()
        oi.scan(self.root, 'blog')
        stats = oi.scan(self.root, 'blog')
        self.assertEqual(stats['compressed'], 0, '第二次不应重复压缩（画质会累积劣化）')

    def test_svg_untouched(self):
        svg = self.root / 'blog' / 'images' / 'x.svg'
        svg.write_text('<svg/>', encoding='utf-8')
        stats = oi.scan(self.root, 'blog')
        self.assertEqual(stats['files'], 0, 'SVG 不应被当栅格图处理')
        self.assertEqual(svg.read_text(encoding='utf-8'), '<svg/>')


class GitDateTests(unittest.TestCase):
    """#15 批量取日期必须与逐文件 --follow 结果一致。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'blog').mkdir()
        self._git('init', '-q', '-b', 'main')
        self._git('config', 'user.name', 'T')
        self._git('config', 'user.email', 't@t')

    def tearDown(self):
        self.temp.cleanup()

    def _git(self, *args, **env):
        e = dict(os.environ)
        e.update(env)
        return subprocess.run(['git', *args], cwd=self.root, check=True,
                              capture_output=True, env=e)

    def _commit(self, date):
        self._git('add', '-A')
        self._git('commit', '-qm', 'c',
                  GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)

    def test_bulk_matches_follow(self):
        names = [f'post{i:02d}.md' for i in range(6)]
        for n in names:
            (self.root / 'blog' / n).write_text(f'# {n}\n\n正文。\n', encoding='utf-8')
        self._commit('2026-01-01T10:00:00+0000')
        # 只改前 3 篇，制造不同的 updated
        for n in names[:3]:
            p = self.root / 'blog' / n
            p.write_text(p.read_text(encoding='utf-8') + '\n第二次提交。\n', encoding='utf-8')
        self._commit('2026-03-05T10:00:00+0000')

        bulk, renamed = build_index.git_dates_bulk(self.root)
        mismatch = []
        for n in names:
            p = self.root / 'blog' / n
            follow = build_index.git_dates(self.root, p)          # 旧逻辑（逐文件）

            b = bulk.get('blog/' + n)
            got = (b[-1], b[0]) if b else ('', '')
            if got != follow:
                mismatch.append((n, got, follow))
        self.assertEqual(mismatch, [], f'#15 批量结果不一致：{mismatch}')

        # 抽样校验具体日期
        self.assertEqual(build_index.git_dates(self.root, self.root / 'blog' / 'post00.md', bulk, renamed),
                         ('2026-01-01', '2026-03-05'))
        self.assertEqual(build_index.git_dates(self.root, self.root / 'blog' / 'post05.md', bulk, renamed),
                         ('2026-01-01', '2026-01-01'))

    def test_renamed_file_falls_back_to_follow(self):
        """批量查询按路径收集，重命名过的文件在新路径下查不到旧历史。
        必须回退到 --follow 才能拿到改名前那次提交，否则 created 会算错。"""
        old = self.root / 'blog' / '旧名字.md'
        old.write_text('# 旧名字\n\n正文。\n', encoding='utf-8')
        self._commit('2026-01-01T10:00:00+0000')

        new = self.root / 'blog' / '新名字.md'
        old.rename(new)
        self._commit('2026-04-01T10:00:00+0000')

        bulk, renamed = build_index.git_dates_bulk(self.root)
        # 批量按路径统计，重命名后的新路径只挂得上改名那次提交
        self.assertEqual(bulk.get('blog/新名字.md'), ['2026-04-01'],
                         f'批量按路径统计，实际 {bulk.get("blog/新名字.md")}')

        # 但 git_dates 必须回退到 --follow，把改名前那次也算进来
        got = build_index.git_dates(self.root, new, bulk, renamed)
        self.assertEqual(got, ('2026-01-01', '2026-04-01'),
                         f'重命名文件必须回退 --follow，实际 {got}')

    def test_sha_matches_file_content(self):
        """index.json 的 sha 决定前端是否重新拉正文，必须等于文件真实摘要。"""
        art = self.root / 'blog' / '正文.md'
        art.write_text('# 标题\n\n正文内容。\n', encoding='utf-8')
        self._commit('2026-01-01T10:00:00+0000')
        data = build_index.build(self.root, 'blog')
        entry = next(f for f in data['files'] if f['name'] == '正文.md')

        import hashlib
        # 前端用这个 sha 判断「正文要不要重新拉」，必须精确等于文件内容摘要
        self.assertEqual(entry['sha'], hashlib.sha256(art.read_bytes()).hexdigest(),
                         'sha 必须等于文件内容 sha256，否则缓存判断会失真')
        # 改内容 → sha 必须变，否则改了文章访客还读旧的
        art.write_text('# 标题\n\n改过的正文。\n', encoding='utf-8')
        self._commit('2026-02-01T10:00:00+0000')
        d2 = build_index.build(self.root, 'blog')
        e2 = next(f for f in d2['files'] if f['name'] == '正文.md')
        self.assertNotEqual(e2['sha'], entry['sha'], '内容改变后 sha 必须变')

    def test_non_ascii_paths_are_not_quoted_away(self):
        """中文文件名必须命中批量结果。

        git 默认把非 ASCII 路径转义成 "blog/\344\270\255..." 并加引号。
        不加 core.quotePath=false 的话，中文仓库里每篇文章都匹配不上，
        静默退化回逐文件 --follow —— 结果仍正确，但批量优化等于白做，
        且没有任何报错。这是本次审计实际抓到的 bug。
        """
        names = ['桂林山水.md', '从零部署博客.md', '50个必去的地方.html']
        for n in names:
            (self.root / 'blog' / n).write_text('# t\n\n正文。\n', encoding='utf-8')
        self._commit('2026-01-01T10:00:00+0000')

        bulk, renamed = build_index.git_dates_bulk(self.root)
        for n in names:
            self.assertIn('blog/' + n, bulk,
                          f'中文文件名「{n}」未命中批量结果（路径被转义了？）现有 key: '
                          f'{[k for k in bulk if "blog/" in k][:3]}')
            self.assertEqual(bulk['blog/' + n], ['2026-01-01'])

        # 命中后 git_dates 应直接取用，不再逐个 spawn --follow
        p = self.root / 'blog' / names[0]
        self.assertEqual(build_index.git_dates(self.root, p, bulk, renamed),
                         ('2026-01-01', '2026-01-01'))

    def test_bulk_is_single_git_call(self):
        """批量方案的关键：不是 N 次子进程。"""
        for i in range(10):
            (self.root / 'blog' / f'p{i}.md').write_text('# t\n\n正文。\n', encoding='utf-8')
        self._commit('2026-01-01T10:00:00+0000')

        calls = {'n': 0}
        real = build_index.git

        def counting(*args, **kw):
            calls['n'] += 1
            return real(*args, **kw)

        build_index.git = counting
        try:
            build_index.git_dates_bulk(self.root)
            one = calls['n']
            calls['n'] = 0
            for p in sorted((self.root / 'blog').iterdir()):
                build_index.git_dates(self.root, p)      # 回退路径（无 bulk）
            many = calls['n']
        finally:
            build_index.git = real

        self.assertEqual(one, 1, f'#15 批量应只调 1 次 git，实际 {one}')
        self.assertGreater(many, 1, '旧的逐文件方式确实是多进程（对照）')
        self.assertLess(one, many, '#15 批量必须比逐文件少')


class WorkflowTests(unittest.TestCase):
    """#2/#3 workflow 配置检查（纯文本，无需 PyYAML）。"""

    def setUp(self):
        self.text = WORKFLOW.read_text(encoding='utf-8')

    def test_assets_in_trigger_paths(self):
        self.assertIn("'assets/**'", self.text,
                      "#2 只提交 assets/ 时不会触发构建 → 本地化脚本静默不发版")

    def test_extract_runs_before_index(self):
        i_ex = self.text.find('extract_inline_images.py')
        i_build = self.text.find('build_index.py')
        self.assertGreater(i_ex, 0, '#9 提取步骤缺失')
        self.assertLess(i_ex, i_build,
                        '#9 提取必须在 build_index 之前（否则 sha 算的是旧内容）')

    def test_pillow_install_has_fallback(self):
        self.assertIn('--break-system-packages', self.text,
                      '#3 ubuntu-24.04 的 PEP 668 会让裸 pip install 失败')
        self.assertIn('apt-get install', self.text, '#3 应有 apt 兜底')
        self.assertIn('python3 -c "import PIL"', self.text, '#3 已装则跳过')

    def test_optimized_manifest_not_published(self):
        self.assertIn(".optimized.json", self.text, '构建期账本不应随站点发布')


if __name__ == '__main__':
    unittest.main()
