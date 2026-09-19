"""Fetch official documentation for personal local indexing, not redistribution."""
import os
import time
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request
from .docs import BASE, DEFAULT_DB, build_index
from .paths import DATA_DIR


class OfficialRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).hostname != 'developer.marvelousdesigner.com' or urlsplit(newurl).scheme != 'https':
            raise ValueError('Refusing off-domain redirect')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def update(offline=False):
    cache = DATA_DIR / 'docs' / 'html'
    cache.mkdir(parents=True, exist_ok=True)
    if not offline:
        opener = build_opener(OfficialRedirect())
        for page in ['index', 'list', 'optiontype', 'scenario', 'python', 'register', 'changelog']:
            request = Request(BASE + page + '.html', headers={'User-Agent': 'MD-MCP-Docs/1.0 (local documentation index)'})
            with opener.open(request, timeout=30) as response:
                data = response.read(16 * 1024 * 1024 + 1)
            if len(data) > 16 * 1024 * 1024:
                raise ValueError('Documentation page too large')
            (cache / (page + '.html')).write_bytes(data)
            time.sleep(1)
    return build_index(cache, os.environ.get('MD_MCP_DOCS_DB', DEFAULT_DB))
