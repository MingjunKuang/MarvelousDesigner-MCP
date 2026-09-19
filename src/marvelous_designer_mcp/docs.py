"""Small, offline Sphinx documentation index using SQLite FTS5/BM25."""
from __future__ import annotations

from datetime import datetime, timezone
from contextlib import closing
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sqlite3

from .paths import DATA_DIR
DEFAULT_DB = DATA_DIR / 'docs' / 'md-docs.sqlite3'
BASE = 'https://developer.marvelousdesigner.com/'
MODULES = {'export-api', 'import-api', 'pattern-api', 'fabric-api', 'utility-api', 'rest-api'}


class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def text(self):
        return ''.join(c.text() if isinstance(c, Node) else c for c in self.children)

    def walk(self, tag=None):
        if tag is None or self.tag == tag:
            yield self
        for c in self.children:
            if isinstance(c, Node):
                yield from c.walk(tag)


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs)
        self.stack[-1].children.append(n)
        if tag not in {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}:
            self.stack.append(n)

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse_page(html, page, fetched_at):
    doc = Document(html).root
    title = next((n.text() for n in doc.walk('title')), '')
    version = re.search(r'API ([\d.]+) documentation', title)
    records = {}
    for section in doc.walk('section'):
        anchor = section.attrs.get('id', '')
        if page == 'list.html' and anchor in MODULES:
            module = anchor.replace('-', '_')
            for pre in section.walk('pre'):
                block = pre.text().strip()
                match = re.match(r'def\s+(\w+)\s*\(', block)
                if not match:
                    continue
                function = match[1]
                key = module + '.' + function
                entry = records.setdefault(key, dict(id=key, kind='api', module=module,
                    function=function, signature=[], overloads=[], examples=[],
                    source_url=BASE+page+'#'+anchor, fetched_at=fetched_at,
                    docs_version=version[1] if version else None))
                sig, _, body = block.partition('\n')
                entry['signature'].append(sig)
                entry['overloads'].append({'signature':sig, 'documentation':body.strip().strip('"').strip()})
        elif page == 'scenario.html' and anchor.lower() in {'pattern','simulation','animation','substance'}:
            code = [p.text().strip() for p in section.walk('pre')]
            key = 'scenario.' + anchor.title()
            records[key] = dict(id=key, kind='scenario', module='scenario', function=anchor.title(),
                signature=[], overloads=[], examples=code, text=section.text().strip(),
                source_url=BASE+page+'#'+anchor, fetched_at=fetched_at, docs_version=version[1] if version else None)
        elif page == 'optiontype.html' and anchor and anchor not in {'apitypes','api-types'}:
            key = 'ApiTypes.' + anchor
            records[key] = dict(id=key, kind='type', module='ApiTypes', function=anchor,
                signature=[], overloads=[], examples=[p.text() for p in section.walk('pre')],
                text=section.text().strip(), source_url=BASE+page+'#'+anchor,
                fetched_at=fetched_at, docs_version=version[1] if version else None)
    if page in {'python.html','register.html','changelog.html','index.html'}:
        main = next((n for n in doc.walk() if n.attrs.get('role')=='main'), doc)
        key = 'guide.' + page.removesuffix('.html')
        records[key] = dict(id=key, kind='guide', module='guide', function=key[6:], signature=[],
            overloads=[], examples=[], text=main.text().strip(), source_url=BASE+page,
            fetched_at=fetched_at, docs_version=version[1] if version else None)
    for entry in records.values():
        if 'text' not in entry:
            entry['text'] = '\n\n'.join(o['signature']+'\n'+o['documentation'] for o in entry['overloads'])
        brief = re.search(r'@brief\s+([^\n]+)', entry['text'])
        entry['description'] = brief[1].strip() if brief else entry['text'][:240]
        entry['parameters'] = [v.strip() for v in re.findall(r'@(?:param|parm)\s+(.+?)(?=\n\s*@|\n\ndef |\Z)', entry['text'], re.S)]
        entry['return_value'] = re.findall(r'@return\s+([^\n]+)', entry['text'])
    return list(records.values())


