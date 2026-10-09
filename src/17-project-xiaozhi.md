# 17. 实战五：小智 AI 对话（另一套架构）

| 项目 | 值 |
| --- | --- |
| 排名 | **#1** |
| 下载量 | **7244**（第二名 2725，断层领先） |
| 仓库 | `github.com/FoloToy/folo-ai-passport-xiaozhi` |
| 规模 | `main/` 8 个 .cc（3625 行）+ 45 个子目录源文件 |
| IDF | **≥ 6.0.1**（推荐 6.1），**不支持 5.x** |
| 语言 | **C++（.cc）**，不是 C |

**为什么拆解它**：不是让你学它的代码（那是 C++），而是学它的**架构**。
另外，它是社区里下载量断层第一的项目——
**如果你想知道“用户最想要什么”，答案是 AI 语音对话。**

## 17.1 它和前四个项目都不一样

| | 前四个项目 | 小智 |
| --- | --- | --- |
| 语言 | C | **C++** |
| 硬件抽象 | `components/bsp` | **自己的 `Board` 基类** |
| 分区表 | 顶层 `partitions.csv` | **`partitions/v2/16m_c3.csv`** |
| IDF | 5.5.3 | **≥ 6.0.1** |
| 支持板型 | 只有 AI Passport | **171 种变体** |
| 事件模型 | 回调 + 队列 | **单线程事件循环** |

**为什么要自己搞一套 Board 抽象？** 因为它要支持 171 种板子。
`bsp_*` 这种“扁平函数”的写法在多板型下会失控，
于是它用了面向对象的做法：

```text
main/boards/
├── common/   board.cc/.h  wifi_board.cc/.h  backlight.cc/.h  button.cc/.h
└── folotoy/ai-passport/
              ai_passport_board.cc   ← AI Passport 的具体实现
              config.h               ← 引脚与参数
              cw2017_battery_monitor.cc/.h
```

板子是一个**类**，换板子 = 换一个派生类。这是合理的设计，
代价是你要写 C++。

## 17.2 入口只有 29 行

> 源码：`main/main.cc`（全文）

```cpp
extern "C" void app_main(void)
{
    // Initialize NVS flash for WiFi configuration
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "Erasing NVS flash to fix corruption");
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    // Initialize and run the application
    auto& app = Application::GetInstance();
    app.Initialize();
    app.Run();  // This function runs the main event loop and never returns
}
```

**这是第 2 章说的“写法 B”**：`app_main` 永不返回。

真正的生命周期在 `Application::Initialize()`（10 步）和 `Run()` 里。

## 17.3 核心架构：单线程事件循环

> 源码：`main/application.cc`
>
> 术语提示：这里的“单线程”是描述小智这套架构的惯用说法，
> 落到 ESP-IDF 里就是**一个任务**在跑主循环（本书统一叫“任务”，见第 2.8 节）。

```cpp
void Application::Run() {
    vTaskPrioritySet(nullptr, 10);        // 主任务优先级提到 10

    const EventBits_t ALL_EVENTS =
        MAIN_EVENT_SCHEDULE | MAIN_EVENT_SEND_AUDIO | MAIN_EVENT_WAKE_WORD_DETECTED |
        MAIN_EVENT_VAD_CHANGE | MAIN_EVENT_CLOCK_TICK | MAIN_EVENT_ERROR |
        MAIN_EVENT_NETWORK_CONNECTED | MAIN_EVENT_NETWORK_DISCONNECTED | ...;

    while (true) {
        auto bits = xEventGroupWaitBits(event_group_, ALL_EVENTS,
                                        pdTRUE, pdFALSE, portMAX_DELAY);
        // 按位处理各种事件
        if (bits & MAIN_EVENT_SEND_AUDIO) { /* ... */ }
        if (bits & MAIN_EVENT_CLOCK_TICK)  { /* ... */ }
    }
}
```

**这个设计的精髓在于**：所有回调（音频、唤醒词、网络、按键）
**一律只做一件事——`xEventGroupSetBits()`**，
真正的处理全部回到这个循环里做。

**好处**：LVGL、codec、协议栈永远只在一条线程上被访问，
**不需要任何锁**。这在第 12 章讲过，是并发问题最优雅的解法之一。

代价：所有处理必须快，不能在这个循环里阻塞。

## 17.4 招牌实现：三个键共用一路 ADC

