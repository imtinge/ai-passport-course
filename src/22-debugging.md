# 22. 调试与排错

嵌入式调试和 PC 调试最大的区别是：**没有断点，没有 debugger**——**大多数情况下**如此。
你的主要工具是日志、经验和对 panic 信息的解读能力。

> 📌 **但你这块板是个例外：它能打断点。**
> 前面说过 GPIO18/19 是 **USB-Serial-JTAG**。ESP32-C3 内置这个外设
> （`SOC_USB_SERIAL_JTAG_SUPPORTED = 1`），它**同时**是串口和 JTAG 调试口——
> 一根 USB 线、零额外硬件，就能用 OpenOCD + GDB 打断点、看变量、单步。
> 所以“嵌入式没法调试”是过时印象，不是这块板的事实。
> 怎么用见 **22.9 真断点调试（JTAG）**；不想折腾就接着用日志，**99% 的问题日志够用**。

## 22.0 先按现象定位（排障索引）

不知道从哪查起时，先用这张表按**现象**跳到对应章节；章节内再按子系统细查。

| 你看到的现象 | 优先看 |
| --- | --- |
| 设备一直重启 / 反复复位 | 12.7 看门狗（任务长时间不让出 CPU）、12.8 栈溢出；**插上 USB 供电试试** → 22.3.1 欠压（brownout） |
| 重启只在用电池时发生，插 USB 就正常 | 22.3.1 欠压：电压跌破 2.51 V 硬件直接复位 |
| 串口打出 `Guru Meditation` / panic | 22.2 读懂 panic、A.10 内存数字 |
| 中文显示成方框 / 空白 | 5.8 为什么缺字、19.5–19.6 字形覆盖与占位符 |
| 屏幕撕裂、局部花屏、UI 卡顿 | 5.3 一帧画面怎么上屏、5.4 LVGL 锁 |
| 开机“啪”一声爆音 / 播放杂音 | 7.6 开机爆音、7.4 真实播放循环 |
| 连不上 Wi-Fi / 连上就掉 | 10.2 全部事件、10.3 重连退避、10.6 连接失败降级 |
| HTTPS 握手失败、证书报错 | 10c.2 证书 / 时间 / 内存（TLS 依赖系统时间） |
| 待机电流偏高、睡不下去 | 8.4 深睡契约（C 版）、B.7.4 深睡（MicroPython 版） |
| 内存越跑越少 / 慢慢变小 | 11.2 五条纪律、12.5.1 停止握手（别硬删任务） |
| 烧录失败 / 构建跑不起来 | 3.3.1 Windows 实战、3.5 合并镜像与救砖 |
| 按键不灵 / 误触 / 长按无效 | 6.3 回调里不许干活、6.6 两个真实坑 |
| 音频播到一半卡死 / 无法打断 | 7.3 播放必须在自己任务里、21.4 分块送数据 |
| 改了字体/文案/主题后缺字 | 19.6 不要关掉占位符、19.5 验证覆盖 |
| 外设上电瞬间“被选中”一次 / 初始化时序诡异 | 1.5 上电毛刺（MTCK/MTDO/GPIO10/U0RXD 约 5 ns 低毛刺，规格书表 2-2） |

> 这张表是按“新手最常踩”排的，不是全集。子系统级的完整排障表在各章末尾
> （如 10.11、10b.9、10c.8、19.7、20.9），那里更细。

### 22.0.1 先定层，再查代码

上面那张表是「现象 → 原因」平铺的，好用，但有个陷阱：
**你会直接跳到自己最熟悉的那层去查**，通常是代码层——翻 `git diff`、加日志、二分注释。

而有些故障**在代码里根本看不出来**：供电不足、信号太弱、云端限流。
代码写得再对，该崩还是崩。

所以在这之前，先花一分钟**由下往上过一遍这五层**，每层只有一条判据：

