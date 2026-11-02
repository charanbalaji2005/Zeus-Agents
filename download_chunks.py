import urllib.request
import re
import os

os.makedirs('marketing_landing/chunks', exist_ok=True)

with open('marketing_landing/original_index.html', 'r', encoding='utf-8') as f:
    text = f.read()

urls = re.findall(r'<script[^>]*src=\"(https://web-assets\.nousresearch\.com/[^\"]+\.js)\"', text)
print(f'Found {len(urls)} JS chunks')

for url in urls:
    name = url.split('/')[-1]
    path = os.path.join('marketing_landing/chunks', name)
    if not os.path.exists(path):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as resp:
                content = resp.read()
            with open(path, 'wb') as f:
                f.write(content)
            print(f'Downloaded {name} ({len(content)} bytes)')
        except Exception as e:
            print(f'Failed {name}: {e}')
    else:
        print(f'Already have {name}')

