# 18. 端到端实战：巴巴爸爸角色图鉴（逐行拆解你用 Trae 生成的 `demo_barbapapa.c`）

前面 17 章讲的都是**别人的代码片断**。这一章带你把一个**完整、可跑、你自己用 Trae 生成**的页面
`main/demo_barbapapa.c`（359 行）从头读到尾——它是全书包得最全的一个示例：
**屏幕 + 图片 + 中文字体 + 音频 + 按键 + Flash 素材**一次用上，
正好把第 5、6、7、19、20、21 章的东西串成一次总练习。

> 本章不靠“据说”，直接对着 `D:/trae_projects/AIP/ai-passport/main/demo_barbapapa.c` 读。
> 引用的行号都来自这份源码；编译用本书 `snippets/` 同一套官方参数（含 `-Werror`）。
> ⚠️ **重要定位**：`demo_barbapapa.c` **不是官方仓库 `folotoy/ai-passport` 的内容**（官方 `DEMOS[]`
> 只有 7 项，没有它，也没有 `BOOT_DEMO_INDEX`）。它是作者（你）用 **Trae** 在自己的工作副本里
> 生成的实战项目，被放在「实战拆解」部分当范例。本章代码对这套硬件完全有效，只是它属于你自己的
> 项目，而非“官方内置项”。

## 18.1 这个页面到底做了什么

源码顶部的注释（`main/demo_barbapapa.c:5-27`）把行为说得很清楚：

| 操作 | 行为 |
| --- | --- |
| 打开页面 | 显示第 0 个角色（巴巴爸爸）的大图 + 中文名标题牌 + 底部 10 个名字的导航条 |
| UP / DOWN（短按） | 上 / 下**循环**切换角色；切换会**立刻打断**还没播完的语音 |
| OK（短按） | 用 ES8311 芯片播放当前角色名（PC 端预生成的 PCM） |
| OK（长按） | 返回菜单——**由 main.c 框架统一拦截**，不会到达本文件 |

设计决策（`:12-20`）：10 张图、10 段语音、2 个中文字体**全在 PC 上预生成后烧进 Flash**，
通过 CMake 的 `EMBED_FILES` 原样链入 Flash 的内存映射区，程序里读到的是指向 Flash 的指针——
**不占 RAM、不开机解码、即开即显**。之所以不在设备上联网取图、不做 GIF 解码：本机**没有 PSRAM**
（RAM 只有几百 KB），且 Wi-Fi demo 目前只扫描不联网。

## 18.2 三类资源怎么进固件

| 资源 | 形态 | 进固件方式 | RAM 代价 |
| --- | --- | --- | --- |
| 图片 | RGB565 **裸像素**（高 240，宽 173~240） | `EMBED_FILES` 链入 → `const uint8_t[]` | **0**（Flash 映射） |
| 音频 | 16 kHz / 16 bit / 单声道 PCM | `EMBED_FILES` 链入 → `const uint8_t[]` | **0**（流式播放） |
| 中文字库 | 子集 C 文件（20px 标题 + 14px 导航） | `lv_font_conv` 生成，编译进固件 | **0** |
| 文本 | `bbp_chars[10]` 字符串表（C 源码里） | 直接编进 `.text` | 极小 |

**结论：全部编译期内嵌为 `const`，不挂文件系统。** 理由（与第 9 章一致）：
官方默认分区表只有 nvs / phy_init / factory 三个分区，没有 SPIFFS/LittleFS；
`const` 数组进 `.rodata`，ESP32-C3 经 Flash 映射直接读取，不占 RAM；素材也没有运行中替换需求。

> ⚠️ `const` 不能去掉。带初始化器的 `const` 数组在 Flash；去掉 `const` 才会被拷进 RAM（第 11 章）。

以 10 个角色**实测**算 Flash 增量（数字取自工作副本 `main/assets/barbapapa/` 的真实素材文件）：
10 张图 **995 KiB**（单张 81–112 KiB，约 240×200 的 RGB565 小端）、10 段语音 **596 KiB**、
2 个字库 `bbp_font_20.c`+`bbp_font_14.c` **36 KiB**，素材共约 **1.6 MiB**。

