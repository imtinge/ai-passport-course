# A. API 速查表

全部来自官方基线 `components/bsp/include/`，可直接复制使用。

## A.1 BSP：显示与 LVGL（`bsp_display.h`）

```c
esp_err_t bsp_display_init(void);
esp_lcd_panel_handle_t bsp_display_panel(void);        // 逃生舱口：裸面板句柄
esp_lcd_panel_io_handle_t bsp_display_io(void);        // 逃生舱口：裸 IO 句柄
void bsp_display_backlight(uint8_t percent);           // 0–100，默认 0（不点亮=黑屏）
esp_err_t bsp_display_prepare_deep_sleep(void);
struct _lv_display_t *bsp_lvgl_init(void);             // 失败返回 NULL
bool bsp_lvgl_lock(int timeout_ms);                    // 超时返回 false
void bsp_lvgl_unlock(void);
```

标准顺序：

```c
bsp_display_init();          // 失败通常直接 return
bsp_lvgl_init();             // 返回 NULL 也要处理
bsp_display_backlight(100);  // ★ 必须在建 UI 之前
```

## A.2 BSP：按键（`bsp_button.h`）

```c
typedef enum { BSP_BTN_UP = 0, BSP_BTN_DOWN, BSP_BTN_OK } bsp_btn_t;

typedef enum {
    BSP_BTN_PRESS = 0,   // 按下瞬间（游戏用）
    BSP_BTN_CLICK,       // 单击（菜单用）
    BSP_BTN_DOUBLE,      // 双击
    BSP_BTN_LONG,        // 长按（返回用）
} bsp_btn_ev_t;

typedef void (*bsp_btn_cb_t)(bsp_btn_t btn, bsp_btn_ev_t ev, void *user);

esp_err_t bsp_button_init(bsp_btn_cb_t cb, void *user);
int bsp_button_read_mv(void);            // 轮询方案用；也是标定时读电压的手段
```

电压窗口（`bsp_pins.h`）：

```c
#define BSP_BTN_MV_TABLE  { {0, 150}, {150, 447}, {447, 1900} }   // 上 / 下 / 确定
#define BSP_BTN_SHORT_PRESS_MS  180
#define BSP_BTN_LONG_PRESS_MS   500
```

## A.3 BSP：音频（`bsp_audio.h`）

```c
esp_err_t bsp_audio_init(void);
esp_err_t bsp_audio_set_format(uint32_t hz, uint8_t bits, uint8_t ch);
esp_err_t bsp_audio_write(const void *pcm, size_t bytes);   // 阻塞！放任务里
esp_err_t bsp_audio_read(void *pcm, size_t bytes);          // 阻塞！
void bsp_audio_set_volume(uint8_t percent);
esp_err_t bsp_audio_sleep(void);                            // ⚠ 之后 write 一律失败
esp_err_t bsp_audio_wake(void);                             //   ↑ 必须 wake 才恢复
esp_err_t bsp_audio_prepare_deep_sleep(void);               // 内部 disable I2S，不等 DMA 排空
```

推荐参数：`bsp_audio_set_format(16000, 16, 1)`。
**`bytes` = 采样数 × 2**（int16）。

三条容易搞错的语义：

| 说法 | 真相 |
| --- | --- |
| `write` 返回 = 播完了 | ❌ 只阻塞到 **I2S DMA 收下数据**，声音还在排队 |
| `sleep()` 之后还能接着write | ❌ `sleep()` 会复位 codec 状态，之后 `set_format` / `write` **全部失败且静默** |
| `prepare_deep_sleep()` 会播完队列 | ❌ 它内部 `i2s_channel_disable()` **直接丢弃**未播数据 |

**关机/深睡前要等 DMA 排空**（见第 7.2 节）：

```c
bsp_audio_write(bye_pcm, bye_bytes);
vTaskDelay(pdMS_TO_TICKS(bye_bytes / 32 + 120));   // 16k/16bit/mono：字节/32000 秒
```

