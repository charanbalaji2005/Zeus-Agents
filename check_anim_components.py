with open('marketing_landing/chunks/3ifnovzsklquy.js', 'r', encoding='utf-8', errors='ignore') as f:
    c = f.read()

import re
# Find exported component names or displayNames or JSX tags
tags = set(re.findall(r'(\b[A-Z][a-zA-Z0-9]+(?:Animation|Motion|Scroll|Hero|View|Section)\b)', c))
print('Tags in 3ifnovzsklquy.js:', tags)

# Let's check 24okfw_pkx945.js
with open('marketing_landing/chunks/24okfw_pkx945.js', 'r', encoding='utf-8', errors='ignore') as f:
    c2 = f.read()

tags2 = set(re.findall(r'(\b[A-Z][a-zA-Z0-9]+(?:Animation|Motion|Scroll|Hero|View|Section)\b)', c2))
print('Tags in 24okfw_pkx945.js:', tags2)