> ⚠️ 别按「96 KB 合计」估预算——96 KB 只是**单张**图量级，10 张合计是约 1 MiB（实测 995 KiB）。

官方默认 factory 分区 `0x7F0000` ≈ 8.3 MB，加完素材后仍有大量余量。

## 18.3 素材管线（PC 侧，真实脚本）

本实战的素材不是手工转的，而是一套脚本一次性生成（`tools/barbapapa/`）：

```text
官网 GIF  ──► fetch_assets.py ──► bbp_img_00..09.bin   (裸 RGB565 像素，无文件头)
Windows TTS ─► make_tts.ps1 ──► wav/NN.wav ─┐
                                          └─► fetch_assets.py ──► bbp_voice_00..09.pcm
黑体 16 字 ──► gen_font.ps1 ────► bbp_font_20.c / bbp_font_14.c
                                 └─► (上面三者) ──► barbapapa_assets.{h,c}  (清单)
```

### 图片：PIL 直接生成裸 RGB565（没有 12 字节头）

注意：本项目**不走**“LVGL 转换器导出带 12 字节头的 `.bin` 再剥头”那条路（那是第 20 章的通用做法）。
它用 Python + Pillow 自己把像素写成裸 RGB565，描述符在 C 里现建。
`fetch_assets.py:72-96` 的关键：取 GIF 首帧 → 贴到 `UI_PAPER`(0xF4F4EA) 底 → 等比缩放到高 240 →
逐像素转 RGB565 小端。

```python
# fetch_assets.py:91-94  —— green 用 0xFC 不是 0xE0，否则丢低 3 位绿、白色偏成品红
rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
struct.pack_into("<H", buf, i, rgb565)   # C3 小端，与 LVGL u16 内存序一致
```

### 音频：WAV 剥头成裸 PCM

`make_tts.ps1` 用 Windows 自带中文语音（Microsoft Huihui）离线 TTS，
输出 **16 kHz / 16 bit / 单声道** WAV（`:34-39` 的 `SpeechAudioFormatInfo`）。
`fetch_assets.py:99-122` 再**逐 chunk 找** `fmt`/`data` 把头部剥掉——不要假定偏移恒定：

```python
if (channels, rate, bits) != (1, 16000, 16):
    sys.exit(f"{wav_path.name} 格式 ...,应为 16000/16/1；改 make_tts.ps1")
```

> 这个 16k/16bit/1 必须和页面里 `bsp_audio_set_format(16000, 16, 1)` 完全一致，否则变调/杂音。

### ⚠ 多音字：TTS 会把“的”读成“dí”

离线 TTS 有个和产品体验直接相关的问题：**多音字它不一定读对**。
本机 Microsoft Huihui 在合成“我们是大美的好朋友”时，
把“的”读成了 **dí**（像“的确”），而正确读法是中性的轻声 **de**。

代码、资源、设备都没问题——**是语音素材本身就是错的**。
这类问题只在设备上播放时才暴露，而且很容易被误判成“解码不对”。

解法是用 **SSML 的 `<phoneme>` 标签强制读音**：

```xml
<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="zh-CN">
  我们是大美<phoneme alphabet="zh" ph="de5">的</phoneme>好朋友
</speak>
```

`ph="de5"` 的含义：`de` 是拼音，**末尾数字是声调**，`5` = 轻声。
所以 `de5` = “的”的中性轻声。常用对照：

| 想要的字 | 错读 | 强制写法 |
|---|---|---|
| 的（轻声） | dí | `ph="de5"` |
| 了（轻声） | liǎo | `ph="le5"` |
| 重（重复） | zhòng | `ph="chong2"` |
| 行（可以） | xíng（行业 háng） | `ph="xing2"` |

注意 `alphabet="zh"` 不要省——不写的话 SAPI 会按通用 IPA 去解释 `de5`，结果不可预期。

