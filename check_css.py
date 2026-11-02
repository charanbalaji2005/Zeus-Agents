import urllib.request
import re

css_links = [
  "https://web-assets.nousresearch.com/marketing/b6e121e2175ca968d0d566a80c335622b59ea6f9/_next/static/immutable/chunks/32va4xuv19ip4.css",
  "https://web-assets.nousresearch.com/marketing/b6e121e2175ca968d0d566a80c335622b59ea6f9/_next/static/immutable/chunks/3tcnr869gb1yq.css",
  "https://web-assets.nousresearch.com/marketing/b6e121e2175ca968d0d566a80c335622b59ea6f9/_next/static/immutable/chunks/38r4opd7ram-c.css",
  "https://web-assets.nousresearch.com/marketing/b6e121e2175ca968d0d566a80c335622b59ea6f9/_next/static/immutable/chunks/2t57mcc55_soe.css",
  "https://web-assets.nousresearch.com/marketing/b6e121e2175ca968d0d566a80c335622b59ea6f9/_next/static/immutable/chunks/3p8koy1z1l4u7.css",
  "https://web-assets.nousresearch.com/marketing/b6e121e2175ca968d0d566a80c335622b59ea6f9/_next/static/immutable/chunks/01j2rq-9wihaa.css"
]

for url in css_links:
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as resp:
        content = resp.read().decode('utf-8', errors='ignore')
    keyframes = re.findall(r'@keyframes\s+([a-zA-Z0-9_\-]+)', content)
    if keyframes:
        print(f'{url.split("/")[-1]}: keyframes -> {keyframes}')

