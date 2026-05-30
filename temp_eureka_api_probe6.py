import urllib.request
import json

base = 'https://eureka.mf.gov.pl/api/public/v1'

def api_post(path, body):
    url = base + path
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'pl-PL,pl;q=0.9,en;q=0.8',
        'Referer': 'https://eureka.mf.gov.pl/',
        'Origin': 'https://eureka.mf.gov.pl',
        'Content-Type': 'application/json',
    }
    data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read().decode('utf-8'))

# Test basic search
print("=== BASIC SEARCH ===")
body = {
    "filter": {},
    "columns": ["KATEGORIA_INFORMACJI", "SYG", "DT_WYD", "AUTOR", "ID_INFORMACJI", "TEZA", "SLOWA_KLUCZOWE", "PRZEPISY", "ZAGADNIENIA", "STATUS_INFORMACJI"],
    "searchInFullPhrase": True,
    "searchInContent": False,
    "searchInSynonyms": False,
    "searchQuery": "",
    "warunkiDodatkowe": []
}

try:
    results = api_post('/wyszukiwarka/informacje/?size=5&page=0&sort=parametryPozycjonowania,asc', body)
    print(f"Total hits: {results.get('totalHits')}")
    print(f"Results: {len(results.get('results', []))}")
    if results.get('results'):
        r = results['results'][0]
        print(f"First: SYG={r.get('SYG')}, DT_WYD={r.get('DT_WYD')}, ID={r.get('ID_INFORMACJI')}")
except Exception as e:
    print(f"Error: {e}")

# Test with date filter
print("\n=== SEARCH WITH DATE FILTER ===")
body2 = {
    "filter": {
        "DT_WYD": {"od": "2024-01-01T00:00:00.000Z", "do": "2024-12-31T23:59:59.999Z"}
    },
    "columns": ["KATEGORIA_INFORMACJI", "SYG", "DT_WYD", "AUTOR", "ID_INFORMACJI", "TEZA", "SLOWA_KLUCZOWE", "PRZEPISY", "ZAGADNIENIA", "STATUS_INFORMACJI"],
    "searchInFullPhrase": True,
    "searchInContent": False,
    "searchInSynonyms": False,
    "searchQuery": "",
    "warunkiDodatkowe": []
}

try:
    results = api_post('/wyszukiwarka/informacje/?size=5&page=0&sort=parametryPozycjonowania,asc', body2)
    print(f"Total hits: {results.get('totalHits')}")
    print(f"Results: {len(results.get('results', []))}")
except Exception as e:
    print(f"Error: {e}")

# Test with different date format
print("\n=== SEARCH WITH DATE FILTER (alt format) ===")
body3 = {
    "filter": {
        "DT_WYD": {"od": "2024-01-01", "do": "2024-12-31"}
    },
    "columns": ["KATEGORIA_INFORMACJI", "SYG", "DT_WYD", "AUTOR", "ID_INFORMACJI", "TEZA", "SLOWA_KLUCZOWE", "PRZEPISY", "ZAGADNIENIA", "STATUS_INFORMACJI"],
    "searchInFullPhrase": True,
    "searchInContent": False,
    "searchInSynonyms": False,
    "searchQuery": "",
    "warunkiDodatkowe": []
}

try:
    results = api_post('/wyszukiwarka/informacje/?size=5&page=0&sort=parametryPozycjonowania,asc', body3)
    print(f"Total hits: {results.get('totalHits')}")
    print(f"Results: {len(results.get('results', []))}")
except Exception as e:
    print(f"Error: {e}")
