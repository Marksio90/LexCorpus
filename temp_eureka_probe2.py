import urllib.request
import json

base = 'https://eureka.mf.gov.pl/api/public/v1'

# Try common endpoints
endpoints = [
    '/search',
    '/interpretacje',
    '/interpretacje/szukaj',
    '/documents',
    '/documents/search',
    '/api/public/v1/search',
    '/api/public/v1/interpretacje',
]

for ep in endpoints:
    url = base + ep if not ep.startswith('/api') else 'https://eureka.mf.gov.pl' + ep
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
        })
        resp = urllib.request.urlopen(req, timeout=10)
        body = resp.read().decode('utf-8', errors='replace')
        print(f'{url} -> {resp.status}')
        print(body[:500])
        print()
    except urllib.error.HTTPError as e:
        print(f'{url} -> HTTP {e.code}: {e.reason}')
        body = e.read().decode('utf-8', errors='replace')[:200]
        if body:
            print('  Body:', body)
    except Exception as e:
        print(f'{url} -> {type(e).__name__}: {e}')
    print()
