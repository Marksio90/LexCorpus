import urllib.request
import re

# Fetch main JS and extract ALL URL patterns
main_js = 'https://eureka.mf.gov.pl/main.535d199cee3ec94fe527.js'
req = urllib.request.Request(main_js, headers={'User-Agent': 'Mozilla/5.0'})
resp = urllib.request.urlopen(req, timeout=15)
js_body = resp.read().decode('utf-8', errors='replace')

# Look for all URL path patterns
paths = re.findall(r'["\'](/[^"\']*?)["\']', js_body)
print('All paths found:', len(paths))
interesting = [p for p in set(paths) if any(k in p.lower() for k in ['api', 'search', 'szukaj', 'interpret', 'document', 'v1', 'v2', 'public', 'rest'])]
for p in sorted(interesting)[:50]:
    print(' ', p)

# Look for full URLs
urls = re.findall(r'["\'](https?://[^"\']*?)["\']', js_body)
print('\nFull URLs:', len(urls))
for u in sorted(set(urls))[:20]:
    print(' ', u)

# Look for specific patterns like /api/.../...
api_paths = re.findall(r'["\'](/api/[^"\']*?)["\']', js_body)
print('\nAPI paths:', len(api_paths))
for p in sorted(set(api_paths))[:30]:
    print(' ', p)
