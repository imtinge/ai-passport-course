# D. 分模块常用代码手册

这一章是**照着抄的地方**。前面各章讲的是"为什么"，这里给的是"怎么写"。

使用方式：

- 每段代码顶部都标了**出处**（来自官方基线哪个文件），可以打开原文对照；
- 标了 **⚠** 的是这块的坑，抄的时候不要删注释；
- 所有代码都以官方基线（IDF v5.5.3 + LVGL 9.5）为准。

> 这一章默认你已经读过第 4 章（BSP）和第 5 章（LVGL 页面契约）。
> 如果你还不清楚 `enter/exit/key/start/stop` 五个钩子的调用时机，先看第 5.6 节。

---

## D.1 启动：外设初始化与"单项失败不致命"

**出处**：`main/main.c` `app_main()`

```c
void app_main(void) {
    // 0) 先弄清"我是怎么醒的"（深睡唤醒会重新跑一遍 app_main）
    esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();
    if (cause != ESP_SLEEP_WAKEUP_UNDEFINED) {
        ESP_LOGI(TAG, "唤醒原因: %d", cause);
    }

    // 1) I2C 是共享总线，audio / battery 内部也会调（幂等）
    bsp_i2c_init();
    bsp_i2c_scan();                      // 排障神器：打印 0x08~0x77 应答地址

    // 2) 显示是 UI 的载体，失败就没有界面可言 → 打清楚日志后放弃
    if (bsp_display_init() != ESP_OK || !bsp_lvgl_init()) {
        ESP_LOGE(TAG, "显示/LVGL 初始化失败。检查 SPI 接线(MOSI=%d SCLK=%d CS=%d DC=%d BL=%d)",
                 BSP_LCD_MOSI, BSP_LCD_SCLK, BSP_LCD_CS, BSP_LCD_DC, BSP_LCD_BL);
        return;
    }
    bsp_display_backlight(100);

    // 3) 其余外设【单项失败不阻塞】：菜单里标 [FAIL]，其他功能照常可测
    s_ok_audio   = (bsp_audio_init()   == ESP_OK);
    s_ok_battery = (bsp_battery_init() == ESP_OK);

    // 4) 按键：回调只入队（见 D.6）
    bsp_button_init(on_key, NULL);
}
```

**讲解**：官方基线把外设分成两类——

| 类别 | 失败怎么办 | 例子 |
| --- | --- | --- |
| **UI 载体** | 直接放弃（没有界面就没法交互） | `bsp_display_init` / `bsp_lvgl_init` |
| **可选能力** | 记下来，UI 上标 `[FAIL]`，其余照跑 | `bsp_audio` / `bsp_battery` / Wi-Fi / BLE |

这个分级值得照抄。很多初学者的 `app_main` 里全是 `ESP_ERROR_CHECK(...)`，
结果**少焊一个电量计整机就起不来**——而实际上电量计本来就是可选件。

> ⚠ `bsp_*_init()` 全部**幂等可重试**：重复调用直接返回 OK，失败会回滚本次
> 已建资源，修好故障后再调一次就行。所以"先 init 音频再 init 电量计"这种
> 顺序依赖不存在，不用担心谁先谁后。

---

## D.2 屏幕与背光

**出处**：`main/demo_display.c`

```c
// 背光 0~100（%），LEDC PWM，0 = 全灭
bsp_display_backlight(100);

// 不用 LVGL 也能画：拿 panel 句柄直接推像素
esp_lcd_panel_handle_t panel = bsp_display_panel();
// esp_lcd_panel_draw_bitmap(panel, x_start, y_start, x_end, y_end, color_data);
```

**讲解**：

- 背光是**全局状态**，不属于任何页面。所以官方 Display 页在 `exit()` 里
  把背光恢复成 100%——否则你调暗了退出菜单，整个菜单都看不见了；
- 屏幕**没有 MISO**，读不回像素，所以没有低成本的"截图"；
- 四角会被 BSP 裁成半径 30 的圆角（在 flush 时逐行遮罩），
  重要内容离边缘留 ≥14 px。

```c
// 退出页面时的标准收尾（demo_display.c:47）
void demo_display_exit(void) {
    bsp_display_backlight(100);          // 恢复全亮，免得菜单看不见
    if (s_scr) { lv_obj_delete(s_scr); s_scr = NULL; s_info = NULL; }
}
```

---

## D.3 LVGL 页面骨架（五个钩子）

**出处**：`main/demo.h` + 各 `demo_*.c`

这是你 90% 的时间在写的东西。完整可跑的最小版本：

```c
// ---- demo_hello.c ----
#include "demo.h"
#include "bsp_display.h"
#include "ui_pixel.h"
#include "lvgl.h"

static lv_obj_t *s_scr;
static lv_obj_t *s_value;
static int s_count;

// 框架调用时【已持有 LVGL 锁】：只建 UI，不做慢操作
void demo_hello_enter(void) {
    s_count = 0;
    s_scr = ui_pixel_screen_create("HELLO");

    s_value = ui_pixel_label(s_scr, "0", &lv_font_montserrat_20, UI_INK);
    lv_obj_set_pos(s_value, 0, 165);
    lv_obj_set_width(s_value, 240);
    lv_obj_set_style_text_align(s_value, LV_TEXT_ALIGN_CENTER, 0);

    lv_screen_load(s_scr);               // 最后一步才载入
}

// 框架调用时【已持有 LVGL 锁】：删 screen，指针全部置 NULL
void demo_hello_exit(void) {
    if (s_scr) { lv_obj_delete(s_scr); s_scr = NULL; s_value = NULL; }
}

// 【未持锁】：改 UI 前自己加短锁，拿不到就放弃本次更新
void demo_hello_key(bsp_btn_t btn, bsp_btn_ev_t ev) {
    if (ev != BSP_BTN_CLICK) return;
    if (!bsp_lvgl_lock(250)) return;     // ⚠ 超时就放弃，不要死等

    if (btn == BSP_BTN_UP)        s_count++;
    else if (btn == BSP_BTN_DOWN) s_count--;
    else if (btn == BSP_BTN_OK)   s_count = 0;
    lv_label_set_text_fmt(s_value, "%d", s_count);

    bsp_lvgl_unlock();
}
```

