// 02 LVGL 页面骨架：五个钩子 + 定时器的正确生命周期。
//
// 这是官方 demo_entry_t 契约的完整模板（main/demo.h）。
// 新增页面照抄这个结构，再按 D.15 做五处改动即可。
//
// 编译校验：snippets/check_snippets.py（官方工程同一套参数，带 -Werror）
#include "demo.h"

#include "bsp_display.h"
#include "esp_log.h"
#include "lvgl.h"

static const char *TAG = "demo_page";

static lv_obj_t *s_scr = NULL;
static lv_obj_t *s_label = NULL;
static lv_timer_t *s_timer = NULL;
static unsigned s_ticks = 0;

// ---- 定时器回调：运行在 LVGL 任务里，不用加锁，但【不能阻塞】--------------
static void on_timer(lv_timer_t *t)
{
    (void)t;
    if (!s_label) return;
    s_ticks++;
    lv_label_set_text_fmt(s_label, "tick %u", s_ticks);
}

// ---- enter：框架调用时【已持有 LVGL 锁】，只做建 UI 这类快操作 ------------
void demo_page_enter(void)
{
    s_scr = lv_obj_create(NULL);              // 独立页面容器
    lv_obj_remove_style_all(s_scr);
    lv_obj_set_size(s_scr, 240, 320);
    lv_obj_set_style_bg_color(s_scr, lv_color_hex(0x101014), 0);
    lv_obj_set_style_bg_opa(s_scr, LV_OPA_COVER, 0);

    s_label = lv_label_create(s_scr);
    lv_label_set_text(s_label, "tick 0");
    lv_obj_center(s_label);

    s_timer = lv_timer_create(on_timer, 500, NULL);   // 每 500ms 一次

    lv_screen_load(s_scr);
    bsp_display_backlight(100);               // ★ 不点亮=黑屏
}

// ---- exit：框架调用时【已持有 LVGL 锁】------------------------------------
void demo_page_exit(void)
{
    // ★ 顺序不能反：先删定时器，再删对象。
    //   反了的话，定时器回调会访问已经被删掉的 label —— 随机崩溃。
    if (s_timer) {
        lv_timer_delete(s_timer);
        s_timer = NULL;
    }
    if (s_scr) {
        lv_obj_delete(s_scr);                 // 删根对象会连带删掉所有子对象
        s_scr = NULL;
    }
    s_label = NULL;

    bsp_display_backlight(100);               // ★ 把亮度还回去，否则回菜单一片黑
}

// ---- key：框架调用时【不持锁】，要碰 UI 必须自己加 ------------------------
void demo_page_key(bsp_btn_t btn, bsp_btn_ev_t ev)
{
    if (ev != BSP_BTN_CLICK) return;

    // 拿不到锁就放弃本次按键，不要死等（UI 正忙）
    if (!bsp_lvgl_lock(250)) return;
    if (btn == BSP_BTN_OK && s_label) {
        s_ticks = 0;
    }
    bsp_lvgl_unlock();
    ESP_LOGI(TAG, "btn=%d", (int)btn);
}

// ---- 可选：慢服务在 start/stop 里做，【不持锁】----------------------------
// esp_err_t demo_page_start(void) { ... }
// esp_err_t demo_page_stop(void)  { ... 超时必须返回 ESP_ERR_TIMEOUT }
