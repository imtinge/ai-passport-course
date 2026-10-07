# 28. 官方 Battery 示例：CW2017 电量与电压

源码：`main/demo_battery.c`（57 行）。它是“**进页面建 timer、出页面删 timer + 周期刷新**”模板的
最小范例，比 Button 页还短，但把“低电量变红”“进页面先刷一次避免等 1 秒”两个细节做对了。

> 行号来自官方基线 `main/demo_battery.c`。

## 28.1 它验证什么

| 操作 | 行为 |
| --- | --- |
| 打开页面 | 显示电量百分比（SOC%）与电池电压（mV），每秒刷新；电量 < 20% 数字变红 |
| 任意键 | 无响应（本页不接按键） |
| OK（长按） | 返回菜单（框架拦截） |

源码注释（`demo_battery.c:1`）：`// main/demo_battery.c —— CW2017 电量与电压,每秒刷新。`
CW2017 是板载电量计芯片，通过 I2C 读；`bsp_battery_*` 把它封装成 `soc()`/`mv()` 两个函数（第 8 章）。

## 28.2 `tick`：读电量 + 优雅降级 + 低电量变红

```c
// main/demo_battery.c:11-25
// lv_timer 跑在 LVGL 任务里,已持有锁,可直接操作对象。
static void tick(lv_timer_t *t) {
    (void)t;
    int soc = bsp_battery_soc();
    int mv  = bsp_battery_mv();

    if (soc < 0) lv_label_set_text(s_soc, "-- %");        // 读不到 → 优雅降级
    else         lv_label_set_text_fmt(s_soc, "%d %%", soc);

    if (mv < 0)  lv_label_set_text(s_mv, "-- mV");
    else         lv_label_set_text_fmt(s_mv, "%d mV", mv);

    // 低电量变红,便于一眼判断
    lv_obj_set_style_text_color(s_soc,
        (soc >= 0 && soc < 20) ? lv_color_hex(0xFF5A5A) : lv_color_hex(0x39FF88), 0);
}
```

三个细节都值得抄：

1. **`< 0` 优雅降级**：电量计读不到时显示 `-- %` 而不是崩溃/显示乱码。板子上“外设暂时不可用”是常态，
   永远给一个可读的占位。
2. **低电量变红**：`soc < 20` 用红色 `0xFF5A5A`，否则用绿色 `0x39FF88`——一眼判断是否需要充电。
   这就是第 25 章 Display 里“反色”思路的同类：用颜色传达状态。
3. **`tick` 跑在 LVGL 任务内已持锁**，所以直接 `lv_label_set_text` / `set_style_text_color` 不用自己加锁。

## 28.3 `enter`：先刷一次，再起 timer

```c
// main/demo_battery.c:27-49（节选）
void demo_battery_enter(void) {
    s_scr = ui_pixel_screen_create("BATTERY");
    lv_obj_t *panel = ui_pixel_panel_create(s_scr, 24, 67, 192, 157, UI_YELLOW);
    s_soc = lv_label_create(panel);
    lv_obj_set_style_text_font(s_soc, &lv_font_montserrat_20, 0);
    ...
    tick(NULL);                                   // ★ 先立刻显示一次,不用等 1 秒
    s_timer = lv_timer_create(tick, 1000, NULL);  // ★ 之后每秒刷
    lv_screen_load(s_scr);
}
```

**关键细节：`tick(NULL)` 在起 timer 之前先手动调一次。** 否则用户进页面要干等 1 秒才看到数字，
体验很差。timer 回调设计为“可被手动调用”——它只用 `t` 参数 `(void)t`，不依赖 timer 上下文，
所以传 `NULL` 也安全。这是官方 demo 的一个小但体贴的写法。

## 28.4 `exit` / `key`

```c
// main/demo_battery.c:51-56
void demo_battery_exit(void) {
    if (s_timer) { lv_timer_delete(s_timer); s_timer = NULL; }   // ★ 退页面必删 timer
    if (s_scr) { lv_obj_delete(s_scr); s_scr = NULL; s_soc = s_mv = NULL; }
}

void demo_battery_key(bsp_btn_t btn, bsp_btn_ev_t ev) { (void)btn; (void)ev; }  // 不接按键
```

- `exit` 删 timer——和 Button 页（第 26 章）同一纪律：**进页面注册、出页面注销**。
- `key` 是**空实现** `(void)btn;(void)ev;`——这页没有任何按键交互，但钩子不能省（结构体成员留 `NULL`
  也行；这里官方选了给一个空函数，效果一样）。注意它**没有 `start/stop`**：因为本页没有后台任务，
  只有 LVGL timer（timer 由 `enter/exit` 管，不由 `start/stop` 管）。

## 28.5 这个 demo 能抄什么

- **周期刷新模板**：`lv_timer_create(tick, 1000, NULL)` + `enter` 建 / `exit` 删；
- **进页面先 `tick(NULL)` 立即显示**，别让用户等一个周期；
- **外设读不到 → `--` 占位**的优雅降级；
- **用颜色表达状态**（低电量变红）；
- **无后台任务就不实现 `start/stop`**——和第 24.1 节铁律一致。

和第 8 章的关系：第 8 章讲电量计、熄屏、深睡的原理，本章是官方把“读电量上屏”做成最小可跑实例。
想看“熄屏/深睡前怎么按序停外设”，见第 31 章（Low Power）。