> 源码：`main/boards/folotoy/ai-passport/ai_passport_board.cc`

```cpp
        // One ADC1 unit shared by all three ladder keys. AdcButton reuses the
        // handle when adc_config.adc_handle is non-null, so the same physical
        // pin can decode several keys without "adc1 is already in use".
        adc_oneshot_unit_init_cfg_t init_cfg = { .unit_id = ADC_UNIT_1 };
        ESP_ERROR_CHECK(adc_oneshot_new_unit(&init_cfg, &adc_handle_));

        button_adc_config_t adc_cfg = {};
        adc_cfg.adc_handle = &adc_handle_;      // ★ 复用同一个句柄
        adc_cfg.unit_id = ADC_UNIT_1;
        adc_cfg.adc_channel = ADC_CHANNEL_0;    // GPIO0

        adc_cfg.button_index = kAdcButtonUp;    // UP:   ~0 mV
        adc_cfg.min = BSP_ADC_BUTTON_UP_MIN;    // 0
        adc_cfg.max = BSP_ADC_BUTTON_UP_MAX;    // 150
        adc_button_[kAdcButtonUp] = new AdcButton(adc_cfg);

        adc_cfg.button_index = kAdcButtonDown;  // DOWN: ~300 mV
        adc_cfg.min = BSP_ADC_BUTTON_DOWN_MIN;  // 150
        adc_cfg.max = BSP_ADC_BUTTON_DOWN_MAX;  // 447
        adc_button_[kAdcButtonDown] = new AdcButton(adc_cfg);

        adc_cfg.button_index = kAdcButtonOk;    // OK:   ~595 mV
        adc_cfg.min = BSP_ADC_BUTTON_OK_MIN;    // 447
        adc_cfg.max = BSP_ADC_BUTTON_OK_MAX;    // 1900
        adc_button_[kAdcButtonOk] = new AdcButton(adc_cfg);

        // Button callbacks run on the button task; schedule all UI/audio
        // work onto the main task so LVGL and codec access stay on one thread.
        auto up = adc_button_[kAdcButtonUp];
        up->OnClick([this]() {
            Application::GetInstance().Schedule([this]() { ChangeVolume(10); });
        });
```

（电压窗口和官方 `bsp_pins.h` 完全一致：0/150/447/1900——
**这是硬件事实，谁也改不了。**）

## 17.5 config.h 里那些“别乱改”的注释

> 源码：`main/boards/folotoy/ai-passport/config.h`

```c
// Keep the C3 codec path at the protocol/native 16 kHz rate.  The C3 has no
// PSRAM; forcing a 16 kHz -> 24 kHz resampler allocates a temporary buffer
// during playback and can fragment the remaining internal SRAM.
```

```c
// Amplifier enable is not wired to the MCU (always enabled on Passport).
#define AUDIO_CODEC_PA_PIN       GPIO_NUM_NC
```

```c
// Display: ST7789 (ST7789P3) 240x320 portrait, 4-line SPI.
// MOSI-only (no MISO), reset is a software reset (RST not wired).
#define DISPLAY_RST_PIN         GPIO_NUM_NC
#define DISPLAY_INVERT_COLOR true   // this panel ships inverted (needs INVON)
```

```c
// CW2017 fuel gauge is optional; a missing chip just disables battery UI.
```

```c
// CW2017 reports no charge state and the Passport has no charge-detect
// GPIO, so report a plain (discharging) reading.
```

**这几条和本书第 1、4、8 章讲的是同一批事实**——
只是换了个项目、换了个语言。这正说明它们是**硬件事实**，不是某个 fork 的偏好。

## 17.6 素材：独立 assets 分区 + mmap

```csv
# partitions/v2/16m_c3.csv
nvs,      data, nvs,     0x9000,    0x4000,
otadata,  data, ota,     0xd000,    0x2000,
phy_init, data, phy,     0xf000,    0x1000,
ota_0,    app,  ota_0,   0x20000,   0x3f0000,
ota_1,    app,  ota_1,   ,          0x3f0000,
assets,   data, spiffs,  0x800000,  4000K
```

注意 **OTA 双分区**（`ota_0` / `ota_1` + `otadata`）——
这是它和其他项目的又一个区别：**支持 OTA 升级**。

素材读取走 mmap（`main/assets.cc`）：

