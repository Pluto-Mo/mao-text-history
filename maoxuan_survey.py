#!/usr/bin/env python3
"""Read-only whole-Maoxuan first-pass survey. Outputs are not a critical edition.
Run: python maoxuan_survey.py
Uses retained text only; never downloads, executes source material, or alters archive/.
"""
from __future__ import annotations
import csv, hashlib, json, re, subprocess
from collections import Counter, defaultdict
from pathlib import Path
import research as r
from maoxuan_reviewed import reviewed as curated_review

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'research/maoxuan'
TOC = {1:(10,14,14,18),2:(5,11,-329,40),3:(5,7,-779,32),4:(5,10,-1110,70)}
ALIASES = {
 '星星之火，可以燎原':['时局估量和红军行动问题'],
 '反对本本主义':['调查工作','关于调查工作'],
 '中国的红色政权为什么能够存在？':['政治问题和边界党的任务'],
 '中国共产党在民族战争中的地位':['论新阶段','抗日民族战争与抗日民族统一战线发展的新阶段'],
 '反对投降活动':['当前时局的最大危机'],
 '必须制裁反动派':['用国法制裁反动份子'],
 '中国革命和中国共产党':['中国革命与中国共产党'],
 '纪念白求恩':['学习白求恩'],
 '新民主主义论':['新民主主义的政治与新民主主义的文化'],
 '向国民党的十点要求':['延安民众讨汪拥蒋大会通电'],
 '抗日时期的经济问题和财政问题':['经济问题与财政问题','关于过去工作的基本总结'],
 '和美国记者安娜·路易斯·斯特朗的谈话':['和美国记者安娜·刘易斯·斯特朗的谈话'],
 '关于淮海战役的作战方针':['关于淮海战役的的作战方针'],
 '我们党的—些历史经验':['我们党的一些历史经验'],
 '应当重视电影《武训传》的讨论':['为什么重视《武训传》的讨论'],
}
CUE = re.compile(r'修改|改题|改名|删去|删除|删改|删节|补充|增补|加写|校订|修订|审定|定稿|原题|原名|收入|编入|发表|出版|选辑|修正稿|记录稿|手稿')
FORM = [('excerpt',r'一部分|第一部分|第一章|节录|节选|主要部分|要点'),('compiled_documents',r'两个电报|两个文件|两次谈话|两次书面|一些重要指示|几段指示|选辑|序言和跋|序言和按语'),('institutional_drafting',r'为中共中央|为.*起草|受.*委托|代表中共中央'),('speech',r'讲话|讲演|演说|开幕词|闭幕词|开会词|祝词'),('report',r'报告'),('directive',r'指示|决定|通报|通知|决议|命令|训令|布告'),('commentary',r'社论|评论|发刊词'),('correspondence',r'一封信|给.*的信|电报'),('annotation',r'批语|批示|按语')]
LABELS = {'excerpt':'节录／部分文本','compiled_documents':'多文件／多段选编','institutional_drafting':'受托／机构起草','speech':'讲话／演说','report':'报告','directive':'指示／决议等公文','commentary':'社论／评论','correspondence':'信件／电报','annotation':'批语／按语'}

def load(p): return json.loads((ROOT/p).read_text(encoding='utf-8'))
def rows(p): return [json.loads(x) for x in (ROOT/p).read_text(encoding='utf-8').splitlines() if x.strip()]
def sha(t): return hashlib.sha256(t.encode('utf-8')).hexdigest()
def compact(t): return re.sub(r'\s+','',t)
def write(p,x):
 p=OUT/p;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(x,encoding='utf-8')
