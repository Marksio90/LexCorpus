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

# Try warunkiDodatkowe with DATA_PUBLIKACJI
print("=== DATA_PUBLIKACJI filter ===")
body = {
    "filter": {},
    "columns": ["SYG", "DT_WYD", "DATA_PUBLIKACJI", "ID_INFORMACJI", "TEZA"],
    "searchInFullPhrase": True,
    "searchInContent": False,
    "searchInSynonyms": False,
    "searchQuery": "",
    "warunkiDodatkowe": [
        {"parametr": "DATA_PUBLIKACJI", "od": "2024-01-01T00:00:00.000Z", "do": "2024-01-31T23:59:59.999Z"}
    ]
}
try:
    results = api_post('/wyszukiwarka/informacje/?size=5&page=0&sort=DATA_PUBLIKACJI,desc', body)
    print(f"Total: {results.get('totalHits')}")
    for r in results.get('results', [])[:3]:
        print(f"  {r.get('DATA_PUBLIKACJI', 'N/A')[:10]} | {r.get('TEZA', '')[:60]}")
except Exception as e:
    print(f"Error: {e}")

# Try with just od (from date)
print("\n=== DATA_PUBLIKACJI from 2024 ===")
body2 = {
    "filter": {},
    "columns": ["SYG", "DT_WYD", "DATA_PUBLIKACJI", "ID_INFORMACJI", "TEZA"],
    "searchInFullPhrase": True,
    "searchInContent": False,
    "searchInSynonyms": False,
    "searchQuery": "",
    "warunkiDodatkowe": [
        {"parametr": "DATA_PUBLIKACJI", "od": "2024-01-01T00:00:00.000Z"}
    ]
}
try:
    results = api_post('/wyszukiwarka/informacje/?size=5&page=0&sort=DATA_PUBLIKACJI,desc', body2)
    print(f"Total: {results.get('totalHits')}")
except Exception as e:
    print(f"Error: {e}")

# Try with filter object for DATA_PUBLIKACJI
print("\n=== filter DATA_PUBLIKACJI range ===")
body3 = {
    "filter": {"DATA_PUBLIKACJI": {"od": "2024-01-01T00:00:00.000Z", "do": "2024-01-31T23:59:59.999Z"}},
    "columns": ["SYG", "DT_WYD", "DATA_PUBLIKACJI", "ID_INFORMACJI", "TEZA"],
    "searchInFullPhrase": True,
    "searchInContent": False,
    "searchInSynonyms": False,
    "searchQuery": "",
    "warunkiDodatkowe": []
}
try:
    results = api_post('/wyszukiwarka/informacje/?size=5&page=0&sort=DATA_PUBLIKACJI,desc', body3)
    print(f"Total: {results.get('totalHits')}")
except Exception as e:
    print(f"Error: {e}")
