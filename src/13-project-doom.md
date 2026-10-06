# 13. 实战一：DOOM（36 个文件的最小可跑项目）

| 项目 | 值 |
| --- | --- |
| 排名 | #18 |
| 下载量 | 511 |
| 仓库 | `github.com/YeatsLiao/ai-passport-doom` |
| GitHub | `github.com/YeatsLiao/ai-passport-doom` |
| 规模 | `main/` **只有 1 个 .c 文件，80 行** |
| IDF | 5.5.3+ |
| 语言 | C |

**为什么第一拆解它**：它是全部 172 个仓库里**最小且完整**的项目。
`app_main` 只有 80 行，你能一口气读完整个程序的骨架。
如果你想找"第一个能读懂、能改动的仓库"，就是它。

## 13.1 工程结构

```
ai-passport-doom/
├── CMakeLists.txt          sdkconfig.defaults
├── partitions.csv          README.md
├── DOOM1.WAD  DOOM1_GBA.WAD  DOOM1_PROCESSED.WAD
├── main/
│   ├── CMakeLists.txt
│   └── main.c              ← 只有这一个 .c，80 行
├── components/
│   ├── bsp_doom/           ← 自定义精简 BSP（6 个导出函数）
│   │   ├── include/bsp_doom.h  bsp_pins.h
│   │   └── src/bsp_display.c (124 行)  bsp_button.c (59 行)
│   └── doom/
│       ├── i_system_esp32.c (528 行)   ← ESP32 适配层，真正的干货
│       └── esp32_wad.c      (79 行)    ← WAD 分区 mmap
└── tools/
```

两个不寻常的地方：

1. **它没有 `components/bsp`，而是自己写了 `bsp_doom`**（只有 6 个函数）；
2. **它完全不用 LVGL**——直接往面板推像素。

## 13.2 app_main 全文

这是全书最短的一个入口，值得逐行看：

```c
static void doom_task(void *arg)
{
    ESP_LOGI(TAG, "Doom engine starting...");

    I_PreInitGraphics();   // -> I_InitScreen_e32()
    I_Init();              // sound init (no-op on ESP32, GBA-only code)
    Z_Init();              // zone memory allocator (~256KB malloc)
    InitGlobals();         // zero-init the global state struct
    D_DoomMain();          // game main loop (never returns)
}

void app_main(void)
{
    ESP_LOGI(TAG, "=== AI-Passport Doom ===");
    esp_err_t e;

    e = bsp_display_init();
    if (e != ESP_OK) {
        ESP_LOGE(TAG, "Display init failed: %s", esp_err_to_name(e));
        return;
    }

    e = bsp_button_init();
    if (e != ESP_OK) {
        ESP_LOGE(TAG, "Button init failed: %s", esp_err_to_name(e));
        return;
    }

    if (doom_wad_init() != 0) {          // 从 flash 分区 mmap WAD
        ESP_LOGE(TAG, "WAD load failed!");
        return;
    }

    // Launch Doom engine on core 0 with 16KB stack
    xTaskCreatePinnedToCore(
        doom_task,
        "doom",
        16384,    // stack size (reduced from 32768)
        NULL,
        5,        // priority (higher than idle)
        NULL,
        0         // core 0 (ESP32-C3 only has one core)
    );

    // app_main returns; Doom runs in its own task forever
}
```

**启动只有五步**：屏幕 → 按键 → 加载 WAD → 建任务 → 返回。

注意最后一句注释：`app_main` 返回后游戏在自己任务里跑。
这就是第 2 章说的"写法 A"。

## 13.3 招牌实现：分条刷屏

这是本项目最值得学的一段。文件：`components/doom/i_system_esp32.c`。

```c
void I_FinishUpdate_e32(const byte *srcBuffer, const byte *palette,
                        const unsigned int width, const unsigned int height)
{
    if (!s_backbuffer || !s_linebuf) return;

    // D_DoomLoop runs the engine flat-out; yield once every few frames so
    // the IDLE task can feed the task watchdog.
    static unsigned int frame_count;
    if ((++frame_count & 0x3) == 0) {
        vTaskDelay(1);
    }

    const byte *src = (const byte *)s_backbuffer;

    // Convert and blit in strips of STRIP_H game rows, scaled VSCALE x vertically.
    for (int y = 0; y < FB_H; y += STRIP_H) {
        int sh = (y + STRIP_H > FB_H) ? FB_H - y : STRIP_H;
        const byte *row_src = src + y * FB_W;

        for (int r = 0; r < sh; r++) {
            const byte *sr = row_src + r * FB_W;
            uint16_t *dst = s_linebuf + (r * VSCALE) * FB_W;
            for (int x = 0; x < FB_W; x++) {
                uint16_t c = s_palette[sr[x]];
                for (int v = 0; v < VSCALE; v++)
                    dst[v * FB_W + x] = c;
            }
        }

        bsp_display_draw_bitmap(DISP_X_OFF, y * VSCALE,
                                FB_W, sh * VSCALE, s_linebuf);
    }
}
```

