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

body = {
    "filter": {},
    "columns": ["SYG", "DT_WYD", "DATA_PUBLIKACJI", "ID_INFORMACJI", "TEZA"],
    "searchInFullPhrase": True,
    "searchInContent": False,
    "searchInSynonyms": False,
    "searchQuery": "",
    "warunkiDodatkowe": []
}

for size in [25, 50, 100, 200]:
    try:
        results = api_post(f'/wyszukiwarka/informacje/?size={size}&page=0&sort=DATA_PUBLIKACJI,desc', body)
        count = len(results.get('results', []))
        print(f"size={size}: returned {count} results")
    except Exception as e:
        print(f"size={size}: ERROR {e}")
