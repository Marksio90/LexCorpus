import urllib.request
import re

url = 'https://eureka.mf.gov.pl'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
resp = urllib.request.urlopen(req, timeout=10)
body = resp.read().decode('utf-8', errors='replace')

# Find JS files
js_files = re.findall(r'src="([^"]*\.js)"', body)
print('JS files found:', len(js_files))
for js in js_files[:15]:
    print(' ', js)

# Find any API-like URLs
apis = re.findall(r'["\']((?:/|https?://)[^"\']*api[^"\']*)["\']', body, re.IGNORECASE)
print('\nAPI refs:')
for a in set(apis)[:20]:
    print(' ', a)

# Look for config objects
configs = re.findall(r'window\.__[A-Z_]+__\s*=\s*({.*?});', body, re.DOTALL)
print('\nConfigs found:', len(configs))

# Look for any backend URLs
backends = re.findall(r'["\']((?:/|https?://)[^"\']*(?:backend|service|gateway)[^"\']*)["\']', body, re.IGNORECASE)
print('\nBackend refs:')
for b in set(backends)[:10]:
    print(' ', b)
