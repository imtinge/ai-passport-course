#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用 ai-passport 工程的**同一套编译参数**编译 snippets/*.c，验证示例代码真的能编过。

原理：从 <官方工程>/build/compile_commands.json 里取出 main/main.c 的编译命令
（它带了全部 -I/-D/-march 与 -Werror），把末尾的 "-o <obj> -c <src>" 换成
我们自己的 snippet，然后原样执行。

用法：
    python check_snippets.py                 # 编译 snippets/ 下全部 .c
    python check_snippets.py 03 04           # 只编译编号含 03 / 04 的

依赖：本机已装 ESP-IDF v5.5.3 + 一个 ai-passport 工程至少成功构建过一次
（即 build/compile_commands.json 存在）。路径可用环境变量覆盖：
    AIP_REPO=D:/xxx/ai-passport   # 指向含 demo_barbapapa.c 的 ai-passport 工程
                                   # （官方仓无此文件；巴巴爸爸片段需要它，见第 18 章）
"""
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
# 路径解析优先级（从高到低）：
#   1) 环境变量 AIP_REPO                 —— 跨平台，推荐
#   2) snippets/.aip_repo 文本文件        —— 把工程路径写一行进去即可，Windows 读者不用记环境变量
#   3) 作者工作副本默认值（含 demo_barbapapa.c 的巴巴爸爸工程，非官方；读者请务必覆盖）
AIP_REPO_ENV = os.environ.get("AIP_REPO")
if AIP_REPO_ENV:
    REPO = Path(AIP_REPO_ENV)
else:
    _aip_repo_file = HERE / ".aip_repo"
    if _aip_repo_file.exists():
        REPO = Path(_aip_repo_file.read_text(encoding="utf-8").strip())
    else:
        REPO = Path(r"D:/trae_projects/AIP/ai-passport")
CC_JSON = REPO / "build" / "compile_commands.json"
MAIN_SRC = "main/main.c"


def load_base_cmd():
    if not CC_JSON.exists():
        sys.exit(f"找不到 {CC_JSON}\n先把官方工程完整构建一次：idf.py build")
    cc = json.load(io.open(CC_JSON, encoding="utf-8"))
    for e in cc:
        f = str(e["file"]).replace("\\", "/")
        if f.endswith("/" + MAIN_SRC):
            return str(REPO / "build"), e["command"]
    sys.exit(f"compile_commands.json 里没有 {MAIN_SRC}")


def main():
    build_dir, base = load_base_cmd()
    # 去掉原命令末尾的 "-o <obj> -c <src>"
    idx = base.rfind(" -o ")
    flags = shlex.split(base[:idx], posix=False)
    # compile_commands.json 里的 -D 带 shell 转义的引号（\"x\"），
    # posix=False 不会消掉反斜杠，清一下否则 gcc 报 missing terminating "
    flags = [a.replace('\\"', '"') for a in flags]

    only = sys.argv[1:]
    files = sorted(HERE.glob("*.c"))
    if only:
        files = [f for f in files if any(k in f.name for k in only)]
    if not files:
        sys.exit("没有匹配到 .c 文件")

    ok, bad = 0, []
    tmp = Path(tempfile.gettempdir()) / "aip_snippets"
    tmp.mkdir(parents=True, exist_ok=True)

    for src in files:
        obj = tmp / (src.stem + ".o")
        # 不走 shell：整条命令 13k 字符会撞上 cmd.exe 8191 的限制，
        # 直接给 CreateProcess 传 argv（上限 32767）就没问题。
        argv = flags + ["-o", str(obj), "-c", str(src)]
        r = subprocess.run(argv, cwd=build_dir,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode == 0:
            print(f"  OK    {src.name}")
            ok += 1
        else:
            print(f"  FAIL  {src.name}")
            print((r.stdout + r.stderr).strip()[:2500])
            bad.append(src.name)

    print(f"\n通过 {ok}/{len(files)}")
    if bad:
        print("失败：", ", ".join(bad))
        sys.exit(1)


if __name__ == "__main__":
    main()
