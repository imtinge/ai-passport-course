# 24. 官方示例框架：菜单、生命周期与 UI 小部件

第 2 部分讲了每个功能"概念上"怎么做（屏幕、按键、音频……）。
从第 25 章开始，我们**逐行读官方 `main/demo_*.c`**，看这些概念在生产代码里到底怎么落地。
但在读具体 demo 之前，得先读**框架**——因为每一个 demo 都是同一个套路：实现 5 个钩子函数，
往 `main.c` 的 `DEMOS[]` 里加一笔，剩下的（菜单、按键派发、长按返回、退出清理）全由框架管。

源码都在官方仓库 `folotoy/ai-passport` 的 `main/` 目录：
`demo.h`（接口）、`main.c`（菜单+派发）、`demo_navigation.c/.h`（菜单状态机）、
`ui_pixel.c/.h`（统一像素风 UI 小部件）。

> 这一章的所有行号都来自官方基线 `main/` 下的真实文件；编译用本书 `snippets/` 同一套官方参数。

> ### ⚠ 先确认你手上的是哪一份 `main/`
>
> 本书第 24–31 章讲的是**官方基线**（`folotoy/ai-passport`）的 7 个硬件测试 demo。
> 如果你本地工程是某个**二次开发 fork**（例如作者本机的 `D:\trae_projects\AIP\ai-passport`，
> 是巴巴爸爸 fork，`main/` 里只有 Bluey / Barbapapa / PawPatrol / MengKe / Volume
> 五个玩法页），那么：
>
> - `components/bsp` **是一致的**——板级事实（引脚、时钟、缓冲）照样对得上；
> - `main/` **不一样**——你不会在菜单里看到 `demo_display.c` 这类测试页，
>   但它们的文件可能仍然存在，只是**没有注册进菜单**。
>
> 所以照着章节去 `main/` 里找文件时，请认准 `DEMOS[]` 注册表和 `main.c` 的派发逻辑；
> 找不到的，先 `git branch -r --list 'origin/demo/*'` 看官方有没有对应分支。

## 24.1 `demo_entry_t`：每个 demo 只是一笔注册

接口定义在 `main/demo.h:7-14`，全文只有 14 行，是所有 demo 的"宪法"：

```c
typedef struct {
    const char *name;
    void (*enter)(void);                          // 持 LVGL 锁创建并载入页面
    void (*exit)(void);                           // lifecycle stop 成功后,持 LVGL 锁删除页面
    void (*key)(bsp_btn_t btn, bsp_btn_ev_t ev);  // lifecycle task 调用;函数自行缩短 LVGL 锁范围
    esp_err_t (*start)(void);                     // 可选:页面创建后,不持 LVGL 锁启动慢服务
    esp_err_t (*stop)(void);                      // 可选:删页面前,不持 LVGL 锁停止 producer
} demo_entry_t;
```

五个成员就是五个**钩子**，框架在固定时机调用它们。记住三条铁律（注释写在 `demo.h:8-13`）：

1. `enter()` / `exit()` **在框架已经持有 LVGL 锁时被调用**，你放心建/删 UI，不要自己再加锁；
2. `start()` / `stop()` **不持锁**，可以做慢操作（开 Wi-Fi、起任务）；
   `stop()` 必须在超时内停干净，否则返回错误、框架中止退出（防止带着后台任务切走页面）；
3. `key()` **不持锁**——它跑在按键派发任务里，要碰 LVGL 对象必须自己先 `bsp_lvgl_lock()`，
   并且**尽快缩小加锁范围**（按键回调不能阻塞）。

> 只有"需要慢服务"的页面才实现 `start/stop`。Display、Button、Battery 三个没有后台任务，
> 结构体里那两个成员直接留空（`NULL`）。**这是判断你要不要写 `stop()` 的标准**：没有 worker 就不要画蛇添足。

## 24.2 `DEMOS[]`：7 个官方 demo 的登记处

`main/main.c:25-40` 把 7 个官方页面登记成一个数组，下标就是菜单顺序：

```c
static const demo_entry_t DEMOS[] = {
    { .name = "Display", .enter = demo_display_enter, .exit = demo_display_exit,
      .key = demo_display_key },
    { .name = "Button",  .enter = demo_button_enter,  .exit = demo_button_exit,
      .key = demo_button_key },
    { .name = "Audio",   .enter = demo_audio_enter,   .exit = demo_audio_exit,
      .key = demo_audio_key, .start = demo_audio_start, .stop = demo_audio_stop },
    { .name = "Battery", .enter = demo_battery_enter, .exit = demo_battery_exit,
      .key = demo_battery_key },
    { .name = "Wi-Fi",   .enter = demo_wifi_enter,    .exit = demo_wifi_exit,
      .key = demo_wifi_key, .start = demo_wifi_start, .stop = demo_wifi_stop },
    { .name = "BLE",     .enter = demo_ble_enter,     .exit = demo_ble_exit,
      .key = demo_ble_key, .start = demo_ble_start, .stop = demo_ble_stop },
    { .name = "Low Power", .enter = demo_low_power_enter, .exit = demo_low_power_exit,
      .key = demo_low_power_key, .start = demo_low_power_start, .stop = demo_low_power_stop },
};
#define DEMO_COUNT (sizeof(DEMOS) / sizeof(DEMOS[0]))
```

