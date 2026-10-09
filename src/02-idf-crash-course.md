# 2. 给 C 程序员的 ESP-IDF 速通

本章的目标是：**用你已经会的 C 知识，把 ESP-IDF 里陌生的部分全部类比掉**。
读完之后你应该能看懂任何一个社区仓库的工程结构，不需要先去读官方文档。

> **版本提醒**：本书所有示例锁定 **ESP-IDF 5.5.3**（组件契约 `>=5.5.3,<5.6.0`）。
> 官方另有 6.1 线（AI 语音对话走这条，且已声明 5.x 不再支持），两条线**不兼容**。
> 你现在该选哪条、5.5→6.1 差在哪，统一定论在第 23.4 节，动手前先扫一眼。

## 2.1 ESP-IDF 是什么

一句话：**一套 CMake 构建系统 + 一个 FreeRTOS 内核 + 一堆芯片外设驱动库。**

你写的还是标准 C（GCC 编译），`stdio.h`、`string.h`、`stdlib.h` 都在。
多出来的东西只有三类：

| 新增的东西 | 类比你已经知道的 |
| --- | --- |
| CMake 构建（`idf.py build`） | 相当于有人帮你写好了 Makefile，你只列源文件 |
| FreeRTOS 任务 | 相当于“能独立跑的第二个 `for(;;)`”，但栈大小要你手动指定 |
| `esp_xxx()` / `driver/gpio.h` 等 | 相当于 libc 之外的“系统库”，用来操作硬件 |

## 2.2 一个工程长什么样

以官方基线为例（去掉文档目录）：

```text
ai-passport/
├── CMakeLists.txt          # 项目根：三行，几乎不用改
├── sdkconfig.defaults      # 默认配置（相当于 .config 的默认值）
├── partitions.csv          # Flash 怎么分区
├── dependencies.lock       # 托管组件版本锁（相当于 package-lock.json）
├── main/                   # 你的应用代码
│   ├── CMakeLists.txt      # 列出源文件 + 依赖
│   └── *.c
└── components/             # 可复用组件
    └── bsp/                # 板级支持包（本书第 4 章的主角）
        ├── CMakeLists.txt
        ├── include/*.h
        └── src/*.c
```

根 `CMakeLists.txt` 通常只有三行，几乎永远是这三行：

```cmake
cmake_minimum_required(VERSION 3.16)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(FoloToy-AI-Passport)
```

第二行是关键：它把 ESP-IDF 的整个构建系统拉了进来。`project(...)` 这一行
会触发 ESP-IDF 扫描所有组件、生成 `sdkconfig`、配置编译工具链。
**你不需要写任何编译规则。**

## 2.3 列出源文件：idf_component_register

你会写 C，那你一定知道 Makefile 里要列 `.c` 文件。
在 ESP-IDF 里，这件事换了个名字，写在 `main/CMakeLists.txt`：

```cmake
idf_component_register(
    SRCS "main.c"
         "demo_navigation.c"
         "ui_pixel.c"
         "demo_display.c"
         "demo_button.c"
         "demo_audio.c"
         "demo_battery.c"
    INCLUDE_DIRS "."
    REQUIRES bsp bt esp_event esp_hw_support esp_netif esp_timer esp_wifi nvs_flash
)
```

三个参数对上你已知的概念：

| 参数 | 相当于 |
| --- | --- |
| `SRCS` | Makefile 里的源文件列表 |
| `INCLUDE_DIRS` | `-I` 头文件搜索路径 |
| `REQUIRES` | `-l` 链接的库 + 那些库的头文件路径 |

**`REQUIRES` 是最容易忘的一项。** 忘了会得到一个很误导人的错误：
`fatal error: bsp_display.h: No such file or directory`。
明明文件就在 `components/bsp/include/` 里，却说找不到——
因为 ESP-IDF 的组件之间**默认不共享头文件路径**，必须显式声明依赖。

## 2.4 组件 = 一个带 CMakeLists 的目录

组件没有注册表、没有配置文件。
**任何目录下只要有一个调用 `idf_component_register()` 的 `CMakeLists.txt`，
它就是一个组件。**

- `components/` 下的目录：项目自带组件
- ESP-IDF 自带的：`$IDF_PATH/components/`（FreeRTOS、driver、esp_wifi……）
- `managed_components/`：从组件仓库在线拉取的（**不要手动改这个目录**）

AI Passport 项目一般会拉到这几个托管组件：

