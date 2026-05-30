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

# Try warunkiDodatkowe for date filtering
print("=== DATE FILTER via warunkiDodatkowe ===")
body = {
    "filter": {},
    "columns": ["SYG", "DT_WYD", "ID_INFORMACJI", "TEZA", "KATEGORIA_INFORMACJI"],
    "searchInFullPhrase": True,
    "searchInContent": False,
    "searchInSynonyms": False,
    "searchQuery": "",
    "warunkiDodatkowe": [
        {"parametr": "DT_WYD", "od": "2024-01-01T00:00:00.000Z", "do": "2024-01-31T23:59:59.999Z"}
    ]
}
try:
    results = api_post('/wyszukiwarka/informacje/?size=5&page=0&sort=parametryPozycjonowania,asc', body)
    print(f"Total: {results.get('totalHits')}")
    for r in results.get('results', [])[:3]:
        print(f"  {r.get('DT_WYD')} | {r.get('TEZA', '')[:60]}")
except Exception as e:
    print(f"Error: {e}")

# Try with different warunkiDodatkowe format
print("\n=== DATE FILTER alt format ===")
body2 = {
    "filter": {},
    "columns": ["SYG", "DT_WYD", "ID_INFORMACJI", "TEZA"],
    "searchInFullPhrase": True,
    "searchInContent": False,
    "searchInSynonyms": False,
    "searchQuery": "",
    "warunkiDodatkowe": [
        {"parametr": "DT_WYD", "od": "2024-01-01", "do": "2024-01-31"}
    ]
}
try:
    results = api_post('/wyszukiwarka/informacje/?size=5&page=0&sort=parametryPozycjonowania,asc', body2)
    print(f"Total: {results.get('totalHits')}")
except Exception as e:
    print(f"Error: {e}")

# Try filter with range object
print("\n=== DATE FILTER via filter range ===")
body3 = {
    "filter": {"DT_WYD": {"gte": "2024-01-01", "lte": "2024-01-31"}},
    "columns": ["SYG", "DT_WYD", "ID_INFORMACJI", "TEZA"],
    "searchInFullPhrase": True,
    "searchInContent": False,
    "searchInSynonyms": False,
    "searchQuery": "",
    "warunkiDodatkowe": []
}
try:
    results = api_post('/wyszukiwarka/informacje/?size=5&page=0&sort=parametryPozycjonowania,asc', body3)
    print(f"Total: {results.get('totalHits')}")
except Exception as e:
    print(f"Error: {e}")
