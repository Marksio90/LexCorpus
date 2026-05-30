import urllib.request
import json
import urllib.parse

base = 'https://eureka.mf.gov.pl/api/public/v1'

def api_call(method, path, params=None, body=None):
    url = base + path
    if params:
        url += '?' + urllib.parse.urlencode(params)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
        'Referer': 'https://eureka.mf.gov.pl/',
        'Origin': 'https://eureka.mf.gov.pl',
    }
    
    if body:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    else:
        data = None
    
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read().decode('utf-8'))

# Try GET with fraza parameter
print("=== GET with fraza ===")
try:
    results = api_call('GET', '/wyszukiwarka/informacje/', {
        'fraza': 'VAT',
        'size': 5,
        'page': 0,
        'sort': 'parametryPozycjonowania,asc',
    })
    print(f"Results: {len(results.get('results', []))}")
    if results.get('results'):
        print(f"First SYG: {results['results'][0].get('SYG')}")
except Exception as e:
    print(f"Error: {e}")

# Try GET without any params (like the browser did initially)
print("\n=== GET without params ===")
try:
    results = api_call('GET', '/wyszukiwarka/informacje/')
    print(f"Results: {len(results.get('results', []))}")
except Exception as e:
    print(f"Error: {e}")

# Try GET with empty query params
print("\n=== GET with empty params ===")
try:
    results = api_call('GET', '/wyszukiwarka/informacje/', {
        'size': 5,
        'page': 0,
    })
    print(f"Results: {len(results.get('results', []))}")
except Exception as e:
    print(f"Error: {e}")

# Try to get detail of a known interpretation
print("\n=== GET detail ===")
try:
    detail = api_call('GET', '/informacje/693315')
    print(f"Keys: {list(detail.keys())[:20]}")
    if 'TRESC' in detail:
        print(f"TRESC: {str(detail['TRESC'])[:300]}")
except Exception as e:
    print(f"Error: {e}")

# Try detail with different path patterns
for path in ['/informacje/693315', '/informacja/693315', '/dokument/693315', '/dokumenty/693315']:
    print(f"\n=== GET {path} ===")
    try:
        detail = api_call('GET', path)
        print(f"Success! Keys: {list(detail.keys())[:10]}")
        break
    except Exception as e:
        print(f"Error: {e}")
