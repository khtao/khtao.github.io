"""Regression tests for safe manual image upload and immutable published URLs."""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPT_DIR))
from import_images import import_one, safe_segment  # noqa: E402
from check_image_overwrites import changes  # noqa: E402
from extract_inline_images import process_file  # noqa: E402
from optimize_images import scan  # noqa: E402


class ImportTests(unittest.TestCase):
    def test_same_name_different_bytes_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            first = d / 'a' / '01.jpg'
            second = d / 'b' / '01.jpg'
            first.parent.mkdir()
            second.parent.mkdir()
            first.write_bytes(b'A' * 100)
            second.write_bytes(b'B' * 100)
            out = d / 'blog' / 'images' / 'trip'
            out.mkdir(parents=True)
            p1, fresh1 = import_one(first, out)
            p2, fresh2 = import_one(second, out)
            self.assertNotEqual(p1, p2)
            self.assertTrue(fresh1 and fresh2)
            self.assertEqual(p1.read_bytes(), b'A' * 100)
            self.assertEqual(p2.read_bytes(), b'B' * 100)
            reused, fresh3 = import_one(first, out)
            self.assertEqual(reused, p1)
            self.assertFalse(fresh3)

    def test_prefix_collision_extends_hash_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            src = d / 'cover.jpg'
            raw = b'expected content'
            src.write_bytes(raw)
            digest = hashlib.sha256(b'.jpg\0' + raw).hexdigest()
            out = d / 'dest'
            out.mkdir()
            collision = out / f'cover-{digest[:12]}.jpg'
            collision.write_bytes(b'PREEXISTING DIFFERENT DATA')
            new, is_new = import_one(src, out)
            self.assertEqual(new.name, f'cover-{digest[:16]}.jpg')
            self.assertTrue(is_new)
            self.assertEqual(collision.read_bytes(), b'PREEXISTING DIFFERENT DATA')

    def test_invalid_slugs(self):
        for name in ('../other', 'foo/bar', '..', 'x\\y'):
            with self.assertRaises(ValueError):
                safe_segment(name)

    def test_same_source_name_different_extensions_no_webp_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            out = d / 'out'
            out.mkdir()
            s1 = d / 'photo.jpg'
            s2 = d / 'photo.png'
            s1.write_bytes(b'same byte content')
            s2.write_bytes(b'same byte content')
            p1, _ = import_one(s1, out)
            p2, _ = import_one(s2, out)
            self.assertNotEqual(p1.with_suffix('.webp'), p2.with_suffix('.webp'))


class BuildTests(unittest.TestCase):
    def test_duplicate_webp_output_aborts_before_rewriting_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / 'blog' / 'images'
            folder.mkdir(parents=True)
            a = folder / 'same.jpg'
            b = folder / 'same.png'
            a.write_bytes(b'JPG stay untouched')
            b.write_bytes(b'PNG stay untouched')
            with self.assertRaisesRegex(ValueError, 'WebP 文件名冲突'):
                scan(root, 'blog')
            self.assertEqual(a.read_bytes(), b'JPG stay untouched')
            self.assertEqual(b.read_bytes(), b'PNG stay untouched')

    def test_inline_extraction_preserves_existing_hash_prefix(self):
        import base64
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / 'images' / 'inline'
            out.mkdir(parents=True)
            raw = b'\xff\xd8\xff' + b'X' * 2096
            digest = hashlib.sha256(raw).hexdigest()
            old = out / f'{digest[:12]}.jpg'
            old.write_bytes(b'PREEXISTING DIFFERENT')
            article = root / 'article.html'
            article.write_text('<img src="data:image/jpeg;base64,' + base64.b64encode(raw).decode() + '">')
            added, removed = process_file(article, out, root)
            self.assertEqual(added, 1)
            self.assertGreater(removed, 2000)
            self.assertEqual(old.read_bytes(), b'PREEXISTING DIFFERENT')
            self.assertTrue((out / f'{digest[:16]}.jpg').exists())
            self.assertIn(f'{digest[:16]}.jpg', article.read_text())


class GitGuardTests(unittest.TestCase):
    def run_git(self, *args, cwd):
        return subprocess.run(['git', *args], cwd=cwd, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.strip()

    def test_same_path_replace_fails_new_image_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.run_git('init', '-q', cwd=folder)
            self.run_git('config', 'user.email', 'nobody@example.org', cwd=folder)
            self.run_git('config', 'user.name', 'Test', cwd=folder)
            assets = folder / 'blog' / 'images'
            assets.mkdir(parents=True)
            old = assets / 'pic.jpg'
            old.write_bytes(b'old')
            self.run_git('add', '.', cwd=folder)
            self.run_git('commit', '-qm', 'initial', cwd=folder)
            base = self.run_git('rev-parse', 'HEAD', cwd=folder)
            new = assets / 'pic-unique-abcdef123456.jpg'
            new.write_bytes(b'new')
            self.run_git('add', '.', cwd=folder)
            self.run_git('commit', '-qm', 'new asset', cwd=folder)
            here = Path.cwd()
            try:
                os.chdir(folder)
                self.assertEqual(changes(base), [])
                old.write_bytes(b'overwritten!')
                self.run_git('add', '.', cwd=folder)
                self.run_git('commit', '-qm', 'bad overwrite', cwd=folder)
                self.assertEqual(changes(base), ['blog/images/pic.jpg'])
            finally:
                os.chdir(here)


if __name__ == '__main__':
    unittest.main()
