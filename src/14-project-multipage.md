# 14. 实战二：一个仓库装 5 个玩法（页面栈）

| 项目 | 值 |
| --- | --- |
| 排名 | #8 |
| 下载量 | 1101 |
| 仓库 | `github.com/pax-zhang/ai-passport` |
| 规模 | `main/` 37 个 .c，12630 行；3 条远程分支 |
| IDF | 5.5.3 |
| 玩法 | ANCS 通知、Walkie 对讲、天气、TOTP 口令、设置 |

**为什么拆解它**：它回答了一个工程问题——
**一个设备想装多个玩法时，代码怎么组织？**

它的答案（页面栈 + 函数指针）只有 60 行，却是全书最值得抄的架构。

## 14.1 工程结构

```text
pax-zhang__ai-passport/
├── components/bsp/          ← 扩展版 BSP（9 个头文件）
│   ├── include/ bsp_audio.h bsp_battery.h bsp_ble.h bsp_button.h
│   │            bsp_display.h bsp_i2c.h bsp_pins.h bsp_pm.h bsp_wifi.h
│   └── src/    (9 个 .c)
├── main/
│   ├── main.c           (79 行)
│   ├── app_shell.c      (421 行)  ← ★ 页面栈，本章主角
│   ├── app_home.c       (62 行)
│   ├── app_wx.c         (1444 行) ← 天气玩法
│   ├── app_totp.c       (762 行)  ← 动态口令
│   ├── app_ancs.c       (715 行)  ← 通知
│   ├── walkie.c / walkie_ble.c / walkie_codec.c
│   ├── app_prefs.c  app_settings.c  app_lock.c  app_time.c
│   ├── fonts/lv_font_cjk_12.c      ← 中文字体
│   └── certs/                      ← HTTPS 证书（EMBED_TXTFILES）
└── partitions.csv  sdkconfig.defaults  AGENTS.md
```

注意它的模块划分方式：**每个玩法一个 `app_*.c`**，
`app_shell.c` 负责调度，`app_prefs.c` 管设置。
这是“多玩法仓库”的通用组织法。

## 14.2 招牌实现：页面栈

> 源码：`main/app_shell.c`

```c
typedef struct {
    app_enter_fn enter;      // 进入页面：建 UI
    app_exit_fn  exit;       // 退出页面：销毁 UI
    app_key_fn   key;        // 按键处理
} page_t;

static lv_obj_t *s_scr, *s_main, *s_clock, *s_batt, *s_ico_bt, *s_ico_wf;
static page_t s_stack[STACK_MAX];     // 页面栈
static int    s_sp = -1;              // 栈顶指针

static void show_page(void)
{
    if (s_sp < 0) return;
    lv_obj_clean(s_main);              // 清空容器
    s_stack[s_sp].enter(s_main);       // 新页面往里画
}

void app_shell_open(app_enter_fn enter, app_exit_fn exit, app_key_fn key)
{
    if (s_sp + 1 >= STACK_MAX) return;
    if (s_sp >= 0 && s_stack[s_sp].exit) s_stack[s_sp].exit();
    s_sp++;
    s_stack[s_sp].enter = enter;
    s_stack[s_sp].exit  = exit;
    s_stack[s_sp].key   = key;
    show_page();
}

void app_shell_back(void)
{
    if (s_sp <= 0) return;
    if (s_stack[s_sp].exit) s_stack[s_sp].exit();
    s_sp--;
    show_page();
}

void app_shell_reload(void)
{
    if (s_sp < 0) return;
    if (s_stack[s_sp].exit) s_stack[s_sp].exit();
    show_page();
}
```

**60 行代码解决三件事：**

1. **统一接口**：每个页面只要实现 `enter/exit/key` 三个函数，
   就能被栈调度。新增玩法 = 写三个函数 + 注册一行；
2. **内存可控**：切页只 `lv_obj_clean(s_main)` 再重画，
   **始终只有一棵对象树**，不会为 5 个页面各留一份 UI；
3. **返回语义正确**：`back()` 天然支持多级返回（A→B→C→B→A）。

这是 **C 语言里“面向接口编程”的标准写法**——
如果你写过 C++ 的多态，这就是用函数指针手写的那一版。

## 14.3 注册一个玩法有多简单

> 源码：`main/app_home.c`

```c
static const home_item_t ITEMS[] = {
    { "通知",   app_ancs_enter,     app_ancs_exit,     app_ancs_key },
    { "对讲",   app_walkie_enter,   app_walkie_exit,   app_walkie_key },
    { "天气",   app_wx_enter,       app_wx_exit,       app_wx_key },
    { "口令",   app_totp_enter,     app_totp_exit,     app_totp_key },
    { "设置",   app_settings_enter, app_settings_exit, app_settings_key },
};
```

一张函数指针表 = 整个菜单。**加一个玩法就是加一行。**

## 14.4 app_main：18 步启动

> 源码：`main/main.c`（79 行，摘录关键部分）

