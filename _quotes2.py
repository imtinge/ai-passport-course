"""第 2 轮排版：跨行双引号 + 中文内层单引号（逐行状态机，零索引改写）。

设计要点（吸取上一版教训）：
- **不做任何行号回填**，逐行读、逐行写，天然不会塌陷。
- 每行独立处理，只把该行里的 `"` 字符替换掉，行首缩进与 '> ' 前缀完全不碰。
- 用模块级 carry 记录"当前处于引号内"状态，跨行延续。
- 围栏代码块内一律跳过；行内代码片段先切出来保护，处理完再拼回（不用占位符）。
"""
import re
import glob
import os

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src')
CJK = re.compile(r'[\u4e00-\u9fff]')
INLINE = re.compile(r'`[^`\n]*`')

state = {'in_quote': False}


def convert_line(line):
    """返回 (新行, 双引号对数, 单引号对数)。只替换字符，不改结构。"""
    nl = '\n' if line.endswith('\n') else ''
    body = line[:-1] if nl else line

    # 保护行内代码：切分为 [代码/非代码] 片段
    segs = []
    pos = 0
    for m in INLINE.finditer(body):
        if m.start() > pos:
            segs.append((False, body[pos:m.start()]))
        segs.append((True, m.group(0)))
        pos = m.end()
    if pos < len(body):
        segs.append((False, body[pos:]))

    dq = 0
    sq = 0
    out = []
    for is_code, seg in segs:
        if is_code:
            out.append(seg)
            continue
        buf = []
        i = 0
        n = len(seg)
        while i < n:
            ch = seg[i]
            if ch == '"':
                # 中文语境才用弯引号：看本段或所处引用是否含中文由调用方保证，
                # 这里只按状态切换；纯英文引用不在候选行里（见挑选逻辑）。
                if state['in_quote']:
                    buf.append('”'); state['in_quote'] = False
                else:
                    buf.append('“'); state['in_quote'] = True
                dq += 1
                i += 1
                continue
            if ch == "'":
                j = seg.find("'", i + 1)
                if j != -1 and CJK.search(seg[i + 1:j]):
                    buf.append('‘'); buf.append(seg[i + 1:j]); buf.append('’')
                    sq += 1
                    i = j + 1
                    continue
                buf.append(ch); i += 1
                continue
            buf.append(ch); i += 1
        out.append(''.join(buf))
    return ''.join(out) + nl, dq, sq


def candidate(line):
    """该行是否值得处理：中文语境 且 含引号。"""
    if '```' in line:
        return False
    t = INLINE.sub('', line)
    if not CJK.search(t):
        return False
    return ('"' in t) or ("'" in t)


def process(path):
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    out = []
    in_fence = False
    dq = sq = 0
    for line in lines:
        if line.lstrip().startswith('```'):
            in_fence = not in_fence
            state['in_quote'] = False   # 围栏切换处重置，避免跨块污染
            out.append(line)
            continue
        if in_fence or not candidate(line):
            out.append(line)
            continue
        new, a, b = convert_line(line)
        dq += a; sq += b
        out.append(new)

    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(out)
    return dq, sq


if __name__ == '__main__':
    GD = GS = 0
    for p in sorted(glob.glob(os.path.join(SRC, '*.md'))):
        state['in_quote'] = False
        d, s = process(p)
        if d or s:
            print("%-34s 双引号 %3d | 单引号 %3d" % (os.path.basename(p), d, s))
        GD += d; GS += s
    print("---")
    print("合计：双引号 %d 个，单引号 %d 对" % (GD, GS))