**它解决了什么**：内存放不下 150 KB 的整屏 RGB565。于是——

1. 引擎只渲染 **240×160 的 8bpp 调色板索引**（38 KB，而不是 150 KB）；
2. 用一条 **7.5 KB 的静态行缓冲**做"索引 → RGB565 转换 + 纵向 2× 拉伸"；
3. 每次只推 8 行游戏画面（16 物理行），分 10 次推完；
4. 每 4 帧 `vTaskDelay(1)`，防看门狗。

**这是第 11 章"纪律 1 + 纪律 3"的完整演示。**

## 13.4 另一个巧思：--wrap 重定向 clock()

DOOM 引擎用 `clock()` 做定时。但 newlib 在 ESP-IDF 上的 `clock()`
**恒返回 0**，引擎的定时循环会死等。

作者的解决方式非常漂亮——用链接器 `--wrap` 把 `clock` 换掉：

```c
// components/doom/i_system_esp32.c
clock_t __wrap_clock(void)
{
    return (clock_t)esp_timer_get_time();
}
```

```cmake
# components/doom/CMakeLists.txt
target_link_options(${COMPONENT_LIB} INTERFACE "-Wl,--wrap=clock")
```

**`--wrap=symbol` 会让所有对 `symbol` 的引用重定向到 `__wrap_symbol`。**
当你移植一个"假设有标准 libc"的 C 库到嵌入式平台时，这招能救你的命。

## 13.5 它踩过的坑（docs/issues.md 原文）

**坑 1：Z_Malloc 内存耗尽（红屏卡死）**

> 现象：进入关卡或 demo 演示时 `Z_Malloc: failed on allocation of 36348 bytes`。
> 根因：ESP32-C3 无 PSRAM，可用 SRAM ~400 KB，系统堆占 ~100 KB+；
> 原始 zone 256 KB 太大。
> 解决：1. zone 256 KB → **80 KB**，添加 128 KB 静态 overflow 缓冲区（.bss 段）……

**坑 3：帧缓冲分配失败**

> 解决：帧缓冲（38 KB）和行缓冲（8 KB）从 `malloc` 改为 `.bss` 静态数组……
> DOOM 任务栈从 32 KB 缩减到 16 KB（大数组已移出）

**坑 4：WiFi 配置无法持久关闭**

> 接受现状——WiFi 编译进固件但不调用 `esp_wifi_init()`，运行时不占额外内存。

**待解决**：

> 声音系统：**已禁用**——ESP32-C3 RAM 不够同时跑音频。

最后一条最能说明问题：**连 DOOM 都要放弃声音。**

## 13.6 构建它

```bash
# 必须把 GBADoom 单独克隆到同级目录，否则编译不过
git clone https://github.com/YeatsLiao/ai-passport-doom
git clone https://github.com/pret/GBADoom          # 同级目录

cd ai-passport-doom
idf.py build
idf.py -p COM4 flash

# 首次要单独烧 WAD（一次性）
esptool.py -p COM4 -b 460800 write_flash 0x310000 DOOM1_PROCESSED.WAD
idf.py -p COM4 monitor
```

注意：**不能直接烧 `DOOM1.WAD`**，它需要两步预处理
（`tools/merge_pwad.py` + `GbaWadUtil.exe`）。

## 13.7 你能从它抄走什么

| 想抄的东西 | 在哪 |
| --- | --- |
| 极简入口骨架 | `main/main.c`（80 行） |
| 分条刷屏 | `components/doom/i_system_esp32.c` |
| 裸 `esp_lcd` 初始化（不用 LVGL） | `components/bsp_doom/src/bsp_display.c` |
| ADC 按键轮询 | `components/bsp_doom/src/bsp_button.c` |
| 分区 mmap 加载大文件 | `components/doom/esp32_wad.c` |
| 省内存 sdkconfig | `sdkconfig.defaults` |

## 13.8 小结

- 36 个文件、`main.c` 80 行——**最好的第一个练手项目**；
- 分条刷屏 = 静态行缓冲 + 分次推送，是无 PSRAM 下的标准答案；
- `--wrap=clock` 是移植第三方 C 库的利器；
- 它**禁用了音频**，说明内存有多紧；
- 想"看懂一个完整项目"就从这里开始。
