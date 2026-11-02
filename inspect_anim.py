import re

with open('marketing_landing/original_index.html', 'r', encoding='utf-8') as f:
    text = f.read()

print('Canvas elements:', re.findall(r'<canvas[^>]*>', text))

# Look for HermsLandingScroll or similar components
components = re.findall(r'\"([a-zA-Z0-9_]*(?:Scroll|Anim|Hero|Wing)[a-zA-Z0-9_]*)\"', text)
print('Components found:', set(components))

# Let's see what scripts are loaded
scripts = re.findall(r'<script[^>]*src=\"([^\"]+)\"', text)
print('\nExternal scripts count:', len(scripts))
for s in scripts:
    print(' ', s)