```text
L1 供电与物理
     电池供电换成 USB，还复现吗？设备烫吗？
     ── 不复现 = 物理层问题，到此为止，别查代码（22.3.1）

L2 链路与射频
     2.4 GHz 吗？RSSI 多少？中间有遮挡吗？
     ── RSSI < -80 dBm，先解决信号再谈代码（10.2 / 10.11）

L3 协议与连接
     Wi-Fi 事件走到哪一步？拿到 IP 了吗？DNS 通吗？
     ── 打印断开 reason code，对照 10.11 那张表

L4 应用与状态
     超时设了吗？重试有退避吗？时间同步了吗（影响 TLS）？
     ── 10c.2 证书 / 时间 / 内存三件套

L5 云端与服务
     接口还在吗？鉴权过期了吗？被限流了吗？
     ── 连接正常但返回 401 = 10c.2 ④ 鉴权与 token
```

**这条链的价值不在于每层都要查，在于你能在正确的那一层停下来。**
查到 L1 就定位了，就不该再往 L3 走；反过来，
如果在 L1 明明复现了却还去翻 `git diff`，那是把 30 秒的事做成三天。

> 这套顺序是按**这块板**裁剪的，不是通用的 TCP/IP 五层。
> 比如本书用 IDF 的高层 API，不直接操作 UART 帧，所以 L2 没有波特率和校验位——
> 照搬通用物联网排查表在这里反而会浪费时间。

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

