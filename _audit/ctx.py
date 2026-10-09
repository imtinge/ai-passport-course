# -*- coding: utf-8 -*-
"""抓取指定词在正文中的上下文，人工判定用"""
import os, re, sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src')

def strip_fence(lines):
    out, inf = [], False
    for i, l in enumerate(lines, 1):
        if l.lstrip().startswith('```'):
            inf = not inf
            continue
        out.append((i, l, inf))
    return out

def show(word, maxn=40, width=110):
    hits = []
    for fn in sorted(os.listdir(SRC)):
        if not fn.endswith('.md'):
            continue
        raw = open(os.path.join(SRC, fn), encoding='utf-8').read()
        for no, line, inf in strip_fence(raw.split('\n')):
            if inf:
                continue
            if word in line:
                # 去掉行内代码
                clean = re.sub(r'`[^`\n]*`', '', line).strip()
                if word not in clean:
                    continue
                s = clean[:width]
                hits.append(f'{fn}:{no}  {s}')
    print(f'\n########## 「{word}」 共 {len(hits)} 处 ##########')
    for h in hits[:maxn]:
        print(h)
    if len(hits) > maxn:
        print(f'  ...(另 {len(hits)-maxn} 处)')

if __name__ == '__main__':
    for w in sys.argv[1:]:
        show(w)