注意到没有 `BOOT_DEMO_INDEX`、没有 `boot_into_demo()`——官方骨架就是"开机进菜单，你自己选"。
加一个新页面 = 在各自 `.c` 里实现 5 个钩子 + 在 `demo.h` 加声明 + 在这里 `DEMOS[]` 末尾追加一项。
**下标、`s_ok[]` 索引、菜单位置三者必须一一对应**（第 16 章 PokeWalk 的 bug 就是这里错位）。

## 24.3 `app_main`：初始化顺序与"单项失败不阻塞"

`main/main.c:193-242` 的 `app_main()` 是开机入口。它的初始化策略很克制：
**屏幕是 UI 载体，失败就没法显示菜单，直接退出**；其余外设单项失败只标 `[FAIL]`，不阻塞其他项。

```c
bsp_i2c_init();
bsp_i2c_scan();

// 屏幕失败 → 打清楚日志后退出（不做"串口菜单"降级，那会让文件复杂一倍）
if (bsp_display_init() != ESP_OK || !bsp_lvgl_init()) {
    ESP_LOGE(TAG, "显示/LVGL 初始化失败,demo 无法继续。检查 SPI 接线 ...");
    return;
}
bsp_display_backlight(100);

demo_navigation_init(&s_navigation, DEMO_COUNT);

s_ok[0] = true;                                   // Display 已确认可用
s_ok[1] = input_err == ESP_OK && button_err == ESP_OK;   // Button 依赖按键派发
s_ok[2] = (bsp_audio_init() == ESP_OK);           // Audio
s_ok[3] = (bsp_battery_init() == ESP_OK);         // Battery
s_ok[4] = true;                                   // Wi-Fi：页面内按需初始化并显示错误
s_ok[5] = true;                                   // BLE：同上
s_ok[6] = true;                                   // Low Power：同上
```

`s_ok[i]` 是个**降级标志**：菜单里失败的项是灰色 + `[FAIL]`，且不允许进入（第 3 章交互约定）。
Wi-Fi / BLE 这种"进页才初始化"的，预先标 `true`，页面内自己处理错误——这是官方"可选外设不阻塞"的范本。

## 24.4 按键派发：为什么先入队、再处理

三个按键走的是 **ADC 分压 + `esp_timer` 共享任务**（`bsp_button`），按键回调 `on_key` 就跑在这个共享任务上。
框架的做法是：**回调里只把事件塞进队列，立刻返回**，绝不阻塞共享任务（`main.c:186-191`）：

```c
// button callbacks run on the shared esp_timer task; enqueue only and return immediately.
static void on_key(bsp_btn_t btn, bsp_btn_ev_t ev, void *user) {
    if (!s_input_ready || !s_input_queue) return;
    const input_event_t input = { .btn = btn, .event = ev };
    (void)xQueueSend(s_input_queue, &input, 0);
}
```

队列由独立任务 `input_task` 消费（`main.c:152-160`），再调 `process_input`：

```c
static void input_task(void *arg) {
    (void)arg;
    input_event_t input;
    for (;;) {
        if (xQueueReceive(s_input_queue, &input, portMAX_DELAY) == pdTRUE)
            process_input(&input);
    }
}
```

为什么要这层间接？因为 `demo_xxx_key()` 里可能 `bsp_lvgl_lock()` 甚至启动任务，
如果在 `esp_timer` 共享回调里直接做，会卡住**所有**按键的后续事件。入队后由专用任务处理，
回调永远轻量。**这是板子上"按键回调不要干重活"的官方落地方式**，和你自己写应用时同理。

## 24.5 `process_input`：菜单导航 + 全局拦截长按

`process_input`（`main.c:104-150`）是大脑。它先把物理按键翻译成导航输入
（`navigation_input()`，`main.c:95-102`）：

```c
// 全局统一语义：上/下短按=移动；确定短按=进入；确定长按=返回（由本文件统一拦截）
static demo_nav_input_t navigation_input(bsp_btn_t btn, bsp_btn_ev_t event) {
    if (event == BSP_BTN_LONG && btn == BSP_BTN_OK) return DEMO_NAV_INPUT_OK_LONG;
    if (event != BSP_BTN_CLICK) return DEMO_NAV_INPUT_OTHER;
    if (btn == BSP_BTN_UP)   return DEMO_NAV_INPUT_UP_CLICK;
    if (btn == BSP_BTN_DOWN) return DEMO_NAV_INPUT_DOWN_CLICK;
    if (btn == BSP_BTN_OK)   return DEMO_NAV_INPUT_OK_CLICK;
    return DEMO_NAV_INPUT_OTHER;
}
```

然后分两种状态：

- **已在某个 demo 内**（`s_navigation.active >= 0`）：长按 OK → `DEMO_NAV_ACTION_EXIT`（先 `stop()`，
  持锁 `exit()`，回到菜单）；其它按键 → `DEMO_NAV_ACTION_FORWARD`，转发给 `demo->key()`。
