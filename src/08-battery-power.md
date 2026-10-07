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
CW2017 也不上报充电状态。所以别做“充电中”的动画——你拿不到这个信息。

### 显示惯例（其实是官方约定，不只是“社区习惯”）

电量百分比放在**屏幕右上角**，低电量（< 20%）变红提醒。

但注意：**这不是“社区通行”，是官方写进 `docs/development/ai-guide.zh_CN.md`
运行时规约和 `coding-conventions.zh_CN.md` 的交付要求**——
除非开发者指定其他位置或明确不需要，否则默认右上角显示电量，
读值为 `-1` 时优雅降级，且**不能遮挡应用自己的内容**。
维护官方基线主题时还要**避开右上角的白云装饰**（`add_cloud`，约 `x≈188, y≈8`，
源码 `main/ui_pixel.c` 里就是 `add_cloud(scr, 188, 8)`）。

### 电量计是怎么算出这个百分比的

CW2017 不是“测”出来的，是**按电池曲线换算**的。源码与官方指南能对上的细节：

| 事实 | 值 / 出处 |
| --- | --- |
| I2C 地址 | 7 位 `0x63`，与 ES8311 共用 I2C0（`bsp_pins.h`） |
| 电池 profile | **80 字节**，厂家为**优特利 520 mAh** 电芯生成；初始化时逐字节校验，不符则写入并回读 |
| 重启时序 | 写完按 `0x30 → 0x00` 重启，**最长等 5 秒**取到有效 SOC |
| SOC 寄存器 | 读 `0x04`–`0x05`，**只用高字节整数百分比**；`> 100` 视为未就绪，返回 **-1** |
| 电压 | 读 `0x02`–`0x03` 的 14 bit 值，`raw × 312.5 µV`，API 返回 mV |
| 事务超时 | **100 ms**，设备时钟 100 kHz |
| 芯片不应答 | `bsp_battery_init()` 返回 **`ESP_ERR_NOT_FOUND`**，上层禁用该项即可 |

**两条由此推出的纪律**：

1. **换电芯必须换 profile**，并重新做完整充放电验证——
   SOC 准不准取决于 profile 与电芯是否匹配，官方明说“不等于实验室标定结果”；
2. **首帧不要编一个百分比出来**。SOC 未就绪时返回 -1，界面显示 `-- %`
   等读数到位再刷新（真机验收清单里明确写了“不要求首帧虚构百分比”）。

> 顺带澄清一个常见困惑：商品页/早期资料写 **500 mAh**，官方
> `docs/hardware-design/specifications.zh_CN.md` 与 BSP profile 都是 **520 mAh**。
> 以官方规格文档与 BSP 为准（第 E.7 节的“事实来源优先级”）。

## 8.2 空闲自动熄屏

可穿戴设备没人操作时必须熄屏。社区普遍的阈值是
**空闲 2 分钟自动关机（深睡）**，短时间（比如 30 秒）先熄屏。

实现思路：用 `lv_timer` 或者在按键分发处重置一个“最后活动时间”计数器，
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

### 官方契约：每个函数内部到底做了什么

上面五步不是“打个招呼”，每一步背后有具体校验。
出处：`docs/reference/shinku-chen/deep-sleep-peripheral-power-off.zh_CN.md` +
`components/bsp` 实现。

| 步 | 接口 | 内部契约 |
| ---: | --- | --- |
| 1 | `bsp_battery_sleep()` | 写 CW2017 CONFIG 睡眠值，**等 5 ms 后回读**；写入/回读不符**重试一次** |
| 2 | `bsp_audio_sleep()` | 走完整 ES8311 suspend 序列，**校验 6 个关键寄存器**，失败重试一次，并**显式停两条 I2S channel** |
| 3 | `bsp_audio_prepare_deep_sleep()` | MCLK / BCLK / WS / DOUT / DIN 设为**关闭内部上下拉的输入** |
| 4 | `bsp_i2c_prepare_deep_sleep()` | 两个共享总线外设都完成后，SDA / SCL 设为关闭内部上下拉的输入 |
| 5 | `bsp_display_prepare_deep_sleep()` | 阻止 LVGL flush → 关显示 + Sleep In → 背光停低电平 → LCD SPI 安全电平并**在深睡期间 hold** |

补充几点容易踩的：

- **Wi-Fi / BLE 不在上面五步里**。它们由各自的 demo 页持有，进 Low Power 页前已经停了。
  如果你的应用让无线长期存活，**必须在 LCD 那一步之前**另行停止；
- **寄存器失败只记日志，不阻塞后续关闭**。宁可带着某个外设没睡透进深睡，
  也不能卡在半路把电池耗光；
- **终端引脚释放后如果深睡入口意外返回 → 重启**，不要试图恢复已部分脱离的总线。

### 为什么 `esp_codec_dev_close()` 不够

这是官方明确点名的一个坑，值得单独记：

`esp_codec_dev_close()` **只在 codec-dev 的输入或输出曾被打开时**才走 ES8311 disable 路径。
**开机后从没播放或录音过的话，即使 ES8311 控制接口和 I2S channel 都已初始化，这条路径也会被跳过。**

