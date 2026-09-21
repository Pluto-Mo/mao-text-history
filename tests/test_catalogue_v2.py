import unittest
from bs4 import BeautifulSoup
import catalogue_v2 as v

class CatalogueV2Tests(unittest.TestCase):
    def test_legacy_chinese_not_latin1(self):
        text,encoding=v.decode_html('<title>毛泽东思想万岁</title>'.encode('gb18030'),'windows-1252')
        self.assertIn('毛泽东思想万岁',text)
        self.assertEqual(encoding,'gb18030')
    def test_utf8_first(self):
        text,encoding=v.decode_html('毛泽东年谱'.encode('utf-8'),'gb2312')
        self.assertEqual(text,'毛泽东年谱')
        self.assertEqual(encoding,'utf-8')
    def test_extended_gb(self):
        text='<meta charset="gb2312">㐀标题'
        self.assertEqual(v.decode_html(text.encode('gb18030'))[0],text)
    def test_column_alignment(self):
        soup=BeautifulSoup('<table><tr><td colspan="2">第一卷 初期</td><td colspan="2">第二卷 井冈山期</td></tr><tr><td>页</td><td id="left">篇目<br>甲</td><td>页</td><td id="right">篇目<br>乙</td></tr></table>','html5lib')
        self.assertEqual(v.column_volume(soup.find(id='left'))[0],1)
        self.assertEqual(v.column_volume(soup.find(id='right'))[0],2)
    def test_nested_text_does_not_split_title(self):
        soup=BeautifulSoup('<td>篇目<br>关于<b>正确处理</b>的问题<br>另一篇</td>','html.parser')
        self.assertEqual(v.line_texts(soup.td),['篇目','关于正确处理的问题','另一篇'])
    def test_navigation_does_not_change_work_edition(self):
        soup=BeautifulSoup('<a href="#other">其它</a><h4>第一卷</h4><a href="first.htm">中国社会各阶级的分析</a><h4>其它</h4><a href="other.htm">致美国记者的信</a>','html5lib')
        source={'id':'MIA-MAIN','url':'https://www.marxists.org/chinese/maozedong/index.htm','kind':'mia_main','edition_id':'maoxuan-mia-catalogue'}
        rows=v.catalogue(soup,source,{})
        self.assertEqual(rows[0]['edition_id'],'maoxuan-mia-catalogue')
        self.assertEqual(rows[0]['volume'],1)
        self.assertEqual(rows[1]['edition_id'],'mia-other')
        self.assertIsNone(rows[1]['volume'])
    def test_parallel_toc_assigns_correct_volumes(self):
        soup=BeautifulSoup('<table><tr><td colspan="4">《毛泽东集》</td></tr><tr><td colspan="2">第一卷 初期</td><td colspan="2">第二卷 井冈山期</td></tr><tr><td>页<br>1</td><td>篇目<br>第一卷的某一篇</td><td>页<br>2</td><td>篇目<br>第二卷的某一篇</td></tr></table>','html5lib')
        source={'id':'MIA-COLLECT','url':'https://www.marxists.org/chinese/maozedong/collect/index.htm','kind':'mia_collect','edition_id':'mia-ji-10'}
        rows=v.catalogue(soup,source,{})
        self.assertEqual([(r['title'],r['volume']) for r in rows],[('第一卷的某一篇',1),('第二卷的某一篇',2)])
    def test_date_ranges_are_volume_boundaries(self):
        soup=BeautifulSoup('<h3>一九一三年～一九四三年</h3><a href="a.htm">甲乙丙丁文</a><h3>一九四三年～一九四九年</h3><a href="b.htm">戊己庚辛文</a>','html5lib')
        source={'id':'MIA-1968','url':'https://www.marxists.org/chinese/maozedong/1968/index.htm','kind':'mia_1968','edition_id':'mia-1968'}
        self.assertEqual([r['volume'] for r in v.catalogue(soup,source,{})],[1,2])

    def test_volume_heading_with_period_subtitle(self):
        soup=BeautifulSoup('<h4>第二卷<br>抗日战争时期（上）</h4><a href="a.htm">论持久战</a><h4>第五卷<br>社会主义革命和社会主义建设时期（一）</h4><a href="b.htm">关于正确处理人民内部矛盾的问题</a>', 'html5lib')
        source={'id':'MIA-MAIN','url':'https://www.marxists.org/chinese/maozedong/index.htm','kind':'mia_main','edition_id':'maoxuan-mia-catalogue'}
        self.assertEqual([r['volume'] for r in v.catalogue(soup,source,{})],[2,5])

if __name__=='__main__': unittest.main()
