import urllib.request

base = 'https://eureka.mf.gov.pl'
paths = [
    '/swagger-ui.html',
    '/swagger-ui/',
    '/v3/api-docs',
    '/v2/api-docs',
    '/api-docs',
    '/api/public/v1/api-docs',
    '/actuator',
    '/actuator/health',
    '/api/public/v1/actuator',
    '/openapi.json',
    '/api/public/v1/openapi.json',
]

for p in paths:
    url = base + p
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json,text/html'})
        resp = urllib.request.urlopen(req, timeout=10)
        body = resp.read().decode('utf-8', errors='replace')
        print(f'{url} -> {resp.status}')
        print(body[:300])
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')[:100]
        print(f'{url} -> HTTP {e.code}')
    except Exception as e:
        print(f'{url} -> {type(e).__name__}')
    print()
