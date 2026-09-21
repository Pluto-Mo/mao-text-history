from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import fulltexts as f

class FulltextTests(unittest.TestCase):
    def spec(self, **extra):
        return dict(id='test-doc', approval='reviewed_official_document_body',
                    url='https://www.marxists.org/chinese/test.htm', rights_references=['test-fixture-only'],
                    completeness='available_web_body', title='测试文书', agency='测试机关',
                    historical_date='1950-01-01', work_id='test-work', start='正文开始', end='正文结束',
                    min_chars=8, max_chars=500, **extra)

    def test_preserve_body_exclude_notes(self):
        raw='<title>测试</title><p>后出说明</p><div>正文开始<br>甲乙丙丁。<br>正文结束</div><p>现代注释</p>'.encode()
        body, _=f.extract_body(raw,self.spec())
        self.assertEqual(body,'正文开始\n甲乙丙丁。\n正文结束\n')
        self.assertNotIn('后出说明', body)
        self.assertNotIn('现代注释', body)

    def test_gb18030_does_not_become_latin1(self):
        raw='<meta charset="gb2312"><p>正文开始，甲乙丙丁，正文结束</p>'.encode('gb18030')
        body, meta=f.extract_body(raw,self.spec(),'iso-8859-1')
        self.assertIn('甲乙丙丁', body)
        self.assertEqual(meta['encoding'],'gb18030')

    def test_utf8_first(self):
        text, enc=f.decode_html('正文开始𠀀正文结束'.encode())
        self.assertEqual(text,'正文开始𠀀正文结束')
        self.assertEqual(enc,'utf-8-sig')

    def test_preserve_suspected_typo(self):
        body,_=f.extract_body('<p>正文开始，一九四九年十日一日，正文结束</p>'.encode(),self.spec())
        self.assertIn('十日一日',body)
        self.assertNotIn('十月一日',body)

    def test_remove_only_boundary_whitespace(self):
        body,_=f.extract_body('<p>正文 <b>开始</b><br>甲  乙<br>正文结束</p>'.encode(),self.spec())
        self.assertEqual(f.compact(body),'正文开始甲乙正文结束')

    def test_missing_end_refused(self):
        with self.assertRaises(ValueError):
            f.extract_body('<p>正文开始甲乙丙丁</p>'.encode(),self.spec())

    def test_duplicate_start_refused(self):
        with self.assertRaises(ValueError):
            f.extract_body('<p>正文开始正文开始甲乙正文结束</p>'.encode(),self.spec())

    def test_duplicate_end_after_start_refused(self):
        with self.assertRaises(ValueError):
            f.extract_body('<p>正文开始甲乙正文结束正文结束</p>'.encode(),self.spec())

    def test_end_in_header_not_selected(self):
        body,_=f.extract_body('<h1>正文结束</h1><p>正文开始甲乙正文结束</p>'.encode(),self.spec())
        self.assertEqual(body,'正文开始甲乙正文结束\n')

    def test_script_is_not_executed_or_copied(self):
        body,_=f.extract_body('<p>正文开始<script>alert(1)</script>甲乙丙丁正文结束</p>'.encode(),self.spec())
        self.assertNotIn('alert',body)

    def test_excluded_marker_inside_refused(self):
        with self.assertRaises(ValueError):
            f.extract_body('<p>正文开始版权模板正文结束</p>'.encode(),self.spec(excluded_markers=['版权模板']))

    def test_unreviewed_refused(self):
        s=self.spec(); s['approval']='unknown'
        with self.assertRaises(ValueError): f.check_spec(s)

    def test_unsafe_id_refused(self):
        s=self.spec(); s['id']='../../oops'
        with self.assertRaises(ValueError): f.check_spec(s)

    def test_network_scope(self):
        for url in ('http://www.marxists.org/a','https://example.com/a','https://user@www.marxists.org/a','https://127.0.0.1/a','https://www.marxists.org:444/a'):
            self.assertFalse(f.safe_url(url),url)
        self.assertTrue(f.safe_url('https://zh.wikisource.org/wiki/test?oldid=1'))

    def test_source_replacement_not_silently_accepted(self):
        with self.assertRaises(ValueError): f.decode_html('正文\ufffd开始'.encode())

    def test_policy_keeps_excerpt_status(self):
        policy=f.read_json(f.POLICY)
        for s in policy['documents']: f.check_spec(s)
        excerpt=[s for s in policy['documents'] if s['id']=='mia-1950-1008'][0]
        self.assertEqual(excerpt['completeness'],'source_explicit_excerpt')
        self.assertEqual(len(policy['pending_collections']),4)

    def test_missing_requested_witness_does_not_make_fake_text(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(f,'ROOT',Path(tmp)), patch('sys.argv',['fulltexts.py','read','missing-doc']):
            self.assertEqual(f.main(),2)

if __name__=='__main__': unittest.main()