Python 侧（替代 PowerShell 的 `make_tts.ps1`，便于和素材管线用同一种语言）：

```python
import comtypes.client as cc

SVSFParseSsml = 128        # SPF_PARSE_SSML：让引擎按 SSML 解析输入

voice = cc.CreateObject("SAPI.SpVoice")
for v in voice.GetVoices():                      # 挑一个中文语音
    if "Chinese" in str(v.GetDescription()):
        voice.Voice = v
        break

stream = cc.CreateObject("SAPI.SpFileStream")
stream.Open(str(wav_path), 4)                    # 4 = SSFMCreateForWrite
voice.AudioOutputStream = stream
voice.Speak(ssml_text, SVSFParseSsml)            # ← 关键是这个 flag
stream.Close()
voice.AudioOutputStream = None
```

> **判别 SSML 有没有生效**：SSML 必须配 `SVSFParseSsml` 这个 flag 提交。
> 如果 flag 传 0（当作纯文本），`<phoneme>` 会被逐字念出来，反而更糟。
> 合成后先检查产出的 WAV 大小——若只有几十字节（空音频），
> 说明 SSML 格式有问题被引擎拒绝了。

Shinku/PokeWalk 那条线的经验是：**音效素材一旦进了 `.rodata`，
改一个字的读音要重新走一遍“合成 → 剥头 → 生成 assets → 编译 → 烧录”，
成本远高于第一次就多听一遍。** 建议在合成脚本里保留原始 SSML 文本，
并把“逐条试听”列进发布前的验收清单。

### 字体：16 个汉字，两种字号，`--bpp 4`

`gen_font.ps1:15-28` 把 10 个名字去重得 **16 个码点**，用 Windows 自带的 `simhei.ttf`（单 face TTF，
**不能用 `.ttc` 如 msyh.ttc**），循环生成 20px 与 14px 两个字库：

```powershell
$range = "0x4E3D,0x4F2F,...,0x8D1D"   # 丽伯利塔妈尔巴巴拉波洛爸特祖莱贝（16 字）
foreach ($size in 20, 14) {
    npx --yes lv_font_conv@1.5.3 `
        --font C:\Windows\Fonts\simhei.ttf --range $range `
        --size $size --bpp 4 --format lvgl --no-compress `
        --lv-font-name "bbp_font_$size" -o "bbp_font_$size.c"
}
```

**两个 Windows 专属坑**（脚本注释原文）：
1. 用 `--range` 传十六进制码点，**不要 `--symbols "中文"`**——经 npx/node 中文参数会被破坏；
2. `lv_font_conv` 打不开 `.ttc` 字体集，只能用单 face 的 `.ttf`。

### 清单：把素材绑成 C 表

`fetch_assets.py:176-234` 生成 `barbapapa_assets.h`（结构）和 `.c`（描述符数组）。
`EMBED_FILES` 只按**文件基名**生成符号（`_binary_<基名>_start`），所以描述符的 `.data` 用
`asm("_binary_bbp_img_00_start")` 取到像素（`:206-207`）。图片描述符在 C 里现建：

```c
// barbapapa_assets.c（自动生成）—— .data 指向 Flash 像素，不占 RAM
const lv_image_dsc_t bbp_imgs[BBP_CHAR_COUNT] = {
    { .header = { .magic = LV_IMAGE_HEADER_MAGIC, .cf = LV_COLOR_FORMAT_RGB565,
                  .flags = 0, .w = 200, .h = 240, .stride = 400 },
      .data_size = 200u * 240u * 2u, .data = bbp_img_00 },
    /* ... */
};
```

> ⚠️ **`voice_bytes` 必须写字面量**（`(uint32_t)N u`）。两个 `extern` 符号相减不是整型常量表达式，
> 在文件作用域初始化结构体时 GCC 14 / RISC-V 直接报错（`:225-227` 注释原文）。

## 18.4 页面契约：5 个钩子

**所有** demo 页（官方 7 项 + 你的巴巴爸爸）都遵守同一套接口（`main/demo.h:7-14`）：

```c
typedef struct {
    const char *name;
    void      (*enter)(void);                 // 持 LVGL 锁：建并载入页面
    void      (*exit)(void);                  // 持 LVGL 锁：删页面（stop 成功后）
    void      (*key)(bsp_btn_t, bsp_btn_ev_t);// 不持锁：自行缩短锁范围
    esp_err_t (*start)(void);                 // 不持锁：建慢服务（可选）
    esp_err_t (*stop)(void);                  // 不持锁：停 producer（可选）
} demo_entry_t;
```

`demo_barbapapa.c` 顶部注释（`main/demo_barbapapa.c:22-27`）把三条铁律写得很直白：

1. `enter()` 在持有 LVGL 锁时被调用，只做创建 UI 这类快操作；
2. `start()/stop()` 不持锁，可以做慢操作；`stop()` 必须在超时内停干净，否则返回错误、
   框架中止退出（防止带着后台任务切走页面）；
3. `key()` 不持锁，要碰 LVGL 对象必须自己先 `bsp_lvgl_lock()`。

**铁律**：按键回调、LVGL 任务里**禁止任何会阻塞的调用**（比如写音频）。

## 18.5 逐段读代码

### 18.5.1 文件头、字体声明与全局状态

```c
// main/demo_barbapapa.c:29-44
#include "demo.h"          // 钩子原型
#include "bsp_audio.h"     // init / set_format / set_volume / write
#include "bsp_display.h"   // bsp_lvgl_lock / bsp_lvgl_unlock
#include "bsp_pins.h"      // BSP_LCD_W 等尺寸常量
#include "ui_pixel.h"      // 统一像素风配色 UI_SKY/UI_PAPER/UI_INK
#include "barbapapa_assets.h"  // bbp_chars[10] 素材表

