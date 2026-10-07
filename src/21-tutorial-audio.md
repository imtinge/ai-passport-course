# 21. 手把手：让板子发出声音

三件套的最后一件。音频是这块板子上**最容易写错、也最容易把整个 UI 拖死**的部分——
因为 `bsp_audio_write()` 是**阻塞**调用：I2S 缓冲区满了它就等着。

本章代码来自两部分：**官方 `main/demo_audio.c`**（在 `folotoy/ai-passport` 里）+ **作者工作副本的 `main/demo_barbapapa.c`**（第 18 章，巴巴爸爸项目），
配套可编译文件 `snippets/05_audio_play.c`（发声与分块）、`snippets/06_audio_worker.c`（worker 与停止握手）、
`snippets/07_audio_drain.c`（**收尾**：等 DMA 排空再断电、`sleep()` 单向门的正确用法）。

---

## 21.1 先认清硬件

| 项 | 值 | 出处 |
|---|---|---|
| Codec | **ES8311** | `bsp_audio.h` |
| 控制口 | I2C（与 CW2017 电量计**共用一条总线**） | `bsp_pins.h:69` |
| 数据口 | I2S 全双工（一 tx 一 rx，共用 MCLK/BCLK/WS） | `bsp_pins.h:80~87` |
| 引脚 | MCLK=6, BCLK=5, WS=3, DOUT=2, DIN=4 | 同上 |
| 功放使能 | `BSP_I2S_PA_CTRL` = **-1**（没接 MCU） | `bsp_pins.h:87` |
| 采样率 | **16000 Hz / 16 bit / 单声道** | `demo_audio.c:20` |

> **`PA_CTRL` 是 -1 这件事很重要**：你**没法用 GPIO 关掉功放**，它是常通的。
> 所以"静音"只能靠不送数据 + codec 休眠，不能靠拉一个引脚。

### BSP 给你的全部 API

```c
esp_err_t bsp_audio_init(void);                              // 初始化 codec 与 I2S
esp_err_t bsp_audio_set_format(uint32_t hz, uint8_t bits, uint8_t ch);
esp_err_t bsp_audio_write(const void *pcm, size_t bytes);    // 播放（阻塞）
esp_err_t bsp_audio_read(void *pcm, size_t bytes);           // 录音（阻塞）
void      bsp_audio_set_volume(uint8_t percent);             // 0..100
esp_err_t bsp_audio_sleep(void);                             // light sleep 前
esp_err_t bsp_audio_wake(void);                              // light sleep 后恢复
esp_err_t bsp_audio_prepare_deep_sleep(void);                // deep sleep 专用
```

注意 `bsp_audio_init()` **内部会调 `bsp_i2c_init()`**（幂等），你不用自己先初始化 I2C。

---

## 21.2 最小发声：四步

```c
bsp_audio_init();                       // 1. 初始化
bsp_audio_set_format(16000, 16, 1);     // 2. 定格式：16kHz / 16bit / 单声道
bsp_audio_set_volume(80);               // 3. 音量 0..100
bsp_audio_write(pcm, bytes);            // 4. 送数据（阻塞！）
```

就这么简单。但**第 4 步不能在错误的地方调**——这是下一节的主题。

### 采样率怎么定

`16000 × 2 字节 = 32,000 字节/秒`。记住这个数：

| 时长 | 字节数 |
|---|---|
| 1 秒 | 32 KB |
| 3 秒 | 96 KB |
| 10 秒 | 320 KB |

在没 PSRAM 的机器上，**96 KB 已经是可分配内存的一大块**（可用堆约 230 KB，
而最大连续空闲块 < 8 KB）。这也是官方 `demo_audio.c` 录音只录 3 秒的原因。

---

## 21.3 铁律：播放必须在独立任务里

看第 18 章 `demo_barbapapa.c:122`（作者工作副本）的注释原文：

> *"为什么必须在独立任务里：`bsp_audio_write()` 是阻塞调用
> （I2S 缓冲区满了会等），如果在按键回调或 LVGL 任务里调用，
> 按键和屏幕都会'卡住不动'直到播完。"*

**绝对不要在按键回调里调 `bsp_audio_write()`。**
按键回调运行在 button 组件的共享 `esp_timer` 任务里（见第 6 章），
你在里面阻塞几秒，整个按键系统和 UI 就都死了。

正确的结构是**"下单 / 干活"分离**：

