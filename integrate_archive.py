#!/usr/bin/env python3
"""Reconcile actually retained sources; do not replace old reports with invented totals.
Internal PDF bookmarks supplement (but never overwrite) the original web catalogue.
"""
from collections import Counter
import json
from pathlib import Path
import re
import fitz
import archive_corpus as a
import corpus as c
import research as r


def book_entries(records):
    out=[]
    for record in records:
        if record['status']!='preserved': continue
        editions=r.extra_editions(record)
        for i,(level,title,page) in enumerate(record.get('pdf_bookmarks',[])):
            if page<=0 or page>record.get('pdf_pages',0) or not title.strip(): continue
            ref=next((x for x in editions if x.get('volume') is not None),editions[0] if editions else {})
            out.append({'id':'B-'+a.digest((record['raw_sha256']+'|'+str(i)+'|'+title+'|'+str(page)).encode())[:20],
                        'title':title,'normalized_title':c.norm_title(title),'kind':'pdf_bookmark',
                        'source_id':record.get('source_ids',['UNKNOWN'])[0],'source_url':record['url'],'url':record['url'],
                        'source_raw_sha256':record['raw_sha256'],'edition_id':ref.get('edition_id'),
                        'volume':ref.get('volume'),'pdf_page':page,'bookmark_level':level,
                        'locator':f'PDF bookmark[{i+1}] -> PDF page {page}',
                        'witness_id':record['id'],'identity_status':'source_bookmark_label_not_manually_verified_work_identity'})
    a.lines('archive/index/book-catalogue.jsonl',out)
    return out


def edition_evidence(records):
    results=[]; preview=fitz.open(); preview_map=[]
    sample_editions={'wengao-old-13':6,'wengao-2023-20':1,'nianpu-2023-9':1}
    for record in records:
        if record['status']!='preserved' or record.get('media')!='pdf': continue
        text=(a.ROOT/record['text_path']).read_text(encoding='utf-8') if record.get('text_path') else ''
        page_map=a.rows(record['page_map_path']) if record.get('page_map_path') else []
        page_count=record.get('pdf_pages',0)
        candidates=[]
        for p in page_map:
            if p['pdf_page']>12 and p['pdf_page']<page_count-8: continue
            raw=text[p['char_start']:p['char_end']]
            flat=re.sub(r'\s+','',raw)
            if any(x in flat for x in ['ISBN','书在版编目','版权','出版说明','2023年','1993年','1991年','1977年']):
                candidates.append({'pdf_page':p['pdf_page'],'whitespace_normalized_text':flat[:2500],
                                   'locator_note':'normalization only for finding imprint text; inspect original page before edition authentication'})
        results.append({'id':record['id'],'title':record['title'],'edition_refs':r.extra_editions(record),
                        'source_url':record['url'],'raw_sha256':record['raw_sha256'],
                        'internal_publication_candidates':candidates,'manually_authenticated':False})
        sample=any(sample_editions.get(e.get('edition_id'))==e.get('volume') for e in r.extra_editions(record))
        if sample:
            doc=fitz.open(stream=a.raw_bytes(record),filetype='pdf')
            chosen=[0,1]+[x['pdf_page']-1 for x in candidates[:2]]
            for page in dict.fromkeys(chosen):
                if 0<=page<len(doc):
                    preview.insert_pdf(doc,from_page=page,to_page=page)
                    preview_map.append({'preview_page':len(preview),'witness_id':record['id'],'title':record['title'],
                                        'source_pdf_page':page+1,'source_url':record['url'],'raw_sha256':record['raw_sha256']})
            doc.close()
    a.write('reports/edition-evidence.json',results)
    if len(preview):
        preview.save(a.ROOT/'reports/edition-preview.pdf',garbage=3,deflate=True)
        a.write('reports/edition-preview-map.json',preview_map)
    preview.close()


