# 22. 调试与排错

嵌入式调试和 PC 调试最大的区别是：**没有断点，没有 debugger**（除非接 JTAG）。
你的主要工具是日志、经验和对 panic 信息的解读能力。

## 22.1 第一工具：日志

```bash
idf.py -p COM4 monitor
```

几个技巧：

```c
esp_log_level_set("my_module", ESP_LOG_DEBUG);   // 只开某个模块的调试日志
```

在关键位置打印内存，这是最有用的调试信息：

```c
ESP_LOGI(TAG, "free=%u min=%u largest=%u",
         esp_get_free_heap_size(),
         esp_get_minimum_free_heap_size(),
         heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
```

```c
ESP_LOGI(TAG, "stack left=%u", uxTaskGetStackHighWaterMark(NULL));
```

## 22.2 读懂 panic

设备崩溃时串口会输出一大段。关键是这几行：

```
Guru Meditation Error: Core  0 panic'ed (LoadProhibited). Exception was unhandled.

Core  0 register dump:
PC      : 0x4200abcd  PS      : 0x00060030  ...
```

| panic 类型 | 含义 | 最常见原因 |
| --- | --- | --- |
| **LoadProhibited** | 读了非法地址 | **空指针 / 已释放的 `lv_obj_t`** |
| StoreProhibited | 写了非法地址 | 数组越界写、野指针 |
| **Stack protection fault** | 栈溢出 | 栈上大数组、递归太深 |
| **Task watchdog got triggered** | 看门狗 | 任务长时间不让出 CPU |
| IllegalInstruction | 非法指令 | 函数指针跑飞、栈被踩 |
| assert failed: ... | 断言 | 参数不合法（LVGL 断言很常见） |

### 怎么从 PC 找到代码行

ESP-IDF 提供了 `addr2line`：

```bash
# 把 panic 里的 PC 地址（如 0x4200abcd）换成行号
xtensa-esp32-elf-addr2line -pfiaC -e build/myproject.elf 0x4200abcd
# ESP32-C3 是 RISC-V，用：
riscv32-esp-elf-addr2line -pfiaC -e build/myproject.elf 0x4200abcd
```

或者更简单：

```bash
idf.py monitor   # 新版本会自动解析地址成 文件:行号
```

**如果 monitor 已经显示了 `0x4200abcd:app_main at main/main.c:42`，就不需要手动查了。**

## 22.3 症状 → 原因对照表

这是本章最实用的部分。

| 症状 | 最可能的原因 | 怎么查 |
| --- | --- | --- |
| **黑屏，但日志正常** | 背光没点亮 | 查 `bsp_display_backlight()` 有没有调用 |
| **黑屏，日志停在 display init** | SPI 接线/引脚不对 | 对比 `bsp_pins.h` 的引脚号 |
| **画面是负片** | 忘了发 INVON | `BSP_LCD_INVERT_COLOR` 应为 1 |
| **中文不显示** | 字体没有对应字形 | 检查字体 glyph 覆盖（不是编码问题） |
| **`adc1 is already in use`** | 第二次调 `adc_oneshot_new_unit()` | 全局只能 new 一次（第 6.6 节） |
| **按键没反应** | 回调阻塞了 / 队列没建 | 查 `input_dispatch_init()` 返回值 |
| **按键偶尔丢** | 队列满了被丢（正常） | 加大 `INPUT_QUEUE_DEPTH` 或加快处理 |
| **随机花屏** | 没加 `bsp_lvgl_lock()` | 所有非 LVGL 任务都要加锁 |
| **随机重启** | 栈溢出 / 看门狗 / 内存耗尽 | 看 panic 类型 |
| **`Task watchdog`** | 循环里没 `vTaskDelay` | 每帧加 `vTaskDelay(1)` |
| **`Stack protection fault`** | 栈上数组太大 | 改 `static` |
| **编译报找不到头文件** | `REQUIRES` 少了组件 | 加到 `main/CMakeLists.txt` |
| **编译报 undefined reference** | `SRCS` 漏了源文件 | 加到 `idf_component_register` |
| **NVS 读不出来 / 每次都像新机** | NVS 没初始化就 `nvs_open` | 确保 `nvs_flash_init()` 在前面 |
| **设置保存了但重启丢失** | 忘了 `nvs_commit()` | 加 commit（第 9.2 节） |
| **固件太大编译不过** | app 分区不够 | 加大分区或砍功能（3 MB 是契约上限） |
| **睡了醒不过来** | 引脚号当位掩码传了 | `gpio_wakeup_enable(GPIO_NUM_0, ...)` |
| **播一次声音后就不播了** | 堆碎片化，`xTaskCreate` 失败 | 改常驻任务 + 静态栈 |
| **本来有声音，之后突然没了** | 走过 `bsp_audio_sleep()` 却没有配对的 `wake()` | 之后 `set_format`/`write` 静默失败；用前先 `wake()`（第 21.8 节） |
| **关机/深睡前的播报听不到** | DMA 未排空就被 `i2s_channel_disable()` 掐断 | 写完等 `bytes/32 + 120` ms（第 7.2 节） |
| **串口满屏 `ClearCommError`，读不到日志** | 设备在 **deep sleep**，USB-Serial-JTAG 随 SoC 断电 | 先上电唤醒再抓；端口在 ≠ SoC 在跑（第 22.8 节） |
| **设备正常跑但日志一个字节都没有** | 控制台被配成 UART0（TX=GPIO21，与背光冲突） | 保持走 USB-Serial-JTAG（第 22.8 节） |

