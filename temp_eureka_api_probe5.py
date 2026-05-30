import urllib.request
import json
import urllib.parse

base = 'https://eureka.mf.gov.pl/api/public/v1'

def api_call(method, path, params=None, body=None, extra_headers=None):
    url = base + path
    if params:
        url += '?' + urllib.parse.urlencode(params)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'pl-PL,pl;q=0.9,en;q=0.8',
        'Referer': 'https://eureka.mf.gov.pl/',
        'Origin': 'https://eureka.mf.gov.pl',
    }
    if extra_headers:
        headers.update(extra_headers)
    
    if body:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    else:
        data = None
    
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read().decode('utf-8'))

# Try GET with X-Requested-With
print("=== GET with X-Requested-With ===")
try:
    results = api_call('GET', '/wyszukiwarka/informacje/', 
        params={'size': 5, 'page': 0, 'sort': 'parametryPozycjonowania,asc'},
        extra_headers={'X-Requested-With': 'XMLHttpRequest'})
    print(f"Results: {len(results.get('results', []))}")
except Exception as e:
    print(f"Error: {e}")

# Try POST with the exact body that browser might send
print("\n=== POST with search body ===")
try:
    # Based on EUREKA's search interface, try different body formats
    bodies = [
        {'fraza': 'VAT', 'size': 5, 'page': 0},
        {'query': 'VAT', 'size': 5, 'page': 0},
        {'searchText': 'VAT', 'size': 5, 'page': 0},
        {'fraza': '', 'size': 5, 'page': 0, 'sort': 'parametryPozycjonowania,asc'},
        {'size': 5, 'page': 0, 'sort': 'parametryPozycjonowania,asc'},
        {},
    ]
    for i, body in enumerate(bodies):
        try:
            results = api_call('POST', '/wyszukiwarka/informacje/', body=body)
            print(f"Body {i} ({body}): SUCCESS - {len(results.get('results', []))} results")
            break
        except Exception as e:
            print(f"Body {i} ({body}): {e}")
except Exception as e:
    print(f"Error: {e}")

# Try POST to /wyszukiwarka with different paths
print("\n=== POST to different paths ===")
for path in ['/wyszukiwarka', '/wyszukiwarka/informacje', '/wyszukiwarka/informacje/']:
    try:
        results = api_call('POST', path, body={'size': 5, 'page': 0})
        print(f"POST {path}: SUCCESS")
    except Exception as e:
        print(f"POST {path}: {e}")