LV_FONT_DECLARE(bbp_font_20);   // 20px 中文字体：标题牌
LV_FONT_DECLARE(bbp_font_14);   // 14px 中文字体：导航条
```

`LV_FONT_DECLARE` 告诉编译器“这个 `lv_font_t` 定义在别的 .c 里”——即 `lv_font_conv` 生成的字体文件。

布局与音频常量（`:46-54`）：

```c
#define IMG_TOP_Y        44      // 图片顶边：给标题牌(y=8..41)让位
#define NAV_Y           286      // 导航条顶边：320-34，贴屏幕底
#define NAV_H            34
#define CHUNK_BYTES    2048      // 每次送 2048 字节 = 64ms(16k/16bit/1)
#define STOP_TIMEOUT_MS 2000     // stop() 等语音任务确认的最长时限
```

**关键认知：`CHUNK_BYTES` 是字节不是样本。** 16k/16bit/单声道 = 32000 字节/秒，
2048 字节 = 64 ms——块之间能检查“要不要打断”。全局状态用 `volatile` 标记
（`:72-83`），因为按键回调和语音任务这两个执行流会并发读写，禁止编译器缓存进寄存器：

```c
static TaskHandle_t      s_task;        // 语音任务句柄（NULL=不存在）
static SemaphoreHandle_t s_stopped;     // 二值信号量：任务退出前 give
static volatile bool     s_cancel;      // "请立刻停"标志
static volatile bool     s_busy;        // "正在播"标志，OK 用它防重复触发
static volatile uint8_t  s_play_idx;    // 本次要播的角色下标
static int  s_idx;                      // 当前显示角色(0..9)
static bool s_audio_ok;                 // 音频芯片是否初始化成功
```

### 18.5.2 page_refresh —— 持有锁刷新三处

`page_refresh()`（`:89-117`）只被“已持锁”的调用方使用（enter 内、key 内）。
它按 `s_idx` 换标题文字、换图片（只换一个指向 Flash 的描述符指针，**不拷贝不解码**）、
并把导航条当前项高亮成“墨底纸字”、其余“纸底墨字”，再 `lv_obj_scroll_to_view` 让当前项滚入视野：

```c
lv_label_set_text(s_title, c->name_zh);
lv_img_set_src(s_img, c->img);                 // 旧 API 名；新名 lv_image_set_src 等价
lv_obj_set_pos(s_img, (BSP_LCD_W - c->img->header.w) / 2, IMG_TOP_Y);  // 按实宽居中
```

> 注意源码用 `lv_img_set_src`（LVGL 9 的兼容别名）。第 5 章讲过：
> `lv_img_*` 与新的 `lv_image_*` 都能编译、行为一致，读老代码认识前者即可。

### 18.5.3 play_voice —— 分块写给 ES8311

`play_voice()`（`:126-154`）**只在语音任务里运行**。开头一段注释把“为什么必须独立任务”讲透了：
`bsp_audio_write()` 是阻塞调用（I2S 缓冲满会等），若在按键回调或 LVGL 任务里调用，
按键和屏幕都会卡到播完。

```c
if (bsp_audio_set_format(16000, 16, 1) != ESP_OK) { ESP_LOGE(TAG,"音频格式设置失败"); return; }
bsp_audio_set_volume(75);                      // 0~100，75 是适中经验值
uint32_t off = 0;
while (off < c->voice_bytes && !s_cancel) {    // 每块检查 s_cancel → 64ms 内可打断
    uint32_t n = c->voice_bytes - off;
    if (n > CHUNK_BYTES) n = CHUNK_BYTES;
    if (bsp_audio_write(c->voice + off, n) != ESP_OK) { ESP_LOGE(TAG,"失败@%u",off); break; }
    off += n;
}
```

### 18.5.4 voice_task —— 任务通知 + 停止握手（重点！）

这是全章最该抄的并发模板，和第 12 章、附录 D.14 是同一套：

```c
// main/demo_barbapapa.c:163-185
static void voice_task(void *arg) {
    (void)arg;
    for (;;) {
        uint32_t cmd = 0;
        if (xTaskNotifyWait(0, UINT32_MAX, &cmd, portMAX_DELAY) != pdTRUE) continue;
        if (cmd == BBP_CMD_STOP) break;          // 收到停止 → 跳出循环去收尾
        if (cmd == BBP_CMD_PLAY) {
            s_cancel = false; s_busy = true;
            play_voice(s_play_idx);              // 阻塞播完（或被打断）
            s_busy = false;
        }
    }
    xSemaphoreGive(s_stopped);                   // ★ 通知 stop()："我停好了"
    for (;;) vTaskSuspend(NULL);                 // ★ 挂起，等 stop() 来 vTaskDelete
}
```

**两个必须要记住的点：**

1. **worker 不自己删自己。** 收尾是 `xSemaphoreGive(s_stopped)` 然后 `for(;;) vTaskSuspend(NULL)`。
   源码注释（`:181-182`）写明原因：ESP-IDF 里任务自删后栈回收有时机问题，
   **由 `stop()` 统一 `vTaskDelete` 更可控**（与 `demo_audio.c` 写法一致）。
   所以**不要**写 `vTaskDelete(NULL)` 自删——那会留下悬空句柄且删除时机不可控。
2. **通信零拷贝。** 按键 → 语音任务用 `xTaskNotify` 传一个命令字；语音任务 → `stop()` 调用方
   用二值信号量表示“已停好”。都是事件驱动，不是轮询。

### 18.5.5 enter —— 只建 UI（框架已持锁）

`demo_barbapapa_enter()`（`:190-252`）创建整屏容器、顶部标题牌、图片控件、底部导航条。
导航条用 LVGL 9 的 flex 横向布局排 10 个名字（宽度不同，LVGL 自动排，不用手算 x）：

```c
s_scr = lv_obj_create(NULL);                    // 无父 = 新屏幕
lv_obj_set_style_bg_color(s_scr, lv_color_hex(UI_SKY), 0);
lv_obj_t *plate = ui_pixel_panel_create(s_scr, 5, 8, 230, 33, UI_PAPER);  // 纸底墨边面板
s_title = lv_label_create(plate);
lv_obj_set_style_text_font(s_title, &bbp_font_20, 0);   // ★ 中文字体绑到控件

