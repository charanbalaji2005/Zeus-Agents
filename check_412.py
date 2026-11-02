with open('marketing_landing/chunks/01gaqcovpeeyl.js', 'r', encoding='utf-8') as f:
    c = f.read()

print('Length of 01gaqcovpeeyl.js:', len(c))
# Look for 412
idx = c.find('412')
while idx != -1:
    print('412 occurrence:', c[max(0, idx-50):min(len(c), idx+100)])
    idx = c.find('412', idx+1)

