# 20. 手把手：把一张图片画到屏幕上

上一章解决了文字，这一章解决图片。

先说结论：**在这块板子上，图片不是"解码"出来的，是"搬"上去的。**
你在 PC 上把图片转成屏幕原生格式，烧进 Flash，运行时 LVGL 拿一个指针直接读。
没有 PNG 解码、没有 JPEG 解码、没有文件系统。

这不是偷懒，是这台机器的硬件条件决定的。本章代码全部来自**作者工作副本的巴巴爸爸项目**
（第 18 章）：`tools/barbapapa/fetch_assets.py`、`main/assets/barbapapa/barbapapa_assets.c`
和 `main/demo_barbapapa.c`（巴巴爸爸不在官方仓库，是你用 Trae 生成的实战玩法）。
配套可编译文件 `snippets/04_image_rgb565.c`。

---

## 20.1 为什么不在设备上解码

| 约束 | 数值 | 后果 |
|---|---|---|
| RAM | 约 400 KB，可用堆约 230 KB | 解码一张 240×320 的图要一整帧 RGB565 = 150 KB，直接吃掉大半 |
| 最大连续空闲块 | **< 8 KB** | 即使总量够，也未必能 `malloc` 出一大块 |
| PSRAM | **没有** | 没有"外挂内存"这条路 |
| Flash | 8 MB | 空间充裕，而且**可以直接内存映射读** |

所以社区的标准做法是：**把解码这件事挪到 PC 上，只做一次**。

```
PC（一次性）                     设备（每次运行）
  原图 PNG/GIF/JPG
    → 缩放到 ≤240×240
    → 转 RGB565 小端裸数据 .bin
    → EMBED_FILES 链进 Flash  ─────→  LVGL 拿指针直接读，不解码、不占 RAM
```

代价是图片尺寸和数量得在编译期定下来，不能运行时换。
对徽章/挂件这类"图鉴、头像、图标"场景，这完全够用。

---

## 20.2 屏幕的原生格式：RGB565 小端

ST7789 这块屏是 RGB565：**红 5 位、绿 6 位、蓝 5 位，一个像素 2 字节**。

```
 15 14 13 12 11 10  9  8  7  6  5  4  3  2  1  0
  R  R  R  R  R  G  G  G  G  G  G  B  B  B  B  B
```

打包公式（第 18 章 `fetch_assets.py:93`，作者工作副本）：

```python
rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
```

> ⚠ **绿通道掩码是 `0xFC` 不是 `0xE0`**
>
> 绿是 6 位，所以要保留高 6 位 → `0xFC`（1111 1100）。
> 有人凭直觉写成 `0xE0`（只留 3 位），结果丢掉绿色的低 3 位，
> 最典型的表现是**白色偏成品红**。这个 bug 肉眼很难一眼看出，
> 但把屏幕拍下来对比就会发现颜色发红。

**字节序**：C3 是小端，文件里按小端存（低字节在前）：

```python
struct.pack_into("<H", buf, i, rgb565)   # "<H" = 小端 uint16
```

> ⚠ **不要手工做字节交换**
>
> 你可能会想"SPI 要 big-endian，那我存成大端吧"。**别**。
> BSP 在 LVGL port 配置里已经设了 `.swap_bytes = true`
> （`components/bsp/src/bsp_display_lvgl.c:91`），port 会在送屏时统一交换。
> 你要是提前换了一次，等于换了两次——**颜色全乱**。
>
> 记住这条：`.bin` 里存**小端**，剩下的交给 BSP。

**透明通道**：RGB565 没有 alpha。如果原图有透明区域，先在 PC 上**贴一个底色**
（官方贴的是 `UI_PAPER` = `#F4F4EA`）：

```python
PAPER = (0xF4, 0xF4, 0xEA)          # ui_pixel.h 的 UI_PAPER
rgba = im.convert("RGBA")
bg = Image.new("RGB", rgba.size, PAPER)
bg.paste(rgba, mask=rgba.split()[3]) # 透明像素贴底色
```

动图只取首帧：`im.seek(0)`。做逐帧动画是另一个话题（见 20.9）。

---

## 20.3 PC 端管线：把原图变成 .bin

一个完整可跑的转换脚本（本节代码可直接使用，需 `pip install pillow`）：