## A.4 BSP：电量（`bsp_battery.h`）

```c
esp_err_t bsp_battery_init(void);
int bsp_battery_soc(void);      // 0–100；失败返回负数 → 显示 "--"
int bsp_battery_mv(void);       // 毫伏；失败返回负数
esp_err_t bsp_battery_sleep(void);
```

**无法检测充电状态**（没有 charge-detect GPIO）。

## A.5 BSP：I2C（`bsp_i2c.h`）

```c
esp_err_t bsp_i2c_init(void);                      // 最先初始化
i2c_master_bus_handle_t bsp_i2c_bus(void);
esp_err_t bsp_i2c_scan(void);                      // 调试利器：打印总线上的设备
esp_err_t bsp_i2c_prepare_deep_sleep(void);
```

总线上应该有：`0x18`（ES8311 音频）、`0x63`（CW2017 电量计）。

## A.6 BSP：引脚（`bsp_pins.h`）

```c
#define BSP_LCD_W  240
#define BSP_LCD_H  320
#define BSP_LCD_MOSI 9   #define BSP_LCD_SCLK 8
#define BSP_LCD_CS   1   #define BSP_LCD_DC   20
#define BSP_LCD_RST  (-1)          // 未接 MCU，软复位
#define BSP_LCD_BL   21            // 背光 LEDC
#define BSP_LCD_INVERT_COLOR 1     // 出厂需反色

#define BSP_BTN_ADC_UNIT     ADC_UNIT_1
#define BSP_BTN_ADC_CHANNEL  ADC_CHANNEL_0    // GPIO0

#define BSP_I2C_SDA 10   #define BSP_I2C_SCL 7
#define BSP_I2C_ES8311_ADDR 0x18
#define BSP_I2C_CW2017_ADDR 0x63

#define BSP_I2S_MCLK 6  #define BSP_I2S_BCLK 5  #define BSP_I2S_WS 3
#define BSP_I2S_DOUT 2  #define BSP_I2S_DIN  4
#define BSP_I2S_PA_CTRL (-1)       // 功放不可控
```

## A.7 常用 ESP-IDF API

### 系统

```c
esp_get_free_heap_size()               // 当前空闲
esp_get_minimum_free_heap_size()       // 历史最低（最有价值）
heap_caps_get_largest_free_block(MALLOC_CAP_8BIT)   // 最大连续块
esp_restart()                          // 重启
esp_reset_reason()                     // 上次重启原因
esp_timer_get_time()                   // 开机微秒数（int64）
esp_random()                           // 随机数
```

### 日志

```c
ESP_LOGE(TAG, "...");   ESP_LOGW  ESP_LOGI  ESP_LOGD  ESP_LOGV
esp_log_level_set("tag", ESP_LOG_DEBUG);
esp_err_to_name(err);   ESP_ERROR_CHECK(x);
```

### FreeRTOS

```c
xTaskCreate(fn, "name", stack_bytes, arg, prio, &handle)
xTaskCreateStatic(fn, "name", depth, arg, prio, stack_buf, &tcb)
xTaskCreatePinnedToCore(fn, "name", stack, arg, prio, &handle, 0)
vTaskDelete(handle)
vTaskDelay(pdMS_TO_TICKS(ms))
uxTaskGetStackHighWaterMark(NULL)      // 剩余栈

xQueueCreate(depth, item_size)
xQueueSend(q, &item, 0)                // 0 = 不阻塞
xQueueReceive(q, &item, portMAX_DELAY)

xSemaphoreCreateBinary()  xSemaphoreGive  xSemaphoreTake
xSemaphoreCreateMutex()
xEventGroupCreate()  xEventGroupSetBits  xEventGroupWaitBits
```

### NVS

```c
nvs_flash_init()   nvs_flash_erase()
nvs_open("ns", NVS_READWRITE, &h)
nvs_set_u8/u16/u32/i32/str/blob(h, "key", val)
nvs_get_u8/u16/u32/i32/str/blob(h, "key", &val)
nvs_commit(h)      // ★ 不 commit 就丢
nvs_close(h)
```

