with open('marketing_landing/chunks/01gaqcovpeeyl.js', 'r', encoding='utf-8') as f:
    c = f.read()

idx = c.find('412')
print(c[max(0, idx-400):min(len(c), idx+300)])

