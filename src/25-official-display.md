# 25. 官方 Display 示例：色块 + 背光调光

源码：`main/demo_display.c`（66 行，含注释）。它是 7 个官方 demo 里最简单的一个，但把
"**用 LVGL 验证屏幕 + 背光**"这件最基础的事做对了——你拿到板子第一件事就该是确认屏能亮、能刷、背光能调。

> 行号来自官方基线 `main/demo_display.c`。

## 25.1 它验证什么

| 操作 | 行为 |
| --- | --- |
| 打开页面 | 中间一个大色块（红/绿/蓝/白/黑循环），下方显示色名 + 当前背光百分比 |
| OK（短按） | 切到下一种颜色 |
| UP / DOWN（短按） | 背光在 100% / 50% / 10% 三档间调 |
| OK（长按） | 返回菜单（框架拦截，不到本文件） |

源码顶部一句话点明设计意图（`demo_display.c:1-2`）：

```c
// main/demo_display.c —— 色块 + 背光调光。
// 用 LVGL 铺纯色(而非底层 draw_bitmap),这样和菜单共用同一套屏幕管理。
```

## 25.2 全局状态与两张查找表

```c
// main/demo_display.c:8-20
static lv_obj_t *s_scr;
static lv_obj_t *s_swatch;
static lv_obj_t *s_info;
static lv_obj_t *s_mascot;
static int s_color_idx;
static int s_bl_idx;

static const uint32_t COLORS[] = { 0xFF0000, 0x00FF00, 0x0000FF, 0xFFFFFF, 0x000000 };
static const char    *COLOR_NAME[] = { "RED", "GREEN", "BLUE", "WHITE", "BLACK" };
#define COLOR_COUNT (sizeof(COLORS) / sizeof(COLORS[0]))

static const uint8_t BL_LEVELS[] = { 100, 50, 10 };
#define BL_COUNT (sizeof(BL_LEVELS) / sizeof(BL_LEVELS[0]))
```

这里有个**可抄的小技巧**：颜色用"下标 + 查找表"表达，而不是堆 `if`。`s_color_idx` / `s_bl_idx`
就是当前选到第几个，按键切换时只做 `(idx + 1) % COUNT` 的环形自增——后面每个 demo 都这么干。

## 25.3 `refresh`：只改样式，不重建对象

```c
// main/demo_display.c:22-29
static void refresh(void) {
    lv_obj_set_style_bg_color(s_swatch, lv_color_hex(COLORS[s_color_idx]), 0);
    // 文字用与背景相反的明度,保证任何色块上都看得见
    bool dark = (s_color_idx == 2 || s_color_idx == 4);   // BLUE / BLACK
    lv_obj_set_style_text_color(s_info, dark ? lv_color_white() : lv_color_black(), 0);
    lv_label_set_text_fmt(s_info, "%s\n\nBACKLIGHT %d%%\n\nOK: NEXT COLOR\nUP/DOWN: LIGHT",
                          COLOR_NAME[s_color_idx], BL_LEVELS[s_bl_idx]);
}
```

**两个值得记的点**：

1. **反色逻辑**：蓝(`0x0000FF`)和黑(`0x000000`)背景下必须用白字，否则看不见。这是嵌入式 UI
   里"对比度"的硬要求——纯装饰的 PC 网页很少考虑，但板子上的单色/少色界面必须考虑。
2. **`refresh()` 只改 style / text，不 `lv_obj_del` 重建**。对象在 `enter` 里建一次，之后只更新属性，
   这对内存和性能都友好（也避免反复分配 LVGL 对象）。这是官方 demo 的统一习惯。

## 25.4 `enter`：建屏、建色块、调背光、刷新

