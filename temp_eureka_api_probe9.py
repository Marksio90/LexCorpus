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

# Try various date filter formats in warunkiDodatkowe
formats = [
    {"parametr": "DT_WYD", "od": "2024-01-01T00:00:00.000Z", "do": "2024-01-31T23:59:59.999Z"},
    {"parametr": "DT_WYD", "od": "2024-01-01", "do": "2024-01-31"},
    {"parametr": "DT_WYD", "dataOd": "2024-01-01", "dataDo": "2024-01-31"},
    {"parametr": "DT_WYD", "wartoscOd": "2024-01-01", "wartoscDo": "2024-01-31"},
    {"parametr": "DT_WYD", "from": "2024-01-01", "to": "2024-01-31"},
    {"parametr": "DT_WYD", "zakres": {"od": "2024-01-01", "do": "2024-01-31"}},
    {"parametr": "DT_WYD", "typ": "ZAKRES_DAT", "od": "2024-01-01", "do": "2024-01-31"},
]

for i, wf in enumerate(formats):
    body = {
        "filter": {},
        "columns": ["SYG", "DT_WYD", "ID_INFORMACJI", "TEZA"],
        "searchInFullPhrase": True,
        "searchInContent": False,
        "searchInSynonyms": False,
        "searchQuery": "",
        "warunkiDodatkowe": [wf]
    }
    try:
        results = api_post('/wyszukiwarka/informacje/?size=3&page=0&sort=parametryPozycjonowania,asc', body)
        total = results.get('totalHits', 0)
        first_date = results['results'][0].get('DT_WYD', 'N/A') if results.get('results') else 'N/A'
        print(f"Format {i}: total={total}, first_date={first_date}")
        if total < 500000:
            print(f"  -> WORKING! Body: {wf}")
            break
    except Exception as e:
        print(f"Format {i}: ERROR {e}")

# Try filter with DT_WYD as array
print("\n=== FILTER with array ===")
body = {
    "filter": {"DT_WYD": ["2024-01-01T00:00:00.000Z", "2024-01-31T23:59:59.999Z"]},
    "columns": ["SYG", "DT_WYD", "ID_INFORMACJI", "TEZA"],
    "searchInFullPhrase": True,
    "searchInContent": False,
    "searchInSynonyms": False,
    "searchQuery": "",
    "warunkiDodatkowe": []
}
try:
    results = api_post('/wyszukiwarka/informacje/?size=3&page=0&sort=parametryPozycjonowania,asc', body)
    print(f"Array filter: total={results.get('totalHits')}")
except Exception as e:
    print(f"Array filter: ERROR {e}")
