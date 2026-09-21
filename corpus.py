#!/usr/bin/env python3
"""Provenance-first catalogue and local research tools. Python 3.10+.
Web material is untrusted data. The public output contains metadata, not book text.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import threading
import time
import unicodedata
from urllib.parse import urljoin, urlsplit, urldefrag
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
UA = 'MaoTextHistoryResearch/1.0 (+https://github.com/Pluto-Mo/mao-text-history)'
ALLOWED = {'www.marxists.org', 'marxists.org', 'ebook.dswxyjy.org.cn',
           'www.theorychina.org.cn', 'cn.theorychina.org.cn', 'fuwu.12371.cn',
           'hprc.cssn.cn', 'www.dswxyjy.org.cn', 'paper.people.com.cn'}
CN = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10,
      '十一':11,'十二':12,'十三':13,'十四':14,'十五':15,'十六':16,'十七':17,
      '十八':18,'十九':19,'二十':20}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ident(prefix: str, *values: str) -> str:
    return prefix + '-' + sha('\0'.join(values).encode())[:16]


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def rows(path: str) -> list[dict]:
    p = ROOT / path
    return [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines() if s.strip()] if p.exists() else []


def save(path: str, value) -> None:
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def save_rows(path: str, values: list[dict]) -> None:
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(''.join(json.dumps(v, ensure_ascii=False, separators=(',', ':'))+'\n' for v in values), encoding='utf-8')


def clean(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def norm_title(text: str) -> str:
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'〔未删节本〕|\[未删节本\]|〖附录\d*〗', '', text)
    text = re.sub(r'\(([一二三四五六七八九十〇○零廿卅0-9]{4}年)[^)]*\)$', '', text)
    return ''.join(c for c in text if c.isalnum())


def safe_url(url: str) -> bool:
    try:
        u = urlsplit(url)
        return u.scheme == 'https' and u.hostname in ALLOWED and not u.username and not u.password and u.port in (None, 443)
    except ValueError:
        return False


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not safe_url(newurl):
            raise ValueError('redirect outside HTTPS source allowlist')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Fetcher:
    """Bounded requests; robots respected; raw bytes stay in ignored .cache/."""
    def __init__(self, delay: float = 0.8):
        self.delay = delay
        self.lock = threading.Lock()
        self.last = defaultdict(float)
        self.robots = {}
        self.opener = build_opener(SafeRedirect())

    def _request(self, url: str) -> tuple[bytes, str, str, str]:
        if not safe_url(url):
            raise ValueError('URL outside HTTPS source allowlist')
        host = urlsplit(url).hostname
        with self.lock:
            wait = self.delay - (time.monotonic() - self.last[host])
            if wait > 0:
                time.sleep(wait)
            self.last[host] = time.monotonic()
        req = Request(url, headers={'User-Agent': UA, 'Accept': 'text/html,text/plain;q=0.9'})
        with self.opener.open(req, timeout=25) as response:
            ct = response.headers.get_content_type()
            if ct not in {'text/html', 'application/xhtml+xml', 'text/plain'}:
                raise ValueError('binary or non-HTML content is not harvested by public collector: '+ct)
            raw = response.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise ValueError('response exceeds 8 MiB limit')
            return raw, ct, response.geturl(), response.headers.get_content_charset() or ''

    def prepare(self, urls: list[str]) -> None:
        for origin in sorted({f'{urlsplit(u).scheme}://{urlsplit(u).netloc}' for u in urls}):
            rp = RobotFileParser(origin+'/robots.txt')
            try:
                raw, _, _, _ = self._request(origin+'/robots.txt')
                rp.parse(raw.decode('utf-8', errors='replace').splitlines())
                self.robots[origin] = rp
            except HTTPError as exc:
                if exc.code == 404:
                    rp.parse([])
                    self.robots[origin] = rp
                else:
                    self.robots[origin] = 'robots_http_'+str(exc.code)
            except Exception as exc:
                self.robots[origin] = 'robots_unavailable_'+type(exc).__name__

    def get(self, url: str) -> tuple[dict, BeautifulSoup | None]:
        url = urldefrag(url)[0]
        record = {'id': ident('F', url), 'url': url, 'retrieved_at': now(),
                  'raw_retention': 'ephemeral_cache_not_in_repository', 'published_fulltext': False}
        try:
            origin = f'{urlsplit(url).scheme}://{urlsplit(url).netloc}'
            rp = self.robots.get(origin)
            if not isinstance(rp, RobotFileParser):
                raise ValueError(str(rp or 'robots_not_checked'))
            if not rp.can_fetch(UA, url):
                raise ValueError('robots_disallowed')
            raw, ct, final, declared = self._request(url)
            soup = BeautifulSoup(raw, 'html.parser', from_encoding=declared or None)
            for bad in soup(['script','style','noscript']):
                bad.decompose()
            text = soup.get_text('\n', strip=True)
            p = ROOT / '.cache' / (sha(raw)+'.html')
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(raw)
            record.update(status='retrieved_html', final_url=final, content_type=ct,
                          byte_count=len(raw), raw_sha256=sha(raw),
                          extracted_text_sha256=sha(text.encode()), text_char_count=len(text),
                          encoding=soup.original_encoding, html_title=clean(soup.title.get_text()) if soup.title else None)
            if len(text) < 80 or any(s in text[:1500].lower() for s in ('access denied','just a moment','checking your browser')):
                record['status'] = 'shell_or_block_page'
            return record, soup
        except Exception as exc:
            record.update(status='fetch_failed', error=type(exc).__name__+': '+str(exc)[:240])
            return record, None


def catalogue(soup: BeautifulSoup, source: dict, receipt: dict) -> list[dict]:
    """Extract link metadata. Titles without links in printed TOCs are separate records."""
    output = []
    source_url = source['url']
    kind = source['kind']
    current_volume = None
    group = source['edition_id']
    contexts = {}
    for node in soup.descendants:
        if isinstance(node, str):
            s = clean(str(node))
            if kind == 'mia_collect' and s == '《毛泽东集》':
                group, current_volume = 'mia-ji-10', None
            elif kind == 'mia_collect' and s == '《毛泽东集补卷》':
                group, current_volume = 'mia-bujuan-9', None
            match = re.match(r'^第([一二三四五六七八九十]+)卷(?:\s|　|$)', s)
            if match and len(s) < 100:
                current_volume = CN.get(match.group(1))
            if kind == 'mia_main' and s.startswith('其它'):
                group, current_volume = 'mia-other', None
        else:
            contexts[id(node)] = (group, current_volume)
    for i, a in enumerate(soup.find_all('a', href=True), 1):
        href = a['href'].strip()
        title = clean(a.get_text(' ', strip=True))
        if not title or title in {'Image', '首页', '中文马克思主义文库', '毛泽东'}:
            continue
        if not href or href.startswith(('#','javascript:','mailto:')):
            continue
        url = urljoin(source_url, href)
        if not safe_url(url):
            continue
        path = urlsplit(url).path
        if kind.startswith('mia_'):
            if ('/chinese/maozedong/' not in path and not path.lower().endswith('.pdf')) or path.endswith('/index.htm') or path.endswith('/index.html'):
                continue
        elif kind.startswith('official_'):
            if not re.search(r'/detail/\d+', path) or not ('毛泽东' in title):
                continue
            if kind == 'official_nianpu' and '年谱' not in title:
                continue
            if kind == 'official_maoxuan' and '选集' not in title:
                continue
        else:
            continue
        edition, volume = contexts.get(id(a), (group, None))
        output.append({'id': ident('I', source['id'], url, title), 'title': title,
                       'normalized_title': norm_title(title), 'source_id': source['id'],
                       'source_url': source_url, 'source_raw_sha256': receipt.get('raw_sha256'),
                       'locator': f'a[{i}]', 'url': url, 'edition_id': edition, 'volume': volume,
                       'kind': 'pdf_link' if path.lower().endswith('.pdf') else ('book_landing' if kind.startswith('official_') else 'html_link'),
                       'body_status': 'not_fetched', 'edition_basis': 'website_catalogue_label_not_print_collation'})
    if kind == 'mia_collect':
        for i, td in enumerate(soup.find_all(['td','th']), 1):
            lines = [clean(s) for s in td.get_text('\n').splitlines() if clean(s)]
            if not lines or re.sub(r'\s+', '', lines[0]) != '篇目':
                continue
            edition, volume = contexts.get(id(td), (source['edition_id'], None))
            linked = {clean(a.get_text(' ', strip=True)) for a in td.find_all('a')}
            for n, title in enumerate(lines[1:], 2):
                if title in linked or len(title) < 2 or title.isdigit():
                    continue
                output.append({'id': ident('I', source['id'], f'td{i}:line{n}', title),
                               'title': title, 'normalized_title': norm_title(title), 'source_id':source['id'],
                               'source_url':source_url,'source_raw_sha256':receipt.get('raw_sha256'),
                               'locator':f'td[{i}]/text-line[{n}]', 'url':None,
                               'edition_id':edition,'volume':volume,'kind':'unlinked_toc',
                               'body_status':'no_individual_url','printed_page':None,
                               'edition_basis':'website_catalogue_label_not_print_collation'})
    return list({r['id']:r for r in output}.values())


def relations(entries: list[dict]) -> list[dict]:
    buckets = defaultdict(list)
    for row in entries:
        if len(row['normalized_title']) >= 6:
            buckets[row['normalized_title']].append(row)
    result = []
    for title, group in sorted(buckets.items()):
        if len({r['source_id'] for r in group}) < 2:
            continue
        members = sorted({r['id'] for r in group})
        result.append({'id':ident('M',*members), 'kind':'same_title_candidate',
                       'normalized_title':title, 'members':members,
                       'status':'needs_text_and_date_review',
                       'is_historical_revision_edge':False,
                       'basis':'exact normalized title across distinct catalogue sources; not proof of same work'})
    return result


def build_volumes() -> list[dict]:
    result=[]
    for edition in load('config/editions.json'):
        for ordinal, number in enumerate(edition.get('volume_numbers', list(range(1, edition['expected_volumes']+1)))):
            result.append({'id':f"{edition['id']}:v{number:02d}", 'edition_id':edition['id'],
                           'volume':number, 'title':edition['title'], 'source_ids':edition['source_ids'],
                           'full_volume_acquired':False, 'public_fulltext':False,
                           'status':'not_acquired', 'date_range':edition.get('date_ranges',[])[ordinal] if edition.get('date_ranges') else None})
    return result


def collect(limit: int, workers: int) -> None:
    sources=load('config/sources.json')
    fetcher=Fetcher()
    fetcher.prepare([s['url'] for s in sources])
    receipts, entries=[],[]
    for source in sources:
        record,soup=fetcher.get(source['url'])
        record['source_id']=source['id']
        receipts.append(record)
        if soup and record['status']=='retrieved_html':
            entries.extend(catalogue(soup,source,record))
        print(source['id'],record['status'],flush=True)
    entries=list({r['id']:r for r in entries}.values())
    targets=sorted({r['url'] for r in entries if r['kind']=='html_link'})
    targets=list(dict.fromkeys([s['url'] for s in sources if s['kind']=='text_witness']+targets))
    already={r['url'] for r in receipts}
    targets=[u for u in targets if u not in already]
    selected=targets[:limit]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for k,(record,_) in enumerate(pool.map(fetcher.get,selected),1):
            receipts.append(record)
            if k % 40 == 0:
                print(f'witness checks {k}/{len(selected)}',flush=True)
    by_url={r['url']:r for r in receipts}
    for row in entries:
        if row.get('url') in by_url:
            row['body_status']=by_url[row['url']]['status']
            row['receipt_id']=by_url[row['url']]['id']
    mappings=relations(entries)
    save_rows('catalog/entries.jsonl',entries)
    save_rows('catalog/fetches.jsonl',receipts)
    save_rows('catalog/relations.jsonl',mappings)
    save_rows('catalog/volumes.jsonl',build_volumes())
    report={'generated_at':now(),'scope':'catalogues and HTML witness acquisition checks; not full books',
            'source_pages':len(sources),'source_page_statuses':dict(Counter(r['status'] for r in receipts if 'source_id' in r)),
            'catalogue_entries':len(entries),'entries_by_source':dict(Counter(r['source_id'] for r in entries)),
            'entries_by_kind':dict(Counter(r['kind'] for r in entries)),
            'fetch_statuses':dict(Counter(r['status'] for r in receipts)),
            'same_title_candidate_groups':len(mappings), 'confirmed_revision_edges':0,
            'unattempted_html_urls':max(0,len(targets)-len(selected)),
            'persistent_full_volumes':0,'published_book_fulltexts':0,
            'raw_bytes_location':'temporary runner .cache; not retained in public Git or artifacts',
            'warnings':['Catalogue coverage is not full-text coverage.','Exact title matches are not verified edition mappings.','Fetch hashes identify observed bytes, not authenticity.','Missing books remain explicit volume records.']}
    save('reports/coverage.json',report)
    save('reports/manifest.json',{'generated_at':now(),'files':{str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in sorted((ROOT/'catalog').glob('*.jsonl'))}})
    print(json.dumps(report,ensure_ascii=False,indent=2))


def validate() -> int:
    errors=[]
    sources=load('config/sources.json')
    ids=[s['id'] for s in sources]
    if len(ids)!=len(set(ids)): errors.append('duplicate source IDs')
    for s in sources:
        if not safe_url(s['url']): errors.append('unsafe source '+s['id'])
    editions=load('config/editions.json')
    for e in editions:
        if e['expected_volumes']<1: errors.append('invalid volume count')
        if any(s not in ids for s in e['source_ids']): errors.append('unknown edition source '+e['id'])
        if e.get('date_ranges') and len(e['date_ranges'])!=e['expected_volumes']: errors.append('date range count '+e['id'])
    entries=rows('catalog/entries.jsonl')
    entry_ids={r['id'] for r in entries}
    if len(entry_ids)!=len(entries): errors.append('duplicate entries')
    for row in entries:
        if row['source_id'] not in ids: errors.append('orphan entry')
        if row.get('url') and not safe_url(row['url']): errors.append('unsafe entry')
    for rel in rows('catalog/relations.jsonl'):
        if not set(rel['members'])<=entry_ids: errors.append('orphan relation')
        if rel.get('is_historical_revision_edge'): errors.append('automatic historical edge forbidden')
    for case in load('data/evidence.json'):
        if not set(case['source_ids'])<=set(ids): errors.append('orphan evidence '+case['id'])
    mp=ROOT/'reports/manifest.json'
    if mp.exists():
        for name,expected in load('reports/manifest.json')['files'].items():
            p=(ROOT/name).resolve()
            if not p.is_relative_to(ROOT.resolve()) or not p.is_file() or sha(p.read_bytes())!=expected:
                errors.append('manifest mismatch '+name)
    print(json.dumps({'ok':not errors,'errors':errors,'catalogue_entries':len(entries)},ensure_ascii=False))
    return 1 if errors else 0


def search(query: str) -> list[dict]:
    q=norm_title(query)
    return [r for r in rows('catalog/entries.jsonl') if q and q in r['normalized_title']]


def context(query: str) -> dict:
    evidence=[r for r in load('data/evidence.json') if query in json.dumps(r,ensure_ascii=False)]
    hits=search(query)
    source_ids={r['source_id'] for r in hits}|{s for e in evidence for s in e['source_ids']}
    return {'query':query,'evidence':evidence,'catalogue_hits':hits,
            'sources':[r for r in load('config/sources.json') if r['id'] in source_ids],
            'limitations':['Catalogue matches do not mean the body is stored.','Do not infer missing drafts or political motives.','Use exact source, edition and locator for every historical claim.']}


def ingest(path: str, source_id: str, edition_id: str, rights_note: str, text_path: str | None) -> str:
    if source_id not in {s['id'] for s in load('config/sources.json')}:
        raise ValueError('Register source ID first in config/sources.json')
    if edition_id not in {e['id'] for e in load('config/editions.json')}:
        raise ValueError('Register edition ID first in config/editions.json')
    if not rights_note.strip(): raise ValueError('rights note required')
    p=Path(path).expanduser().resolve()
    if not p.is_file(): raise ValueError('input file missing')
    if p.stat().st_size>300*1024*1024: raise ValueError('input exceeds 300 MiB limit')
    raw=p.read_bytes(); key=ident('LOCAL',source_id,edition_id,sha(raw))
    out=ROOT/'local'/key; out.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(p,out/('original'+p.suffix))
    record={'id':key,'source_id':source_id,'edition_id':edition_id,'raw_sha256':sha(raw),
            'imported_at':now(),'rights_note':rights_note,'printed_page':None,'published':False}
    tp=Path(text_path).expanduser() if text_path else (p if p.suffix.lower() in {'.txt','.md'} else None)
    if tp:
        text=tp.read_text(encoding='utf-8')
        paragraphs=[{'id':f'{key}:p{i:06d}','text':s,'printed_page':None} for i,s in enumerate(re.split(r'\n\s*\n',text),1) if s.strip()]
        (out/'paragraphs.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in paragraphs),encoding='utf-8')
        record['text_sha256']=sha(text.encode())
    (out/'record.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return key


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='cmd',required=True)
    sub.add_parser('validate')
    c=sub.add_parser('collect'); c.add_argument('--limit',type=int,default=1500); c.add_argument('--workers',type=int,default=3)
    for name in ('search','context','trace'):
        c=sub.add_parser(name); c.add_argument('query')
    c=sub.add_parser('ingest'); c.add_argument('path'); c.add_argument('--source-id',required=True); c.add_argument('--edition-id',required=True); c.add_argument('--rights-note',required=True); c.add_argument('--text-path')
    args=p.parse_args()
    if args.cmd=='validate': raise SystemExit(validate())
    if args.cmd=='collect':
        if not 0<=args.limit<=5000 or not 1<=args.workers<=4: p.error('limit 0..5000, workers 1..4')
        collect(args.limit,args.workers)
    elif args.cmd=='search': print(json.dumps(search(args.query),ensure_ascii=False,indent=2))
    elif args.cmd=='context': print(json.dumps(context(args.query),ensure_ascii=False,indent=2))
    elif args.cmd=='trace':
        records=load('config/sources.json')+load('config/editions.json')+load('data/evidence.json')
        for path in ('catalog/entries.jsonl','catalog/relations.jsonl','catalog/fetches.jsonl','catalog/volumes.jsonl'): records+=rows(path)
        found=[r for r in records if r['id']==args.query]
        print(json.dumps(found,ensure_ascii=False,indent=2))
        if not found: raise SystemExit(1)
    else: print(ingest(args.path,args.source_id,args.edition_id,args.rights_note,args.text_path))


if __name__=='__main__':
    main()
