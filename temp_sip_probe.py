import urllib.request
import json

base = 'https://sip.mf.gov.pl'

# Try common API patterns
paths = [
    '/api/interpretacja/szukaj',
    '/api/interpretacje',
    '/api/search',
    '/rest/interpretacje',
    '/ws/interpretacje',
    '/api/v1/interpretacje',
    '/api/public/v1/interpretacje',
]

for p in paths:
    url = base + p
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
        resp = urllib.request.urlopen(req, timeout=10)
        body = resp.read().decode('utf-8', errors='replace')
        print(f'GET {url} -> {resp.status}')
        print(body[:300])
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')[:100]
        print(f'GET {url} -> HTTP {e.code}: {body}')
    except Exception as e:
        print(f'GET {url} -> {type(e).__name__}: {e}')
    print()