```c
按键回调（快）  ──xTaskNotify(命令)──▶  音频 worker 任务（慢，阻塞也无所谓）
                                            │
                                        bsp_audio_write()
```

按键回调只发一个通知就返回，真正的播放在 worker 里做。

---

## 21.4 分块送数据，才能被打断

即使放到了独立任务里，也**不要一次把整段 PCM 送进去**。
要切成小块，每块之间检查"要不要停"。

两个参考值（分别来自官方 `demo_audio.c` 与第 18 章 `demo_barbapapa.c`）：

| 场景 | 块大小 | 出处 | 换算 |
|---|---|---|---|
| 合成音（方波） | `CHUNK_SAMPLES 512`（= 1024 B） | `demo_audio.c:24` | 32 ms |
| 语音播报 | `CHUNK_BYTES 2048` | 第 18 章 `demo_barbapapa.c:51` | **64 ms** |

第 18 章 `demo_barbapapa.c` 的注释解释了为什么是 2048：

> *"16kHz/16bit/单声道 = 32000 字节/秒，2048 字节 = 64ms，
> 块之间能检查'要不要打断'"*

**64 ms 是可感知延迟的上限附近**——用户按了下一个角色，最多 64 ms 内停掉旧的、
开始播新的。块太大，切换就迟钝；块太小，I2S 容易断流（underflow）产生杂音。

### 完整 worker 模板（可直接抄）

```c
#define CHUNK_BYTES     2048
#define STOP_TIMEOUT_MS 2000

static TaskHandle_t     s_task;
static SemaphoreHandle_t s_stopped;
static volatile bool     s_cancel;

// ---- worker：只在这里碰 bsp_audio_* ----------------------------------------
static void play_voice(const uint8_t *pcm, uint32_t bytes)
{
    if (bsp_audio_set_format(16000, 16, 1) != ESP_OK) return;
    bsp_audio_set_volume(80);

    uint32_t off = 0;
    while (off < bytes && !s_cancel) {          // ★ 每块都检查取消
        uint32_t n = bytes - off;
        if (n > CHUNK_BYTES) n = CHUNK_BYTES;
        if (bsp_audio_write(pcm + off, n) != ESP_OK) break;
        off += n;
    }
}

static void audio_task(void *arg)
{
    (void)arg;
    for (;;) {
        uint32_t cmd = 0;
        if (xTaskNotifyWait(0, UINT32_MAX, &cmd, portMAX_DELAY) != pdTRUE) continue;
        if (cmd == CMD_STOP) break;
        if (cmd == CMD_PLAY) play_voice(g_pcm, g_pcm_bytes);
    }
    // ★ 不要 vTaskDelete(NULL)！先给确认，再自己挂起，等 owner 来删
    xSemaphoreGive(s_stopped);
    for (;;) vTaskSuspend(NULL);
}
```

> ⚠ **worker 任务不能自己删自己**
>
> 官方 `demo_audio.c:126` 的写法是：
> ```c
> xSemaphoreGive(s_stopped);
> for (;;) vTaskSuspend(NULL);
> ```
> 然后由 `stop()` 的调用方来做 `vTaskDelete(task)`。
>
> 为什么？因为 stop 可能**超时**。如果 worker 自己删了自己，
> 超时的 `stop()` 再去 `vTaskDelete(handle)` 就是在删一个已经不存在的任务
> （handle 变成野指针）。让 worker 挂起、由 owner 统一删除，
> 超时重试也是安全的。

### start / stop 握手

```c
esp_err_t audio_start(void)
{
    if (s_task) return ESP_OK;
    s_stopped = xSemaphoreCreateBinary();
    if (!s_stopped) return ESP_ERR_NO_MEM;
    s_cancel = false;
    // 栈 4096 字节（注意 FreeRTOS 的栈单位是"字"还是"字节"取决于移植，
    // ESP-IDF 的 xTaskCreate 是字节），优先级 4 —— 与 LVGL 同级
    if (xTaskCreate(audio_task, "audio", 4096, NULL, 4, &s_task) != pdPASS) {
        vSemaphoreDelete(s_stopped); s_stopped = NULL;
        return ESP_ERR_NO_MEM;
    }
    return ESP_OK;
}

esp_err_t audio_stop(void)
{
    TaskHandle_t task = s_task;
    if (!task) return ESP_OK;

    s_cancel = true;
    xTaskNotify(task, CMD_STOP, eSetValueWithOverwrite);
    if (!s_stopped ||
        xSemaphoreTake(s_stopped, pdMS_TO_TICKS(STOP_TIMEOUT_MS)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;        // ★ 返回错误，让框架中止退出
    }
    vTaskDelete(task);
    s_task = NULL;
    vSemaphoreDelete(s_stopped);
    s_stopped = NULL;
    return ESP_OK;
}
```

