import urllib.request
import json
import urllib.parse

base = 'https://eureka.mf.gov.pl/api/public/v1'

def api_get(path, params=None):
    url = base + path
    if params:
        url += '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
        'Referer': 'https://eureka.mf.gov.pl/',
    })
    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read().decode('utf-8'))

# 1. Get search parameters
print("=== PARAMETRY WYSZUKIWARKI ===")
try:
    params = api_get('/parametry-wyszukiwarki/all')
    for p in params[:5]:
        print(f"  {p.get('id')}: {p.get('etykieta')} ({p.get('metadane',{}).get('kod','')})")
except Exception as e:
    print(f"Error: {e}")

# 2. Search for interpretations
print("\n=== WYSZUKIWANIE INTERPRETACJI ===")
try:
    # Try with query parameter
    search_params = {
        'size': 5,
        'page': 0,
        'sort': 'parametryPozycjonowania,asc',
    }
    results = api_get('/wyszukiwarka/informacje/', search_params)
    print(f"Total results: {results.get('totalHits', 'N/A')}")
    print(f"Results count: {len(results.get('results', []))}")
    
    if results.get('results'):
        first = results['results'][0]
        print(f"\nFirst result keys: {list(first.keys())}")
        print(f"SYG: {first.get('SYG')}")
        print(f"ID: {first.get('ID_INFORMACJI')}")
        print(f"STATUS: {first.get('STATUS_INFORMACJI')}")
        print(f"DT_WYD: {first.get('DT_WYD')}")
        print(f"AUTOR: {first.get('AUTOR')}")
        print(f"ZAGADNIENIA: {first.get('ZAGADNIENIA', [])[:2]}")
        
        # Try to get full detail
        info_id = first.get('ID_INFORMACJI')
        if info_id:
            print(f"\n=== DETAIL FOR ID {info_id} ===")
            try:
                detail = api_get(f'/informacje/{info_id}')
                print(f"Detail keys: {list(detail.keys())[:20]}")
                if 'TRESC' in detail:
                    print(f"TRESC preview: {str(detail['TRESC'])[:300]}")
            except Exception as e:
                print(f"Detail error: {e}")
except Exception as e:
    print(f"Search error: {e}")

# 3. Try search with date filter
print("\n=== WYSZUKIWANIE Z FILTREM DATY ===")
try:
    # Try POST search with body
    url = base + '/wyszukiwarka/informacje/'
    body = {
        'fraza': '',
        'size': 5,
        'page': 0,
        'sort': 'parametryPozycjonowania,asc',
        'filtry': {
            'DT_WYD': {'od': '2024-01-01', 'do': '2024-12-31'}
        }
    }
    data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={
        'User-Agent': 'Mozilla/5.0',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Referer': 'https://eureka.mf.gov.pl/',
    }, method='POST')
    resp = urllib.request.urlopen(req, timeout=15)
    results = json.loads(resp.read().decode('utf-8'))
    print(f"POST results count: {len(results.get('results', []))}")
except Exception as e:
    print(f"POST search error: {e}")