- **在菜单中**：上/下 → 移动选中项并刷新；确定短按 → `DEMO_NAV_ACTION_ENTER`，**删掉菜单屏、
  调 `enter()`、再异步 `start()`**：

```c
// 进入一个 demo 的完整流程（main.c:134-147）
const demo_entry_t *demo = &DEMOS[result.index];
lv_obj_delete(s_menu_scr);                 // 删菜单屏
s_menu_scr = NULL;
demo->enter();                             // 持锁建页面
bsp_lvgl_unlock();

esp_err_t e = demo->start ? demo->start() : ESP_OK;   // 不持锁启动慢服务
if (e != ESP_OK)
    ESP_LOGE(TAG, "%s 页面启动失败: %s", demo->name, esp_err_to_name(e));
```

**关键纪律：长按 OK 返回是全局拦截**（`navigation_input` 把 `LONG+OK` 直接变成 `OK_LONG`），
demo 的 `key()` 永远收不到长按 OK，所以你的页面**不需要、也不能**自己处理"返回"——框架统一管。

## 24.6 `demo_navigation`：纯状态机，和你无关

`demo_navigation.c` 是个**只管菜单选择/进入/退出的状态机**，跟具体 demo 功能无关
（`init`/`handle`/`complete_exit`，`demo_navigation.c:3-40`）。它维护三个字段：

```c
typedef struct {
    size_t selected;   // 菜单里当前高亮项
    int    active;     // 当前是否在某 demo 内（>=0 表示在里面，=-1 表示在菜单）
    size_t count;      // demo 总数
} demo_navigation_t;
```

`handle()` 根据输入返回动作（`REFRESH` / `ENTER` / `EXIT` / `FORWARD`）。**这套状态机是官方测试菜单专属的**——
你写自己的应用时，导航完全可以自己设计（甚至不要菜单），不必照搬它；但理解它有助于你明白
`enter/exit/start/stop/key` 是被谁、在什么时机调用的。

## 24.7 `ui_pixel`：统一像素风 UI 小部件（但"外壳"不能抄）

每个 demo 的界面长得很像（天蓝底、纸色面板、墨色字、一只"小电视机器人"吉祥物），
因为它们都调用同一套 `ui_pixel` 小部件（`ui_pixel.c/.h`）：

| 函数 | 作用 |
| --- | --- |
| `ui_pixel_screen_create(title)` | 建一屏：天蓝底 + 顶部标题牌 + 云朵 + 草地带 |
| `ui_pixel_panel_create(parent,x,y,w,h,color)` | 带墨色描边和投影的方块面板（官方"卡片"） |
| `ui_pixel_label(parent,text,font,color)` | 指定字体/颜色的文字 |
| `ui_pixel_mascot_create(parent,x,y)` | 画那只原创吉祥物（含眨眼动画） |
| `ui_pixel_mascot_jump(m)` | 让吉祥物跳一下（按键反馈用） |
| `ui_pixel_set_selected(panel,sel,en)` | 菜单卡片选中/失败态上色 |

配色常量（你写自己的 UI 可以复用这些十六进制值，但**不能复用整个外壳**）：

```c
#define UI_SKY       0x1689E8   // 屏幕底色（天蓝）
#define UI_INK       0x17202A   // 墨色（文字/描边）
#define UI_PAPER     0xF4F4EA   // 纸色（面板底）
#define UI_YELLOW    0xFFD928   // 选中高亮
#define UI_RED       0xE43B2F   // 强调红
#define UI_GRASS     0x82BE2D   // 草地带
```

> ⚠️ **官方《衍生应用必须重新设计 UI》规则**（第 3.7 节引过）：
> "Reusing the current demo test menu, screens, or visual shell is prohibited;
> renaming, recoloring, or adding a feature to that shell does not count as a redesign."
>
> 也就是说：**菜单、`ui_pixel` 这套视觉外壳是用来验证硬件的，不是给你套壳做应用的。**
> 配色常量可以抄，整个 shell（菜单网格、吉祥物、面板）不能抄。BSP 和非 UI 的逻辑（lvgl 锁、
> 任务模板、stop 握手）则随便复用——第 25–31 章讲的就是这些"可抄的非 UI 逻辑"。

## 24.8 五条必须记住的纪律

1. **回调不阻塞**：`on_key` 只入队；`key()` 里要干活就下发到任务，自己立刻返回。
2. **锁规则**：`enter/exit` 框架已持锁；`key/start/stop` 不持锁，`key` 碰 LVGL 必须自己 `bsp_lvgl_lock(毫秒)`。
3. **降级用 `s_ok[]`**：单项外设失败标 `[FAIL]` 且不进菜单，其他项照常可测。
4. **长按返回是全局的**：`main.c` 拦截 `LONG+OK`，你的 `key()` 收不到它，不用自己处理退出。
5. **`DEMOS[]`/`s_ok[]`/菜单位置三者下标必须对应**——错位会串页、崩溃。

理解了框架，下面 7 章逐个拆官方 demo 的源码，你会发现它们全是这套纪律的复述。
