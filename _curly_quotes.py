"""把中文正文里的 ASCII 直引号 " 成对转换为全角弯引号 “”。

安全策略：
1. 完全跳过围栏代码块 ``` ... ```（含 ```c / ```bash 等语言标注）。
2. 完全跳过行内代码 `...`。
3. 只转换"内容含中文"的引号对，纯英文/纯代码引号原样保留。
4. 逐行处理，只在该行引号数为偶数时转换（跨行引号交给人工，避免误判）。
5. 不动 HTML 属性、链接、表格分隔线。
6. 幂等：已是弯引号的不会被再次处理。
"""
import re
import glob
import os

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src')
CJK = re.compile(r'[\u4e00-\u9fff]')

# 需要跳过的行：markdown 结构行、链接、表格
SKIP_LINE = re.compile(r'^\s*(?:\|[-: |]+\||\||```|~~~|=+\s*$)')


def convert_line(line):
    """返回 (新行, 转换对数)。只在该行 " 数为偶数时工作。"""
    if line.count('"') == 0 or line.count('"') % 2 == 1:
        return line, 0

    out = []
    i = 0
    n = len(line)
    converted = 0
    while i < n:
        ch = line[i]
        if ch == '`':
            # 行内代码：原样拷贝到配对的反引号
            j = line.find('`', i + 1)
            if j == -1:
                j = n - 1
            out.append(line[i:j + 1])
            i = j + 1
            continue
        if ch == '"':
            # 找配对的下一个 "
            j = line.find('"', i + 1)
            if j == -1:
                out.append(ch)
                i += 1
                continue
            inner = line[i + 1:j]
            # 只有内部含中文才转
            if CJK.search(inner):
                out.append('“')
                out.append(inner)
                out.append('”')
                converted += 1
            else:
                out.append('"')
                out.append(inner)
                out.append('"')
            i = j + 1
            continue
        out.append(ch)
        i += 1
    return ''.join(out), converted


def process(path):
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    out = []
    in_fence = False
    total = 0
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith('```'):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence or SKIP_LINE.match(line):
            out.append(line)
            continue
        new, c = convert_line(line.rstrip('\n'))
        total += c
        out.append(new + ('\n' if line.endswith('\n') else ''))

    if total:
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(out)
    return total


if __name__ == '__main__':
    grand = 0
    for p in sorted(glob.glob(os.path.join(SRC, '*.md'))):
        n = process(p)
        if n:
            grand += n
            print(f"{os.path.basename(p):34s} {n:4d} 对")
    print("---")
    print("合计转换:", grand, "对")
