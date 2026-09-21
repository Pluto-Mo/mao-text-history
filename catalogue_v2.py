#!/usr/bin/env python3
"""Audited catalogue parser: legacy Chinese encodings and parallel volume columns.
Default invocation refreshes catalogue metadata and reuses earlier raw-byte observations.
Use --full to also refetch all HTML witnesses with the corrected decoder.
"""
from __future__ import annotations
import json
import re
from collections import Counter
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString
import corpus as c

BASE_GET = c.Fetcher.get
BASE_CATALOGUE = c.catalogue


def decode_html(raw: bytes, declared: str = '') -> tuple[str, str]:
    try:
        return raw.decode('utf-8-sig'), 'utf-8'
    except UnicodeDecodeError:
        pass
    head = raw[:8192].decode('ascii', errors='ignore')
    meta = re.search(r'charset\s*=\s*[\"\']?([a-zA-Z0-9_-]+)', head, re.I)
    encodings = [meta.group(1) if meta else '', declared, 'gb18030', 'big5']
    for encoding in encodings:
        encoding = encoding.lower().strip()
        if not encoding or encoding in {'iso-8859-1','latin1','windows-1252','ascii','utf-8'}:
            continue
        if encoding in {'gb2312','gbk','gb_2312-80'}:
            encoding = 'gb18030'
        try:
            return raw.decode(encoding), encoding
        except (UnicodeDecodeError, LookupError):
            pass
    return raw.decode('gb18030', errors='replace'), 'gb18030-with-replacements'


def corrected_get(self, url):
    record, old_soup = BASE_GET(self, url)
    if not record.get('raw_sha256'):
        return record, old_soup
    raw = (c.ROOT / '.cache' / (record['raw_sha256']+'.html')).read_bytes()
    text, encoding = decode_html(raw, record.get('encoding') or '')
    soup = BeautifulSoup(text, 'html5lib')
    for node in soup(['script','style','noscript']):
        node.decompose()
    extracted = soup.get_text('\n', strip=True)
    record.update(encoding=encoding, parser='html5lib', extraction_version=2,
                  replacement_characters=extracted.count('\ufffd'),
                  extracted_text_sha256=c.sha(extracted.encode()),
                  text_char_count=len(extracted),
                  html_title=c.clean(soup.title.get_text()) if soup.title else None)
    if len(extracted) < 80 or any(s in extracted[:1500].lower() for s in ('access denied','just a moment','checking your browser')):
        record['status'] = 'shell_or_block_page'
    else:
        record['status'] = 'retrieved_html'
    return record, soup


def compact(text):
    return re.sub(r'\s+', '', text)


def line_texts(tag):
    """Use rendered BR boundaries, not every nested text node, as TOC item boundaries."""
    lines, current = [], []
    for node in tag.descendants:
        if isinstance(node, NavigableString):
            current.append(str(node))
        elif node.name == 'br':
            line = c.clean(''.join(current))
            if line:
                lines.append(line)
            current = []
    line = c.clean(''.join(current))
    if line:
        lines.append(line)
    return lines


def column_volume(td):
    row = td.find_parent('tr')
    table = td.find_parent('table')
    if row is None or table is None:
        return None, None
    column = 0
    for cell in row.find_all(['td','th'], recursive=False):
        if cell is td:
            break
        column += int(cell.get('colspan',1))
    prior = [r for r in table.find_all('tr') if r.find_parent('table') is table]
    try:
        index = next(i for i,r in enumerate(prior) if r is row)
    except StopIteration:
        return None, None
    for earlier in reversed(prior[:index]):
        start = 0
        for cell in earlier.find_all(['td','th'], recursive=False):
            end = start + int(cell.get('colspan',1))
            if start <= column < end:
                title = c.clean(cell.get_text(' ',strip=True))
                match = re.match(r'^第([一二三四五六七八九十]+)卷',title)
                if match and len(title) < 120:
                    return c.CN.get(match.group(1)), title
            start = end
    return None, None