```text
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
| **改了旋转/镜像却没生效** | `bsp_display_lvgl.c` 的 `rotation` 会**在注册显示时重新下发 MADCTL**，覆盖底层 mirror | 改 `lvgl_port_display_cfg_t.rotation`，别只改 `esp_lcd_panel_mirror()`（第 5.1 节） |
| **颜色怪/颠倒且越改越乱** | `swap_bytes`、RGB/BGR、反色三个变量同时动 | **一次只改一个变量**（第 5.1 节） |
| **两个 I2C 芯片同时失联** | 在 I2C0 上创建了第二条临时总线 | 只走 `bsp_i2c_bus()` + `i2c_master_probe()`（第 4.4 节） |
| **只找不到 ES8311（CW2017 正常）** | 控制接口要 **8 bit 地址 `0x18 << 1`** | 别把 7 bit 地址直接传给 codec-dev（第 4.4 节） |
| **录音全是 0** | `no_dac_ref` 被改成 false（读入通道变 DAC reference） | 保持 `no_dac_ref=true`；再查 DIN=GPIO4 与麦克风增益 30 dB（第 7 章） |
| **电量一直显示 `--`** | `0x63` 没应答 / SOC 读到 >100 / profile 未就绪 | 按第 8.1 节的表逐项查；首帧别虚构百分比 |
| **加大 UI 之后 I2S 报 NO_MEM** | 双缓冲/LVGL 池与 I2S DMA 抢内部 RAM | 三者一起算（第 11 章；I2S 是 6×240 frame） |
| **加大字体/图片后开机白屏** | LVGL 24 KB 池耗尽 | 池耗尽表现为白屏而不是报错；别盲目调大池（第 5、11 章） |

### 22.3.1 设备重启，先怀疑供电

上一张表里「**随机重启**」给了三个原因：栈溢出、看门狗、内存耗尽。
**这三个全是软件原因。** 但在这块板上还有一个同样常见、却被漏掉的原因——
**电压瞬间跌落，芯片自己把自己复位了**，软件完全来不及干预。

这个机制叫 **brownout（欠压）检测**：

> 源码：`components/esp_hw_support/power_supply/port/esp32c3/Kconfig.power`
>
> “The ESP32-C3 has a built-in brownout detector which can detect if the voltage is lower than
> a specific value. If this happens, it will **reset the chip** in order to prevent unintended behaviour.”

**官方项目是开着的**（`sdkconfig:1319-1320`）：

```text
CONFIG_ESP_BROWNOUT_DET=y
CONFIG_ESP_BROWNOUT_DET_LVL_SEL_7=y     → 阈值 2.51 V
```

而芯片的工作电压是 **3.0~3.6 V**（规格书表 5-2，见附录 F.4）。
也就是说：**电压跌破 2.51 V，硬件直接复位**，不由你决定，也不给你打日志的机会。

> ⚠️ **这个数字别从别的教程抄。** ESP32-C3 的档位是 2.51 / 2.64 / 2.76 / 2.92 / 3.10 / 3.27 V
> （`esp32c3/Kconfig.power`），而 **ESP32 的同名配置是 2.80 V**（`esp32/Kconfig.power`）。
> 同一份配置文件名字一样、数值不同——又是“芯片变了、教程没变”的一类。

#### 为什么这件事特别难查

**症状和软件 bug 一模一样。** brownout 复位、看门狗复位、栈溢出复位，从外面看都是“设备重启了”，
你没有任何直观线索能区分它们。

**更麻烦的是，电量百分比会主动误导你。** 第 1.5 节讲过：SOC 不是测出来的，
是 CW2017 按 **520 mAh profile 换算**出来的。它是一个**平均值**，
而电压跌落是**瞬时的**——

> **设备屏幕上可能还显示着 35%，电压已经在那一瞬间跌到 2.5 V 了。**

你一眼看到“还有电”，就理所当然地把供电排除了，然后去查栈、查看门狗，
查上好几天都查不到。

#### 什么操作最容易把它触发

| 操作 | 瞬时电流 | 出处 |
| --- | --- | --- |
| Wi-Fi 发射 | **335 mA** | 附录 F.2（规格书 §5.6） |
| 喇叭 / 功放出声 | 峰值拉电流 | 第 7 章 |
| 两者叠加 + 电池电量偏低 | 电池内阻变大，跌落更深 | — |

注意这三个**全都是本书正文里的高频场景**：第 10 章联网、第 10c 章 OTA、第 7 章音频、第 21 章放音。
所以这不是“偶发硬件问题”，而是**你在正常开发流程里就会撞上的**。

#### 怎么区分：看日志签名

三类复位在日志里留下的痕迹不同，这是最可靠的判据：

| 复位原因 | 日志里会出现 | 备注 |
| --- | --- | --- |
| 任务看门狗 | `Task watchdog got triggered` | 会列出卡住的任务名 |
| 栈溢出 | `Stack canary watchpoint triggered` | 会列出任务名 |
| 内存耗尽 | 分配失败 / `ESP_ERR_NO_MEM` | 通常先有一串失败日志 |
| **欠压（brownout）** | `Brownout detector was triggered` | **可能是乱码，也可能一行都没有** |

最后一行是关键：这行日志出自 `brownout.c:70`，用的是 `ESP_DRAM_LOGE`
（写进 DRAM 的日志，专为崩溃场景准备）。但**复位是硬件行为**——
串口波特率还没同步完就断电了，这一行**经常显示成乱码**，或者干脆来不及输出。

所以：**不要因为“日志里没看到 brownout 字样”就排除供电。**

#### 验证方法：换 USB 供电的对照实验

不需要万用表，也不需要示波器，成本最低、命中率最高的一招：

```text
1. 用电池供电，复现问题（记录 10 次里复现几次）
2. 插上 USB 供电，做完全相同的操作
3. 不复现了        → 物理层问题，别再查代码了
   照样复现        → 回到软件侧，继续查栈 / 看门狗 / 内存