```c
void app_main(void)
{
    app_logs_start();                                  // 1. 日志

    esp_err_t e = nvs_flash_init();                    // 2. NVS（含容错擦除）
    if (e == ESP_ERR_NVS_NO_FREE_PAGES || e == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        nvs_flash_init();
    }

    bsp_i2c_init();                                    // 3. I2C 最先

    if (bsp_display_init() != ESP_OK || !bsp_lvgl_init()) {   // 4. 屏幕
        ESP_LOGE(TAG, "显示/LVGL 初始化失败。检查 SPI 接线(MOSI=%d SCLK=%d CS=%d DC=%d BL=%d)",
                 BSP_LCD_MOSI, BSP_LCD_SCLK, BSP_LCD_CS, BSP_LCD_DC, BSP_LCD_BL);
        return;
    }
    ui_pixel_fonts_init();                             // 5. 字体
    bsp_display_backlight(50);                         // 6. ★ 建 UI 前点亮

    s_ok[1] = (bsp_button_init(on_key, NULL) == ESP_OK);   // 7. 按键
    s_ok[2] = (bsp_audio_init() == ESP_OK);                // 8. 音频
    s_ok[3] = (bsp_battery_init() == ESP_OK);              // 9. 电量
    s_ok[4] = (bsp_wifi_init() == ESP_OK);                 // 10. Wi-Fi
    walkie_ble_prepare();                                  // 11.
    s_ok[5] = (bsp_ble_init() == ESP_OK);                  // 12. BLE
    app_web_listen();                                      // 13. HTTPS 服务

    app_prefs_load();                                      // 14. 读设置
    app_prefs_apply_audio();
    app_prefs_apply_display();
    app_time_init();                                       // 15. 时间
    app_tone_start();
    bsp_pm_init();                                         // 16. 电源管理

    if (bsp_lvgl_lock(1000)) {                             // 17. 建 UI（加锁）
        app_shell_start();
        bsp_lvgl_unlock();
    }
}
```

**这套顺序可以直接当你的启动模板。** 它的特点是：

- **I2C 最先**（音频和电量都靠它）；
- **屏幕失败才 return**，其他失败只记 `s_ok[]`；
- **背光在建 UI 之前点亮**；
- **建 UI 时加锁**。

## 14.5 源码里当注释写下的五个坑

这个项目最宝贵的不是代码，是**那些解释“为什么”的注释**：

```c
/* 背光默认 duty=0。必须在建 UI 之前点亮,否则 shell 里排版卡住就会一直黑屏。 */
bsp_display_backlight(50);
```

```c
/* httpd 栈必须 ≥4KB,2048 会 Stack protection fault 整机重启回主界面。 */
app_web_listen();
```

```c
// ADC1 是 unit 级独占资源:iot_button 与 bsp_button_read_mv() 必须共用同一个 oneshot
// 句柄。谁第二个调 adc_oneshot_new_unit() 谁就拿到 "adc1 is already in use"。
static adc_oneshot_unit_handle_t s_adc;
```

```c
# LVGL 内置 malloc 池大小(KB)。它是独立静态区、不与系统堆共享,配大了会白白占用 RAM。
# 24KB 够 header + 列表 + 通知/锁屏浮层;32KB 会从系统堆再拿走 8KB,天气 DNS 容易碎掉。
CONFIG_LV_MEM_SIZE_KILOBYTES=24
```

```c
# Default 1 MB factory overflows after linking Wi-Fi STA (~1.2 MB).
```

最后一条解释了**为什么分区表里 factory 要给 3 MB**：
光是链上 Wi-Fi STA，固件就 1.2 MB 了。

## 14.6 它的“运行时不可破坏规则”

README 里列了 6 条，这 6 条基本就是本书第二部分的浓缩版：

1. LVGL 不是线程安全的；非 LVGL 上下文操作 `lv_*` 对象必须持有 `bsp_lvgl_lock()`；
2. 按键回调只派发轻量事件；录音、播放、存储和其他慢操作放到工作任务；
3. 页面退出时先停止可能访问 UI 的任务或定时器，再删除 screen 并清空对象指针；
4. 全局交互默认是菜单中 `UP`/`DOWN` 导航、`OK` 单击进入、页面中 `OK` 长按返回；
5. 新图片、字体、网络栈、音频缓存、LVGL buffer 或任务栈都要评估内部 RAM；
   总空闲堆足够不代表存在足够大的连续内存块；
6. 可测试的状态机、协议、计时和布局计算应与 ESP-IDF/LVGL 分离，优先加入主机逻辑测试。

## 14.7 你能从它抄走什么

| 想抄的东西 | 在哪 |
| --- | --- |
| **页面栈 / 函数指针架构** | `main/app_shell.c`（强烈推荐） |
| 18 步启动模板 | `main/main.c` |
| 设置持久化（NVS + 应用） | `main/app_prefs.c` |
| 熄屏 10 步序列 | `main/app_shell.c` 的 `sleep_now()` |
| 扩展版 BSP（Wi-Fi/BLE/PM） | `components/bsp/` |
| 中文字体接入 | `main/fonts/` + `ui_pixel_fonts_init()` |

## 14.8 小结

- **页面栈 = 函数指针三元组 + 手动栈**，60 行搞定多玩法调度；
- 始终只有一棵 UI 对象树，切页靠 `lv_obj_clean()` 重画；
- 加玩法 = 写三个函数 + 注册一行；
- 它的 `app_main` 是可以直接抄的启动模板；
- 源码注释里的踩坑记录比代码本身更有价值。
