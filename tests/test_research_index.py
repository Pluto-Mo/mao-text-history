import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import archive_corpus as a
import research as r
import integrate_archive as i
from official_books import data_array, script_value


class ResearchIndexTests(unittest.TestCase):
    def test_overlapping_titles_and_failure_links(self):
        m=r.Matcher(['正确处理','处理','矛盾'])
        hits=list(m.find('正确处理矛盾'))
        self.assertIn(('正确处理',0),hits)
        self.assertIn(('处理',2),hits)
        self.assertIn(('矛盾',4),hits)

    def test_search_normalization_does_not_simplify_characters(self):
        self.assertEqual('正确处理',r.normal('正\n确　处理。'))
        self.assertNotEqual(r.normal('處理'),r.normal('处理'))
        self.assertEqual('AB12',r.normal('ＡＢ１２'))

    def test_search_array_is_data_not_executed_code(self):
        self.assertEqual(['甲','乙'],data_array('var textForPages = ["甲","乙"]; evil();','textForPages'))
        with self.assertRaises(ValueError): data_array('textForPages = [evil()]','textForPages')
        self.assertIsNone(data_array('other = []','textForPages'))

    def test_configuration_uses_last_literal_assignment(self):
        self.assertEqual(359,script_value('bookConfig.totalPageCount=0;bookConfig.totalPageCount=359;','totalPageCount'))
        self.assertEqual('../files/mobile/',script_value('bookConfig.normalPath="../files/mobile/";','normalPath'))

    def test_pdf_segment_respects_original_page_boundaries(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            raw='\n\n=== PDF PAGE 1 ===\n甲\n\n\n=== PDF PAGE 2 ===\n乙\n'
            split=raw.index('\n\n=== PDF PAGE 2')
            (root/'text.txt').write_text(raw,encoding='utf-8')
            (root/'pages.jsonl').write_text('\n'.join(json.dumps(x) for x in [
                {'pdf_page':1,'char_start':0,'char_end':split},
                {'pdf_page':2,'char_start':split,'char_end':len(raw)}]),encoding='utf-8')
            with patch.object(a,'ROOT',root):
                values=list(r.pages({'text_path':'text.txt','page_map_path':'pages.jsonl'}))
            self.assertEqual([1,2],[x['number'] for x in values])
            self.assertIn('甲',values[0]['text'])
            self.assertNotIn('乙',values[0]['text'])
            self.assertIsNone(values[0]['printed_page'])

    def test_web_lines_remain_exact(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); text=''.join(f'行{x}\n' for x in range(1,64))
            (root/'t.txt').write_text(text,encoding='utf-8')
            with patch.object(a,'ROOT',root): values=list(r.pages({'text_path':'t.txt'}))
            self.assertEqual(2,len(values))
            self.assertEqual(text,''.join(x['text'] for x in values))
            self.assertEqual(61,values[1]['number'])

    def test_wuhan_pdf_range_mapping_does_not_change_original_record(self):
        record={'media':'pdf','title':'毛泽东思想万岁（1949—1957）','edition_refs':[{'edition_id':'mia-other','volume':None}]}
        refs=r.extra_editions(record)
        self.assertTrue(any(x['edition_id']=='mia-1968' and x['volume']==3 for x in refs))
        self.assertEqual(1,len(record['edition_refs']))

    def test_internal_bookmark_is_traceable_not_a_claim_of_authenticity(self):
        record={'id':'A-x','status':'preserved','raw_sha256':'abc','url':'https://example.test/book.pdf',
                'source_ids':['S-x'],'pdf_pages':10,'pdf_bookmarks':[[1,'某一篇文章',3]],
                'edition_refs':[{'edition_id':'E-x','volume':1}]}
        with patch.object(a,'lines') as save:
            values=i.book_entries([record])
        self.assertEqual(3,values[0]['pdf_page'])
        self.assertIn('not_manually_verified',values[0]['identity_status'])
        self.assertEqual('abc',values[0]['source_raw_sha256'])
        save.assert_called_once()


if __name__=='__main__': unittest.main()
