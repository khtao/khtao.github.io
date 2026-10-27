"""端到端：按 CI 的顺序跑一遍脚本，校验最终产物。

CI 的顺序是 extract_inline_images → optimize_images → build_index，
顺序错了会导致 index.json 里的 sha 与最终内容不符（缓存判断失真）。
这里固定按这个顺序跑两遍，同时验证幂等。
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'
BLOG = ROOT / 'blog'

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def noisy_jpeg(size=(200, 200), seed=7):
    from PIL import Image as _I
    import io
    import random
    rnd = random.Random(seed)
    data = bytes(rnd.randrange(256) for _ in range(size[0] * size[1] * 3))
    buf = io.BytesIO()
    _I.frombytes('RGB', size, data).save(buf, 'JPEG', quality=85)
    return buf.getvalue()


def run(script, root):
    # 必须显式传 --root：默认指向脚本所在仓库，否则测试会改写真实仓库而不是临时目录
    return subprocess.run([sys.executable, str(SCRIPTS / script), '--root', str(root)],
                          cwd=root, capture_output=True, text=True)


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copytree(BLOG, self.root / 'blog')
        # 塞一篇带内联图的文章，模拟最费的那类内容
        import base64
        b64 = base64.b64encode(noisy_jpeg()).decode()
        (self.root / 'blog' / '内联图测试.html').write_text(
            f'<h1>带内联图</h1><img src="data:image/jpeg;base64,{b64}"><p>结尾</p>',
            encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def _pipeline(self):
        r1 = run('extract_inline_images.py', self.root)
        r2 = run('optimize_images.py', self.root)
        r3 = run('build_index.py', self.root)
        for name, r in (('extract', r1), ('optimize', r2), ('build_index', r3)):
            self.assertEqual(r.returncode, 0, f'{name} 失败：{r.stderr[-400:]}')
        return r1, r2, r3

    @unittest.skipIf(not HAS_PIL, '需要 Pillow')
    def test_pipeline_produces_expected_artifacts(self):
        self._pipeline()
        out = self.root / 'blog'
        self.assertTrue((out / 'index.json').is_file(), '缺少 blog/index.json')
        # feed / sitemap / robots 落在站点根目录，与 index.html 同级
        for f in ('feed.xml', 'sitemap.xml', 'robots.txt'):
            self.assertTrue((self.root / f).is_file(), f'缺少产物 {f}')

        data = json.loads((out / 'index.json').read_text(encoding='utf-8'))
        self.assertGreaterEqual(len(data['files']), 1, 'index.json 应有文章')

        art = (out / '内联图测试.html').read_text(encoding='utf-8')
        self.assertNotIn('base64', art, '#9 内联图未抽出')
        self.assertIn('images/inline/', art, '#9 引用路径不对')

        inline_dir = out / 'images' / 'inline'
        self.assertTrue(inline_dir.is_dir(), '未生成 inline 目录')
        self.assertTrue(list(inline_dir.glob('*.jpg')), '未落盘图片文件')

    @unittest.skipIf(not HAS_PIL, '需要 Pillow')
    def test_pipeline_is_idempotent(self):
        self._pipeline()
        snap = {}
        for p in sorted((self.root / 'blog').rglob('*')):
            if p.is_file():
                snap[p.relative_to(self.root).as_posix()] = p.stat().st_size

        self._pipeline()          # 第二遍

        changed = []
        for rel, size in snap.items():
            p = self.root / rel
            if not p.exists():
                changed.append((rel, '消失'))
            elif p.stat().st_size != size:
                changed.append((rel, f'{size} → {p.stat().st_size}'))
        # 图片重跑不应再变小（画质不累积劣化）
        real = [c for c in changed if 'index.json' not in c[0]
                and 'feed.xml' not in c[0] and 'sitemap.xml' not in c[0]
                and '.optimized.json' not in c[0]]
        self.assertEqual(real, [], f'第二遍改变了产物：{real}')

    @unittest.skipIf(not HAS_PIL, '需要 Pillow')
    def test_webp_twins_exist_for_raster(self):
        self._pipeline()
        imgs = sorted((self.root / 'blog' / 'images').glob('*.jpg'))
        self.assertTrue(imgs, '应有栅格图')
        missing = [p.name for p in imgs if not p.with_suffix('.webp').is_file()]
        self.assertEqual(missing, [], f'缺 WebP：{missing}')


if __name__ == '__main__':
    unittest.main()