```

**一次只改一个变量**（这是 22.3 那张表里已经立过的规矩），
改完供电如果还复现，再考虑温度、信号这些因素。

> **偶发问题的排查优先级**：换供电不复现 > 温度 > 软件。
> 「10 次里复现 1 次」和「100 次里复现 1 次」指向完全不同的原因——
> 后者高度怀疑供电与温度，而不是代码逻辑（见 22.5 方法四）。

## 22.4 15 条运行时红线

除了“出错了怎么查”，更重要的是“一开始就别写错”。
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
    **不要凭“芯片好像支持”去调**，需要时先改 BSP 并完成真机验证。
14. **射频与功耗只认真机实测**：扫描/广播 demo 通过 ≠ 联网可靠 ≠ 续航达标；
    低功耗电流必须用仪器测。
15. **二次开发必须重设计 UI**：不得把测试菜单 / `ui_pixel` 外壳改名沿用；
    BSP、LVGL 控件与并发模式可复用。

> 第 6 条和第 13 条值得单独记住，它们是两类最常见的错误根源：
> **抄了一个魔数**（改硬件时会静默失效），
> 和**假设了一个不存在的硬件能力**（怎么写都调不通）。

## 22.5 定位方法：从“现象”到“代码”

### 方法一：二分注释

嵌入式没有 debugger 时，这是最快的方法：

1. 把 `app_main` 里后半部分的初始化注释掉，看还崩不崩；
2. 逐步加回来，直到找到触发点。

### 方法二：最小化复现

把可疑逻辑抽成一个独立页面/命令，单独跑。
PokeWalk 项目甚至专门做了**串口注入按键**来自动走一遍所有页面：

> “串口注入按键——让整条链路能自动走一遍并逐页截图。
> 与截图通道是同一思路的两半：那个解决‘看不见屏幕’，这个解决‘按不了键’。”

### 方法三：把逻辑搬到 PC 上跑

这是官方推荐的做法：

> "Keep testable state machines, protocols, timing, and layout calculations
> independent from ESP-IDF/LVGL and cover them with host tests."

如果你的状态机不 `#include` 任何 IDF 头文件，
它就能在 PC 上用 gcc 编译、用 gdb 调试、写单元测试。
**这比在设备上二分注释快十倍。**

社区项目普遍有 `tests/` 目录：

