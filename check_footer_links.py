with open('marketing_landing/index.html', 'r', encoding='utf-8') as f:
    text = f.read()

idx = text.find('hw-teams-footer-grid')
print(text[idx:idx+3000])
