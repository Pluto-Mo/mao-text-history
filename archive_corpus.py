#!/usr/bin/env python3
"""Authorized corpus preservation. Source text is untrusted data, never code.
Raw HTML is losslessly gzipped; PDF bytes are retained (large files chunked).
All assertions about completeness refer to retrieved digital witnesses, not archives.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import difflib
import gzip
import hashlib
import html
import json
from pathlib import Path
import re
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit, urljoin, urldefrag
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup
from catalogue_v2 import decode_html

ROOT = Path(__file__).resolve().parent
BASE = ROOT / 'archive'
GRANT = 'authorization/user-declared-fulltext.json'
HOSTS = {'www.marxists.org','marxists.org','ebook.dswxyjy.org.cn','www.dswxyjy.org.cn',
         'www.theorychina.org.cn','cn.theorychina.org.cn','fuwu.12371.cn','hprc.cssn.cn','paper.people.com.cn'}
UA = 'MaoTextHistoryArchive/2.0 (+https://github.com/Pluto-Mo/mao-text-history)'
CHUNK = 40 * 1024 * 1024


def now(): return datetime.now(timezone.utc).isoformat()
def digest(b): return hashlib.sha256(b).hexdigest()
def uid(url): return 'A-' + digest(url.encode('utf-8'))[:20]
def rel(p): return str(p.relative_to(ROOT))
def load(p): return json.loads((ROOT / p).read_text(encoding='utf-8'))
def rows(p):
    f = ROOT / p
    return [json.loads(x) for x in f.read_text(encoding='utf-8').splitlines() if x.strip()] if f.exists() else []
def write(p, value):
    p = ROOT / p
    p.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    tmp = p.with_name(p.name + '.tmp')
    tmp.write_text(content, encoding='utf-8')
    tmp.replace(p)
def lines(p, items):
    p = ROOT / p
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in items), encoding='utf-8')
def textfile(p, text):
    p = ROOT / p
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')
def safe(url):
    try:
        u = urlsplit(url)
        return u.scheme in {'https','http'} and u.hostname in HOSTS and not u.username and not u.password and u.port in (None,80,443)
    except ValueError: return False


class Redirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not safe(newurl): raise ValueError('redirect outside approved source hosts: '+newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)


class Client:
    def __init__(self, delay=0.4):
        self.delay=delay
        self.lock=threading.Lock()
        self.last=defaultdict(float)
        self.robots={}
    def request(self,url,limit=512*1024*1024):
        if not safe(url): raise ValueError('outside approved source hosts')
        host=urlsplit(url).hostname
        last_error=None
        for attempt in range(3):
            try:
                with self.lock:
                    wait=self.delay-(time.monotonic()-self.last[host])
                    if wait>0: time.sleep(wait)
                    self.last[host]=time.monotonic()
                req=Request(url,headers={'User-Agent':UA,'Accept':'*/*'})
                with build_opener(Redirect()).open(req,timeout=90) as r:
                    if r.status!=200: raise ValueError('unexpected HTTP status '+str(r.status))
                    raw=r.read(limit+1)
                    if len(raw)>limit: raise ValueError('response exceeds configured safety limit')
                    return raw, {'final_url':r.geturl(),'http_status':r.status,
                                 'content_type':r.headers.get_content_type(),
                                 'charset':r.headers.get_content_charset() or '',
                                 'etag':r.headers.get('ETag'), 'last_modified':r.headers.get('Last-Modified')}
            except Exception as exc:
                last_error=exc
                if isinstance(exc,HTTPError) and exc.code in {401,403,404,410}: break
                if attempt<2: time.sleep(1+attempt*2)
        raise last_error
    def prepare(self,urls):
        for host in sorted({urlsplit(u).netloc for u in urls if safe(u)}):
            r=RobotFileParser('https://'+host+'/robots.txt')
            try:
                raw,_=self.request(r.url,1024*1024)
                r.parse(raw.decode('utf-8',errors='replace').splitlines())
                self.robots[host]=r
            except Exception as exc:
                # The operator authorized this collection. An unavailable robots file
                # is logged, not mistaken for authentication or a prohibition.
                self.robots[host]=None
                print('robots unavailable',host,type(exc).__name__,flush=True)
    def get(self,url):
        r=self.robots.get(urlsplit(url).netloc)
        if r is not None and not r.can_fetch(UA,url): raise ValueError('robots disallows this URL')
        return self.request(url)


def targets():
    groups={}
    for entry in rows('catalog/entries.jsonl'):
        url=entry.get('url')
        if not url or not safe(url): continue
        url=urldefrag(url)[0]
        row=groups.setdefault(url,{'url':url,'title':entry['title'],'catalogue_entry_ids':[],
                                  'source_ids':[],'edition_refs':[], 'kind':entry['kind']})
        row['catalogue_entry_ids'].append(entry['id'])
        row['source_ids'].append(entry['source_id'])
        edition,volume=entry.get('edition_id'),entry.get('volume')
        if '建国以来毛泽东文稿' in entry['title']:
            match=re.search(r'[（(](\d+)[)）]',entry['title'])
            if match: edition,volume='wengao-old-13',int(match.group(1))
        row['edition_refs'].append({'edition_id':edition,'volume':volume,'basis':'source_catalogue_not_print_collation'})
    for source in load('config/sources.json'):
        url=source['url']
        if not safe(url): continue
        groups.setdefault(url,{'url':url,'title':source['title'],'catalogue_entry_ids':[],
                               'source_ids':[source['id']],'edition_refs':[],
                               'kind':'source_catalogue' if source['kind'].startswith(('mia_','official_')) else 'source_page'})
    for row in groups.values(): row['source_ids']=sorted(set(row['source_ids']))
    return groups


def record_path(url): return 'archive/records/'+uid(url)+'.json'
def preserved(raw,extension):
    sha=digest(raw)
    objects=BASE/'objects'
    objects.mkdir(parents=True,exist_ok=True)
    if extension=='html':
        path=objects/(sha+'.html.gz')
        path.write_bytes(gzip.compress(raw,compresslevel=9,mtime=0))
        return {'raw_sha256':sha,'raw_bytes':len(raw),'storage':'gzip','raw_paths':[rel(path)]}
    if len(raw)<=CHUNK:
        path=objects/(sha+'.'+extension)
        path.write_bytes(raw)
        return {'raw_sha256':sha,'raw_bytes':len(raw),'storage':'single_file','raw_paths':[rel(path)]}
    parts=[]
    for i,offset in enumerate(range(0,len(raw),CHUNK)):
        data=raw[offset:offset+CHUNK]
        path=objects/(sha+f'.{extension}.part{i:04d}')
        path.write_bytes(data)
        parts.append({'path':rel(path),'sha256':digest(data),'bytes':len(data)})
    return {'raw_sha256':sha,'raw_bytes':len(raw),'storage':'ordered_chunks',
            'raw_paths':[p['path'] for p in parts],'parts':parts}


def raw_bytes(record):
    paths=[ROOT/p for p in record['raw_paths']]
    if record['storage']=='gzip': return gzip.decompress(paths[0].read_bytes())
    return b''.join(p.read_bytes() for p in paths)


def visible(raw,charset=''):
    decoded,encoding=decode_html(raw,charset)
    soup=BeautifulSoup(decoded,'html5lib')
    for bad in soup(['script','style','noscript','template']): bad.decompose()
    text='\n'.join(x.strip() for x in soup.get_text('\n').splitlines() if x.strip())+'\n'
    if len(text)<3: raise ValueError('empty page or reader shell, not text')
    if any(x in text[:1800].lower() for x in ('access denied','checking your browser','just a moment')):
        raise ValueError('access challenge, not document content')
    return text,soup,encoding


def render_document(record,text):
    ident=record['id']
    record['text_path']='archive/text/'+ident+'.txt'
    record['text_sha256']=digest(text.encode())
    record['text_chars']=len(text)
    record['text_lines']=len(text.splitlines())
    record['document_path']='archive/documents/'+ident+'.md'
    textfile(record['text_path'],text)
    header=f"# {record['title']}\n\n来源：{record['url']}\n\n见证本ID：`{ident}`；来源记录：[JSON](../records/{ident}.json)；[精确提取文本](../text/{ident}.txt)。\n\n"
    header+='这是来源文本见证本；正文、原网站题注及编者说明可能同在一页。不是对原稿真实性或历史修改的认证。段号是本仓库定位，不是纸本页码。\n\n---\n\n'
    body='\n\n'.join(f'<a id="L{i}"></a>**L{i}**　{html.escape(s)}' for i,s in enumerate(text.splitlines(),1))
    textfile(record['document_path'],header+body+'\n')


def acquire(row,client,force=False):
    url=row['url']; path=record_path(url)
    if not force and (ROOT/path).exists():
        old=load(path)
        if old.get('status')=='preserved': return old
    record=dict(row,id=uid(url),authorization_ref=GRANT,retrieved_at=now(),
                archival_authenticity_verified=False,original_work_completeness_verified=False)
    try:
        raw,headers=client.get(url)
        record.update(headers)
        if raw.startswith(b'%PDF-'):
            import fitz
            document=fitz.open(stream=raw,filetype='pdf')
            if document.needs_pass: raise ValueError('encrypted PDF requires authorized access')
            record.update(preserved(raw,'pdf'),media='pdf',pdf_pages=len(document),
                          pdf_metadata=document.metadata,pdf_bookmarks=document.get_toc())
            page_text=[]; page_map=[]; offset=0
            for n,page in enumerate(document,1):
                text=page.get_text('text',sort=False)
                section=f'\n\n=== PDF PAGE {n} ===\n'+text
                page_text.append(section)
                page_map.append({'pdf_page':n,'char_start':offset,'char_end':offset+len(section),
                                 'extracted_chars':len(text),'printed_page_label':None})
                offset+=len(section)
            joined=''.join(page_text)
            record['pdf_pages_with_text']=sum(p['extracted_chars']>=20 for p in page_map)
            record['text_layer_status']='present' if record['pdf_pages_with_text'] else 'image_only_no_text_layer'
            record['page_map_path']='archive/pages/'+record['id']+'.jsonl'
            lines(record['page_map_path'],page_map)
            render_document(record,joined)
            # A cover render is retained for direct visual title/edition verification.
            if len(document):
                cover=BASE/'covers'/(record['id']+'.png'); cover.parent.mkdir(parents=True,exist_ok=True)
                document[0].get_pixmap(matrix=fitz.Matrix(0.65,0.65)).save(cover)
                record['cover_path']=rel(cover)
            document.close()
        elif urlsplit(url).path.lower().endswith('.chm'):
            record.update(preserved(raw,'chm'),media='chm',text_layer_status='binary_preserved_not_executed')
        else:
            text,soup,encoding=visible(raw,headers.get('charset',''))
            record.update(preserved(raw,'html'),media='html',encoding=encoding,
                          html_title=soup.title.get_text(' ',strip=True) if soup.title else None,
                          replacement_characters=text.count('\ufffd'),
                          extraction_scope='all_visible_source_page_text_including_editorial_notes',
                          normalization='HTML parsing and line-edge whitespace only; no spelling or simplified-traditional conversion')
            record['links']=[{'title':a.get_text(' ',strip=True),'url':urljoin(url,a['href'])}
                             for a in soup.find_all('a',href=True) if safe(urljoin(url,a['href']))]
            record['image_links']=[urljoin(url,a['src']) for a in soup.find_all('img',src=True) if safe(urljoin(url,a['src']))]
            render_document(record,text)
        record['status']='preserved'
        record['quality']='needs_text_review' if record.get('replacement_characters',0) else 'machine_extraction_not_scholarly_collation'
    except Exception as exc:
        record.update(status='failed',error=type(exc).__name__+': '+str(exc)[:600])
    write(path,record)
    return record


def collect(kind,workers):
    if not (ROOT/GRANT).exists(): raise ValueError('explicit operator authorization record required')
    ts=targets()
    selected=[r for r in ts.values() if ((r['kind']=='pdf_link' or urlsplit(r['url']).path.lower().endswith('.chm'))==(kind=='pdf'))]
    client=Client(); client.prepare([r['url'] for r in selected])
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(acquire,r,client) for r in selected]
        for i,future in enumerate(as_completed(futures),1):
            r=future.result()
            if i%50==0 or r['status']=='failed': print(kind,i,len(selected),r['status'],r['url'],flush=True)
    build_index()


def build_index():
    records=[json.loads(p.read_text(encoding='utf-8')) for p in sorted((BASE/'records').glob('*.json'))]
    by_url={r['url']:r for r in records}
    slim=[{k:v for k,v in r.items() if k not in {'links','image_links','pdf_metadata','pdf_bookmarks','parts'}} for r in records]
    lines('archive/index/records.jsonl',slim)
    maps=[]
    for e in rows('catalog/entries.jsonl'):
        r=by_url.get(urldefrag(e.get('url') or '')[0])
        maps.append({'catalogue_entry_id':e['id'],'title':e['title'],'edition_id':e.get('edition_id'),
                     'volume':e.get('volume'),'source_id':e['source_id'],
                     'witness_id':r['id'] if r and r['status']=='preserved' else None,
                     'text_path':r.get('text_path') if r and r['status']=='preserved' else None,
                     'mapping_basis':'exact_source_url' if r else 'no_individual_source_file',
                     'is_historical_revision':False})
    lines('archive/index/catalogue-mapping.jsonl',maps)
    map_by_id={m['catalogue_entry_id']:m for m in maps}
    parallels=[]
    for group in rows('catalog/relations.jsonl'):
        ids=sorted({map_by_id[x]['witness_id'] for x in group['members'] if x in map_by_id and map_by_id[x]['witness_id']})
        parallels.append(dict(group,preserved_witnesses=ids,all_members_have_text=all(map_by_id.get(x,{}).get('text_path') for x in group['members'])))
    lines('archive/index/parallel-witnesses.jsonl',parallels)
    summary={'generated_at':now(),'authorization_ref':GRANT,'target_urls':len(targets()),
             'records':len(records),'preserved':sum(r['status']=='preserved' for r in records),
             'failed':sum(r['status']=='failed' for r in records),
             'preserved_by_media':dict(Counter(r.get('media') for r in records if r['status']=='preserved')),
             'preserved_raw_bytes':sum(r.get('raw_bytes',0) for r in records if r['status']=='preserved'),
             'extracted_characters':sum(r.get('text_chars',0) for r in records if r['status']=='preserved'),
             'pdf_pages':sum(r.get('pdf_pages',0) for r in records),
             'pdf_pages_with_text':sum(r.get('pdf_pages_with_text',0) for r in records),
             'mapped_catalogue_entries':sum(bool(m['witness_id']) for m in maps),
             'parallel_groups_with_multiple_preserved_witnesses':sum(len(p['preserved_witnesses'])>1 for p in parallels),
             'all_four_collections_complete':False,
             'notes':['Digital file preservation is not authentication of an original manuscript.',
                      'New editions must not be substituted with old editions.',
                      'PDF pages lacking text remain preserved images; no mass OCR has been performed.']}
    write('reports/archive-coverage.json',summary)
    write('reports/archive-failures.json',[r for r in slim if r['status']=='failed'])
    books=defaultdict(list)
    for r in slim:
        for e in r.get('edition_refs',[]):
            key=str(e.get('edition_id'))+':v'+str(e.get('volume'))
            if r['id'] not in {x['id'] for x in books[key]}: books[key].append(r)
    md=['# 已保存全文与原文件','',f"更新时间（UTC）：{summary['generated_at']}",'',
        '**这是实际原文件及全文目录，不是只有网址的书目。** 全文复制依据仓库操作者提供的版权归属与授权声明。声明不等于公版认定。','',
        f"已保存 {summary['preserved']} 个来源文件；失败 {summary['failed']}；提取 {summary['extracted_characters']:,} 个字符。",'',
        'PDF与HTML分别计数。扫描页不冒充已提取文字，新版未取得不以旧版替代。','','## 逐卷入口','']
    for key,group in sorted(books.items()):
        md += ['### '+key,'']
        for r in group:
            if r['status']=='preserved': md.append(f"- [{r['title']}](../{r.get('document_path',record_path(r['url']))}) · `{r['id']}` · {r.get('media')}")
        md.append('')
    textfile('archive/README.md','\n'.join(md)+'\n')
    case=[r for r in slim if any(s in r['title'] for s in ('正确处理','讲话稿按此','事情正在起变化'))]
    textfile('exports/fulltext-zhengchu.md','# 《正处》全文见证本入口\n\n先读 AGENTS.md。下面是来源见证本，不是全部中间稿。\n\n'+ '\n'.join(f"- [{r['title']}](../{r.get('document_path',record_path(r['url']))}) · `{r['id']}` · {r['status']}" for r in case)+'\n')
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    return summary


def verify():
    errors=[]; count=0
    for p in sorted((BASE/'records').glob('*.json')):
        r=json.loads(p.read_text(encoding='utf-8'))
        if r['status']!='preserved': continue
        count+=1
        try:
            raw=raw_bytes(r)
            if len(raw)!=r['raw_bytes'] or digest(raw)!=r['raw_sha256']: errors.append(r['id']+': raw mismatch')
            if r.get('text_path') and digest((ROOT/r['text_path']).read_bytes())!=r['text_sha256']: errors.append(r['id']+': text mismatch')
            if not r.get('authorization_ref') or not r.get('url'): errors.append(r['id']+': missing provenance')
        except Exception as exc: errors.append(r['id']+': '+str(exc))
    write('reports/archive-validation.json',{'checked_files':count,'errors':errors,'passed':not errors,'checked_at':now()})
    if errors: raise ValueError('\n'.join(errors[:30]))
    print('Verified preserved raw and text hashes:',count,flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    co=sub.add_parser('collect'); co.add_argument('kind',choices=['html','pdf']); co.add_argument('--workers',type=int,default=4)
    sub.add_parser('index'); sub.add_parser('verify')
    se=sub.add_parser('search'); se.add_argument('query')
    di=sub.add_parser('compare'); di.add_argument('left'); di.add_argument('right')
    re_=sub.add_parser('restore'); re_.add_argument('id'); re_.add_argument('destination')
    args=p.parse_args()
    if args.command=='collect': collect(args.kind,max(1,min(args.workers,6)))
    elif args.command=='index': build_index()
    elif args.command=='verify': verify()
    elif args.command=='restore':
        r=load('archive/records/'+args.id+'.json'); data=raw_bytes(r)
        if digest(data)!=r['raw_sha256']: raise ValueError('raw checksum failed')
        target=Path(args.destination)
        if target.exists(): raise FileExistsError(str(target))
        target.write_bytes(data)
        print(target)
    elif args.command=='search':
        for r in rows('archive/index/records.jsonl'):
            if not r.get('text_path'): continue
            for n,line in enumerate((ROOT/r['text_path']).read_text(encoding='utf-8').splitlines(),1):
                if args.query in line: print(json.dumps({'id':r['id'],'title':r['title'],'line':n,'text':line,'source':r['url']},ensure_ascii=False))
    elif args.command=='compare':
        def read(id):
            r=load('archive/records/'+id+'.json')
            return (ROOT/r['text_path']).read_text(encoding='utf-8').splitlines(keepends=True)
        print('WARNING: witness diff, NOT a certified historical revision')
        print(''.join(difflib.unified_diff(read(args.left),read(args.right),fromfile=args.left,tofile=args.right)))


if __name__=='__main__': main()