### 分区与素材

```c
esp_partition_find_first(ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_ANY, "label")
esp_partition_mmap(part, 0, part->size, SPI_FLASH_MMAP_DATA, &addr, &handle)
esp_partition_read(part, offset, buf, size)
spi_flash_mmap_get_free_pages(SPI_FLASH_MMAP_DATA)   // mmap 前先查页够不够

esp_vfs_spiffs_register(&(esp_vfs_spiffs_conf_t){
    .base_path="/voices", .partition_label="voicefs",
    .max_files=8, .format_if_mount_failed=true })
```

### 睡眠

```c
esp_sleep_get_wakeup_cause()               // 开机第一件事查它
esp_sleep_enable_timer_wakeup(us)
esp_sleep_enable_gpio_wakeup()
gpio_wakeup_enable(GPIO_NUM_0, GPIO_INTR_LOW_LEVEL)   // ★ 引脚号，不是位掩码
esp_deep_sleep_start()                     // 正常不返回
```

### Wi-Fi（第 10 章）

```c
esp_netif_init()
esp_event_loop_create_default()
esp_netif_create_default_wifi_sta()
esp_wifi_init(&(wifi_init_config_t)WIFI_INIT_CONFIG_DEFAULT())
esp_wifi_set_mode(WIFI_MODE_STA)
esp_wifi_set_config(WIFI_IF_STA, &cfg)
esp_wifi_set_storage(WIFI_STORAGE_RAM)     // 或 WIFI_STORAGE_FLASH（自动存 NVS）
esp_wifi_start()
esp_wifi_connect()
esp_wifi_scan_start(&cfg, false)           // ★ block=false，别阻塞
esp_wifi_scan_get_ap_num(&num)             // 先取总数
esp_wifi_scan_get_ap_records(&num, aps)    // 再取记录（不取不释放缓存）
esp_wifi_sta_get_ap_info(&ap)              // 连着的时候查当前 RSSI/信道
esp_wifi_disconnect()  esp_wifi_stop()  esp_wifi_deinit()
esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, handler, NULL)
esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, handler, NULL)
```

事件：`WIFI_EVENT_STA_START` / `STA_CONNECTED` / `STA_DISCONNECTED` / `SCAN_DONE` /
`WIFI_EVENT_AP_STACONNECTED` → `IP_EVENT_STA_GOT_IP`（★ 唯一"已联网"标志）/
`IP_EVENT_STA_LOST_IP` / `IP_EVENT_AP_STAIPASSIGNED`（SoftAP 下发 IP）。

断开 reason：`wifi_event_sta_disconnected_t::reason`
`15/202`=密码错 · `201`=`NO_AP_FOUND`（想想 5 GHz）· `200`=`BEACON_TIMEOUT`（信号弱）。

### 校时 SNTP

```c
esp_sntp_config_t c = ESP_NETIF_SNTP_DEFAULT_CONFIG("pool.ntp.org");
c.server_from_dhcp = true; c.start = true;
esp_netif_sntp_init(&c)
esp_netif_sntp_sync_wait(ticks)      // 带超时；返回 ESP_TIMEOUT 时用开机时长兜底
esp_netif_sntp_deinit()
time() / localtime() / settimeofday()
```

### HTTP 客户端（第 10c 章）

```c
esp_http_client_init(&cfg)      esp_http_client_perform(client)
esp_http_client_set_url(c,url)  esp_http_client_set_method(c,HTTP_METHOD_POST)
esp_http_client_set_header(c,"Content-Type","application/json")
esp_http_client_set_post_field(c,body,len)
esp_http_client_get_status_code(client)
esp_http_client_get_content_length(client)      // 可能 -1（chunked）
esp_http_client_cleanup(client)                 // ★ 成败都要调
// 手动模式（下载大文件）
esp_http_client_open(c,0) → esp_http_client_fetch_headers(c)
  → esp_http_client_read(c,buf,len) → esp_http_client_close(c)
// 事件：HTTP_EVENT_ON_CONNECTED / ON_HEADER / ON_DATA / ON_FINISH / ERROR / DISCONNECTED
```

