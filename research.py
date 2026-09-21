#!/usr/bin/env python3
"""Offline, provenance-first full-text research CLI; no LLM and no network.
Raw source text is immutable. Whitespace-normalized search is only a retrieval aid.
Title occurrences and PDF bookmarks are candidates, not authenticated revisions.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict, deque
import difflib
import json
from pathlib import Path
import re
import unicodedata
import archive_corpus as a
import corpus as c


def normal(text):
    return ''.join(x for x in unicodedata.normalize('NFKC',text) if x.isalnum())


class Matcher:
    """Aho-Corasick exact normalized multi-title matching, standard library only."""
    def __init__(self,words):
        self.next=[{}]; self.fail=[0]; self.out=[[]]
        for word in sorted(set(words)):
            state=0
            for char in word:
                if char not in self.next[state]:
                    self.next[state][char]=len(self.next)
                    self.next.append({}); self.fail.append(0); self.out.append([])
                state=self.next[state][char]
            self.out[state].append(word)
        queue=deque(self.next[0].values())
        while queue:
            state=queue.popleft()
            for char,child in self.next[state].items():
                queue.append(child); f=self.fail[state]
                while f and char not in self.next[f]: f=self.fail[f]
                self.fail[child]=self.next[f].get(char,0)
                self.out[child].extend(self.out[self.fail[child]])
    def find(self,text):
        state=0
        for i,char in enumerate(text):
            while state and char not in self.next[state]: state=self.fail[state]
            state=self.next[state].get(char,0)
            for word in self.out[state]: yield word,i-len(word)+1


def all_records():
    return [json.loads(p.read_text(encoding='utf-8')) for p in sorted((a.BASE/'records').glob('*.json'))]


def pages(record):
    if not record.get('text_path'): return
    text=(a.ROOT/record['text_path']).read_text(encoding='utf-8')
    if record.get('page_map_path'):
        for p in a.rows(record['page_map_path']):
            if 'pdf_page' in p:
                content=text[p['char_start']:p['char_end']]
                content=re.sub(r'^\s*=== PDF PAGE \d+ ===\n','',content,count=1)
                yield {'kind':'pdf_page','number':p['pdf_page'],'text':content,'printed_page':None}
            else:
                yield {'kind':'reader_page','number':p.get('reader_page') or p.get('array_index',0)+1,
                       'text':p.get('text',text[p['char_start']:p['char_end']]),'printed_page':None,
                       'reader_alignment_verified':record.get('reader_text_array_complete',False)}
    else:
        source_lines=text.splitlines(keepends=True)
        for start in range(0,len(source_lines),60):
            yield {'kind':'web_lines','number':start+1,'end_line':min(start+60,len(source_lines)),
                   'text':''.join(source_lines[start:start+60]),'printed_page':None}


def extra_editions(record):
    result=list(record.get('edition_refs',[]))
    if record.get('media')=='pdf' and '毛泽东思想万岁' in record['title']:
        dates=re.findall(r'\d{4}',record['title'])
        mapping={('1913','1943'):1,('1943','1949'):2,('1949','1957'):3,('1958','1960'):4,('1961','1968'):5}
        v=mapping.get(tuple(dates))
        if v: result.append({'edition_id':'mia-1968','volume':v,'basis':'five_date_ranges_linked_in_MIA_catalogue; print_identity_not_independently_authenticated'})
    for e in list(result):
        if e.get('edition_id')=='maoxuan-mia-catalogue' and e.get('volume')==5:
            result.append({'edition_id':'maoxuan-1977-v5','volume':5,'basis':'MIA_selected_works_volume_5_web_section'})
    return result


def build():
    records=all_records(); good=[r for r in records if r['status']=='preserved']
    entries=a.rows('catalog/entries.jsonl')
    patterns=defaultdict(list)
    for e in entries:
        title=e.get('normalized_title') or c.norm_title(e['title'])
        if 6<=len(title)<=150: patterns[title].append(e['id'])
    matcher=Matcher(patterns)
    locations=[]; occurrences=[]; record_by_id={r['id']:r for r in records}
    for index,r in enumerate(good,1):
        batch=[]; batch_start=1; segment_count=0
        for segment in pages(r):
            segment_count+=1
            location={'witness_id':r['id'],'source_url':r['url'],'source_raw_sha256':r['raw_sha256'],
                      'edition_refs':extra_editions(r),'kind':segment['kind'],'number':segment['number'],
                      'printed_page':None,'source_text_sha256':a.digest(segment['text'].encode()),
                      'text_chars':len(segment['text'])}
            if 'end_line' in segment: location['end_line']=segment['end_line']
            segment.update(location)
            batch.append(segment)
            compact=normal(segment['text'])
            found=set()
            for title,offset in matcher.find(compact):
                if title in found: continue
                found.add(title)
                occurrences.append({'title_key':title,'catalogue_entry_ids':patterns[title],
                                    'witness_id':r['id'],'locator':{'kind':segment['kind'],'number':segment['number']},
                                    'normalized_text_offset':offset,'normalization':'NFKC; letters/digits retained; whitespace/punctuation ignored',
                                    'basis':'exact_normalized_title_occurs_in_source_page',
                                    'status':'candidate_occurrence_not_work_identity_or_revision',
                                    'source_raw_sha256':r['raw_sha256'],'source_url':r['url']})
            if len(batch)==20:
                path=f"archive/segments/{r['id']}/{batch_start:05d}-{segment_count:05d}.jsonl"
                a.lines(path,batch)
                locations.extend(dict(x,segment_file=path,segment_file_line=n) for n,x in enumerate([{k:v for k,v in x.items() if k!='text'} for x in batch],1))
                batch=[]; batch_start=segment_count+1
        if batch:
            path=f"archive/segments/{r['id']}/{batch_start:05d}-{segment_count:05d}.jsonl"
            a.lines(path,batch)
            locations.extend(dict(x,segment_file=path,segment_file_line=n) for n,x in enumerate([{k:v for k,v in x.items() if k!='text'} for x in batch],1))
        if index%100==0: print('Segmented witnesses',index,len(good),flush=True)
    a.lines('archive/index/locations.jsonl',locations)
    a.lines('archive/index/title-occurrences.jsonl',occurrences)
    by_edition=defaultdict(list)
    for r in good:
        for e in extra_editions(r): by_edition[(e.get('edition_id'),e.get('volume'))].append(r)
    by_url=defaultdict(list)
    for r in good:
        by_url[r['url']].append(r)
        if r.get('landing_url'): by_url[r['landing_url']].append(r)
    maps=[]
    for e in entries:
        direct=by_url.get(e.get('url'),[])
        containers=[r for r in by_edition[(e.get('edition_id'),e.get('volume'))] if r.get('media') in {'pdf','official_page_text','official_page_images'}]
        maps.append({'catalogue_entry_id':e['id'],'title':e['title'],'source_id':e['source_id'],
                     'edition_id':e.get('edition_id'),'volume':e.get('volume'),
                     'direct_witness_ids':sorted({r['id'] for r in direct}),
                     'volume_container_witness_ids':sorted({r['id'] for r in containers}),
                     'available_in_retained_files':bool(direct or containers),
                     'direct_basis':'exact_URL_or_explicit_official_landing_URL',
                     'container_basis':'same_catalogue_edition_and_volume; not proof_of_page_or_text_identity'})
    a.lines('archive/index/work-mappings.jsonl',maps)
    bookmarks=[]
    for r in good:
        bm=r.get('pdf_bookmarks',[])
        for i,(level,title,start) in enumerate(bm):
            following=[x[2] for x in bm[i+1:] if x[0]<=level and x[2]>start]
            end=(following[0]-1) if following else r.get('pdf_pages')
            bookmarks.append({'witness_id':r['id'],'title':title,'level':level,'pdf_page_start':start,
                              'pdf_page_end_candidate':end,'source_url':r['url'],
                              'basis':'source_PDF_bookmark_not_manually_verified_article_boundary'})
    a.lines('archive/index/bookmarks.jsonl',bookmarks)
    edition_reports=[]
    for edition in a.load('config/editions.json'):
        vols=edition.get('volume_numbers',list(range(1,edition['expected_volumes']+1)))
        items=[]
        for v in vols:
            selected=by_edition[(edition['id'],v)]
            distinct={r['id']:r for r in selected}
            containers=[r for r in distinct.values() if r.get('media') in {'pdf','official_page_text','official_page_images'}]
            htmls=[r for r in distinct.values() if r.get('media')=='html' and r.get('kind')=='html_link']
            indexed=[e for e in entries if (e.get('edition_id')==edition['id'] or (edition['id']=='maoxuan-1977-v5' and e.get('edition_id')=='maoxuan-mia-catalogue')) and e.get('volume')==v and e.get('kind')=='html_link']
            container_complete=any(r.get('media')=='pdf' or r.get('reader_text_array_complete') or r.get('complete_reader_pages') for r in containers)
            html_complete=bool(indexed) and all(by_url.get(e.get('url')) for e in indexed)
            items.append({'volume':v,'whole_source_file_or_reader_complete':container_complete,
                          'all_registered_HTML_entries_preserved':html_complete,
                          'registered_HTML_entries':len(indexed),'preserved_HTML_witnesses':len(htmls),
                          'container_witnesses':[{'id':r['id'],'media':r['media'],'source_url':r['url'],
                             'raw_paths':r['raw_paths'],'text_path':r.get('text_path'),
                             'document_path':r.get('document_path'),'record_path':'archive/records/'+r['id']+'.json',
                             'native_text_layer':r.get('text_layer_status'),
                             'native_page_count':r.get('pdf_pages') or r.get('reader_page_count'),
                             'printed_edition_identity':r.get('edition_verification_status','source_label_not_print_imprint_review')} for r in containers],
                          'status':'source_files_preserved' if container_complete else ('registered_web_texts_preserved' if html_complete else 'not_complete')})
        report={'edition_id':edition['id'],'title':edition['title'],'expected_volumes':len(vols),
                'volumes_with_source_files':sum(x['whole_source_file_or_reader_complete'] for x in items),
                'volumes_covered_by_files_or_registered_web_texts':sum(x['status']!='not_complete' for x in items),
                'volumes':items,'meaning_of_complete':'complete retrieved digital files or bounded reader pages, NOT independent printed-book or manuscript authentication'}
        a.write('archive/editions/'+edition['id']+'.json',report)
        md=['# '+edition['title'],'','旧新版、网页转录和扫描件分别标注。下面的“已保存”描述来源数字文件，不是对档案原件的认证。','']
        for v in items:
            md+=['## 卷 '+str(v['volume'])+' · '+v['status'],'']
            for b in v['container_witnesses']:
                target=b['document_path'] or b['record_path']
                md += [f"- [全文与定位](../../{target}) · `{b['id']}` · {b['media']} · 页数 {b['native_page_count']}",
                       f"  [来源及原文件路径](../../{b['record_path']})"]
            if v['preserved_HTML_witnesses']: md.append(f"已保存 {v['preserved_HTML_witnesses']} 份网页文本；逐篇入口见全局工作映射。")
            md.append('')
        a.textfile('archive/editions/'+edition['id']+'.md','\n'.join(md)+'\n')
        edition_reports.append(report)
    a.write('reports/edition-coverage.json',edition_reports)
    summary={'generated_at':a.now(),'retained_witnesses':len(good),'searchable_segments':len(locations),
             'title_page_occurrences':len(occurrences),'source_PDF_bookmarks':len(bookmarks),
             'catalogue_entries_with_direct_or_volume_source':sum(m['available_in_retained_files'] for m in maps),
             'catalogue_entries':len(maps),'confirmed_historical_revision_edges_added':0,
             'warning':'Occurrence and container mappings do not independently authenticate work identity or revision causation.'}
    a.write('reports/research-index.json',summary)
    # A small, inspectable packet for the initial research question.
    needles=['关于正确处理人民内部矛盾的问题','修改','十三','十四']
    snippets=[]
    wanted_titles=['关于正确处理人民内部矛盾的问题','事情正在起变化']
    wanted_keys={c.norm_title(t) for t in wanted_titles}
    for hit in occurrences:
        if hit['title_key'] not in wanted_keys: continue
        r=record_by_id[hit['witness_id']]
        if not any(e.get('edition_id') in {'wengao-old-13','wengao-2023-20','nianpu-2023-9','nianpu-post1949-6','maoxuan-1977-v5','maoxuan-mia-catalogue'} for e in extra_editions(r)): continue
        snippets.append({'title':r['title'],**hit})
    a.write('exports/zhengchu-source-locations.json',snippets)
    a.textfile('exports/zhengchu-fulltext-guide.md','# 《正处》：先看全文，再讨论演变\n\n'
        '正文已实际保存在 archive/；大文件可按页或行读取，不需要把整本书塞入上下文。\n\n'
        '```bash\npython research.py search 关于正确处理人民内部矛盾的问题 --limit 20\n'
        'python research.py versions 关于正确处理人民内部矛盾的问题\n'
        'python research.py read <见证本ID> --page <PDF或阅读器页码>\n```\n\n'
        '定位表见 [zhengchu-source-locations.json](zhengchu-source-locations.json)。索引命中可能来自目录、正文或后出题注，先读前后页再判断。'
        'PDF页码与纸本页码不自动等同；修改次数不把论文转引升级成原稿直接证明。'
        '二月讲话、六月发表及各套文稿/年谱是不同见证材料，不得补造中间稿。\n')
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    return summary


def iter_segments(witness=None):
    folder=a.BASE/'segments'
    files=(folder/witness).glob('*.jsonl') if witness else folder.glob('*/*.jsonl')
    for p in sorted(files):
        for n,line in enumerate(p.read_text(encoding='utf-8').splitlines(),1):
            x=json.loads(line); x['segment_file']=a.rel(p); x['segment_file_line']=n
            yield x


def search(query,limit=20,witness=None,edition=None):
    key=normal(query); count=0
    if not key: raise ValueError('Non-empty letters or Chinese characters required')
    for s in iter_segments(witness):
        if edition and not any(e.get('edition_id')==edition for e in s['edition_refs']): continue
        text=normal(s['text']); pos=text.find(key)
        if pos<0: continue
        result={k:v for k,v in s.items() if k!='text'}
        result.update(normalized_excerpt=text[max(0,pos-80):pos+len(key)+200],
                      excerpt_warning='whitespace/punctuation normalized for search, use read for exact stored source text')
        print(json.dumps(result,ensure_ascii=False)); count+=1
        if count>=limit: break
    return count


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('build')
    q=sub.add_parser('search'); q.add_argument('query'); q.add_argument('--limit',type=int,default=20); q.add_argument('--witness'); q.add_argument('--edition')
    r=sub.add_parser('read'); r.add_argument('witness'); r.add_argument('--page',type=int); r.add_argument('--line',type=int)
    v=sub.add_parser('versions'); v.add_argument('title')
    args=p.parse_args()
    if args.command=='build': build()
    elif args.command=='search': search(args.query,max(1,min(args.limit,200)),args.witness,args.edition)
    elif args.command=='read':
        found=False
        for s in iter_segments(args.witness):
            if args.page is not None and (s['kind']=='web_lines' or s['number']!=args.page): continue
            if args.line is not None and not (s['kind']=='web_lines' and s['number']<=args.line<=s.get('end_line',s['number'])): continue
            print(json.dumps({k:v for k,v in s.items() if k!='text'},ensure_ascii=False,indent=2))
            print(s['text']); found=True
            if args.page is not None or args.line is not None: break
        if not found: raise SystemExit('No stored segment matches the requested witness/locator')
    elif args.command=='versions':
        key=c.norm_title(args.title)
        for r in a.rows('archive/index/title-occurrences.jsonl'):
            if r['title_key']==key: print(json.dumps(r,ensure_ascii=False))


if __name__=='__main__': main()