```python
# tools/img2rgb565.py —— 原图 → LVGL 可直接用的 RGB565 裸数据
import struct, sys
from pathlib import Path
from PIL import Image

TARGET_H = 240      # 屏幕高
MAX_W    = 240      # 屏幕宽
PAPER    = (0xF4, 0xF4, 0xEA)   # 透明处贴的底色

def convert(src: Path, dst: Path):
    im = Image.open(src)
    im.seek(0)                                  # 动图只取首帧
    rgba = im.convert("RGBA")
    bg = Image.new("RGB", rgba.size, PAPER)
    bg.paste(rgba, mask=rgba.split()[3])        # 透明贴底色

    w0, h0 = bg.size
    scale = min(TARGET_H / h0, MAX_W / w0)      # 优先填满高，过宽时按宽收
    w, h = max(1, round(w0 * scale)), max(1, round(h0 * scale))
    bg = bg.resize((w, h), Image.LANCZOS)

    px = bg.load()
    buf = bytearray(w * h * 2)
    i = 0
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            # 绿是 0xFC 不是 0xE0，否则白色偏成品红
            rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            struct.pack_into("<H", buf, i, rgb565)   # 小端
            i += 2
    dst.write_bytes(buf)
    print(f"{src.name}: {w0}x{h0} -> {w}x{h}  {len(buf)} B")

if __name__ == "__main__":
    convert(Path(sys.argv[1]), Path(sys.argv[2]))
```

跑一下：

```bash
python tools/img2rgb565.py gif/anim_02barbapapa.gif main/assets/barbapapa/bbp_img_00.bin
# anim_02barbapapa.gif: 400x400 -> 240x240  115200 B
```

**一条硬规矩：转换脚本要打印"原始尺寸 → 输出尺寸 → 字节数"。**
第 18 章的 `fetch_assets.py` 就是这么做的：

```
idx 角色名        原始尺寸  -> 输出     GIF
 0. 巴巴爸爸     400x400  -> 240x240  115200B  anim_02barbapapa.gif
```

这张表是你的第一道防线——尺寸不对、体积异常，在这一步就能看出来，
不用烧进去才发现。

另外**加断言**。`fetch_assets.py` 对音频做了严格校验（必须是 16000/16/1，
否则直接 `sys.exit`），图片同理，建议至少断言：

```python
assert w <= 240 and h <= 240, f"{src.name} 超出屏幕 {w}x{h}"
assert len(buf) == w * h * 2,  "字节数必须等于 宽×高×2"
```

---

## 20.4 塞进固件：EMBED_FILES

图片是二进制，用 CMake 的 `EMBED_FILES` 原样链进 Flash
（`main/CMakeLists.txt`）：

```cmake
idf_component_register(
    SRCS "main.c" ...
    INCLUDE_DIRS "." "assets/barbapapa"
    EMBED_FILES
         "assets/barbapapa/bbp_img_00.bin"
         "assets/barbapapa/bbp_img_01.bin"
         ...
)
```

链接器会为**每个文件**生成一对符号，规则是：

```
`_binary_<文件名（非字母数字替换为下划线）>_start`
`_binary_<文件名（非字母数字替换为下划线）>_end`
```

