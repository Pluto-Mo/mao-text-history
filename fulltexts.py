#!/usr/bin/env python3
"""Persist reviewed public-document bodies; never mirror a whole source or book.
Python 3.10+. Only the explicit rights/fulltext-allowlist.json URLs are fetched.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit, urldefrag
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
POLICY = 'rights/fulltext-allowlist.json'
UA = 'MaoTextHistoryResearch/2.0 (+https://github.com/Pluto-Mo/mao-text-history)'
HOSTS = {'www.marxists.org', 'marxists.org', 'zh.wikisource.org'}
LIMIT = 4 * 1024 * 1024


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_json(path: str):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def read_rows(path: str) -> list[dict]:
    file = ROOT / path
    return [json.loads(x) for x in file.read_text(encoding='utf-8').splitlines() if x.strip()] if file.exists() else []


def write_json(path: str, value) -> None:
    file = ROOT / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_rows(path: str, values: list[dict]) -> None:
    file = ROOT / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in values), encoding='utf-8')


def safe_url(url: str) -> bool:
    try:
        p = urlsplit(url)
        return p.scheme == 'https' and p.hostname in HOSTS and p.port in (None, 443) and not p.username and not p.password
    except ValueError:
        return False


class Redirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not safe_url(newurl) or urlsplit(newurl).hostname != urlsplit(req.full_url).hostname:
            raise ValueError('cross-host or unsafe redirect refused')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Fetcher:
    def __init__(self):
        self.opener = build_opener(Redirect())
        self.robots: dict = {}
        self.last: dict = {}

    def request(self, url: str) -> tuple[bytes, dict]:
        if not safe_url(url):
            raise ValueError('source URL not allowed')
        host = urlsplit(url).hostname
        time.sleep(max(0, 1.0 - (time.monotonic() - self.last.get(host, 0))))
        self.last[host] = time.monotonic()
        encoded = quote(url, safe=":/?=&%#+@,;()")
        with self.opener.open(Request(encoded, headers={'User-Agent': UA, 'Accept': 'text/html,text/plain'}), timeout=25) as response:
            ct = response.headers.get_content_type()
            if ct not in ('text/html', 'application/xhtml+xml', 'text/plain'):
                raise ValueError('not HTML/text')
            raw = response.read(LIMIT + 1)
            if len(raw) > LIMIT:
                raise ValueError('response too large')
            return raw, {'final_url': response.geturl(), 'content_type': ct,
                         'http_charset': response.headers.get_content_charset(), 'http_status': response.status}

    def get(self, url: str) -> tuple[bytes, dict]:
        p = urlsplit(url)
        origin = f'{p.scheme}://{p.netloc}'
        if origin not in self.robots:
            rp = RobotFileParser(origin + '/robots.txt')
            try:
                raw, _ = self.request(origin + '/robots.txt')
                rp.parse(raw.decode('utf-8', errors='strict').splitlines())
            except HTTPError as exc:
                if exc.code != 404:
                    raise ValueError(f'robots unavailable: HTTP {exc.code}') from exc
                rp.parse([])
            self.robots[origin] = rp
        if not self.robots[origin].can_fetch(UA, quote(url, safe=':/?=&%')):
            raise ValueError('robots disallows request')
        return self.request(url)


def compact(text: str) -> str:
    return ''.join(c for c in text if not c.isspace())


def decode_html(raw: bytes, declared: str | None = None) -> tuple[str, str]:
    """Do not accept permissive Latin-1 decoding of legacy Chinese pages."""
    candidates = ['utf-8-sig']
    header = raw[:4096].decode('ascii', errors='ignore')
    match = re.search(r'charset\s*=\s*[\"\x27]?([\w-]+)', header, re.I)
    hint = (declared or (match.group(1) if match else '')).lower()
    if hint in ('big5', 'big5-hkscs'):
        candidates += ['big5hkscs']
    candidates += ['gb18030']
    for enc in dict.fromkeys(candidates):
        try:
            text = raw.decode(enc, errors='strict')
            if '\ufffd' in text:
                raise ValueError('source contains replacement characters')
            return text, enc
        except UnicodeDecodeError:
            continue
    raise ValueError('no strict supported Chinese encoding')


def check_spec(spec: dict) -> None:
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{2,100}', spec['id']):
        raise ValueError('unsafe document id')
    if spec.get('approval') != 'reviewed_official_document_body' or not spec.get('rights_references'):
        raise ValueError('document body has not been reviewed')
    if not safe_url(spec['url']):
        raise ValueError('unapproved source host')
    if spec.get('completeness') not in ('available_web_body', 'source_explicit_excerpt'):
        raise ValueError('missing source completeness declaration')
    for key in ('start', 'end', 'title', 'work_id', 'agency', 'historical_date'):
        if not isinstance(spec.get(key), str) or not spec[key].strip():
            raise ValueError(f'missing {key}')


def extract_body(raw: bytes, spec: dict, declared: str | None = None) -> tuple[str, dict]:
    check_spec(spec)
    html, encoding = decode_html(raw, declared)
    soup = BeautifulSoup(html, 'html.parser')
    for bad in soup(['script', 'style', 'noscript']):
        bad.decompose()
    page = soup.get_text('\n', strip=True)
    if any(x in page[:1500].lower() for x in ('access denied', 'checking your browser', 'just a moment')):
        raise ValueError('blocked or challenge page')
    indices = [i for i, c in enumerate(page) if not c.isspace()]
    joined = ''.join(page[i] for i in indices)
    start, end = compact(spec['start']), compact(spec['end'])
    if joined.count(start) != 1:
        raise ValueError('start boundary absent or ambiguous')
    first = joined.index(start)
    last = joined.find(end, first + len(start))
    if last < 0 or joined.find(end, last + len(end)) >= 0:
        raise ValueError('end boundary absent or ambiguous after start')
    stop = last + len(end)
    piece = page[indices[first]:indices[stop - 1] + 1]
    body = '\n'.join(x.strip() for x in piece.splitlines() if x.strip()) + '\n'
    if compact(body) != joined[first:stop]:
        raise ValueError('non-whitespace text changed during extraction')
    n = len(compact(body))
    if not spec.get('min_chars', 100) <= n <= spec.get('max_chars', 20000):
        raise ValueError(f'unexpected body length {n}')
    for forbidden in spec.get('excluded_markers', []):
        if forbidden in body:
            raise ValueError('editorial/navigation material crossed body boundary')
    return body, {'encoding': encoding, 'html_title': soup.title.get_text(' ', strip=True) if soup.title else None,
                  'source_text_start_index': indices[first], 'source_text_end_index_exclusive': indices[stop - 1] + 1,
                  'non_whitespace_characters': n, 'extraction_version': 1,
                  'transformations': ['HTML entities decoded by parser', 'script/style/noscript excluded',
                                      'reviewed inclusive body boundaries applied', 'blank lines/line-edge whitespace removed'],
                  'spelling_corrected': False, 'traditional_simplified_conversion': False,
                  'locator_note': 'Indices address parser text, NOT raw HTML bytes or printed book pages.'}


def collect() -> int:
    policy = read_json(POLICY)
    specs = policy['documents']
    if len({x['id'] for x in specs}) != len(specs):
        raise ValueError('duplicate document id')
    for spec in specs:
        check_spec(spec)
    # Existing successful witnesses survive a subsequent failed network request.
    manifests = {x['id']: x for x in read_rows('fulltext/manifest.jsonl')}
    entries = read_rows('catalog/entries.jsonl')
    fetcher = Fetcher()
    failures, attempts = [], []
    for spec in specs:
        stamp = datetime.now(timezone.utc).isoformat()
        try:
            raw, receipt = fetcher.get(spec['url'])
            body, extraction = extract_body(raw, spec, receipt.get('http_charset'))
            sha = digest(body.encode('utf-8'))
            path = f"fulltext/snapshots/{spec['id']}/{sha}.txt"
            file = ROOT / path
            file.parent.mkdir(parents=True, exist_ok=True)
            if file.exists() and file.read_bytes() != body.encode('utf-8'):
                raise ValueError('content-addressed snapshot collision')
            file.write_text(body, encoding='utf-8')
            matches = [e['id'] for e in entries if e.get('url') and urldefrag(e['url'])[0] == urldefrag(spec['url'])[0]]
            record = {**spec, **receipt, **extraction, 'retrieved_at': stamp, 'body_path': path,
                      'body_sha256': sha, 'body_byte_count': len(body.encode('utf-8')),
                      'raw_sha256': digest(raw), 'raw_byte_count': len(raw),
                      'raw_html_retained': False, 'official_body_retained': True,
                      'complete_original_verified': False, 'archival_authenticity_verified': False,
                      'catalogue_entry_ids': matches, 'catalogue_mapping_basis': 'exact_source_url_only'}
            manifests[spec['id']] = record
            write_json(f"fulltext/provenance/{spec['id']}.json", record)
            md = [f"# {spec['title']}", '', f"文献日期：{spec['historical_date']}；发布机关：{spec['agency']}。",
                  '', f"来源：[{spec['source_label']}]({spec['url']})。", '',
                  f"底本说明：{spec['edition_note']}", '',
                  '**收录边界：' + ('原网页明确标为节录；不是原文件全文。' if spec['completeness'] == 'source_explicit_excerpt' else '保存该网页可见的公文正文；不等于认证原件全文。') + '**',
                  '', spec['limitations'], '',
                  f"[精确文本快照](../snapshots/{spec['id']}/{sha}.txt) · [来源与校验值](../provenance/{spec['id']}.json)",
                  '', '---', '', body.rstrip(), '']
            dest = ROOT / f"fulltext/documents/{spec['id']}.md"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text('\n'.join(md), encoding='utf-8')
            attempts.append({'id': spec['id'], 'status': 'stored', 'retrieved_at': stamp, 'body_sha256': sha})
            print(spec['id'], 'stored', n if (n := extraction['non_whitespace_characters']) else 0, flush=True)
        except Exception as exc:
            error = {'id': spec['id'], 'url': spec['url'], 'attempted_at': stamp,
                     'status': 'failed', 'error': f'{type(exc).__name__}: {exc}'[:500]}
            failures.append(error)
            attempts.append(error)
            print(spec['id'], error['error'], flush=True)
    allowed = {s['id'] for s in specs}
    values = sorted((m for k, m in manifests.items() if k in allowed), key=lambda x: (x['historical_date'], x['id']))
    write_rows('fulltext/manifest.jsonl', values)
    segments, mappings = [], []
    groups = defaultdict(list)
    for m in values:
        body = (ROOT / m['body_path']).read_text(encoding='utf-8')
        for i, line in enumerate(body.splitlines(), 1):
            segments.append({'id': f"{m['id']}:{m['body_sha256'][:16]}:L{i:04d}", 'document_id': m['id'],
                             'body_sha256': m['body_sha256'], 'line': i, 'text': line,
                             'segment_sha256': digest(line.encode()), 'locator_kind': 'generated_text_line_not_printed_paragraph'})
        mappings.append({'document_id': m['id'], 'url': m['url'], 'catalogue_entry_ids': m['catalogue_entry_ids'],
                         'basis': 'exact_source_url_only', 'is_historical_revision_edge': False})
        groups[m['work_id']].append(m['id'])
    pairs = [{'work_id': k, 'members': v, 'relation': 'parallel_web_witness_candidate',
              'basis': 'reviewed document identity/date/agency; not proof of same printed edition',
              'is_historical_revision_edge': False} for k, v in sorted(groups.items()) if len(v) > 1]
    write_rows('fulltext/segments.jsonl', segments)
    write_rows('fulltext/mappings.jsonl', mappings)
    write_rows('fulltext/parallel-witnesses.jsonl', pairs)
    write_json('reports/fulltext-attempts.json', attempts)
    write_json('reports/fulltext-failures.json', failures)
    report = {'generated_at': datetime.now(timezone.utc).isoformat(), 'approved_targets': len(specs),
              'persisted_web_bodies': len(values), 'distinct_work_ids': len(groups),
              'source_explicit_excerpts': sum(m['completeness'] == 'source_explicit_excerpt' for m in values),
              'available_web_bodies_not_explicitly_excerpted': sum(m['completeness'] == 'available_web_body' for m in values),
              'non_whitespace_characters_across_witnesses': sum(m['non_whitespace_characters'] for m in values),
              'generated_text_lines': len(segments), 'parallel_witness_groups': len(pairs),
              'failed_this_attempt': len(failures), 'confirmed_original_full_documents': 0,
              'complete_book_volumes': 0, 'four_complete_collections': False,
              'rights_scope': 'individually reviewed official-document bodies, not source-wide or book-wide permission',
              'source_counts': dict(Counter(m['source_label'] for m in values)), 'pending_collections': policy['pending_collections']}
    write_json('reports/fulltext-coverage.json', report)
    lines = ['# 全文正文入库验收', '', f"生成时间：{report['generated_at']}", '',
             f"实际保存 {len(values)} 个网页正文见证本，涉及 {len(groups)} 份公文；其中 {report['source_explicit_excerpts']} 个网页明确为节录。",
             f"非空白字符总计 {report['non_whitespace_characters_across_witnesses']}（不同见证本重复计入，不能当作去重作品字数）。",
             '', '**完整原书卷册：0。四套资料仍未全文收齐。没有把网站正文认证为档案原件。**', '',
             '| 文本 | 日期 | 来源 | 收录状态 |', '|---|---|---|---|']
    for m in values:
        status = '来源明确节录' if m['completeness'] == 'source_explicit_excerpt' else '可见公文正文已保存'
        lines.append(f"| [{m['title']}](../fulltext/documents/{m['id']}.md) | {m['historical_date']} | {m['source_label']} | {status} |")
    lines += ['', '## 查阅和比较', '', '`python fulltexts.py search 金门`', '',
              '`python fulltexts.py read mia-1958-1006`', '',
              '`python fulltexts.py compare mia-1958-1006 ws-1958-1006`', '',
              'compare 仅显示网页见证本文字差异；不声称这是作者改稿，也不自动推断政治动机。', '',
              '## 来源及权利', '', '逐篇依据在 `rights/fulltext-allowlist.json`。正文以UTF-8快照长期保存；整页HTML不随仓库分发。',
              '原网页的现代导言、题注、版权模板和导航不属于本次复制范围。纸本版次和页码只有来源明示时才记录，且未声称已核原书。', '',
              f"本轮未成功：{len(failures)}；详情见 `fulltext-failures.json`。"]
    (ROOT / 'reports/fulltext-coverage.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    (ROOT / 'fulltext/README.md').write_text('# 已保存的公文正文\n\n[逐篇目录及实际覆盖](../reports/fulltext-coverage.md)。\n\n'
        'documents/ 是可读正文；snapshots/ 是按正文SHA256命名的UTF-8精确快照；provenance/ 是逐篇来源；'
        'segments.jsonl 是带行号的正文检索数据；mappings.jsonl 以原URL连接既有目录。\n\n'
        '同一历史文件的不同网页见证本不等于相邻历史稿本，网站转录中的错字不会静默更正。\n', encoding='utf-8')
    return validate()


def validate() -> int:
    specs = {s['id']: s for s in read_json(POLICY)['documents']}
    records = read_rows('fulltext/manifest.jsonl')
    errors = []
    ids = set()
    for r in records:
        try:
            if r['id'] in ids:
                raise ValueError('duplicate manifest id')
            ids.add(r['id'])
            spec = specs[r['id']]
            check_spec(spec)
            if r['url'] != spec['url'] or r['completeness'] != spec['completeness']:
                raise ValueError('provenance conflicts with reviewed policy')
            path = ROOT / r['body_path']
            if not path.resolve().is_relative_to((ROOT / 'fulltext/snapshots').resolve()):
                raise ValueError('unsafe snapshot path')
            raw = path.read_bytes()
            body = raw.decode('utf-8', errors='strict')
            if digest(raw) != r['body_sha256'] or len(raw) != r['body_byte_count']:
                raise ValueError('body digest/size mismatch')
            if not compact(body).startswith(compact(spec['start'])) or not compact(body).endswith(compact(spec['end'])):
                raise ValueError('stored boundaries changed')
            if r['complete_original_verified'] or r['archival_authenticity_verified']:
                raise ValueError('unjustified original certification')
            sidecar = read_json(f"fulltext/provenance/{r['id']}.json")
            if sidecar != r:
                raise ValueError('sidecar differs from manifest')
        except Exception as exc:
            errors.append(f"{r.get('id')}: {exc}")
    by_id = {x['id']: x for x in records}
    actual_segments = read_rows('fulltext/segments.jsonl')
    expected_segments = []
    for r in records:
        path = ROOT / r['body_path']
        if path.exists():
            for i, text in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                expected_segments.append((r['id'], i, text, digest(text.encode())))
    if [(s['document_id'], s['line'], s['text'], s['segment_sha256']) for s in actual_segments] != expected_segments:
        errors.append('segments do not exactly reconstruct stored bodies')
    for pair in read_rows('fulltext/parallel-witnesses.jsonl'):
        if pair['is_historical_revision_edge'] or any(x not in by_id for x in pair['members']):
            errors.append('invalid parallel-witness relation')
    print(json.dumps({'ok': not errors, 'persisted_web_bodies': len(records), 'errors': errors}, ensure_ascii=False))
    return 1 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('collect')
    sub.add_parser('validate')
    search = sub.add_parser('search'); search.add_argument('query')
    read = sub.add_parser('read'); read.add_argument('id')
    compare = sub.add_parser('compare'); compare.add_argument('left'); compare.add_argument('right')
    args = parser.parse_args()
    if args.command == 'collect':
        return collect()
    if args.command == 'validate':
        return validate()
    records = {r['id']: r for r in read_rows('fulltext/manifest.jsonl')}
    if args.command == 'search':
        for s in read_rows('fulltext/segments.jsonl'):
            if args.query in s['text']:
                pos = s['text'].index(args.query)
                print(json.dumps({'locator': s['id'], 'url': records[s['document_id']]['url'],
                                  'context': s['text'][max(0, pos-60):pos+len(args.query)+120]}, ensure_ascii=False))
        return 0
    keys = [args.id] if args.command == 'read' else [args.left, args.right]
    if any(k not in records for k in keys):
        print('Requested witness has not been stored; see reports/fulltext-failures.json.', file=sys.stderr)
        return 2
    if args.command == 'read':
        print((ROOT / f'fulltext/documents/{args.id}.md').read_text(encoding='utf-8'))
    else:
        print('网页见证本文字比较；不是确认的历史改稿。保留简繁体和转录差异，不解释动机。')
        left, right = [records[k] for k in keys]
        a, b = [(ROOT / r['body_path']).read_text(encoding='utf-8').splitlines(keepends=True) for r in (left, right)]
        print(''.join(difflib.unified_diff(a, b, fromfile=f"{args.left} {left['url']}", tofile=f"{args.right} {right['url']}")))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