```c
// main/demo_display.c:31-45
void demo_display_enter(void) {
    s_color_idx = 0;
    s_bl_idx = 0;
    bsp_display_backlight(BL_LEVELS[s_bl_idx]);      // 进页面先设好背光档位

    s_scr = ui_pixel_screen_create("DISPLAY");
    s_swatch = ui_pixel_panel_create(s_scr, 18, 58, 204, 188, COLORS[s_color_idx]);
    s_info = lv_label_create(s_swatch);
    lv_obj_set_style_text_font(s_info, &lv_font_montserrat_14, 0);
    lv_obj_set_style_text_align(s_info, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_center(s_info);
    s_mascot = ui_pixel_mascot_create(s_scr, 101, 238);
    refresh();
    lv_screen_load(s_scr);
}
```

注意 `enter()` 不持锁、直接操作 LVGL——因为框架在调它之前已经 `bsp_lvgl_lock()` 了
（回顾第 24.5 节）。色块就是一块 `ui_pixel_panel_create` 的面板，底色设为当前颜色。

## 25.5 `exit`：恢复背光 + 删屏

```c
// main/demo_display.c:47-50
void demo_display_exit(void) {
    bsp_display_backlight(100);          // 退出时恢复全亮,免得菜单看不见
    if (s_scr) { lv_obj_delete(s_scr); s_scr = NULL; s_swatch = s_info = s_mascot = NULL; }
}
```

**两个纪律**：① 退出页面时把背光恢复 100%，否则返回菜单会"看起来黑屏"（菜单用了 LVGL，
但物理背光被你压低了）；② 删根对象 `s_scr` 会连带删所有子对象，指针置 NULL 是防御重复调用。
这个"进页面设状态、出页面还原状态"的对称写法，后面 Audio / Low Power 也严格遵循。

## 25.6 `key`：加锁、改下标、刷新、解锁

```c
// main/demo_display.c:52-65
void demo_display_key(bsp_btn_t btn, bsp_btn_ev_t ev) {
    if (ev != BSP_BTN_CLICK) return;             // 只响应短按；长按返回被框架拦了
    if (!bsp_lvgl_lock(250)) return;             // ★ 要碰 LVGL 对象，先拿锁（250ms 拿不到就放弃）
    if (btn == BSP_BTN_OK) {
        s_color_idx = (s_color_idx + 1) % COLOR_COUNT;
        ui_pixel_mascot_jump(s_mascot);          // 按键反馈：吉祥物跳一下
    } else {
        s_bl_idx = (btn == BSP_BTN_UP) ? (s_bl_idx + BL_COUNT - 1) % BL_COUNT
                                       : (s_bl_idx + 1) % BL_COUNT;
        bsp_display_backlight(BL_LEVELS[s_bl_idx]);
    }
    refresh();
    bsp_lvgl_unlock();                            // ★ 立刻解锁，锁范围缩到最小
}
```

`key()` 是**唯一不预持锁的钩子**，所以第一行就是 `bsp_lvgl_lock(250)`。
参数 `250` 是**毫秒**（不是 tick——这是本书早前真编译抓出的错误，见前言勘误 #7）。
`bsp_display_backlight()` 调的是 BSP，不在 LVGL 里，但放在锁内也无害，且保证和刷新原子。

> `ui_pixel_mascot_jump()` 是按键的"视觉确认"——让用户知道按键被吃到了。板子没有鼠标光标，
> 这种即时反馈比在 PC 上还重要。

## 25.7 这个 demo 能抄什么

- **验证屏幕/背光的极简模板**：新板子到手，先写个"色块 + `bsp_display_backlight`"确认显示链路；
- **查找表 + 环形下标的状态表达**：比一堆 `if/else` 清爽，也省 Flash；
- **`enter` 设状态、`exit` 还原状态的对称纪律**（尤其背光）；
- **`key()` 的加锁模板**：`if (!bsp_lvgl_lock(250)) return;` —— 超时就放弃本次更新，绝不死等。

和第 5 章的关系：第 5 章讲 LVGL 的通用知识（对象树、style、字体、图片），本章是官方把它落到
"一块屏 + 三档背光"的最小可跑实例。想看"色块之外真正画图/中文/图片"的综合范例，见第 18 章
（巴巴爸爸，你自己的 Trae 项目，非官方）和第 20 章（图片教程）。