def completion(records,index_report):
    editions=a.load('reports/edition-coverage.json')
    entries=a.rows('catalog/entries.jsonl')
    ok={x['url']:x for x in records if x['status']=='preserved'}
    mia_urls={x['url'] for x in entries if x.get('url') and x.get('source_id','').startswith('MIA-')}
    mia_missing=sorted(mia_urls-set(ok))
    core=[e for e in editions if e['edition_id']!='wenji-1999']
    book_missing=[{'edition_id':e['edition_id'],'volume':v['volume']} for e in core for v in e['volumes'] if v['status']=='not_complete']
    good=[x for x in records if x['status']=='preserved']
    report={'generated_at':a.now(),'authorization_ref':a.GRANT,
            'copy_scope':'four named collections; editions registered before this acquisition; MIA three catalogue scopes',
            'registered_MIA_URLs':len(mia_urls),'registered_MIA_URLs_preserved':len(mia_urls)-len(mia_missing),
            'missing_registered_MIA_URLs':mia_missing,'missing_core_edition_volumes':book_missing,
            'registered_copy_scope_complete':not mia_missing and not book_missing,
            'not_claimed':['all historical manuscript revisions reconstructed','all OCR layers perfectly transcribed',
                           'all original paper books independently authenticated','a public-domain or third-party reuse license'],
            'retained_source_witnesses':len(good),'media_counts':dict(Counter(x.get('media') for x in good)),
            'source_PDF_files':sum(x.get('media')=='pdf' for x in good),
            'source_PDF_pages':sum(x.get('pdf_pages',0) for x in good),
            'source_PDF_pages_with_native_text':sum(x.get('pdf_pages_with_text',0) for x in good),
            'original_raw_bytes':sum(x.get('raw_bytes',0) for x in good),
            'retained_extracted_characters':sum(x.get('text_chars',0) for x in good),
            'official_page_images':sum(x.get('preserved_pages',0) for x in good if x.get('media')=='official_page_images'),
            'bookmarks_and_web_catalogue_entries':index_report['catalogue_entries'],
            'page_level_title_occurrences':index_report['title_page_occurrences'],
            'web_catalogue_baseline_entries':len(entries),'historical_revision_edges_verified':0,
            'edition_summaries':[{k:v for k,v in e.items() if k!='volumes'} for e in editions],
            'failed_noncore_source_fetches':[{'id':x['id'],'url':x['url'],'error':x.get('error')} for x in records if x['status']!='preserved']}
    a.write('reports/completion.json',report)
    md=['# 全文复制与对应映射：最终验收','',f"生成时间：{report['generated_at']}",'',
        '## 实际交付','',
        f"已保存 **{len(good):,} 个来源见证文件**，其中源 PDF **{report['source_PDF_files']} 份、{report['source_PDF_pages']:,} 页**；另保存官方阅读器原始文字数组及逐页图片。",'',
        f"MIA 三个已登记目录的 **{report['registered_MIA_URLs_preserved']}/{report['registered_MIA_URLs']} 个文件 URL** 已保存。",'',
        '## 逐套逐卷','',
        '| 版本 | 应有卷数 | 整份数字文件／完整阅读器 | 数字文件或全部登记网页已覆盖 |','|---|---:|---:|---:|']
    for e in editions:
        md.append(f"| [{e['title']}](../archive/editions/{e['edition_id']}.md) | {e['expected_volumes']} | {e['volumes_with_source_files']} | {e['volumes_covered_by_files_or_registered_web_texts']} |")
    md+=['','“整份数字文件”指来源文件已完整保存并验证字节；不代表原书无缺页、文字层无识别错误，或全部历史原稿已取得。',
         '第五卷的网页转录与实体版扫描件分开计数；新版文稿20册与旧版13册、年谱新旧版本不互相替代。','',
         '## 映射已经落地到哪里','',
         f"- 原网页目录：{len(entries):,} 条；补入 PDF 内部目录后：{index_report['catalogue_entries']:,} 条。",
         f"- 源 PDF 书签：{index_report['source_PDF_bookmarks']:,} 条；标题在具体页／文本行中的出现记录：{index_report['title_page_occurrences']:,} 条。",
         '- 作品入口 → 原网站目录定位 → 已存网页正文／整卷文件 → PDF页或阅读器页 → 字节校验值。',
         '- 标题出现、同题和同卷关系仍是查阅线索，不自动成为确认的改稿因果链。','',
         '## 使用','',
         '```bash','python research.py search 关于正确处理人民内部矛盾的问题 --limit 20',
         'python research.py versions 关于正确处理人民内部矛盾的问题',
         'python research.py read <见证本ID> --page <PDF页或阅读器页>',
         'python archive_corpus.py restore <见证本ID> /一个尚不存在的输出路径.pdf','```','',
         '扫描件已有文字层时保留其文字层；原文件、原文字层和检索时的空白归一化严格区分。不要把来源已有OCR错误解释成作者修订。',
         '早期 reports/coverage.json、fulltext-coverage.json 和 docs/missing-materials.md 是历史阶段记录；最新状态以本报告与 completion.json 为准。','',
         '## 尚未取得的登记目标','']
    if mia_missing or book_missing:
        md += [json.dumps({'MIA_missing':mia_missing,'core_edition_missing':book_missing},ensure_ascii=False,indent=2)]
    else: md += ['本轮登记的四类复制范围内，没有剩余未保存的 MIA 文件 URL 或未覆盖的核心卷册。']
    if report['failed_noncore_source_fetches']:
        md += ['','辅助来源访问失败（不伪装成已取得）：',json.dumps(report['failed_noncore_source_fetches'],ensure_ascii=False,indent=2)]
    a.textfile('reports/completion.md','\n'.join(md)+'\n')
    return report


