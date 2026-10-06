# 31. 官方 Low Power 示例：light / deep sleep + RTC 定时器唤醒

源码：`main/demo_low_power.c`（291 行）。这是 7 个官方 demo 里**外设操作最重**的一个：熄屏/深睡前
要按固定顺序停掉一整条硬件链（电量计 → 音频 codec → I2S → 共享 I2C → LCD），否则深睡会漏电或醒不来。
它也是另一个用 worker-stop 模板的页面。

> 行号来自官方基线 `main/demo_low_power.c`。

## 31.1 它验证什么

| 操作 | 行为 |
| --- | --- |
| 打开页面 | 两张模式卡：`LIGHT SLEEP 2 SEC` / `DEEP SLEEP 5 SEC`；显示"RTC 定时器唤醒"提示 |
| UP / DOWN（短按） | 选模式 |
| OK（短按） | 跑选中的睡眠（醒来后由 RTC 定时器唤醒） |
| OK（长按） | 返回菜单（框架拦截） |

源码注释（`demo_low_power.c:1-4`）点出设计边界：

```c
// main/demo_low_power.c —— light/deep sleep + RTC timer 唤醒验证。
// 两种模式入睡前均 suspend ES8311；light sleep 返回后显式恢复。
// deep sleep 还会按 CW2017 -> ES8311 -> I2S -> 共享 I2C -> LCD 顺序停止外设。
// 不使用按键唤醒：仓库尚无板级唤醒电路证据。
```

## 31.2 `RTC_DATA_ATTR`：deep sleep 后还想记得的数

```c
// main/demo_low_power.c:47-48
static RTC_DATA_ATTR uint32_t s_deep_sleep_magic;
static RTC_DATA_ATTR uint32_t s_deep_sleep_count;
```

`RTC_DATA_ATTR` 把变量放进 **RTC 慢速内存**——deep sleep 时这部分不掉电，普通 RAM 会清空。
所以用 `s_deep_sleep_magic`（魔数 `0x464F4C4F`）区分"冷启动"和"从 deep sleep 唤醒"，
用 `s_deep_sleep_count` 累计唤醒次数。`enter` 据此显示"DEEP TIMER WAKE #N"：

```c
// main/demo_low_power.c:184-191（节选 enter）
if (s_deep_sleep_magic == DEEP_SLEEP_MAGIC &&
    esp_sleep_get_wakeup_cause() == ESP_SLEEP_WAKEUP_TIMER) {
    lv_label_set_text_fmt(s_status, "DEEP TIMER WAKE  #%lu\nUP/DOWN: SELECT  OK: RUN",
                          (unsigned long)s_deep_sleep_count);
} else {
    lv_label_set_text(s_status, "UP/DOWN: SELECT  OK: RUN\nRTC TIMER WAKE ONLY");
}
```

## 31.3 菜单：两张模式卡 + 选中态

和 Display 页一样用查找表 + 环形下标表达"当前选哪一项"（`:193-207`）。`menu_refresh()` 调
`ui_pixel_set_selected` 给选中卡上黄底。`key` 里 UP/DOWN 切 `s_selected`、`OK` 下发睡眠命令
（`:277-290`）。这页的 `key` 和 Display 一样是"加锁改状态"的轻量写法。

## 31.4 `sleep_task`：命令循环 + 停止握手

```c
// main/demo_low_power.c:72-173（节选）
static void sleep_task(void *arg) {
    (void)arg;
    for (;;) {
        uint32_t command = 0;
        xTaskNotifyWait(0, UINT32_MAX, &command, portMAX_DELAY);
        if (command == SLEEP_COMMAND_STOP || s_stop_requested) break;   // 收到停止 → 收尾
        s_busy = true;
        if (command == SLEEP_COMMAND_DEEP) { ... }      // 深睡分支
        else { ... }                                    // 浅睡分支
        s_busy = false;
    }
    s_busy = false;
    xSemaphoreGive(s_stopped);                          // ★ 通知 stop()："我停好了"
    for (;;) vTaskSuspend(NULL);                        // ★ 挂起，等 stop() 来 vTaskDelete
}
```

又是 Audio 页（第 27 章）那套 worker-stop 模板：`s_stop_requested` 标志 + `xTaskNotify(STOP)`
+ `xSemaphoreGive(s_stopped)` + `vTaskSuspend`。`key` 里 `if (... || s_busy || s_stop_requested) return;`
保证睡眠进行中不被重复触发。

## 31.5 DEEP SLEEP：严格的外设停序

深睡前要按"电量计 → 音频 → I2S → 共享 I2C → LCD"顺序 suspend，且**任何一步失败也继续往下停**
（用 `log_deep_sleep_warning` 只记日志不中断），最后锁 LVGL 防关屏后刷屏，再进深睡：