**讲解——三条不能破的规矩**：

1. **`enter` 只建 UI，`start` 才做慢操作。**
   `enter` 是持锁调用的，在里面建任务、初始化音频会让整个界面卡住；
2. **`exit` 之前 `stop` 必须成功。** `stop()` 返回非 `ESP_OK` 时
   框架会**中止退出、保留页面**，让你能重试——所以 `stop()` 里
   **不要强删任务**，超时就返回 `ESP_ERR_TIMEOUT`；
3. **删 screen 后把所有对象指针置 NULL。**
   这是为了下次 `enter` 不会拿到野指针。

> ⚠ **长按 OK 由 `main.c` 全局拦截为退出**，你的页面不用处理"返回"，
> 但也**吃不到长按事件**。

### 页面里要周期刷新：用 `lv_timer`

**出处**：`main/demo_battery.c`

```c
static lv_timer_t *s_timer;

static void tick(lv_timer_t *t) {        // 跑在 LVGL 任务里，【已持锁】
    (void)t;
    lv_label_set_text_fmt(s_soc, "%d %%", bsp_battery_soc());
}

void demo_battery_enter(void) {
    /* ...建 UI... */
    tick(NULL);                          // 先立刻显示一次，不用等第一个周期
    s_timer = lv_timer_create(tick, 1000, NULL);
}

void demo_battery_exit(void) {
    if (s_timer) { lv_timer_delete(s_timer); s_timer = NULL; }   // ⚠ 必须删
    if (s_scr) { lv_obj_delete(s_scr); s_scr = NULL; }
}
```

> ⚠ **退页不删 timer 是最高频的崩溃来源**：screen 已经删了，
> 定时器回调还在访问它。删的顺序必须是 **先 timer，后 screen**。

---

## D.4 中文显示

> 完整手把手（选字体、抽码点、`lv_font_conv`、编进工程、验证缺字）见**第 19 章**。
> 可编译示例：`snippets/03_chinese_font.c`。

**原理**（第 5.8 节讲过结论，第 19 章是完整手把手）：UTF-8 只解决"字符串怎么存"，**字形必须由字库提供**。
默认的 Montserrat 14/20 不含汉字，所以直接写中文会显示空白或方框。

### 方案 A：快速验证（内置 CJK 子集）

```text
# sdkconfig.defaults 增加一行，重新编译
CONFIG_LV_FONT_SOURCE_HAN_SANS_SC_16_CJK=y
```

```c
lv_obj_set_style_text_font(label, &lv_font_source_han_sans_sc_16_cjk,
                           LV_PART_MAIN | LV_STATE_DEFAULT);
```

代价：固件增大约 1 MB。**只用于验证和兜底。**

### 方案 B：生成应用子集（推荐）

**出处**：官方 `docs/development/engineering/lvgl-chinese-fonts.zh_CN.md`

```bash
lv_font_conv \
  --font /path/to/licensed-cjk-font.otf \
  --range 0x20-0x7E --symbols "加分减归零返回菜单确定上下" \
  --size 20 --bpp 4 --format lvgl --no-compress \
  --lv-font-name app_font_20 --lv-include lvgl.h \
  --output assets/fonts/app_font_20.c
```

```cmake
# main/CMakeLists.txt：在 idf_component_register(...) 【之后】追加
target_sources(${COMPONENT_LIB} PRIVATE
    "${CMAKE_CURRENT_LIST_DIR}/../assets/fonts/app_font_20.c")
```

```c
LV_FONT_DECLARE(app_font_20);            // 声明，不要 #include 字体 .c
lv_obj_set_style_text_font(label, &app_font_20, LV_PART_MAIN | LV_STATE_DEFAULT);
```

### fallback：中文 + 图标混排

**出处**：官方中文字体文档第 5 节

```c
LV_FONT_DECLARE(app_font_20);
static lv_font_t s_app_font_with_symbols;   // ⚠ 必须是可写的静态描述符

void app_fonts_init(void) {
    s_app_font_with_symbols = app_font_20;                  // 浅拷贝
    s_app_font_with_symbols.fallback = &lv_font_montserrat_20;  // 缺字时去查它
}
```

> ⚠ 三个坑：
> ① LVGL 9 的字段名是 **`fallback`**（v8 叫 `fallback_font`）；
> ② **不要**直接改 `const` 字体的 fallback（那要去掉 const，不安全），
>    官方做法是拷一份可写描述符；
> ③ 描述符必须**全程有效**，别放栈上。

### 缺字检查（改文案后必做）

