# snippets —— 可编译的示例

这里每个 `.c` 都是**可以真编译过的**独立模块，不是从文档里摘出来的片段。

## 验证方式

用 ai-passport 工程的**同一套编译参数**（全部 `-I`/`-D`/`-march`，并且带 `-Werror`）
逐个编译。参数取自 `<ai-passport 工程>/build/compile_commands.json` 里 `main/main.c` 那一条。

```bash
# 前置：ai-passport 工程至少完整构建过一次（要有 build/compile_commands.json）
# ESP-IDF 装在别处时用 AIP_REPO 指定仓库路径（或写 snippets/.aip_repo 一行路径）
python check_snippets.py            # 全部
python check_snippets.py 03 04      # 只编 03、04
```

输出示例：

```
  OK    01_hello_screen.c
  OK    02_page_skeleton.c
  OK    03_chinese_font.c
  OK    04_image_rgb565.c
  OK    05_audio_play.c
  OK    06_audio_worker.c

通过 6/6
```

## 为什么值得这么做

本书的口号是"能查源码的就不写据说"。但**读源码只能保证思路对，不能保证 API 名字对**。
真编译过一次，才抓得出这类问题：

- `BSP_LCD_W` 在 `bsp_pins.h` 里，不在 `bsp_display.h`（04）；
- `bsp_lvgl_lock()` 的参数是**毫秒**不是 tick（01）；
- `lv_text_encoded_next()` 在 LVGL 9.5 里已经进了**私有头**，不能直接用（03）；
- `//` 注释里行尾的 `\` 会触发 `-Werror=comment`（03）。

上面第 1、4 条就是靠这个脚本当场抓出来的。
**文档里"看起来对"的代码，编译器不一定同意。**

## 怎么用到自己的工程

每个文件顶部都写了"三段改动"：

1. 拷到 ai-passport 工程的 `main/` 下；
2. `main/CMakeLists.txt` 的 `SRCS` 里加上它；
3. `main/main.c` 的 `DEMOS[]` 里注册（详见教材 D.15）。

## 清单

| 文件 | 内容 | 对应章节 |
| --- | --- | --- |
| `01_hello_screen.c` | 最小页面：点亮 + 一行文字 | 5、D.3 |
| `02_page_skeleton.c` | 五钩子 + 定时器生命周期（先删 timer 再删 obj） | 5.6、D.3 |
| `03_chinese_font.c` | 可写描述符 + fallback + 缺字自检 | **19**、D.4 |
| `04_image_rgb565.c` | EMBED_FILES + `lv_image_dsc_t` | **20**、D.5 |
| `05_audio_play.c` | 四步发声、分块播放、录音 | **21**、D.7 |
| `06_audio_worker.c` | worker + 任务通知 + 停止握手 | **21**、D.14 |