## 22.4 15 条运行时红线

除了"出错了怎么查"，更重要的是"一开始就别写错"。
下面是社区总结的运行时红线，**写代码时逐条对照**：

1. **LVGL 锁**：非渲染任务上下文操作任何 `lv_*` 必须 `bsp_lvgl_lock()`；超时放弃本次更新。
2. **按键回调只入队**：回调在共享 esp_timer 任务，禁止阻塞、操作 LVGL、播放/录音/联网。
3. **页面退出顺序**：先 `stop()` 停掉会访问 UI 的任务/定时器（拿到停止确认再继续），
   再 `exit()` 删 screen 并置空指针；**stop 超时应中止本次退出并允许重试**。
4. **音频阻塞与串行**：`bsp_audio_write/read` 放任务里；
   格式切换/睡眠/唤醒串行，切换前停 PCM；
   **`sleep()` 是单向门**（之后必须 `wake()` 才恢复），
   **`write()` 返回 ≠ 声音响完**（要关 I2S/断电前须按 `bytes/32 + 120ms` 等 DMA 排空）。
5. **I2C/I2S/ADC 唯一实例**：总线由 BSP 持有，不要重复 `i2c_new_master_bus`、
   不要新建 I2S；自定义 I2C 设备用 `bsp_i2c_bus()` 挂接；
   **不要再建第二个 ADC1 unit 或重配 GPIO0**。
6. **常量只引用不复制**：引脚、地址、电压窗口、面板参数一律 `#include "bsp_pins.h"` 用宏；
   **应用代码里出现 `20`、`0x18` 这类复制字面量即违规**。
7. **背光 GPIO21 与 UART0 默认 TX 冲突**：控制台固定用 USB-Serial-JTAG，
   别把日志改回 UART0。
8. **deep sleep 不可逆**：`*_prepare_deep_sleep()` 之后本次运行不能再恢复外设，
   必须马上深睡或重启；light sleep **只用** `bsp_audio_sleep/wake`，不能用 deep 版接口。
9. **无 PSRAM**：警惕大分配；总空闲堆够 ≠ 连续块够。
10. **中文字体**：Montserrat 无中文，必须集成子集字库；改文案/字号后做缺字排查，
    **禁止用隐藏方框掩盖**。
11. **电量 -1 降级**：`bsp_battery_soc()` 可能返回 -1，UI 必须容忍。
12. **失败可重试**：所有 `bsp_*_init()` 失败已回滚资源，
    可在修正接线/配置后重调，**不必重启**。