| 组件 | 干什么 |
| --- | --- |
| `lvgl/lvgl` | 图形库 |
| `esp_lvgl_port` | 把 LVGL 接到 ESP 的屏幕/触摸/锁上 |
| `button` | 按键组件（支持 ADC 按键、长按、双击） |
| `esp_codec_dev` | 音频 codec 抽象（ES8311 用它） |

它们写在 `main/idf_component.yml` 或 `components/bsp/idf_component.yml` 里，
首次构建时自动下载，版本记录在 `dependencies.lock`。

### 2.4.1 驱动的名字：为什么是 `esp_driver_i2c` 而不是 `driver`

从 ESP-IDF 5.2 起，官方把原来那个巨大的 `driver` 组件**按外设拆成了独立组件**。
这件事第一次做的人几乎都会栽——网上老教程里清一色写 `REQUIRES driver`，
你在 5.5.3 上照抄就会编译失败。

本项目 `components/bsp/CMakeLists.txt` 的真实依赖长这样：

```cmake
idf_component_register(
    SRCS "src/bsp_i2c.c" ... "src/bsp_battery.c"
    INCLUDE_DIRS "include"
    REQUIRES driver esp_driver_i2c esp_driver_i2s esp_lcd esp_lvgl_port button esp_adc esp_codec_dev
    PRIV_REQUIRES esp_timer
)
```

对照关系（这些目录名都在 `$IDF_PATH/components/` 下真实存在）：

| 你要用的东西 | 头文件 | 5.5.3 里的组件名 | 写 `driver` 行不行 |
| --- | --- | --- | --- |
| GPIO | `driver/gpio.h` | `esp_driver_gpio` | 勉强能编过，但**别依赖** |
| I2C 主机 | `driver/i2c_master.h` | `esp_driver_i2c` | ❌ 会报错 |
| I2S | `driver/i2s_std.h` | `esp_driver_i2s` | ❌ 会报错 |
| SPI | `driver/spi_master.h` | `esp_driver_spi` | ❌ 会报错 |
| UART | `driver/uart.h` | `esp_driver_uart` | ❌ 会报错 |
| ADC | `esp_adc/adc_oneshot.h` | `esp_adc` | ❌ 会报错 |
| LCD | `esp_lcd_panel_io.h` | `esp_lcd` | ❌ 会报错 |
| TWAI / CAN | `driver/twai.h` | 仍在 `driver` 里 | ✅ 可以 |

注意最后两行——**不是所有东西都搬走了**。
`driver/` 目录在 5.5.3 里仍然存在，但只剩下 `deprecated/`、`i2c`（兼容层）、
`touch_sensor`、`twai` 这些残留；`components/driver/sdkconfig.rename` 就是迁移标记。
所以“老教程写 `driver`”在个别外设上还能过，在 I2C/I2S/SPI/ADC 上就断了。

