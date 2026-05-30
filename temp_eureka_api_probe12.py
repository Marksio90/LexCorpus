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

# Test search with year in query
for year in [2026, 2025, 2024, 2023, 2022]:
    body = {
        "filter": {},
        "columns": ["SYG", "DT_WYD", "DATA_PUBLIKACJI", "ID_INFORMACJI", "TEZA"],
        "searchInFullPhrase": True,
        "searchInContent": False,
        "searchInSynonyms": False,
        "searchQuery": str(year),
        "warunkiDodatkowe": []
    }
    try:
        results = api_post('/wyszukiwarka/informacje/?size=1&page=0&sort=DATA_PUBLIKACJI,desc', body)
        print(f"Year {year}: total={results.get('totalHits')}")
    except Exception as e:
        print(f"Year {year}: ERROR {e}")

# Test with searchInContent=True
print("\n=== searchInContent=True ===")
for year in [2026, 2024]:
    body = {
        "filter": {},
        "columns": ["SYG", "DT_WYD", "DATA_PUBLIKACJI", "ID_INFORMACJI", "TEZA"],
        "searchInFullPhrase": False,
        "searchInContent": True,
        "searchInSynonyms": False,
        "searchQuery": str(year),
        "warunkiDodatkowe": []
    }
    try:
        results = api_post('/wyszukiwarka/informacje/?size=1&page=0&sort=DATA_PUBLIKACJI,desc', body)
        print(f"Year {year} (content): total={results.get('totalHits')}")
    except Exception as e:
        print(f"Year {year} (content): ERROR {e}")
