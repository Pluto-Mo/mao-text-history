#!/usr/bin/env python3
"""Follow actual public reader links; preserve reader configuration for inspection.
No browser scripts are executed, no guessed credentials or access bypasses.
"""
from pathlib import Path
import json
import re
from urllib.parse import urljoin,urlsplit
from bs4 import BeautifulSoup
import archive_corpus as a


def main():
    targets=[r for r in a.targets().values() if r['kind']=='book_landing']
    client=a.Client(0.35)
    client.prepare([r['url'] for r in targets])
    reports=[]
    assets=set()
    for row in targets:
        report={'title':row['title'],'landing_url':row['url'],'readers':[]}
        try:
            raw,headers=client.get(row['url'])
            decoded,encoding=a.decode_html(raw,headers.get('charset',''))
            soup=BeautifulSoup(decoded,'html5lib')
            readers=[]
            for link in soup.find_all('a',href=True):
                url=urljoin(row['url'],link['href'])
                if a.safe(url) and ('立即阅读' in link.get_text() or '/storage/files/' in url): readers.append(url)
            for url in sorted(set(readers)):
                rr={'url':url,'scripts':[]}
                try:
                    data,h=client.get(url)
                    decoded,enc=a.decode_html(data,h.get('charset',''))
                    a.textfile('archive/portal-assets/'+a.uid(url)+'.html',decoded)
                    rr.update(raw_sha256=a.digest(data),asset_path='archive/portal-assets/'+a.uid(url)+'.html')
                    page=BeautifulSoup(decoded,'html5lib')
                    for tag in page.find_all('script',src=True):
                        script=urljoin(url,tag['src'])
                        if not a.safe(script): continue
                        if any(x in script.lower() for x in ['jquery','analytics','bootstrap','ga.js','hm.js']): continue
                        entry={'url':script}
                        try:
                            b,m=client.get(script)
                            text,enc=a.decode_html(b,m.get('charset',''))
                            path='archive/portal-assets/'+a.uid(script)+'.js.txt'
                            a.textfile(path,text)
                            entry.update(path=path,sha256=a.digest(b),bytes=len(b))
                            matches=[]
                            for match in re.finditer(r'.{0,100}(?:\.pdf|totalPage|pageCount|basic-html|search|bookConfig|large/|files/mobile).{0,200}',text,re.I):
                                matches.append(match.group(0))
                                if len(matches)>=30: break
                            entry['configuration_samples']=matches
                        except Exception as exc: entry['error']=str(exc)[:200]
                        rr['scripts'].append(entry)
                    rr['resource_links']=[{'tag':tag.name,'url':urljoin(url,tag.get('src') or tag.get('href') or '')} for tag in page.find_all(['iframe','embed','object','link']) if tag.get('src') or tag.get('href')]
                except Exception as exc: rr['error']=str(exc)[:200]
                report['readers'].append(rr)
        except Exception as exc: report['error']=str(exc)[:200]
        reports.append(report)
        a.write('reports/official-reader-discovery.json',reports)
        print(row['title'],len(report['readers']),flush=True)
    print('Reader discovery records:',len(reports),flush=True)


if __name__=='__main__': main()