**`stop()` 超时要返回 `ESP_ERR_TIMEOUT`**，这一点是页面契约的一部分（第 5 章）：
框架收到错误会**中止退出页面**，而不是带着一个还在跑的后台任务切走。

---

## 21.5 播放 Flash 里的音频

把 WAV 剥成裸 PCM，用 `EMBED_FILES` 链进 Flash（和上一章图片完全一样）：

```c
extern const uint8_t voice_00[] asm("_binary_voice_00_pcm_start");
```

然后按 21.4 的模板分块送。**`pcm` 指针直接指向 Flash**——
和图片一样，音频数据也不占 RAM，`.rodata` 可以直接喂 I2S DMA（第 11 章）。

### WAV → PCM

WAV 只是"44 字节（或更多）的头部 + 裸 PCM"。剥头即可，
但**别假定偏移恒定为 44**——要逐 chunk 找：

```python
def wav_to_pcm(path):
    raw = open(path, 'rb').read()
    assert raw[:4] == b'RIFF', "不是 WAV"
    fmt = data = None
    pos = 12
    while pos + 8 <= len(raw):
        cid  = raw[pos:pos+4]
        size = struct.unpack_from('<I', raw, pos+4)[0]
        body = raw[pos+8:pos+8+size]
        if   cid == b'fmt ': fmt  = body
        elif cid == b'data': data = body
        pos += 8 + size + (size & 1)      # chunk 按偶数字节对齐
    af, channels, rate, br, ba, bits = struct.unpack_from('<HHIIHH', fmt, 0)
    assert (channels, rate, bits) == (1, 16000, 16), \
        f"应为 16000/16/1，实际 {rate}/{bits}/{channels}"
    return data
```

**必须有那个 `assert`。** 第 18 章 `fetch_assets.py:119`（作者工作副本）就是这么做的，
不满足直接 `sys.exit`。理由和第 20 章一样：**格式不匹配在设备上表现为"变调/杂音"，
你根本想不到是 PC 端转换的问题**。

---

## 21.6 录音

录音就是把 `write` 换成 `read`，同样分块：

```c
#define RECORD_SEC     3
#define CHUNK_SAMPLES  512

size_t total = 16000 * RECORD_SEC;                 // 3 秒 = 48000 采样
int16_t *rec = malloc(total * sizeof(int16_t));    // = 96 KB ！
if (!rec) {
    // C3 无 PSRAM，96KB 可能分配不到 —— 明确告知而不是静默失败
    ESP_LOGE(TAG, "录音缓冲 %u 字节分配失败", (unsigned)(total * sizeof(int16_t)));
    return;
}

size_t got = 0;
while (got < total && !s_cancel) {
    size_t n = (total - got) < CHUNK_SAMPLES ? (total - got) : CHUNK_SAMPLES;
    if (bsp_audio_read(rec + got, n * sizeof(int16_t)) != ESP_OK) break;
    got += n;
}
```

> ⚠ **96 KB 可能 `malloc` 失败**
>
> 官方 `demo_audio.c:78` 的注释：*"C3 无 PSRAM，96KB 可能分配不到"*。
> 两个要点：
> 1. **一定要检查 `malloc` 返回值**，并且失败时打日志——
>    不要静默失败，否则你会以为是麦克风坏了。
> 2. 分配不到就**缩短录音时长**，或者改成边录边处理（流式），
>    不要一次攒满整段。

录完回放：把 `read` 换成 `write`，同一个缓冲再送一遍即可
（官方 `demo_audio.c` 的 `record_and_play()` 就是这么做的）。

---

## 21.7 采样率切换：BSP 已经替你踩过坑了

这是个非常隐蔽的 bug，值得单独讲——**即使你现在用不到，也要知道原因**。

`esp_codec_dev_open()` 在 codec **已经打开**时会直接返回 `ESP_OK`，
**并且不重新配置采样率**。于是：

