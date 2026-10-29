import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class SearchIndexSmoke(unittest.TestCase):
    def test_manifest_and_fulltext_have_identical_sha_set(self):
        idx=json.loads((ROOT/'blog/index.json').read_text())
        search=json.loads((ROOT/'blog/search-index.json').read_text())
        actual={x['name']:x['sha'] for x in idx['files']}
        texts={x['name']:x['sha'] for x in search['files']}
        self.assertEqual(actual,texts)
        self.assertEqual(len(idx['files']),3)
    def test_html_no_bulk_base64(self):
        for html in (ROOT/'blog').glob('*.html'):
            s=html.read_text(encoding='utf8')
            self.assertNotIn('data:image/jpeg;base64,',s)
        self.assertGreaterEqual(len(list((ROOT/'blog/images/inline').glob('*.jpg'))),12)
    def test_webp_and_intrinsic_sizes_exist(self):
        imgs=list((ROOT/'blog/images').rglob('*.jpg'))
        self.assertEqual(len([x for x in imgs if not x.with_suffix('.webp').exists()]),0)
        sizes=json.loads((ROOT/'blog/image-sizes.json').read_text())
        self.assertIn('articles',sizes)

if __name__=='__main__':unittest.main()