s_nav = lv_obj_create(s_scr);
lv_obj_set_scroll_dir(s_nav, LV_DIR_HOR);       // 只许横向滚（10 个名字排不开自动横滑）
lv_obj_set_flex_flow(s_nav, LV_FLEX_FLOW_ROW);  // 弹性横排，子对象自动布局
for (int i = 0; i < BBP_CHAR_COUNT; i++) {     // 10 个名字 label
    lv_obj_t *lb = lv_label_create(s_nav);
    lv_obj_set_style_text_font(lb, &bbp_font_14, 0);
    lv_label_set_text(lb, bbp_chars[i].name_zh);
    s_nav_label[i] = lb;
}
page_refresh(); lv_screen_load(s_scr);          // 填好内容并切到前台
```

### 18.5.6 start —— 软依赖音频 + 建任务（不持锁）

`demo_barbapapa_start()`（`:257-280`）体现“可选外设降级”思想：音频初始化失败只记 `s_audio_ok=false`，
图片浏览照常。

```c
s_audio_ok = (bsp_audio_init() == ESP_OK);      // 幂等：Audio 页可能已 init 过，重复安全
if (!s_audio_ok) ESP_LOGW(TAG, "音频初始化失败：仅看图，OK 不发声");
if (s_task) return ESP_OK;                       // 已建（重复 start）直接成功
s_stopped = xSemaphoreCreateBinary();
if (xTaskCreate(voice_task, "bbp_voice", 4096, NULL, 4, &s_task) != pdPASS) {
    vSemaphoreDelete(s_stopped); s_stopped = NULL; return ESP_ERR_NO_MEM;
}
```

优先级 **4**：与 LVGL port 任务同级、低于按键派发任务（5）。音频慢一点无所谓，UI 必须流畅（注释 `:272`）。
> 任务优先级实测见第 12.1 节：LVGL=4（esp_lvgl_port 默认）、`demo_input`=5、本 worker=4。

### 18.5.7 stop —— 发 STOP + 等确认（不持锁）

`demo_barbapapa_stop()`（`:286-306`）是契约 2 的落地：

```c
TaskHandle_t task = s_task;
if (!task) return ESP_OK;                        // 任务没起 = 成功
s_cancel = true;                                 // 让正在播的循环尽快跳出
xTaskNotify(task, BBP_CMD_STOP, eSetValueWithOverwrite);
if (!s_stopped ||
    xSemaphoreTake(s_stopped, pdMS_TO_TICKS(STOP_TIMEOUT_MS)) != pdTRUE) {
    ESP_LOGE(TAG, "语音任务停止超时");
    return ESP_ERR_TIMEOUT;                      // ★ 超时：中止退出，页面保留，允许重试
}
vTaskDelete(task);                               // 任务此刻挂起在 vTaskSuspend，安全删除
s_task = NULL; vSemaphoreDelete(s_stopped); s_stopped = NULL;
return ESP_OK;
```

**超时返回 `ESP_ERR_TIMEOUT` 是刻意的**：不让“带着后台任务切走页面”这种危险发生。

### 18.5.8 exit —— 删 UI（框架已持锁）

`demo_barbapapa_exit()`（`:311-322`）：LVGL 对象是树形结构，删根对象会连带删所有子对象，
不用逐个删；指针置 NULL 是防御重复调用。

```c
if (s_scr) { lv_obj_delete(s_scr); s_scr = NULL;
             s_title = s_img = s_nav = NULL;
             for (int i=0;i<BBP_CHAR_COUNT;i++) s_nav_label[i] = NULL; }
