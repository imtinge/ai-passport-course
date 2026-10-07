# 5. 屏幕与 LVGL

> **可抄代码**：[D.2 屏幕/背光](D-module-cookbook.md#d2-屏幕与背光) · [D.3 页面骨架](D-module-cookbook.md#d3-lvgl-页面骨架五个钩子) · [D.4 中文](D-module-cookbook.md#d4-中文显示) · [D.5 图片](D-module-cookbook.md#d5-显示图片)。


如果你没写过 GUI 程序，LVGL 会是你在这块板子上遇到的第一个“范式转换”。
本章从“你会的 C”出发讲它，并且会一路讲到**怎么显示一张图片**
和**怎么让中文真正显示出来**——这两件事是新人的头两个坑。

## 5.1 先确认版本：LVGL 9.5

官方基线用的是 **LVGL 9.5**（`lvgl/lvgl ^9.5.0`）+ 移植层
**esp_lvgl_port 2.9.0**。

这件事很重要：**网上大量教程是 LVGL 7/8 的，API 拼写不一样。**
搜到教程先核对版本，否则你会写出编译不过的代码。

| LVGL 8（旧教程常见） | LVGL 9（本固件） |
| --- | --- |
| `lv_scr_load()` | `lv_screen_load()` |
| `lv_obj_del()` / `lv_obj_del_async()` | `lv_obj_delete()` / `lv_obj_delete_async()` |
| `lv_disp_t` / `lv_disp_get_default()` | `lv_display_t` / `lv_display_get_default()` |
| `lv_disp_draw_buf_t` | `lv_draw_buf_t` |
| `lv_img_*` / `lv_img_set_src` | **`lv_image_*` / `lv_image_set_src`** |

> 另注意：姊妹仓库 `ai-passport-micropython` 也用 LVGL v9，
> 但走的是 Python 绑定（`lv.label()`、`.set_text()`），**和本章的 C API 不能混用**。

> ⚠️ **屏幕 SPI 时钟：官方两份文档自己就打架。**
> `docs/README.zh_CN.md` 的硬件能力表写 **40 MHz**，
> 而 `components/bsp/include/bsp_pins.h` 里的 `BSP_LCD_PCLK_HZ` 是 **80 MHz**，
> 硬件开发指南（`AI_HARDWARE_DEVELOPMENT_GUIDE`）同页也写 **80 MHz**，mode 0。
> 第三方实测贴跟着 README 抄成了 40 MHz。**信 `bsp_pins.h`：这块屏跑 80 MHz。**
> 这类“摘要表没跟上源码”的事在本仓库不是孤例——凡是要用的数字，回到头文件确认一遍。

## 5.2 三步点亮

```c
esp_err_t e = bsp_display_init();     // 1. 硬件：SPI、面板、背光 PWM
if (e != ESP_OK) return;              //    屏幕失败通常直接放弃（UI 的唯一载体）

if (!bsp_lvgl_init()) return;         // 2. 接上 LVGL：驱动、缓冲、tick、任务

bsp_display_backlight(100);           // 3. ★ 点亮背光
```

第三步最容易被忘。官方 BSP 的背光默认 duty 是 0，
**不点亮就是纯黑**——而且你会以为是自己画错了。

> 源码注释（pax-zhang）：“背光默认 duty=0。必须在建 UI 之前点亮，
> 否则 shell 里排版卡住就会一直黑屏。”

## 5.3 一帧画面是怎么上屏的

理解这条链路，能帮你判断“为什么我的动画卡”。

```text
你的代码：lv_label_set_text() / lv_obj_set_style_*()   ← 只是改对象状态、标脏
   │（必须持有 bsp_lvgl_lock）
   ▼
taskLVGL（esp_lvgl_port 创建，5ms tick）运行 lv_timer_handler()
   │  每 CONFIG_LV_DEF_REFR_PERIOD=20ms 检查一次脏区域，目标 50 FPS
   ▼
LVGL 把脏区域渲染进绘制缓冲：240×40 像素 RGB565（≈19.2 KB 内部 RAM，单缓冲）
   │  FLUSH_START 事件：BSP 按圆角半径 30 把圆角外像素清 0
   ▼
esp_lcd 面板驱动（swap_bytes：小端 RGB565 → SPI 大端）
   ▼
SPI2 DMA 事务队列（80 MHz，trans_queue_depth=10）→ ST7789P3
```

**四个推论：**

1. **改属性 ≠ 立刻刷屏。** LVGL 合并脏区域、最多每 20 ms 刷一次。
   所以不要去调“强制同步刷新”接口，那只会打乱它的节奏。
2. **一屏分 8 个 40 行的块传输。** 缓冲只有 40 行，
   所以动画要尽量做**局部脏区**——全屏重绘会连续占满多个 20 ms 周期。
3. **圆角不是面板特性。** BSP 在 `FLUSH_START` 事件里逐行遮罩
   （`bsp_display_lvgl.c` 的 `rounded_flush_event`）。
   为什么不用 LVGL 自带的 `clip_corner`？因为全屏圆角裁剪会生成 ARGB 图层，
   在 24 KB 内存池 + 无 PSRAM 上不可靠。
4. **没有 TE 信号**，高速动画理论上可能撕裂——用局部更新、降低重绘面积来规避。

> ⚠️ **官方指南在这里和源码对不上，以源码为准。**
> `docs/hardware-design/AI_HARDWARE_DEVELOPMENT_GUIDE.zh_CN.md` 写的是
> “240 × 20 像素的单 DMA 缓冲，RGB565 约 9.6 KB”，而当前
> `components/bsp/src/bsp_display_lvgl.c` 是 `#define BSP_LVGL_DRAW_BUFFER_LINES 40`
> （注释：40 行单缓冲约 19.2 KB）。
> 原因是指南标注的“代码复核日期 2026-09-14”早于 `perf(display): improve LVGL
> refresh throughput`（2026-09-20，把行数从 20 提到 40）。
> **这是第 E.7 节“文档滞后”的又一个实例**——看到 9.6 KB 不用怀疑自己算错了。
> 量化影响：一屏从 16 个块变成 8 个块，全屏重绘占满的 20 ms 周期数减半。

## 5.4 任务模型与锁（最容易出事的地方）

`bsp_lvgl_init()` 之后存在一个独立任务，参数来自
`ESP_LVGL_PORT_INIT_CONFIG()` 的默认值：

| 参数 | 值 |
| --- | --- |
| 任务名 / 优先级 | `taskLVGL` / **4** |
| 任务栈 | 7168 字节（内部 RAM） |
| tick 定时器 | 5 ms 周期 esp_timer（心跳，**不是**渲染周期） |
| 渲染周期 | 20 ms（目标 50 FPS） |
| 锁 | **递归互斥**（同任务可重复加锁，跨任务互斥） |

这几个数字是**核对过源码的**：官方 `bsp_display_lvgl.c` 原样使用
`ESP_LVGL_PORT_INIT_CONFIG()`，没有改任何字段，所以
优先级 4 / 栈 7168 / tick 5 ms 就是 esp_lvgl_port 2.9.0 的默认值，
可以直接查 `managed_components/espressif__esp_lvgl_port/include/esp_lvgl_port.h`。

> ⚠️ **但社区仓库的注释里会出现“LVGL（5）”**（PokeWalk 就写着
> “优先级 4 —— 低于 LVGL（5）”）。那是它自己固件的配置。
> **思路照抄（慢活别抢 UI），数字别照抄，以你手上的源码为准。**
>
> 还有一点容易误读：官方**输入派发任务是 5，比 LVGL 高**
> （`main/main.c:175`）。它能这么高是因为只做“收队列 → 加锁 → 转发 → 放锁”，
> 持锁时间极短。**你的 worker 不要模仿这个数字**，照第 12.1 节的表配就好。

### 三条铁律

**铁律 1：只有 taskLVGL 可以裸调 `lv_*`。**

你的 worker、按键回调、输入任务，碰 LVGL API 前后必须：

```c
if (bsp_lvgl_lock(100)) {          // 超时（ms）返回 false 就放弃本次更新
    lv_label_set_text(label, "更新了");
    bsp_lvgl_unlock();
}
```

不加锁的表现**不是报错，是随机花屏和随机重启**——两个任务同时改对象树。
这类 bug 极难复现，所以规则要刻进肌肉记忆。

**铁律 2：`lv_timer` 的回调运行在 taskLVGL 内——不用加锁，但绝不能阻塞。**

> 源码注释（官方 `demo_battery.c`）：
> “lv_timer 跑在 LVGL 任务里,已持有锁,可直接操作对象。”

回调里 `vTaskDelay`、等信号量、读写音频，**都会卡住整屏刷新**。
基线电池页的 1 秒刷新就是标准示范：回调里只读 SOC 然后 `set_text`。

**铁律 3：不要自己调 `lv_timer_handler()` / `lv_tick_inc()`。**

心跳与调度已由 port 接管。也不要调强制立即刷新类 API。

### 什么时候需要加锁

| 场景 | 要不要锁 |
| --- | --- |
| `lv_timer` 回调里 | 不需要（已在 taskLVGL 内） |
| 按键回调里 | **需要**（跑在 button 组件的共享 esp_timer 任务） |
| 自己的 worker 任务里 | 需要 |
| `app_main` 里建 UI | 需要 |
| 页面的 `enter()` / `exit()` | **已由框架持锁**（见 5.6） |

## 5.5 对象模型与常用 API

**对象树**：screen 是根对象（`lv_obj_create(NULL)`），
子对象生命周期归父对象所有——**删掉 screen 会连带删除全部子对象**。
所以 `exit()` 里 `lv_obj_delete(scr)` 之后，要把保存的子对象指针全部置 NULL。

**切页姿势**：先在**未加载**的 screen 上建好全部子对象，
最后一次 `lv_screen_load(scr)`——否则用户会看到控件一个个弹出来。

**样式是局部绑定的**：

```c
lv_obj_set_style_text_font(label, &my_font, LV_PART_MAIN | LV_STATE_DEFAULT);
```

最后一个参数是 **part | state 的组合**。
你常看到的 `0` 就是 `LV_PART_MAIN | LV_STATE_DEFAULT` 的简写，两者等价。
传 `LV_STATE_PRESSED` 表示“按下时的样式”。

**这引出一条重要的坑**：改主题字体/默认字体
**不会**替换控件上已显式设置的字体——
这是“我明明设了中文字体，标题还是方块”的常见原因。

**常用 API**（仓库实际使用的拼写，可照抄）：

| 用途 | LVGL 9 API |
| --- | --- |
| 建 screen / 通用对象 | `lv_obj_create(NULL)` / `lv_obj_create(parent)` |
| 建标签 | `lv_label_create()`、`lv_label_set_text()`、`lv_label_set_text_fmt()` |
| 建图片 | `lv_image_create()`、`lv_image_set_src()` |
| 载入屏幕 | `lv_screen_load(scr)` |
| 删除对象 | `lv_obj_delete(obj)` |
| 对齐/尺寸 | `lv_obj_align()`、`lv_obj_center()`、`lv_obj_set_width()`、`lv_obj_set_pos()` |
| 样式 | `lv_obj_set_style_bg_color/text_color/text_font/text_align/pad_all()` |
| 颜色 | `lv_color_hex(0xRRGGBB)` |
| 事件 / 定时器 | `lv_obj_add_event_cb()`、`lv_timer_create()` |
| 内置字体 | `&lv_font_montserrat_14`、`&lv_font_montserrat_20` |

## 5.6 一个完整可抄的页面

官方基线的电量显示页，**结构完整、可直接当模板**。
注意它的 `enter` / `exit` / `key` 三段式。

> 源码：`main/demo_battery.c`（官方基线 `folotoy/ai-passport`）

```c
static lv_obj_t   *s_scr, *s_soc, *s_mv;
static lv_timer_t *s_timer;

// lv_timer 跑在 LVGL 任务里,已持有锁,可直接操作对象。
static void tick(lv_timer_t *t) {
    (void)t;
    int soc = bsp_battery_soc();
    int mv  = bsp_battery_mv();

    if (soc < 0) lv_label_set_text(s_soc, "-- %");
    else         lv_label_set_text_fmt(s_soc, "%d %%", soc);

    if (mv < 0)  lv_label_set_text(s_mv, "-- mV");
    else         lv_label_set_text_fmt(s_mv, "%d mV", mv);

    lv_obj_set_style_text_color(s_soc,
        (soc >= 0 && soc < 20) ? lv_color_hex(0xFF5A5A) : lv_color_hex(0x39FF88), 0);
}

void demo_battery_enter(void) {
    s_scr = ui_pixel_screen_create("BATTERY");
    lv_obj_t *panel = ui_pixel_panel_create(s_scr, 24, 67, 192, 157, UI_YELLOW);

    s_soc = lv_label_create(panel);
    lv_obj_set_style_text_font(s_soc, &lv_font_montserrat_20, 0);
    lv_obj_set_style_text_color(s_soc, lv_color_hex(UI_INK), 0);
    lv_obj_align(s_soc, LV_ALIGN_TOP_MID, 0, 18);
    lv_label_set_text(s_soc, "-- %");

    s_mv = lv_label_create(panel);
    lv_obj_set_style_text_color(s_mv, lv_color_hex(UI_INK), 0);
    lv_obj_align(s_mv, LV_ALIGN_TOP_MID, 0, 52);
    lv_label_set_text(s_mv, "-- mV");

    lv_obj_t *battery = ui_pixel_panel_create(panel, 38, 91, 100, 38, UI_GRASS);
    lv_obj_set_style_border_width(battery, 4, 0);
    ui_pixel_mascot_create(s_scr, 101, 238);

    tick(NULL);                                   // 先立刻显示一次,不用等 1 秒
    s_timer = lv_timer_create(tick, 1000, NULL);
    lv_screen_load(s_scr);
}

void demo_battery_exit(void) {
    if (s_timer) { lv_timer_delete(s_timer); s_timer = NULL; }
    if (s_scr) { lv_obj_delete(s_scr); s_scr = NULL; s_soc = s_mv = NULL; }
}
```

五个值得学的地方：

1. **`enter` / `exit` / `key` 三段式**——社区统一的页面接口；
2. **`tick(NULL)` 先手动调一次**——否则第一秒是空白；
3. **`soc < 0` 显示 `--`**——优雅降级，而不是崩；
4. **`exit` 里先删 timer 再删 screen**——顺序错了会访问野指针；
5. **删完把指针置 NULL**。

### 官方的页面契约（五个钩子的精确定义）

如果你要在官方基线的菜单里加页面，这是必须遵守的契约：

| 钩子 | 调用时是否持 LVGL 锁 | 该做什么 |
| --- | --- | --- |
| `enter()` | **是**（500 ms） | 建 screen 与全部子对象、`lv_screen_load`；**不做慢操作** |
| `exit()` | **是** | `stop` 成功后才调；删 screen 并把对象指针全部置 NULL |
| `key(btn, ev)` | 否（自己按需短锁） | 处理页内按键；改 UI 时自取 `bsp_lvgl_lock(250)` |
| `start()` | 否 | 可选；建 worker / 开无线电 / 开始播放，允许慢 |
| `stop()` | 否 | 可选；**必须在超时内拿到 worker 停止确认**；返回非 OK 则中止退出、页面保留 |

最后一条很关键：**`stop()` 超时不要强删任务，让页面保留、允许重试。**

结构体本身叫 **`demo_entry_t`**（在 `main/demo.h`，注意不是 `demo_if_t`）：

```c
typedef struct {
    const char *name;
    void (*enter)(void);                          // 持 LVGL 锁创建并载入页面
    void (*exit)(void);                           // lifecycle stop 成功后,持 LVGL 锁删除页面
    void (*key)(bsp_btn_t btn, bsp_btn_ev_t ev);  // lifecycle task 调用;自行缩短锁范围
    esp_err_t (*start)(void);                     // 可选:页面创建后,不持锁启动慢服务
    esp_err_t (*stop)(void);                      // 可选:删页面前,不持锁停止 producer
} demo_entry_t;
```

官方基线内置 **7 个页面**（`main/main.c` 的 `DEMOS[]`，下标就是数组顺序）：

> 官方仓库 `folotoy/ai-passport` 的 `DEMOS[]` **始终只有这 7 项**，并没有 `BOOT_DEMO_INDEX` /
> `boot_into_demo()` 这类开机直达宏。第 18 章的「巴巴爸爸图鉴」是作者（你）用 **Trae**
> 在自己的工作副本里生成的实战项目（图片 + 中文 + 语音三件套），**不在官方仓库**，放在「实战拆解」部分当范例。第 24–31 章会逐行拆解这 7 个官方 demo 的源码。

| 下标 | 名字 | enter/exit/key | start/stop | 说明 |
| --- | --- | --- | --- | --- |
| 0 | Display | ✅ | — | 屏幕/背光/圆角 |
| 1 | Button | ✅ | — | 实时显示 ADC 电压，**换电阻后标定就靠它** |
| 2 | Audio | ✅ | ✅ | 录音 3 秒后回放 |
| 3 | Battery | ✅ | — | SOC% 与电压 |
| 4 | Wi-Fi | ✅ | ✅ | 扫描附近 AP（**只扫描不连接**，不存凭证） |
| 5 | BLE | ✅ | ✅ | NimBLE peripheral 广播 |
| 6 | Low Power | ✅ | ✅ | 浅睡 / 深睡 |

> 只有“需要慢服务”的页面才实现 `start/stop`——Display、Button、Battery 三个
> 没有后台任务，所以结构体里那两个成员留空。
> **这是判断你要不要写 `stop()` 的标准**：没有 worker 就不要画蛇添足。

`OK 长按` 在 `main.c` 里被**全局拦截**为退出当前页
（`navigation_input()` 把 `BSP_BTN_LONG + BSP_BTN_OK` 映射成 `DEMO_NAV_INPUT_OK_LONG`），
所以你的页面**不需要自己处理“返回”**——但也不能指望吃掉长按。

### 七个 demo 各自的“该抄哪一段”

这些页面不是示例玩具，是**官方给的可抄模板**。逐个说清楚该看什么
（数值都从源码核过）：

| 页面 | 界面 | 该抄的东西 |
| --- | --- | --- |
| **Display** | 大色块循环，UP/DOWN 调背光 100/50/10% | `key()` 加锁模板：`if (!bsp_lvgl_lock(250)) return;` **超时就放弃本次更新**；退出时恢复背光 100% |
| **Button** | 顶部实时 ADC 电压 + 事件滚动记录 | 换电阻后的**标定工具**；四类事件（PRESS/CLICK/DOUBLE/LONG）的实测效果 |
| **Audio** | OK 播 1 kHz 方波，UP 录 3 秒回放 | **全仓库最值得抄的并发模板**（见下）；`CHUNK_SAMPLES 512`、`AUDIO_STOP_TIMEOUT_MS 2000` |
| **Battery** | 每秒刷新 SOC% 与 mV，<20% 变红 | `lv_timer_create(tick, 1000, NULL)` 周期刷新 + **`exit` 必删 timer**；`soc < 0 → "-- %"` 的优雅降级 |
| **Wi-Fi** | 扫描列表 RSSI/SSID/CH | STA 标准启动链；**退出逆序回滚**（scan_stop→stop→deinit→销毁 netif） |
| **BLE** | 广播名 `FoloPassport`，手机可扫 | NimBLE 需要自己的 host 任务；`nimble_port_init` → `sync_cb` → `ble_gap_adv_start` |
| **Low Power** | `LIGHT SLEEP \| 2 SEC` / `DEEP SLEEP \| 5 SEC` | 深睡断电顺序；`RTC_DATA_ATTR` + 魔数 `0x464F4C4F` 区分冷启动与唤醒 |

> 图片 + 中文 + 语音的“三件套”综合示例，见本书第 18 章「巴巴爸爸图鉴」——那是作者（你）
> 用 **Trae** 生成的实战项目（非官方，不在 `folotoy/ai-passport` 仓库），但代码仍是可抄范例。

Audio 页那个模板值得单独记住，它是 6 个文件共用的骨架：

```text
start()   建 worker，set_format(16000,16,1)、set_volume
key()     只 xTaskNotify 下命令（不阻塞）
worker    512 样本一块 write/read；每块前探测停止/新命令
stop()    通知停止 → take 停止信号量（2 秒超时）→ 返回
exit()    删 UI
```

## 5.7 显示一张图片

这块板子上**没有运行时解码**：图片必须在 PC 上预先转成屏幕原生格式
（RGB565 小端），编进 Flash，运行时 LVGL 拿一个指针直接读。
原因是内存——可用堆约 230 KB，而解码一张全屏图要 150 KB 缓冲，
且最大连续空闲块不足 8 KB。

完整流程（转换脚本、EMBED_FILES、描述符、排错表）见 **第 20 章**。
这里只留两个容易踩的点：

**一、`lv_image_dsc_t` 的 `stride` 是“一行字节数”，不是宽度。**

```c
const lv_image_dsc_t my_img = {
    .header = { .magic = LV_IMAGE_HEADER_MAGIC,
                .cf    = LV_COLOR_FORMAT_RGB565,
                .flags = 0,
                .w = 200, .h = 240, .stride = 400 },   // ★ 400 = 200 × 2
    .data_size = 200u * 240u * 2u,
    .data      = my_pixels,        // const，指向 Flash，不占 RAM
};
```

`stride` 填成 `w` 就会错行/花屏。

**二、LVGL 官方转换器导出的 `.bin` 带 12 字节文件头。**

| 偏移 | 长度 | 内容 | 典型值 |
| --- | --- | --- | --- |
| 0 | 1 | magic | `0x19` |
| 1 | 1 | cf（颜色格式） | `0x12`（RGB565） |
| 2 | 2 | flags | 0 |
| 4 | 2 | w | 200 |
| 6 | 2 | h | 240 |
| 8 | 2 | stride | 400 |
| 10 | 2 | reserved | 0 |
| 12 | … | RGB565 像素 | |

自己生成裸数据时**不要加这个头**（直接用像素即可）；
如果你拿到的是 LVGL 转换器导出的 `.bin`，**要先剥掉这 12 字节**。

**字节序：不要自己 swap。** BSP 的 LVGL port 在 flush 时统一做 `swap_bytes`
（`bsp_display_lvgl.c`），素材存标准小端 RGB565 即可。自己再 swap 一次会红蓝互换。

> 💡 官方代码里是 `lv_img_create()` / `lv_img_set_src()`（LVGL 9 的兼容别名），
> 新 API 正名是 `lv_image_create()` / `lv_image_set_src()`。
> 两种都能编译、行为一致；读老代码时认识 `lv_img_*` 就行。

## 5.8 中文为什么显示成空白或方框

结论先行：

```c
lv_label_set_text(label, "你好世界");   // 编译通过，烧进去可能是空白或方块
```

**UTF-8 编码正确、编译成功，不代表能显示。**

原理是字体本质上有三张只读表：

1. **位图数据**（每个字形的点阵）；
2. **字形描述表**（宽高、偏移、步进）；
3. **cmap 映射表**（Unicode 码点 → 字形编号）。

显示过程是：**UTF-8 解码出码点 → 查 cmap → 命中则画位图，未命中则画缺字占位符。**

由此得到关键认知：

- **UTF-8 和中文字库是两回事**。`CONFIG_LV_TXT_ENC_UTF8` 只告诉 LVGL
  “怎么把字节解析成码点”，**不会安装任何字形**。Montserrat 的 cmap 只覆盖拉丁字母，
  汉字码点全部 miss——这就是“英文正常、中文空白/方框”的根因；
- 基线固件默认只启用 Montserrat 14/20，**没有中文字体**；
- **一个字体只有一个字号**。要 16 px 和 20 px 中文，就得生成**两个**字体文件；
- **不要关掉 `CONFIG_LV_USE_FONT_PLACEHOLDER`**：缺字时画个可见符号让问题暴露，
  关掉会把缺字变空白，让所有故障折叠成同一个现象。

**怎么做**：从选字体、抽码点、`lv_font_conv` 生成、编进工程、
绑定 fallback 到程序化验证缺字，完整手把手在 **第 19 章**。
这章只负责让你知道“空白/方框”到底是哪一层的问题。

## 5.9 240×320 到底能放多少东西

| 内容 | 建议 |
| --- | --- |
| 正文字号 | 12–14 px（`lv_font_montserrat_14`） |
| **中文舒适下限** | **16 px**（bpp1） |
| 标题字号 | 20 px |
| 一屏列表项 | **不超过 5–6 行**（每行 40 px） |
| 一行中文 | 12 px 字体约 18 个字 |
| 导航深度 | 不超过 3 层 |

记住：**240×320 不是“缩小版手机屏”，是“比智能手表大一点”**。
把手机 App 界面搬上去一定失败。

介绍文字太长时，用单行循环滚动：

```c
lv_label_set_long_mode(s_desc, LV_LABEL_LONG_SCROLL_CIRCULAR);
```

不要为了塞文字把字号缩到不可读。

## 5.10 熄屏与删页的固定顺序

**删页面：先停定时器，再删对象。**

```c
void my_page_exit(void) {
    if (s_timer) { lv_timer_delete(s_timer); s_timer = NULL; }
    if (s_scr)   { lv_obj_delete(s_scr);     s_scr = NULL;   }
}
```

**熄屏：按固定顺序关外设。**

> 源码：`main/app_shell.c`（pax-zhang fork）

```c
static void sleep_now(void)
{
    if (s_asleep) return;
    s_asleep = true;
    bsp_display_backlight(0);        // 1. 先灭背光
    lv_refr_now(NULL);               // 2. 刷完最后一帧
    bsp_lvgl_flush_enable(false);    // 3. 禁止再刷屏
    bsp_display_sleep(true);         // 4. 面板休眠
    bsp_audio_standby();             // 5. 音频待机
    bsp_wifi_radio_suspend();        // 6. 挂射频
    bsp_button_sleep_gpio(true);     // 7. 按键转 GPIO 唤醒
    bsp_lvgl_tick_enable(false);     // 8. 停 tick
    bsp_pm_set_sleeping(true);       // 9. 通知电源管理
}
```

顺序不能乱：**先让软件停止访问硬件，再让硬件睡。**

## 5.11 游戏与高帧率场景：官方验收 SOP

做游戏类玩法（第 13/14 章）时，“在电脑上跑得动”和“在板上玩得舒服”是两件事。
官方为此专门写了一篇 SOP：
[`docs/development/engineering/game-demo-to-device-acceptance.zh_CN.md`](https://github.com/FoloToy/ai-passport/blob/main/docs/development/engineering/game-demo-to-device-acceptance.zh_CN.md)。核心是这条链路：

```text
可移植 C 内核 → H5 / Wasm 评审外壳 → 同种子回放比对 → 真机验收
```

**关键约束**：玩法状态机、时钟与 tick 规则、行走/碰撞/计分放在**可移植 C** 里，
让**同一批源文件**同时用于主机测试、Wasm 和固件；浏览器输入、显示、缩放与评审控件
留在 H5 外壳，**不再实现第二套计分或行走模型**。渲染器可移植就共用，
基于 LVGL 的页面也可以只共用玩法模型与布局数据。
ESP-IDF/LVGL、ADC 按键、电量、显示传输与任务所有权放在**设备适配层**。

**五步**：

| 步 | 做什么 | 通过条件 |
| ---: | --- | --- |
| 0 | 先写**场景表**：开始/结束、屏幕方向、三键映射、短按/长按、正常与失败路径、重玩/退出 | 不看源码的玩家也能说清每一步按哪个键 |
| 1 | 可移植 C + H5 外壳；原生 C 与 Wasm **同种子、同输入序列、同时间步进**回放比对 | 状态与共享渲染输出差异在容差内 |
| 2 | 两轮互补验收：**受控场景**（覆盖各分支）+ **无提示游玩**（从头玩一遍） | 场景表全 PASS；**只靠场景注入或单张截图都不算** |
| 3 | 集成进应用自己的 UI，跑仓库完整验证，记录提交号/固件哈希/素材哈希 | 能进预期起始画面，且能识别装的是哪一版 |
| 4 | 真机重复同一张场景表，测量**设备独有事实** | 实体按键与完整流程通过，真机测量达标 |

第 4 步的“设备独有事实”是这份 SOP 最有价值的部分——**网页性能计数器、串口截图和
C 自动化测试都不能证明实体屏幕的流畅度或长时间游玩的内存安全性**。要实测的是：

- 提交帧率，以及可获得时的屏幕完成帧节奏；
- 渲染与显示耗时；
- **空闲/最低堆内存与最大连续块**（第 11 章）；
- 按键响应、崩溃、看门狗、分配失败、撕裂或黑帧。

按游戏探针计划**预热并采样足够时长，只比较相同场景**，用第 0 步预先定下的目标判。

两条硬纪律：

- **改了共享 C 或素材 → 重新构建 Wasm 与固件 → 复测 Demo 场景 → 再复测真机**，
  不能仅凭网页结果关闭真机失败项；
- 交接记录留五类证据：**版本身份 / Demo / 构建 / 真机 / 结论**，
  每类分别标 `PASS`、`FAIL` 或 `NOT RUN`，缺证据就标 `NOT RUN`，
  必要关卡为 `FAIL` 或 `NOT RUN` 时**不得标为可发布**。

## 5.12 小结

- 版本是 **LVGL 9.5**，旧教程的 `lv_img_*` / `lv_scr_load` 要换成 `lv_image_*` / `lv_screen_load`；
- 点亮三步：`bsp_display_init` → `bsp_lvgl_init` → `bsp_display_backlight`；
- 渲染链路：改属性只是标脏，20 ms 刷一次，绘制缓冲只有 **240×40（19.2 KB）**；
- **`taskLVGL` 之外碰 `lv_*` 必须 `bsp_lvgl_lock()`**；`lv_timer` 回调不用锁但**不能阻塞**；
- 图片：构造 `lv_image_dsc_t`，`.bin` 素材要**剥掉 12 字节头**，**字节序不要自己 swap**；
- 中文：**UTF-8 ≠ 字形**。验证用方案 A，产品用方案 B（lv_font_conv 子集）+ fallback；
- 缺字要**按码点检查**，保留 placeholder，真机验证前一律报 Unverified；
- 240×320 只能放 5–6 行，中文 16 px 是舒适下限。

下一章讲按键——三个键怎么撑起一整套交互。

> 官方把“屏幕 + 背光”做成最小可跑示例的逐行源码，见第 25 章（Display 示例）。

> **延伸阅读 · 官方经验条目**（`docs/reference/`，非强制但带实测数字）：
> [显示刷新与深睡](https://github.com/FoloToy/ai-passport/blob/main/docs/reference/shinku-chen/display-refresh-and-deep-sleep.zh_CN.md) ·
> [横屏旋转与深睡按键唤醒](https://github.com/FoloToy/ai-passport/blob/main/docs/reference/shinku-chen/landscape-rotation-and-deep-sleep-key-wake.zh_CN.md) ·
> [串口截屏协议](https://github.com/FoloToy/ai-passport/blob/main/docs/reference/y2lin/serial-screenshot-protocol.zh_CN.md) ·
> [音量计 UI 平滑与杂色块](https://github.com/FoloToy/ai-passport/blob/main/docs/reference/y2lin/meter-ui-smoothing-and-layout.zh_CN.md)
