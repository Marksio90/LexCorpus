import urllib.request
import json
from datetime import datetime

base = 'https://eureka.mf.gov.pl/api/public/v1'

body = {
    "filter": {},
    "columns": ["SYG", "DT_WYD", "DATA_PUBLIKACJI", "ID_INFORMACJI", "TEZA", "KATEGORIA_INFORMACJI"],
    "searchInFullPhrase": True,
    "searchInContent": False,
    "searchInSynonyms": False,
    "searchQuery": "",
    "warunkiDodatkowe": []
}

data = json.dumps(body).encode('utf-8')
req = urllib.request.Request(
    base + '/wyszukiwarka/informacje/?size=5&page=0&sort=DATA_PUBLIKACJI,desc',
    data=data,
    headers={
        'User-Agent': 'Mozilla/5.0',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Referer': 'https://eureka.mf.gov.pl/',
    },
    method='POST'
)
resp = urllib.request.urlopen(req, timeout=15)
results = json.loads(resp.read().decode('utf-8'))

print(f"Total: {results.get('totalHits')}")
for r in results.get('results', []):
    dt_wyd = r.get('DT_WYD', 'N/A')
    data_pub = r.get('DATA_PUBLIKACJI', 'N/A')
    
    # Try parsing
    year = ''
    try:
        dt = datetime.fromisoformat(data_pub.replace('Z', '+00:00'))
        year = dt.year
    except Exception as e:
        year = f"ERROR: {e}"
    
    print(f"ID={r.get('ID_INFORMACJI')}, DT_WYD={dt_wyd}, DATA_PUBLIKACJI={data_pub}, year={year}, KAT={r.get('KATEGORIA_INFORMACJI')}")
