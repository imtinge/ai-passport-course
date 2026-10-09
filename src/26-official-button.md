# 26. 官方 Button 示例：事件流 + 实时 ADC 电压

源码：`main/demo_button.c`（81 行）。这个 demo 看起来简单，却是**换过分压电阻的人必看的标定工具**——
它把三个按键产生的**四类事件**和**当前 ADC 电压**实时显示出来，你改了上拉/分压阻值后，
靠它重标 `BSP_BTN_MV_TABLE`（第 6 章讲过）。

> 行号来自官方基线 `main/demo_button.c`。

## 26.1 它验证什么

| 操作 | 行为 |
| --- | --- |
| 打开页面 | 顶部实时显示 ADC 电压（mV），下方滚动显示按键事件日志 |
| 任意键 | 日志里追加一行 `BTN: EV`（UP/DOWN/OK × PRESS/CLICK/DOUBLE/LONG） |
| OK（长按） | 返回菜单（框架拦截） |

源码注释点明核心（`demo_button.c:1-2`）：

```text
// main/demo_button.c —— 按键事件流 + 实时 ADC 电压。
// 电压显示是本页的核心:换了分压/上拉阻值的开发者靠它重标 BSP_BTN_MV_TABLE。
```

## 26.2 实时电压：用 `lv_timer` 周期性读 ADC

```c
// main/demo_button.c:21-27
// 每 100ms 刷新一次电压。lv_timer 跑在 LVGL 任务里,已持有锁,可直接操作对象。
static void tick(lv_timer_t *t) {
    (void)t;
    int mv = bsp_button_read_mv();
    if (mv < 0) lv_label_set_text(s_mv, "ADC read failed");
    else        lv_label_set_text_fmt(s_mv, "%d mV", mv);
}
```

**这是“在屏幕上显示实时传感器数据”的标准做法**：`lv_timer_create(tick, 100, NULL)` 注册一个
100 ms 周期回调，回调跑在 LVGL 任务内、已持锁，所以能直接 `lv_label_set_text` 而不用自己加锁。
`bsp_button_read_mv()` 返回当前 ADC 毫伏值（三键共用一个 ADC 分压网络，不同键对应不同电压窗口，
见第 6 章）。

> 为什么用 `lv_timer` 而不是直接在 `key()` 里读？因为电压要**持续**显示、不依赖按键，
> 而 `key()` 只在按键时触发。`lv_timer` 是 LVGL 里的“软定时器”，是板子上刷新动态数据的首选。

## 26.3 事件日志：一个滚动 ring buffer

```c
// main/demo_button.c:14-43
#define LOG_LINES 6
static char s_lines[LOG_LINES][32];
static int  s_line_cnt;

static void log_push(const char *text) {
    if (s_line_cnt < LOG_LINES) {
        snprintf(s_lines[s_line_cnt++], sizeof(s_lines[0]), "%s", text);
    } else {
        for (int i = 0; i < LOG_LINES - 1; i++)        // 满 6 行后整体上移一行
            memcpy(s_lines[i], s_lines[i + 1], sizeof(s_lines[0]));
        snprintf(s_lines[LOG_LINES - 1], sizeof(s_lines[0]), "%s", text);
    }
    char all[LOG_LINES * 32 + 1] = { 0 };
    for (int i = 0; i < s_line_cnt; i++) {
        strcat(all, s_lines[i]);
        if (i < s_line_cnt - 1) strcat(all, "\n");
    }
    lv_label_set_text(s_log, all);
}
```

**可抄点**：固定大小的二维 `char` 数组当 ring buffer，满了就 `memcpy` 上移（O(n) 但 n=6 无所谓），
再 `strcat` 拼成多行字符串喂给一个 `lv_label`。板子内存紧张，**不要**为了“日志”去 `malloc` 动态缓冲——
这种静态数组才是嵌入式正道。每行 32 字节、`LOG_LINES 6` 行，总共不到 200 字节，固定占用。

## 26.4 `enter` / `exit`：建标签 + 起 timer；退出删 timer

