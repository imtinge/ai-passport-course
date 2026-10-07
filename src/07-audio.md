# 7. 音频：播放、录音与开机爆音

> **可抄代码**：[D.7 音频](D-module-cookbook.md#d7-音频)。


AI Passport 有扬声器、麦克风和 ES8311 codec，大部分玩法都要出声。
本章讲怎么用，以及为什么音频是社区 bug 的重灾区。

## 7.1 硬件与 API

ES8311 挂在 I2C（`0x18`）上被配置，音频数据走 I2S 全双工。
BSP 把这些全藏了，你只看到 8 个函数：

```c
esp_err_t bsp_audio_init(void);
esp_err_t bsp_audio_set_format(uint32_t hz, uint8_t bits, uint8_t ch);
esp_err_t bsp_audio_write(const void *pcm, size_t bytes);   // 播放
esp_err_t bsp_audio_read(void *pcm, size_t bytes);          // 录音
void bsp_audio_set_volume(uint8_t percent);
esp_err_t bsp_audio_sleep(void);
esp_err_t bsp_audio_wake(void);
esp_err_t bsp_audio_prepare_deep_sleep(void);
```

**注意没有 `bsp_audio_play_file()` 这样的函数。**
BSP 只认 **PCM 原始数据**——你要播 MP3/Opus，得自己解码成 PCM 再喂进去。

## 7.2 最小播放流程

```c
bsp_audio_init();
bsp_audio_set_format(16000, 16, 1);     // 16 kHz / 16 bit / 单声道
bsp_audio_set_volume(80);

// pcm 是 int16 采样，字节数 = 采样数 × 2
bsp_audio_write(pcm_buffer, samples * 2);
```

### ⚠ `write` 返回 ≠ 声音已经响完

这是很多人第一次做音频都会搞错的一件事，**也是本书要纠正的一个常见误解**：

> **`bsp_audio_write()` 阻塞的终点是“I2S 的 DMA 缓冲收下了数据”，
> 不是“喇叭把这段声音放完了”。**

调用链是这样的（`esp_codec_dev` → 驱动 → HAL）：

```c
bsp_audio_write(pcm, bytes)
  └─ esp_codec_dev_write()
       └─ audio_codec_data_i2s.c: _i2s_data_write()
            └─ i2s_channel_write(tx_chan, ...)     // 拷进 DMA 环形缓冲即返回
```

最后那一步 `i2s_channel_write()` 只是把数据**推进 DMA 队列**。
它返回成功时，声音还在队列里排队，喇叭可能一个字都没出。
真正的播放由 DMA 在后台按采样时钟慢慢送出。

为什么会咬人？因为**DMA 不会因为你停 I2S 就把剩下的播完**：

```text
工作流程：  write(全部数据) ──► DMA 边排队边播放 ──► 真正出声
                              ▲
                              └── 如果你在这里 i2s_channel_disable()
                                  队列里剩下的数据直接被丢弃，声音被掐断
```

而 `bsp_audio_prepare_deep_sleep()` 内部恰好就有这句 `i2s_channel_disable()`。
**所以“播完再关机”必须你自己保证**——驱动程序不会替你等。

### 怎么等：按字节数算出来

16 kHz / 16 bit / 单声道，每秒 = 16000 × 2 = **32000 字节**。
所以时长就是 `字节数 ÷ 32000` 秒：

```c
// 写完 PCM 之后、决定动 I2S 之前，显式等它播完
static void wait_audio_drained(size_t bytes_written)
{
    // 16kHz/16bit/mono：1 秒 = 32000 字节
    uint32_t ms = (uint32_t)(bytes_written / 32);     // 字节数 / 32000 * 1000
    vTaskDelay(pdMS_TO_TICKS(ms + 120));              // +120ms 覆盖 PA 上电斜坡与尾段
}
```

> `bytes_written / 32` 就是 `bytes * 1000 / 32000` 的约简形式——
> 用整数除法即可，**不需要 `uint64_t`**（几万字节远在 32 位范围内）。

> **可编译版**：这段话连同“播完道别语再关机”的完整序列，见
> `snippets/07_audio_drain.c`（`wait_audio_drained()` + 深睡收尾 + `sleep()` 单向门的正确用法）。

**什么时候必须等**：

| 场景 | 要不要等 | 为什么 |
| --- | --- | --- |
| 播完就进 deep sleep / 关机 | **必须等** | 否则一句都说不出来就被断电 |
| 播完调用 `bsp_audio_prepare_deep_sleep()` | **必须等** | 它内部会 `i2s_channel_disable()` |
| 播完调用 `bsp_audio_sleep()` | 建议等 | suspend 会停 codec |
| 接着播下一段（同格式） | 不用等 | DMA 会自己续上，等待反而造成断续 |
| 页面照常运行、什么都不关 | 不用等 | 让它自然播完即可 |

> 一句话记法：**只要下一步要“关音频/关 I2S/断电”，就得先等；
> 只是接着用，就不用管。**

这一点决定了下一条规则。

## 7.3 规则：播放必须在自己的任务里

> 官方规则（pax-zhang README）：
> “PCM 读写为阻塞调用，应放工作任务。”

如果你在按键回调里调 `bsp_audio_write()` 播一个 3 秒的音效，
整个按键系统会卡死 3 秒。

标准结构（和按键那章一样）——**常驻任务 + 队列/信号量**。

## 7.4 一个真实的播放循环

这是音效钥匙扣项目的核心循环，值得完整读一遍：

> 源码：`main/voice_app.c`，分支 `feature/voice-keychain`（Shinku-Chen fork）

```c
uint8_t hdr[2];
uint8_t pkt[OPUS_MAX_PACKET];
int16_t pcm[OPUS_FRAME_SAMPLES];

while (!job->stop) {
    if (fread(hdr, 1, 2, fp) != 2) break;              // 读 2 字节包长度
    uint16_t plen = (uint16_t)(hdr[0] | (hdr[1] << 8));
    if (plen == 0 || plen > OPUS_MAX_PACKET) break;
    if (fread(pkt, 1, plen, fp) != plen) break;
    if (job->stop) break;                              // ★ 每帧检查停止标志

    int nsamp = opus_decode(dec, pkt, plen, pcm, OPUS_FRAME_SAMPLES, 0);
    if (nsamp < 0) break;

    bsp_audio_write(pcm, (size_t)nsamp * 2u);           // int16 采样 → 字节
}
```

四个要点：

1. **逐包解码，不整文件解码**——一个 3 秒音频的 PCM 是 96 KB，放不下；
2. **每帧检查 `job->stop`**——用户再按一次键要能立刻停；
3. **`nsamp * 2`**——`bsp_audio_write` 要的是**字节数**，`int16` 采样要乘 2；
4. **帧缓冲 `pcm[]` 在栈上**——所以这个任务需要大栈（见下）。

### 为什么用静态栈

同一个文件里：

```c
#define PLAYER_STACK_BYTES 16384       // Opus SILK 单帧解码栈需求大，
                                       // 用静态栈避免每次播放重复 16KB 堆分配
static StackType_t  s_player_stack[PLAYER_STACK_BYTES / sizeof(StackType_t)];
static StaticTask_t s_player_tcb;
```

> 作者踩过的坑（源码注释）：
> “从堆上申请 16 KB——堆不足/碎片化曾导致‘只停不播’（`xTaskCreate` 16 KB 栈失败）。”

这是一个非常典型的无 PSRAM 场景：**反复创建销毁大栈任务会把堆打碎**，
最后不是“内存不够”，而是“没有足够大的连续块”。
解法是**任务常驻 + 静态栈 + 信号量唤醒**。

### 如果你的素材是裸 PCM（不需要解码）

音效、提示音这类素材常常直接就是 16 kHz / 16 bit / 单声道的 PCM，
**零转换**就能用——编进固件当 `const` 数组，然后分块喂进去：

```c
#define CHUNK_SAMPLES 1024          // 2048 字节一块

size_t off = 0;
while (off < pcm_bytes) {
    // 每块之间检查一次新命令 → 播放中按键能立刻打断/切换
    uint32_t cmd = 0;
    if (xTaskNotifyWait(0, 0, &cmd, 0) == pdTRUE && cmd != 0) {
        if (cmd == EV_EXIT)  break;
        if (cmd == EV_PLAY)  { /* 切到新素材，off = 0，continue */ }
    }
    size_t n = CHUNK_SAMPLES * 2;
    if (off + n > pcm_bytes) n = pcm_bytes - off;
    if (bsp_audio_write(pcm + off, n) != ESP_OK) break;
    off += n;
}
```

两个要点：

1. **1024 样本（2048 字节）一块**是个舒服的粒度——
   既不会因为块太小而频繁调用，又能保证响应延迟在几十毫秒内；
2. **从 Flash 地址直接读是合法的**。`const` 数组在 `.rodata`，
   I2S 驱动会把数据拷进它自己的 DMA 缓冲，
   **对“数据源在 Flash 还是 RAM”没有要求**——所以不需要先读到 RAM。

> 完整可运行的页面骨架（含停止握手、`xTaskNotify` 命令字、退出流程）
> 见**第 18 章**。

## 7.5 采样率：别自作聪明重采样

> 源码注释（小智项目 `config.h`）：
> "Keep the C3 codec path at the protocol/native 16 kHz rate. The C3 has no PSRAM;
> forcing a 16 kHz → 24 kHz resampler allocates a temporary buffer during playback
> and can fragment the remaining internal SRAM."

**结论：在 C3 上就用 16 kHz。** 想升到 24 kHz/48 kHz 会引入重采样缓冲，
在没有 PSRAM 的板子上代价远大于收益。

常见采样率选择：

| 场景 | 建议 |
| --- | --- |
| 语音/音效 | 16 kHz 单声道 |
| 音乐（可接受音质损失） | 16–22 kHz |
| 需要高保真 | 这块板子不合适 |

## 7.6 开机爆音：第一个动作就该是静音

ES8311 上电瞬间会有“啪”的一声。PokeWalk 项目的 `app_main` 第一行是：

```c
void app_main(void) {
    // First app action: silence a connected PA and, in silent builds, the
    // codec before scans, display initialization, gameplay or debug tasks.
    esp_err_t quiet = bsp_audio_boot_quiet();
    if (quiet != ESP_OK) ESP_LOGE(TAG, "Early audio shutdown failed: %s",
                                  esp_err_to_name(quiet));
    // ...
}
```

注意注释里的“before scans, display initialization…”——
**在任何其他初始化之前**。这是一个很好的习惯：
让设备安静下来，然后再慢慢做别的事。

如果你的 BSP 版本没有 `bsp_audio_boot_quiet()`，
可以用 `bsp_audio_set_volume(0)` 起步，初始化完成后再调回去。

## 7.7 录音

```c
int16_t buf[640];                                  // 20 ms @ 16 kHz
bsp_audio_read(buf, sizeof(buf));                  // 同样阻塞
```

录音同样阻塞、**同样要放任务里**，而且通常要连续采集并编码。
上行语音的常见参数（社区实测）：

> “设备端 Opus 上行——16 kHz 采集、60 ms 帧、DTX，约 3 KB/s（PCM 的十分之一）；
> 在没有 PSRAM 的 ESP32-C3 上用静态栈跑编码，避开堆碎片。”

PCM 是 32 KB/s（16 kHz × 16 bit），**Opus 压到 3 KB/s**。
所以联网语音必须编码，不只是为了带宽，也是为了内存。

## 7.8 深睡前的音频关闭顺序

音频和电量计共用 I2C，所以关闭顺序有讲究。而且要注意：**如果关机前还有语音要播，
必须先按 7.2 的算法等 DMA 排空**，否则 `prepare_deep_sleep()` 一停 I2S，
道别语就永远留在队列里出不来了：

```c
// 0) 有道别/提示音要播的，先播，再【等它真的放完】
bsp_audio_write(bye_pcm, bye_bytes);
wait_audio_drained(bye_bytes);          // ← 见 7.2，少了这步声音会被掐断

// 1~4) 按依赖顺序收尾
bsp_battery_sleep();                    // 1. 先让电量计写完
bsp_audio_sleep();                      // 2. codec 睡眠
bsp_audio_prepare_deep_sleep();         // 3. 释放 I2S 引脚（内部 disable I2S）
bsp_i2c_prepare_deep_sleep();           // 4. 最后释放共享 I2C
// 5. 再关屏幕、进深睡
```

**顺序一句话**：`等播完 → 电量计 → codec → I2S 引脚 → I2C`。

> 一个真实的分岔场景：设备长按关机要播“再见”，但**用户听不到**。
> 排查时先问一句“是没播，还是没播完就断了”——两者的根因完全不同：
>
> | 现象 | 根因 | 定位方法 |
> | --- | --- | --- |
> | 一个字都听不到 | `write` 之前就失败了（格式没设 / codec 已 suspend） | 检查 `set_format()` 返回值，检查有没有漏调 `bsp_audio_wake()` |
> | 听到开头一小截就断 | DMA 没排空就被 `i2s_channel_disable()` | 补 `wait_audio_drained()` |
> | 完整听得到 | 正常工作 | — |

> 源码注释（Shinku `demo_low_power.c`）：
> “CW2017 与 ES8311 共用 I2C，必须先完成电量计写入/回读。”
> “即使 codec 寄存器操作失败，也继续停时钟并释放引脚。”

**第二条更有意思**：关机序列要**容忍失败**。
已经要睡了，某个寄存器写失败不应该阻止整个流程——
否则设备永远睡不下去，电池一夜耗尽。

## 7.9 音频能力边界

| 能做 | 不能做 / 代价大 |
| --- | --- |
| 16 kHz 单声道播放 | 同时播多个音轨混音（CPU 吃紧） |
| 短音效、语音提示 | 长时间高保真音乐 |
| Opus 逐包解码播放 | 整文件解码到内存 |
| 录音 + Opus 编码上行 | 本地长时间录音存储 |

> DOOM 项目在它的“待解决”表里明确写着：
> “声音系统：已禁用——ESP32-C3 RAM 不够同时跑音频”。
> 也就是说，**连 DOOM 这种重量级移植都只能放弃声音**。
> 你的应用如果要音频 + 图形同时跑，务必先算内存。

## 7.10 小结

- BSP 只吃 **PCM**：`bsp_audio_write(pcm, 字节数)`，解码是你自己的事；
- **`write`/`read` 阻塞** → 必须放独立任务；
- **`write` 返回 ≠ 声音响完**（阻塞只到 DMA 收下数据）：
  要关 I2S /  codec / 断电之前，按 `字节数/32 + 120ms` 显式等待排空；
- 大栈任务用**静态栈常驻**，别反复 `xTaskCreate`（会碎片化到“只停不播”）；
- **C3 上就用 16 kHz**，别重采样；
- `app_main` 第一件事应该是**静音**；
- 深睡前按顺序关：**等播完 →** 电量计 → codec → I2S 引脚 → I2C，且**容忍失败**。

下一章讲电量、熄屏和深睡的完整流程。

> 官方把“1 kHz 方波 / 录 3 秒回放”做成并发模板（worker-stop 握手）的逐行源码，见第 27 章（Audio 示例）。

> **延伸阅读 · 官方经验条目**：
> [音频压缩方式的权衡](https://github.com/FoloToy/ai-passport/blob/main/docs/reference/shinku-chen/audio-compression-trade-offs.zh_CN.md)（IMA-ADPCM / Opus / MP3 实测容量与解码成本） ·
> [网络音频流与内存预算](https://github.com/FoloToy/ai-passport/blob/main/docs/reference/phoenixzhc/network-audio-streaming-and-memory.zh_CN.md)（第 10c.5 节的官方版）
