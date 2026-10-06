# 4. BSP：你和硬件之间唯一的中间人

> **可抄代码**：[D.1 启动与外设初始化](D-module-cookbook.md#d1-启动外设初始化与单项失败不致命)。


## 4.1 为什么要有 BSP

假设你要点亮屏幕。不用 BSP 的话，你要写这些：

```c
spi_bus_initialize(SPI2_HOST, &buscfg, SPI_DMA_CH_AUTO);
esp_lcd_new_panel_io_spi(...);
esp_lcd_new_panel_st7789(...);
esp_lcd_panel_reset(panel);
esp_lcd_panel_init(panel);
esp_lcd_panel_invert_color(panel, true);   // 这个屏出厂就要反色
esp_lcd_panel_set_gap(panel, 0, 0);
esp_lcd_panel_disp_on_off(panel, true);
ledc_timer_config(...);      // 背光 PWM
ledc_channel_config(...);
// ... 还有 LVGL 的初始化、锁、tick、刷新回调
```

这些代码里至少有三个坑是靠"踩过才知道"的：

- 这个屏**需要发 INVON 反色**，否则画面是负片；
- 复位脚**没接 MCU**，必须走软复位；
- 背光默认 duty 是 0，**不点亮就是黑屏**。

BSP 就是有人替你把这些踩完了。你只需要：

```c
bsp_display_init();
bsp_lvgl_init();
bsp_display_backlight(100);
```

## 4.2 BSP 目录结构

```
components/bsp/
├── CMakeLists.txt
├── idf_component.yml          # 托管依赖（esp_codec_dev、button 等）
├── include/
│   ├── bsp_pins.h             # ★ 硬件引脚与参数的单一事实来源
│   ├── bsp_display.h
│   ├── bsp_button.h
│   ├── bsp_audio.h
│   ├── bsp_battery.h
│   └── bsp_i2c.h
└── src/
    ├── bsp_display.c
    ├── bsp_display_lvgl.c     # LVGL 接线部分单独一个文件
    ├── bsp_button.c
    ├── bsp_audio.c
    ├── bsp_battery.c
    └── bsp_i2c.c
```

六个头文件，就是这块板子的全部能力面。**没有 `bsp_touch.h`、`bsp_imu.h`、
`bsp_sdcard.h`**——这些能力板子上不存在。

## 4.3 bsp_pins.h：改硬件只改这一个文件

这个文件值得单独说，因为它是"硬件事实的单一来源"：

```c
// components/bsp/include/bsp_pins.h
// FoloToy AI Passport 硬件引脚与参数的【单一事实来源】。换板/改硬件只需改这一个文件。
// 每项都注明"为什么是这个值",便于二次开发时判断能不能改。
```

它不只是列数字，每个数字都写了**为什么**。比如：

```c
// -1 = 复位脚未接 MCU(硬接 3.3V),由 esp_lcd_panel_reset() 走 SWRESET 软复位。
#define BSP_LCD_RST          (-1)

// 本屏出厂即需反色(参考例程 TFT_init() 末尾无条件发 0x21 INVON)。
// 若换屏后画面呈负片,把这里改成 0。
#define BSP_LCD_INVERT_COLOR 1

// ⚠ 不能改用【内部上拉】:约 45kΩ 且精度差,会把三档全挤到 0~154mV 并随温漂重叠。
#define BSP_BTN_ADC_CHANNEL  ADC_CHANNEL_0
```

**这是本书最推荐你先读的一个文件**（全文不到 120 行）。
读完它，第 1 章那张硬件表就从"要背的知识"变成了"有理由的安排"。

## 4.4 六头文件 API 总览

### bsp_display.h

```c
esp_err_t bsp_display_init(void);
esp_lcd_panel_handle_t bsp_display_panel(void);
esp_lcd_panel_io_handle_t bsp_display_io(void);
void bsp_display_backlight(uint8_t percent);
esp_err_t bsp_display_prepare_deep_sleep(void);
struct _lv_display_t *bsp_lvgl_init(void);
bool bsp_lvgl_lock(int timeout_ms);
void bsp_lvgl_unlock(void);
```

注意返回类型：前两个返回**裸的 `esp_lcd` 句柄**——
这是逃生舱口，万一你要直接操作面板（比如 DOOM 项目那样绕过 LVGL 直推像素）就用它们。

### bsp_button.h

```c
typedef enum { BSP_BTN_UP = 0, BSP_BTN_DOWN, BSP_BTN_OK } bsp_btn_t;

typedef enum {
    BSP_BTN_PRESS = 0,   // 按下瞬间(低延迟,适合游戏类即时响应)
    BSP_BTN_CLICK,       // 单击(按下并抬起)
    BSP_BTN_DOUBLE,      // 双击
    BSP_BTN_LONG,        // 长按
} bsp_btn_ev_t;

typedef void (*bsp_btn_cb_t)(bsp_btn_t btn, bsp_btn_ev_t ev, void *user);
esp_err_t bsp_button_init(bsp_btn_cb_t cb, void *user);
int bsp_button_read_mv(void);
```

四种事件里，`BSP_BTN_PRESS` 是"按下瞬间"——做游戏时要用它，
而不是 `CLICK`（那要等抬手才触发）。

### bsp_audio.h

```c
esp_err_t bsp_audio_init(void);
esp_err_t bsp_audio_set_format(uint32_t hz, uint8_t bits, uint8_t ch);
esp_err_t bsp_audio_sleep(void);
esp_err_t bsp_audio_prepare_deep_sleep(void);
esp_err_t bsp_audio_wake(void);
esp_err_t bsp_audio_write(const void *pcm, size_t bytes);
esp_err_t bsp_audio_read(void *pcm, size_t bytes);
void bsp_audio_set_volume(uint8_t percent);
```

### bsp_battery.h

```c
esp_err_t bsp_battery_init(void);
esp_err_t bsp_battery_sleep(void);
int bsp_battery_soc(void);   // 百分比，失败返回负数
int bsp_battery_mv(void);    // 毫伏，失败返回负数
```

### bsp_i2c.h

```c
esp_err_t bsp_i2c_init(void);
i2c_master_bus_handle_t bsp_i2c_bus(void);
esp_err_t bsp_i2c_scan(void);
esp_err_t bsp_i2c_prepare_deep_sleep(void);
```

`bsp_i2c_scan()` 在调试时很有用——它会打印总线上所有响应的设备地址。
如果你怀疑 ES8311 没焊好，先看 `0x18` 在不在。

## 4.5 边界：什么属于 BSP，什么属于 main

官方规定：

> Reusable board logic belongs in `components/bsp`; pages, state machines,
> animations, and application tasks belong in `main`.

| 放 `components/bsp` | 放 `main` |
| --- | --- |
| 引脚定义 | 页面（screen） |
| 外设初始化 | 状态机 |
| 总线读写 | 动画 |
| 电源/睡眠序列 | 应用任务 |
| 与"这块板"强绑定的一切 | 与"这个玩法"强绑定的一切 |

判断标准很简单：**换一块板子时要改的 → BSP；换一个玩法时要改的 → main。**

## 4.6 什么时候可以不走 BSP

社区里确实有不走 BSP 的项目，理由都是合理的：

**DOOM 项目**：整个仓库只有 36 个文件，它自己写了一个 6 个函数的 `bsp_doom`：

```c
bsp_display_init        bsp_display_panel
bsp_display_backlight   bsp_display_draw_bitmap
bsp_button_init         bsp_button_read
```

因为它**完全不用 LVGL**，直接往面板推像素。完整 BSP 里的 LVGL 部分对它来说是累赘。

**小智 AI 项目**：它不用 `components/bsp`，而是自己的 `Board` 基类 +
`AiPassportBoard` 派生类。因为它要支持 **171 种板型**，需要一套插件式抽象。
（第 17 章会讲它的设计。）

**但作为初学者，你应该用 BSP。** 理由不是"官方要求"，而是：
BSP 里的注释是社区踩坑的沉淀，你自己重写一遍会在同一个地方再踩一次。

## 4.7 一个典型 fork 扩展了什么

官方 BSP 只有 6 个头文件。有的 fork 会往上加，比如 `pax-zhang` 的 BSP：

```
bsp_audio.h  bsp_battery.h  bsp_ble.h  bsp_button.h
bsp_display.h  bsp_i2c.h  bsp_pins.h  bsp_pm.h  bsp_wifi.h
```

多了 `bsp_ble.h`（蓝牙）、`bsp_pm.h`（电源管理）、`bsp_wifi.h`（Wi-Fi）。
它的 Wi-Fi 部分就有 20 多个函数：

```c
bsp_wifi_init / connect / scan / forget / state / ssid / ip
bsp_wifi_enabled / has_saved / saved_pass / set_enabled
bsp_wifi_set_auto_connect / auto_connect
bsp_wifi_radio_suspend / radio_resume / ps_hold / ps_release
```

这说明了 BSP 的扩展方式：**需要什么能力，就在 BSP 里加一层薄封装**，
`main` 里永远只调 `bsp_*`。

## 4.8 从 BSP 里能学到的三条隐藏规则

读 BSP 源码时留意这些，它们是社区共识的固化：

**规则 1：I2C 是最先初始化的。**
ES8311 和 CW2017 共用一条总线，音频和电量都依赖它。
所有项目的 `app_main` 里，`bsp_i2c_init()` 都排在前面。

**规则 2：背光必须在建 UI 之前点亮。**

> 源码注释（pax-zhang `main/main.c`）：
> "背光默认 duty=0。必须在建 UI 之前点亮，否则 shell 里排版卡住就会一直黑屏。"

**规则 3：单项外设失败不阻塞启动。**

```c
s_ok[0] = true;                                    // Display 已确认可用
s_ok[1] = (bsp_button_init(on_key, NULL) == ESP_OK);
s_ok[2] = (bsp_audio_init() == ESP_OK);
s_ok[3] = (bsp_battery_init() == ESP_OK);
```

只有屏幕失败才 `return`，其余的记录状态、菜单里标 `[FAIL]`、其他功能照常。

## 4.9 小结

- BSP 把"踩过才知道"的硬件细节封装掉了：反色、软复位、背光默认灭；
- `bsp_pins.h` 是硬件事实的单一来源，**值得全文读一遍**；
- 六个头文件覆盖全部能力：display / button / audio / battery / i2c / pins；
- 换板要改的放 BSP，换玩法要改的放 main；
- 初始化顺序不是随意的：**I2C 最先，背光在建 UI 之前，屏幕失败才终止**。

下一章讲屏幕和 LVGL——这是你花时间最多的部分。