```c
esp_partition_find_first → esp_partition_read(header)
  → spi_flash_mmap_get_free_pages(SPI_FLASH_MMAP_DATA)
  → esp_partition_mmap(...) → 校验 → 按 mmap_assets_table 索引取数据
```

先查空闲 MMU 页够不够，再 mmap——**这是个好习惯**（第 9.3 节讲过，
C3 只有 128 个 MMU 页）。

## 17.7 省内存配置（可以直接抄）

> 源码：`sdkconfig.defaults.esp32c3`

```text
CONFIG_ESP_WIFI_STATIC_RX_BUFFER_NUM=3
CONFIG_ESP_WIFI_DYNAMIC_RX_BUFFER_NUM=6
CONFIG_ESP_WIFI_RX_BA_WIN=3
CONFIG_LWIP_TCPIP_RECVMBOX_SIZE=16
CONFIG_MBEDTLS_DYNAMIC_FREE_CONFIG_DATA=y
CONFIG_ESP_WIFI_ENABLE_WPA3_SAE=n
CONFIG_ESP_WIFI_ESPNOW_MAX_ENCRYPT_NUM=0
CONFIG_FREERTOS_IDLE_TASK_STACKSIZE=768
CONFIG_LWIP_IPV6=n
```

每一项都能省一点内存，加起来很可观。

## 17.8 关于版本：官方已经放弃 5.x

> README 原文：
> "The project now requires ESP-IDF v6.0.1 or later. ESP-IDF v6.1 is the
> recommended SDK. **ESP-IDF 5.x is no longer supported**. The current matrix
> contains 171 variants."

`main/idf_component.yml` 里还有硬性声明：

```yaml
  ## Required IDF version
  idf:
    version: '>=6.0.1'
```

**这意味着什么**（第 3.1 节提过）：
如果你的目标是给设备加 AI 语音，**直接装 IDF 6.1**，
不要从某个 5.x 的 fork 起步——否则你迟早要迁移一次。

## 17.9 你能从它抄走什么

| 想抄的东西 | 在哪 |
| --- | --- |
| **单线程事件循环架构** | `main/application.cc` 的 `Run()` |
| ADC 多键复用句柄 | `ai_passport_board.cc` |
| 省内存 sdkconfig | `sdkconfig.defaults.esp32c3` |
| OTA 分区布局 | `partitions/v2/16m_c3.csv` |
| mmap 素材 + MMU 页检查 | `main/assets.cc` |
| 多板型抽象（如果做跨设备） | `main/boards/` |

**有一件事这张表里没有，但你自己做联网设备一定会撞上：云端鉴权。**

小智连的是云端对话服务，设备要有身份才能用——也就是 token 那一套
（本书把它放在 [10c.2 ④](10c-network-data.md#10c2-https证书时间和内存三件事一个都不能漏) 讲，不在本章展开）。

值得注意的只有一点：这类服务的 token **有有效期**，而设备经常一连几天不上电。
等你某天开机发现“功能不好使了”，多半不是代码坏了，是**token 过期了**——
详见 10c.2 ④。

> 顺带一句工程上的分寸：别把 token 硬编码进固件。
> 它会被原样写进 `.bin`，拿到固件就能提取，而且过期后必须重刷。

> 联网这条线（长连接协议、音频流的内存预算）本书单独讲了：
> [10b 配网](10b-provisioning.md) · [10c.4 长连接](10c-network-data.md#10c4-长连接mqtt--websocket--裸-socket) ·
> [10c.5 流式音频](10c-network-data.md#10c5-最苛刻的场景流式音频)。
> 小智走的是“WebSocket/MQTT 信令 + UDP/Opus 音频”那一套，原理在那两节。

## 17.10 小结

- 它是**社区第一**（7244 下载），说明 AI 语音是最大需求；
- **C++，不用 `components/bsp`**，自己搞 `Board` 抽象支持 171 种板子；
- 核心架构是**单线程事件循环**：回调只置位，处理全在主循环 → **不需要锁**；
- IDF **≥ 6.0.1**，已放弃 5.x；
- 它和本书其他章节讲的硬件事实完全一致（16 kHz、无 PA 控制、屏幕反色、
  无法检测充电）——**这些是板子的事实，不是 fork 的偏好**。

下一章讲调试：当设备不按你想的运行时，怎么查。
