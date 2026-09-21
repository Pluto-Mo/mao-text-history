#!/usr/bin/env python3
"""Read data literals in the public official reader; never execute source JavaScript.
The original search-data bytes and reader configuration remain independently traceable.
Image-only yearbooks are preserved as numbered page images and reconstructed view PDFs.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
from urllib.parse import urljoin, urlsplit
import fitz
import archive_corpus as a


def script_value(text,key):
    found=re.findall(r'bookConfig\.'+re.escape(key)+r'\s*=\s*("(?:\\.|[^"\\])*"|\d+)',text)
    return json.loads(found[-1]) if found else None


def data_array(text,name):
    match=re.search(r'\b'+re.escape(name)+r'\s*=\s*',text)
    if not match: return None
    start=match.end()
    result,_=json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(result,list) or not all(isinstance(x,str) for x in result): raise ValueError('unexpected data array type')
    return result


def descriptions():
    results=[]
    entries=a.rows('catalog/entries.jsonl')
    for book in a.load('reports/official-reader-discovery.json'):
        row=next((x for x in entries if x.get('url')==book['landing_url']),None)
        for reader in book['readers']:
            config=next((x for x in reader.get('scripts',[]) if x['url'].endswith('/config.js') and x.get('path')),None)
            search=next((x for x in reader.get('scripts',[]) if x['url'].endswith('/search_config.js') and x.get('path')),None)
            if not config: continue
            cfg=(a.ROOT/config['path']).read_text(encoding='utf-8-sig')
            n=script_value(cfg,'totalPageCount')
            title=book['title']
            number=re.search(r'第([一二三四五六七八九十]+)卷',title)
            cn={'一':1,'二':2,'三':3,'四':4,'五':5,'六':6}
            v=cn.get(number.group(1)) if number else None
            if '选集' in title: edition='maoxuan-official'
            elif any(x in title for x in ['上卷','中卷','下卷']):
                edition='nianpu-pre1949-3'
                v=next((i for i,label in enumerate(['上卷','中卷','下卷'],1) if label in title),None)
            else: edition='nianpu-post1949-6'
            pages=None; error=None
            if search:
                try: pages=data_array((a.ROOT/search['path']).read_text(encoding='utf-8-sig'),'textForPages')
                except Exception as exc: error=str(exc)
            normal=script_value(cfg,'normalPath')
            results.append({'title':title,'landing_url':book['landing_url'],'reader_url':reader['url'],
                            'reader_page_count':n,'config':config,'search':search,
                            'page_texts':pages,'text_parse_error':error,
                            'normal_image_directory':urljoin(reader['url'],normal) if normal else None,
                            'edition_id':edition,'volume':v,'catalogue_entry_ids':[row['id']] if row else []})
    return results


def extract_texts():
    results=[]
    for b in descriptions():
        summary={k:v for k,v in b.items() if k!='page_texts'}
        pages=b['page_texts']
        if pages is None:
            summary['status']='reader_has_no_search_text_array'
            results.append(summary); continue
        source=b['search']; url=source['url']; ident=a.uid(url)
        # The probe saved decoded UTF-8 text; fetch the exact bytes again so that
        # raw_sha256 genuinely identifies the retained original response bytes.
        client=a.Client(); raw,headers=client.get(url)
        decoded,enc=a.decode_html(raw,headers.get('charset',''))
        original_pages=data_array(decoded,'textForPages')
        if original_pages!=pages: raise ValueError('reader search-data changed since discovery: '+b['title'])
        storage=a.preserved(raw,'js')
        r={'id':ident,'title':b['title']+'〔官方阅读器全文文字层〕','url':url,
           'reader_url':b['reader_url'],'landing_url':b['landing_url'],
           'status':'preserved','media':'official_page_text','authorization_ref':a.GRANT,
           'source_ids':['OFF-MAO' if '选集' in b['title'] else 'OFF-NIAN'],
           'catalogue_entry_ids':b['catalogue_entry_ids'],
           'edition_refs':[{'edition_id':b['edition_id'],'volume':b['volume'],'basis':'official_book_landing_and_reader_configuration'}],
           'reader_page_count':b['reader_page_count'],'page_array_length':len(pages),
           'reader_text_array_complete':len(pages)==b['reader_page_count'],
           'array_index_to_reader_page':'index + 1' if len(pages)==b['reader_page_count'] else 'unresolved',
           'encoding':enc,'retrieved_at':a.now(),'archival_authenticity_verified':False,
           'original_work_completeness_verified':False,
           'text_role_note':'original publication text including prefaces, author text, editorial notes; not newly authored history',
           'normalization':'JSON string escapes decoded; page text unchanged',**storage}
        text=''; page_map=[]
        for i,page in enumerate(pages):
            start=len(text)
            text+=f'\n\n=== READER PAGE {i+1}; ARRAY INDEX {i} ===\n'+page+'\n'
            page_map.append({'array_index':i,'reader_page':i+1 if r['reader_text_array_complete'] else None,
                             'char_start':start,'char_end':len(text),'text':page,'text_sha256':a.digest(page.encode())})
        a.render_document(r,text)
        r['page_map_path']='archive/pages/'+ident+'.jsonl'
        a.lines(r['page_map_path'],page_map)
        a.write(a.record_path(url),r)
        summary.update(status='preserved',witness_id=ident,array_length=len(pages),complete_array=r['reader_text_array_complete'],text_chars=r['text_chars'])
        results.append(summary)
    a.write('reports/official-page-texts.json',results)
    print(json.dumps([{k:v for k,v in b.items() if k in ['title','reader_page_count','status','array_length','complete_array','normal_image_directory','reader_url','edition_id','volume']} for b in results],ensure_ascii=False,indent=2),flush=True)


def preserve_images(b,client,workers=5):
    n=b['reader_page_count']; base=b['normal_image_directory']
    if not isinstance(n,int) or not 1<=n<=1500 or not base: raise ValueError('missing bounded reader page configuration')
    ident='P-'+a.uid(b['reader_url'])[2:]
    target=a.BASE/'official-pages'/ident
    target.mkdir(parents=True,exist_ok=True)
    records=[]; failures=[]
    def one(i):
        url=urljoin(base,f'{i}.jpg')
        p=target/f'{i:04d}.jpg'
        if p.exists():
            raw=p.read_bytes()
        else:
            raw,headers=client.get(url)
            if not raw.startswith(b'\xff\xd8'): raise ValueError('not JPEG: '+url)
            image=fitz.open(stream=raw,filetype='jpeg')
            if len(image)!=1: raise ValueError('invalid image')
            image.close(); p.write_bytes(raw)
        return {'reader_page':i,'url':url,'path':a.rel(p),'sha256':a.digest(raw),'bytes':len(raw)}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        fs={pool.submit(one,i):i for i in range(1,n+1)}
        for done,f in enumerate(as_completed(fs),1):
            try: records.append(f.result())
            except Exception as exc: failures.append({'reader_page':fs[f],'error':str(exc)[:400]})
            if done%100==0: print(b['title'],done,n,flush=True)
    records.sort(key=lambda r:r['reader_page'])
    manifest={'id':ident,'title':b['title'],'reader_url':b['reader_url'],'landing_url':b['landing_url'],
              'edition_id':b['edition_id'],'volume':b['volume'],'reader_page_count':n,
              'preserved_pages':len(records),'complete_reader_pages':len(records)==n and not failures,
              'image_url_basis':'reader config normalPath plus main.js sequential page JPEG naming',
              'config_source':b['config'],'authorization_ref':a.GRANT,'records':records,'failures':failures,'generated_at':a.now()}
    a.write('archive/official-pages/'+ident+'/manifest.json',manifest)
    # Reconstructed PDF is a convenience derivative. Original page JPEGs and
    # per-page provenance remain authoritative, and this is not a publisher PDF.
    if manifest['complete_reader_pages']:
        doc=fitz.open()
        for r in records:
            im=fitz.open(r['path'])
            converted=fitz.open(stream=im.convert_to_pdf(),filetype='pdf')
            doc.insert_pdf(converted); converted.close(); im.close()
        raw=doc.tobytes(garbage=3,deflate=True); doc.close()
        r={'id':ident,'title':b['title']+'〔官方阅读器逐页保存〕','url':b['reader_url'],
           'landing_url':b['landing_url'],'status':'preserved','media':'official_page_images',
           'authorization_ref':a.GRANT,'source_ids':['OFF-MAO' if '选集' in b['title'] else 'OFF-NIAN'],
           'edition_refs':[{'edition_id':b['edition_id'],'volume':b['volume'],'basis':'official_landing_reader_page_count_and_sequence'}],
           'catalogue_entry_ids':b['catalogue_entry_ids'],'reader_page_count':n,
           'preserved_pages':len(records),'complete_reader_pages':True,
           'image_manifest':'archive/official-pages/'+ident+'/manifest.json',
           'pdf_origin':'reconstructed_from_source_page_JPEGs_not_publisher_original_PDF',
           'original_work_completeness_verified':False,'archival_authenticity_verified':False,
           'retrieved_at':a.now(),**a.preserved(raw,'pdf')}
        a.write('archive/records/'+ident+'.json',r)
    return manifest


def main():
    if len(sys.argv)>1 and sys.argv[1]=='images':
        wanted={int(x) for x in sys.argv[2:]}
        books=[b for b in descriptions() if b['edition_id']=='nianpu-post1949-6' and (not wanted or b['volume'] in wanted)]
        client=a.Client(0.18); client.prepare([b['reader_url'] for b in books])
        results=[]
        for b in books:
            results.append(preserve_images(b,client))
            print('Saved pages',b['title'],results[-1]['preserved_pages'],flush=True)
        a.write('reports/official-image-batch-'+('-'.join(map(str,sorted(wanted))) or 'all')+'.json',
                [{k:v for k,v in b.items() if k not in ['records','config_source']} for b in results])
    else: extract_texts()


if __name__=='__main__': main()
