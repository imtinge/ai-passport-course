# -*- coding: utf-8 -*-
"""找出"高频使用但从未定义"的术语 = 小白的跳步点"""
import os, re, collections

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src')

# 1) 已定义的术语（00b 硬件词表 + C 术语表的加粗条目）
defined = set()
for fn in ('00b-hardware-words.md', 'C-glossary.md'):
    raw = open(os.path.join(BASE, fn), encoding='utf-8').read()
    for m in re.finditer(r'\|\s*\*\*([^*]+)\*\*', raw):
        t = m.group(1)
        defined.add(t.lower())
        # 拆开 "中断/ISR" "任务task" "组件component" 这类
        for part in re.split(r'[/（(]', t):
            defined.add(part.strip().lower())
defined |= {'esp-idf', 'idf', 'bsp', 'lvgl', 'nvs', 'ota', 'uart', 'i2c', 'spi', 'i2s',
            'gpio', 'adc', 'dma', 'mcu', 'soc', 'psram', 'wdt', 'ble', 'gatt', 'gap',
            'rtos', 'freertos', 'nfc', 'pcm', 'codec', 'sram', 'flash', 'rodata',
            'bootloader', 'menuconfig', 'sdkconfig', 'kconfig', 'st7789', 'rgb565',
            'nimble', 'esp_timer', 'queue', 'semaphore', 'handle', 'task', 'widget'}

# 2) 候选技术词（正文里的英文术语/缩写）
CAND = re.compile(r'\b([A-Z][A-Za-z0-9_]{1,20}|[a-z][a-z0-9_]{2,20})\b')

STOP = set('''the and for you are not this that with from have will can how why what
when where into out off own too very just also than then them they their there
here more most some such only same so if but or as at by on in to of is it be
use used using make makes made get gets got put puts run runs need needs want
like time times way ways one two three first next last new old good bad big
small high low long short back down up over under again once each both few
other another all any every each no yes ok OK end start stop open close
read write readme file files line lines code codes note notes tip tips
step steps part parts page pages book chapter see see also etc eg ie
idf py md txt bin csv json yaml toml cmake c h app main src inc doc docs
com http https url uri api api s sdk sdk git github repo repos mdbook
TODO NOTE WARN WARNING TIPS INFO BUG FIX XXX HACK'''.split())

def strip_code(text):
    text = re.sub(r'```.*?```', '', text, flags=re.S)
    text = re.sub(r'`[^`\n]*`', '', text)
    return text

usage = collections.defaultdict(lambda: collections.defaultdict(int))  # term -> file -> n

files = sorted(f for f in os.listdir(BASE) if f.endswith('.md'))
for fn in files:
    if fn in ('00b-hardware-words.md', 'C-glossary.md'):
        continue
    body = strip_code(open(os.path.join(BASE, fn), encoding='utf-8').read())
    for m in CAND.finditer(body):
        t = m.group(1)
        if t.lower() in STOP or t.lower() in defined:
            continue
        if len(t) < 2:
            continue
        usage[t][fn] += 1

# 3) 只报"出现 >=4 次 且 跨 >=2 篇"的
print('=' * 72)
print('高频但未在词汇表/术语表中定义的词（按 总次数 降序）')
print('=' * 72)
rows = []
for t, d in usage.items():
    tot = sum(d.values())
    if tot >= 4 and len(d) >= 2:
        rows.append((tot, len(d), t, sorted(d.keys())))
rows.sort(reverse=True)
for tot, nf, t, fl in rows[:70]:
    print(f'{tot:>4}次 /{nf:>2}篇  {t:<22} {",".join(fl[:4])}{"…" if nf>4 else ""}')
