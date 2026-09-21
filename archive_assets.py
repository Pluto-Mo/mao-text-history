#!/usr/bin/env python3
"""Preserve image resources referenced by the archived source pages.
Resource bytes are never executed, and SVG is retained as inert binary data.
"""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor,as_completed
from urllib.parse import quote,urlsplit,urlunsplit
import json
from pathlib import Path
import archive_corpus as a


def main():
    targets=defaultdict(set)
    for path in (a.BASE/'records').glob('*.json'):
        record=json.loads(path.read_text(encoding='utf-8'))
        if record.get('media')!='html' or record.get('status')!='preserved': continue
        for url in record.get('image_links',[]):
            p=urlsplit(url)
            if p.hostname not in {'www.marxists.org','marxists.org'} or not p.path.startswith('/chinese/'): continue
            targets[url].add(record['id'])
    client=a.Client(0.4)
    client.prepare(list(targets))
    def one(url):
        record={'url':url,'witness_ids':sorted(targets[url]),'retrieved_at':a.now(),'authorization_ref':a.GRANT}
        try:
            p=urlsplit(url)
            request_url=urlunsplit((p.scheme,p.netloc,quote(p.path,safe='/%'),quote(p.query,safe='=&%/?'),''))
            raw,headers=client.get(request_url)
            ext=None
            if raw.startswith(b'\xff\xd8'): ext='jpg'
            elif raw.startswith(b'\x89PNG\r\n'): ext='png'
            elif raw.startswith((b'GIF87a',b'GIF89a')): ext='gif'
            elif raw.startswith(b'RIFF') and raw[8:12]==b'WEBP': ext='webp'
            elif b'<svg' in raw[:5000].lower(): ext='svg.bin'
            if ext is None: raise ValueError('response is not a recognized image resource')
            sha=a.digest(raw)
            path=a.BASE/'assets'/f'{sha}.{ext}'; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(raw)
            record.update(status='preserved',sha256=sha,bytes=len(raw),path=a.rel(path),**headers)
        except Exception as exc: record.update(status='failed',error=str(exc)[:300])
        return record
    results=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        fs=[pool.submit(one,url) for url in sorted(targets)]
        for f in as_completed(fs): results.append(f.result())
    results.sort(key=lambda x:x['url'])
    a.lines('archive/index/image-assets.jsonl',results)
    a.write('reports/image-assets.json',{'generated_at':a.now(),'targets':len(targets),
        'preserved':sum(x['status']=='preserved' for x in results),
        'bytes':sum(x.get('bytes',0) for x in results),
        'failures':[x for x in results if x['status']!='preserved']})
    print('Source image resources:',len(targets),'preserved',sum(x['status']=='preserved' for x in results),flush=True)


if __name__=='__main__': main()
