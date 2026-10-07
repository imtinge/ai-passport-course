# 27. 官方 Audio 示例：1 kHz 方波 / 录 3 秒回放

源码：`main/demo_audio.c`（216 行）。这是**全仓库最值得抄的并发模板**——音频收发会阻塞较久，
官方把它放进独立任务，并设计了一套“停止握手”协议，后面第 18 章（巴巴爸爸）和第 12 章都复用同一套。

> 行号来自官方基线 `main/demo_audio.c`。

## 27.1 它验证什么

| 操作 | 行为 |
| --- | --- |
| OK（短按） | 播 1 kHz 方波 1 秒 |
| UP（短按） | 录 3 秒环境音，然后回放 |
| OK（长按） | 返回菜单（框架拦截） |

源码头部的注释**很重要**，是官方写给想复用这页的人看的警告（`demo_audio.c:1-5`）：

```c
// main/demo_audio.c —— 播 1kHz 方波 / 录 3 秒后回放。
// 音频收发会阻塞较久,故放到独立任务里跑,不占用按键回调与 LVGL 任务。
// Continuous BGM + UI/NVS needs feed-latency and Flash/cache checks; a tone alone
// does not validate this. See docs/hardware-design/AI_HARDWARE_DEVELOPMENT_GUIDE.md
// section 8.1 before reusing this demo for continuous playback.
```

**诚实声明**：这段 demo 只是验证“声卡能出声/能录音”。如果你要做**连续 BGM 同时跑 UI + 存 NVS**，
还要额外考虑喂数据的延迟、Flash/cache 竞争——单播一个 tone 证明不了这些。官方明确指出看
硬件设计指南 §8.1。**这正是本书一直强调的“编译通过 ≠ 硬件通过”的官方版注脚。**

## 27.2 常量与“为什么放独立任务”

```c
// main/demo_audio.c:20-25
#define SAMPLE_RATE   16000
#define TONE_HZ        1000
#define TONE_MS        1000
#define RECORD_SEC        3
#define CHUNK_SAMPLES   512          // 每次收发的采样数,控制临时缓冲大小
#define AUDIO_STOP_TIMEOUT_MS 2000
```

`CHUNK_SAMPLES 512` 是**采样数不是字节**：16 kHz / 16 bit / 单声道 = 32000 字节/秒，
512 采样 = 1024 字节 ≈ 32 ms 一块。块之间检查“要不要打断”。注意第 18 章巴巴爸爸用的是
`CHUNK_BYTES 2048`（64 ms）——两者都是“分块”思想，只是粒度不同，按你的延迟容忍度选。

> 为什么音频必须放独立任务？因为 `bsp_audio_write()` 是**阻塞调用**（I2S 缓冲满会等）。
> 若在 `key()` 或 LVGL 任务里直接播，按键和屏幕都会卡到播完。所以：按键只发“命令字”，
> 真正的播放在 `audio_task` 里做。

## 27.3 `play_tone`：生成方波并分块写

```c
// main/demo_audio.c:45-70
static void play_tone(void) {
    set_status("playing 1kHz...");
    if (bsp_audio_set_format(SAMPLE_RATE, 16, 1) != ESP_OK) { set_status("format failed"); return; }
    bsp_audio_set_volume(80);

    int16_t *buf = malloc(CHUNK_SAMPLES * sizeof(int16_t));   // 1 KB 临时缓冲
    if (!buf) { set_status("out of memory"); return; }

    const int period = SAMPLE_RATE / TONE_HZ;        // 每个方波周期的采样数 = 16
    int total = SAMPLE_RATE * TONE_MS / 1000;        // 总采样数 = 16000
    int phase = 0;
    while (total > 0 && !s_cancel) {                  // ★ 每块查 s_cancel → 32ms 内可打断
        int n = total < CHUNK_SAMPLES ? total : CHUNK_SAMPLES;
        for (int i = 0; i < n; i++) {
            buf[i] = (phase < period / 2) ? 6000 : -6000;   // ±6000 的方波（留余量防削顶）
            if (++phase >= period) phase = 0;
        }
        if (bsp_audio_write(buf, (size_t)n * sizeof(int16_t)) != ESP_OK) {
            set_status("playback failed");
            break;
        }
        total -= n;
    }
    free(buf);
    if (!s_cancel && total == 0) set_status("done. OK: tone  UP: record");
}
```