```c
bool app_font_has_glyph(const lv_font_t *font, uint32_t codepoint) {
    if (font == NULL) return false;
    lv_font_glyph_dsc_t g = {0};
    return lv_font_get_glyph_dsc(font, &g, codepoint, 0) && !g.is_placeholder;
}
```

保留 `CONFIG_LV_USE_FONT_PLACEHOLDER=y`——**关掉它缺字会变成空白，问题反而看不见**。

---

## D.5 显示图片

> 完整手把手（转换脚本、EMBED_FILES、描述符、容量账、排错表）见**第 20 章**。
> 可编译示例：`snippets/04_image_rgb565.c`。

**出处**：`main/demo_barbapapa.c`

```c
// 素材进 Flash：const 放在 .rodata，不占 RAM
const lv_image_dsc_t bp_img_00 = {
    .header = {
        .magic = LV_IMAGE_HEADER_MAGIC,   // 0x19
        .cf    = LV_COLOR_FORMAT_RGB565,  // 0x12
        .flags = 0,
        .w = 200, .h = 240, .stride = 400, .reserved_2 = 0,
    },
    .data_size = 200u * 240u * 2u,
    .data = bp_imgdata_00,               // const uint8_t[]
};

// 使用
s_img = lv_img_create(s_scr);            // lv_image_create() 是 LVGL 9 正名
lv_img_set_src(s_img, &bp_img_00);       // 只换指针，不拷贝、不解码
```

**讲解**：

- `lv_img_*` 是 LVGL 9 保留的**兼容别名**，官方代码用的就是它，
  `lv_image_*` 与其行为一致；新代码建议用 `lv_image_*`；
- 切换图片是即时的——`set_src` 只是改了一个指向 Flash 的指针；
- `.bin` 素材前面有 **12 字节文件头**，生成 C 数组时要剥掉；
- **不要自己 swap 字节序**，port 在 flush 时统一处理（红蓝互换就是这个原因）。

---

## D.6 按键

**出处**：`main/demo_button.c`、`main/main.c`

### 回调只入队

```c
typedef struct { bsp_btn_t btn; bsp_btn_ev_t event; } input_event_t;

// ⚠ 运行在 button 组件的共享 esp_timer 任务里：只能入队/置标志，立即返回
static void on_key(bsp_btn_t btn, bsp_btn_ev_t ev, void *user) {
    (void)user;
    if (!s_input_ready || !s_input_queue) return;
    const input_event_t input = { .btn = btn, .event = ev };
    (void)xQueueSend(s_input_queue, &input, 0);   // 队列满则丢弃，不阻塞
}
```

### 四类事件怎么选

| 事件 | 触发时机 | 用在哪 |
| --- | --- | --- |
| `BSP_BTN_PRESS` | 按下瞬间 | 游戏（跳、射击）——**零等待** |
| `BSP_BTN_CLICK` | 按下并抬起 | 菜单确认 |
| `BSP_BTN_DOUBLE` | 双击 | 次要功能 |
| `BSP_BTN_LONG` | 按住 500 ms | **已被 main.c 全局拦截为退页** |

### 标定（换了分压电阻必做）

```c
int mv = bsp_button_read_mv();   // 松开 ≈3300；失败返回 -1
```

官方 Button 页每 100 ms 刷一次电压，就是给你标定用的：
逐个按住三键记下读数，取相邻两档中点，改 `bsp_pins.h` 的 `BSP_BTN_MV_TABLE`。

> ⚠ 判定窗口是 `{0,150} {150,447} {447,1900}`，来自 0 / 300 / 595 mV 三档。
> **不能改用内部上拉**（约 45 kΩ 且随温漂），换了电阻必须重新标定。

---

## D.7 音频

> 完整手把手（四步发声、分块、worker 模板、录音、采样率坑、低功耗）见**第 21 章**。
> 可编译示例：`snippets/05_audio_play.c`、`snippets/06_audio_worker.c`、
> `snippets/07_audio_drain.c`（排空等待 + 关机收尾 + sleep 单向门）。

**出处**：`main/demo_audio.c`（模板）+ `main/demo_barbapapa.c`（分块播放）

### 铁律

1. `bsp_audio_write/read` **阻塞到 DMA**（不是到"喇叭响完"），只能在 worker 任务里调用；
2. **要关 I2S / codec / 断电之前，先等 DMA 排空**（见下方"排空等待"）；
3. 格式切换、sleep/wake 必须**串行化**，切换前先停 PCM；
4. 分块写，块之间检查"要不要停"。

### ⚠ 排空等待：`write` 返回 ≠ 声音已经响完

`bsp_audio_write()` 的终点是 **I2S DMA 缓冲收下数据**，声音还在队列里排队。
`bsp_audio_prepare_deep_sleep()` 内部的 `i2s_channel_disable()` **不会等队列排空**，
剩下的数据直接丢弃——表现就是"道别语音一个字都没出来"。

```c
// 下一步要【关机/深睡/停 I2S】时，写完必须显式等待
static void wait_audio_drained(size_t bytes_written)
{
    uint32_t ms = (uint32_t)(bytes_written / 32);   // 16k/16bit/mono：秒 = 字节/32000
    vTaskDelay(pdMS_TO_TICKS(ms + 120));            // +120ms 覆盖 PA 斜坡与尾段
}

bsp_audio_write(bye_pcm, bye_bytes);
wait_audio_drained(bye_bytes);            // ← 少了这步就没声
bsp_audio_prepare_deep_sleep();
```

**只在"下一步要关音频/断电"时才需要等**；接着播下一段不用等（DMA 自己续上，
等待反而造成断续）。

