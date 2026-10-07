# 11. 没有 PSRAM 怎么活：内存纪律

> **可抄代码**：[D.13 内存诊断](D-module-cookbook.md#d13-内存诊断)。


这是全书最重要的一章。前面所有章节里那些"奇怪的写法"，
在这一章会得到统一解释。

## 11.1 先记住三个数字

| 指标 | 实测值 |
| --- | --- |
| 芯片 SRAM | 约 400 KB |
| **可用堆（跑起 Wi-Fi + LVGL 后）** | **约 230 KB** |
| **最大连续空闲块** | **不到 8 KB** |

第三个数字是本章的主角。

有项目在 README 里记录了它的实测：

> "一次只解一块（单块解压 3 KB、缓冲 4 KB），因为开机后**最大连续空闲块不到 8 KB**。"

再看一个对照：**整屏 240×320 RGB565 = 153,600 字节 = 150 KB**。

也就是说，你**根本不能申请一整屏的帧缓冲**。
这不是"优化"，是"不做就做不出来"。

## 11.2 五条纪律

### 纪律 1：大数组用静态，不要用 malloc

**反例**（会失败）：

```c
void init_screen(void) {
    uint16_t *framebuf = malloc(240 * 320 * 2);   // 150 KB，几乎必定失败
}
```

**正例**（DOOM 项目）：

```c
// 帧缓冲（38 KB）和行缓冲（8 KB）从 malloc 改为 .bss 静态数组
static uint8_t  s_backbuffer[FB_W * FB_H];          // 240 × 160，8bpp
static uint16_t s_linebuf[FB_W * STRIP_H * VSCALE]; // 7.5 KB 中转行
```

为什么静态的就能行？因为 **`.bss` 在编译期就定了地址**，
链接器会保证它放得下；而 `malloc` 要在运行时找一整块连续的空闲内存。

**这个改动救了 DOOM 项目**（它的 `docs/issues.md` 里明确记录）：

> "帧缓冲分配失败 → 解决：帧缓冲（38 KB）和行缓冲（8 KB）从 `malloc` 改为
> `.bss` 静态数组……DOOM 任务栈从 32 KB 缩减到 16 KB（大数组已移出）。"

### 纪律 2：不要反复创建销毁大栈任务

**问题**（音效钥匙扣项目的真实 bug）：

> "从堆上申请 16 KB——堆不足/碎片化曾导致**'只停不播'**
> （`xTaskCreate` 16 KB 栈失败）。"

每次按键播一个音效就 `xTaskCreate` 一个 16 KB 栈任务、播完删掉。
反复几次之后，堆上全是碎片——**总空闲内存还有，但凑不出连续的 16 KB**。
现象很诡异：能停止播放，但再也播不出声音。

**解法：常驻任务 + 静态栈。**

```c
#define PLAYER_STACK_BYTES 16384
static StackType_t  s_player_stack[PLAYER_STACK_BYTES / sizeof(StackType_t)];
static StaticTask_t s_player_tcb;
static SemaphoreHandle_t s_job_sem;   // 有新 job 时 give
static play_job_t *s_job;             // 当前 job，自带 stop 标志

// 创建一次，永不删除
xTaskCreateStatic(player_task, "player", PLAYER_STACK_BYTES / sizeof(StackType_t),
                  NULL, 5, s_player_stack, &s_player_tcb);
```

然后任务里阻塞等信号量：

```c
for (;;) {
    xSemaphoreTake(s_job_sem, portMAX_DELAY);
    // 播放 s_job，每帧检查 s_job->stop
}
```

### 纪律 3：分块处理代替整块处理

**帧缓冲放不下 → 分条刷屏。** DOOM 的做法：

```c
// Convert and blit in strips of STRIP_H game rows
for (int y = 0; y < FB_H; y += STRIP_H) {
    int sh = (y + STRIP_H > FB_H) ? FB_H - y : STRIP_H;
    // ...把 sh 行游戏画面转成 RGB565 填进 s_linebuf...
    bsp_display_draw_bitmap(DISP_X_OFF, y * VSCALE, FB_W, sh * VSCALE, s_linebuf);
}
```

中转缓冲只有 `240 × 16 × 2 = 7.5 KB`，一条一条推给屏幕。
**代价是多次 SPI 传输，收益是活下来了。**

同样的思路出现在别处：

> "无 PSRAM 也能铺满全屏美术——背景是内存映射分区里的 LVGL 索引图，
> 直接从 flash 绘制、**按行解码（约 960 字节）**，而不是 150 KB 的帧缓冲。"

**960 字节 vs 150 KB**——这就是 156 倍的差距。

### 纪律 4：大素材留在 Flash，用 mmap

不要"读进内存再用"，要"直接映射"：

```c
esp_partition_mmap(part, 0, part->size, SPI_FLASH_MMAP_DATA, &addr, &handle);
const uint8_t *data = addr;   // 当指针用，不占 RAM
```

DOOM 用 mmap 加载 4 MB 的 WAD；小智项目用 mmap 读素材分区。

**但 mmap 不是免费的**：ESP32-C3 只有 **128 个 flash-MMU 页**，
前面提到过一个项目用掉了 **83 个**。用之前先想清楚用不用得起。

### 纪律 5：解压也要按块来

> "自写 inflate 替代 ROM 解压器——整块解压到一个缓冲区，
> 不需要 32 KB 滑动字典，在没有 PSRAM 的 ESP32-C3 上把**工作缓冲压到 4 KB**。"

标准 zlib 解压需要 32 KB 的滑动窗口字典——在这里是奢侈品。
社区的做法是**自己写个解压器，按块解，不要历史窗口**。

### 纪律 6：只读数据一律 const，它不占 RAM

```c
const uint8_t my_image[] = { 0x12, 0x34, ... };   // ✅ 进 .rodata，Flash，0 RAM
        uint8_t my_image[] = { 0x12, 0x34, ... }; // ❌ 启动时被拷进 RAM
```

在 ESP32-C3 上，**带初始化器的 `const` 数组驻留 Flash（`.rodata`）**，
通过 cache 直接读取，不占一字节 RAM。
这就是为什么社区项目敢把 1.5 MB 的图片和 PCM 编进固件
（第 18 章里有完整的容量账）。

**去掉 `const` 是灾难性的**——同样的素材会全部被搬进 RAM。

从 Flash 地址直接喂外设也是合法的：
把 `.rodata` 里的 PCM 直接传给 `bsp_audio_write()` 没问题，
因为 I2S 驱动会把数据拷进它自己的 DMA 缓冲，
**对"数据源在 Flash 还是 RAM"没有要求**。

## 11.3 一个反直觉的判断

> "新图片、字体、网络栈、音频缓存、LVGL buffer 或任务栈都要评估内部 RAM；
> **总空闲堆足够不代表存在足够大的连续内存块**。"

这句话值得抄在显示器上。

`esp_get_free_heap_size()` 返回 100 KB，
不代表你能 `malloc(50 * 1024)`。**这两个数字之间没有必然关系。**

正确的检查方法是看**最大连续块**：

```c
ESP_LOGI(TAG, "free=%u min_free=%u largest=%u",
         esp_get_free_heap_size(),
         esp_get_minimum_free_heap_size(),
         heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
```

三个数字都有用：

| 函数 | 告诉你什么 |
| --- | --- |
| `esp_get_free_heap_size()` | 现在总共还剩多少 |
| `esp_get_minimum_free_heap_size()` | **历史最低点**（判断有没有濒临崩溃过） |
| `heap_caps_get_largest_free_block()` | **最大能申请多少** |

把它烧进板子，串口会看到类似：

```text
I (1240) mem: free=228410 min_free=201120 largest=7264
```

三个数一起看才有意义：`free` 接近 **230 KB** 是"总量"，但 `largest` 只有 **7264 B**——
这意味着任何 `malloc(8000)` 都会失败，尽管总量还剩两百多 KB。这也正是 `largest < 8 KB`
那条**贯穿全书的约束的真机来源**：下次怀疑"内存够为啥分配失败"，先打这三个数自己验证一遍。

**`esp_get_minimum_free_heap_size()` 是最有价值的**——
它记录了开机以来最危险的时刻。如果它长期低于 20 KB，你离崩溃很近了。

## 11.4 LVGL 的内存池是独立的一块

LVGL 有自己的内存池，**不和系统堆共享**：

```text
# LVGL 内置 malloc 池大小(KB)。它是独立静态区、不与系统堆共享，
# 配大了会白白占用 RAM。
# 24KB 够 header + 列表 + 通知/锁屏浮层；
# 32KB 会从系统堆再拿走 8KB，天气 DNS 容易碎掉。
CONFIG_LV_MEM_SIZE_KILOBYTES=24
```

这段注释（来自 pax-zhang 的 `sdkconfig.defaults`）是一个**实测调参的记录**：
从 32 调到 24，因为 32 会让天气的 DNS 解析失败。

**调 LVGL 内存池时要同时考虑它对系统堆的挤压。**
LVGL 对象树占多少，取决于你同时存在多少个对象和多少样式。

### 另外两块内存也来自内部 RAM

**绘制缓冲**（第 5.3 节讲过）：
`240 × 40 × 2 = 19,200` 字节，`BSP_LVGL_DRAW_BUFFER_LINES=40`，单缓冲。
开双缓冲要**再花 19.2 KB 连续内部 RAM**——必须和音频、Wi-Fi 的预算一起评估，
不能随手打开。

**警惕 ARGB 图层**：阴影、模糊、圆角全屏裁剪、某些 transform
会让 LVGL 临时开一个带 alpha 的图层，**24 KB 的池很容易爆**。
官方的像素风 UI 刻意不用这类效果（圆角是 BSP 在 flush 时逐行遮罩做的），
二次开发也应优先纯色 / 扁平设计。

## 11.5 省内存的 sdkconfig 清单

```text
# 关掉用不到的协议栈
CONFIG_LWIP_IPV6=n
CONFIG_BT_ENABLED=n                    # 不用蓝牙就关（省几十 KB）

# Wi-Fi 缓冲调小
CONFIG_ESP_WIFI_STATIC_RX_BUFFER_NUM=3
CONFIG_ESP_WIFI_DYNAMIC_RX_BUFFER_NUM=6
CONFIG_ESP_WIFI_RX_BA_WIN=3
CONFIG_ESP_WIFI_ENABLE_WPA3_SAE=n

# TLS 用完即释放
CONFIG_MBEDTLS_DYNAMIC_FREE_CONFIG_DATA=y

# 任务栈
CONFIG_FREERTOS_IDLE_TASK_STACKSIZE=768
CONFIG_ESP_MAIN_TASK_STACK_SIZE=8192

# 编译优化：选体积优先
CONFIG_COMPILER_OPTIMIZATION_SIZE=y

# 日志只留 Error（发布版）
CONFIG_LOG_DEFAULT_LEVEL_ERROR=y
```

DOOM 项目的 `sdkconfig.defaults` 思路总结得很好：
**关 BT、关 WiFi 运行时、日志只留 ERROR、编译选 -Os。**

## 11.6 内存预算表（做设计前先填）

| 项目 | 估算 |
| --- | --- |
| 系统 + FreeRTOS + 驱动 | ~100 KB |
| Wi-Fi（如启用） | 数十 KB |
| BLE（如启用） | ~73 KB |
| LVGL 内存池 | 24 KB（可配） |
| 你的静态数组（.bss） | ？ |
| 任务栈总和 | ？ |
| **剩余可用** | **目标 ≥ 50 KB** |

**如果算出来剩余 < 30 KB，砍功能。** 不要指望"跑起来再说"——
内存不足的表现是随机重启，而随机重启在真机上极难定位。

## 11.7 检查清单

写完代码后过一遍：

- [ ] 有没有 `malloc` 超过 4 KB 的地方？→ 改静态数组
- [ ] 有没有在栈上开数组超过 1 KB？→ 改 `static`
- [ ] 有没有反复 `xTaskCreate` 大栈任务？→ 改常驻 + 静态栈
- [ ] 有没有一次读整个文件进内存？→ 改流式 / mmap
- [ ] 有没有整屏帧缓冲？→ 改分条
- [ ] `esp_get_minimum_free_heap_size()` 有没有低于 30 KB？
- [ ] LVGL 池是不是配得过大？
- [ ] 用不到的协议栈（IPv6 / BT）关了吗？

## 11.8 小结

- 三个数字：400 KB SRAM / 230 KB 可用堆 / **最大连续块 < 8 KB**；
- 五条纪律：静态数组、静态栈、分块处理、mmap、按块解压；
- **总空闲 ≠ 最大连续块**，用 `heap_caps_get_largest_free_block()` 判断；
- LVGL 池独立配置，调大它会挤系统堆；
- 剩余可用堆 < 30 KB 就该砍功能了。

下一章讲并发：任务之间怎么安全协作。

> **延伸阅读 · 官方经验条目**：
> [静态缓冲按面板算 / 发布产物验证](https://github.com/FoloToy/ai-passport/blob/main/docs/reference/shinku-chen/release-artifact-verification.zh_CN.md)
> （一处 51 KB 缓冲错误让空闲堆只剩 8 KB） ·
> [视觉小说剧本包预算](https://github.com/FoloToy/ai-passport/blob/main/docs/reference/shinku-chen/vn-script-pack-budget-and-failure-modes.zh_CN.md) ·
> [网络音频流与内存预算](https://github.com/FoloToy/ai-passport/blob/main/docs/reference/phoenixzhc/network-audio-streaming-and-memory.zh_CN.md)
