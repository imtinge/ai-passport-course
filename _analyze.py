#!/usr/bin/env python3
import os, re, sys
from collections import defaultdict, Counter

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
files = sorted(f for f in os.listdir(SRC) if f.endswith(".md"))
fileset = set(files)

def slug(text):
    s = text.strip().lower()
    s = re.sub(r"[^\w\u4e00-\u9fff\- ]", "", s)  # keep word chars, CJK, hyphen, space
    s = s.replace(" ", "-")
    return s

# collect headings + anchors per file
headings = {}   # file -> list of (orig_text, anchor, line)
for f in files:
    with open(os.path.join(SRC, f), encoding="utf-8") as fh:
        lines = fh.readlines()
    anchors = []
    seen = Counter()
    in_fence = False
    for i, ln in enumerate(lines, 1):
        if ln.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if m:
            txt = m.group(2).strip()
            base = slug(txt)
            if seen[base] == 0:
                anchor = base
            else:
                anchor = f"{base}-{seen[base]}"
            seen[base] += 1
            anchors.append((txt, anchor, i))
    headings[f] = anchors

# code fences without language
fence_issues = []
for f in files:
    with open(os.path.join(SRC, f), encoding="utf-8") as fh:
        lines = fh.readlines()
    in_fence = False
    fence_lang = None
    start = 0
    for i, ln in enumerate(lines, 1):
        if ln.lstrip().startswith("```"):
            if not in_fence:
                in_fence = True
                fence_lang = ln.strip()[3:].strip()
                start = i
            else:
                if fence_lang == "":
                    fence_issues.append((f, start, i))
                in_fence = False
                fence_lang = None

# duplicate anchor detection within file
dup_anchors = {}
for f in files:
    c = Counter(a for _, a, _ in headings[f])
    dups = [a for a, n in c.items() if n > 1]
    if dups:
        dup_anchors[f] = dups

# links
link_re = re.compile(r"\]\(([^)]+)\)")
broken = []
for f in files:
    with open(os.path.join(SRC, f), encoding="utf-8") as fh:
        lines = fh.readlines()
    in_fence = False
    for i, ln in enumerate(lines, 1):
        if ln.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for m in link_re.finditer(ln):
            target = m.group(1).strip()
            if target.startswith(("http://", "https://", "mailto:", "#")):
                # anchor-only link in same file
                if target.startswith("#"):
                    anc = target[1:]
                    if anc not in [a for _, a, _ in headings[f]]:
                        broken.append((f, i, target, "anchor-not-found(local)"))
                continue
            # relative link
            if "#" in target:
                path, anc = target.split("#", 1)
            else:
                path, anc = target, ""
            path = path.strip()
            if path == "":
                # same-file anchor already handled
                if anc and anc not in [a for _, a, _ in headings[f]]:
                    broken.append((f, i, target, "anchor-not-found(local)"))
                continue
            # normalize
            base = os.path.dirname(f)
            resolved = os.path.normpath(os.path.join(base, path))
            if resolved not in fileset:
                broken.append((f, i, target, f"file-missing:{resolved}"))
            else:
                if anc and anc not in [a for _, a, _ in headings[resolved]]:
                    broken.append((f, i, target, f"anchor-not-found:{resolved}#{anc}"))

# SUMMARY consistency
with open(os.path.join(SRC, "SUMMARY.md"), encoding="utf-8") as fh:
    summ = fh.read()
summ_links = re.findall(r"\(([^)]+\.md)\)", summ)
summ_files = set(os.path.normpath(p) for p in summ_links)
missing_in_summ = [f for f in files if f != "SUMMARY.md" and f not in summ_files]
extra_in_summ = [f for f in summ_files if f not in fileset]

print("=== FILES ===")
print("Total md in src:", len(files))
print("In SUMMARY:", len(summ_files))
print("Missing from SUMMARY:", missing_in_summ)
print("Extra in SUMMARY (not on disk):", extra_in_summ)

print("\n=== CODE FENCES WITHOUT LANGUAGE ===")
if fence_issues:
    for f, s, e in fence_issues:
        print(f"  {f}:{s}-{e}")
else:
    print("  (none)")

print("\n=== DUPLICATE ANCHORS (mdBook auto-suffixes, links to bare anchor may break) ===")
if dup_anchors:
    for f, d in dup_anchors.items():
        print(f"  {f}: {d}")
else:
    print("  (none)")

print("\n=== BROKEN LINKS / ANCHORS ===")
if broken:
    for f, i, t, why in broken:
        print(f"  {f}:{i}  {t}  [{why}]")
else:
    print("  (none)")

# heading count + table count + code fence count stats
print("\n=== PER-FILE STATS (headings / tables / fences / unlang-fences) ===")
for f in files:
    with open(os.path.join(SRC, f), encoding="utf-8") as fh:
        lines = fh.readlines()
    nh = len(headings[f])
    nt = sum(1 for ln in lines if ln.strip().startswith("|") and "|" in ln[1:])
    # crude table rows
    ntablerows = 0
    in_fence = False
    nfence = 0
    for ln in lines:
        if ln.lstrip().startswith("```"):
            if not in_fence: nfence += 1
            in_fence = not in_fence
            continue
        if in_fence: continue
        if re.match(r"^\s*\|.*\|\s*$", ln) and not re.match(r"^\s*\|[\s:\-]+\|\s*$", ln):
            ntablerows += 1
    nun = sum(1 for (ff,s,e) in fence_issues if ff==f)
    print(f"  {f:32s} h={nh:2d} tabs~={ntablerows:3d} fences={nfence:2d} unlang={nun}")

print("\n=== HEADING ANCHOR MAP (for cross-check) ===")
for f in files:
    print(f"  [{f}]")
    for txt, a, l in headings[f]:
        print(f"      {l:4d}  #{a}   {txt[:50]}")