> 可编译示例：`snippets/07_audio_drain.c`——含 `wait_audio_drained()`、
> 播完道别语再进 deep sleep 的完整序列，以及 `sleep()` 单向门的正确/错误写法对照。

### 播放一段 Flash 里的 PCM

```c
#define CHUNK_BYTES 2048        // barbapapa 用 2048 字节 = 1024 采样 = 64ms

static void play_voice(const uint8_t *pcm, uint32_t bytes) {
    if (bsp_audio_set_format(16000, 16, 1) != ESP_OK) return;   // 必须和素材一致
    bsp_audio_set_volume(75);                                    // 0~100

    uint32_t off = 0;
    while (off < bytes && !s_cancel) {          // ⚠ 每块都检查取消标志
        uint32_t n = bytes - off;
        if (n > CHUNK_BYTES) n = CHUNK_BYTES;
        if (bsp_audio_write(pcm + off, n) != ESP_OK) break;
        off += n;
    }
}
```

**为什么分块**：`bsp_audio_write` 会阻塞到 DMA 传送完成。
整段一次性写进去，中途你就**没有机会让它停下**——
用户切歌要等到播完。2048 字节 = 64 ms，块之间能检查一次取消标志。

> `.rodata` 里的 PCM 直接传给 `bsp_audio_write()` 是合法的：
> I2S 驱动会把数据拷进自己的 DMA 缓冲，不需要你先搬到 RAM。

### 录音

```c
#define CHUNK_SAMPLES 512       // demo_audio.c 用 512 采样（1024 字节）

size_t total = (size_t)SAMPLE_RATE * RECORD_SEC;
int16_t *rec = malloc(total * sizeof(int16_t));   // 3s@16k/16bit = 96 KB
if (!rec) {
    ESP_LOGE(TAG, "录音缓冲分配失败（可缩短 RECORD_SEC）");   // 无 PSRAM 常态
    return;
}
size_t got = 0;
while (got < total && !s_cancel) {
    size_t n = (total - got) < CHUNK_SAMPLES ? (total - got) : CHUNK_SAMPLES;
    if (bsp_audio_read(rec + got, n * sizeof(int16_t)) != ESP_OK) break;
    got += n;
}
free(rec);
```

> ⚠ 96 KB 的连续缓冲在无 PSRAM 的板子上**经常分配不到**。
> 官方代码的应对是打一条明确的日志建议缩短 `RECORD_SEC`，
> 而不是静默失败——这个态度值得学。

### 格式切换的坑

`bsp_audio_set_format()` 在格式变化时会内部 **close → open**
（绕过 esp_codec_dev 在已打开时不重配时钟的 bug）。
如果你绕过它直接操作 codec，16 kHz 播完再播 8 kHz **会以 16 k 时钟送出**——
音调和速度都快一倍。

---

## D.8 电量

**出处**：`main/demo_battery.c`

```c
int soc = bsp_battery_soc();   // 0~100，失败 -1
int mv  = bsp_battery_mv();    // mV，失败 -1

// ⚠ -1 必须优雅降级，不能当 0%，更不能崩
if (soc < 0) lv_label_set_text(s_soc, "-- %");
else         lv_label_set_text_fmt(s_soc, "%d %%", soc);
```

**讲解**：

- 芯片可能不应答（`bsp_battery_init()` 返回 `ESP_ERR_NOT_FOUND`），
  UI 上要能标记"该项不可用"；
- SOC% 是 CW2017 按 **BSP 内置的 520 mAh profile** 算出来的，
  不是标定级计量，别拿它做精确电量断言；
- UI 规范：右上角放电量，低电量（<20%）变色。

---

## D.9 存储：NVS

```c
#include "nvs_flash.h"
#include "nvs.h"

// 启动时一次（Wi-Fi/BLE 协议栈依赖它；失败【不要】自动 erase 用户数据）
esp_err_t ret = nvs_flash_init();
if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
    // 只有在确认"设置可以丢"时才 erase + 重新 init
}

void save_count(int32_t v) {
    nvs_handle_t h;
    if (nvs_open("myapp", NVS_READWRITE, &h) != ESP_OK) return;
    nvs_set_i32(h, "count", v);
    nvs_commit(h);          // ⚠ 不 commit 重启就丢
    nvs_close(h);
}

int32_t load_count(int32_t defv) {
    nvs_handle_t h;
    if (nvs_open("myapp", NVS_READONLY, &h) != ESP_OK) return defv;
    int32_t v = defv;
    nvs_get_i32(h, "count", &v);   // 键不存在时保留默认值
    nvs_close(h);
    return v;
}
```

**讲解**：

- 支持 i32/u32/i16/u8/字符串(`_str`)/二进制块(`_blob`)；
- **键名 ≤ 15 字符**；
- 有磨损：**不要每帧/每秒写**。状态变化时才写（番茄钟分支的做法）；
- 大素材（图片/音频）不要进 NVS，走 Flash 资源分区（第 9 章）。

---

## D.10 Wi-Fi

**出处**：`main/demo_wifi.c` + `main/demo_radio.c`；配网与取数见 `demo/blufi-provisioning` 分支与 IDF 组件
（对应章节：[10](10-network.md) / [10b](10b-provisioning.md) / [10c](10c-network-data.md)）

### 启动链（顺序不能乱）