要点：① 方波就是“上半周 +6000、下半周 −6000”（满幅是 ±32767，取 ±6000 是留余量防削顶破音）；
② `period = SAMPLE_RATE/TONE_HZ = 16` 个采样一个周期；③ **循环里查 `s_cancel`**——这是“可打断播放”的关键，
外部想停只需置 `s_cancel=true`，最多 32 ms 内循环退出；④ 临时缓冲只有 1 KB，`free` 配对。

## 27.4 `record_and_play`：注意 C3 无 PSRAM 的分配风险

```c
// main/demo_audio.c:72-83（节选）
static void record_and_play(void) {
    if (bsp_audio_set_format(SAMPLE_RATE, 16, 1) != ESP_OK) { set_status("format failed"); return; }
    size_t total = (size_t)SAMPLE_RATE * RECORD_SEC;          // 48000 采样
    int16_t *rec = malloc(total * sizeof(int16_t));           // 3s @16k 16bit = 96KB
    if (!rec) {
        // C3 无 PSRAM,96KB 可能分配不到 —— 明确告知而不是静默失败
        ESP_LOGE(TAG, "录音缓冲 %u 字节分配失败(C3 内存紧张,可缩短 RECORD_SEC)",
                 (unsigned)(total * sizeof(int16_t)));
        set_status("record buffer alloc failed");
        return;
    }
    ...
}
```

**这就是“无 PSRAM”的代价**（第 11 章主题）：录 3 秒就要 96 KB 连续内存，C3 大概率分不到，
官方**不静默失败**，而是打日志 + 上屏提示，让用户知道该缩短 `RECORD_SEC`。回放逻辑和 `play_tone`
对称：分块 `bsp_audio_read` 录入、`bsp_audio_write` 放出，每块查 `s_cancel`。

## 27.5 `audio_task`：命令循环 + 停止握手（重点）

```c
// main/demo_audio.c:114-128
static void audio_task(void *arg) {
    (void)arg;
    for (;;) {
        uint32_t command = 0;
        if (xTaskNotifyWait(0, UINT32_MAX, &command, portMAX_DELAY) != pdTRUE) continue;
        if (command == AUDIO_COMMAND_STOP) break;              // 收到停止 → 跳出循环去收尾
        if (command == AUDIO_COMMAND_TONE) play_tone();
        else if (command == AUDIO_COMMAND_RECORD) record_and_play();
    }
    // The lifecycle owner retains the handle until it receives this acknowledgement.
    // No shared state or UI accesses are allowed after giving it. Stay alive so a
    // timed-out stop can safely retry; only the owner deletes/replaces this task.
    xSemaphoreGive(s_stopped);                                 // ★ 通知 stop()："我停好了"
    for (;;) vTaskSuspend(NULL);                               // ★ 挂起，等 stop() 来 vTaskDelete
}
```

**这是全章最该抄的模板**（和第 18 章、附录 D.14 同一套）：

1. **worker 不自己删自己**。收尾是 `xSemaphoreGive(s_stopped)` 然后 `for(;;) vTaskSuspend(NULL)`。
   源码注释写明原因：任务自删后栈回收有时机问题，**由 `stop()` 统一 `vTaskDelete` 更可控**。
   所以**不要**写 `vTaskDelete(NULL)` 自删——那会留下悬空句柄且删除时机不可控。
2. **通信零拷贝**。按键 → 任务用 `xTaskNotify` 传一个命令字；任务 → `stop()` 调用方用二值信号量
   表示“已停好”。都是事件驱动，不是轮询。

## 27.6 `enter` / `start` / `stop` / `exit` / `key`

