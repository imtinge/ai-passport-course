// 03 中文显示：可写描述符 + fallback + 缺字自检。
//
// 前置（PC 上做一次，见教材第 19 章）：
//   lv_font_conv --font C:/Windows/Fonts/simhei.ttf
//     --range 0x5DF4,0x7238,0x9AD8,0x5174 --size 20 --bpp 4
//     --format lvgl --no-compress --lv-font-name my_font_20
//     --lv-include lvgl.h --output main/assets/my_font_20.c
//
// ★ --lv-font-name 必须和下面的 LV_FONT_DECLARE 完全一致。
//
// 编译校验：snippets/check_snippets.py
#include "demo.h"

#include "bsp_display.h"
#include "esp_log.h"
#include "lvgl.h"

static const char *TAG = "cn_font";

LV_FONT_DECLARE(my_font_20);          // 声明（定义在生成的 .c 里）

// ★ 可写描述符：与 app 同寿命。生成的字体是 const，不能直接改它的 fallback。
static lv_font_t s_font_20;

// ---- 极简 UTF-8 解码 ------------------------------------------------------
// 不用 lv_text_encoded_next()：LVGL 9.5 把它挪进了私有头 lv_text_private.h。
static size_t utf8_next(const char *s, uint32_t *cp)
{
    const uint8_t *p = (const uint8_t *)s;
    uint8_t c = p[0];
    if (c == 0x00) return 0;
    if (c < 0x80) { *cp = c; return 1; }
    if ((c & 0xE0) == 0xC0) { *cp = ((uint32_t)(c & 0x1F) << 6) | (p[1] & 0x3F); return 2; }
    if ((c & 0xF0) == 0xE0) {
        *cp = ((uint32_t)(c & 0x0F) << 12) | ((uint32_t)(p[1] & 0x3F) << 6) | (p[2] & 0x3F);
        return 3;
    }
    if ((c & 0xF8) == 0xF0) {
        *cp = ((uint32_t)(c & 0x07) << 18) | ((uint32_t)(p[1] & 0x3F) << 12)
            | ((uint32_t)(p[2] & 0x3F) << 6) | (p[3] & 0x3F);
        return 4;
    }
    *cp = 0xFFFD; return 1;
}

// ---- 缺字探针 --------------------------------------------------------------
// ★ 关键是 && !glyph.is_placeholder：开了占位符时 get_glyph_dsc 会"成功"返回
//   一个占位字形，只看返回值会把方框误判为通过。
static bool font_has_glyph(const lv_font_t *font, uint32_t cp)
{
    if (font == NULL) return false;
    lv_font_glyph_dsc_t g = {0};
    return lv_font_get_glyph_dsc(font, &g, cp, 0) && !g.is_placeholder;
}

// ---- 必须在【创建任何控件之前】调用一次 -----------------------------------
void app_fonts_init(void)
{
    s_font_20 = my_font_20;                             // 浅拷贝描述符
    s_font_20.fallback = &lv_font_montserrat_20;       // 缺字（如 LV_SYMBOL_*）时找它
}

// ---- 把一段固定文案逐码点过一遍，缺字打日志 -------------------------------
void app_fonts_selfcheck(const char *text)
{
    for (const char *p = text; *p; ) {
        uint32_t cp = 0;
        size_t len = utf8_next(p, &cp);
        if (len == 0) break;
        if (cp > 0x2000 && !font_has_glyph(&s_font_20, cp)) {
            ESP_LOGW(TAG, "缺字 U+%04X", (unsigned)cp);
        }
        p += len;
    }
    // 反例：这个字肯定没收。如果它也"通过"了，说明检查本身写错了。
    if (font_has_glyph(&s_font_20, 0x9F98)) {
        ESP_LOGE(TAG, "自检失效：U+9F98 本应缺字");
    }
}

// ---- 用法 ------------------------------------------------------------------
static lv_obj_t *s_label = NULL;

void demo_cn_enter(void)
{
    app_fonts_init();                                   // ★ 先初始化描述符
    app_fonts_selfcheck(u8"爸爸高兴");                  // 再自检

    s_label = lv_label_create(lv_screen_active());
    lv_obj_set_style_text_font(s_label, &s_font_20, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_label_set_text(s_label, u8"爸爸高兴 " LV_SYMBOL_OK);   // 图标走 fallback
    lv_obj_center(s_label);

    bsp_display_backlight(100);
}

void demo_cn_exit(void)
{
    s_label = NULL;
    bsp_display_backlight(100);
}

void demo_cn_key(bsp_btn_t btn, bsp_btn_ev_t ev)
{
    (void)btn; (void)ev;
}
