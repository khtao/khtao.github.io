"""Coverage for the robots generator and the image optimizer.

Run with: python3 -m unittest discover -s tests -v
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_index import build_robots  # noqa: E402

try:
    import optimize_images as oi
except ImportError:  # pragma: no cover - scripts/ always importable in this repo
    oi = None


class RobotsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def parse(self, text):
        """Return {user_agent: [directives]}; a bare '*' maps to Allow/Deny list."""
        out, cur = {}, None
        for line in text.splitlines():
            line = line.strip()
            if line.startswith('#') or not line:
                continue
            key, _, val = line.partition(':')
            key, val = key.strip().lower(), val.strip()
            if key == 'user-agent':
                cur = val
                out.setdefault(cur, [])
            elif cur is not None:
                out[cur].append((key, val))
        return out

    def build(self, cfg):
        build_robots(self.root, 'https://example.com/', cfg)
        return (self.root / 'robots.txt').read_text(encoding='utf-8')

    def test_string_input_is_not_split_per_character(self):
        """A stray string must not become one User-agent per character."""
        parsed = self.parse(self.build({'blockedBots': 'MyBot'}))
        self.assertIn('mybot', [k.lower() for k in parsed])
        self.assertNotIn('y', parsed)   # would appear if "MyBot" were exploded
        self.assertNotIn('b', parsed)

    def test_comma_separated_string_is_split(self):
        parsed = self.parse(self.build({'blockedBots': 'A, B'}))
        keys = [k.lower() for k in parsed]
        self.assertIn('a', keys)
        self.assertIn('b', keys)

    def test_list_input_works(self):
        parsed = self.parse(self.build({'blockedBots': ['XBot', 'YBot']}))
        keys = [k.lower() for k in parsed]
        self.assertIn('xbot', keys)
        self.assertIn('ybot', keys)

    def test_default_ai_scrapers_are_denied(self):
        parsed = self.parse(self.build({}))
        keys = [k.lower() for k in parsed]
        for bot in ('gptbot', 'ccbot', 'claudebot', 'google-extended'):
            self.assertIn(bot, keys)
        for bot in ('gptbot', 'ccbot'):
            directives = dict(parsed[[k for k in parsed if k.lower() == bot][0]])
            self.assertEqual(directives.get('disallow'), '/')

    def test_classic_search_engines_still_allowed(self):
        parsed = self.parse(self.build({}))
        star = dict(parsed['*'])
        self.assertEqual(star.get('allow'), '/')

    def test_sitemap_is_emitted(self):
        text = self.build({})
        self.assertIn('Sitemap: https://example.com/sitemap.xml', text)

    def test_duplicates_are_collapsed(self):
        parsed = self.parse(self.build({'blockedBots': ['GPTBot', 'GPTBot']}))
        self.assertEqual(len([k for k in parsed if k.lower() == 'gptbot']), 1)

    def test_empty_entries_dropped(self):
        parsed = self.parse(self.build({'blockedBots': ['', '  ', 'OK']}))
        self.assertNotIn('', parsed)


@unittest.skipIf(oi is None, 'optimize_images.py not importable')
class ImageOptimizerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'blog' / 'images').mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_missing_directory_degrades_gracefully(self):
        empty = self.root / 'nope'
        empty.mkdir()
        oi.scan(empty, 'blog')
        # 只要不抛异常即通过；目录下没有 images/ 时应该安静跳过
        self.assertTrue(True)

    def test_manifest_skips_already_processed_files(self):
        """Second run must be a no-op: never re-compress (quality would decay)."""
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Pillow not installed')
        img_dir = self.root / 'blog' / 'images'
        p = img_dir / 'a.png'
        Image.new('RGB', (8, 8), (200, 30, 30)).save(p)
        oi.scan(self.root, 'blog')                       # 第一次：压缩 + 生成 webp
        manifest = json.loads((img_dir / oi.MANIFEST).read_text())
        digest_after_first = manifest['a.png']['sha']
        stats = oi.scan(self.root, 'blog')               # 第二次
        self.assertEqual(stats['compressed'], 0, '第二次不应重复压缩')
        self.assertEqual(stats['files'], 1)
        manifest2 = json.loads((img_dir / oi.MANIFEST).read_text())
        self.assertEqual(manifest2['a.png']['sha'], digest_after_first)
        self.assertEqual(
            manifest['a.png']['sha'],
            oi.sha256(p), 'manifest 记录的应是落盘后的 sha')

    def test_webp_twin_is_written(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Pillow not installed')
        img_dir = self.root / 'blog' / 'images'
        Image.new('RGB', (8, 8), (10, 120, 200)).save(img_dir / 'b.jpg')
        oi.scan(self.root, 'blog')
        self.assertTrue((img_dir / 'b.webp').is_file())

    def test_svg_and_other_files_untouched(self):
        svg = self.root / 'blog' / 'images' / 'c.svg'
        svg.write_text('<svg/>', encoding='utf-8')
        stats = oi.scan(self.root, 'blog')
        self.assertEqual(stats['files'], 0, '非栅格图不应被处理')
        self.assertEqual(svg.read_text(encoding='utf-8'), '<svg/>')


if __name__ == '__main__':
    unittest.main()
