with open('marketing_landing/index.html', 'r', encoding='utf-8') as f:
    text = f.read()

idx = 246441
print(text[idx-200:idx+2500])
