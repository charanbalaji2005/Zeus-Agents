with open('marketing_landing/index.html', 'r', encoding='utf-8') as f:
    text = f.read()

import re

# Find the footer columns and text in the screenshot
idx = text.find('GO TO DISCORD')
if idx != -1:
    print('Found GO TO DISCORD at:', idx)
    print(text[idx-400:idx+600])

# Also find where the big NOUS RESEARCH or ZEUS is in footer
idx2 = text.find('hw-ghost')
if idx2 != -1:
    print('\nFound hw-ghost at:', idx2)
    print(text[idx2-200:idx2+400])
