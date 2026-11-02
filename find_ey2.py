with open('marketing_landing/chunks/01gaqcovpeeyl.js', 'r', encoding='utf-8') as f:
    c = f.read()

import re
# Find all occurrences of ey as a standalone word
for m in re.finditer(r'\bey\b', c):
    idx = m.start()
    print('ey at', idx, ':', c[max(0, idx-50):min(len(c), idx+50)])

