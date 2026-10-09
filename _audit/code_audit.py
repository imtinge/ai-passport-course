"""全书 C 代码块静态审查：危险模式 / 错误处理 / 内存安全"""
import os, re, io, collections

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src')

# 危险模式：(名称, 正则, 说明)
PATTERNS = [
    ('不安全字符串', r'\b(strcpy|strcat|sprintf|gets)\s*\(', '无长度校验，应改 strncpy/snprintf/strlcpy'),
    ('malloc未判空', r'^\s*\w+\s*=\s*(malloc|calloc|realloc)\s*\(', '分配后立即使用，未检查 NULL'),
    ('无free配对', r'\b(malloc|calloc|heap_caps_malloc)\s*\(', '需确认同作用域有对应 free'),
    ('scanf读串', r'\bscanf\s*\(\s*"[^"]*%s', '%s 无宽度限制'),
    ('魔法数sizeof', r'\bsizeof\s*\(\s*\w+\s*\)\s*\*\s*\d+', '手工算长度易错,推荐 sizeof(arr)/sizeof(arr[0])'),
    ('裸printf调试', r'\bprintf\s*\(', '嵌入式应用 ESP_LOGx'),
    ('空指针解引用风险', r'\*\s*\w+\s*=', '需确认指针已判空'),
    ('除零风险', r'/\s*\w+\s*(?![/*])', '需确认分母非 0'),
]

# 应检查返回值的 ESP-IDF API（出现即检查同一语句是否含错误判断）
CHECK_APIS = [
    'nvs_open', 'nvs_get_blob', 'nvs_set_blob', 'nvs_commit',
    'esp_http_client_init', 'esp_http_client_perform',
    'esp_tls_conn_new', 'esp_netif_create_default_wifi_sta',
    'esp_wifi_start', 'esp_wifi_connect', 'esp_event_handler_register',
    'xQueueCreate', 'xSemaphoreCreateBinary', 'xSemaphoreCreateMutex',
    'xTaskCreate', 'xQueueSend', 'esp_camera_init',
    'esp_lcd_panel_io_tx_param', 'esp_https_ota', 'cJSON_Parse',
    'esp_mqtt_client_init', 'lv_msgbox_create',
]

def extract_code(fn):
    """返回 [(起始行, 语言, 代码文本)]"""
    lines = open(fn, encoding='utf-8').read().split('\n')
    out = []
    inf = False; lang = ''; buf = []; start = 0
    for i, l in enumerate(lines, 1):
        s = l.lstrip()
        if s.startswith('```'):
            if not inf:
                lang = s[3:].strip().lower(); buf = []; start = i
            else:
                out.append((start, lang, '\n'.join(buf)))
            inf = not inf
            continue
        if inf:
            buf.append(l)
    return out

def main():
    hits = collections.defaultdict(list)
    api_nocheck = collections.defaultdict(list)
    total_c = 0; total_lines = 0
    # 统计每文件 malloc / free 配对
    memstat = {}

    for fn in sorted(os.listdir(BASE)):
        if not fn.endswith('.md'):
            continue
        p = os.path.join(BASE, fn)
        blocks = extract_code(p)
        for start, lang, code in blocks:
            if lang not in ('c', 'cpp', 'h', 'hpp'):
                continue
            total_c += 1
            nline = len(code.split('\n'))
            total_lines += nline
            lines = code.split('\n')

            for name, pat, desc in PATTERNS:
                for m in re.finditer(pat, code):
                    ln = start + code[:m.start()].count('\n') + 1
                    txt = lines[code[:m.start()].count('\n')].strip()
                    hits[name].append((fn, ln, txt[:80], desc))

            # esp_err_t 返回值未检查
            for api in CHECK_APIS:
                for m in re.finditer(r'\b' + api + r'\s*\(', code):
                    off = code[:m.start()].count('\n')
                    ln = start + off + 1
                    stmt = lines[off].strip()
                    # 判据：同行没有 ESP_ERROR_CHECK / != ESP_OK / == ESP_OK / if (!  / ret =
                    if not re.search(r'ESP_ERROR_CHECK|ESP_OK|ESP_ERR|if\s*\(\s*!|if\s*\(\s*\w+\s*\)|= *\w+ *;.*if|assert', stmt):
                        api_nocheck[api].append((fn, ln, stmt[:90]))

            # malloc/free 配对（按文件粒度）
            na = len(re.findall(r'\b(?:malloc|calloc|heap_caps_malloc|heap_caps_calloc|psram_malloc)\s*\(', code))
            nf = len(re.findall(r'\b(?:free|heap_caps_free)\s*\(', code))
            if na or nf:
                a, b = memstat.get(fn, (0, 0))
                memstat[fn] = (a + na, b + nf)

    print(f'C 代码块: {total_c} | 总行数: {total_lines}\n')

    print('=== 一、危险模式命中（按数量排序）===  ')
    for k, v in sorted(hits.items(), key=lambda x: -len(x[1])):
        print(f'\n【{k}】{len(v)} 处 —— {v[0][3]}')
        seen = set()
        for fn, ln, txt, _ in v[:8]:
            if (fn, ln) in seen: continue
            seen.add((fn, ln))
            print(f'   {fn}:{ln}  {txt}')
        if len(v) > 8:
            print(f'   ... 另 {len(v)-8} 处')

    print('\n\n=== 二、esp_err_t / 句柄类 API 返回值疑似未检查 ===')
    tot = 0
    for k, v in sorted(api_nocheck.items(), key=lambda x: -len(x[1])):
        print(f'\n【{k}】{len(v)} 处')
        for fn, ln, stmt in v[:5]:
            print(f'   {fn}:{ln}  {stmt}')
        tot += len(v)
    print(f'\n合计 {tot} 处（含引用真实源码的片段，需人工区分教学代码 vs 源码引用）')

    print('\n\n=== 三、malloc/free 配对（按文件）===')
    for fn, (a, b) in sorted(memstat.items(), key=lambda x: -(x[1][0] - x[1][1])):
        flag = '  ⚠ 不配对' if a != b else ''
        print(f'   {fn:<32} 分配 {a:>3} / 释放 {b:>3}{flag}')

if __name__ == '__main__':
    main()
