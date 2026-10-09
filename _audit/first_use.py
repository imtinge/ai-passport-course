# -*- coding: utf-8 -*-
"""按阅读顺序找术语"首次出现"的位置，判断是否有解释"""
import os, re

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src')

# 按 SUMMARY 的阅读顺序
ORDER = """00-preface 00b-hardware-words 01-hardware 02-idf-crash-course 03-first-build
04-bsp 05-display-lvgl 06-button 07-audio 08-battery-power 09-storage 10-network
10b-provisioning 10c-network-data 11-memory 12-concurrency 13-project-doom
14-project-multipage 15-project-voice 16-project-pokewalk 17-project-xiaozhi
18-project-barbapapa 19-tutorial-chinese-font 20-tutorial-image 21-tutorial-audio
22-debugging 23-whats-next 24-official-framework 25-official-display
26-official-button 27-official-audio 28-official-battery 29-official-wifi
30-official-ble 31-official-lowpower""".split()

TERMS = ['回调', '阻塞', '句柄', 'volatile', '位运算', '位操作', '轮询', '死锁',
         '竞态', '竞争', '互斥', '临界区', '原子', '对齐', '字对齐', '字节序',
         '大端', '小端', '回调', '事件循环', '状态机', '防抖', '去抖', '去抖动']

HINT = re.compile(r'是什么|意思是|即|也就是|所谓|指的是|可以理解|简单说|相当于|类比|换句话说')

for t in TERMS:
    found = False
    for stem in ORDER:
        p = os.path.join(BASE, stem + '.md')
        if not os.path.exists(p):
            continue
        raw = open(p, encoding='utf-8').read()
        # 剥离代码块
        body = re.sub(r'```.*?```', '', raw, flags=re.S)
        body = re.sub(r'`[^`\n]*`', '', body)
        if t in body:
            idx = body.find(t)
            # 取该行
            line_start = body.rfind('\n', 0, idx) + 1
            line_end = body.find('\n', idx)
            line = body[line_start:line_end].strip()
            has_hint = bool(HINT.search(line)) or bool(HINT.search(body[max(0,idx-200):idx+200]))
            # 是否在表格里（术语表式）
            in_table = line.startswith('|')
            print(f'{t:<8} 首现 {stem:<24} {"[表]" if in_table else "    "} {"[有解释]" if has_hint else "[! 无解释]"}')
            print(f'         └─ {line[:100]}')
            found = True
            break
    if not found:
        print(f'{t:<8} —— 全书正文未出现')
