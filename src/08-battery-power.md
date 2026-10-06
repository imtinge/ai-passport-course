# 8. 电量、熄屏与深睡

> **可抄代码**：[D.8 电量](D-module-cookbook.md#d8-电量) · [D.12 低功耗](D-module-cookbook.md#d12-低功耗)。


可穿戴设备是电池供电的。这一章讲三件事：怎么显示电量、
怎么熄屏、怎么进深睡——以及**为什么这三件事的顺序不能改**。

## 8.1 电量只有两个函数

```c
esp_err_t bsp_battery_init(void);
int bsp_battery_soc(void);    // 剩余百分比 0–100
int bsp_battery_mv(void);     // 电压，毫伏
esp_err_t bsp_battery_sleep(void);
```

**两个函数都可能返回负数**（电量计没焊、I2C 失败、芯片没准备好）。
所以显示逻辑必须降级，不能假设一定成功：

```c
int soc = bsp_battery_soc();
if (soc < 0) lv_label_set_text(s_soc, "-- %");
else         lv_label_set_text_fmt(s_soc, "%d %%", soc);
```

这是官方 demo 的写法。**不要写 `printf("%d%%", bsp_battery_soc())`**——
电量计失效时你会显示一个 `-1 %`。

### 电量计是可选件

> 源码注释（小智项目 `ai_passport_board.cc`）：
> "CW2017 fuel gauge is optional; a missing chip just disables battery UI."

以及：

> "CW2017 reports no charge state and the Passport has no charge-detect GPIO,
> so report a plain (discharging) reading."

**你无法判断设备是否在充电。** 板子上没有接充电检测引脚，
CW2017 也不上报充电状态。所以别做"充电中"的动画——你拿不到这个信息。

### 显示惯例

电量百分比放在**屏幕右上角**，这是社区通行的位置。
低电量（< 20%）变红提醒。

## 8.2 空闲自动熄屏

可穿戴设备没人操作时必须熄屏。社区普遍的阈值是
**空闲 2 分钟自动关机（深睡）**，短时间（比如 30 秒）先熄屏。

实现思路：用 `lv_timer` 或者在按键分发处重置一个"最后活动时间"计数器，
超时就调用熄屏序列。

## 8.3 熄屏序列：九步，顺序不能乱

> 源码：`main/app_shell.c`（pax-zhang fork）

```c
static void sleep_now(void)
{
    if (s_asleep) return;
    if (walkie_busy()) return;             // 有活没干完就不睡

    const app_prefs_t *p = app_prefs();
    if (p->lock_on || app_lock_visible()) {
        app_lock_show();                   // 锁屏界面
        lv_refr_now(NULL);
        if (p->lock_stay) { s_idle_ms = 0; return; }
    }

    s_asleep = true;
    bsp_display_backlight(0);              // 1. 灭背光
    lv_refr_now(NULL);                     // 2. 刷完最后一帧
    bsp_lvgl_flush_enable(false);          // 3. 禁止 LVGL 再推数据
    bsp_display_sleep(true);               // 4. 面板进睡眠
    bsp_audio_standby();                   // 5. 音频待机
    app_wx_pause(true);                    // 6. 暂停联网任务
    bsp_wifi_radio_suspend();              // 7. 挂起射频
    bsp_button_sleep_gpio(true);           // 8. 按键切 GPIO 唤醒模式
    bsp_lvgl_tick_enable(false);           // 9. 停 LVGL tick
    bsp_pm_set_sleeping(true);             // 10. 通知电源管理
}
```

**核心原则：先让软件停止访问硬件，再让硬件睡。**

如果顺序反了（比如先 `bsp_display_sleep()` 再 `bsp_lvgl_flush_enable(false)`），
LVGL 会往一个已经睡着的面板推数据——轻则花屏，重则 I2C/SPI 报错。

## 8.4 深睡序列：更严格的一套

深睡（deep sleep）比熄屏更彻底：CPU 停掉，只有 RTC 和唤醒源活着，
唤醒后**程序从头跑一遍**。

> 源码：`main/demo_low_power.c`（**官方基线**，`demo_low_power.c:91~118`；
> Shinku-Chen 的 fork 里也有同一套序列，说明它是社区共识而非某家独创）

```c
esp_err_t err = esp_sleep_enable_timer_wakeup(DEEP_SLEEP_TIME_US);
if (err == ESP_OK) {
    // CW2017 与 ES8311 共用 I2C，必须先完成电量计写入/回读。
    log_deep_sleep_warning("CW2017 suspend", bsp_battery_sleep());
    log_deep_sleep_warning("ES8311 suspend", bsp_audio_sleep());

    // 即使 codec 寄存器操作失败，也继续停时钟并释放引脚。
    log_deep_sleep_warning("I2S pin release", bsp_audio_prepare_deep_sleep());
    log_deep_sleep_warning("shared I2C pin release", bsp_i2c_prepare_deep_sleep());

    // 加锁等待当前 flush 完成，然后阻止 LVGL 在 LCD 关闭后再刷屏。
    if (!bsp_lvgl_lock(1000)) {
        ESP_LOGE(TAG, "deep sleep 前无法停止 LVGL 刷屏，重启恢复外设");
        esp_restart();
    }
    log_deep_sleep_warning("ST7789 suspend", bsp_display_prepare_deep_sleep());

    esp_deep_sleep_start();

    // 从 deep-sleep 准备接口返回后总线已不可在本次运行中恢复。
    ESP_LOGE(TAG, "esp_deep_sleep_start 意外返回，重启恢复外设");
    esp_restart();
}
```

这段话里藏着四条经验：

1. **`log_deep_sleep_warning()` 只打日志不中断**——关机序列要容忍失败。
   一个寄存器没写成功，不该让设备永远睡不下去（那会一夜耗尽电池）；
2. **LVGL 加锁失败就 `esp_restart()`**——这说明有东西卡住了刷屏，
   与其带病进深睡（可能变砖），不如重启；
3. **`esp_deep_sleep_start()` 理论上不返回**——返回了就是异常，直接重启；
4. **I2C 最后释放**——因为前面几步（电量计、codec）都要用它。

### 唤醒源：只有 RTC 定时器是有板级证据的

官方基线只用了 `esp_sleep_enable_timer_wakeup(微秒)`。
**别想当然地用 `esp_sleep_enable_ext1_wakeup()` 去接按键**——
三个键不是三个独立的 RTC GPIO，它们是**一路 ADC 分压**（第 1.3 节），
只有 GPIO0 这一个引脚，而且深睡期间 ADC 已经断电。

社区里真正的坑不是"能不能唤醒"，而是**参数传错**：

> "GPIO0 唤醒源此前从未启用（**把引脚号当位掩码传入**）。"

`ext1` 的掩码参数要的是 `1ULL << GPIO_NUM_0`，不是 `GPIO_NUM_0`（=0，等于什么都不选）。
这种错误不会报错，只会表现为"怎么按都唤不醒"——见第 8.5 节。

## 8.5 唤醒后第一件事：查唤醒原因

深睡醒来程序从头跑，你通常需要知道"我是怎么醒的"：

```c
void app_main(void) {
    esp_sleep_wakeup_cause_t wakeup = esp_sleep_get_wakeup_cause();
    if (wakeup != ESP_SLEEP_WAKEUP_UNDEFINED) {
        ESP_LOGI(TAG, "休眠唤醒原因: %d", wakeup);
    }
    // ...
}
```

`ESP_SLEEP_WAKEUP_UNDEFINED` = 上电启动（不是唤醒）。
其他可能值：`ESP_SLEEP_WAKEUP_TIMER`（定时到）、`ESP_SLEEP_WAKEUP_GPIO`（按键）。

**几乎所有社区项目的 `app_main` 开头都有这两行**——
这是一个便宜又高效的调试手段。

## 8.6 唤醒配置的两个坑

### 坑 1：引脚号 ≠ 位掩码

> Shinku README 里修过的 bug：
> "GPIO0 唤醒源此前从未启用（把引脚号当位掩码传入）"

```c
esp_sleep_enable_gpio_wakeup();        // 配置哪些引脚能唤醒
gpio_wakeup_enable(GPIO_NUM_0, GPIO_INTR_LOW_LEVEL);
```

`gpio_wakeup_enable()` 的第一个参数是 **gpio_num_t**（引脚号），
不是 `1ULL << GPIO_NUM_0`。传错就永远唤不醒。

### 坑 2：深睡时 ADC 不工作

熄屏后要用 GPIO 唤醒，不能用 ADC 按键检测——
**深睡期间 ADC 断电了**。所以熄屏序列里必须有
`bsp_button_sleep_gpio(true)` 这一步来做切换。

## 8.7 没有的能力：诚实清单

关于电源，有一个 fork 明确列出了"没有证据保证"的能力：

- 充电控制
- USB 插拔检测
- 可控功放使能（`BSP_I2S_PA_CTRL` 是 `-1`）
- 深度睡眠唤醒（**该 fork 当时的状态**，官方 BSP 是有的）
- 电池精确容量或量产级电源指标

**读别人的 README 时要注意区分"这个 fork 没有"和"这块板子没有"。**
本书凡是引用 fork 的自述，都会标明出处。判断某个能力到底有没有，
最可靠的方法是看 `bsp_*.h` 里有没有对应函数。

## 8.8 一个实用的电量预算思维

可穿戴设备的核心矛盾是：**屏幕是耗电大户，Wi-Fi 是第二大户。**

| 操作 | 相对耗电 |
| --- | --- |
| 深睡 | 极低（µA 级） |
| 熄屏待机 | 低 |
| 亮屏 + LVGL 刷新 | 中 |
| 音频播放 | 中高 |
| Wi-Fi 扫描/连接 | **高** |
| BLE 广播 | 中 |

所以社区里这些设计不是巧合：

- Wi-Fi 扫描要**节流**（PokeWalk 用专门的 pacing 算法控制扫描间隔）；
- 熄屏时**暂停联网任务**再挂射频；
- 后台任务优先级低于 LVGL（省 CPU）；
- 存档**节流写**（避免频繁写 flash）。

## 8.9 小结

- `bsp_battery_soc()` / `mv()` **可能返回负数**，必须降级显示；
- **无法检测充电状态**（没有 charge-detect GPIO）；
- 熄屏 10 步、深睡 6 步，**顺序都是"先停软件，再睡硬件"**；
- 关机序列要**容忍失败**，但 LVGL 卡住要 `esp_restart()`；
- `app_main` 开头查 `esp_sleep_get_wakeup_cause()`；
- 唤醒用**引脚号不是位掩码**；深睡时 ADC 不工作。

下一章讲存储：数据怎么存、素材放哪里。

> 官方把"电量/电压上屏"和"安全地睡/醒"做成最小实例的逐行源码，分别见第 28 章（Battery 示例）和第 31 章（Low Power 示例）。
