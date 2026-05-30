import urllib.request
import json

base = 'https://eureka.mf.gov.pl/api/public/v1'

def api_call(method, path, body=None):
    url = base + path
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
        'Referer': 'https://eureka.mf.gov.pl/',
        'Origin': 'https://eureka.mf.gov.pl',
    }
    
    if body:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    else:
        data = None
    
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read().decode('utf-8'))

# Get detail and print all fields
detail = api_call('GET', '/informacje/693315')

print("=== ALL FIELDS IN dokument ===")
if 'dokument' in detail and isinstance(detail['dokument'], dict):
    doc = detail['dokument']
    
    if 'fields' in doc:
        print(f"\nTotal fields: {len(doc['fields'])}")
        for field in doc['fields']:
            key = field.get('key', 'N/A')
            val = field.get('value', '')
            data_type = field.get('dataType', 'N/A')
            val_preview = str(val)[:200] if val is not None else 'None'
            print(f"  {key} ({data_type}): {val_preview}")
    
    if 'zalacznikiContent' in doc:
        print(f"\nZalaczniki: {len(doc['zalacznikiContent'])}")
        for z in doc['zalacznikiContent'][:3]:
            print(f"  {z}")

print("\n=== informacjaTytulDto ===")
if 'informacjaTytulDto' in detail:
    for item in detail['informacjaTytulDto']:
        print(f"  {item}")