13. **不使用未暴露的硬件能力**：本板没有 LCD MISO / 触摸 / TE、
    没有功放使能脚（常通）、没有经典蓝牙；
    **不要凭"芯片好像支持"去调**，需要时先改 BSP 并完成真机验证。
14. **射频与功耗只认真机实测**：扫描/广播 demo 通过 ≠ 联网可靠 ≠ 续航达标；
    低功耗电流必须用仪器测。
15. **二次开发必须重设计 UI**：不得把测试菜单 / `ui_pixel` 外壳改名沿用；
    BSP、LVGL 控件与并发模式可复用。

> 第 6 条和第 13 条值得单独记住，它们是两类最常见的错误根源：
> **抄了一个魔数**（改硬件时会静默失效），
> 和**假设了一个不存在的硬件能力**（怎么写都调不通）。

## 22.5 定位方法：从"现象"到"代码"

### 方法一：二分注释

嵌入式没有 debugger 时，这是最快的方法：

1. 把 `app_main` 里后半部分的初始化注释掉，看还崩不崩；
2. 逐步加回来，直到找到触发点。

### 方法二：最小化复现

把可疑逻辑抽成一个独立页面/命令，单独跑。
PokeWalk 项目甚至专门做了**串口注入按键**来自动走一遍所有页面：

> "串口注入按键——让整条链路能自动走一遍并逐页截图。
> 与截图通道是同一思路的两半：那个解决'看不见屏幕'，这个解决'按不了键'。"

### 方法三：把逻辑搬到 PC 上跑

这是官方推荐的做法：

> "Keep testable state machines, protocols, timing, and layout calculations
> independent from ESP-IDF/LVGL and cover them with host tests."

如果你的状态机不 `#include` 任何 IDF 头文件，
它就能在 PC 上用 gcc 编译、用 gdb 调试、写单元测试。
**这比在设备上二分注释快十倍。**

社区项目普遍有 `tests/` 目录：

```
tests/
├── test_bsp_button.c
├── test_bsp_display_rounding.c
├── test_demo_navigation.c
├── test_ui_pixel_math.c
└── test_verify_firmware.py
```

### 方法四：官方的校验脚本

官方基线有两级门禁，**和 CI 用的是同一个脚本**：

```bash
./tools/validate.sh --static     # 代码风格 + 主机测试（不需要设备，几十秒）
./tools/validate.sh --firmware   # 干净构建 + merge-bin + 分区容量校验（超容会在这失败）
```

`tools/` 下还有：`verify_firmware.py`（合并镜像布局校验）、
`archive_firmware.py`（按 sha256 归档）、`check_repo.py`（静态检查）。

**在提交/发布前跑一遍**，能避免很多低级错误。

### 把能脱离硬件的逻辑，下沉成主机测试

这套仓库最值得学的工程习惯：**纯逻辑不依赖 ESP-IDF 和 LVGL，就能在电脑上秒级测。**
基线自己就是这么做的——`demo_navigation.c` 只吃输入枚举、只吐动作枚举，
所以整个菜单导航逻辑都能在 PC 上跑完。

编译命令（`tools/validate.sh` 里就是这一行）：

```bash
cc -std=c11 -Wall -Wextra -Werror -Imain \
   tests/test_demo_navigation.c main/demo_navigation.c -o /tmp/t && /tmp/t
```

自己写一个也一样简单：

```c
// tests/test_counter_logic.c
#include <assert.h>
#include "counter_logic.h"

int main(void) {
    assert(counter_step(5, +1) == 6);
    assert(counter_step(0, -1) == 0);     // 下限
    assert(counter_step(999, +1) == 999); // 上限
    return 0;
}
```

被测模块如果 `#include` 了 `esp_log.h`、`freertos/task.h` 这类头文件，
`tests/{audio,bsp,demo}_stubs/` 下提供了同名的精简头与实现——
**只实现被测路径需要的行为**。这就是"桩件（stub）"。
有了它，连"demo 的 `stop()` 必须在超时内完成握手"这种运行时契约都能在电脑上验证。

**TDD-lite 节奏**（比"写完再调"快得多）：

