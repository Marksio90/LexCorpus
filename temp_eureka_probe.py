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

# Now fetch the main JS file and look for API endpoints
if js_files:
    main_js = [j for j in js_files if 'main' in j][0] if any('main' in j for j in js_files) else js_files[-1]
    if main_js.startswith('/'):
        main_js = 'https://eureka.mf.gov.pl' + main_js
    elif not main_js.startswith('http'):
        main_js = 'https://eureka.mf.gov.pl/' + main_js
    print('\nFetching main JS:', main_js)
    req2 = urllib.request.Request(main_js, headers={'User-Agent': 'Mozilla/5.0'})
    resp2 = urllib.request.urlopen(req2, timeout=15)
    js_body = resp2.read().decode('utf-8', errors='replace')
    
    # Look for API endpoints in JS
    js_apis = re.findall(r'["\']((?:/|https?://)[^"\']*(?:api|rest|graphql|search|szukaj)[^"\']*)["\']', js_body, re.IGNORECASE)
    print('API endpoints in JS:', len(js_apis))
    for a in sorted(set(js_apis))[:30]:
        print(' ', a)
    
    # Look for base URLs
    bases = re.findall(r'["\']((?:/|https?://)[^"\']*eureka[^"\']*(?:\.mf\.gov\.pl|/api|/rest))["\']', js_body, re.IGNORECASE)
    print('\nBase URLs:', len(bases))
    for b in sorted(set(bases))[:20]:
        print(' ', b)
        
    # Look for any URL patterns with mf.gov.pl
    mf_urls = re.findall(r'["\']((?:/|https?://)[^"\']*mf\.gov\.pl[^"\']*)["\']', js_body, re.IGNORECASE)
    print('\nMF URLs:', len(mf_urls))
    for u in sorted(set(mf_urls))[:20]:
        print(' ', u)