> ⚠ **符号只按"文件基名"生成，不含目录**
>
> 第 18 章 `fetch_assets.py:178`（作者工作副本）的注释明确写了这一点：
> *"ESP-IDF v5.5 的 EMBED_FILES 只按文件基名生成符号
> （见 build/*.bin.S：`.global _binary_<basename>_start`），不含目录。"*
>
> 所以 `assets/barbapapa/bbp_img_00.bin` 的符号是
> `_binary_bbp_img_00_bin_start`，**不是** `_binary_assets_barbapapa_bbp_img_00_bin_start`。
> 生成 C 文件时的符号拼接函数必须也只取基名，否则链接期报"未定义符号"。

在 C 里声明（`main/assets/barbapapa/barbapapa_assets.c:4`）：

```c
extern const uint8_t bbp_img_00[] asm("_binary_bbp_img_00_bin_start");
```

`asm("...")` 是给这个变量指定**链接符号名**——这是 EMBED_FILES 的标准接法。

---

## 20.5 描述符：告诉 LVGL 这是什么图

光有裸数据不行，LVGL 需要知道宽、高、颜色格式。填一个
`lv_image_dsc_t`（第 18 章 `barbapapa_assets.c:36`，作者工作副本）：

```c
const lv_image_dsc_t bbp_imgs[10] = {
    { .header = { .magic = LV_IMAGE_HEADER_MAGIC,
                  .cf    = LV_COLOR_FORMAT_RGB565,
                  .flags = 0,
                  .w     = 197, .h = 240, .stride = 394 },
      .data_size = 94560,
      .data      = bbp_img_00 },
    ...
};
```

字段说明：

| 字段 | 值 | 说明 |
|---|---|---|
| `.header.magic` | `LV_IMAGE_HEADER_MAGIC` | 固定魔数，LVGL 靠它识别 |
| `.header.cf` | `LV_COLOR_FORMAT_RGB565` | 必须和你生成的格式一致 |
| `.header.w/.h` | 图片宽高 | **必须等于实际像素尺寸**，错了就是花屏 |
| `.header.stride` | `w * 2` | 一行多少字节。RGB565 无填充时就是 `w*2` |
| `.data_size` | `w * h * 2` | 总字节数 |
| `.data` | 指向 Flash 的指针 | **在 Flash 里，不在 RAM** |

> ⚠ **长度要写字面量，不要两个符号相减**
>
> 你可能想写 `.data_size = (uint32_t)(bbp_img_00_end - bbp_img_00)`。
> **编不过**。两个 `extern` 符号相减不是"整型常量表达式"，
> 不能在文件作用域初始化结构体——GCC 14 / RISC-V 会直接报错。
>
> `barbapapa_assets.c` 的注释写得很清楚（第 18 章）：
> *"长度写字面量：两个 extern 符号相减不是整型常量表达式，
> 不能在文件作用域初始化结构体（GCC 14 / RISC-V 直接报错）。"*
>
> 所以让 PC 端脚本把长度算好写进 C 文件（就像 20.3 那样）。

**指针指向 Flash**：`.data` 是 `const uint8_t*`，指向 Flash 的内存映射区。
LVGL 直接从那里取像素——**不占 RAM、不需要解码、开机即显示**。

---

## 20.6 显示出来

第 18 章 `demo_barbapapa.c` 的做法，一共三步：

```c
// 1) 创建控件（只创建一次，第 213 行）
s_img = lv_img_create(s_scr);

// 2) 换图：只换一个"指向 Flash 的描述符"指针，不拷贝像素（第 97 行）
lv_img_set_src(s_img, c->img);

// 3) 定位：按实际宽度水平居中
lv_obj_set_pos(s_img, (BSP_LCD_W - c->img->header.w) / 2, IMG_TOP_Y);
```

**换图的代价只有一个指针赋值。** 这是预转格式最大的好处——
10 张图来回切，不掉帧、不分配内存。

> **LVGL 9 的命名**：新 API 叫 `lv_image_create()` / `lv_image_set_src()`，
> 但 `lv_img_*` 这组名字**仍然可用**（兼容别名）。你抄社区或官方代码时两种都会见到
> （官方 7 个 demo 本身不显示图片，不会给你示范），新代码两种都能写，但**别混用**——
> 同一个工程里统一用一套，避免链接期反复横跳。

### 一个最小完整例子

```c
#include "lvgl.h"
#include "barbapapa_assets.h"     // 声明了 extern const lv_image_dsc_t bbp_imgs[10]

static lv_obj_t *s_img;

void show_image(lv_obj_t *parent, uint8_t idx)
{
    s_img = lv_img_create(parent);
    lv_img_set_src(s_img, &bbp_imgs[idx]);      // 传 &lv_image_dsc_t
    lv_obj_set_pos(s_img, (240 - bbp_imgs[idx].header.w) / 2, 44);
}
```

---

## 20.7 四角会被裁掉

**屏幕是圆角矩形**，四个角在 flush 时被遮成黑色。

这不是你的图片问题，是 BSP 干的：`bsp_display_lvgl.c` 在 `FLUSH_START` 事件里
按 `BSP_LVGL_SCREEN_RADIUS`（= **30**）逐行做遮罩，圆角外的像素填纯黑。

```
┌──────────────────┐
╭──────────────────╮   ← 半径 30 的圆角，角上是黑的
│                  │
│   你的图片区域    │
│                  │
╰──────────────────╯
└──────────────────┘
```

**设计含义：四个角约 30×30 的区域放不了内容。** 把重要信息（文字、按钮）
放在中心区域。同理，第 5 章讲过为什么不用 LVGL 的 `clip_corner`——
全屏圆角裁剪会生成 ARGB 图层，在没 PSRAM 的机器上是灾难。

---

## 20.8 容量账

第 18 章 10 张图的真实体积（巴巴爸爸项目，作者工作副本）：

| 项目 | 数值 |
|---|---|
| 单张 240×240 RGB565 | `240 × 240 × 2` = **115,200 B ≈ 112 KB** |
| 10 张图合计 | 约 **1,016 KB（≈ 1 MB）** |
| 10 段语音 + 2 个中文字体 | 约 **0.7 MB** |
| 合计素材 | 约 **1.7 MB**，app 分区约 7.9 MB，还剩很多 |

**算一算再动手**：`宽 × 高 × 2` 就是字节数。
一张全屏图 112 KB，10 张就 1 MB——加图之前先算，别等编译报
"分区溢出"才回头。

### 图太大怎么办：mmap

如果图片多到 Flash 放不下，或者你想放文件系统里，用**内存映射**
（`esp_partition_mmap`）。但有个硬限制：

> **Flash MMU 只有 128 个映射页**，每页 64 KB。
> 映射区域用完要 `esp_partition_munmap` 释放，否则后续映射会失败。

这是第 9 章和第 11 章都讲过的约束。对徽章场景，能用 `EMBED_FILES`
就别上 mmap——简单得多，也没有页耗尽的烦恼。

---

## 20.9 故障排查表

| 现象 | 原因 | 怎么查 |
|---|---|---|
| 花屏 / 颜色条纹 | 宽高或 stride 填错 | 核对 `.w`/`.h`/`.stride`，stride 应为 `w*2` |
| **白色偏红** | 绿通道掩码写成 `0xE0` | 改成 `0xFC` |
| 颜色整体错乱 | 手工做了字节交换 | 存小端，别手动 swap（BSP 的 `.swap_bytes` 已处理） |
| 图片偏一边 | 没按实际宽度居中 | `(240 - header.w) / 2` |
| 链接期"未定义符号" | 符号名带了目录 | 只用文件基名：`_binary_bbp_img_00_bin_start` |
| 编译期报"不是常量表达式" | 用了 `end - start` 算长度 | 让 PC 脚本写死字面量 |
| 四角内容看不见 | BSP 圆角遮罩（半径 30） | 内容放在中心区 |
| 图片不显示但日志正常 | 背光没点亮 | `bsp_display_backlight(100)` |
| 屏幕内容是上一页的 | 换页前没 `lv_obj_clean()` | 见第 5 章页面契约 |

---

## 20.10 进阶

- **动图**：GIF 逐帧转成多张 `.bin`，用 `lv_timer` 定时 `lv_img_set_src()` 切。
  注意 Flash 体积（每帧 112 KB，10 帧就 1.1 MB）。
- **缩放显示**：`lv_img_set_zoom()`。但缩放要实时重采样，
  在没 PSRAM 的机器上开销不小，能预转就预转。
- **Alpha 混合**：RGB565 没有 alpha 通道。需要透明效果用 `LV_COLOR_FORMAT_ARGB8565`
  之类带 alpha 的格式，代价是每像素 3 字节。
- **运行时换图**：`EMBED_FILES` 是编译期的。要运行时换图，得走文件系统 + mmap
  （见第 9 章），并注意 128 个 MMU 页的预算。

---

## 20.11 小结

图片管线的完整路径：

1. PC 上把原图**贴底色 → 等比缩放到 ≤240×240 → 转 RGB565 小端**；
2. 绿通道掩码 **`0xFC`**，透明处贴 `UI_PAPER`；
3. 脚本**打印"原始尺寸 → 输出尺寸 → 字节数"**并加断言；
4. `EMBED_FILES` 链进 Flash，符号**只按文件基名**；
5. 填 `lv_image_dsc_t`：**长度写字面量**，不能两个 extern 符号相减；
6. `lv_img_create()` + `lv_img_set_src(&dsc)`，换图只是换指针；
7. 内容避开**半径 30 的圆角**；加图前先算 `宽×高×2`。

可编译示例：`snippets/04_image_rgb565.c`。

下一章是三件套的最后一件：让板子发出声音。