> **为什么官方要拆？** 以前你为了用 I2C，得把整个 `driver` 拖进来，
> 于是 GPIO、TWAI、触摸全都跟着编译进固件。拆分后按需声明，
> 既能少编译无关代码，也让“这个组件到底依赖什么”变得可查。
> 迁移背景见官方 [5.2→5.3 迁移指南](https://docs.espressif.com/projects/esp-idf/zh_CN/v5.3.2/esp32/migration-guides/release-5.x/5.2-to-5.3.html)。

**你什么时候需要关心这段？** 只有当你要**自己写组件**（而不是直接用现成的 `bsp`）时。
如果你的 `main/CMakeLists.txt` 只 `REQUIRES bsp`，那 bsp 已经把依赖传递过来了，你不用管。
一旦你开始 `#include "driver/i2s_std.h"` 写自己的驱动，就得自己把 `esp_driver_i2s` 写上。

### 2.4.2 加新组件的三步：声明 → fullclean → 验证

想用注册表上的第三方组件（比如官方 `button`），有命令行一步的方式：

```bash
idf.py add-dependency "espressif/button^4.1.6"
```

它会自动改写 `main/idf_component.yml`、下载到 `managed_components/`、更新 `dependencies.lock`。

**但紧接着必须做一次完整清理**：

```bash
idf.py fullclean
```

为什么这么强调？因为 CMake 的配置结果有缓存。
**旧构建目录里没有新组件的头文件路径**，于是你会看到一个
“我明明写对名字了却说找不到”的错，这类错最消耗时间：

| 现象 | 真实原因 |
| --- | --- |
| `fatal error: button.h: No such file or directory` | 依赖加了，但没 fullclean，CMake 不知道 |
| 头文件找到了，链接时报 undefined symbol | CMakeLists 改了但没重新配置 |
| 改动“没生效”、跑的还是旧程序 | 同上，缓存 |

在 VS Code 里等价操作是 `ESP-IDF: Full Clean Project`。
官方文档特别提醒：**在已有工程上改依赖时这一步尤其重要**——
新建工程天然干净，改老工程最容易忘了。

> **顺带一句**：`dependencies.lock` 是自动生成的，别手改。
> 它锁死了每个托管组件的确切版本——这个项目里 `espressif/button` 钉在 **4.2.0**、
> `esp_lvgl_port` 钉在 **2.9.0**、LVGL 是 `^9.5.0`。
> 想升级就改 `idf_component.yml`（第 3.1 节讲过为什么本项目要钉死版本）。

## 2.5 你熟悉的 main() 变成了 app_main()

不是 `int main(void)`，而是：

```c
void app_main(void)
{
    // 你的程序从这里开始
}
```

区别不只是名字。在 PC 上，`main()` 返回意味着进程结束。
在这里，`app_main()` 是一个**任务的入口函数**，它返回之后设备还在跑，
只是你创建的任务继续活着。

所以你会看到两种写法：

**写法 A：app_main 里把活干完，然后返回**（最常见）

```c
void app_main(void)
{
    bsp_display_init();
    bsp_lvgl_init();
    bsp_button_init(on_key, NULL);
    // ... 建好 UI 和任务，然后返回
}
```

**写法 B：app_main 里跑一个永不返回的循环**

```c
void app_main(void)
{
    // 初始化...
    while (true) {
        auto bits = xEventGroupWaitBits(event_group_, ALL_EVENTS, ...);
        // 处理事件
    }
}
```

写法 B 出现在小智 AI 项目里（第 17 章会讲）。两种都合法，
但**绝大多数 AI Passport 项目用写法 A**——UI 由 LVGL 自己的任务驱动，
你不需要自己写主循环。

## 2.6 错误处理：esp_err_t 而不是 -1

ESP-IDF 的函数几乎不返回 `int`，而是返回 `esp_err_t`。
它本质上是 `int32_t`，`ESP_OK` = 0，其他都是负数错误码。

```c
esp_err_t err = bsp_display_init();
if (err != ESP_OK) {
    ESP_LOGE(TAG, "显示初始化失败: %s", esp_err_to_name(err));
    return;
}
```

三个必须认识的东西：

| 宏/函数 | 作用 | 什么时候用 |
| --- | --- | --- |
| `ESP_ERROR_CHECK(x)` | 出错就打印 + `abort()` | 只在“这个失败就没必要活下去”时用 |
| `esp_err_to_name(e)` | 错误码 → 可读字符串 | 打日志时 |
| `esp_err_to_name` vs `esp_err_to_name` | — | — |

**习惯上的约定**：初始化阶段用 `ESP_ERROR_CHECK`（早点炸，别带着坏状态继续跑），
运行阶段手动判断并降级（比如电量读不出来就显示 `-- %` 而不是重启）。

> 一个真实的分寸感：官方 demo 的判断是
> “屏幕失败就直接 return，不做降级”——因为屏幕是 UI 的唯一载体，
> 而“电量计失败”只是让电量显示变成 `--`，其他功能照常。
> **不同的失败，代价不同。**

## 2.7 日志：printf 的替代品

```c
static const char *TAG = "main";

ESP_LOGI(TAG, "启动完成, 堆 %d 字节", esp_get_free_heap_size());
ESP_LOGW(TAG, "电量低: %d%%", soc);
ESP_LOGE(TAG, "音频失败: %s", esp_err_to_name(err));
ESP_LOGD(TAG, "调试信息");   // 默认不输出
```

| 宏 | 级别 | 说明 |
| --- | --- | --- |
| `ESP_LOGE` | Error | 错误 |
| `ESP_LOGW` | Warning | 警告 |
| `ESP_LOGI` | Info | 信息（默认输出） |
| `ESP_LOGD` | Debug | 调试（默认不输出） |
| `ESP_LOGV` | Verbose | 啰嗦（默认不输出） |

运行时可以单独调某个 TAG 的级别：

```c
esp_log_level_set("main", ESP_LOG_DEBUG);
```

**为什么不用 `printf`**：`printf` 能用，但它不带级别、不带 TAG，
在几十个模块同时输出时会变成一团浆糊。而且它的开销更大。

## 2.8 FreeRTOS：让几件事“同时”进行的办法

你肯定写过这种主循环：

```c
void app_main(void) {
    for (;;) {
        check_button();     // 看按键
        update_screen();    // 刷画面
        play_audio();       // 放声音
    }
}
```

这样写有个硬伤：**任何一件事卡住，后面全跟着卡**。
`play_audio()` 要等 200 ms 的 DMA 搬完，这 200 ms 里屏幕是死的、按键是不响应的。

FreeRTOS 的任务就是把上面这个循环**拆成三个独立的小循环**，
由调度器负责在它们之间切换：

```c
static void my_task(void *arg)
{
    for (;;) {
        // 干活
        vTaskDelay(pdMS_TO_TICKS(100));   // 主动让出 CPU
    }
}

xTaskCreate(my_task,      // 函数
            "my_task",    // 名字（调试用，最多 16 字符）
            4096,         // ★ 栈大小，单位是【字节】
            NULL,         // 传给任务的参数
            5,            // 优先级
            NULL);        // 任务句柄（不需要就 NULL）
```

**“任务”这个词要记住**：FreeRTOS 官方叫 **task**，本书统一叫**任务**。
你在别处看到有人叫它“线程”，说的是同一个东西，但本书不会用“线程”这个词
（原因见第 12.1.1 节——单核上叫“线程”容易让人误以为真能并行）。

和你在 PC 上写多线程的三个关键差别：

1. **栈大小必须你指定，单位是字节。** 4096 字节 = 4 KB。
   这不是虚拟内存，是实打实从堆里挖走的。栈溢出不会报“段错误”，
   而是触发栈保护直接重启。
2. **优先级数字越大越优先。** 官方基线里 LVGL 任务是 **4**
   （esp_lvgl_port 2.9.0 的默认值），音频这类慢活也是 **4**，
   只有输入派发任务是 **5**。所以你做重活时用 **4 或更低**，别抢画面的 CPU。
   （第 12.1 节有完整表格和出处。）
3. **单核。** ESP32-C3 只有一个核（`SOC_CPU_CORES_NUM` 就是 `1U`），
   任务是**交替执行**不是同时执行，别指望并行计算加速。
   所以 `xTaskCreatePinnedToCore` 那种指定核的写法在这块板上没有意义——
   详见第 12.1.1 节。

延时用 `vTaskDelay(pdMS_TO_TICKS(100))`，别用 `sleep()`。
（`vTaskDelay` 是**让出 CPU** 的等待：这 100 ms 里别的任务照跑。
`sleep()` 来自标准库，在裸机环境里行为不可靠。）

> 一个真实的优先级设计（PokeWalk 的后台任务）：
> ```c
> // 4096 栈：大数组都是 static，栈上只有指针与循环变量。
> // 优先级 4 —— 低于 LVGL（5），扫描不该抢画面的 CPU。
> xTaskCreate(world_task, "world", 4096, NULL, 4, NULL);
> ```
>
> 注：这句注释里的“LVGL（5）”是 **PokeWalk 自己固件**的配置；
> 官方基线的 LVGL 任务是 **4**（源码可查，见第 12.1 节）。
> 思路照抄（慢活别抢 UI），数字别照抄。

## 2.9 Kconfig / sdkconfig：编译期开关

ESP-IDF 有几百个编译期配置（`CONFIG_XXX`），通过 `menuconfig` 改，
结果存在 `sdkconfig` 里。项目用 `sdkconfig.defaults` 提交默认值：

```text
CONFIG_COMPILER_OPTIMIZATION_SIZE=y
CONFIG_LV_MEM_SIZE_KILOBYTES=24
CONFIG_FREERTOS_IDLE_TASK_STACKSIZE=768
CONFIG_LWIP_IPV6=n
```

常用命令：

```bash
idf.py menuconfig   # 图形界面改配置
idf.py build        # 编译
```

你的代码里可以直接用：

```c
#if CONFIG_POKEWALK_SILENT_BOOT
    ESP_LOGI(TAG, "静音构建：本次启动禁用音频输出");
#endif
```

## 2.10 把素材编进固件

PC 程序读文件用 `fopen`。嵌入式里没有文件系统（除非你专门做一个），
所以小素材通常用 CMake 直接编进固件：

```cmake
idf_component_register(
    SRCS "main.c"
    EMBED_FILES "assets/gen1.bin"
    EMBED_TXTFILES "certs/servercert.pem"
)
```

编译后你会得到三个符号，命名规则是文件名加点换位：

```c
extern const uint8_t _binary_gen1_bin_start[] asm("_binary_gen1_bin_start");
extern const uint8_t _binary_gen1_bin_end[]   asm("_binary_gen1_bin_end");

size_t len = _binary_gen1_bin_end - _binary_gen1_bin_start;
```

规则：`assets/gen1_front.bin` → `_binary_gen1_front_bin_start`（**路径中的 `/` 会丢掉，只留文件名**）。

大素材不要这么干——它会被算进 app 分区（很多社区项目把 app 开成 3 MB，素材一多就顶到边）。大素材用独立分区，第 9 章讲；第 18 章有一份完整的容量账。

## 2.11 标准 C 在这里的几点不同

这些是“会 C”的人最容易踩的：

| 你以为 | 实际上 |
| --- | --- |
| `malloc(150 * 1024)` 没问题 | 会失败。最大连续块往往 < 8 KB |
| 递归没问题 | 栈只有几 KB，别递归，别在栈上开大数组 |
| `float`/`double` 随便用 | ESP32-C3 无硬件浮点单元，软件模拟很慢，能免则免 |
| `printf("%f")` 能打印 | 默认 **newlib 的 `%f` 被裁掉了**，打不出来 |
| `clock()` 能用 | **恒返回 0**（有项目被这个坑到，见第 13 章） |
| `malloc/free` 反复用没事 | 会碎片化，社区里因此出现过“只停不播”的 bug |
| 未对齐访问只是慢 | 在 RISC-V 上是**异常**，不是慢速 |

### 2.11.1 位运算：`1ULL << n` 到底在干什么

嵌入式代码里到处是 `1ULL << n`，书上一般默认你会，这里补半页。
它做的事很简单：**把一个整数的第 n 位（从 0 数起）单独挑出来**。

```c
1 << 0   == 0b0001  == 1
1 << 3   == 0b1000  == 8
1 << 9   == 0b10_0000_0000 == 512
```

实际用的是这三件套：

```c
mask  = (1ULL << n);        // 造掩码：只保留第 n 位
a |=  (1ULL << n);          // 置位：把第 n 位设成 1
a &= ~(1ULL << n);          // 清零：把第 n 位设成 0
if (a & (1ULL << n)) { }    // 判断：第 n 位是不是 1
```

**为什么是 `1ULL` 而不是 `1`**：`1` 是 `int`，在 ESP32-C3 上是 **32 位**。
左移超过 31 位就是未定义行为，实际会丢掉高位。
GPIO 编号能到 48，所以官方代码一律写 `1ULL`（unsigned long long，64 位）。
这不是笔误，是必须。

**本书里你会碰到的三处**：

| 位置 | 代码 | 含义 |
| --- | --- | --- |
| 第 6 章按键唤醒 | `gpio_wakeup_enable(pin, ...)` 的掩码是 `1ULL << pin` | 指定哪根脚能唤醒 |
| 第 8 章深睡 | ext1 的掩码要 `1ULL << GPIO_NUM_0`，**不是** `GPIO_NUM_0` | 传错就**永远唤不醒** |
| 第 20 章图片 | `rgb565 = ((r & 0xF8) << 8) \| ((g & 0xFC) << 3) \| (b >> 3)` | 把 RGB888 压成 16 位 |

最后那行逐段拆开看就明白了：`r & 0xF8` 是**只留红色高 5 位**（丢掉低 3 位），
再左移 8 位放到高 5 位的位置；绿色留高 6 位左移 3 位居中；蓝色只留高 5 位右移 3 位。
5 + 6 + 5 = 16 位，正好一个 RGB565 像素。

## 2.12 小结：你只需要记住的新东西

```c
工程结构      CMakeLists.txt(根) + main/CMakeLists.txt(SRCS/REQUIRES) + components/
入口          void app_main(void)，通常初始化完就返回
错误          esp_err_t / ESP_OK / ESP_ERROR_CHECK / esp_err_to_name
日志          ESP_LOGI/W/E + TAG
并发          xTaskCreate(函数名, 名字, 栈字节数, 参数, 优先级, 句柄)
延时          vTaskDelay(pdMS_TO_TICKS(ms))
配置          sdkconfig.defaults + CONFIG_XXX + menuconfig
资源          EMBED_FILES → _binary_xxx_start
```

下一章把这些用起来：装环境、编译、烧到板子上、看日志。