```text
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
**只实现被测路径需要的行为**。这就是“桩件（stub）”。
有了它，连“demo 的 `stop()` 必须在超时内完成握手”这种运行时契约都能在电脑上验证。

**TDD-lite 节奏**（比“写完再调”快得多）：

1. 先分清哪些是纯逻辑（状态机、计算、协议解析）→ 写成独立 .c + 主机测试；
2. 再写一层薄薄的 BSP/LVGL 封装把逻辑接到硬件；
3. 每改一小块就跑主机测试（几秒一次反馈）；
4. 交付前跑完整门禁；
5. 真机按清单验收。

#### 实例：在电脑上验证“停止握手”这条运行时契约

`stop()` 有个很难在真机上测的分支：**worker 卡住时，它必须在超时后返回
`ESP_ERR_TIMEOUT`**，而不是假装成功（见第 21 章）。
真机上要触发它，得让 worker 真的卡 2 秒——慢，而且不稳定。

用桩件把“有没有收到确认”变成**可注入的输入**，这条分支在 PC 上就是一行开关：

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

为什么值得写这 40 行：真机上“带着后台任务切走页面”是个**偶发**故障——
可能切十次才复现一次，而且复现时你已经不记得改了什么。
在 PC 上它是**必现**的，每次改 `stop()` 都能立刻验证。

> 同样的思路也可以套在按键去抖、菜单导航（`demo_navigation.c` 就是官方的例子）、
> NVS 默认值降级、电量 `-1` 降级这些地方——**凡是“输入 → 分支”清晰的逻辑，都能下沉。**

### 方法五：偶发问题先取证，再动手

前面三个方法都是**定位到代码**的。但它们在一种情况下会全部失效：

> “可能切十次才复现一次，而且复现时你已经不记得改了什么。”

这类问题不能靠“再点几次试试”，要**先取证**。三条可执行的动作：

**① 记“复现频率”，不是只记“复现了”。**

「复现了」这个信息几乎没用。有用的是**比例**：

| 复现频率 | 通常指向 |
| --- | --- |
| 必现 | 逻辑错误——用方法一/二/三 |
| 10 次里 1 次 | 时序竞争、边界条件 |
| **100 次里 1 次** | **高度怀疑供电与温度**（22.3.1），不是代码逻辑 |

最后一行是关键：**越难复现，越该怀疑物理层**。
因为代码里的逻辑错误通常是确定性的，而电压跌落、温度升高是概率性的。

**② 一次只改一个条件。**

这和 22.3 那张表里“一次只改一个变量”是同一条规矩——
排查 CSS 式的“越改越乱”，往往就是因为同时动了两个条件：

```text
换 USB 供电（其他都不动）→ 看还复现吗
把设备挪到 AP 旁边       → 看还复现吗
换一台同型号设备         → 看还复现吗
```

**换供电是其中最便宜、命中率最高的一招**（22.3.1），不需要任何仪器。

**③ 偶发问题要挂长测，别靠手动点。**

手动点十次就下结论，样本量根本不够。
让设备**自己跑**：加上日志，让它循环执行可疑操作，跑一晚上，
第二天看日志里出现了几次、间隔多久、有没有规律。

> 一条经验：**偶发问题的答案通常在日志的“时间分布”里，不在单条日志的内容里。**
> 比如“总是隔 40 分钟左右来一次”，会直接指向定时器、看门狗或温度累积。

### 交付时按四段汇报

这是社区约定的汇报格式，目的是**不把“编译通过”说成“硬件通过”**：

```text
Build       : idf.py build 通过 / 镜像 xxxx KB
Host tests  : tests/ 下 N 个主机测试通过
Device tests: 真机验收矩阵 N 项中 M 项通过
Unverified  : 中文显示 / 续航 / ...（未上板确认的部分）
```

最后一段最重要。**诚实标注未验证的部分**，
比事后被人发现“其实没测”要好得多。

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

## 22.7 一个“先查这个”的顺序

设备出问题时，按这个顺序排除：

```text
0. 换 USB 供电还复现吗？    → 不复现：22.3.1 欠压，别再查代码了
1. 日志有没有输出？        → 没有：烧录/串口/供电问题
2. app_main 跑到了哪一行？  → 加日志定位
3. panic 是什么类型？       → 对照 22.2 的表
4. 最小可用内存是多少？     → < 20 KB 就是内存问题
5. 最近改了什么？           → git diff
```

**第 5 条看似废话，但在嵌入式开发里命中率极高。**

**第 0 条是特意放在最前面的。** 这块板是电池供电的可穿戴设备，
电压跌落导致的复位和软件 bug 表现一模一样，但**在代码里查不出来**——
先花 30 秒做一次对照实验，能省下几天的无效排查。

## 22.8 连日志都抓不到的时候

上面的顺序里有一步是“日志有没有输出”。**这一步本身失败时，整套调试方法就断了**——
没有日志，你连 `app_main` 跑到哪一行都不知道。而这件事在本板上会用一个很有迷惑性的方式失败。

### 症状：`ClearCommError failed`

用 Python（pyserial）自己抓串口时，满屏刷这个错：

```text
串口异常: ClearCommError failed (PermissionError(13, '设备不识别此命令。', None, 22))
```

端口**打得开**（设备管理器里 COM 口在、`list_ports` 也能列出 ESP32-C3），
但**一个字节的应用日志都读不出来**。这时不要怀疑脚本、也不要怀疑线材：
先看设备当前是不是**处于 deep sleep**。

**原因**：ESP32-C3 的“串口”不是独立 USB 转串口芯片，而是芯片内部的
**USB-Serial-JTAG 外设**。它在 SoC 内部，**deep sleep 时随 SoC 一起断电**。
USB 描述符可能还挂在总线上（所以 COM 口“在”），但设备已无法响应任何读命令。

```text
设备运行中   → USB-Serial-JTAG 有电 → monitor 正常
设备 deep sleep → SoC 断电           → COM 口在，但读命令全部失败
设备刚被硬复位 → USB 重新枚举中      → 端口短暂不可用
设备已关机     → 电池通路断开        → COM 口整个消失（设备管理器里都没有）
```

**另一种“端口没了”：硬件电源键。** 板子除了三个功能键，还有一个**独立的硬件电源开关**，
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
如果你的抓取脚本要在“设备可能还没醒”的时候启动，得让它具备断点重连能力：

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

> 关键点是“**异常记一笔就重试，而不是让它往上抛**”。
> 否则脚本在设备休眠期一上来就死掉，你永远等不到设备上电那一刻。

### 第二个可能：日志根本没从 USB 口出来

如果设备**明明在运行**（屏幕亮着、有声音），但 monitor 依然一个字节都没有，
那要查的是**控制台被路由到了哪里**。`sdkconfig` 里这几项决定日志出口：

```text
CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y     ← 想要走原生 USB
CONFIG_ESP_CONSOLE_UART=y                ← 想要走 UART0 引脚（TX 在 GPIO21！）
CONFIG_ESP_CONSOLE_UART_NUM=0
CONFIG_ESP_CONSOLE_UART_BAUDRATE=115200
```

本板**必须走 USB-Serial-JTAG**（第 3.2 节“坑 4”）：
UART0 的默认 TX 是 **GPIO21，和背光是同一个引脚**——把日志改回 UART0，
不只屏幕背光会出问题，你也读不到任何东西。

### 抓日志的可靠顺序

```text
1. 确认设备在运行（屏幕亮 / 有声音 / 按 RST 有反应）
   └─ 没反应 → 先上电唤醒，deep sleep 状态下串口是不存在的
