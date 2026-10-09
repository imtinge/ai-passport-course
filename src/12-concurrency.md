# 12. 并发：任务、队列与 LVGL 锁

> **可抄代码**：[D.14 通用并发模板](D-module-cookbook.md#d14-通用并发模板worker--通知--停止握手)。


ESP32-C3 是单核，但 FreeRTOS 会做抢占式调度——
所以你写的是“看起来并行”的代码，也就有了所有并发问题。
本章讲怎么不出事。

## 12.1 任务的实际形态

### 12.1.0 先把“任务在干嘛”说清楚

任务在任何时刻只处于四种状态之一。看懂这四个词，后面所有“优先级抢占”才有意义：

| 状态 | 在干什么 | 吃 CPU 吗 | 怎么出来的 |
| --- | --- | --- | --- |
| **运行态** Running | 此刻真的在被 CPU 执行 | 是 | 被调度器选中 |
| **就绪态** Ready | 排着队，等 CPU | 不吃，但只差一个抢占 | 等到 CPU 或同级让出 |
| **阻塞态** Blocked | 在等某件事（队列有数据 / 延时到 / 信号量） | **完全不吃** | `xQueueReceive` 等不到、`vTaskDelay` |
| **挂起态** Suspended | 被“无限期”停住，调度器不看他 | 完全不吃 | `vTaskSuspend()`，要 `vTaskResume()` 才回来 |

**最关键的一条：阻塞和挂起都不消耗 CPU。**
很多人以为“任务在跑就一直在烧 CPU”，其实一个 `vTaskDelay(pdMS_TO_TICKS(1000))`
会让它整整一秒处于阻塞态。深睡电流那些章节之所以能把均值压到几十微安，
前提就是**绝大部分时间是阻塞，不是就绪**。

另一个容易混的点：**就绪 ≠ 运行**。本板单核，同一时刻**只有一个**任务在运行态。
当一个高优先级任务从阻塞转为就绪，它会立刻把当前任务**抢**下去（抢占）；
同级任务之间则按时间片轮流，这就是“同级不是抢、但也不饿死”。

调度器三条规则（官方 FreeRTOS 语义）：

- **固定优先级**：永远选就绪态里优先级最高的那个；
- **时间片**：最高优先级有多个就绪任务时，轮流跑；
- **抢占**：更高优先级任务一旦就绪，立刻切过去。

**把任务做成“大部分时间阻塞”，而不是“大部分时间就绪”**——
这是嵌入式省电和流畅度的第一原则。UI 任务如果在没有重绘时还在空转轮询，
它就一直是就绪态，既抢 CPU 又费电。

下面这张表是**从官方基线源码里逐个查出来的**（不是经验估计），
行末都给了出处，你可以自己打开对照：

| 任务 | 谁创建 | 优先级 | 栈 | 出处 |
| --- | --- | --- | --- | --- |
| `main` | ESP-IDF | 1 | 8 KB（可配） | — |
| `IDLE` | FreeRTOS | 0 | 768 B（可配） | — |
| LVGL 刷新 | `bsp_lvgl_init()` | **4** | **7168 B** | esp_lvgl_port 2.9.0 `ESP_LVGL_PORT_INIT_CONFIG()` |
| 输入派发 `demo_input` | `main.c` | **5** | **4096 B** | `main/main.c:175` |
| 音频 worker | `demo_audio.c` | **4** | **4096 B** | `main/demo_audio.c:167` |
| 语音 worker | `demo_barbapapa.c` | **4** | **4096 B** | `main/demo_barbapapa.c:274` |
| 低功耗 worker | `demo_low_power.c` | **4** | **3072 B** | `main/demo_low_power.c:226` |
| NimBLE host | `demo_ble.c` | NimBLE 定 | `NIMBLE_HS_STACK_SIZE` | `main/demo_ble.c:148` |

`bsp_display_lvgl.c` 里是**原样**使用 port 默认配置（`ESP_LVGL_PORT_INIT_CONFIG()`），
没有改任何字段，所以上表的 LVGL 行就是 esp_lvgl_port 2.9.0 的默认值：

```c
#define ESP_LVGL_PORT_INIT_CONFIG()                \
    {                                              \
        .task_priority = 4,                        \
        .task_stack = 7168,                        \
        .task_affinity = -1,                       \
        .task_max_sleep_ms = 500,                  \
        .timer_period_ms = 5,                      \
    }
```

**优先级设计原则**（照抄这张表就不会错）：

- **做慢活的 worker 用 4，和 LVGL 同级。** 官方源码注释写明了理由：
  > “优先级 4（低于 LVGL/按键，音频慢一点无所谓，UI 必须流畅）”
  注意同级不是“抢”——单核上同级任务分时运行，LVGL 不会被饿死。
- **唯一官方“高于 LVGL”的是输入派发任务（5）。** 它能这么高，
  是因为它只做一件事：收队列 → 调 `bsp_lvgl_lock(500)` → 转发 → 放锁。
  持锁时间极短，且拿不到锁就 `return`。
  **你自己的任务不要模仿这个——除非你也这么短。**
- 别用 20+ 的高优先级，那会饿死 IDLE 任务，触发看门狗。

> ⚠️ **社区仓库的注释里会出现“LVGL（5）”。** 比如 PokeWalk 写着
> “优先级 4 —— 低于 LVGL（5），扫描不该抢画面的 CPU”。
> 那是**它自己固件**的配置，不是官方基线的值——官方基线是 **4**。
> 这类注释可以照抄它的**思路**（慢活别抢 UI），但**别照抄数字**。

### 12.1.1 单核板上别抄双核代码

网上（和某些板卡教程）讲 FreeRTOS 时给的例子几乎都是双核的，
因为要演示“核亲和性”这个卖点：

```c
xTaskCreatePinnedToCore(task_a, "A", 4096, NULL, 10, &hA, 0);  // 钉在核 0
xTaskCreatePinnedToCore(task_b, "B", 4096, NULL, 10, &hB, 1);  // 钉在核 1
```

**这段代码在本板上毫无意义。** 硬事实（`$IDF_PATH/components/soc/esp32c3/include/soc/soc_caps.h`）：

```c
#define SOC_CPU_CORES_NUM               (1U)   // C3 只有 1 个核
```

于是有三个后果：

1. **没有真正的并行。** 两个任务再也不会“同时”跑——时间片轮转而已。
   上例里 A 和 B 各自 `pdMS_TO_TICKS(1000)` 延时，日志会严格交替出现，
   不会像双核那样偶尔并发交错。
2. **亲和性参数是摆设。** `xTaskCreatePinnedToCore(..., 0)` 和 `(..., 1)`
   在单核上都能编过、都能跑，行为没有区别——最后那个 `xCoreID` 不会被 C3 真正采纳
   （IDF 内部对 unicore 做了退化处理）。
3. **`tskNO_AFFINITY` 才是你该用的值。** 官方 `esp_lvgl_port` 的默认配置里
   `.task_affinity = -1`，就是 `tskNO_AFFINITY` 的别名，意思是“随便哪个核都行”。
   本板只有 1 个核，填 -1 / 0 / 1 效果一样，但填 -1 意图最清楚、跨型号移植也最稳。

> **一句话**：C3 上谈“优先级抢占”和“时间片轮转”就够了，
> 谈“核亲和性”“负载均衡到两个核”是 S3/P4 的话题。
> 第 12.1 节表格里 LVGL 那行的 `.task_affinity = -1` 就是这个原因。

## 12.2 任务间通信：三选一

| 机制 | 用在哪 | 例子 |
| --- | --- | --- |
| **队列** `xQueue` | 传数据（按键事件、音频包） | 按键派发 |
| **信号量** `xSemaphore` | 通知“有事了”/互斥 | 播放任务唤醒 |
| **事件组** `xEventGroup` | 多事件聚合等待 | 小智主循环 |

### 队列（最常用）

```c
typedef struct { bsp_btn_t btn; bsp_btn_ev_t event; } input_event_t;

QueueHandle_t q = xQueueCreate(8, sizeof(input_event_t));

// 生产者（回调里，不阻塞）
xQueueSend(q, &input, 0);

// 消费者（任务里，阻塞等）
xQueueReceive(q, &input, portMAX_DELAY);
```

### 信号量（唤醒常驻任务）

```c
SemaphoreHandle_t sem = xSemaphoreCreateBinary();

// 触发
xSemaphoreGive(sem);

// 等待
xSemaphoreTake(sem, portMAX_DELAY);
```

**互斥用 `xSemaphoreCreateMutex()`**，但你真正需要互斥的地方（LVGL）
已经有专门的锁了，见 12.3。

### 事件组（等多个事件）

```c
const EventBits_t ALL_EVENTS = MAIN_EVENT_SEND_AUDIO | MAIN_EVENT_WAKE_WORD_DETECTED
                             | MAIN_EVENT_CLOCK_TICK | MAIN_EVENT_ERROR;

auto bits = xEventGroupWaitBits(event_group_, ALL_EVENTS,
                                pdTRUE,        // 读后清零
                                pdFALSE,       // 任一置位即返回（不是全部）
                                portMAX_DELAY);
```

### 共享变量与 `volatile`（第四种办法，最容易被漏掉的一个词）

队列、信号量、事件组之外还有第四种最原始的办法：**一个全局变量，一个任务写，另一个任务读**。
没有队列的拷贝开销，也没有信号量的等待，但它有一个硬性前提——
**这个变量必须声明成 `volatile`**。

```c
static volatile bool s_cancel;   // ← volatile 不能省
```

**`volatile` 是什么**：一句写给编译器看的声明——
“这个变量会在我看不见的地方被改掉，你别自作聪明把它缓存进寄存器。”

不加会怎样？看这段很常见的等待循环：

```c
while (s_busy) {           // 编译器看见：这循环里没人改 s_busy 啊
    vTaskDelay(1);         //   → 那我读一次就够了，后面一直用寄存器里的副本
}
```

编译器完全有理由认为“`vTaskDelay` 又不会动 `s_busy`”，于是**只在进循环前读一次**。
后果是：另一个任务明明已经把 `s_busy` 置成 false 了，**这个循环永远退不出来**。
设备表现为“卡死”，但日志一切正常——这是最难查的一类 bug。

**什么时候必须加**：

| 场景 | 要不要 `volatile` |
| --- | --- |
| 一个任务写、另一个任务读的标志位 | **必须** |
| 回调 / 中断里写、任务里读 | **必须** |
| 只在同一个任务内部使用的变量 | 不需要 |
| 已经用队列 / 信号量传递 | 不需要（它们内部已经处理好） |

**`volatile` 管不了的事**：它只保证“每次都真的去内存读”，**不保证原子性**。
如果跨任务对一个变量做“读—改—写”（比如 `s_count++`），`volatile` 救不了你，
那得上临界区或信号量。

**这块板的实际情况**：C3 是单核（第 12.1.1 节），在“一个写、一个读”的**布尔标志**场景下
`volatile` 就够了，不必额外加锁。官方与社区代码里那些 `static volatile bool` 都是这个用法——
`main/main.c` 的 `s_input_ready`、巴巴爸爸的 `s_cancel` / `s_busy`、配网章的 `s_state`。

## 12.3 LVGL 锁：唯一的硬性规则

```c
if (bsp_lvgl_lock(100)) {        // 超时 100 ms，失败返回 false
    lv_label_set_text(label, "...");
    bsp_lvgl_unlock();
}
```

规则回顾（第 5 章）：

| 在哪 | 要不要锁 |
| --- | --- |
| `lv_timer` 回调 | 不需要 |
| 自己的任务 | **需要** |
| 按键回调 | **需要** |
| `app_main` 建 UI | 需要 |

**忘记加锁的表现**：随机花屏、随机重启、莫名其妙的 `LoadProhibited`。
而且**复现概率和时机相关**——你测试十次可能都正常，用户第一次就中招。

**锁的超时不要设太长**：100–500 ms 够了。
设 `portMAX_DELAY` 意味着你的任务可能永远卡住。

## 12.4 回调派发的四种模式（汇总）

第 6 章讲过按键，这里把它抽象成通用模式——
**任何回调（音频、网络、定时器）都适用**：

```c
// 模式 1：回调里直接干（只在处理时间 < 1 ms 时接受）
void on_key(...) { counter++; }

// 模式 2（推荐）：入队，任务里干
void on_key(...) {
    input_event_t e = {.btn=btn, .event=ev};
    xQueueSend(q, &e, 0);        // 不阻塞
}

// 模式 3：回调里加锁分发（只在纯 UI 操作时用）
void on_key(...) {
    if (!bsp_lvgl_lock(500)) return;
    app_shell_on_key(btn, ev);
    bsp_lvgl_unlock();
}

// 模式 4：调度回主循环
up->OnClick([this]() {
    Application::GetInstance().Schedule([this]() { ChangeVolume(10); });
});
```

判断标准只有一条：**回调里有没有可能阻塞超过 1 ms？**
有就用模式 2 或 4。

## 12.5 销毁顺序：先停后删

这是官方的硬性规则：

> "A demo must stop every task, timer, callback, and event handler that can
> access its UI before deleting the screen."

标准模板：

```c
void my_page_exit(void) {
    // 1. 置停止标志 / 取消订阅
    s_running = false;

    // 2. 停定时器
    if (s_timer) { lv_timer_delete(s_timer); s_timer = NULL; }

    // 3. 停任务（协作停止握手，见 12.5.1；不要直接 vTaskDelete）
    worker_stop(&s_worker);

    // 4. 最后删 UI
    if (s_scr)   { lv_obj_delete(s_scr); s_scr = NULL; }
}
```

**顺序错了会怎样**：定时器回调访问一个已经 `free` 掉的 `lv_obj_t`——
在最好的情况下是 `LoadProhibited` 崩溃重启，最坏的情况是静默写坏内存。

> PokeWalk 的规则原文：
> “**删 screen 前先停定时器**——否则 timer 回调会访问野指针。
> `play_collect_exit()` 就是照这条写的：先 `lv_timer_delete` 再 `lv_obj_delete`。”

### 12.5.1 停止握手：不要用 `vTaskDelete` 硬删

上面第 3 步是最容易写错的地方。很多教程（包括本书前面某些地方）会写成
`vTaskDelete(s_task)`，**官方明确不这么做**：

> 音频、低功耗和 BLE 工作任务使用**协作取消和明确的退出握手**，
> 不再强制删除仍可能访问外设或 UI 的任务。
> —— `docs/hardware-design/AI_HARDWARE_DEVELOPMENT_GUIDE.zh_CN.md` §4

理由是：`vTaskDelete` 会在任务**任意一条指令处**把它抹掉。
如果这个任务此刻正持有 I2C 总线、正写 I2S DMA、或正持有 LVGL 锁，
删掉它就等于把这些资源永久留在“被占用”状态——
下一次初始化会失败，或者更糟：静默拿到一个半初始化的外设。

**官方契约（照抄就能用）**：

1. 工作任务在**最后一次共享状态访问之后**才发完成确认，然后**自己挂起**
   （`vTaskSuspend(NULL)` 或等信号量），**由生命周期所有者**决定何时 `vTaskDelete`；
2. **停止超时后保留任务句柄和完成信号量**，供后续重试；
3. **不能让旧任务清空新任务的句柄**——这是最隐蔽的一条：
   用户快速“退出→再进入”时，旧任务的收尾代码跑到一半，
   把新任务刚写进去的句柄/信号量清成 NULL，于是新任务再也没人能停止它。
   判断依据是“这个句柄是不是我这次启动的”，不是“它是不是非空”。

```c
// 工作任务侧
static void worker_task(void *arg)
{
    while (!s_stop_requested) {
        do_one_chunk();                 // 可能访问 I2S / I2C / UI（持锁）
    }
    // ★ 到这一行，之后不会再碰任何共享状态
    xSemaphoreGive(s_done_sem);         // 1. 先发完成确认
    vTaskSuspend(NULL);                 // 2. 再挂起，等所有者删除
}

// 所有者侧
static bool worker_stop(TickType_t timeout)
{
    s_stop_requested = true;
    if (xSemaphoreTake(s_done_sem, timeout) != pdTRUE) {
        return false;                   // 3. 超时：保留句柄与信号量，留给下次重试
    }
    vTaskDelete(s_task);                // 只有确认它已挂起，才真正删除
    s_task = NULL;
    return true;
}
```

> 第 27 章的 Audio 示例和第 30 章的 BLE 示例都是这套写法的官方活样本
> （手写 `host_task` + `xSemaphoreGive` + `vTaskSuspend`），建议对照读。
> 只有**确定不碰外设、不持锁**的纯计算任务，才可以直接 `vTaskDelete`。

## 12.6 一个真实的死锁案例

> 源码注释（小智项目 `application.cc`）：
> "Drop the remaining packets. Leaving them in the queue would
> stall the Opus codec task (it waits for queue space), which in
> turn **deadlocks the whole audio input pipeline**, as no new
> `MAIN_EVENT_SEND_AUDIO` event would ever be triggered again."

```c
if (protocol_ && !protocol_->SendAudio(std::move(packet))) {
    // 发送失败 → 把队列里剩下的全部丢掉
    while (audio_service_.PopPacketFromSendQueue())
        ;
    break;
}
```

**死锁链条**：网络断了 → 包发不出去 → 队列堆满 → Opus 编码任务等队列空间卡住
→ 不再产生新事件 → 主循环永远等不到事件 → 整个音频输入死掉。

教训：**生产者和消费者之间的队列，在消费者侧出错时必须排空。**
否则背压会传导回去，把上游卡死。

## 12.7 看门狗：为什么设备一直重启

如果你在日志里看到 `Task watchdog got triggered`，原因通常是：

- 某个任务**长时间不让出 CPU**（死循环、阻塞调用）；
- IDLE 任务被饿死。

**解法**：

```c
vTaskDelay(1);        // 让出 CPU，哪怕只 1 个 tick
```

DOOM 项目里有个很典型的例子：

```c
// D_DoomLoop runs the engine flat-out; yield once every few frames so
// the IDLE task can feed the task watchdog.
static unsigned int frame_count;
if ((++frame_count & 0x3) == 0) {
    vTaskDelay(1);
}
```

游戏主循环是“跑满”的，每 4 帧让出一次 CPU 就够了。
**这不影响手感，但能让看门狗吃饱。**

如果确实需要长时间独占（比如刷屏），可以临时喂狗或者调整看门狗配置，
但那通常是设计有问题的信号。

## 12.8 栈溢出：另一类静默杀手

> ⚠️ **ESP-IDF 的任务栈单位是“字节”，不是 FreeRTOS 原生的“字”。**
> 原生 FreeRTOS 里 `xTaskCreate` 的第二个参数是 `uint16_t usStackDepth`（字，通常 4 字节），
> 所以老代码里 `xTaskCreate(..., 4096, ...)` 实际是 16 KB。
> **ESP-IDF 明确改成了字节**（`freertos/idf_additions.h` 原文：
> *"The size of the task stack specified as the NUMBER OF BYTES. Note that this differs from vanilla FreeRTOS."*）。
> 所以本项目表格里的 `4096` 就是 4 KB，不是 16 KB。
> 抄老教程时最容易在这里少算 4 倍，症状就是莫名的随机崩溃。

```c
void my_task(void *arg) {
    char buf[8192];      // 8 KB 栈上数组 → 大概率溢出
}
```

栈溢出的表现是 `Stack protection fault` 或直接重启，
而且**日志里的行号常常是错的**（因为栈已经坏了）。

**规则**：

- 栈上数组**不超过 1 KB**；
- 大数组一律 `static` 或放 `.bss`；
- 需要大栈的任务，明确算好：局部变量总和 + 函数调用深度 × 256 B；
- 用 `uxTaskGetStackHighWaterMark()` 看实际用了多少：

```c
ESP_LOGI(TAG, "stack left: %u", uxTaskGetStackHighWaterMark(NULL));
```

## 12.9 可测试性：把逻辑和 IDF 分开

官方规则：

> "Keep testable state machines, protocols, timing, and layout calculations
> independent from ESP-IDF/LVGL and cover them with host tests."

意思是：**状态机、协议解析、布局计算这些纯逻辑，不要 `include` IDF 头文件**，
这样它们可以在 PC 上编译运行、写单元测试。

社区项目普遍有 `tests/` 目录，里面是能在主机跑的测试。
官方基线有 `tests/test_bsp_button.c`、`test_ui_pixel_math.c`、
`test_demo_navigation.c` 等——都是纯逻辑测试。

**这是值得养成的习惯**：把“能不能在 PC 上测”作为模块划分的标准。

## 12.10 小结

- 优先级：LVGL 是 **4**（官方基线），慢活 worker 也是 **4**，只有输入派发是 **5**；别饿死 IDLE；
- 通信：队列传数据、信号量通知、事件组聚合；
- **非 LVGL 任务碰 UI 必须 `bsp_lvgl_lock()`**；
- 回调派发四模式，判断标准是“会不会阻塞超过 1 ms”；
- 销毁顺序：**停定时器 → 停任务 → 删 UI**；
- 停任务要用**协作停止握手**（先发完成确认 → 挂起 → 所有者删除），
  **不要 `vTaskDelete` 硬删**可能正持有外设或 UI 的任务（12.5.1）；
- 队列出错要排空，否则背压会死锁上游；
- 每帧跑满的循环要 `vTaskDelay(1)` 喂看门狗；
- 栈上数组不超过 1 KB，用 `uxTaskGetStackHighWaterMark()` 验证。

第二部分到此结束。接下来是五个真实项目的拆解。

> **延伸阅读 · 官方经验条目**：
> [设备端对弈 AI 的墙钟预算](https://github.com/FoloToy/ai-passport/blob/main/docs/reference/shinku-chen/on-device-game-ai-wall-clock-budget.zh_CN.md)
> ——每秒约 1.5 万节点、用时间预算做迭代加深、让出 CPU 别饿死空闲任务（第 13 章 Doom 与棋类玩法直接相关）