def documentation():
    path=a.ROOT/'README.md'
    text=path.read_text(encoding='utf-8')
    marker='## 全文库：本轮实际交付'
    if marker not in text:
        heading='# 毛泽东文本演变研究库'
        insert='\n\n'+marker+'\n\n[最终验收与逐卷入口](reports/completion.md) · [全文和原文件](archive/README.md) · [《正处》全文查阅包](exports/zhengchu-fulltext-guide.md)。\n\n'
        insert+='源文件、网页全文、整卷PDF及页面定位已实际保存；查看最新验收报告，不再把早期目录数量当作全文数量。复制依据[仓库操作者的授权声明](authorization/user-declared-fulltext.json)。\n'
        text=text.replace(heading,heading+insert,1)
    text=text.replace('**尚未取得四套原书的全部全文，也未重建全部中间稿。**','**全文复制状态以最新 reports/completion.json 为准；全部中间稿的历史校勘不因文件入库而自动完成。**')
    text=text.replace('本公开仓库发布来源书目、卷册清单、目录索引、采集收据、候选映射和原创研究卡。','本公开仓库保存原文件、全文、页面索引、来源书目、采集收据、候选映射和原创研究卡。')
    text=text.replace('正文缓存不在本公共仓库。','首轮缓存没有保留；本轮长期保存的原文件与正文位于 archive/。')
    text=text.replace('原始HTML缓存不随Git或Actions附件发布。','旧工作流不发布其临时缓存；本轮授权全文采集在 archive/objects 保存可还原的原始字节。')
    path.write_text(text,encoding='utf-8')
    path=a.ROOT/'AGENTS.md'; text=path.read_text(encoding='utf-8')
    if '## 本轮全文入口' not in text:
        text=text.replace('# Agent 研究规则','# Agent 研究规则\n\n## 本轮全文入口\n\n先读 reports/completion.json、reports/research-index.json 和 exports/zhengchu-fulltext-guide.md。archive/ 保存真实原文件及全文，不要再说仓库只有八篇正文。\n\nresearch.py 支持跨空白的中文检索、按PDF页／阅读器页或网页行读取；按需加载 archive/segments/ 下小文件，不要把整套书装入上下文。\n\narchive/index/book-catalogue.jsonl 是源PDF书签目录；title-occurrences.jsonl 是具体页中的标题出现，不是认证过的历史修改。引用必须带见证本ID、URL、版本说明、PDF页／阅读器页和原文件SHA256；纸本页码未知时不要推造。\n\n来源PDF的已有OCR文字层可能有误；关键字词增删要与原页面复核。归一化的检索摘要不是逐字引文。版权依据是用户声明，不是助手对整套材料公版状态的认证。\n',1)
    text=text.replace('原始字节仅在运行器临时 .cache 内，不在公共仓库。','早期记录的临时字节未保留；本轮原始字节和全文已经保存在 archive/objects、archive/text 和 archive/segments。')
    text=text.replace('不得声称本仓库已拥有四套全文。','是否已覆盖某一套、版次或卷册，应以最新 completion.json 和 archive/editions 的实际记录为准。')
    path.write_text(text,encoding='utf-8')
    path=a.ROOT/'docs/missing-materials.md'
    if path.exists():
        text=path.read_text(encoding='utf-8')
        banner='> 本文保留为早期基线，最新全文入库与逐卷关闭状态见 [最终验收报告](../reports/completion.md)。不要将本文的“0全文”基线作为当前状态。\n\n'
        if banner not in text: path.write_text(banner+text,encoding='utf-8')


def main():
    records=r.all_records()
    a.build_index()
    extra=book_entries(records)
    original_rows=a.rows
    baseline=original_rows('catalog/entries.jsonl')
    # Inject an augmented read-only catalogue for this full rebuild; the original
    # web catalogue is never modified or inflated with synthetic network entries.
    def augmented(path):
        return baseline+extra if path=='catalog/entries.jsonl' else original_rows(path)
    a.rows=augmented
    try: index_report=r.build()
    finally: a.rows=original_rows
    locations=original_rows('archive/index/locations.jsonl')
    index_report['retained_segments']=len(locations)
    index_report['searchable_segments']=sum(x['text_chars']>0 for x in locations)
    index_report['web_catalogue_entries']=len(baseline)
    index_report['source_PDF_bookmark_entries']=len(extra)
    a.write('reports/research-index.json',index_report)
    edition_evidence(records)
    result=completion(records,index_report)
    documentation()
    a.verify()
    print(json.dumps({k:v for k,v in result.items() if k not in ['edition_summaries','failed_noncore_source_fetches']},ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__': main()