```c
demo_radio_nvs_prepare();          // nvs_flash_init（协议栈依赖）
demo_radio_network_prepare();      // esp_netif_init + 默认事件循环

esp_netif_config_t cfg = ESP_NETIF_DEFAULT_WIFI_STA();
s_sta_netif = esp_netif_new(&cfg);
esp_netif_attach_wifi_station(s_sta_netif);
esp_wifi_set_default_wifi_sta_handlers();

wifi_init_config_t wcfg = WIFI_INIT_CONFIG_DEFAULT();
esp_wifi_init(&wcfg);
esp_wifi_set_storage(WIFI_STORAGE_RAM);   // 凭据只留 RAM，不写 NVS
esp_wifi_set_mode(WIFI_MODE_STA);
esp_wifi_start();
```

### 扫描

```c
esp_event_handler_instance_register(WIFI_EVENT, WIFI_EVENT_SCAN_DONE, scan_done, NULL, &h);
esp_wifi_scan_start(NULL, false);          // 非阻塞

// scan_done 回调里：
uint16_t total = 0;
esp_wifi_scan_get_ap_num(&total);
wifi_ap_record_t *recs = malloc(total * sizeof(wifi_ap_record_t));
esp_wifi_scan_get_ap_records(&total, recs);
```

### 连接

```c
wifi_config_t cfg = { 0 };
strcpy((char *)cfg.sta.ssid, "你的SSID");
strcpy((char *)cfg.sta.password, "你的密码");
cfg.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;
esp_wifi_set_config(WIFI_IF_STA, &cfg);
esp_wifi_connect();
```

> **拿到 `IP_EVENT_STA_GOT_IP` 才算真正联网**，不是 `esp_wifi_connect()` 返回就算。
> 断线重连要带退避与上限，别无限狂连。

### 凭据与重连退避

```c
// 凭据存哪：RAM（demo 选择，零副作用）/ FLASH（IDF 自动存，上电自动连）/ 自管 NVS
esp_wifi_set_storage(WIFI_STORAGE_RAM);   // 或 WIFI_STORAGE_FLASH

// 重连：指数退避 + 抖动 + 上限（★ 别在事件回调里 while/delay）
static void schedule_reconnect(int retry)
{
    int backoff = 1000 << (retry < 5 ? retry : 5);          // 1→2→4→8→16→32s
    if (backoff > 30000) backoff = 30000;
    backoff += esp_random() % 250;                          // 抖动，避免齐刷刷
    // 用 esp_timer / 软件定时器 / 队列通知自己的 worker，不要在回调里阻塞
    xTimerChangePeriod(s_timer, pdMS_TO_TICKS(backoff), 0);
}

// 断开原因：打印 reason，15/202=密码错、201=扫不到（想想 5 GHz）、200=信号弱
wifi_event_sta_disconnected_t *d = (wifi_event_sta_disconnected_t *)data;
ESP_LOGW(TAG, "ssid=%s rssi=%d reason=%d", (char *)d->ssid, d->rssi, d->reason);
```

> **确定性失败（密码错 2xx）不要无限重试**——回到配网界面让人重输。

### 配网骨架（`wifi_provisioning`，BLE / BLUFI）

**出处**：官方 `demo/blufi-provisioning` 分支 + IDF 组件 `wifi_provisioning`
（详见第 10b 章）

```cmake
# main/CMakeLists.txt
idf_component_register(SRCS "main.c" INCLUDE_DIRS "."
                       PRIV_REQUIRES wifi_provisioning nvs_flash ...)
```

```c
#include "wifi_provisioning/manager.h"
#include "wifi_provisioning/scheme_ble.h"

wifi_prov_mgr_config_t cfg = {
    .scheme = wifi_prov_scheme_ble,
    .scheme_event_handler = WIFI_PROV_SCHEME_BLE_EVENT_HANDLER_FREE_BTDM, // 配完释放 BT
};
ESP_ERROR_CHECK(wifi_prov_mgr_init(cfg));
esp_event_handler_register(WIFI_PROV_EVENT, ESP_EVENT_ANY_ID, &prov_event, NULL);

bool provisioned = false;
ESP_ERROR_CHECK(wifi_prov_mgr_is_provisioned(&provisioned));
if (!provisioned) {
    const char *pop = "abcd1234";        // WIFI_PROV_SECURITY_1 的 PoP
    ESP_ERROR_CHECK(wifi_prov_mgr_start_provisioning(
        WIFI_PROV_SECURITY_1, pop, "BLUFI_FoloPassport", NULL));
}
// 事件：WIFI_PROV_START → CRED_RECV → CRED_SUCCESS / CRED_FAIL(reason) → END
// 清凭据：wifi_prov_mgr_reset_provisioning();
```

> **STA 拿到 IP 才算配网成功**；"BLE 连上"不算。
> **旧凭据要在新凭据验证成功后才覆盖**；密码绝不进日志、绝不提交 Git。

### HTTP 流式取数（推荐写法）

**出处**：IDF `esp_http_client`（第 10c 章）

