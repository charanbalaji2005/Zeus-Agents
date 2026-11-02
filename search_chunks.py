import os
import re

chunks_dir = 'marketing_landing/chunks'
for f in os.listdir(chunks_dir):
    if not f.endswith('.js'): continue
    path = os.path.join(chunks_dir, f)
    with open(path, 'r', encoding='utf-8', errors='ignore') as fp:
        c = fp.read()
    
    matches = []
    if 'requestAnimationFrame' in c:
        matches.append('requestAnimationFrame')
    if 'framer-motion' in c or 'motion.' in c:
        matches.append('framer-motion')
    if 'gsap' in c:
        matches.append('gsap')
    if 'canvas' in c:
        matches.append('canvas')
    if 'scroll' in c.lower():
        matches.append('scroll')
    if 'keyframes' in c or 'animate' in c:
        matches.append('animate/keyframes')
    if 'marquee' in c:
        matches.append('marquee')
    if 'lenis' in c:
        matches.append('lenis')
    
    if matches:
        print(f'{f}: {", ".join(matches)}')

