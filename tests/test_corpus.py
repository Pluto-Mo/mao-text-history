import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import corpus
from bs4 import BeautifulSoup

class CorpusTests(unittest.TestCase):
    def test_hash_is_stable(self):
        self.assertEqual(corpus.sha(b'x'),corpus.sha(b'x'))
        self.assertNotEqual(corpus.sha(b'x'),corpus.sha(b'y'))
    def test_domain_allowlist(self):
        self.assertTrue(corpus.safe_url('https://www.marxists.org/chinese/maozedong/index.htm'))
        for u in ['http://www.marxists.org/a','https://evil.test/a','https://127.0.0.1/a','https://www.marxists.org@evil.test/a','https://www.marxists.org:8080/a']:
            self.assertFalse(corpus.safe_url(u))
    def test_normalization_preserves_meaning(self):
        self.assertNotEqual(corpus.norm_title('人民内部矛盾'),corpus.norm_title('敌我矛盾'))
        self.assertEqual(corpus.norm_title('《论十大关系》'),corpus.norm_title('论十大关系'))
    def test_date_suffix_only(self):
        self.assertEqual(corpus.norm_title('论十大关系（一九五六年四月二十五日）'),corpus.norm_title('论十大关系'))
        self.assertNotEqual(corpus.norm_title('讲话（一）'),corpus.norm_title('讲话（二）'))
    def test_catalogue_links_keep_provenance(self):
        html='<h4>第五卷</h4><a href="text.htm">关于正确处理人民内部矛盾的问题</a><a href="#f">其它</a>'
        src={'id':'S','url':'https://www.marxists.org/chinese/maozedong/index.htm','kind':'mia_main','edition_id':'web'}
        data=corpus.catalogue(BeautifulSoup(html,'html.parser'),src,{'raw_sha256':'a'*64})
        self.assertEqual(len(data),1)
        self.assertEqual(data[0]['volume'],5)
        self.assertEqual(data[0]['source_raw_sha256'],'a'*64)
        self.assertEqual(data[0]['body_status'],'not_fetched')
    def test_pdf_links_are_not_fulltext(self):
        html='<h4>第五卷</h4><a href="test.pdf">第五卷</a>'
        src={'id':'S','url':'https://www.marxists.org/chinese/maozedong/index.htm','kind':'mia_main','edition_id':'web'}
        data=corpus.catalogue(BeautifulSoup(html,'html.parser'),src,{})
        self.assertEqual(data[0]['kind'],'pdf_link')
        self.assertEqual(data[0]['body_status'],'not_fetched')
    def test_unlinked_toc_does_not_invent_page(self):
        html='<p>《毛泽东集》</p><p>第二卷 井冈山期</p><table><tr><td>页<br>9<br>11</td><td>篇　目<br>甲乙丙丁戊己文稿<br>另一条没有链接</td></tr></table>'
        src={'id':'S','url':'https://www.marxists.org/chinese/maozedong/collect/index.htm','kind':'mia_collect','edition_id':'mia-ji-10'}
        data=corpus.catalogue(BeautifulSoup(html,'html.parser'),src,{})
        self.assertEqual(len(data),2)
        self.assertTrue(all(r['url'] is None and r['printed_page'] is None for r in data))
    def test_title_relations_not_historical(self):
        data=[{'id':'a','source_id':'S1','normalized_title':'关于正确处理人民内部矛盾的问题'}, {'id':'b','source_id':'S2','normalized_title':'关于正确处理人民内部矛盾的问题'}]
        rel=corpus.relations(data)
        self.assertEqual(len(rel),1)
        self.assertFalse(rel[0]['is_historical_revision_edge'])
    def test_same_source_does_not_create_cross_source_mapping(self):
        self.assertEqual(corpus.relations([{'id':'a','source_id':'S','normalized_title':'关于正确处理人民内部矛盾的问题'},{'id':'b','source_id':'S','normalized_title':'关于正确处理人民内部矛盾的问题'}]),[])
    def test_expected_volume_sets(self):
        editions={e['id']:e for e in corpus.load('config/editions.json')}
        self.assertEqual(editions['wengao-old-13']['expected_volumes'],13)
        self.assertEqual(editions['wengao-2023-20']['expected_volumes'],20)
        self.assertEqual(editions['nianpu-2023-9']['expected_volumes'],9)
    def test_expected_volumes_are_missing_until_observed(self):
        self.assertTrue(all(not v['full_volume_acquired'] for v in corpus.build_volumes()))
    def test_v5_is_not_numbered_v1(self):
        v=[v for v in corpus.build_volumes() if v['edition_id']=='maoxuan-1977-v5']
        self.assertEqual(v[0]['volume'],5)
    def test_nianpu_route(self):
        v=[v for v in corpus.build_volumes() if v['edition_id']=='nianpu-2023-9' and v['volume']==6]
        self.assertEqual(v[0]['date_range'],['1956-10','1959-03'])
    def test_unknown_source_import_rejected(self):
        with self.assertRaises(ValueError): corpus.ingest('/does-not-exist','UNKNOWN','x','note',None)
    def test_data_integrity(self):
        self.assertEqual(corpus.validate(),0)
    def test_local_import_preserves_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'config').mkdir()
            (root/'config/sources.json').write_text('[{"id":"S"}]')
            (root/'config/editions.json').write_text('[{"id":"E"}]')
            src=root/'owned.txt';src.write_text('第一段\n\n第二段',encoding='utf-8')
            with patch.object(corpus,'ROOT',root):
                key=corpus.ingest(str(src),'S','E','用户合法提供',None)
                record=json.loads((root/'local'/key/'record.json').read_text())
                self.assertEqual(record['raw_sha256'],corpus.sha(src.read_bytes()))
                self.assertFalse(record['published'])
                self.assertIsNone(record['printed_page'])

if __name__=='__main__': unittest.main()