```

### 18.5.9 key —— 只下单，不干活

`demo_barbapapa_key()`（`:328-359`）典型“按键回调只改状态 + 发通知”：

```c
if (ev != BSP_BTN_CLICK) return;                // 只响应短按；长按返回菜单被框架拦了
if (btn == BSP_BTN_UP || btn == BSP_BTN_DOWN) {
    if (!bsp_lvgl_lock(250)) return;             // 要碰 LVGL 对象，先拿锁（250ms 拿不到就放弃）
    s_idx = (btn == BSP_BTN_UP)
          ? (s_idx + BBP_CHAR_COUNT - 1) % BBP_CHAR_COUNT   // 环形下标：0 再按 UP 绕回 9
          : (s_idx + 1) % BBP_CHAR_COUNT;
    s_cancel = true;                             // 正在播的名字立刻打断（64ms 内退出）
    page_refresh(); bsp_lvgl_unlock(); return;
}
if (btn == BSP_BTN_OK) {
    // 三个条件全满足才"下单"：任务存在 && 音频 OK && 没在播
    if (s_task && s_audio_ok && !s_busy) {
        s_play_idx = (uint8_t)s_idx;
        xTaskNotify(s_task, BBP_CMD_PLAY, eSetValueWithOverwrite);   // 真正的播放在任务里
    }
}
```

`!s_busy` 防止播报期间 OK 堆积通知；真正的播放在 `voice_task` 里做，这里立刻返回。

## 18.6 工程接入：四处改动

**1. `main/CMakeLists.txt`**（`:1-49`）——源文件、素材、字体：

```cmake
idf_component_register(
    SRCS "main.c" ... "demo_barbapapa.c"            # 页面源码
    INCLUDE_DIRS "." "assets/barbapapa"
    REQUIRES bsp lvgl ...
)
EMBED_FILES                                          # 图片/语音裸数据进 Flash
    "assets/barbapapa/bbp_img_00.bin" ... bbp_img_09.bin
    "assets/barbapapa/bbp_voice_00.pcm" ... bbp_voice_09.pcm