常用 `esp_http_client_config_t` 字段：`timeout_ms`（必设）、`event_handler`+`user_data`、
`buffer_size`、`cert_pem`（+`EMBED_TXTFILES`）、`crt_bundle_attach`、`use_global_ca_store`、
`max_redirection_count`、`keep_alive_enable`、`skip_cert_common_name_check`（仅调试）。

### 配网（第 10b 章，组件 `wifi_provisioning`）

```c
wifi_prov_mgr_init(cfg)                     // cfg.scheme = wifi_prov_scheme_ble
wifi_prov_mgr_is_provisioned(&provisioned)
wifi_prov_mgr_start_provisioning(WIFI_PROV_SECURITY_1, pop, "BLUFI_FoloPassport", NULL)
wifi_prov_mgr_stop_provisioning()  wifi_prov_mgr_deinit()
wifi_prov_mgr_reset_provisioning()          // 清除凭据
// 事件 WIFI_PROV_EVENT：INIT / START / CRED_RECV / CRED_FAIL / CRED_SUCCESS / END
wifi_prov_mgr_get_wifi_disconnect_reason(&reason)
```

### JSON（组件 `json` / cJSON）

```c
cJSON_ParseWithLength(buf, len)     // ★ 传长度，别让它自己 strlen
cJSON_GetObjectItem(root, "key")    cJSON_IsNumber() / cJSON_IsString()
cJSON_GetStringValue(item)          cJSON_Delete(root)     // ★ 一定删
```

## A.8 常用 LVGL API

### 对象

```c
lv_obj_create(parent)      lv_obj_delete(obj)     lv_obj_clean(obj)
lv_obj_set_size(obj, w, h) lv_obj_set_pos(obj, x, y)
lv_obj_align(obj, LV_ALIGN_TOP_MID, x, y)     lv_obj_center(obj)
lv_obj_add_flag(obj, LV_OBJ_FLAG_HIDDEN)      lv_obj_remove_flag(...)
lv_screen_load(scr)        lv_obj_invalidate(obj)
```

### 文本

```c
lv_label_create(parent)
lv_label_set_text(label, "abc")
lv_label_set_text_fmt(label, "%d %%", soc)
lv_label_set_long_mode(label, LV_LABEL_LONG_MODE_SCROLL_CIRCULAR)
```

### 样式（最后一个参数是 selector，通常传 0）

```c
lv_obj_set_style_bg_color(obj, lv_color_hex(0xFFE066), 0)
lv_obj_set_style_bg_opa(obj, LV_OPA_COVER, 0)
lv_obj_set_style_text_color(obj, lv_color_hex(UI_INK), 0)
lv_obj_set_style_text_font(obj, &lv_font_montserrat_14, 0)
lv_obj_set_style_text_align(obj, LV_TEXT_ALIGN_CENTER, 0)
lv_obj_set_style_border_width(obj, 4, 0)
lv_obj_set_style_radius(obj, 0, 0)
lv_obj_set_style_pad_all(obj, 8, 0)
```

### 图片（LVGL 9 用 `lv_image_*`，不是 `lv_img_*`）

```c
lv_obj_t *img = lv_image_create(parent);
lv_image_set_src(img, &my_image_dsc);      // 传 const lv_image_dsc_t*
```

手工构造描述符（`.bin` 素材要**剥掉前 12 字节头**才填进 `data`）：

```c
const lv_image_dsc_t my_img = {
    .header = {
        .magic = LV_IMAGE_HEADER_MAGIC,   // 0x19
        .cf    = LV_COLOR_FORMAT_RGB565,  // 0x12（标准小端，别用 SWAPPED 的 0x1B）
        .flags = 0,
        .w = 200, .h = 240, .stride = 400, .reserved_2 = 0,
    },
    .data_size = 200u * 240u * 2u,
    .data = my_pixels,
};
```