1. 先分清哪些是纯逻辑（状态机、计算、协议解析）→ 写成独立 .c + 主机测试；
2. 再写一层薄薄的 BSP/LVGL 封装把逻辑接到硬件；
3. 每改一小块就跑主机测试（几秒一次反馈）；
4. 交付前跑完整门禁；
5. 真机按清单验收。

#### 实例：在电脑上验证"停止握手"这条运行时契约

`stop()` 有个很难在真机上测的分支：**worker 卡住时，它必须在超时后返回
`ESP_ERR_TIMEOUT`**，而不是假装成功（见第 21 章）。
真机上要触发它，得让 worker 真的卡 2 秒——慢，而且不稳定。

用桩件把"有没有收到确认"变成**可注入的输入**，这条分支在 PC 上就是一行开关：

```c
// tests/stubs/rtos_stub.h —— 只实现被测路径需要的行为，别追求完整
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>

typedef void *TaskHandle_t;
typedef void *SemaphoreHandle_t;

#define pdTRUE   1
#define pdFALSE  0
#define pdPASS   1
#define pdMS_TO_TICKS(ms)  (ms)

void     stub_set_ack(bool ack);       // ★ 控制"worker 是否回确认"
bool     stub_ack_consumed(void);      // 确认信号量是否被取走
uint32_t stub_last_notify(void);       // 最近一次通知的命令字
```

```c
// tests/stubs/rtos_stub.c
#include "rtos_stub.h"

static bool     s_ack;
static bool     s_taken;
static uint32_t s_notify;

void     stub_set_ack(bool ack)     { s_ack = ack; s_taken = false; }
bool     stub_ack_consumed(void)    { return s_taken; }
uint32_t stub_last_notify(void)     { return s_notify; }

// 下面这几个"假实现"只要语义对就行：
//   xSemaphoreTake 的返回值就是被测的那条分支
int xSemaphoreTake(SemaphoreHandle_t s, uint32_t ticks)
{
    (void)s; (void)ticks;
    if (s_ack) { s_taken = true; return pdTRUE; }
    return pdFALSE;                    // ← 模拟超时
}
SemaphoreHandle_t xSemaphoreCreateBinary(void) { return (SemaphoreHandle_t)1; }
void vSemaphoreDelete(SemaphoreHandle_t s)     { (void)s; }
void xSemaphoreGive(SemaphoreHandle_t s)       { (void)s; s_ack = true; }
void xTaskNotify(TaskHandle_t t, uint32_t v, uint32_t a)
{ (void)t; (void)a; s_notify = v; }
void vTaskDelete(TaskHandle_t t)               { (void)t; }
```

```c
// tests/test_audio_worker_stop.c
#include <assert.h>
#include <stdio.h>
#include "rtos_stub.h"
#include "audio_worker.h"        // 被测的 stop() 实现（第 21 章 / snippets/06）

int main(void)
{
    assert(audio_worker_start() == 0);

    // 分支一：worker 正常回确认 → 必须成功，并真的删掉任务
    stub_set_ack(true);
    assert(audio_worker_stop() == 0);
    assert(stub_last_notify() == AUDIO_CMD_STOP);
    assert(stub_ack_consumed());

    // 分支二：worker 不回确认（超时）→ 必须【报错】，不能假装成功
    assert(audio_worker_start() == 0);
    stub_set_ack(false);
    assert(audio_worker_stop() != 0);      // ESP_ERR_TIMEOUT
    assert(!stub_ack_consumed());

    puts("stop handshake: 2/2 passed");
    return 0;
}
```

```bash
cc -std=c11 -Wall -Wextra -Werror -Itests/stubs -I. \
   tests/test_audio_worker_stop.c tests/stubs/rtos_stub.c audio_worker.c -o /tmp/t && /tmp/t
```

为什么值得写这 40 行：真机上"带着后台任务切走页面"是个**偶发**故障——
可能切十次才复现一次，而且复现时你已经不记得改了什么。
在 PC 上它是**必现**的，每次改 `stop()` 都能立刻验证。