```c
// main/demo_button.c:45-70
void demo_button_enter(void) {
    s_line_cnt = 0;
    s_scr = ui_pixel_screen_create("BUTTON / ADC");
    lv_obj_t *panel = ui_pixel_panel_create(s_scr, 18, 58, 204, 184, UI_PAPER);
    s_mv = lv_label_create(panel);
    lv_obj_set_style_text_font(s_mv, &lv_font_montserrat_20, 0);
    lv_obj_set_style_text_color(s_mv, lv_color_hex(UI_SKY_DARK), 0);
    lv_obj_align(s_mv, LV_ALIGN_TOP_MID, 0, 8);
    lv_label_set_text(s_mv, "-- mV");
    s_log = lv_label_create(panel);
    lv_obj_set_style_text_color(s_log, lv_color_hex(UI_INK), 0);
    lv_obj_align(s_log, LV_ALIGN_TOP_LEFT, 9, 54);
    lv_label_set_text(s_log, "press any key...");
    ui_pixel_mascot_create(s_scr, 101, 238);
    s_timer = lv_timer_create(tick, 100, NULL);   // ★ 进页面就起 100ms 电压刷新
    lv_screen_load(s_scr);
}

void demo_button_exit(void) {
    if (s_timer) { lv_timer_delete(s_timer); s_timer = NULL; }   // ★ 退页面必须删 timer
    if (s_scr) { lv_obj_delete(s_scr); s_scr = NULL; s_mv = s_log = NULL; }
}
```

**铁律：`lv_timer` 必须在 `exit` 里 `lv_timer_delete`**。否则页面删了、timer 还在跑，回调里访问的
`s_mv`/`s_log` 已成野指针 → 崩溃。Battery 页（第 28 章）也是同一套：`enter` 建 timer、`exit` 删 timer。
凡是“进页面注册、出页面必须注销”的资源（timer、任务、事件处理器、Wi-Fi/BLE 栈），都要在 `exit`/`stop` 对称清理。

## 26.5 `key`：只把事件推入日志

```c
// main/demo_button.c:72-80
void demo_button_key(bsp_btn_t btn, bsp_btn_ev_t ev) {
    if ((unsigned)btn >= sizeof(BTN_NAME) / sizeof(BTN_NAME[0]) ||
        (unsigned)ev >= sizeof(EV_NAME) / sizeof(EV_NAME[0])) return;     // 边界保护
    char line[32];
    snprintf(line, sizeof(line), "%s: %s", BTN_NAME[btn], EV_NAME[ev]);
    if (!bsp_lvgl_lock(250)) return;       // 要改 LVGL 标签，先拿锁
    log_push(line);
    bsp_lvgl_unlock();
}
```

两个细节：

1. **边界保护**：`btn`/`ev` 是新版 `bsp_button` 的枚举，先确认在 `BTN_NAME`/`EV_NAME` 范围内再引用，
   防止未来枚举扩值导致数组越界。这种防御在“事件来自硬件”的代码里很值得。
2. **`key()` 里才加锁**：因为 `key` 不预持锁。`log_push` 内部会 `lv_label_set_text`，所以包在
   `bsp_lvgl_lock(250)` 内；`250` 毫秒超时拿不到就放弃本次更新，绝不阻塞按键派发。

> `BTN_NAME`/`EV_NAME` 是 `{"UP","DOWN","OK"}` 和 `{"PRESS","CLICK","DOUBLE","LONG"}`
> 两个字符串表（`demo_button.c:18-19`）。四类事件（PRESS/CLICK/DOUBLE/LONG）就是第 6 章讲的
> `esp_button` 组件产出的事件——这个 demo 把它们全部如实打印，是调试“我的双击怎么不触发”的利器。

## 26.6 这个 demo 能抄什么

- **实时数据上屏**：`lv_timer` 周期读传感器（电压/温度/电量）并 `set_text`，跑在 LVGL 任务内免加锁；
- **静态 ring buffer 日志**：固定数组上移 + `strcat`，不 `malloc`；
- **`enter` 建 timer、`exit` 必删 timer** 的对称纪律；
- **换分压电阻后用它重标 `BSP_BTN_MV_TABLE`**：这是它存在的首要价值。

和第 6 章的关系：第 6 章讲 ADC 分压 + 四类事件的原理，本章是官方把原理变成“可目视的标定工具”。
