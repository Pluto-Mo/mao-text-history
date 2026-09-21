import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import archive_corpus as a


class ArchiveTests(unittest.TestCase):
    def test_allowlist_rejects_credentials_and_other_hosts(self):
        self.assertTrue(a.safe('https://www.marxists.org/chinese/maozedong/index.htm'))
        for url in ['file:///etc/passwd','https://evil.test/x','https://user:pass@www.marxists.org/x','http://127.0.0.1/x']:
            self.assertFalse(a.safe(url))

    def test_legacy_chinese_is_not_latin1(self):
        text,_,enc=a.visible('<meta charset="gb2312"><h1>矛盾问题</h1><p>正文全文。</p>'.encode('gb18030'))
        self.assertIn('正文全文。',text)
        self.assertNotIn('\ufffd',text)

    def test_all_visible_text_retained_and_scripts_removed(self):
        raw='<html><body>导航<h1>题名</h1><p>原文甲。</p><div>编者注乙。</div><script>secret()</script></body></html>'.encode()
        text,_,_=a.visible(raw)
        for needle in ['导航','题名','原文甲。','编者注乙。']:
            self.assertIn(needle,text)
        self.assertNotIn('secret',text)

    def test_access_challenge_not_fulltext(self):
        with self.assertRaises(ValueError): a.visible(b'<h1>Access denied</h1>')

    def test_gzip_roundtrip_preserves_exact_source_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch.object(a,'ROOT',root),patch.object(a,'BASE',root/'archive'):
                raw=b'\xff\x00 original HTML \r\n'
                r=a.preserved(raw,'html')
                self.assertEqual(raw,a.raw_bytes(r))
                self.assertEqual(a.digest(raw),r['raw_sha256'])
                first=(root/r['raw_paths'][0]).read_bytes()
                a.preserved(raw,'html')
                self.assertEqual(first,(root/r['raw_paths'][0]).read_bytes())

    def test_large_file_chunk_order_is_lossless(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch.object(a,'ROOT',root),patch.object(a,'BASE',root/'archive'),patch.object(a,'CHUNK',5):
                raw=b'0123456789abcdefghijk'
                r=a.preserved(raw,'pdf')
                self.assertEqual('ordered_chunks',r['storage'])
                self.assertEqual(raw,a.raw_bytes(r))
                self.assertEqual(5,len(r['parts']))

    def test_document_line_numbers_and_text_hash(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch.object(a,'ROOT',root),patch.object(a,'BASE',root/'archive'):
                r={'id':'A-test','title':'测试文献','url':'https://www.marxists.org/x'}
                a.render_document(r,'第一行\n第二行\n')
                self.assertEqual(2,r['text_lines'])
                self.assertEqual(a.digest('第一行\n第二行\n'.encode()),r['text_sha256'])
                self.assertIn('id="L2"',(root/r['document_path']).read_text())

    def test_wengao_pdf_catalogue_assigned_to_13_volume_edition(self):
        entry={'id':'I-test','url':'https://www.marxists.org/chinese/pdf/chinese_marxists/mao/c06.pdf',
               'title':'建国以来毛泽东文稿(6)','source_id':'MIA-MAIN','edition_id':'mia-other','volume':None,'kind':'pdf_link'}
        with patch.object(a,'rows',return_value=[entry]),patch.object(a,'load',return_value=[]):
            target=list(a.targets().values())[0]
            self.assertEqual('wengao-old-13',target['edition_refs'][0]['edition_id'])
            self.assertEqual(6,target['edition_refs'][0]['volume'])


if __name__=='__main__': unittest.main()
