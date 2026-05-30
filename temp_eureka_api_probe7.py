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

# Check the full structure of a search result
print("=== SEARCH RESULT STRUCTURE ===")
body = {
    "filter": {},
    "columns": ["KATEGORIA_INFORMACJI", "SYG", "DT_WYD", "AUTOR", "ID_INFORMACJI", "TEZA", "SLOWA_KLUCZOWE", "PRZEPISY", "ZAGADNIENIA", "STATUS_INFORMACJI", "TRESC_INTERESARIUSZ"],
    "searchInFullPhrase": True,
    "searchInContent": False,
    "searchInSynonyms": False,
    "searchQuery": "",
    "warunkiDodatkowe": []
}
results = api_post('/wyszukiwarka/informacje/?size=2&page=0&sort=parametryPozycjonowania,asc', body)
print(f"Total: {results.get('totalHits')}")
if results.get('results'):
    r = results['results'][0]
    print(f"Keys: {list(r.keys())}")
    for k, v in r.items():
        preview = str(v)[:150] if v is not None else 'None'
        print(f"  {k}: {preview}")

# Try filtering by KATEGORIA_INFORMACJI (1 = interpretacja indywidualna?)
print("\n=== FILTER BY KATEGORIA ===")
body2 = {
    "filter": {"KATEGORIA_INFORMACJI": ["1"]},
    "columns": ["KATEGORIA_INFORMACJI", "SYG", "DT_WYD", "AUTOR", "ID_INFORMACJI", "TEZA", "STATUS_INFORMACJI"],
    "searchInFullPhrase": True,
    "searchInContent": False,
    "searchInSynonyms": False,
    "searchQuery": "",
    "warunkiDodatkowe": []
}
results2 = api_post('/wyszukiwarka/informacje/?size=5&page=0&sort=parametryPozycjonowania,asc', body2)
print(f"Total with KATEGORIA=1: {results2.get('totalHits')}")

# Try with KATEGORIA 2, 3, etc.
for cat in ['2', '3', '4', '5']:
    body_cat = {
        "filter": {"KATEGORIA_INFORMACJI": [cat]},
        "columns": ["KATEGORIA_INFORMACJI", "SYG", "DT_WYD", "AUTOR", "ID_INFORMACJI", "TEZA"],
        "searchInFullPhrase": True,
        "searchInContent": False,
        "searchInSynonyms": False,
        "searchQuery": "",
        "warunkiDodatkowe": []
    }
    try:
        r = api_post('/wyszukiwarka/informacje/?size=1&page=0&sort=parametryPozycjonowania,asc', body_cat)
        print(f"  KATEGORIA={cat}: {r.get('totalHits')} hits")
    except Exception as e:
        print(f"  KATEGORIA={cat}: error")
