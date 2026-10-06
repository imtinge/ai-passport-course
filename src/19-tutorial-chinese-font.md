# 19. 手把手：让屏幕显示中文

这一章只解决一件事：**让 240×320 的屏幕上正确出现汉字**。

它是 AI Passport 上劝退率最高的一个坑。原因不是它难，而是它把三个**互相独立**的问题
挤在了同一个现象里——"中文不显示"。你看到的可能是空白、可能是方框（豆腐块）、
可能是乱码，而这三种表现对应三种完全不同的原因，网上搜到的解法往往只治其中一种。

本章的代码来自两部分：**官方中文字体指南** `docs/development/engineering/lvgl-chinese-fonts.zh_CN.md`
（在官方仓库 `folotoy/ai-passport` 里）+ **作者工作副本的巴巴爸爸项目**（第 18 章，
`main/demo_barbapapa.c`、`tools/barbapapa/gen_font.ps1`）。配套可编译文件在
`snippets/03_chinese_font.c`。

---

## 19.1 先分清三件事：编码、字形、样式

这是全章最重要的一节。分不清这三者，后面所有操作都是在撞运气。

| 层 | 问题 | 典型症状 | 谁负责 |
|---|---|---|---|
| **编码** | 源码里的中文用什么字节序列存 | 乱码、一个字变两个怪字 | 编辑器 / 编译器（UTF-8） |
| **字形** | 字体文件里有没有这个字的**图形** | 空白，或方框 ⯀ | `lv_font_conv` 生成的字体 |
| **样式** | 这个控件**实际用**哪个字体 | 英文正常、中文方框 | `lv_obj_set_style_text_font` |

关键认知：**UTF-8 正确 ≠ 能显示**。

UTF-8 只保证"这串字节等于汉字'爸'这个字符"。它完全不保证你编译进固件的字体里
有"爸"这个字的**点阵图形**。没有图形，LVGL 就画不出东西——于是你得到空白或方框。

反过来也成立：**字体里有这个字 ≠ 会显示**。因为控件可能根本没用你的中文字体。
官方 `ui_pixel.h` 里的 `ui_pixel_label()` 会设置局部字体，
`ui_pixel_screen_create()` 的标题用的是 Montserrat 20——
如果你把中文 label 建在这样一个父容器里，又没显式设字体，那它就是纯英文字体，
一个汉字也画不出来。

> **排查口诀**：先看编码（源码是不是 UTF-8），再看字形（字体里有没有），
> 最后看样式（这个控件到底绑了哪个字体）。**顺序不能反**，
> 因为前一步错了，后一步查出来的结论是假的。

### 一个必须记住的区别：字节 vs 码点

`"巴巴爸爸"` 这个字符串：

- 在 C 里它是 **12 个字节**的 UTF-8（每个汉字 3 字节）加上 1 个结尾 `\0`；
- 在 Unicode 里它是 **4 个码点**：U+5DF4 U+5DF4 U+7238 U+7238。

`lv_font_conv` 关心的是**码点**，不是字节，也不是"字符个数"。
生成字体时给它字节或给它中文字符串，都可能出错——下一节会讲到 Windows 上
真实的翻车现场。

---

## 19.2 三条路线，怎么选

| 方案 | 做法 | 覆盖 | Flash 代价 | 适用 |
|---|---|---|---|---|
| **A. 内置 CJK 子集** | 打开 `CONFIG_LV_FONT_SOURCE_HAN_SANS_SC_16_CJK` | 几千常用字 | 大（数百 KB 起） | 只想快速验证"能不能显示中文" |
| **B. 自制应用子集**（推荐） | `lv_font_conv` 只切你要的字 | 你要多少有多少 | 极小 | 做产品、做正式玩法 |
| **C. 整套字库** | 塞一个完整 CJK 字体 | 全 | 数 MB，**放不下** | 别想了 |

**为什么 C 不可行**：这块板子 8 MB flash，app 分区约 7.9 MB，还要装图片和音频。
一套完整黑体是 5~10 MB，塞进去别的什么都别干了。而且大字体在没 PSRAM 的机器上
解码慢、缓存命中差。

**方案 B 的威力有多大**：巴巴爸爸图鉴（第 18 章，作者工作副本）用了 10 个角色名，去重后一共 **16 个不同的汉字**
（`gen_font.ps1` 注释里逐个列了出来），生成两档字号（20px 和 14px）：

