with open('marketing_landing/chunks/24okfw_pkx945.js', 'r', encoding='utf-8', errors='ignore') as f:
    c = f.read()

import re
matches = [m.start() for m in re.finditer(r'getContext\(["\']2d["\']\)', c)]
print('getContext(2d) occurrences:', len(matches))
for idx in matches:
    print('--- CONTEXT 2D ---')
    print(c[max(0, idx-200):min(len(c), idx+400)])