def collect_contexts(soup):
    """Section labels are separate from volume headers, which may be side by side."""
    result, group = {}, 'mia-ji-10'
    for node in soup.descendants:
        if isinstance(node, NavigableString):
            text = compact(str(node))
            if len(text)<24 and '毛泽东集' in text:
                if '补卷' in text:
                    group = 'mia-bujuan-9'
                elif text in {'《毛泽东集》','毛泽东集'}:
                    group = 'mia-ji-10'
        else:
            result[id(node)] = group
    return result


def catalogue(soup, source, receipt):
    data = BASE_CATALOGUE(soup,source,receipt)
    anchors = soup.find_all('a',href=True)
    kind = source['kind']
    if kind == 'mia_main':
        volume, edition, contexts = None, 'maoxuan-mia-catalogue', {}
        for node in soup.descendants:
            if isinstance(node,NavigableString):
                continue
            if node.name=='h4':
                title=c.clean(node.get_text(' ',strip=True))
                match=re.match(r'^第([一二三四五六七八九十]+)卷(?:\s|$)',title)
                if match:
                    volume,edition=c.CN[match.group(1)],'maoxuan-mia-catalogue'
                elif re.match(r'^其它(?:\s|$)',title):
                    volume,edition=None,'mia-other'
            contexts[id(node)]=(edition,volume)
        for row in data:
            anchor=anchors[int(re.search(r'\d+',row['locator']).group())-1]
            row['edition_id'],row['volume']=contexts.get(id(anchor),(edition,None))
    elif kind == 'mia_1968':
        volume,contexts=0,{}
        for node in soup.descendants:
            if isinstance(node,NavigableString): continue
            if node.name=='h3':
                title=compact(node.get_text(' ',strip=True))
                if len(title)<35 and any(s in title for s in ('～','~')):
                    volume+=1
            contexts[id(node)]=volume if 1<=volume<=5 else None
        for row in data:
            anchor=anchors[int(re.search(r'\d+',row['locator']).group())-1]
            row['volume']=contexts.get(id(anchor))
            row['volume_basis']='order_of_five_main_date_range_headings'
    elif kind == 'mia_collect':
        groups=collect_contexts(soup)
        data=[r for r in data if r['kind']!='unlinked_toc']
        for row in data:
            anchor=anchors[int(re.search(r'\d+',row['locator']).group())-1]
            td=anchor.find_parent(['td','th'])
            row['edition_id']=groups.get(id(anchor),'mia-ji-10')
            row['volume'],row['volume_heading']=column_volume(td) if td else (None,None)
            row['volume_basis']='column_aligned_header' if row['volume'] else 'unresolved'
            if row['kind']=='pdf_link':
                match=re.fullmatch(r'第([一二三四五六七八九十]+)卷',row['title'])
                row['volume']=c.CN.get(match.group(1)) if match else None
                row['volume_basis']='download_link_title'
                if '年表' in row['title']:
                    row['edition_id']='mia-nianbiao'
                    row['volume']=1
        for i,td in enumerate(soup.find_all(['td','th']),1):
            lines=line_texts(td)
            if not lines or compact(lines[0])!='篇目': continue
            group=groups.get(id(td),'mia-ji-10')
            volume,header=column_volume(td)
            linked={c.clean(a.get_text(' ',strip=True)) for a in td.find_all('a',href=True)}
            for n,title in enumerate(lines[1:],2):
                if title in linked or len(title)<2 or title.isdigit(): continue
                if any(title.endswith(t) and compact(title[:-len(t)]).startswith('〖附录') for t in linked if t):
                    continue
                data.append({'id':c.ident('I',source['id'],f'td{i}:line{n}',title),
                    'title':title,'normalized_title':c.norm_title(title),'source_id':source['id'],
                    'source_url':source['url'],'source_raw_sha256':receipt.get('raw_sha256'),
                    'locator':f'td[{i}]/br-line[{n}]','url':None,'edition_id':group,
                    'volume':volume,'volume_heading':header,
                    'volume_basis':'column_aligned_header' if volume else 'unresolved',
                    'kind':'unlinked_toc','body_status':'no_individual_url','printed_page':None,
                    'edition_basis':'website_catalogue_label_not_print_collation'})
    for row in data:
        row['parser_version']=2
        row['title_has_replacement_character']='\ufffd' in row['title']
    return list({r['id']:r for r in data}.values())