```
main/assets/barbapapa/bbp_font_14.c   13,938 字节
main/assets/barbapapa/bbp_font_20.c   22,906 字节
```

两档中文字体加起来 **不到 36 KB**。这就是"只切需要的字"的收益。
顺带一提：这 36 KB 是 `.rodata`，**不占 RAM**。

---

## 19.3 方案 B 全流程（推荐路线）

整个流程分五步，其中**三步在 PC 上做**，只有后两步碰板子：

```
① 选一个合法授权的 TTF/OTF 字体
② 列出你要显示的汉字 → 转成 Unicode 码点
③ lv_font_conv 生成 .c              ← PC
④ 把 .c 编进工程（target_sources）   ← 工程
⑤ LV_FONT_DECLARE + 绑定到控件       ← 代码
```

### 步骤 ①：选字体

要求只有两个：**授权允许**、**覆盖你需要的字形**。

- Windows 上最省事的是 `C:\Windows\Fonts\simhei.ttf`（黑体，单 face）——本书示例（以及巴巴爸爸项目）用的就是它。
- ⚠ **不能用 `.ttc` 字体集合**（比如 `msyh.ttc` 微软雅黑）。`lv_font_conv` 打不开 `.ttc`，
  会直接失败。这不是参数问题，是格式不支持。
- macOS / Linux 可以用 Noto Sans CJK、思源黑体等，注意看授权。

### 步骤 ②：列出码点

把你要显示的所有中文去重，然后查每个字的 Unicode 码点。

工作副本 `tools/barbapapa/names.txt`（第 18 章）里 10 个角色名去重后是这 16 个字：

```
丽 4E3D  伯 4F2F  利 5229  塔 5854  妈 5988  尔 5C14  巴 5DF4  布 5E03
拉 62C9  波 6CE2  洛 6D1B  爸 7238  特 7279  祖 7956  莱 83B1  贝 8D1D
```

> **手工查码点太累？写个脚本。** 三行 Python 就能从文案里抽出去重码点，
> 而且它是可复现的——文案一改，重跑一次就行：
>
> ```python
> # tools/gen_range.py：把所有固定文案里的汉字去重，输出 lv_font_conv 的 --range
> import sys
> text = "".join(open(f, encoding="utf-8").read() for f in sys.argv[1:])
> cps = sorted({ord(ch) for ch in text if ord(ch) > 0x2000})   # 只收非 ASCII
> print("--range " + ",".join(f"0x{c:04X}" for c in cps))
> ```
>
> 把**字符清单和转换命令都纳入版本管理**。下次加一句文案，重跑脚本重新生成，
> 别手改字体文件。

### 步骤 ③：生成 .c（含 Windows 专属大坑）

`lv_font_conv` 的标准调用（巴巴爸爸项目的 `gen_font.ps1` 就是这么写的，见第 18 章）：

```bash
lv_font_conv \
  --font C:/Windows/Fonts/simhei.ttf \
  --range 0x4E3D,0x4F2F,0x5229,0x5854,0x5988,0x5C14,0x5DF4,0x5E03, \
          0x62C9,0x6CE2,0x6D1B,0x7238,0x7279,0x7956,0x83B1,0x8D1D \
  --size 20 --bpp 4 --format lvgl --no-compress \
  --lv-font-name bbp_font_20 --lv-include lvgl.h \
  --output main/assets/barbapapa/bbp_font_20.c
```

每个参数的含义：

| 参数 | 为什么这么设 |
|---|---|
| `--range` | 要哪些**码点**。ASCII 也要的话加 `0x20-0x7E` |
| `--size 20` | 像素字号。**每个字号要单独生成一次**，不能一个字体缩放了用 |
| `--bpp 4` | 每像素 4 bit（16 级灰）。抗锯齿和体积的平衡点；`1` 会锯齿明显，`8` 体积翻倍 |
| `--format lvgl` | 输出 LVGL 的 C 数组格式 |
| `--no-compress` | ★ **首次接入不要压缩**。压缩需要 `CONFIG_LV_USE_FONT_COMPRESSED=y`，配置不匹配会直接不显示 |
| `--lv-font-name` | 生成的 C 变量名，要和代码里的 `LV_FONT_DECLARE()` **完全一致** |
| `--lv-include lvgl.h` | 生成的 .c 里 `#include` 哪个头文件 |

