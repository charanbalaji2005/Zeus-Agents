with open('marketing_landing/chunks/01gaqcovpeeyl.js', 'r', encoding='utf-8') as f:
    c = f.read()

import re
matches = [m.start() for m in re.finditer(r'\bey\(', c)]
for idx in matches:
    print('ey called at:', c[max(0, idx-100):min(len(c), idx+100)])