```text
16 kHz 播完 → 调 open() 想切到 8 kHz
            → open 返回 OK，但时钟还是 16 kHz
            → 8 kHz 的数据以 16 kHz 送出
            → 音调和速度都快一倍
```

**好消息**：`bsp_audio_set_format()` 内部已经处理了——它在格式变化时
先 `close()` 再 `open()`。所以你正常调 BSP 是安全的。
`bsp_audio.h` 的注释原文：

> *"⚠ 这里有个必须绕开的坑：`esp_codec_dev_open()` 在 codec【已打开】时会直接返回 OK 且
> 【不重新配置采样率】。若不先 close，16kHz 播完再播 8kHz 会以 16k 时钟送出 ——
> 音调和速度都快一倍。故本函数在格式变化时先 close 再 open。"*

**什么时候你会踩到**：绕过 BSP 直接用 `esp_codec_dev` 的时候。

另外注意 BSP 注释里的约束：

- **切换格式前必须停止所有 PCM 读写**；
- **串行化**格式/休眠/唤醒操作（别在音频任务里切格式，同时 UI 任务里又调 sleep）。

---

## 21.8 低功耗：sleep 与 deep sleep

三个函数，用错一个就出怪声或漏电流：

| 函数 | 用在哪 | 后果 |
|---|---|---|
| `bsp_audio_sleep()` | **light sleep 前**、或长时间不用音频时 | 执行 ES8311 完整 suspend 寄存器序列并**回读确认** |
| `bsp_audio_wake()` | light sleep **后** | 重新创建 codec、恢复音量与格式（幂等） |
| `bsp_audio_prepare_deep_sleep()` | **仅 deep sleep** | 把 I2S 引脚设为高阻；**本次运行不能再恢复** |

几个细节：

- `bsp_audio_sleep()` **不依赖 codec 是否打开过**——开机后从没播放也能正确暂停。
  这解决了一个常见问题：开机就没声音的机器，休眠时漏电流。
- `bsp_audio_sleep()` **幂等**，音频未初始化时直接返回成功。
- `prepare_deep_sleep()` **不能用于 light sleep**——它把 I2S 引脚设成高阻，
  唤醒后 I2S 在本次运行里就废了，只能重启。

### ⚠ `sleep()` 是一个不可逆的单向门

这条不在任何官方文档里，是实战排查出来的，但它解释了
**"设备用着用着突然一点声音都没有了"**这个最难查的故障：

```c
// bsp_audio.c 内部的状态（简化）
static bool s_sleeping = false;          // ← sleep() 置 true
static bool s_opened   = false;          // ← sleep() 置 false
static esp_codec_dev_handle_t s_dev;     // ← sleep() 置 NULL
```

`sleep()` 之后，你在第 21.2 节学的那套调用会**全部静默失败**：

| 调用 | sleep() 之后的行为 |
|---|---|
| `bsp_audio_set_format()` | 第一行 `if (s_sleeping) return ESP_ERR_INVALID_STATE`，**直接失败** |
| `bsp_audio_write()` | 内部 `!s_dev` → 返回失败，**一个字节都写不出去** |
| `bsp_audio_set_volume()` | 值被记住，但 codec 没在工作，听不到变化 |

注意这些失败是**静默的**——`ESP_LOGW` 可能只打一行 `invalid state`，
UI 上看不出任何异常，你就只看到"没声音"。

```c
// ❌ 典型错误：为了省电 sleep，然后忘了 wake
bsp_audio_sleep();
// ... 过了很久 ...
bsp_audio_set_format(16000, 16, 1);   // 返回 ESP_ERR_INVALID_STATE（你没检查）
bsp_audio_write(pcm, n);              // 失败，静默无声

// ✅ 正确：用之前一定先 wake
bsp_audio_wake();                     // 幂等，重复调用无害
bsp_audio_set_format(16000, 16, 1);
bsp_audio_write(pcm, n);
```

**排查口诀**：设备"本来有声音，后来没了"→ 第一步查"是不是有代码路径调用了
`bsp_audio_sleep()` 却没有配对的 `wake()`"。官方 `demo_low_power.c` 是唯一用到它的地方，
所以自己写休眠相关页面时要格外小心。

> 顺带一句：正因为 `sleep()` 会复位这些内部状态，**它必须在 light sleep 前后成对出现**。
> 官方源码注释也强调了同一件事 —— "只要尝试过 suspend，即使没真正睡着也必须调 `wake()`"。