def jwrite(p,x): write(p,json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def jlines(p,x): write(p,''.join(json.dumps(y,ensure_ascii=False)+'\n' for y in x))
def clean_title(t):
 t=re.sub(r'^[〔【\[](?:未删节本|未删节版|未删减版)[〕】\]]','',t)
 t=re.sub(r'[（(](?:一九|19|20)[^）)]*[）)]$','',t)
 return t.replace('附录：','').strip()
def family(rec):
 ids=[e.get('edition_id','') for e in rec.get('edition_refs',[])]
 if any(x.startswith('nianpu') for x in ids): return 'nianpu'
 if any(x.startswith('wengao') for x in ids): return 'wengao'
 if any(x.startswith('mia-ji') or x.startswith('mia-bujuan') for x in ids): return 'mia_collected'
 if any(x.startswith('maoxuan') for x in ids): return 'maoxuan'
 return 'other_mia_and_sources'
def source(rec,kind,number,end=None):
 return {'witness_id':rec['id'],'source_url':rec['url'],'raw_sha256':rec['raw_sha256'],'edition_refs':rec.get('edition_refs',[]),'kind':kind,'number':number,'end':end or number,'record_path':'archive/records/'+rec['id']+'.json','text_path':rec.get('text_path')}
def source_link(s):
 cmd='--line' if s['kind']=='web_lines' else '--page'
 return f"`{s['witness_id']}` · {s['kind']} {s['number']}–{s['end']} · [来源记录](../../../{s['record_path']})；`python research.py read {s['witness_id']} {cmd} {s['number']}`"

def build_registry(records,entries):
 byurl={q['url']:q for q in records}
 off={next(e['volume'] for e in q['edition_refs'] if e.get('edition_id')=='maoxuan-official'):q for q in records if q.get('media')=='official_page_text' and any(e.get('edition_id')=='maoxuan-official' for e in q.get('edition_refs',[]))}
 works=[]
 for v,(a,b,offset,total) in TOC.items():
  rec=off[v]; pages=list(r.pages(rec)); chunks=[]
  for p in pages[a-1:b]:
   t=re.sub(r'^\s*(?:\d+\s+)?(?:目\s*录|毛泽东选集\s*第[一二三四]卷)\s*\d*\s*','',p['text']); chunks.append(compact(t))
  pattern=r'([^0-9…]+?)[…]*（(一九[^）]*?)）[….]*([0-9]+)(?:[—－\-]([0-9]+))?'
  matches=list(re.finditer(pattern,''.join(chunks)))
  assert len(matches)==total,('TOC changed',v,len(matches))
  for ordinal,m in enumerate(matches,1):
   title=re.sub(r'^(第一次国内革命战争时期|第二次国内革命战争时期|抗日战争时期[（(][上下][)）]|第三次国内革命战争时期)','',m[1].lstrip('—'))
   first,last=int(m[3])+offset,int(m[4] or m[3])+offset
   page=pages[first-1]; test=re.sub(r'〔[^〕]*〕','',page['text'][:500])
   assert r.normal(title.replace('附录：','')) in r.normal(test),(title,first,'title not on first page')
   stars=[x.start() for x in re.finditer(r'\*',page['text'])]
   note=compact(page['text'][stars[-1]+1:]) if len(stars)>1 else ''
   text='\n'.join(p['text'] for p in pages[first-1:last])
   works.append({'id':f'MX{v}-{ordinal:03d}','volume':v,'ordinal':ordinal,'title':title,'entry_type':'appendix' if title.startswith('附录') else 'main_work','date_label':m[2],'date_role':'edition_label_not_automatically_composition_or_publication','printed_page_start':int(m[3]),'printed_page_end':int(m[4] or m[3]),'printed_page_basis':'official_TOC_and_title_start_alignment','baseline':source(rec,'reader_page',first,last),'baseline_text_chars':len(text),'baseline_span_text_sha256':sha(text),'opening_note_candidate':note,'opening_note_warning':'仅从篇首页抽取星号题注，可能跨页截断或混入阅读顺序后的正文；不是完整题注校勘。','title_start_checked':True})
 fifth=[e for e in entries if e.get('edition_id')=='maoxuan-mia-catalogue' and e.get('volume')==5 and e['title'] not in {'出版说明','讲话稿 按此'}]
 assert len(fifth)==70
 for n,e in enumerate(fifth,1):
  rec=byurl[e['url']];text=(ROOT/rec['text_path']).read_text(encoding='utf-8');ls=text.splitlines();date=next((x.strip('（）()') for x in ls[:20] if re.match(r'^[（(]一九',x)),None)
  ns=[(i+1,x.lstrip('* ').strip()) for i,x in enumerate(ls[:20]) if x.startswith('*')]
  works.append({'id':f'MX5-{n:03d}','volume':5,'ordinal':n,'title':e['title'],'entry_type':'main_work','date_label':date,'date_role':'website_edition_label_not_automatically_composition_or_publication','printed_page_start':None,'printed_page_end':None,'printed_page_basis':'not_independently_verified_from_1977_print','baseline':source(rec,'web_lines',1,len(ls)),'baseline_text_chars':len(text),'baseline_span_text_sha256':sha(text),'opening_note_candidate':' '.join(x[1] for x in ns),'opening_note_line_numbers':[x[0] for x in ns],'opening_note_warning':'网站转录题注，未独立认证1977年纸本；其中政治评价须归给编者，不作作者成文时的原话。','title_start_checked':r.normal(e['title']) in r.normal(''.join(ls[:8])),'catalogue_entry_ids':[e['id']]})
 for w in works:
  w['aliases_for_search_only']=ALIASES.get(w['title'],[])
  keys={r.normal(clean_title(w['title']))}|{r.normal(x) for x in w['aliases_for_search_only']}
  direct=[]
  for e in entries:
   if e.get('edition_id')!='maoxuan-mia-catalogue' or e.get('volume')!=w['volume']: continue
   key=r.normal(clean_title(e['title']))
   if key not in keys or e.get('url') not in byurl: continue
   rec=byurl[e['url']]
   direct.append({'catalogue_entry_id':e['id'],'source_title':e['title'],'witness_id':rec['id'],'source_url':rec['url'],'relation':'same_title_web_witness_candidate' if key==r.normal(clean_title(w['title'])) else 'alias_or_container_candidate','identity_verified':False})
  w['catalogue_witness_mappings']=direct
  w['document_form_cues']=[{'type':k,'label':LABELS[k],'basis':'opening_note_or_title_keyword_not_independent_document_identification'} for k,pat in FORM if re.search(pat,w['opening_note_candidate']+' '+w['title'])]
 assert sum(x['entry_type']=='main_work' for x in works)==229
 return works

def build():
 records=[q for q in r.all_records() if q.get('status')=='preserved']; byid={q['id']:q for q in records}
 entries=rows('catalog/entries.jsonl');works=build_registry(records,entries);workby={w['id']:w for w in works}
 patterns=defaultdict(set)
 for w in works:
  for t in [clean_title(w['title'])]+w['aliases_for_search_only']:
   if len(r.normal(t))>=3:patterns[r.normal(t)].add(w['id'])
 matcher=r.Matcher(patterns);candidates=[];counts=Counter();catalogue_counts=Counter();input_receipts=[];empty_pages=[]
 for i,rec in enumerate(records,1):
  if not rec.get('text_path'):continue
  file_text=(ROOT/rec['text_path']).read_text(encoding='utf-8')
  input_receipts.append({'witness_id':rec['id'],'text_path':rec['text_path'],'text_sha256':sha(file_text),'record_sha256':sha(json.dumps(rec,sort_keys=True,ensure_ascii=False))})
  for s in r.pages(rec):
   counts['segments_scanned']+=1;txt=s['text'];counts['characters_scanned']+=len(txt)
   if not r.normal(txt):
    if s['kind']!='web_lines':empty_pages.append({'witness_id':rec['id'],'kind':s['kind'],'number':s['number']})
    continue
   # Match normalized text, retaining a normalized-offset locator rather than fabricating an exact quote.
   norm=r.normal(txt);found={}
   for key,pos in matcher.find(norm):
    for wid in patterns[key]:
     # Keep every occurrence pair; choose the strongest cue window on this page, never just the first hit.
     context=norm[max(0,pos-120):pos+len(key)+230];cues=sorted(set(CUE.findall(context)))
     marked=any(r.normal(t)==key for t in re.findall(r'《([^》]+)》', compact(txt)))
     signal='book_title_marks' if marked else ('near_page_heading' if pos<80 else 'plain_phrase_only')
     hit={'work_id':wid,'matched_key':key,'normalized_offset':pos,'normalized_context':context,'cue_words':cues,'title_form_signal':signal}
     if wid not in found or (marked,len(cues))>(found[wid].get('title_form_signal')=='book_title_marks',len(found[wid]['cue_words'])):found[wid]=hit
   for hit in found.values():
    hit.update(source(rec,s['kind'],s['number'],s.get('end_line')));hit['family']=family(rec);hit['id']='C-'+sha(hit['work_id']+'|'+rec['id']+'|'+s['kind']+'|'+str(s['number']))[:16]
    hit['status']='candidate_only_not_work_identity_revision_or_causation'
    if rec['id']=='A-93d18940d055820ccb0b' and s['number']==567 and hit['work_id'] in {'MX3-008','MX2-026','MX5-058','MX5-059'}:
     hit['reviewed_disposition']='not_a_revision_of_target_work_see_MXE-045'
    hit['normalization']='NFKC plus letters/digits only; context is NOT a verbatim quote'
    candidates.append(hit)
  for b in rec.get('pdf_bookmarks',[]):
   if len(b)!=3:continue
   level,title,page=b; key=r.normal(clean_title(title))
   for wid in patterns.get(key,[]):
    catalogue_counts[wid]+=1
    hit=source(rec,'pdf_page',page);hit.update({'id':'B-'+sha(wid+'|'+rec['id']+'|'+title+'|'+str(page))[:16],'work_id':wid,'bookmark_title':title,'family':family(rec),'status':'source_bookmark_title_candidate_not_article_boundary','cue_words':[]});candidates.append(hit)
  if i%200==0:print('surveyed witnesses',i,flush=True)
 reviewed=curated_review(works,records);evidence=[];evidence_by_work=defaultdict(list);page_cache={}
 for item in reviewed['evidence']:
  item=dict(item);sources=[]
  for pointer in item.pop('sources'):
   rec=byid[pointer['witness_id']];key=rec['id']
   if key not in page_cache:page_cache[key]=list(r.pages(rec))
   if pointer['kind']=='web_lines':
    ls=(ROOT/rec['text_path']).read_text(encoding='utf-8').splitlines();text='\n'.join(ls[pointer['number']-1:pointer.get('end',pointer['number'])])
   else:text='\n'.join(s['text'] for s in page_cache[key] if pointer['number']<=s['number']<=pointer.get('end',pointer['number']))
   assert text,(item['id'],pointer,'missing source')
   out=source(rec,pointer['kind'],pointer['number'],pointer.get('end'));out.update(pointer);out['stored_excerpt_sha256']=sha(text);out['evidence_text_file']='evidence-pages/'+item['id']+'-'+rec['id']+'.txt'
   write(out['evidence_text_file'],text+'\n');sources.append(out)
  item['sources']=sources;item['status']='reviewed_source_statement_not_manuscript_authentication';evidence.append(item)
  for wid in item.get('work_ids',[]):
   assert wid in workby,(item['id'],wid);evidence_by_work[wid].append(item)
 grouped=defaultdict(list)
 for c in candidates:grouped[c['work_id']].append(c)
 volume_stats=[];summary_rows=[]
 for w in works:
  hits=grouped[w['id']];ev=evidence_by_work[w['id']];w['reviewed_evidence_ids']=[x['id'] for x in ev]
  w['candidate_count']=len(hits);w['candidate_families']=dict(Counter(x['family'] for x in hits));w['revision_cue_candidates']=sum(bool(x.get('cue_words')) for x in hits)
  w['research_status']='reviewed_source_statements_with_open_gaps' if ev else 'full_corpus_retrieval_first_pass_only'
  w['historical_draft_chain_complete']=False
  w['gaps']=['尚未完成全篇全部历史稿本的逐段校勘；未命中不等于没有修改。','题名命中可能位于目录、引用或编者注；须核对身份和边界。','修改理由必须有来源；同时代事件本身不能证明因果。']
  if w['volume']<=4:w['gaps'].append('《建国以来毛泽东文稿》不承担建国前原始成文稿的完备覆盖；其中的同题命中可能是后来重编记录。')
  else:w['gaps'].append('本篇基线来自MIA第五卷网页；1977纸本和后出文集的编选、题注及删改仍须分别校核。')
  first=w['opening_note_candidate'];abstract='；'.join(x['claim'] for x in ev[:3]) if ev else ('基线题注摘录：'+first[:155] if first else '已定位基线全文；暂无本轮已复核的成文／修改事件，不作“未修改”判断。')
  w['first_pass_summary']=abstract
  md=[f"# {w['id']} · {w['title']}",'',f"卷 {w['volume']} · {w['entry_type']} · 版本所署日期：{w['date_label']}",'','## 本轮结论','',abstract,'','这是一张文本史首轮研究卡，不是文章思想内容摘要或完整历史校勘本。','','## 基线与来源','',source_link(w['baseline']),'',f"读取范围字符数（含题注等）：{w['baseline_text_chars']}；范围SHA256：`{w['baseline_span_text_sha256']}`。",'','## 基线题注（抽取候选）','',first or '此页未检出独立星号题注；不能据此断定没有编者说明。','',w['opening_note_warning'],'','## 已复核的来源陈述','']
  for e in ev:md += [f"### {e['id']} · {e['relation_type']}",'',e['claim'],'',f"日期／阶段：{e.get('date','未确定')}；归因类别：{e['evidence_class']}。",'',f"因果边界：{e.get('cause_limit','未从同时代事件推导原因。')}",'',f"证据限制：{e['limit']}",'']+[source_link(s) for s in e['sources']]+['']
  if not ev:md+=['本轮未把自动命中升级为已复核的历史断言。','']
  md+=['## 全库映射候选','',f"总候选 {len(hits)}；含编修／发表词的页面候选 {w['revision_cue_candidates']}；分库：{w['candidate_families']}。",'','完整清单见每篇对应的mappings文件；下列最多12项仅为有词线索优先显示，不代表真实性排序。','']
  ranked=sorted(hits,key=lambda x:(x.get('title_form_signal')!='book_title_marks',-len(x.get('cue_words',[])),x['family'],x['witness_id'],x['number']))
  for hit in ranked[:12]:md += [f"- `{hit['id']}` · {hit['family']} · {hit['witness_id']} · {hit['kind']} {hit['number']} · 线索词：{'、'.join(hit.get('cue_words',[])) or '无'}"]
  md+=['','## 明确空缺','']+[f'- {g}' for g in w['gaps']]+['']
  md += [f"[查看本篇完整映射清单](../mappings/{w['id']}.jsonl)", ''];write('articles/'+w['id']+'.md','\n'.join(md));jlines('mappings/'+w['id']+'.jsonl',ranked)
  summary_rows.append([w['id'],w['volume'],w['entry_type'],w['title'],w['date_label'],len(hits),len(ev),w['research_status'],abstract])
 for v in range(1,6):
  ws=[w for w in works if w['volume']==v];volume_stats.append({'volume':v,'main_works':sum(w['entry_type']=='main_work' for w in ws),'appendices':sum(w['entry_type']=='appendix' for w in ws),'baselines_located':len(ws),'with_reviewed_statements':sum(bool(w['reviewed_evidence_ids']) for w in ws),'with_nianpu_candidates':sum(bool(w['candidate_families'].get('nianpu')) for w in ws),'with_wengao_candidates':sum(bool(w['candidate_families'].get('wengao')) for w in ws)})
 report={'schema_version':1,'input_text_corpus_sha256':sha(json.dumps(input_receipts,ensure_ascii=False,sort_keys=True)),'scan_scope':'all retained text witnesses; existing text layers only, no OCR','main_works':229,'appendices':1,'volume_statistics':volume_stats,'retained_text_witnesses_scanned':len(input_receipts),**dict(counts),'no_alphanumeric_text_pages':len(empty_pages),'candidate_links':len(candidates),'reviewed_source_statements':len(evidence),'works_with_reviewed_statements':sum(bool(w['reviewed_evidence_ids']) for w in works),'first_pass_traversal_complete':True,'all_historical_revisions_collated':False,'new_manuscripts_authenticated':0,'warnings':['Page/title retrieval is not historical revision confirmation.','Repeated editions may reproduce the same editorial statement and are not automatically independent corroboration.','Only retained searchable text layers were scanned; figures, underlining, marginal codes, and unreadable OCR require source-page review.','All authorial, institutional, later-editorial and electronic-transcriber interventions must remain separate.']}
 jwrite('coverage.json',report);jlines('works.jsonl',works);jwrite('reviewed-evidence.json',evidence);jlines('input-receipts.jsonl',input_receipts);jlines('text-layer-gaps.jsonl',empty_pages)
 table=['# 全《毛选》逐篇梳理总表','','229篇正文与1篇附录分别计数；下表全部有基线定位与跨库检索结果。未复核列不等于未修改。','', '| ID | 卷 | 篇名 | 日期标签 | 全库候选 | 复核陈述 | 当前结论 |','|---|---:|---|---|---:|---:|---|']
 for wid,v,typ,title,date,n,ne,status,abstract in summary_rows:table.append(f"| [{wid}](articles/{wid}.md) | {v} | {title}{'〔附录〕' if typ=='appendix' else ''} | {date} | {n} | {ne} | {abstract.replace('|','／')} |")
 write('all-works.md','\n'.join(table)+'\n')
 with (OUT/'all-works.tsv').open('w',encoding='utf-8',newline='') as f:
  cw=csv.writer(f,delimiter='\t');cw.writerow(['id','volume','entry_type','title','date_label','candidate_count','reviewed_statements','status','first_pass_summary']);cw.writerows(summary_rows)
 checks={'registry_main_count':sum(w['entry_type']=='main_work' for w in works)==229,'one_appendix':sum(w['entry_type']=='appendix' for w in works)==1,'unique_ids':len(workby)==len(works),'all_baselines_nonempty':all(w['baseline_text_chars']>0 for w in works),'all_title_starts_checked':all(w['title_start_checked'] for w in works),'all_cards_and_mapping_files_written':all((OUT/('articles/'+w['id']+'.md')).exists() and (OUT/('mappings/'+w['id']+'.jsonl')).exists() for w in works),'evidence_has_sources':all(e['sources'] for e in evidence),'no_auto_manuscript_authentication':report['new_manuscripts_authenticated']==0,'fifth_alternate_not_double_counted':not any(w['title']=='讲话稿 按此' for w in works),'text_matches_are_retained':sum(c['id'].startswith('C-') for c in candidates)>len(works),'each_baseline_has_title_candidate':all(any(c['witness_id']==w['baseline']['witness_id'] and c['id'].startswith('C-') for c in grouped[w['id']]) for w in works)}
 jwrite('validation.json',{'checks':checks,'passed':all(checks.values())});assert all(checks.values()),checks
 print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':build()