> **为什么本书敢推 `--bpp 4`（适用范围提醒）**
>
> 上面这套是**编译期 .c 字体**路线：字体在构建时烧进 Flash 的 `.rodata`，
> 运行时只是 `.rodata` 里的一个 `const` 数组，**不分配内存、直接按地址寻址**。
> 这条路上 `bpp4` 是体积与清晰度的甜点，本书所有数字都按它给。
>
> 但生态里还有另一条**运行时 .bin 字体**路线（LVGL 10 的 `binfont_create`、
> MicroPython 等）：字体在运行时从 Flash 读进内存再解析。那条路上 `bpp4` 大字库
> 有真机渲染挂死的实测教训——运行时还要为字形建索引/缓存，`bpp4` 的元数据比 `bpp1`
> 重很多。**迁移到运行时 .bin 路线时，`bpp1` 才是稳妥值**，别把本书的 `bpp4` 结论直接带过去。

> ⚠⚠ **Windows 专属大坑：不要用 `--symbols` 传中文**
>
> `lv_font_conv` 有个 `--symbols "中文"` 参数看起来更方便——直接把文案给它。
> 但它在 Windows 上通过 `npx`/node 转发参数时**会把中文参数搞坏**，
> 生成出来的字体里是错的码点，表现为"命令成功了，但部分/全部字是方框"。
>
> `gen_font.ps1` 的注释原文（作者工作副本，第 18 章）：
> *"Why codepoints instead of --symbols: passing Chinese text through
> npx/node on Windows corrupts the argument."*
>
> 所以：**永远用 `--range` 传十六进制码点**。这是最容易被坑一天的地方。

`gen_font.ps1` 里还固定了版本，这个习惯值得学：

```powershell
npx --yes lv_font_conv@1.5.3 ...
```

**固定版本号**。不同版本的 `lv_font_conv` 输出结构可能不同，不固定版本，
换台电脑生成出来的字体可能就编不过。

### 步骤 ④：编进工程

字体 .c 是普通源文件，用 `target_sources` 加进去（`main/CMakeLists.txt`）：

```cmake
target_sources(${COMPONENT_LIB} PRIVATE
    "${CMAKE_CURRENT_LIST_DIR}/assets/barbapapa/bbp_font_20.c"
    "${CMAKE_CURRENT_LIST_DIR}/assets/barbapapa/bbp_font_14.c"
)
```

三条纪律：

1. **不要 `#include` 字体 .c**。它是定义，不是头文件。
2. 加 `target_sources` 或加进 `SRCS` 列表，**二选一**，别重复编译同一个字体。
3. 如果你单独建一个字体组件，该组件必须声明对 LVGL 的依赖。

### 步骤 ⑤：声明并绑定

```c
#include "lvgl.h"

// 告诉编译器：有个叫 bbp_font_20 的 lv_font_t 定义在别的 .c 里
LV_FONT_DECLARE(bbp_font_20);
LV_FONT_DECLARE(bbp_font_14);

// 绑定到控件（第 18 章 demo_barbapapa.c:206，作者工作副本）
lv_obj_t *title = lv_label_create(plate);
lv_obj_set_style_text_font(title, &bbp_font_20, 0);
lv_label_set_text(title, u8"巴巴爸爸");
```

`u8"..."` 前缀显式声明这是 UTF-8 字符串字面量（C11 起）。加上它更稳，
尤其是你的源码可能在别的地方被当成别的编码。

---

## 19.4 fallback：中文字体里没图标怎么办

现实情况：你的中文字体里有汉字和 ASCII，但**没有 LVGL 的内置图标**
（`LV_SYMBOL_OK`、`LV_SYMBOL_CLOSE` 这些）。而官方 `ui_pixel.c` 的控件会用到图标。

错误做法：去改 `lv_font_conv` 生成的字体文件加图标。**不要手改生成物**，
下次重新生成就丢了。

正确做法：**给字体挂一条 fallback 链**。

⚠ 这里有个 LVGL 9 的坑：生成的字体是 `const` 的，你**不能直接改它的 `fallback` 字段**。
官方中文字体指南的做法是**拷一份可写描述符**（`docs/development/engineering/lvgl-chinese-fonts.zh_CN.md` 第 5 节）：