```c
#define MAX_BODY 8192
typedef struct { char *buf; size_t cap, len; bool overflow; } body_t;

static esp_err_t on_http_event(esp_http_client_event_t *evt)
{
    body_t *b = (body_t *)evt->user_data;
    switch (evt->event_id) {
    case HTTP_EVENT_ON_DATA:
        if (evt->data_len == 0) break;                       // 空事件跳过
        if (b->len + evt->data_len > b->cap) { b->overflow = true; break; }
        memcpy(b->buf + b->len, evt->data, evt->data_len);   // evt->data 回调后失效
        b->len += evt->data_len;
        break;
    case HTTP_EVENT_ERROR:        ESP_LOGE(TAG, "DNS/TCP/TLS/超时");  break;
    default: break;
    }
    return ESP_OK;
}

esp_http_client_config_t cfg = {
    .url = url, .method = HTTP_METHOD_GET,
    .timeout_ms = 8000,                 // ★ 必设
    .event_handler = on_http_event, .user_data = &b,
    .buffer_size = 1024,                // 内部单次接收缓冲，别设大
};
esp_http_client_handle_t c = esp_http_client_init(&cfg);
esp_err_t err = esp_http_client_perform(c);
int status = esp_http_client_get_status_code(c);
int64_t len = esp_http_client_get_content_length(c);   // 可能为 -1（chunked）
esp_http_client_cleanup(c);             // ★ 成败都要调，否则 socket 泄漏
```

**HTTPS 三件事**：证书（`.cert_pem` + `EMBED_TXTFILES`，或 `.crt_bundle_attach`）、
**时间（先 SNTP 再请求，否则证书"尚未生效"）**、内存（开 `CONFIG_MBEDTLS_DYNAMIC_BUFFER`）。

### SNTP 校时

```c
esp_sntp_config_t cfg = ESP_NETIF_SNTP_DEFAULT_CONFIG("pool.ntp.org");
cfg.server_from_dhcp = true;
cfg.start = true;
esp_netif_sntp_init(&cfg);
if (esp_netif_sntp_sync_wait(pdMS_TO_TICKS(10000)) == ESP_OK) { /* 已校时 */ }
// 失败也要能用：用 esp_timer_get_time() 的开机微秒数兜底
```

### 拆除（严格逆序）

```c
esp_wifi_scan_stop();
esp_wifi_stop();
esp_event_handler_instance_unregister(WIFI_EVENT, WIFI_EVENT_SCAN_DONE, h);
esp_wifi_deinit();
esp_netif_destroy_default_wifi(s_sta_netif);
```

**讲解**：这是"谁申请谁释放、顺序严格相反"的范本。
每一步都检查返回值，失败也继续往下拆——**不要带着半开资源逃跑**。

---

## D.11 BLE

**出处**：`main/demo_ble.c`

```c
#define DEVICE_NAME "FoloPassport"

// 1) 初始化
nimble_port_init();
ble_svc_gap_init();
ble_svc_gatt_init();
ble_svc_gap_device_name_set(DEVICE_NAME);
ble_hs_cfg.sync_cb  = on_sync;     // 控制器同步后才启动广播
ble_hs_cfg.reset_cb = on_reset;

// 2) NimBLE 需要自己的 host 任务
xTaskCreatePinnedToCore(host_task, "nimble_host", NIMBLE_HS_STACK_SIZE,
                        NULL, 5, &s_host_task);
// host_task 里：nimble_port_run();（不返回）

// 3) on_sync 里启动广播
ble_hs_util_ensure_addr(0);
ble_hs_id_infer_auto(0, &s_addr_type);
/* 填充 adv 字段（含FLAG、TX power、设备名、可选 128bit 服务 UUID） */
ble_gap_adv_start(s_addr_type, NULL, BLE_HS_FOREVER, &params, gap_event, NULL);
```

```c
// 拆除
ble_gap_adv_stop();
nimble_port_stop();                        // 等 host 任务停（2 秒超时）
// 收到 host_stopped 信号量后再：
nimble_port_deinit();
```

**讲解**：

- NimBLE **必须有自己的 host 任务**，这是它和 Wi-Fi 最大的不同；
- 配置边界（`sdkconfig.defaults`）：**只有 peripheral + broadcaster**，
  `MAX_CONNECTIONS=1`，没有 central/observer，**没有经典蓝牙**；
- 约 **73 KB 堆**——在总可用堆约 230 KB 的板子上是三分之一，
  很多项目直接砍掉 BLE 换内存。

---

## D.12 低功耗

**出处**：`main/demo_low_power.c`

### 浅睡（会返回，继续跑）

```c
esp_sleep_enable_timer_wakeup(2ULL * 1000ULL * 1000ULL);
bsp_audio_sleep();                 // 暂停 ES8311（幂等）
esp_light_sleep_start();
bsp_audio_wake();                  // 醒后恢复格式与音量
```

### 深睡（唤醒 = 重启，顺序不可乱）

```c
esp_sleep_enable_timer_wakeup(5ULL * 1000ULL * 1000ULL);

bsp_battery_sleep();               // 1) CW2017
bsp_audio_sleep();                 // 2) ES8311
bsp_audio_prepare_deep_sleep();    // 3) I2S：停时钟、引脚高阻（不可逆）
bsp_i2c_prepare_deep_sleep();      // 4) 共享 I2C（前面几步都要用它）

if (!bsp_lvgl_lock(1000)) {        // 5) 阻止 LVGL 再刷屏
    ESP_LOGE(TAG, "无法停止刷屏，重启恢复外设");
    esp_restart();
}
bsp_display_prepare_deep_sleep();  // 6) ST7789 Sleep In + 背光停

esp_deep_sleep_start();            // 正常不返回
ESP_LOGE(TAG, "意外返回，重启");     // 返回即异常
esp_restart();
```

**讲解**：