def build_index(cache, db=DEFAULT_DB):
    cache, db = Path(cache), Path(db)
    rows = []
    for file in sorted(cache.glob('*.html')):
        stamp = datetime.fromtimestamp(file.stat().st_mtime, timezone.utc).isoformat()
        rows.extend(parse_page(file.read_text(encoding='utf-8'), file.name, stamp))
    if not any(r['kind']=='api' for r in rows) or not any(r['kind']=='scenario' for r in rows):
        raise ValueError('No API/scenario entries parsed; keep previous index')
    changes = next((r['text'] for r in rows if r['id']=='guide.changelog'), '')
    versions = re.findall(r'MD (\d+\.\d+\.\d+)', changes)
    for r in rows:
        r['changelog'] = [line.strip() for line in changes.splitlines() if re.search(r'\b'+re.escape(r['function'])+r'\b',line) and r['kind']=='api']
        r['examples'] += [s['text'] for s in rows if s['kind']=='scenario' and r['kind']=='api' and r['module']+'.'+r['function']+'(' in s['text']]
    db.parent.mkdir(parents=True, exist_ok=True)
    temp = db.with_suffix('.building.sqlite3')
    with closing(sqlite3.connect(temp)) as conn:
        conn.executescript('DROP TABLE IF EXISTS docs; DROP TABLE IF EXISTS search; DROP TABLE IF EXISTS metadata; CREATE TABLE docs(id TEXT PRIMARY KEY, kind TEXT, payload TEXT); CREATE VIRTUAL TABLE search USING fts5(id, name, text, tokenize="porter unicode61"); CREATE TABLE metadata(payload TEXT);')
        for r in rows:
            conn.execute('INSERT INTO docs VALUES(?,?,?)', (r['id'],r['kind'],json.dumps(r,ensure_ascii=False)))
            words = re.sub(r'([a-z])([A-Z])',r'\1 \2',r['function'])
            conn.execute('INSERT INTO search VALUES(?,?,?)',(r['id'],r['id']+' '+words,r['text']))
        meta = dict(schema_version=1, updated_at=datetime.now(timezone.utc).isoformat(),
            entry_count=len(rows), latest_changelog_version=versions[0] if versions else None,
            source=BASE, docs_version=rows[0].get('docs_version'))
        conn.execute('INSERT INTO metadata VALUES(?)',(json.dumps(meta),))
        conn.commit()
    os.replace(temp, db)
    return meta


class DocsIndex:
    def __init__(self, path=None):
        self.path = Path(path or os.environ.get('MD_MCP_DOCS_DB', DEFAULT_DB))

    def connect(self):
        if not self.path.is_file():
            raise FileNotFoundError('Docs index missing. Run md-mcp update-docs to build your local official documentation index.')
        return sqlite3.connect(self.path.as_uri()+'?mode=ro', uri=True)

    def metadata(self):
        with closing(self.connect()) as c:
            return json.loads(c.execute('SELECT payload FROM metadata').fetchone()[0])

    def get(self, name, kind=None):
        name = name.strip().removesuffix('()').replace('::','.')
        with closing(self.connect()) as c:
            rows = c.execute('SELECT payload FROM docs WHERE lower(id)=lower(?) OR lower(id) LIKE lower(?)', (name,'%.'+name)).fetchall()
            found = [json.loads(r[0]) for r in rows]
        if kind:
            found = [r for r in found if r['kind']==kind]
        if len(found)!=1:
            return {'ok':False,'error':{'code':'doc_not_found' if not found else 'ambiguous_api','matches':[r['id'] for r in found]}}
        return {'ok':True, 'result':found[0]}

    def search(self, query, limit=10, kind=None):
        if not 1 <= limit <= 50:
            raise ValueError('limit must be between 1 and 50')
        terms = re.findall(r'\w+', re.sub(r'([a-z])([A-Z])',r'\1 \2',query))
        terms = [t for t in terms if t.lower() not in {'a','an','the','to','of','and','or','between','two','api'}]
        if not terms:
            return []
        # Quoted OR terms safely support natural-language searches and FTS punctuation.
        expanded=list(terms)
        if any(t.lower()=='sewing' for t in terms): expanded += ['seamline','stitching']
        if any(t.lower()=='create' for t in terms): expanded += ['add']
        match = ' OR '.join('"'+t+'"' for t in expanded)
        with closing(self.connect()) as c:
            rows = c.execute('SELECT d.payload,bm25(search,2,5,1) score FROM search JOIN docs d ON d.id=search.id WHERE search MATCH ? AND (? IS NULL OR d.kind=?) ORDER BY score LIMIT 200', (match,kind,kind)).fetchall()
        result=[]
        for payload, score in rows:
            r=json.loads(payload)
            relevance=-score
            if 'create' in [t.lower() for t in terms] and r['function'].startswith(('Create','Add')):
                relevance += 5
            if 'sewing' in [t.lower() for t in terms] and r['function']=='AddSeamlinePairGroup':
                relevance += 10
            result.append({k:r[k] for k in ['id','module','function','signature','description','source_url']} | {'relevance':relevance})
        return sorted(result,key=lambda r:r['relevance'],reverse=True)[:limit]
