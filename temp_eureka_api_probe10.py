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

# Try different sort options
sorts = [
    'parametryPozycjonowania,asc',
    'parametryPozycjonowania,desc',
    'DT_WYD,asc',
    'DT_WYD,desc',
    'DATA_PUBLIKACJI,asc',
    'DATA_PUBLIKACJI,desc',
]

body = {
    "filter": {},
    "columns": ["SYG", "DT_WYD", "ID_INFORMACJI", "TEZA"],
    "searchInFullPhrase": True,
    "searchInContent": False,
    "searchInSynonyms": False,
    "searchQuery": "",
    "warunkiDodatkowe": []
}

for sort in sorts:
    try:
        results = api_post(f'/wyszukiwarka/informacje/?size=3&page=0&sort={sort}', body)
        total = results.get('totalHits', 0)
        dates = [r.get('DT_WYD', 'N/A')[:10] for r in results.get('results', [])]
        print(f"Sort={sort}: total={total}, dates={dates}")
    except Exception as e:
        print(f"Sort={sort}: ERROR {e}")

# Try with a specific phrase to reduce results
print("\n=== SEARCH WITH PHRASE ===")
body2 = {
    "filter": {},
    "columns": ["SYG", "DT_WYD", "ID_INFORMACJI", "TEZA", "KATEGORIA_INFORMACJI"],
    "searchInFullPhrase": True,
    "searchInContent": False,
    "searchInSynonyms": False,
    "searchQuery": "interpretacja indywidualna",
    "warunkiDodatkowe": []
}
try:
    results = api_post('/wyszukiwarka/informacje/?size=5&page=0&sort=parametryPozycjonowania,asc', body2)
    print(f"Phrase search: total={results.get('totalHits')}")
    for r in results.get('results', [])[:3]:
        print(f"  {r.get('DT_WYD', 'N/A')[:10]} | {r.get('KATEGORIA_INFORMACJI', ['?'])[0][:50]} | {r.get('TEZA', '')[:60]}")
except Exception as e:
    print(f"Phrase search: ERROR {e}")
