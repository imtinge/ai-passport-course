# -*- coding: utf-8 -*-
"""HTML 产物静态检查（第 23 轮改动后）"""
import os, re, glob, collections

BOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'book')
htmls = sorted(glob.glob(os.path.join(BOOK, '*.html')))
print(f'HTML 页数: {len(htmls)}')

bad_utf8 = no_charset = fffd = 0
no_lang = 0
titles = collections.Counter()
all_ids = set()
links = []
bare_fence = 0
img_no_alt = 0
pre_code = tables = 0

for p in htmls:
    raw = open(p, 'rb').read()
    try:
        t = raw.decode('utf-8')
    except UnicodeDecodeError:
        bad_utf8 += 1
        continue
    if '\ufffd' in t:
        fffd += 1
    if not re.search(r'<meta[^>]+charset=["\']?UTF-8', t, re.I):
        no_charset += 1
    if not re.search(r'<html[^>]+lang=', t, re.I):
        no_lang += 1
    m = re.search(r'<title>(.*?)</title>', t, re.S)
    if m:
        titles[m.group(1).strip()] += 1
    for i in re.finditer(r'<(h1|h2|h3)[^>]+id="([^"]+)"', t):
        all_ids.add((os.path.basename(p), i.group(2)))
    for a in re.finditer(r'href="([^"]+\.html)(#[^"]*)?"', t):
        tgt, frag = a.group(1), a.group(2)
        links.append((os.path.basename(p), tgt.lstrip('./'), frag))
    # 正文区（去掉 <pre>）里是否残留裸 ```
    body = re.sub(r'<pre>.*?</pre>', '', t, flags=re.S)
    if '```' in body:
        bare_fence += 1
    pre_code += len(re.findall(r'<pre><code', t))
    tables += len(re.findall(r'<table>', t))
    for im in re.finditer(r'<img (?![^>]*\balt=)[^>]*>', t):
        img_no_alt += 1

print(f'非法 UTF-8: {bad_utf8} | 缺 charset: {no_charset} | U+FFFD 乱码: {fffd} | 缺 lang: {no_lang}')
print(f'<pre><code> 代码块: {pre_code} | <table>: {tables}')
print(f'残留裸 ```: {bare_fence} | <img> 缺 alt: {img_no_alt}')
dup = [k for k, v in titles.items() if v > 1]
print(f'title 重复: {dup if dup else "无"}')

# 内链校验
missing_file = []
broken_frag = []
names = {os.path.basename(p) for p in htmls}
for src, tgt, frag in links:
    if tgt not in names:
        missing_file.append((src, tgt))
        continue
    if frag:
        fid = frag[1:]
        tp = os.path.join(BOOK, tgt)
        th = open(tp, encoding='utf-8').read()
        if fid not in th:
            broken_frag.append((src, tgt, fid))
print(f'内链总数: {len(links)} | 目标文件缺失: {len(missing_file)} | 锚点不存在: {len(broken_frag)}')
for x in missing_file[:8]:
    print('  [缺文件]', x)
for x in broken_frag[:12]:
    print('  [断锚点]', x)

# 本轮新增小节的锚点确认（mdbook 保留中文）
print('\n=== 本轮新增小节锚点 ===')
targets = {
    '02-idf-crash-course.html': ['2.8', '位运算', '1ULL'],
    '06-button.html': ['6.8', '6.9', '消抖', 'DEBOUNCE'],
    '12-concurrency.html': ['volatile'],
    'C-glossary.html': ['SSID', 'socket', 'DNS', 'JTAG', 'UTF-8', 'Opus', 'blob', 'worker', '位掩码'],
}
for f, kws in targets.items():
    tp = os.path.join(BOOK, f)
    if not os.path.exists(tp):
        print(f'{f}: 文件不存在!')
        continue
    th = open(tp, encoding='utf-8').read()
    ids = re.findall(r'<h([23])[^>]+id="([^"]+)"', th)
    for kw in kws:
        hit = [i for _, i in ids if kw.lower() in i.lower()]
        print(f'  {f:<28} 含「{kw}」的标题: {hit if hit else "【缺失】"}')
