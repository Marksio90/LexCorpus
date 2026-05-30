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

# Get detail and print full structure
print("=== DETAIL STRUCTURE ===")
detail = api_call('GET', '/informacje/693315')

def print_structure(obj, prefix=''):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                print(f"{prefix}{k}: {type(v).__name__}")
                if isinstance(v, dict):
                    print_structure(v, prefix + '  ')
                elif v and isinstance(v[0], dict):
                    print(f"{prefix}  [0]:")
                    print_structure(v[0], prefix + '    ')
            else:
                val_preview = str(v)[:100] if v is not None else 'None'
                print(f"{prefix}{k}: {type(v).__name__} = {val_preview}")
    elif isinstance(obj, list):
        print(f"{prefix}list of {len(obj)} items")

print_structure(detail)

# Try to find the text content
print("\n=== LOOKING FOR TEXT CONTENT ===")
if 'dokument' in detail and isinstance(detail['dokument'], dict):
    doc = detail['dokument']
    for k, v in doc.items():
        if isinstance(v, str) and len(v) > 50:
            print(f"dokument.{k}: {v[:200]}...")
        elif isinstance(v, dict):
            for k2, v2 in v.items():
                if isinstance(v2, str) and len(v2) > 50:
                    print(f"dokument.{k}.{k2}: {v2[:200]}...")