### 定时器与动画

```c
lv_timer_create(cb, period_ms, user)     lv_timer_delete(t)  lv_timer_reset(t)
lv_anim_init(&a)  lv_anim_set_var(&a, obj)  lv_anim_set_values(&a, from, to)
lv_anim_set_exec_cb(&a, cb)  lv_anim_set_duration(&a, ms)  lv_anim_start(&a)
```

### LVGL 8 → 9 拼写差异（搜旧教程时对照）

| LVGL 8 | LVGL 9 |
| --- | --- |
| `lv_scr_load()` | `lv_screen_load()` |
| `lv_obj_del()` / `lv_obj_del_async()` | `lv_obj_delete()` / `lv_obj_delete_async()` |
| `lv_disp_t` / `lv_disp_get_default()` | `lv_display_t` / `lv_display_get_default()` |
| `lv_disp_draw_buf_t` | `lv_draw_buf_t` |
| `lv_img_*` / `lv_img_set_src` | `lv_image_*` / `lv_image_set_src` |

### 中文字体：lv_font_conv 命令

```bash
lv_font_conv \
  --font SourceHanSansSC-Regular.otf \
  --range 0x20-0x7E \
  --symbols "$(cat charset.txt)" \
  --size 20 --bpp 4 --format lvgl --no-compress \
  --lv-font-name app_font_20 --lv-include lvgl.h \
  --output app_font_20.c
```

```cmake
target_sources(${COMPONENT_LIB} PRIVATE "${CMAKE_CURRENT_LIST_DIR}/../assets/fonts/app_font_20.c")
```

```c
LV_FONT_DECLARE(app_font_20);
lv_obj_set_style_text_font(label, &app_font_20, LV_PART_MAIN | LV_STATE_DEFAULT);
```

| 参数 | 说明 |
| --- | --- |
| `--symbols` | 要抽的**字符**（不是码点），**不接文件路径**，靠 shell 展开 |
| `--size` | 每个字号单独生成一个文件 |
| `--bpp` | 1 最省 Flash，4 抗锯齿 |
| `--lv-font-name` | 生成的 C 符号名（**变量名 = 文件名去掉扩展名**） |

方案 A 快速验证：`CONFIG_LV_FONT_SOURCE_HAN_SANS_SC_16_CJK=y`
→ `&lv_font_source_han_sans_sc_16_cjk`（约 1200 字，**仅验证用**）。

## A.9 命令速查

```bash
idf.py set-target esp32c3
idf.py build
idf.py -p COM4 flash monitor          # 退出 Ctrl+]
idf.py menuconfig
idf.py size / size-components
idf.py merge-bin -o build/firmware.bin
idf.py fullclean
```

```bash
riscv32-esp-elf-addr2line -pfiaC -e build/x.elf 0x4200abcd   # panic 地址 → 行号
xtensa-esp32-elf-addr2line ...                                # ESP32/S2/S3 用这个
```

## A.10 内存数字（贴在显示器上）

```text
SRAM                    约 400 KB
可用堆（跑起 LVGL+WiFi） 约 230 KB
最大连续空闲块          < 8 KB
整屏 240×320 RGB565     150 KB（放不下）
flash-MMU 页            128 个（mmap 用掉一个就少一个）
栈上数组上限            1 KB
任务栈常见值            4096 字节
LVGL 池推荐             24 KB
最低安全剩余堆          30 KB
```

## A.11 官方仓库关键文件索引（"去哪儿找"）

按图索骥用。路径相对于官方基线仓库根目录。