> 同样的思路也可以套在按键去抖、菜单导航（`demo_navigation.c` 就是官方的例子）、
> NVS 默认值降级、电量 `-1` 降级这些地方——**凡是"输入 → 分支"清晰的逻辑，都能下沉。**

### 交付时按四段汇报

这是社区约定的汇报格式，目的是**不把"编译通过"说成"硬件通过"**：

```
Build       : idf.py build 通过 / 镜像 xxxx KB
Host tests  : tests/ 下 N 个主机测试通过
Device tests: 真机验收矩阵 N 项中 M 项通过
Unverified  : 中文显示 / 续航 / ...（未上板确认的部分）
```

最后一段最重要。**诚实标注未验证的部分**，
比事后被人发现"其实没测"要好得多。

> 一个重要的态度（Shinku 的 AGENTS.md）：
> "The complete gate requires an activated ESP-IDF 5.5.3 environment.
> **Do not describe a successful build as hardware validation.**"

**编译通过 ≠ 硬件验证。** 这句话值得反复提醒自己。

## 22.6 内存问题的专门排查

当设备随机重启且怀疑内存时：

```c
// 1. 在启动完成时打一次基线
ESP_LOGI(TAG, "boot done: free=%u largest=%u",
         esp_get_free_heap_size(),
         heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));

// 2. 在每个功能开关前后各打一次
ESP_LOGI(TAG, "after wifi: free=%u largest=%u", ...);
ESP_LOGI(TAG, "after ble:  free=%u largest=%u", ...);

// 3. 跑一段时间后看历史最低点
ESP_LOGI(TAG, "min ever: %u", esp_get_minimum_free_heap_size());
```

判定标准（第 11.6 节）：

- `min_free_heap` 长期 < 20 KB → 危险；
- `largest_free_block` < 8 KB → 任何超过 8 KB 的 `malloc` 都会失败。

## 22.7 一个"先查这个"的顺序

设备出问题时，按这个顺序排除：

```
1. 日志有没有输出？        → 没有：烧录/串口/供电问题
2. app_main 跑到了哪一行？  → 加日志定位
3. panic 是什么类型？       → 对照 22.2 的表
4. 最小可用内存是多少？     → < 20 KB 就是内存问题
5. 最近改了什么？           → git diff
```

**第 5 条看似废话，但在嵌入式开发里命中率极高。**

## 22.8 连日志都抓不到的时候

上面第 1 步是"日志有没有输出"。**这一步本身失败时，整套调试方法就断了**——
没有日志，你连 `app_main` 跑到哪一行都不知道。而这件事在本板上会用一个很有迷惑性的方式失败。

### 症状：`ClearCommError failed`

用 Python（pyserial）自己抓串口时，满屏刷这个错：

```
串口异常: ClearCommError failed (PermissionError(13, '设备不识别此命令。', None, 22))
```

端口**打得开**（设备管理器里 COM 口在、`list_ports` 也能列出 ESP32-C3），
但**一个字节的应用日志都读不出来**。这时不要怀疑脚本、也不要怀疑线材：
先看设备当前是不是**处于 deep sleep**。

**原因**：ESP32-C3 的"串口"不是独立 USB 转串口芯片，而是芯片内部的
**USB-Serial-JTAG 外设**。它在 SoC 内部，**deep sleep 时随 SoC 一起断电**。
USB 描述符可能还挂在总线上（所以 COM 口"在"），但设备已无法响应任何读命令。

```
设备运行中   → USB-Serial-JTAG 有电 → monitor 正常
设备 deep sleep → SoC 断电           → COM 口在，但读命令全部失败
设备刚被硬复位 → USB 重新枚举中      → 端口短暂不可用
设备已关机     → 电池通路断开        → COM 口整个消失（设备管理器里都没有）
```

**另一种"端口没了"：硬件电源键。** 板子除了三个功能键，还有一个**独立的硬件电源开关**，
它断的是电池供电通路——关机后 USB 不再枚举，设备管理器里的 COM 口**直接消失**。
这和 deep sleep 是两种不同现象，排查时先分清：

