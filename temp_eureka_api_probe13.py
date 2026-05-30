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

# Check if TRESC_INTERESARIUSZ in search results is full or truncated
body = {
    "filter": {},
    "columns": ["SYG", "DT_WYD", "DATA_PUBLIKACJI", "ID_INFORMACJI", "TEZA", "TRESC_INTERESARIUSZ", "KATEGORIA_INFORMACJI", "AUTOR", "SLOWA_KLUCZOWE", "ZAGADNIENIA", "PRZEPISY"],
    "searchInFullPhrase": True,
    "searchInContent": False,
    "searchInSynonyms": False,
    "searchQuery": "",
    "warunkiDodatkowe": []
}
results = api_post('/wyszukiwarka/informacje/?size=2&page=0&sort=DATA_PUBLIKACJI,desc', body)

for r in results.get('results', []):
    tresc = r.get('TRESC_INTERESARIUSZ', '')
    print(f"ID: {r.get('ID_INFORMACJI')}")
    print(f"TEZA: {r.get('TEZA', '')[:80]}")
    print(f"TRESC length: {len(tresc)}")
    print(f"TRESC preview: {tresc[:300]}...")
    print(f"TRESC end: ...{tresc[-200:]}")
    print()

# Compare with detail endpoint
print("=== DETAIL ===")
detail = api_post('/informacje/693315', {})
if 'dokument' in detail and 'fields' in detail['dokument']:
    for field in detail['dokument']['fields']:
        if field.get('key') == 'TRESC_INTERESARIUSZ':
            val = field.get('value', '')
            print(f"Detail TRESC length: {len(val)}")
            print(f"Detail TRESC preview: {val[:300]}...")
            break