- 每步失败**只告警继续**——一个寄存器没写成功，不该让设备永远睡不下去；
- `prepare_deep_sleep()` 后本次运行**不可恢复**，必须立刻睡或重启；
- 唤醒源只有 **RTC 定时器**有板级证据。三个键接在 GPIO0 的 ADC 上，
  **不能想当然用 ext1**；真要用也别把引脚号当位掩码传（`1ULL << GPIO_NUM_0`）；
- 深睡后接续状态用 `RTC_DATA_ATTR` + 魔数：

```c
#define DEEP_SLEEP_MAGIC 0x464F4C4FUL
static RTC_DATA_ATTR uint32_t s_deep_sleep_magic;
static RTC_DATA_ATTR uint32_t s_deep_sleep_count;

// 冷启动时魔数不对 → 计数清零；真唤醒才累加
if (s_deep_sleep_magic != DEEP_SLEEP_MAGIC) s_deep_sleep_count = 0;
s_deep_sleep_magic = DEEP_SLEEP_MAGIC;
s_deep_sleep_count++;
```

---

## D.13 内存诊断

```c
#include "esp_heap_caps.h"

ESP_LOGI(TAG, "free=%u largest=%u",
    heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
    heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL));

// 任务栈水位线（单位 word，C3 上 ×4 字节）
UBaseType_t left = uxTaskGetStackHighWaterMark(NULL);
ESP_LOGI(TAG, "stack min free = %u words", (unsigned)left);
```

**讲解**：

- **总空闲大 ≠ 能分配大。** DMA 和显示缓冲要连续内部 RAM，
  所以 `largest_free_block` 比 `free_size` 更重要；
- 无 PSRAM 的基线数字：可用堆约 **230 KB**，**最大连续块 < 8 KB**；
- 崩溃日志出现 `Stack canary watchpoint triggered (任务名)` = 该任务栈溢出，
  调大 `xTaskCreate` 的栈参数；
- `idf.py size-components` 看哪个组件吃 Flash/RAM。

---

## D.14 通用并发模板（worker + 通知 + 停止握手）

**出处**：`demo_audio.c` / `demo_barbapapa.c` / `demo_low_power.c` 三处一致

这是全书**最值得背下来**的一段。凡是"页面里要跑慢活"都用这个：

```c
typedef enum { CMD_DO_WORK = 1, CMD_STOP } worker_cmd_t;

static TaskHandle_t     s_task;
static SemaphoreHandle_t s_stopped;      // worker → stop() 的"我停好了"
static volatile bool    s_cancel;        // stop() → worker 的"请停下"

static void worker(void *arg) {
    (void)arg;
    for (;;) {
        uint32_t cmd = 0;
        if (xTaskNotifyWait(0, UINT32_MAX, &cmd, portMAX_DELAY) != pdTRUE) continue;
        if (cmd == CMD_STOP) break;
        /* 干活：分块，每块检查 s_cancel */
    }
    // ⚠ 不自删：owner 可能还在等握手，自删后句柄失效
    xSemaphoreGive(s_stopped);
    for (;;) vTaskSuspend(NULL);         // 挂起等 owner 来删
}

esp_err_t page_start(void) {
    s_stopped = xSemaphoreCreateBinary();
    if (!s_stopped) return ESP_ERR_NO_MEM;
    s_cancel = false;
    if (xTaskCreate(worker, "worker", 4096, NULL, 4, &s_task) != pdPASS) {
        vSemaphoreDelete(s_stopped); s_stopped = NULL;   // 失败要清理
        return ESP_ERR_NO_MEM;
    }
    return ESP_OK;
}

esp_err_t page_stop(void) {
    TaskHandle_t task = s_task;
    if (!task) return ESP_OK;

    s_cancel = true;                                     // 先让它尽快跳出
    xTaskNotify(task, CMD_STOP, eSetValueWithOverwrite); // 覆盖旧值，不丢命令
    if (!s_stopped ||
        xSemaphoreTake(s_stopped, pdMS_TO_TICKS(2000)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;      // ⚠ 超时就报错，让框架中止退页、保留页面
    }
    vTaskDelete(task);               // 此时 worker 挂在 vTaskSuspend，安全
    s_task = NULL;
    vSemaphoreDelete(s_stopped); s_stopped = NULL;
    return ESP_OK;
}
```

**六条要点**（前四条是模板自带的，后两条是官方在硬件指南里额外强调的）：

1. **worker 不自删。** 自删后 owner 再 `vTaskDelete` 句柄就是野指针；
   ESP-IDF 里任务自删的栈回收时机也不好控制——官方注释明确写了这点；
2. **超时返回错误，不要强删。** 框架会保留页面让你重试；
3. **`eSetValueWithOverwrite`** 保证停止命令不会被旧命令覆盖掉；
4. **任务优先级 4**（与 LVGL 同级）。只有输入派发任务是 5，因为它持锁时间极短；
5. **停止超时后保留任务句柄与完成信号量，供后续重试。**
   别在超时分支里把 `s_task` / `s_stopped` 清成 NULL——清了就再也没有第二次机会，
   也失去了诊断信息（第 12.5.1 节）；
6. **不能让旧任务清空新任务的句柄。** 快速"退出→再进入"时，
   旧任务收尾跑到一半可能把新任务刚写好的句柄覆盖掉，
   于是新任务再也没人能停止它。判据是"这个句柄是不是**我这次启动的**"，不是"它是否非空"。

> 官方原文：音频、低功耗和 BLE 工作任务**在最后一次共享状态访问之后**才发完成确认，
> 随后挂起，由生命周期所有者删除。详见第 12.5.1 节。