**开机爆音**是另一回事（ES8311 上电时序），详见第 7 章。

---

## 21.9 故障排查表

| 现象 | 原因 | 怎么查 |
|---|---|---|
| 完全没声音 | 没调 `bsp_display_backlight`？不，是——没 `bsp_audio_init()` / 音量 0 | 检查四步是否齐全；`set_volume(80)` |
| **UI 卡死、按键失灵** | 在按键回调或 LVGL 任务里调了 `write()` | 移到独立 worker 任务（21.3） |
| 声音断续/有杂音 | 块太小导致 I2S 断流 | 加大块到 1024~2048 字节 |
| **变调、速度快一倍** | 采样率没真正切（绕过 BSP 用 esp_codec_dev） | 先 `close()` 再 `open()`；或改用 `bsp_audio_set_format()` |
| 杂音/像噪声 | PCM 格式与 `set_format` 不一致 | 核对 16000/16/1；检查 WAV 转换的 assert |
| 切歌迟钝 | 块太大，取消检查不及时 | 块调到 2048 B（64 ms） |
| 播完停不下来 | 循环里没检查 `s_cancel` | 每块前检查 |
| 退出页面后还在响 | `stop()` 没等确认就返回 | 用信号量握手，超时返回 `ESP_ERR_TIMEOUT` |
| 录音失败，日志没报错 | `malloc` 96 KB 失败但没检查返回值 | 必须检查并打日志 |
| 休眠后电流没降 | 没调 `bsp_audio_sleep()` | light sleep 前调用；它在未播放时也有效 |
| deep sleep 后喇叭滋滋响 | 用了 `sleep()` 而不是 `prepare_deep_sleep()` | deep sleep 必须用后者 |
| **本来有声音，之后突然全没了** | 某条路径调了 `bsp_audio_sleep()` 却没有配对的 `wake()` | 见 21.8「单向门」：sleep 后 `set_format`/`write` 全部静默失败。先补 `bsp_audio_wake()` |
| **关机/深睡前播的语音听不到** | DMA 未排空就被 `i2s_channel_disable()` 掐断 | 写完等 `vTaskDelay(bytes/32 + 120)`，见第 7.2 节 |
| **只有一小截声音就被切断** | 同上，尾段被丢 | 同上；`+120ms` 余量是覆盖 PA 上电斜坡的，别省 |

> **分辨"没播"和"没播完"是排查的第一步**：
> 一个字都听不到 → 查 `set_format()` 返回值和有没有漏 `wake()`；
> 听到开头就断 → 查 DMA 排空等待。
> 这两种症状的根因完全不同，先分清楚能省一半时间。

---

## 21.10 小结

音频的正确姿势：

1. 四步：`init` → `set_format(16000,16,1)` → `set_volume` → `write`；
2. **`write()` 是阻塞的**，必须在**独立任务**里调，绝不能在按键回调/LVGL 任务里；
3. **分块送**（1024~2048 字节），每块检查 `s_cancel`，块大小决定打断延迟；
4. worker **不自己删自己**：`xSemaphoreGive(s_stopped)` 后 `vTaskSuspend`，由 owner 删；
5. `stop()` **超时返回 `ESP_ERR_TIMEOUT`**，让框架中止退出；
6. PCM 用 `EMBED_FILES` 链进 Flash，**不占 RAM**，WAV 剥头时 `assert` 格式；
7. 切采样率交给 `bsp_audio_set_format()`（它内部 close-then-open）；
8. light sleep 用 `sleep()/wake()`，deep sleep 用 `prepare_deep_sleep()`，**别混**；
9. **`sleep()` 是单向门**——之后 `set_format`/`write` 全部静默失败，用之前必须 `wake()`；
10. **`write()` 返回 ≠ 声音响完**：要关 I2S/断电前，先等 `bytes/32 + 120` ms 让 DMA 排空。

可编译示例：`snippets/05_audio_play.c`、`snippets/06_audio_worker.c`、
`snippets/07_audio_drain.c`（**这一份**专门解决"最后一句语音被掐断"和
"`sleep()` 之后再也播不出声"，是本章最容易踩的两个坑）。

到这里，中文、图片、声音三件套都齐了。
接下来第 22 章讲这三件事出问题时的通用调试手段。