2. 确认没有别的程序占着端口（idf.py monitor / 另一个串口助手 / WSL 转发）
3. esptool 能连上 ≠ 日志能读到
   └─ esptool 走的是 ROM 下载协议，SoC 休眠时它照样能复位芯片
4. 用 idf.py monitor 而不是自己写脚本（它已处理重连与解码）
   └─ 非要自写脚本，就按上面的"异常重试"写，别让异常终止脚本
```

> 这套现象容易误判成“脚本 bug”或“串口线坏了”，实际耗掉的时间远超它本身的价值。
> 记住一句：**端口在 ≠ SoC 在跑**。

## 22.9 真断点调试（JTAG，日志救不了的时候）

前面 22.1–22.8 全是“没有断点”的世界观。但这块板**真的能打断点**——
ESP32-C3 内置 USB-Serial-JTAG（GPIO18/19），一根 USB 线同时是串口和 JTAG。

**链路长这样**（四层，别被名字吓到）：

```text
VS Code  ──esp-gdb──▶  GDB 客户端
                        │ TCP :3333
                        ▼
                     OpenOCD  (openocd-esp32)
                        │ USB 序列口
                        ▼
                 ESP32-C3 内置 USB-Serial-JTAG  ──▶ 你的固件
```

- **esp-gdb / openocd-esp32** 是乐鑫维护的 GDB / OpenOCD 分支，ESP-IDF 已自带；
- OpenOCD 起来后会开三个端口：**3333** 给 GDB、**4444** telnet、**6666** TCL；
- 关键点：**固件必须编成 debug 模式**（默认就是，`-Og` 带 DWARF），
  而且**不能开编译器优化到看不见变量**。release 构建即使连上 JTAG 也看不到变量。

**上手步骤**（VS Code + ESP-IDF 扩展）：

1. `ESP-IDF: Select OpenOCD Board Configuration` → 选 **ESP32-C3 chip (via Built-in USB-JTAG)**
   （**不要**选 ESP32-S3；芯片不同，`/device found` 那一行的 part id 会对不上）；
2. `ESP-IDF: OpenOCD Manager` → `Start OpenOCD`，看到 `Listening on port 3333 for gdb connections`；
3. 在可疑那行按 **F9** 打断点；
4. **F5** 开始调试——会停在 `app_main` 第一行；
5. **F10** 逐过程（不进函数）、**F11** 步入、**Shift+F11** 跳出、
   **Shift+F5** 断开；
6. 右键断点 → 编辑断点 → 填 `i==6`，做**条件断点**（等循环到第 6 次再停）。

**左侧面板**能看变量、监视、调用堆栈、断点；**调试控制台**里直接敲变量名回车就能求值。
这比“加一串 `ESP_LOGI` 重新烧录”快一个数量级——**改一次代码要几十秒编译烧录，看一个变量是零成本**。

**四个必须知道的坑**：

| 坑 | 现象 | 怎么办 |
| --- | --- | --- |
| 芯片配置选错 | OpenOCD 报 `esp_usb_jtag: Device found` 失败 / 一直 `Examination failed` | 必须选 C3 那项；换 USB 线（要数据线） |
| deep sleep 打断点 | 设备睡着后 OpenOCD 失联、halt 超时 | 深睡会断电（第 22.8 节）；**调试时先禁用深睡** |
| 固件是 release | 连上了但变量全是 `<optimized out>` | 用 debug 构建，别开 `-O2`/`-Os` |
| USB 端口被占 | `LIBUSB_ERROR_NOT_FOUND` / 端口打开失败 | 关掉串口监视器、监视脚本、其它 OpenOCD 实例 |

> **什么时候值得用？** 出现“日志打到了但结果不对”“内存地址莫名被改写”
> “同一个 panic 复现不了”这三类问题时，日志已经到极限了——这时断点能直接看到
> “那个变量到底是什么值”。**但 99% 的问题（第 22.3 节那张表里的）用日志就够了**，
> 别为了调一个打印语句去折腾工具链。

**内置 JTAG 之外还有真 JTAG 管脚**：芯片本身把 JTAG 引到 GPIO4（MTMS）、
GPIO5（MTDI）、GPIO6（MTCK）、GPIO7（MTDO）——那是给“用外部 JTAG 调试器”留的。
本板这四根脚**已被外设占用**（表 2-7：GPIO4=I2S DIN、GPIO5=I2S BCLK、
GPIO6=I2S MCLK、GPIO7=I2C SCL），而且**根本不需要外部调试器**：
内置 USB-Serial-JTAG 就在 GPIO18/19 那根 USB 线上。你唯一的动作是
上面第 1 步把 OpenOCD 板型选对。（规格书 §2.3.4 / 附录 F.4）

> 📖 **延伸阅读**：[官方 JTAG 调试指南](https://docs.espressif.com/projects/esp-idf/zh_CN/v5.5.3/esp32c3/api-guides/jtag-debugging/index.html) ·
> [OpenOCD 故障排查](https://github.com/espressif/openocd-esp32/wiki/Troubleshooting-FAQ) ·
> [配置内置 JTAG](https://docs.espressif.com/projects/esp-idf/zh_CN/v5.5.3/esp32c3/api-guides/jtag-debugging/configure-builtin-jtag.html)

## 22.10 小结

- 日志是第一工具，**内存和栈的三个数字要常打**；
- **抓不到日志时先问“设备醒着吗”**——deep sleep 时 USB-Serial-JTAG 随 SoC 断电，
  端口在 ≠ SoC 在跑；日志出口必须保持 USB-Serial-JTAG，不能改回 UART0；
- panic 类型决定方向：LoadProhibited = 野指针，
  Stack protection = 栈溢出，watchdog = 不让出 CPU；
- 22.3 那张症状对照表值得打印贴墙；
- 定位靠二分注释 / 最小复现 / **搬到 PC 上跑**；
- **真断点不是做不到**：内置 USB-JTAG 走 OpenOCD，见 22.9——但别为调日志而折腾它；
- **编译通过 ≠ 硬件验证**。

> **延伸阅读 · 官方经验条目**（这两篇都是“真机才暴露”的排障实录）：
> [串口截屏协议](https://github.com/FoloToy/ai-passport/blob/main/docs/reference/y2lin/serial-screenshot-protocol.zh_CN.md) ·
> [音量计 UI 平滑与杂色块](https://github.com/FoloToy/ai-passport/blob/main/docs/reference/y2lin/meter-ui-smoothing-and-layout.zh_CN.md)
> （屏上杂色块的根因清单、LVGL 池耗尽导致开机白屏）