worker 里要更新界面？自己加锁：

```c
static void set_status(const char *text) {       // demo_audio.c:39
    if (!bsp_lvgl_lock(500)) return;
    if (s_status) lv_label_set_text(s_status, text);
    bsp_lvgl_unlock();
}
```

---

## D.15 加一个新页面：五处改动

**出处**：官方基线 `main/` 的组织方式

| # | 文件 | 改什么 |
| --- | --- | --- |
| ① | 新建 `main/demo_hello.c` | 实现 `enter/exit/key`（慢活再加 `start/stop`） |
| ② | `main/demo.h` | 末尾声明三个（或五个）函数 |
| ③ | `main/CMakeLists.txt` | `SRCS` 列表里加 `"demo_hello.c"` |
| ④ | `main/main.c` | `DEMOS[]` 加一项 |
| ⑤ | `main/main.c` `app_main()` | `s_ok[N] = true;`（N = 你的下标） |

```cmake
idf_component_register(
    SRCS "main.c"
         ...
         "demo_low_power.c"
         "demo_hello.c"          # ← ③
    INCLUDE_DIRS "."
    REQUIRES bsp bt esp_event esp_hw_support esp_netif esp_timer esp_wifi nvs_flash
)
```

```c
// ④
static const demo_entry_t DEMOS[] = {
    /* ... */
    { .name = "Hello", .enter = demo_hello_enter, .exit = demo_hello_exit,
      .key = demo_hello_key },
};
```

> ⚠ `DEMOS[]` 的下标即菜单顺序。官方仓库 `folotoy/ai-passport` 的 `DEMOS[]` **只有 7 项**
> （Display/Button/Audio/Battery/Wi-Fi/BLE/Low Power），**没有** `BOOT_DEMO_INDEX` /
> `boot_into_demo()` 这类开机直达宏，开机即七卡片菜单。
> 第 18 章的「巴巴爸爸图鉴」是作者（你）用 **Trae** 生成的实战项目，**不在官方仓库**，
> 若要把它接回 `DEMOS[]` 作为新增第 8 项，注意下标、`s_ok[]` 索引、菜单位置三者必须一一对应
> （见第 16 章 PokeWalk 的 bug 成因）。

---

## D.16 素材进固件

### 小素材：`EMBED_FILES`

**出处**：`main/CMakeLists.txt`

```cmake
EMBED_FILES
     "assets/barbapapa/bbp_img_00.bin"
     "assets/barbapapa/bbp_voice_00.pcm"
```

```c
extern const uint8_t _binary_bbp_img_00_bin_start[];
extern const uint8_t _binary_bbp_img_00_bin_end[];
size_t len = _binary_bbp_img_00_bin_end - _binary_bbp_img_00_bin_start;
```

**规则**：`assets/foo/bar.bin` → `_binary_bar_bin_start`。
**路径中的 `/` 会丢掉，只留文件名。**

### 大素材：独立分区 + mmap

超过几百 KB 就别 EMBED 了（它会算进 app 分区）。
改 `partitions.csv` 开一个数据分区，再用 `esp_partition_mmap()` 映射。

> ⚠ mmap 的代价不是 RAM，是 **MMU 页**——ESP32-C3 只有 128 个，
> 小智项目实测占用了 83 个。先查空闲页够不够再 mmap。

### 自动生成的 .c（字体、素材表）

```cmake
# 不进 SRCS 显式列表，用 target_sources 追加
target_sources(${COMPONENT_LIB} PRIVATE
    "${CMAKE_CURRENT_LIST_DIR}/assets/barbapapa/barbapapa_assets.c"
    "${CMAKE_CURRENT_LIST_DIR}/assets/barbapapa/bbp_font_20.c"
)
```

> ⚠ **只读数据一定要 `const`。** 去掉 `const` 会被复制到 RAM——
> 这是"莫名其妙内存就没了"最常见的原因（第 11 章纪律 6）。

---

## D.17 一段"抄完就能跑"的最小应用

把上面各段拼起来，一个带按键、中文、图片、语音的完整页面大概长这样：

```c
// 状态
static lv_obj_t *s_scr, *s_title, *s_img, *s_status;
static TaskHandle_t s_task; static SemaphoreHandle_t s_stopped;
static volatile bool s_cancel; static volatile uint8_t s_idx;

// enter：只建 UI（持锁）
// exit ：删 UI（持锁，且 stop 已成功）
// key  ：改 s_idx → xTaskNotify → 自加锁刷新 UI
// start：bsp_audio_init() + 建 worker（不持锁，允许慢）
// stop ：s_cancel=true → Notify(STOP) → 等信号量 2s → vTaskDelete
// worker：set_format → 分块 2048 字节 write，每块检查 s_cancel
//       → 更新界面时 bsp_lvgl_lock(500)
```

完整版见**第 18 章**（角色图鉴），那里有逐行的解释和验收清单。

---

## D.18 每段代码的三条通例

抄完上面的代码，最后再对一遍这三条：

1. **回调里只入队。** 按键回调在共享 esp_timer 任务，阻塞 = 系统卡顿 + 看门狗；
2. **碰 `lv_*` 就加锁。** 不加锁的表现不是报错，是**随机花屏和随机重启**；
3. **退出顺序不能反。** timer → worker → UI；`stop()` 超时就报错让页面保留。

这三条覆盖了这块板上大约八成的崩溃。
