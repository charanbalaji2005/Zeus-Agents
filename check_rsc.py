with open('marketing_landing/original_index.html', 'r', encoding='utf-8') as f:
    orig = f.read()

import re
scripts = re.findall(r'<script>(?:self\.__next_f|\(self\.__next_f).*?</script>', orig, flags=re.DOTALL)
payload = '\n'.join(scripts)

comps = set(re.findall(r'\[\"\$[1-9a-zA-Z_]+\"', payload))
print('Component references:', comps)

# Let's find all module IDs exported in Turbopack
with open('marketing_landing/chunks/turbopack-1a1j5uj1qv02y.js', 'r', encoding='utf-8', errors='ignore') as f:
    tp = f.read()
print('turbopack len:', len(tp))