所以 BSP 不再做“默认格式的无声 open”，而是**通过独立控制接口直接写 suspend 寄存器**：
把 REG45 设为 `0x01`（关 BCLK/LRCK 内部上拉），回读 `0x00`、`0x01`、`0x0D`、`0x0E`、`0x12`、`0x45`，
5 ms 后重试一次完整序列。这样无论之前有没有开过 PCM，路径都会执行。

REG0E 写入值仍是 `0xFF`，但**只校验 bit6:0**（掩码与期望值都是 `0x7F`）——
读回 `0x7F` 或 `0xFF` 都算通过。在 bit7 读为零的硬件上，如果连这一位一起比，
会把**成功的 suspend 误判成失败**。其余五个寄存器做完整字节校验。

真正 suspend 失败时的行为也分两种：Low Power demo 会**取消 light sleep 并尝试恢复音频**；
deep sleep 则**记录失败并继续关流程**。

### 深睡 ≠ 熄屏：light sleep 不能调用这些接口

| | light sleep | deep sleep |
| --- | --- | --- |
| 终端引脚释放（`bsp_*_prepare_deep_sleep()`） | **禁止调用** | 必须调用 |
| LCD hold | **禁止** | 必须 |
| 音频恢复 | `bsp_audio_wake()` | 唤醒后走完整 BSP 初始化 |

原因很直接：light sleep 醒来要**原地继续跑**，引脚和 LCD 都被 hold 住了就回不来了。
另外官方 Low Power demo **只用 RTC 定时器唤醒**——本仓库尚未定义“共享 ADC 按键节点”的
可靠 deep-sleep 唤醒契约（这也是第 8.6 节“坑 2：深睡时 ADC 不工作”的官方印证）。

### 引脚的终端状态：LCD 是唯一的例外

`esp_deep_sleep_start()` 会隔离未 hold 的数字 GPIO，但**显式释放仍有价值**：
立刻停掉 I2S 时钟、去掉最后一笔事务后的 MCU 内部 I2C 上拉，并让过渡契约可被自动检查。

- 绝大多数引脚：输入 + 关闭内部上下拉；
- **LCD 引脚不浮空**：CS 保持**高**，SCLK / MOSI / DC / 背光保持**低**；
- 外部 I2C 上拉电阻是**硬件负载**，软件去不掉。

唤醒后 `bsp_display_init()` 会在 SPI 和 LEDC 接管前解除全局及单引脚 hold。

### 软件修不掉的那部分电流

`BSP_I2S_PA_CTRL = -1`——功放使能脚没接 MCU。以下电流**无法**被这些 API 消除：

- 功放待机电流；
- 稳压器静态电流；
- 外部上拉电流；
- 电池自放电。

寄存器回读全通过、待机电流仍偏高时，就该**逐个隔离测量这些硬件负载**，
而不是继续在软件里找。

### 唤醒源：只有 RTC 定时器是有板级证据的

官方基线只用了 `esp_sleep_enable_timer_wakeup(微秒)`。
**别想当然地用 `esp_sleep_enable_ext1_wakeup()` 去接按键**——
三个键不是三个独立的 RTC GPIO，它们是**一路 ADC 分压**（第 1.3 节），
只有 GPIO0 这一个引脚，而且深睡期间 ADC 已经断电。

社区里真正的坑不是“能不能唤醒”，而是**参数传错**：

> “GPIO0 唤醒源此前从未启用（**把引脚号当位掩码传入**）。”

`ext1` 的掩码参数要的是 `1ULL << GPIO_NUM_0`，不是 `GPIO_NUM_0`（=0，等于什么都不选）。
这种错误不会报错，只会表现为“怎么按都唤不醒”——见第 8.5 节。

## 8.5 唤醒后第一件事：查唤醒原因

深睡醒来程序从头跑，你通常需要知道“我是怎么醒的”：

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
> “GPIO0 唤醒源此前从未启用（把引脚号当位掩码传入）”

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

关于电源，有一个 fork 明确列出了“没有证据保证”的能力：

- 充电控制
- USB 插拔检测
- 可控功放使能（`BSP_I2S_PA_CTRL` 是 `-1`）
- 深睡唤醒（**该 fork 当时的状态**，官方 BSP 是有的）
- 电池精确容量或量产级电源指标

**读别人的 README 时要注意区分“这个 fork 没有”和“这块板子没有”。**
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
- 熄屏 10 步、深睡 6 步，**顺序都是“先停软件，再睡硬件”**；
- 关机序列要**容忍失败**，但 LVGL 卡住要 `esp_restart()`；
- `app_main` 开头查 `esp_sleep_get_wakeup_cause()`；
- 唤醒用**引脚号不是位掩码**；深睡时 ADC 不工作。

下一章讲存储：数据怎么存、素材放哪里。

> 官方把“电量/电压上屏”和“安全地睡/醒”做成最小实例的逐行源码，分别见第 28 章（Battery 示例）和第 31 章（Low Power 示例）。
