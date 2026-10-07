# 15. 实战三：音效钥匙扣（音频 + 文件系统）

| 项目 | 值 |
| --- | --- |
| 排名 | #5 |
| 下载量 | 2299 |
| 仓库 | `github.com/Shinku-Chen/ai-passport` |
| 规模 | `main/` 12 个 .c（1715 行）；**11 条远程分支** |
| IDF | 5.5.3 |
| 招牌玩法 | `feature/voice-keychain`：音效钥匙扣 |

**为什么拆解它**：两个理由。

1. **它是一仓多玩法的最佳范例**——10 条 `feature/*` 分支（外加 main，共 11 条远程分支），
   主干保持干净，每个玩法一条分支（第 1 章扫描数据显示：172 个仓库里
   只有 8 个开了多分支，它是分支最多的一个，11 条）；
2. **`voice-keychain` 分支展示了完整的音频 + 文件系统方案**，
   从素材处理到常驻播放任务，一条龙。

## 15.1 分支结构

```text
origin/HEAD -> origin/main
origin/feature/asunabi-galgame
origin/feature/atri-reader
origin/feature/cheerful-goodall
origin/feature/dracu-riot
origin/feature/sanoba-witch
origin/feature/saya-no-uta
origin/feature/senren-banka
origin/feature/starry-sky-railroad
origin/feature/tsxx-reboot
origin/feature/voice-keychain      ← 本章主角
origin/main
```

**主干 `main` 是官方 BSP demo**（和官方基线一样的功能验证菜单），
每个玩法在自己的分支上独立开发。

这是“一个仓库跑多个玩法”的两种主流方案之一
（另一种是上一章的页面栈）。对比：

| 方案 | 优点 | 缺点 |
| --- | --- | --- |
| **页面栈**（pax-zhang） | 一次烧录全都能玩 | 内存压力大、固件大 |
| **feature 分支**（Shinku） | 每个玩法独立、互不干扰 | 换玩法要重新烧录 |

**小玩法多、内存吃紧时，选分支方案。**

## 15.2 app_main 对比：菜单版 vs 单玩法版

**主干版**（带功能菜单，243 行）要先建菜单、建队列、建派发任务。

**`voice-keychain` 版**（43 行）就清爽多了：

```c
void app_main(void) {
    ESP_LOGI(TAG, "音效钥匙扣启动");
    esp_sleep_wakeup_cause_t wakeup = esp_sleep_get_wakeup_cause();
    if (wakeup != ESP_SLEEP_WAKEUP_UNDEFINED) {
        ESP_LOGI(TAG, "休眠唤醒原因: %d", wakeup);
    }

    bsp_i2c_init();
    bsp_i2c_scan();

    if (bsp_display_init() != ESP_OK || !bsp_lvgl_init()) {
        ESP_LOGE(TAG, "显示/LVGL 初始化失败, 音效应用无法继续。"
                      "检查 SPI 接线(MOSI=%d SCLK=%d CS=%d DC=%d BL=%d)",
                 BSP_LCD_MOSI, BSP_LCD_SCLK, BSP_LCD_CS, BSP_LCD_DC, BSP_LCD_BL);
        return;
    }
    bsp_display_backlight(100);

    // 按键: 直接绑定 voice_app 回调。运行于 button 组件任务, voice_app 内部加锁。
    esp_err_t btn_err = bsp_button_init(voice_app_on_key, NULL);
    if (btn_err != ESP_OK) {
        ESP_LOGE(TAG, "按键初始化失败: %s", esp_err_to_name(btn_err));
        return;   // 无输入无法操作音效应用
    }

    // 音频与电量: 失败不阻塞启动, 但播放/设置会受影响, 记录日志。
    bsp_audio_init();
    bsp_battery_init();

    voice_app_start();
}
```

注意这几行注释：
- “**运行于 button 组件任务，voice_app 内部加锁**”——职责写清楚了；
- “**音频与电量：失败不阻塞启动**”——降级策略明确了；
- 只有**按键失败才 return**（没输入就没法操作）。

## 15.3 招牌实现：常驻播放任务 + 静态栈

> 源码：`main/voice_app.c`（`feature/voice-keychain` 分支）

```c
#define PLAYER_STACK_BYTES 16384
// Opus SILK 单帧解码栈需求大, 用静态栈避免每次播放重复 16KB 堆分配
static StackType_t       s_player_stack[PLAYER_STACK_BYTES / sizeof(StackType_t)];
static StaticTask_t      s_player_tcb;
static SemaphoreHandle_t s_job_sem;    // 常驻播放 worker 的唤醒信号
static play_job_t       *s_job;        // 当前活跃播放 job(单播放, 指向最新一个)
```

播放循环：

