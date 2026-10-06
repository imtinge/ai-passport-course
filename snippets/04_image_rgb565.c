// 04 显示图片：RGB565 裸数据 + EMBED_FILES + lv_image_dsc_t。
//
// 前置（PC 上做一次，见教材第 20 章）：
//   python tools/img2rgb565.py pic.png main/assets/my_pic.bin   # 输出 240x240 / 115200B
//
// main/CMakeLists.txt：
//   EMBED_FILES "assets/my_pic.bin"
//   ★ 链接符号【只按文件基名】：_binary_my_pic_bin_start（不含目录）
//
// 编译校验：snippets/check_snippets.py
#include "demo.h"

#include "bsp_display.h"
#include "bsp_pins.h"          // BSP_LCD_W（屏幕宽 240）
#include "esp_log.h"
#include "lvgl.h"

static const char *TAG = "img";

// EMBED_FILES 的标准接法：asm("...") 指定链接符号名
extern const uint8_t my_pic[] asm("_binary_my_pic_bin_start");

// 尺寸必须和 PC 端转换脚本输出的一致。这里是 240x240 RGB565。
#define PIC_W 240
#define PIC_H 240

// ★ 长度写字面量：两个 extern 符号相减不是整型常量表达式，
//   不能在文件作用域初始化结构体（GCC 14 / RISC-V 直接报错）。
//   让 PC 端脚本把这两个数算好写死。
static const lv_image_dsc_t s_pic = {
    .header = {
        .magic  = LV_IMAGE_HEADER_MAGIC,
        .cf     = LV_COLOR_FORMAT_RGB565,   // 必须和实际格式一致
        .flags  = 0,
        .w      = PIC_W,
        .h      = PIC_H,
        .stride = PIC_W * 2,                // 一行字节数，RGB565 无填充时 = w*2
    },
    .data_size = PIC_W * PIC_H * 2,
    .data      = my_pic,                    // 指向 Flash(.rodata)，不占 RAM
};

static lv_obj_t *s_img = NULL;

static void show(uint8_t idx)
{
    (void)idx;
    if (!s_img) return;
    // 换图 = 换一个指针，不拷贝像素、不分配内存
    lv_img_set_src(s_img, &s_pic);
    lv_obj_set_pos(s_img, (BSP_LCD_W - s_pic.header.w) / 2, 44);
}

void demo_img_enter(void)
{
    s_img = lv_img_create(lv_screen_active());   // LVGL 9 里 lv_image_create() 是同一个东西
    show(0);
    ESP_LOGI(TAG, "图片 %ux%u, %u 字节", (unsigned)s_pic.header.w,
             (unsigned)s_pic.header.h, (unsigned)s_pic.data_size);
    bsp_display_backlight(100);
}

void demo_img_exit(void)
{
    s_img = NULL;
    bsp_display_backlight(100);
}

void demo_img_key(bsp_btn_t btn, bsp_btn_ev_t ev)
{
    (void)btn; (void)ev;
}

// ---------------------------------------------------------------------------
// 排错速查（详见第 20 章）：
//   白色偏红      → PC 端绿通道掩码写成 0xE0 了，应为 0xFC
//   颜色整体错乱  → 手工做了字节交换；存小端即可，BSP 的 .swap_bytes 会处理
//   花屏          → w/h/stride 填错，stride 应为 w*2
//   链接未定义符号 → 符号名带了目录，只用文件基名
//   四角看不见    → BSP 按半径 30 遮罩（BSP_LVGL_SCREEN_RADIUS），内容放中心区