```c
#include "lvgl.h"

LV_FONT_DECLARE(bbp_font_20);
static lv_font_t s_font_20_with_symbols;    // ★ 可写副本，与 app 同寿命

void app_fonts_init(void)
{
    s_font_20_with_symbols = bbp_font_20;                    // 浅拷贝描述符
    s_font_20_with_symbols.fallback = &lv_font_montserrat_20; // 缺字时找它
}

lv_obj_t *make_label(lv_obj_t *parent)
{
    lv_obj_t *label = lv_label_create(parent);
    lv_obj_set_style_text_font(label, &s_font_20_with_symbols,
                               LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_label_set_text(label, u8"中文，ABC 123。" LV_SYMBOL_OK);
    return label;
}
```

几个必须知道的细节：

- **调用顺序**：先 `bsp_lvgl_init()` → 再 `app_fonts_init()` → 最后创建控件。
  任何控件用到这个描述符之前，它必须已经初始化完。
- **字段名**：LVGL **9** 里叫 `fallback`；LVGL 8 里叫 `fallback_font`。
  你要是照着老教程写 `fallback_font`，会编译不过。
- **fallback 有方向**：先查主字体，**只在缺字时**才查 fallback。
  两边都没有的字还是显示不出来。
- **别形成环路**：A 的 fallback 是 B、B 的 fallback 是 A，死循环。
- **别强转去掉 `const`**：`((lv_font_t*)&bbp_font_20)->fallback = ...` 是未定义行为。
  老老实实拷一份。
- **度量不一致**：标称同为 20px 的两个字体，基线/行高不一定一样。
  混排时留足高度，并检查实际渲染效果。

---

## 19.5 验证字形覆盖：别靠眼睛

"看起来显示了"不等于"所有字都有"。固定文案可以自查，但更可靠的做法是**程序化检查**。

官方中文字体指南给的探针（第 6 节）：

```c
#include "lvgl.h"

bool app_font_has_glyph(const lv_font_t *font, uint32_t codepoint)
{
    if (font == NULL) return false;
    lv_font_glyph_dsc_t glyph = {0};
    return lv_font_get_glyph_dsc(font, &glyph, codepoint, 0)
        && !glyph.is_placeholder;
}
```

注意 `&& !glyph.is_placeholder` 这一半——**这才是关键**。
`lv_font_get_glyph_dsc()` 在启用占位符时会"成功"返回一个占位字形，
函数返回 true，但屏幕上其实是个方框。**只看返回值会误判为通过**。

用法：把固定文案逐码点过一遍，缺字记成 `U+XXXX` 打到日志。

> ⚠ **别用 `lv_text_encoded_next()`**
>
> 很多老教程（包括 LVGL 8 的官方示例）用它来遍历 UTF-8。
> 但在 **LVGL 9.5** 里它被挪到了 `src/misc/lv_text_private.h`——**私有头**，
> 而且签名变成了函数指针 `uint32_t (*const)(const char *, uint32_t *)`。
> 直接照抄老代码会编译不过，或者 include 私有头埋下升级隐患。
>
> 自己写个极简解码器更稳，十几行：

```c
// 极简 UTF-8 解码：返回本字符占用的字节数，*cp 得到码点；返回 0 表示结束
static size_t utf8_next(const char *s, uint32_t *cp)
{
    const uint8_t *p = (const uint8_t *)s;
    uint8_t c = p[0];
    if (c == 0x00) return 0;
    if (c < 0x80)  { *cp = c; return 1; }
    if ((c & 0xE0) == 0xC0) {
        *cp = ((uint32_t)(c & 0x1F) << 6) | (p[1] & 0x3F);
        return 2;
    }
    if ((c & 0xF0) == 0xE0) {                      // 汉字基本都落在这里（3 字节）
        *cp = ((uint32_t)(c & 0x0F) << 12) | ((uint32_t)(p[1] & 0x3F) << 6) | (p[2] & 0x3F);
        return 3;
    }
    if ((c & 0xF8) == 0xF0) {
        *cp = ((uint32_t)(c & 0x07) << 18) | ((uint32_t)(p[1] & 0x3F) << 12)
            | ((uint32_t)(p[2] & 0x3F) << 6) | (p[3] & 0x3F);
        return 4;
    }
    *cp = 0xFFFD; return 1;                        // 非法字节：替换字符，跳过继续
}
```

```c
// 逐码点检查，缺字打日志
const char *s = u8"巴巴爸爸";
for (const char *p = s; *p; ) {
    uint32_t cp = 0;
    size_t len = utf8_next(p, &cp);
    if (len == 0) break;
    if (cp > 0x2000 && !app_font_has_glyph(&s_font_20_with_symbols, cp)) {
        ESP_LOGW("font", "缺字 U+%04X", (unsigned)cp);
    }
    p += len;
}
```