| 你想找什么 | 看哪里 |
| --- | --- |
| 引脚 / 硬件参数（唯一来源） | `components/bsp/include/bsp_pins.h` |
| BSP API 头文件 | `components/bsp/include/`：`bsp_display.h`、`bsp_button.h`、`bsp_audio.h`、`bsp_battery.h`、`bsp_i2c.h` |
| 应用入口与调度 | `main/main.c` |
| 页面接口 / 注册（`demo_entry_t`） | `main/demo.h` |
| 导航状态机 | `main/demo_navigation.{h,c}` |
| 各能力示例 | `main/demo_display.c`、`demo_button.c`、`demo_audio.c`、`demo_battery.c`、`demo_wifi.c`、`demo_ble.c`、`demo_low_power.c` |
| 分区 / 配置 | `partitions.csv`、`sdkconfig.defaults`、`main/CMakeLists.txt` |
| 门禁与验证 | `tools/validate.sh`（总入口）、`verify_firmware.py`（合并镜像布局校验）、`archive_firmware.py`（按 sha256 归档）、`check_repo.py`（静态检查） |
| 主机端 C 测试 | `tests/test_bsp_*.c`、`tests/test_demo_*.c`（头文件桩在 `tests/{audio,bsp,demo}_stubs/`） |
| 官方工程文档 | `docs/development/engineering/`：`build-and-test`、`firmware-layout`、`coding-conventions`、`lvgl-chinese-fonts`、`wifi-provisioning` |
| 硬件设计与验收 | `docs/hardware-design/` |

一个有用的观察：**官方仓库带一套"不需要设备就能跑"的主机测试**
（`tests/` 下的 C 测试 + Python 测试）。这正是第 18.6 节那两级门禁的来源——
把"能在 PC 上验证的"和"必须插设备验证的"分开，是这套工程规范的核心思路。

## A.12 动手前红线清单（一页纸）

做设计、估预算、排查"怎么又炸了"之前，先把这张表扫一遍。
每一项都来自前面某章，这里只做**汇总 + 快速定位**，数字变了以原章节为准。

| 红线 | 数字 | 为什么是红线 | 去哪查 |
| --- | --- | --- | --- |
| 没有 PSRAM | — | 大数组/大图/大字体只能留 Flash 或静态，不能 malloc 一大块 | 1.1 / 11.1 |
| 最小空闲堆下限 | **> 30 KB** | 低于此 OTA、BLE、音频峰值叠加会翻车 | 11.1 / 23.3 |
| LVGL 绘制缓冲 | **40 行 ≈ 19.2 KB** | 源码 `BSP_LVGL_DRAW_BUFFER_LINES=40`；改小省内存但掉帧 | 5.3 / E.7 |
| LVGL 内存池 | 推荐 **24 KB** | 独立从内部 RAM 划出，不占你 `malloc` 的堆 | 11.4 |
| I2S DMA 缓冲 | **90 ms**（6 desc × 240 frame @ 16 kHz） | UI 一卡就爆音的量化边界 | 10c.5 |
| 电池容量 | **520 mAh**（优特利电芯） | 电量预算、待机电流都基于它 | 8.1 |
| 栈上数组上限 | **≤ 1 KB** | 超过就栈溢出（静默杀手） | 11.2 纪律 1 |
| 最大连续空闲块 | **< 8 KB** | 总堆够 ≠ 连续块够，mmap/大结构会失败 | 11.1 |
| 整屏 240×320 RGB565 | **150 KB**（放不下堆） | 必须 mmap 或分块，不能整屏驻留 RAM | 9.3 / 11.1 |
| factory 分区 | `0x10000` 起，长 `0x7f0000` | 默认布局**无 OTA 槽**，改分区表才能 OTA | 1.6 / 9.1 / 10c.6 |
| flash-MMU 页 | 128 个 | mmap 每开一个文件用掉一页，用掉就少 | 9.3 方案 B |
| 任务栈常见值 | **4096 B** | 含 LVGL 调用时要更大，且用静态栈更稳 | 7.4 / 11.2 纪律 2 |

**使用姿势**：新建一个玩法前，先把"屏幕 + 音频 + 联网 + 字体"各自的峰值堆加起来，
对照 30 KB 下限看还剩多少；任何一项超出，先回这一页改方案，别等烧进去再救。
