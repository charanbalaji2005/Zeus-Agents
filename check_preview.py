with open('marketing_landing/index.html', 'r', encoding='utf-8') as f:
    text = f.read()

idx = text.find('landing-desktop-preview')
print(text[idx-200:idx+1200])
