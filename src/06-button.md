# 6. 三个按键怎么撑起一套交互

> **可抄代码**：[D.6 按键](D-module-cookbook.md#d6-按键)。


三个键：上、下、确定。听起来很受限，但社区里做出了游戏、播放器、
AI 对话、养成宠物。本章讲这套交互的标准写法。

## 6.1 硬件回顾：一路 ADC，四种事件

三个键共用 GPIO0 的 ADC（0 / 300 / 595 mV），BSP 把这个细节完全藏起来了，
你只看到四个事件：

```c
typedef enum {
    BSP_BTN_PRESS = 0,   // 按下瞬间(低延迟,适合游戏类即时响应)
    BSP_BTN_CLICK,       // 单击(按下并抬起)
    BSP_BTN_DOUBLE,      // 双击
    BSP_BTN_LONG,        // 长按
} bsp_btn_ev_t;
```

**`PRESS` 和 `CLICK` 的区别很重要**：

- `PRESS`：手指刚按下去就触发。做游戏（移动、射击）用它；
- `CLICK`：按下**并抬起**才触发。做菜单导航用它。

用错了手感会很怪：菜单用 `PRESS` 会导致手指一碰就翻页；
游戏用 `CLICK` 会导致角色要等抬手才动。

## 6.2 全局交互约定

社区通用（官方 `main.c` 顶部注释）：

```text
上 / 下 短按   菜单中 = 移动选中项；页面内 = 该页自定义
确定 短按      菜单中 = 进入选中项；页面内 = 该页自定义
确定 长按      页面内 = 返回菜单（统一拦截）
```

**“确定长按返回”是全局约定**，由最外层统一拦截，页面自己不用处理。
改这个约定要在文档里明确写出来，否则用户会以为设备卡住了。

## 6.3 核心规则：回调里不许干活

这是本章唯一必须记住的规则。按键回调**不是在你的任务里执行的**，
它跑在 button 组件的任务里（具体说，是共享的 `esp_timer` 任务）。

官方规则：

> "Button callbacks must stay non-blocking. Audio, storage, networking, and
> other slow operations belong in worker tasks."

**回调里不能做的事**：播放音频、读写 NVS、发网络请求、`vTaskDelay`、
以及任何可能等锁很久的操作（包括长时间持有 `bsp_lvgl_lock`）。

### 标准解法：入队 + 独立任务

这是官方基线的写法，**建议直接抄**：

> 源码：`main/main.c`（官方基线 `folotoy/ai-passport`）

```c
typedef struct {
    bsp_btn_t btn;
    bsp_btn_ev_t event;
} input_event_t;

#define INPUT_QUEUE_DEPTH 8
static QueueHandle_t s_input_queue;
static TaskHandle_t s_input_task;
static volatile bool s_input_ready;

static void input_task(void *arg) {
    (void)arg;
    input_event_t input;
    for (;;) {
        if (xQueueReceive(s_input_queue, &input, portMAX_DELAY) == pdTRUE) {
            process_input(&input);     // 慢活在这里做
        }
    }
}

static esp_err_t input_dispatch_init(void) {
    s_input_queue = xQueueCreate(INPUT_QUEUE_DEPTH, sizeof(input_event_t));
    if (!s_input_queue) return ESP_ERR_NO_MEM;
    if (xTaskCreate(input_task, "demo_input", 4096, NULL, 5, &s_input_task) != pdPASS) {
        vQueueDelete(s_input_queue);
        s_input_queue = NULL;
        return ESP_ERR_NO_MEM;
    }
    return ESP_OK;
}

// button callbacks run on the shared esp_timer task; enqueue only and return immediately.
static void on_key(bsp_btn_t btn, bsp_btn_ev_t ev, void *user) {
    (void)user;
    if (!s_input_ready || !s_input_queue) return;
    const input_event_t input = { .btn = btn, .event = ev };
    (void)xQueueSend(s_input_queue, &input, 0);     // 注意最后一个参数是 0：不等待
}
```

四个细节：

1. **`xQueueSend(..., 0)`**——最后一个参数是超时，传 0 表示队列满就直接丢，
   绝不阻塞。丢一个按键事件远比卡住整个系统好。
2. **队列深度 8**——按键不会产生比这更快的事件流；
3. **任务栈 4096 字节**——够用，因为 `process_input` 里没有大数组；
4. **`s_input_ready` 标志**——UI 建好之前不接受按键。注意它的声明是
   `static volatile bool`：回调里写、任务里读的共享标志，**`volatile` 不能省**，
   省了会读到寄存器里的旧副本（第 12.2 节末尾有完整解释）。

然后在 `process_input` 里做真正的事（这里才加锁、才做慢活）：

```c
static void process_input(const input_event_t *input) {
    // ...
    if (!bsp_lvgl_lock(500)) return;      // 慢活前先拿 UI 锁
    demo->key(input->btn, input->event);
    bsp_lvgl_unlock();
}
```

## 6.4 四种派发模式对比

社区里一共有四种做法，按复杂度递增：

| 模式 | 谁在做 | 适用 | 代表项目 |
| --- | --- | --- | --- |
| **回调里直接处理** | 回调自己 | 极简，处理只要几微秒 | 简单 demo |
| **队列 + 任务**（推荐） | 独立任务 | 绝大多数应用 | 官方基线、Shinku |
| **回调里加锁 + 分发** | 回调自己 | 只要改 UI、无慢活 | pax-zhang |
| **Schedule 回主循环** | 主事件循环 | 复杂状态机 | 小智 AI |

**模式 2（队列）** 是默认选择：**回调只入队，其它一律在任务里做。**

**模式 3** 长这样（pax-zhang 的写法）：

```c
static void on_key(bsp_btn_t btn, bsp_btn_ev_t ev, void *user)
{
    (void)user;
    if (!bsp_lvgl_lock(500)) return;
    app_shell_on_key(btn, ev);      // 只分发给页面状态机
    bsp_lvgl_unlock();
}
```

它能这么写，是因为 `app_shell_on_key` 只做 UI 切换，没有慢活。
**但这有个风险**：如果某个页面偷偷在 `key()` 里播了音频，
就会在回调里阻塞。所以官方基线用了更保险的队列方案。

**模式 4**（小智）会在第 17 章讲，核心是：

```cpp
up->OnClick([this]() {
    Application::GetInstance().Schedule([this]() { ChangeVolume(10); });
});
```

## 6.5 不想用回调？也可以轮询

有的项目（比如 DOOM）不用回调，直接轮询 ADC 电压：

```c
bsp_button_read();      // DOOM 的 bsp_doom 里是读当前按键状态
```

**轮询适合游戏**——游戏本来就有主循环，每帧读一次按键状态最自然，
而且能同时检测“多个键一起按”。

轮询的缺点是拿不到“长按”“双击”这种时序事件，得自己计时。
**做菜单用回调，做游戏用轮询。**

## 6.6 按键相关的两个真实坑

### 坑 1：ADC1 是 unit 级独占资源

> 源码注释（pax-zhang `components/bsp/src/bsp_button.c`）：
> “ADC1 是 unit 级独占资源：iot_button 与 `bsp_button_read_mv()` 必须共用同一个
> oneshot 句柄。谁第二个调 `adc_oneshot_new_unit()` 谁就拿到
> ‘adc1 is already in use’。”

解法（小智项目的写法，三个键共用一个 unit）：

```cpp
adc_oneshot_unit_init_cfg_t init_cfg = { .unit_id = ADC_UNIT_1 };
ESP_ERROR_CHECK(adc_oneshot_new_unit(&init_cfg, &adc_handle_));

button_adc_config_t adc_cfg = {};
adc_cfg.adc_handle = &adc_handle_;   // ★ 复用同一个句柄
adc_cfg.unit_id = ADC_UNIT_1;
adc_cfg.adc_channel = ADC_CHANNEL_0;

adc_cfg.button_index = kAdcButtonUp;
adc_cfg.min = BSP_ADC_BUTTON_UP_MIN;     // 0
adc_cfg.max = BSP_ADC_BUTTON_UP_MAX;     // 150
adc_button_[kAdcButtonUp] = new AdcButton(adc_cfg);
// DOWN / OK 复用同一个 adc_cfg，只改 min/max 和 index
```

**记住：整块板子只能 `adc_oneshot_new_unit()` 一次。**

### 坑 2：衰减档必须一致

> 源码注释（同上）：
> “电压读取的衰减档必须与 button 组件内部的 `ADC_BUTTON_ATTEN` 一致——
> 通道只被配置一次，两边对不上会让读数与按键阈值错位。”

```c
#define BSP_BTN_ATTEN  ADC_ATTEN_DB_12   // 量程约 0~3100mV，覆盖松开态
```

> **这行注释里的“3100 mV”别当真**。三个官方口径对照：
>
> | 来源 | ATTEN3（12 dB）量程 |
> | --- | --- |
> | 规格书表 5-6（校准后有效范围） | **0~2500 mV，误差 ±35 mV** |
> | IDF v5.5.3 文档（adc_calibration.rst） | “仅支持低于 **2800 mV** 的输入电压” |
> | BSP 源码注释 | 0~3100 mV ← **与两个官方来源都不符** |
>
> 实际含义：12 dB 档能**可靠测量**的是 0~2.5 V；再往上读数会饱和（顶到满码）。
> 松开态被 10 kΩ 上拉拉到 3.3 V，ADC 读出来就是饱和值——**检测依然可靠**
> （饱和也是确定性状态，和“按下”的几百 mV 差得远），但你**不能**拿这个档
> 去测 2.5 V 以上的真实电压，比如电池分压、传感器输出。
> 官方数值见附录 F.3。

## 6.7 深睡唤醒时的按键

熄屏后按键要能唤醒设备。BSP 提供了专门的接口：

```c
bsp_button_set_wake_cb(cb);        // 设置唤醒回调
bsp_button_sleep_gpio(true);       // 切到 GPIO 唤醒模式
esp_sleep_enable_gpio_wakeup();    // IDF 原生
```

> **移植提醒**：`bsp_button_set_wake_cb()` 与 `bsp_button_sleep_gpio()` 是课程配套 fork 对官方 `bsp_button.h` 的扩展；官方基线只提供 `bsp_button_init` 与 `bsp_button_read_mv`，自己移植时以官方头文件为准。

注意：**休眠期间 ADC 不工作**，所以唤醒必须走 GPIO 电平变化。
这也是为什么熄屏序列里有 `bsp_button_sleep_gpio(true)` 这一步。

> 一个社区修过的真实 bug（Shinku 的 README）：
> “GPIO0 唤醒源此前从未启用（把引脚号当位掩码传入）”。
> `esp_sleep_enable_gpio_wakeup()` 要的是**引脚号**，
> 而 `gpio_wakeup_enable(pin, ...)` 的掩码是 `1ULL << pin`。别混。

## 6.8 按键会抖：一次按下为什么可能触发好几次

机械按键按下时，金属触点不是“啪”一下接通就完事——
它会在**几毫秒内弹跳若干次**，电平来回跳变。这叫**抖动（bounce）**。

```text
理想波形：  ──────┐___________________________┌────
实际波形：  ──────┐_┌_┌__┌___┌_______________┌────
                   弹跳 5~20 ms
```

如果你的代码是“看到电平变低就算按下”，那一次物理按下会触发**好几次**事件。
典型症状：按一下播了两次音、菜单跳了两格。

### 这块板的答案：组件已经内置了消抖

好消息是，**你大概率不用自己写**——官方用的 `espressif/button` 组件自带消抖，
而且已经在 `sdkconfig` 里配好了：

```ini
# sdkconfig（官方基线）
CONFIG_BUTTON_PERIOD_TIME_MS=5    # 扫描间隔 5 ms
CONFIG_BUTTON_DEBOUNCE_TICKS=2    # 连续 2 次采样一致才认定状态变了
```

**实际消抖时长 = 2 × 5 ms = 10 ms**（出处：`sdkconfig` 与
`managed_components/espressif__button/Kconfig`，Kconfig 里的说明原文是
“One `CONFIG_BUTTON_DEBOUNCE_TICKS` equal to `CONFIG_BUTTON_PERIOD_TIME_MS`”）。

组件里的实现逻辑很朴素（`iot_button.c`）：连续采样计数，攒够 `DEBOUNCE_TICKS` 次
才认定状态真的变了，中途任何一次不一致就清零重数。

同一组 Kconfig 里还有两个你会关心的默认值：

| 配置项 | 默认 | 含义 |
| --- | --- | --- |
| `BUTTON_PERIOD_TIME_MS` | 5 | 按键扫描间隔（范围 2–500） |
| `BUTTON_DEBOUNCE_TICKS` | 2 | 消抖阈值（范围 1–7） |
| `BUTTON_SHORT_PRESS_TIME_MS` | 180 | 短按判定时长 |
| `BUTTON_LONG_PRESS_TIME_MS` | 1500 | 长按判定时长 |

**要改就在 `menuconfig` 里改**，别去动 `sdkconfig`（那是构建生成的）。
如果发现某个键偶尔连发，把 `BUTTON_DEBOUNCE_TICKS` 调到 3~4 试试。

### 什么时候“内置消抖”帮不了你

走组件回调（6.3 的推荐写法）时消抖是自动的。但这两种情况要自己当心：

1. **用轮询自己读**（6.5 节那套 `bsp_button_read()`）——
   你读到的就是原始电平，抖动没有被过滤，得自己做时间戳判断；
2. **深睡唤醒**（6.7 节）——唤醒路径走的是 GPIO 电平变化，
   不走组件的扫描循环，**没有消抖**。如果你发现睡着时按一下醒两次，
   在唤醒回调里加个“上次唤醒时间戳”判断即可。

> 这块板的三个键是 **ADC 分压**（6.1 节），抖动表现为**电压在阈值附近来回跳**，
> 不是 GPIO 的高低电平跳变。所以这里的“消抖”实际是过滤 ADC 采样值——
> 组件替你做了，但你要知道它在过滤什么。

## 6.9 小结

- 四种事件：`PRESS`（游戏）/ `CLICK`（菜单）/ `DOUBLE` / `LONG`（返回）；
- **回调里不许干活**——标准解法是“入队 + 独立任务”；
- `xQueueSend(..., 0)`：队列满就丢，绝不阻塞；
- 做菜单用回调，做游戏用轮询；
- **ADC1 只能 new 一次 unit**，三个键复用句柄；
- 熄屏后靠 GPIO 唤醒，ADC 不工作；
- **消抖组件已内置（10 ms）**，但轮询自读和深睡唤醒这两条路径没有。

下一章讲音频——这块板子上最容易出“玄学 bug”的部分。

> 官方把“按键事件 + 实时 ADC 电压”做成标定工具的逐行源码，见第 26 章（Button 示例）。
