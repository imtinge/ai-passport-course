"""C 代码块括号配平 / 语句完整性检查（抓复制粘贴截断）"""
import os, re

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src')

def blocks(fn):
    lines = open(fn, encoding='utf-8').read().split('\n')
    out = []; inf = False; lang = ''; buf = []; start = 0
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

def strip_code(code):
    """去掉注释和字符串字面量，避免误判"""
    out = []
    i = 0; n = len(code)
    while i < n:
        c = code[i]
        if c == '/' and i + 1 < n and code[i+1] == '/':
            while i < n and code[i] != '\n': i += 1
        elif c == '/' and i + 1 < n and code[i+1] == '*':
            i += 2
            while i + 1 < n and not (code[i] == '*' and code[i+1] == '/'): i += 1
            i += 2
        elif c == '"':
            i += 1
            while i < n and code[i] != '"':
                if code[i] == '\\': i += 1
                i += 1
            i += 1
        elif c == "'":
            i += 1
            while i < n and code[i] != "'":
                if code[i] == '\\': i += 1
                i += 1
            i += 1
        else:
            out.append(c); i += 1
    return ''.join(out)

def main():
    issues = []
    nc = 0
    for fn in sorted(os.listdir(BASE)):
        if not fn.endswith('.md'):
            continue
        for start, lang, code in blocks(os.path.join(BASE, fn)):
            if lang not in ('c', 'cpp', 'h'):
                continue
            nc += 1
            t = strip_code(code)
            # 括号配平
            for op, cl, name in [('{', '}', '花括号'), ('(', ')', '圆括号'), ('[', ']', '方括号')]:
                if t.count(op) != t.count(cl):
                    issues.append((fn, start, f'{name}不配平 {op}={t.count(op)} {cl}={t.count(cl)}',
                                   code.strip().split('\n')[0][:60]))
            # 单行语句缺分号（排除预处理、块首末、标签）
            lines = code.split('\n')
            for idx, l in enumerate(lines):
                # 先剥掉行尾 // 注释，再看是否以分号结尾
                raw = l
                s = re.sub(r'//.*$', '', l).strip()
                if not s:
                    continue
                if s != raw.strip() and raw.strip().startswith(('//',)):
                    continue
                if s.startswith('#'):
                    continue
                if s.endswith((';', '{', '}', ',', ':', ')', '*/', '\\')):
                    continue
                if s.startswith(('//', '/*', '*', 'case ', 'default', 'public', 'private')):
                    continue
                # 续行：下一行以 { 或 ; 开头大概率是函数签名换行
                nxt = lines[idx+1].strip() if idx + 1 < len(lines) else ''
                if nxt.startswith(('{', ';', ')', ':')) or nxt == '':
                    continue
                # 函数定义签名（含 ( 且未闭合）
                if '(' in s and s.count('(') > s.count(')'):
                    continue
                if re.match(r'^(typedef|struct|enum|union)\b', s) and not s.endswith(';'):
                    continue
                # 只保留"像 C 语句"的：含赋值/调用/分号位置特征，排除伪代码与表格行
                is_stmt = bool(re.search(r'(=|:|\(|\)|\breturn\b|\bif\b|\bfor\b|\bwhile\b)', s))
                has_cjk = bool(re.search(r'[\u4e00-\u9fff]', s))
                if not is_stmt or has_cjk:
                    continue
                ln = start + idx + 1
                issues.append((fn, ln, '语句可能缺分号', s[:70]))

    print(f'C 代码块: {nc}\n')
    if not issues:
        print('✅ 括号全部配平，无明显缺分号语句')
        return
    print(f'⚠ 发现 {len(issues)} 处：\n')
    for fn, ln, why, txt in issues:
        print(f'  {fn}:{ln}  [{why}]')
        print(f'      {txt}')

if __name__ == '__main__':
    main()