target_sources(${COMPONENT_LIB} PRIVATE
    "assets/barbapapa/barbapapa_assets.c"           # 描述符数组
    "assets/barbapapa/bbp_font_20.c"
    "assets/barbapapa/bbp_font_14.c")               # 两个字体
```

**2. `main/demo.h`**（`:42-44`）——加五个声明（enter/exit/key/start/stop）；
**3. `main/main.c`**——`DEMOS[]` 末尾追加一项，并给 `s_ok[]` 同一索引赋值。

> ⚠️ `DEMOS[]` 顺序、`s_ok[]` 索引、菜单位置三者必须一一对应（第 16 章 PokeWalk 的 bug 成因）。
> **末尾追加最安全。** 本页是音频软依赖，对应 `s_ok[N] = true`（错误进页后上屏，由 `s_audio_ok` 降级）。

## 18.7 构建与验证

```bash
# PC 侧素材（只需跑一次，不需设备）
python tools/barbapapa/fetch_assets.py --offline   # 用本地 gif/ wav/ 缓存生成图片+语音+清单
powershell -ExecutionPolicy Bypass -File tools/barbapapa/gen_font.ps1   # 生成两个字体
# （语音改 make_tts.ps1 先生成 wav/，再跑上面的 fetch_assets.py）

# 固件
idf.py build && idf.py flash monitor
```

真机验收矩阵（`stop()` 通过 ≠ 硬件通过）：

| 项 | 通过标准 |
| --- | --- |
| 图片颜色 | 与源稿一致（不发蓝/发红），无错行、无花屏 |
| 中文 | 标题与导航条字形正确、**无方框**；导航条 10 名排得下/可横滑 |
| 音频 | 每段逐一播放，音调正常（未变快/变沉），时长与源数据相符 |
| 按键 | 上下循环切换；播放中按 OK/上下立刻打断；OK 长按返回菜单 |
| 退出 | 返回后无残留声音、无崩溃、堆内存不持续下降 |
| 页面间 | 进入再退出后，其他音频页仍正常（格式切换串行无 bug） |

## 18.8 这个项目的 12 个常见问题

1. **图片红蓝互换**：素材用了 SWAPPED 格式或自己又 swap 了一次；
   本管线写的是标准 `0x12` 小端，字节交换只允许 port 做一次（第 20 章）；
2. **图片花屏/错行**：`stride` 不等于 `w*2`，或 GIF 透明底没贴 `UI_PAPER` 引入 Alpha；
3. **中文字全是方框**：字体变量名拼错（`bbp_font_20`/`bbp_font_14`，由 `--lv-font-name` 决定），
   或没在 style 里 `set_text_font`；Montserrat 不含中文；
4. **链接 undefined reference**：忘了把 `bbp_font_20.c`/`bbp_font_14.c` 加进 `target_sources`；
5. **字体生成失败/乱码**：在 Windows 上用 `--symbols "中文"` 会被 npx 破坏，必须 `--range` 码点；
   且不能用 `.ttc`（`simhei.ttf` 单 face 才行）；
6. **音频像快进**：别的页把 codec 设成了 8 kHz 而本页没重新 `set_format`——
   跨页格式切换必须串行（本页 `start`/`play_voice` 每次都 `set_format(16000,16,1)`）；
7. **`stop()` 超时**：语音任务卡在 `bsp_audio_write`。**不要强删任务**，
   按约定返回 `ESP_ERR_TIMEOUT` 让页面保留，查 I2S 日志后重试；
8. **`voice_bytes` 编译报错**：在文件作用域用两个 `extern` 符号相减初始化结构体，
   GCC 14/RISC-V 拒收，必须写字面量 `(uint32_t)N u`；
9. **`const` 数组担心占 RAM**：不会，它在 `.rodata`；去掉 `const` 才会被拷进 RAM；
10. **导航条名字排不下**：用 `LV_FLEX_FLOW_ROW` + `lv_obj_set_scroll_dir(LV_DIR_HOR)` 横滑，
    别手算 x；
11. **若把它接回官方 `DEMOS[]` 作为第 8 项**：官方测试外壳是七卡片网格，加第 8 项需调 `menu_build()` 的坐标让卡片不重叠（注意 `DEMOS[]` 下标、`s_ok[]` 索引、菜单位置三者一一对应）；
12. **以后想 OTA 换素材**：那时再改分区表加 LittleFS、用 `lv_fs` 从文件加载；
    当前内嵌方案刻意保持构建与交付简单（第 9 章）。

## 18.9 如果做成“联网版”

内嵌方案的缺点是要换素材就得重烧。若需联网更新：改分区表加 LittleFS/SPIFFS（第 9 章）；
用 `lv_fs` + `lv_binfont_create()` 从文件加载字库；图片走 HTTP 分块下载，**不要一次 malloc 整个文件**；
无网时用内嵌素材兜底——**降级永远要有**（第 10 章）。

## 18.10 交付时怎么汇报

按四段分开说，**不要把“编译通过”说成“硬件通过”**：

```text
Build       : idf.py build 通过 / 镜像 xxxx KB
Host tests  : （本页无主机测试；snippets/ 有可编译片段）
Device tests: 真机验收矩阵 6 项中 N 项通过
Unverified  : 中文显示 / 电池续航 / ...（未上板确认的部分）
```

最后一项尤其重要：**诚实标注未验证的部分**，比事后被发现“其实没测”好得多。

## 18.11 小结

- 素材全部内嵌为 `const`（Flash，0 RAM）：图片裸 RGB565（无头，C 里建描述符）、
  语音裸 PCM、`lv_font_conv` 子集字库；
- 字体 16 个汉字 × 20px/14px 两种，`--bpp 4`；Windows 上必须用 `--range` 码点、不能 `.ttc`；
- 页面契约 5 钩子：enter/exit 持锁只动 UI，start/stop 不持锁做慢服务，key 不持锁只下单；
- 音频并发三要素：**独立任务**（`bsp_audio_write` 阻塞）、**分块 2048 字节(64ms)** 之间查 `s_cancel`、
  **停止握手**（`xSemaphoreGive` + `vTaskSuspend`，由 `stop()` 统一 `vTaskDelete`，**不自删**）；
- `DEMOS[]` 末尾追加，避免索引错位；`stop()` 超时返回 `ESP_ERR_TIMEOUT` 让页面保留；
- 交付按 Build / Host / Device / Unverified 四段汇报。