```c
// main/demo_low_power.c:88-111（节选）
esp_err_t err = esp_sleep_enable_timer_wakeup(DEEP_SLEEP_TIME_US);
if (err == ESP_OK) {
    // CW2017 与 ES8311 共用 I2C，必须先完成电量计写入/回读。
    log_deep_sleep_warning("CW2017 suspend", bsp_battery_sleep());
    log_deep_sleep_warning("ES8311 suspend", bsp_audio_sleep());
    // 即使 codec 寄存器操作失败，也继续停时钟并释放引脚。
    log_deep_sleep_warning("I2S pin release",    bsp_audio_prepare_deep_sleep());
    log_deep_sleep_warning("shared I2C pin release", bsp_i2c_prepare_deep_sleep());

    // Wi-Fi/BLE 只由各自 demo 页持有；进入本页前已经停止并释放。
    if (!bsp_lvgl_lock(1000)) {                       // ★ 锁 LVGL，等当前 flush 完成
        ESP_LOGE(TAG, "deep sleep 前无法停止 LVGL 刷屏，重启恢复外设");
        esp_restart();
    }
    log_deep_sleep_warning("ST7789 suspend", bsp_display_prepare_deep_sleep());

    if (s_deep_sleep_magic != DEEP_SLEEP_MAGIC) s_deep_sleep_count = 0;
    s_deep_sleep_magic = DEEP_SLEEP_MAGIC;
    s_deep_sleep_count++;
    esp_deep_sleep_start();                           // ★ 进深睡（不会返回）
    ESP_LOGE(TAG, "esp_deep_sleep_start 意外返回，重启恢复外设");   // 若返回说明失败
    esp_restart();
}
```

**三个必须记的官方选择**：

1. **停外设顺序固定**：CW2017 和 ES8311 共用 I2C，必须先把电量计写完再动 codec；否则 I2C 总线冲突。
   这条顺序官方注释写明来自硬件设计，本书前言勘误 #6 也确认它就在官方 `demo_low_power.c` 里。
2. **失败也继续停**：`log_deep_sleep_warning` 只记日志不 return，因为"即使某步寄存器操作失败，
   也宁可继续释放引脚进深睡"，比卡在半状态强。
3. **深睡前锁 LVGL**：`bsp_lvgl_lock(1000)` 等当前 flush 完成，再 `bsp_display_prepare_deep_sleep()`
   关屏——**防止 LCD 关了之后 LVGL 任务还在刷屏**（那会访问已断电的硬件）。`esp_deep_sleep_start()`
   不返回；若返回说明失败，直接 `esp_restart()` 恢复外设。

> 深睡唤醒是**冷重启**：代码从 `app_main` 重新跑，`enter` 靠 `RTC_DATA_ATTR` 的魔数认出"我是被定时器唤醒的"。

## 31.6 LIGHT SLEEP：可恢复，必须对称 resume

浅睡不丢 RAM、能恢复，所以**只要试过 suspend 就必须 resume**，否则醒来外设是关的：

```c
// main/demo_low_power.c:122-163（节选）
set_status("LIGHT SLEEP: 2 SEC\nTimer wakeup");
vTaskDelay(pdMS_TO_TICKS(150));
esp_err_t err = esp_sleep_enable_timer_wakeup(LIGHT_SLEEP_TIME_US);
if (err == ESP_OK) {
    audio_suspend_attempted = true;
    err = bsp_audio_sleep();                          // ① 睡：挂起 ES8311
    failure = "Audio suspend";
}
if (err == ESP_OK) bsp_display_backlight(0);          // ② 关背光
int64_t before = esp_timer_get_time();
if (err == ESP_OK) {
    failure = "Light sleep";
    err = esp_light_sleep_start();                    // ③ 进浅睡（会被定时器唤醒返回）
}
int64_t slept_ms = (esp_timer_get_time() - before) / 1000;
esp_sleep_disable_wakeup_source(ESP_SLEEP_WAKEUP_TIMER);
if (audio_suspend_attempted) {                        // ★ 关键：试过 suspend 就必须 wake
    esp_err_t wake_err = bsp_audio_wake();
    if (err == ESP_OK && wake_err != ESP_OK) { err = wake_err; failure = "Audio resume"; }
}
bsp_display_backlight(100);                           // ④ 恢复背光
```

**`audio_suspend_attempted` 这个标志是点睛之笔**：浅睡可能因故没真正进入（比如 `esp_light_sleep_start`
返回错误），但只要**尝试过** suspend，醒来就必须 `bsp_audio_wake()` 恢复，否则音频芯片停在挂起态。
官方注释明确写："即使未进入 light sleep 也必须恢复"。`slept_ms` 还能算出实际睡了多久，上屏反馈。

## 31.7 `enter` / `start` / `stop` / `exit`

`start`（`:213-234`）建 `sleep_task`（栈 3072）+ 二值信号量；`stop`（`:236-261`）和 Audio/BLE 同款的
"cancel → notify STOP → 等 `s_stopped` → `vTaskDelete`"，并额外恢复背光 100% + 关唤醒源；
`exit`（`:263-275`）恢复背光、关唤醒源、删屏；`enter` 显示唤醒计数（见 31.2）。

## 31.8 这个 demo 能抄什么

- **`RTC_DATA_ATTR` 跨 deep sleep 保留状态**（魔数区分冷启动/唤醒）；
- **深睡前固定外设停序**（电量计→codec→I2S→I2C→LCD）+ 失败也继续；
- **深睡前锁 LVGL 防关屏后刷屏**；
- **浅睡"试过 suspend 就必须 wake"的对称恢复**；
- **worker-stop 模板**（和 Audio/BLE 同一套）；
- **不用按键唤醒**：官方注释说"仓库尚无板级唤醒电路证据"——这是诚实的工程边界，别照抄"按某键唤醒"的旧教程。

和第 8 章的关系：第 8 章讲电量、熄屏、深睡的原理与 wakeup 源，本章是官方把"安全地睡、安全地醒"
做成最小可跑实例。想看"运行时怎么省电不睡死"，第 8 章有 BLE/Wi-Fi 的 modem-sleep 思路，但本 demo
聚焦最彻底的 light/deep sleep 验证。
