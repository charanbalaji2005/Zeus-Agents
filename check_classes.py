with open('marketing_landing/original_index.html', 'r', encoding='utf-8') as f:
    orig = f.read()

import re
matches = re.findall(r'class="([^"]*animate[^"]*)"', orig)
print('Animate classes count:', len(matches))
for m in set(matches):
    print(' ', m)

# Let's inspect CSS files
css_links = re.findall(r'href="([^"]+\.css)"', orig)
print('\nCSS links count:', len(css_links))
for cl in css_links:
    print(' ', cl)
