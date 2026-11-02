import os
import re

css_dir = 'marketing_landing'
# Downloaded css or inspect from web
from check_css import css_links
import urllib.request

for url in css_links:
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as resp:
        content = resp.read().decode('utf-8', errors='ignore')
    
    # search for animation:
    rules = re.findall(r'([^{}]*\{[^{}]*animation[^{}]*\})', content)
    if rules:
        print(f'=== {url.split("/")[-1]} ===')
        for r in rules[:8]:
            print(re.sub(r'\s+', ' ', r).strip())