`enter`（`:130-153`）只建 UI（画个唱片图标 + 状态文字），不碰音频——慢服务留给 `start`：

```c
// main/demo_audio.c:155-174（节选 start）
esp_err_t demo_audio_start(void) {
    if (s_task) return ESP_OK;                       // 已建（重复 start）直接成功
    if (s_stopped) { vSemaphoreDelete(s_stopped); s_stopped = NULL; }
    s_stopped = xSemaphoreCreateBinary();
    if (!s_stopped) { set_status("Cannot create audio worker"); return ESP_ERR_NO_MEM; }
    s_cancel = false;
    if (xTaskCreate(audio_task, "demo_audio", 4096, NULL, 4, &s_task) != pdPASS) {
        vSemaphoreDelete(s_stopped); s_stopped = NULL;
        set_status("Cannot create audio worker"); return ESP_ERR_NO_MEM;
    }
    return ESP_OK;
}
```

`stop`（`:176-198`）是“停止握手”的落地——`cancel` → 通知 STOP → 等 `s_stopped` 信号量（2 秒超时）
→ 确认后 `vTaskDelete`：

```c
// main/demo_audio.c:176-198（节选）
esp_err_t demo_audio_stop(void) {
    TaskHandle_t task = s_task;
    if (!task) { ... return ESP_OK; }                // 任务没起 = 成功
    s_cancel = true;                                 // 让正在播的循环尽快跳出
    xTaskNotify(task, AUDIO_COMMAND_STOP, eSetValueWithOverwrite);
    if (!s_stopped ||
        xSemaphoreTake(s_stopped, pdMS_TO_TICKS(AUDIO_STOP_TIMEOUT_MS)) != pdTRUE) {
        set_status("Audio stop timed out; retry");
        return ESP_ERR_TIMEOUT;                      // ★ 超时：中止退出，页面保留，允许重试
    }
    vTaskDelete(task);                               // 任务此刻挂起在 vTaskSuspend，安全删除
    s_task = NULL; vSemaphoreDelete(s_stopped); s_stopped = NULL;
    return ESP_OK;
}
```

**超时返回 `ESP_ERR_TIMEOUT` 是刻意的**：不让“带着后台任务切走页面”这种危险发生（第 24.1 节铁律 2）。

`key`（`:204-215`）是“只下单、不干活”的范本：

```c
// main/demo_audio.c:204-215
void demo_audio_key(bsp_btn_t btn, bsp_btn_ev_t ev) {
    if (ev != BSP_BTN_CLICK || !s_task || s_cancel) return;     // 没在播才接单
    uint32_t command = 0;
    if (btn == BSP_BTN_OK) command = AUDIO_COMMAND_TONE;
    else if (btn == BSP_BTN_UP) command = AUDIO_COMMAND_RECORD;
    if (!command) return;
    xTaskNotify(s_task, command, eSetValueWithOverwrite);       // 真正的播放在任务里
    if (!bsp_lvgl_lock(250)) return;
    if (s_mascot) ui_pixel_mascot_jump(s_mascot);              // 按键反馈
    bsp_lvgl_unlock();
}
```

## 27.7 这个 demo 能抄什么

- **阻塞 I/O 必进独立任务**：音频/网络/文件等长操作，绝不在 `key()`/`enter()` 里直接做；
- **worker-stop 握手三件套**：`s_cancel` 标志 + `xTaskNotify(STOP)` + 二值信号量确认 + `vTaskSuspend` 等删；
- **`stop()` 超时返回 `ESP_ERR_TIMEOUT`** 而非强删任务；
- **无 PSRAM 下大缓冲 `malloc` 可能失败** → 明确报错而非静默；
- **头注释的诚实声明**：tone 验证不了连续播放的延迟/cache 问题，复用前看硬件指南 §8.1。

和第 7 章、第 12 章、第 18 章的关系：第 7 章讲音频 API；第 12 章讲任务/队列/锁；第 18 章（巴巴爸爸，
你的 Trae 项目）的语音任务和第 12 章附录 D 是**同一套 worker-stop 模板**，可以对照看。