两个实践建议：

1. **加一个已知缺字的反例**（比如 `U+9F98`，一个你确定没收的字形）。
   如果你的检查对它也"通过"，说明检查本身写错了——否则这个测试会无条件通过，等于没测。
2. **检查实际控件绑定的字体**，而不是某个全局变量：
   `lv_obj_get_style_text_font(label, LV_PART_MAIN)` 拿到真正生效的字体再查。
   控件的 checked / focused / disabled 等状态下字体可能不同，都要查。

**到底显示的是哪个字体？用 getter 查，别猜。**
`ui_pixel_screen_create()` 的标题、菜单标签都有显式 Montserrat 配置；
你以为设了中文字体，可能被父容器或主题覆盖掉了。

---

## 19.6 不要关掉占位符

```c
CONFIG_LV_USE_FONT_PLACEHOLDER=y
```

**保持它是 y。** 关掉之后，缺字会变成"什么都不显示"——
你就分不清是"这个字没有"还是"整个字体没生效"还是"这段文本根本没绘制"。

方框虽然丑，但它是**诊断信息**：说明"走到绘制了，但这个字形没有"。
空白则把所有故障都折叠成了同一个现象。

---

## 19.7 故障排查表

按 19.1 的三层顺序查：

| 现象 | 最可能的原因 | 怎么查 |
|---|---|---|
| 中文变成两个奇怪的字 | 源码不是 UTF-8，或被当 GBK 解 | 用 `hexdump` 看字节；确保编辑器存成 UTF-8 无 BOM |
| 中文是空白 | 字体没绑上去 / 字体没这个字 | 先查 `lv_obj_get_style_text_font()`；再用 19.5 探针 |
| 中文是方框 ⯀ | 缺字形（字体没这个字） | 19.5 探针；重新生成字体，补码点 |
| 英文正常、中文方框 | 控件用了纯英文字体 | 显式 `lv_obj_set_style_text_font()` |
| 有的字能显示、有的不能 | 子集没切全 | 把**全部**固定文案跑一遍码点去重 |
| 命令成功但全部方框 | Windows 上用了 `--symbols` 传中文 | 改用 `--range` 十六进制码点 |
| 换台电脑生成就编不过 | `lv_font_conv` 版本不一致 | 固定版本，如 `lv_font_conv@1.5.3` |
| 字符上下被切掉 | 行高/基线/父容器裁剪 | 检查父容器高度与 `lv_obj_set_height()` |
| 换字号后糊 | 一个字体缩放用了 | 每个字号**单独生成** |

---

## 19.8 容量与性能账

用第 18 章那组数字做个标尺：

| 项目 | 大小 | 位置 |
|---|---|---|
| 16 个汉字 @ 20px, bpp4 | 22,906 B | Flash `.rodata`（**不占 RAM**） |
| 16 个汉字 @ 14px, bpp4 | 13,938 B | Flash `.rodata` |

估算你自己要多少：**汉字数 × 每字约 1.4 KB @20px bpp4**（22,906 / 16 ≈ 1,431 B）。
想显示 100 个汉字的 20px 字体，大约 140 KB。这在 7.9 MB 的 app 分区里完全放得下。

**为什么字体不占 RAM**：生成的字体数组是 `const`，链接进 `.rodata`，
直接从 Flash 读。这正是第 11 章"没有 PSRAM 怎么活"里那条纪律的又一个例子——
**能 `const` 就 `const`**。

---

## 19.9 小结与下一步

中文显示的完整路径：

1. 源码存 UTF-8（写 `u8"..."` 更稳）；
2. 把固定文案**去重成码点**，用脚本生成 `--range`；
3. `lv_font_conv --bpp 4 --no-compress` **每个字号单独生成**，固定工具版本；
4. `target_sources` 编进工程，**不要 include .c**；
5. `LV_FONT_DECLARE` 声明，名字要和 `--lv-font-name` 完全一致；
6. 需要图标就拷一份**可写描述符**挂 `fallback`（LVGL 9 的字段名是 `fallback`）；
7. 用带 `!is_placeholder` 的探针**程序化验证覆盖**，并留一个已知缺字的反例。

可编译示例：`snippets/03_chinese_font.c`。

下一章解决第二个高频需求——把一张图片画到屏幕上。