```c
uint8_t hdr[2];
uint8_t pkt[OPUS_MAX_PACKET];
int16_t pcm[OPUS_FRAME_SAMPLES];

ESP_LOGI(TAG, "播放: %s", f->name);
while (!job->stop) {
    if (fread(hdr, 1, 2, fp) != 2) break;                 // 读 2 字节包长度
    uint16_t plen = (uint16_t)(hdr[0] | (hdr[1] << 8));
    if (plen == 0 || plen > OPUS_MAX_PACKET) break;
    if (fread(pkt, 1, plen, fp) != plen) break;
    if (job->stop) break;                                 // ★ 每帧检查停止标志

    int nsamp = opus_decode(dec, pkt, plen, pcm, OPUS_FRAME_SAMPLES, 0);
    if (nsamp < 0) break;

    bsp_audio_write(pcm, (size_t)nsamp * 2u);             // int16 采样 → 字节
}
ESP_LOGI(TAG, "播放结束: %s", f->name);
```

**为什么这么写**（三条，全是无 PSRAM 逼出来的）：

1. **常驻 + 静态栈**：反复 `xTaskCreate` 16 KB 栈会把堆打碎，
   作者实测结果是“只停不播”——能停止播放，但再也播不出来；
2. **逐包解码**：一个 3 秒音效的 PCM 是 96 KB，放不下；
3. **每帧检查 `stop`**：用户再按一次键要能立刻打断。

## 15.4 素材管线：PC 侧预处理

音效不是直接拷进分区的，有一条 Python 管线：

> 语音片段存放在挂载于 `/voices` 的 `voicefs` SPIFFS 数据分区，
> 由 `tools/encode_voice.py` 生成
> （**解码 → 重采样到 8 kHz 单声道 → IMA-ADPCM 4bit
> → 生成 `main/voice_index.h` + `voicefs.img`**）。
> 应用分别烧录合并固件镜像与该数据分区。

四个动作、两个产物：

```text
原始音频 → 重采样(8kHz) → 压缩(IMA-ADPCM 4bit) → voicefs.img（烧到分区）
                                               → voice_index.h（编进固件）
```

`voice_index.h` 里是“名字 → 偏移”的索引表，
**固件不用列目录**，直接按偏移读。这省了运行时的目录遍历开销。

挂载代码：

```c
static bool fs_mount(void) {
    if (s_fs_mounted) return true;
    esp_vfs_spiffs_conf_t cfg = {
        .base_path = VOICE_FS_MOUNT,          // "/voices"
        .partition_label = VOICE_FS_PARTITION,
        .max_files = 8,
        .format_if_mount_failed = true,
    };
    esp_err_t err = esp_vfs_spiffs_register(&cfg);
    // ...
}
```

## 15.5 这个项目里最有意思的几条记录

README 里全是实测数据，读起来像一本实验笔记：

> **无 PSRAM 也能铺满全屏美术** —— 背景是内存映射分区里的 LVGL 索引图，
> 直接从 flash 绘制、按行解码（**约 960 字节**），而不是 150 KB 的帧缓冲；
> 占用芯片 **128 个 flash-MMU 页中的 83 个**。

> **自写 inflate 替代 ROM 解压器** —— 整块解压到一个缓冲区，
> 不需要 32 KB 滑动字典，在没有 PSRAM 的 ESP32-C3 上把**工作缓冲压到 4 KB**。

> **一次只解一块（单块解压 3 KB、缓冲 4 KB），因为开机后最大连续空闲块不到 8 KB。**

> **设备端 Opus 上行** —— 16 kHz 采集、60 ms 帧、DTX，约 **3 KB/s**
> （PCM 的十分之一）；在没有 PSRAM 的 ESP32-C3 上用静态栈跑编码，避开堆碎片。

> **串口截图** —— `FAP_SCREENSHOT_V1` 命令回传真实 320×240 画面……
> 它现在是可选的开发构建，因为在没有 PSRAM 的板子上**它与 BLE 联机无法共存**。

> **深睡唤醒已修复** —— GPIO0 唤醒源此前从未启用（**把引脚号当位掩码传入**），
> 导致“睡了就醒不过来”。

最后一条是个价值千金的调试经验：**引脚号和位掩码别混。**

## 15.6 你能从它抄走什么

| 想抄的东西 | 在哪 |
| --- | --- |
| 常驻播放任务 + 静态栈 | `feature/voice-keychain` 分支 `main/voice_app.c` |
| SPIFFS 挂载与分区 | 同上 `fs_mount()` + `partitions.csv` |
| PC 侧素材编码管线 | `tools/encode_voice.py` |
| 按键队列派发（完整版） | `main/main.c`（主干分支） |
| 深睡关外设顺序 | `main/demo_low_power.c` |
| mmap 全屏背景绘制 | README 描述 + 相应分支 |

## 15.7 小结

- **一仓多玩法用 `feature/*` 分支**，主干保持干净；
- 音频播放三要素：**常驻任务 + 静态栈 + 逐包解码**；
- 素材走“PC 预处理 + 独立分区 + 索引头文件”；
- **最大连续块 < 8 KB** 是这个项目所有设计的起点；
- 串口截图和 BLE 在 C3 上无法共存——**功能之间要做取舍**。

> **延伸阅读 · 官方经验条目**：
> [音频压缩方式的权衡](https://github.com/FoloToy/ai-passport/blob/main/docs/reference/shinku-chen/audio-compression-trade-offs.zh_CN.md)
> ——IMA-ADPCM / Opus / MP3 在有限 Flash 上的实测容量与解码器成本，正是本项目选编解码时的依据
