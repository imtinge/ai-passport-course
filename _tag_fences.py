#!/usr/bin/env python3
import os, re

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
files = sorted(f for f in os.listdir(SRC) if f.endswith(".md"))

SHELL_CMDS = (
    "cd ", "git ", "idf.py", "python", "pip ", "cargo", "mdbook", "export ",
    "source ", "sudo ", "esptool", "./", "cat ", "ls ", "mkdir", "rm ", "cp ",
    "mv ", "echo ", "apt", "brew", "ninja", "cmake", "make ", "chmod", "touch ",
    "curl", "wget", "sh ", "bash ", "which", "cd\t",
)
PROMPT_PREFIX = ("$ ", "PS ", "> ")

def classify(block_lines):
    # block_lines: list of content lines (no fence lines)
    nonblank = [l for l in block_lines if l.strip() != ""]
    if not nonblank:
        return "text"
    joined = "\n".join(block_lines)
    # strong C signals
    if "#include" in joined or "typedef struct" in joined:
        return "c"
    if re.search(r"\b(esp_|lv_|bsp_|i2c_|gpio_|adc_|nvs_)\w+", joined):
        return "c"
    if re.search(r"void\s+\w+\s*\(", joined) and (";" in joined or "{" in joined):
        return "c"
    if "->" in joined and ";" in joined and re.search(r"\w+\s*->\s*\w+", joined):
        return "c"
    # powershell
    if "$env:" in joined or re.search(r"^PS\s", joined, re.M) or "powershell" in joined.lower():
        return "powershell"
    # csv-ish (comma table with header words)
    if re.search(r"^\s*\w+,\s*\w+,\s*\w+", joined, re.M) and (
        "nvs," in joined or "factory," in joined or "app," in joined or "data," in joined or "ota" in joined):
        return "text"  # csv not highlighted by mdBook; text is safe
    # shell: first nonblank line starts with a command prefix
    first = nonblank[0].lstrip()
    if first.startswith(PROMPT_PREFIX):
        return "bash"
    if first.startswith(SHELL_CMDS):
        return "bash"
    return "text"

changed = []
for f in files:
    path = os.path.join(SRC, f)
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()
    out = []
    i = 0
    n = len(lines)
    in_fence = False
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_fence:
                # opening fence
                lang = stripped[3:].strip()
                indent = line[:len(line)-len(line.lstrip())]
                if lang == "":
                    block = []
                    j = i + 1
                    while j < n and not lines[j].strip().startswith("```"):
                        block.append(lines[j].rstrip("\n"))
                        j += 1
                    tag = classify(block)
                    out.append(f"{indent}```{tag}\n")
                    out.extend(lines[i+1:j])
                    if j < n:
                        out.append(lines[j])  # closing fence
                    in_fence = False
                    i = j + 1
                    changed.append((f, i, tag))
                    continue
                else:
                    out.append(line)
                    in_fence = True
                    i += 1
                    continue
            else:
                # closing fence
                out.append(line)
                in_fence = False
                i += 1
                continue
        else:
            out.append(line)
            i += 1
    if any(c[0]==f for c in changed):
        with open(path, "w", encoding="utf-8") as fh:
            fh.writelines(out)

print("Fences tagged (file:line:lang):")
for f, ln, tag in changed:
    print(f"  {f}:{ln} -> {tag}")
print("Total:", len(changed))
