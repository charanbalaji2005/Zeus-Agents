with open('marketing_landing/index.html', 'r', encoding='utf-8') as f:
    text = f.read()

import re
blurs = re.findall(r'[^;{>\n]*blur[^;{<\n]*', text)
for b in blurs[:20]:
    print('BLUR:', b.strip())

# Check all img tags
imgs = re.findall(r'<img[^>]*>', text)
for img in imgs:
    print('IMG:', img[:150])
