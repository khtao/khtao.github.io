"""Unit tests for build-time HTML image staging and subsequent edits."""
import unittest, tempfile
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_html_lazy import prepare

class HTMLStageTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=Path(self.tmp.name)/'article.html'
 def tearDown(self):self.tmp.cleanup()
 def test_stage_offscreen_and_preserve_markup(self):
  self.p.write_text('<!doctype html><html><body><h1>原始内容</h1><img src="a.jpg"><img src="b.jpg" alt="b"><img src="c.jpg"><img src="d.jpg"><p>END</p></body></html>')
  self.assertEqual(prepare(self.p,{'c.jpg':[500,320],'d.jpg':[200,100]}),2)
  s=self.p.read_text()
  self.assertEqual(s.count('data-khtao-src='),2)
  self.assertEqual(s.count('data-khtao-lazy-bootstrap'),1)
  self.assertEqual(s.count('fetchpriority="high"'),1)
  self.assertIn('width="500" height="320"',s)
  self.assertIn('<h1>原始内容</h1>',s)
  self.assertEqual(prepare(self.p,{}),0)
  self.assertEqual(self.p.read_text(),s)
 def test_incremental_new_image(self):
  self.p.write_text('<html><body><img src="a.jpg"><img src="b.jpg"><img src="c.jpg"></body></html>')
  self.assertEqual(prepare(self.p,{}),1)
  s=self.p.read_text().replace('</body>','<img data-src="thumbnail.jpg" src="e.jpg"></body>')
  self.p.write_text(s)
  self.assertEqual(prepare(self.p,{}),1)
  t=self.p.read_text()
  self.assertEqual(t.count('data-khtao-lazy-bootstrap'),1)
  self.assertEqual(t.count('data-khtao-src='),2)
  self.assertIn('data-src="thumbnail.jpg"',t)
  self.assertEqual(prepare(self.p,{}),0)
 def test_skip_remote_and_empty(self):
  self.p.write_text('<html><body><img src="https://example.org/1.jpg"><img src="data:image/png;base64,AA"><img><img src="local.jpg"></body></html>')
  self.assertEqual(prepare(self.p,{}),0)
  self.assertNotIn('data-khtao-lazy-bootstrap',self.p.read_text())

if __name__=='__main__':unittest.main()
