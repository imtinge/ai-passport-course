# AI Passport C 语言自学教材

面向**会写 C、没碰过 ESP-IDF** 的程序员：从零开始给 FoloToy AI Passport（ESP32-C3 + 8 MB Flash + 无 PSRAM）写可穿戴应用。
书里所有代码都来自真实仓库，关键数字逐条标了源码出处（"能查源码就不写据说"）。

## 环境前置

- **ESP-IDF v5.5.3**（本书示例的组件契约是 `>=5.5.3,<5.6.0`；作者本机装在 `D:\esp`）
- **Rust 工具链**（`cargo`，用来装 mdBook）
- **Python 3**（验证脚本用）

## 本地预览 / 构建

```bash
cargo install mdbook          # 只需一次
mdbook build                  # 生成 book/ 静态站
mdbook serve --open           # 本地预览，默认 http://localhost:3000
```

构建产物在 `book/`，是纯静态 HTML，**不进版本库**（见 `.gitignore`）。

## 验证示例代码（snippets）

`snippets/` 下 9 个 `.c` 都用官方工程同一套编译参数（含 `-Werror`）编过：

```bash
cd snippets
AIP_REPO=/path/to/your/ai-passport python check_snippets.py
```

Windows PowerShell 下的等价写法（前缀赋值在 PowerShell 里不能用，要改成临时环境变量）：

```powershell
cd snippets
$env:AIP_REPO = "D:\path\to\your\ai-passport"; python check_snippets.py
```

- `AIP_REPO` 指向你本地的 ai-passport 工程（需要 `build/compile_commands.json`，即先 `idf.py build` 成功一次）。
- 不想记环境变量也行：在 `snippets/` 下新建一个 `.aip_repo` 文件，里面**只写一行**你的 ai-passport 工程路径，脚本会自动读取（已写进 `.gitignore`，不会误入库）。
- 默认指向作者工作副本（含 `demo_barbapapa.c` 的巴巴爸爸工程，**非官方**，见第 18 章）；读者请务必覆盖成自己的路径。

## 目录结构

- `src/` —— 教材 Markdown 源（章节见 `src/SUMMARY.md`）
- `book/` —— 构建产物（git 忽略）
- `snippets/` —— 可编译示例 + 验证脚本 `check_snippets.py`
- `src/D-module-cookbook.md` 等 —— 分模块代码手册、API 速查、术语表

## 章节地图（速览）

| 部分 | 内容 |
| --- | --- |
| 起步（0b,1–3） | 硬件事实、ESP-IDF 速通、把固件跑起来 |
| 常用功能（4–12） | 屏幕、按键、音频、电量、存储、**联网三章（10 连上 / 10b 配网 / 10c 取数）**、内存、并发；**4.9 是官方 10 条不可破坏规则清单，动手前先过一遍** |
| 实战拆解（13–18） | 5 个社区仓库 + 巴巴爸爸（作者用 Trae 生成，非官方） |
| 手把手三件事（19–21） | 中文、图片、声音照着做一遍 |
| 收尾（22–23） | 调试排错、练习路线 |
| 官方示例源码详解（24–31） | 逐行拆解官方 `main/` 下 7 个硬件测试 demo + 框架（另有 11 条 `demo/*` 独立应用分支，见 23.5） |
| 附录（A–E） | API 速查、代表仓库索引（**B.7 = 不想写 C 的 MicroPython 路线**）、术语表、分模块代码手册、官方与社区资源地图 |

## 版权

见 [`LICENSE.md`](LICENSE.md)。
