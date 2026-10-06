// 01 最小可跑页面：点亮屏幕，显示一行文字。
//
// 怎么跑起来（三段改动，见教材 D.15）：
//   1. 把本文件拷到官方工程的 main/ 下；
//   2. main/CMakeLists.txt 的 SRCS 里加 "demo_hello.c"；
//   3. main/main.c 的 DEMOS[] 里加 { .name = "Hello", .enter = demo_hello_enter,
//        .exit = demo_hello_exit, .key = demo_hello_key }。
//
// 编译校验：本文件用官方工程同一套参数编过（snippets/check_snippets.py）。
#include "demo.h"

#include "bsp_display.h"
#include "esp_log.h"
#include "lvgl.h"

static const char *TAG = "demo_hello";

static lv_obj_t *s_label = NULL;

void demo_hello_enter(void)
{
    // LVGL 非线程安全：非 LVGL 任务里动任何 lv_* 都要加锁。
    if (!bsp_lvgl_lock(500)) {          // 单位是毫秒（bsp_display.h: bsp_lvgl_lock(int timeout_ms)）
        ESP_LOGE(TAG, "加锁失败");
        return;
    }

    lv_obj_t *scr = lv_screen_active();
    lv_obj_clean(scr);                       // 换页前清掉上一页的东西

    s_label = lv_label_create(scr);
    lv_label_set_text(s_label, "Hello, Passport!");
    lv_obj_set_style_text_color(s_label, lv_color_hex(0xFFFFFF), 0);
    lv_obj_center(s_label);

    bsp_lvgl_unlock();

    // ★ 这一步漏了就是"黑屏但日志正常"——最常见的入门坑。
    bsp_display_backlight(100);
}

void demo_hello_exit(void)
{
    if (!bsp_lvgl_lock(500)) return;
    s_label = NULL;                          // 页面对象由 lv_obj_clean / 下一页接管
    bsp_lvgl_unlock();

    bsp_display_backlight(100);              // ★ 退出时把亮度还回去，否则回菜单一片黑
}

void demo_hello_key(bsp_btn_t btn, bsp_btn_ev_t ev)
{
    ESP_LOGI(TAG, "key=%d ev=%d", (int)btn, (int)ev);
}
