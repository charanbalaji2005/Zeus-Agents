with open('marketing_landing/original_index.html', 'r', encoding='utf-8') as f:
    orig = f.read()

import re
scripts = re.findall(r'<script[^>]*>(?:self\.__next_f|\(self\.__next_f).*?</script>', orig, flags=re.DOTALL)
print(f'Original has {len(scripts)} __next_f scripts')
for i, s in enumerate(scripts):
    print(f'[{i}] len: {len(s)}')