| 现象 | 大概率原因 | 动作 |
| --- | --- | --- |
| COM 口**在**，但一个字节都读不出 | deep sleep / USB 重新枚举中 | 按复位键或重新上电，见上文 |
| COM 口**整个消失** | 被硬件电源键关机了 | 按一下电源键重新开机 |
| COM 口在，日志是乱码 | 波特率或用了 UART0 而非 USB-Serial-JTAG | 见下一节 |

`esptool` 做完硬复位偶尔会把板子带进关机态，此时不要去改线材或驱动——按电源键开机即可。

**判断方法**：

```python
import serial.tools.list_ports as lp
for p in lp.comports():
    print(p.device, p.description, p.hwid)
# 能看到 VID:PID=303A:1001 → 是 ESP32-C3 原生 USB，但【这只能证明 USB 描述符在，
#                              不能证明 SoC 在跑】
```

**解法**：**先给设备上电/复位把它唤醒，再抓**。
如果你的抓取脚本要在"设备可能还没醒"的时候启动，得让它具备断点重连能力：

```python
while time.time() < deadline:
    try:
        with serial.Serial(PORT, 115200, timeout=1) as ser:
            log.write("port opened\n")
            while time.time() < deadline:
                data = ser.read(ser.in_waiting or 1)
                if data: log.write(data.decode('utf-8', 'replace'))
    except Exception as e:
        log.write(f"串口异常: {e}\n")     # ← 记一笔就重试，别让它中断整个脚本
        time.sleep(1.0)
```

> 关键点是"**异常记一笔就重试，而不是让它往上抛**"。
> 否则脚本在设备休眠期一上来就死掉，你永远等不到设备上电那一刻。

### 第二个可能：日志根本没从 USB 口出来

如果设备**明明在运行**（屏幕亮着、有声音），但 monitor 依然一个字节都没有，
那要查的是**控制台被路由到了哪里**。`sdkconfig` 里这几项决定日志出口：

```
CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y     ← 想要走原生 USB
CONFIG_ESP_CONSOLE_UART=y                ← 想要走 UART0 引脚（TX 在 GPIO21！）
CONFIG_ESP_CONSOLE_UART_NUM=0
CONFIG_ESP_CONSOLE_UART_BAUDRATE=115200
```

本板**必须走 USB-Serial-JTAG**（第 3.2 节"坑 4"）：
UART0 的默认 TX 是 **GPIO21，和背光是同一个引脚**——把日志改回 UART0，
不只屏幕背光会出问题，你也读不到任何东西。

### 抓日志的可靠顺序

```
1. 确认设备在运行（屏幕亮 / 有声音 / 按 RST 有反应）
   └─ 没反应 → 先上电唤醒，deep sleep 状态下串口是不存在的
2. 确认没有别的程序占着端口（idf.py monitor / 另一个串口助手 / WSL 转发）
3. esptool 能连上 ≠ 日志能读到
   └─ esptool 走的是 ROM 下载协议，SoC 休眠时它照样能复位芯片
4. 用 idf.py monitor 而不是自己写脚本（它已处理重连与解码）
   └─ 非要自写脚本，就按上面的"异常重试"写，别让异常终止脚本
```

> 这套现象容易误判成"脚本 bug"或"串口线坏了"，实际耗掉的时间远超它本身的价值。
> 记住一句：**端口在 ≠ SoC 在跑**。

## 22.9 小结

- 日志是第一工具，**内存和栈的三个数字要常打**；
- **抓不到日志时先问"设备醒着吗"**——deep sleep 时 USB-Serial-JTAG 随 SoC 断电，
  端口在 ≠ SoC 在跑；日志出口必须保持 USB-Serial-JTAG，不能改回 UART0；
- panic 类型决定方向：LoadProhibited = 野指针，
  Stack protection = 栈溢出，watchdog = 不让出 CPU；
- 22.3 那张症状对照表值得打印贴墙；
- 定位靠二分注释 / 最小复现 / **搬到 PC 上跑**；
- **编译通过 ≠ 硬件验证**。