def refresh():
    """Repair catalogues without pretending old raw-byte receipts used the new decoder."""
    sources=c.load('config/sources.json')
    if not (c.ROOT/'reports/coverage.json').exists():
        raise RuntimeError('Initial acquisition report is missing; run --full first')
    original=c.rows('catalog/fetches.jsonl')
    source_urls={s['url'] for s in sources}
    receipts=[]
    for row in original:
        if row['url'] not in source_urls:
            row['extraction_quality']='legacy_decoder_not_revalidated'
            row['text_extraction_is_verified']=False
            receipts.append(row)
    f=c.Fetcher()
    f.prepare([s['url'] for s in sources])
    entries=[]
    for source in sources:
        receipt,soup=f.get(source['url'])
        receipt['source_id']=source['id']
        receipts.append(receipt)
        if soup and receipt['status']=='retrieved_html':
            entries.extend(c.catalogue(soup,source,receipt))
        print(source['id'],receipt['status'],receipt.get('encoding'),flush=True)
    entries=list({r['id']:r for r in entries}.values())
    by_url={r['url']:r for r in receipts}
    for row in entries:
        if row.get('url') in by_url:
            receipt=by_url[row['url']]
            row['body_status']=receipt['status']
            row['receipt_id']=receipt['id']
            row['body_text_extraction_verified']=receipt.get('extraction_version')==2
    relations=c.relations(entries)
    c.save_rows('catalog/entries.jsonl',entries)
    c.save_rows('catalog/fetches.jsonl',receipts)
    c.save_rows('catalog/relations.jsonl',relations)
    c.save_rows('catalog/volumes.jsonl',c.build_volumes())
    report=c.load('reports/coverage.json')
    report.update(generated_at=c.now(),parser_version=2,
        source_page_statuses=dict(Counter(r['status'] for r in receipts if 'source_id' in r)),
        catalogue_entries=len(entries),entries_by_source=dict(Counter(r['source_id'] for r in entries)),
        entries_by_kind=dict(Counter(r['kind'] for r in entries)),
        fetch_statuses=dict(Counter(r['status'] for r in receipts)),
        same_title_candidate_groups=len(relations),
        unresolved_catalogue_volumes=sum(1 for r in entries if r['source_id']=='MIA-COLLECT' and r['volume'] is None),
        titles_with_decoding_replacements=sum(1 for r in entries if r['title_has_replacement_character']),
        legacy_text_extractions_not_revalidated=sum(1 for r in receipts if r.get('extraction_quality')=='legacy_decoder_not_revalidated'),
        unattempted_html_urls=len({r['url'] for r in entries if r['kind']=='html_link'}-set(by_url)))
    c.save('reports/coverage.json',report)
    c.save('reports/manifest.json',{'generated_at':c.now(),'files':{str(p.relative_to(c.ROOT)):c.sha(p.read_bytes()) for p in sorted((c.ROOT/'catalog').glob('*.jsonl'))}})
    c.save('reports/parser-audit.json',{'version':2,'checks':{
        'main_volumes':dict(Counter(str(r['volume']) for r in entries if r['source_id']=='MIA-MAIN')),
        'wuhan_volumes':dict(Counter(str(r['volume']) for r in entries if r['source_id']=='MIA-1968')),
        'collect_edition_volume_pairs':dict(Counter(f"{r['edition_id']}:v{r['volume']}" for r in entries if r['source_id']=='MIA-COLLECT'))},
        'examples':[r for r in entries if r['title'] in {'给宫崎滔天的信','井冈山前委对中央的报告','论持久战','关于正确处理人民内部矛盾的问题'}]})
    print(json.dumps(report,ensure_ascii=False,indent=2))


def install():
    c.Fetcher.get=corrected_get
    c.catalogue=catalogue


if __name__=='__main__':
    import sys
    install()
    if '--full' in sys.argv:
        c.collect(1500,3)
    else:
        refresh()
    raise SystemExit(c.validate())
