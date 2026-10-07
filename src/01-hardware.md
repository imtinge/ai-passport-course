# 1. 先看清这块板子

在写第一行代码之前，你需要把这块板子的物理事实装进脑子。
它们不是"背景知识"，而是**你每一个设计决策的约束条件**。

## 1.1 三个数字决定了全部玩法

| 项目 | 数值 | 它意味着什么 |
| --- | --- | --- |
| MCU | ESP32-C3，RISC-V 单核 160 MHz | 单核。`xTaskCreatePinnedToCore` 只能绑 core 0，别指望靠多核分摊 |
| SRAM | 约 400 KB，**无 PSRAM** | 可用堆实测约 230 KB；开机后**最大连续空闲块不到 8 KB** |
| Flash | 8 MB | 官方默认给 app 约 7.9 MB；社区项目常切成 3 MB 档位以留出素材/恢复分区 |

> "无 PSRAM"是本书第 11 章的全部内容，也是社区里绝大多数奇怪写法的根源。
> 现在先记住一个数字：**最大的一整块可用内存不到 8 KB**。

整屏 240×320 的 RGB565 画面需要 240 × 320 × 2 = **153,600 字节**。
这块板子拿不出这么大的连续内存——所以没有一个社区项目是用"整屏帧缓冲"来画画的。

## 1.2 屏幕

| 项目 | 值 |
| --- | --- |
| 驱动 | ST7789P3 |
| 分辨率 | 240 × 320，**竖屏** |
| 像素格式 | RGB565 |
| 接口 | 4 线 SPI（**只有 MOSI，没有 MISO**） |
| SPI 时钟 | 80 MHz（`BSP_LCD_PCLK_HZ`） |
| 复位 | 未接 MCU（`-1`），走软件复位 |
| 反色 | 出厂即需反色（`INVON`） |

官方 `bsp_pins.h` 里的定义（这是事实来源）：

```c
#define BSP_LCD_W            240
#define BSP_LCD_H            320
#define BSP_LCD_SPI_HOST     SPI2_HOST
#define BSP_LCD_MOSI         9
#define BSP_LCD_SCLK         8
#define BSP_LCD_CS           1
#define BSP_LCD_DC           20
#define BSP_LCD_RST          (-1)   // 未接 MCU，走 SWRESET 软复位
#define BSP_LCD_BL           21     // 背光，LEDC PWM 调光
#define BSP_LCD_PCLK_HZ      (80 * 1000 * 1000)
#define BSP_LCD_INVERT_COLOR 1      // 换屏后若呈负片，改成 0
```

**没有 MISO** 这件事有实际后果：**你读不回屏幕内容**。
所以 LVGL 必须自己维护绘制缓冲，也就没有"截图"这种低成本操作——
社区里做串口截图功能的仓库明确写了，截图要静态预留整屏内存，
这让它在没有 PSRAM 的板子上**和 BLE 联机无法共存**。

## 1.3 三个按键：一路 ADC 分压

这是最容易被误解的地方。三个键不是三个 GPIO，而是**一个 ADC 引脚 + 电阻分压**：

```
3.3V ── 外部上拉 10k ──┬── ADC 节点 (GPIO0 / ADC1_CH0)
                        └── 按键 ── 分压电阻 ── GND
```

| 按键 | 分压电阻 | ADC 电压 |
| --- | --- | --- |
| 上 | 0 Ω | 0 mV |
| 下 | 1 kΩ | ≈ 300 mV |
| 确定 | 2.2 kΩ | ≈ 595 mV |
| 松开 | 无通路 | 3300 mV |

BSP 里的判定窗口（边界取相邻两档的中点）：

```c
#define BSP_BTN_MV_TABLE  { {0, 150}, {150, 447}, {447, 1900} }
```

`bsp_pins.h` 里有一条很硬的警告，值得原样记住：

> ⚠ 不能改用**内部上拉**：约 45 kΩ 且精度差，会把三档全挤到 0~154 mV 并随温漂重叠。

这句话背后的意思是：**如果你换了分压电阻，必须重新标定**。
官方给的标定方法很实用——进 demo 的 Button 页，它会实时显示当前 ADC 电压，
你逐个按住三个键记下读数，取相邻两档的中点当作新边界。

判定时序同样写在 `bsp_pins.h` 里（注意它和组件默认值不同）：

```c
#define BSP_BTN_SHORT_PRESS_MS  180   // 短按（单击）判定窗口
#define BSP_BTN_LONG_PRESS_MS   500   // 长按触发时间
```

> 为什么长按是 500 ms 而不是组件默认的 1500 ms？源码注释写得很直白：
> "长按组件默认 1500 ms……在这台三键小设备上明显偏迟钝，收敛到 500 ms。"

## 1.4 I2C 与 I2S：两条总线上的三个芯片

**I2C（SDA=10，SCL=7）上挂两个设备：**

| 地址 | 芯片 | 作用 |
| --- | --- | --- |
| `0x18` | ES8311 | 音频 codec（播放 + 录音） |
| `0x63` | CW2017 | 电量计 |

**I2S 全双工（同端口，一 tx 一 rx，共用 MCLK/BCLK/WS）：**

```c
#define BSP_I2S_PORT         I2S_NUM_0
#define BSP_I2S_MCLK         6
#define BSP_I2S_BCLK         5
#define BSP_I2S_WS           3
#define BSP_I2S_DOUT         2     // 播放：MCU → codec
#define BSP_I2S_DIN          4     // 录音：codec → MCU
#define BSP_I2S_PA_CTRL      (-1)  // 功放使能脚未接 MCU（常通）
```

`BSP_I2S_PA_CTRL` 是 `-1` 这一点很重要：**你无法通过 GPIO 关掉功放**。
所以如果你想让设备安静（比如开机瞬间），只能去操作 codec 寄存器，
不能拉一个 GPIO。这也是为什么有的项目在 `app_main` 的第一行就调静音函数。

## 1.5 剩下三个容易想当然的接口

这三件事在芯片手册上"应该有"，但在这块板上有具体形态，值得单独确认一次。

**控制台**：固定用 **USB-Serial-JTAG**（GPIO18/19 原生 USB），**不是 UART0**。
这是第 3 章"坑 4"的根源——UART0 的默认 TX 正好是 GPIO21（背光），
一旦把日志改回 UART0，屏幕背光就会被串口数据闪成鬼畜。

**无线**：

| 项 | 事实 |
| --- | --- |
| Wi-Fi | 802.11 b/g/n，**2.4 GHz**，STA 模式（第 10 章） |
| BLE | BLE 5，协议栈是 **NimBLE** |
| BLE 角色 | **只有 peripheral / broadcaster**（做外设、做广播） |
| 经典蓝牙 | **没有**，别去找 A2DP / SPP |

**电量计**：CW2017 按 **BSP 内置的 520 mAh profile** 算 SOC%。
也就是说百分比是"按这个电池曲线换算出来的"，不是直接测出来的——
第 8 章会讲为什么它会返回 -1。

> 官方商品页标称电池 **500 mAh**，BSP profile 用的是 **520 mAh**
> （厂家为优特利 520 mAh 电芯生成的 80 字节 profile）。
> 这不是笔误：500 是商品页的标称容量，520 是电量计算 SOC 用的曲线容量。

I2C 总线还有一条不显眼但有用的参数：**标准模式 100 kHz**，
ES8311（0x18）和 CW2017（0x63）都挂在这条 100 kHz 的线上。
它决定了你别指望用 I2C 搬大量数据。

## 1.6 分区表：8 MB 怎么切

官方基线的默认分区表（`partitions.csv`）极简：

```csv
# Name,   Type, SubType, Offset,   Size,     Flags
nvs,      data, nvs,     0x9000,   0x6000,
phy_init, data, phy,     0xf000,   0x1000,
factory,  app,  factory, 0x10000,  0x7f0000,
```

- `nvs`：24 KB，键值对存储（WiFi 密码、你的应用设置）
- `phy_init`：4 KB，射频校准数据，**不要动**
- `factory`：约 7.9 MB，应用程序

官方的态度是：

> Keep the repository's default partition table minimal: NVS, PHY data, and
> one factory application spanning the rest of the 8 MB Flash.

但真实项目会按需要改。例如 PokeWalk 的分区表长这样（多了存档、卡 ID、recovery）：

```csv
nvs,          data, nvs,     0x9000,   0x6000,
phy_init,     data, phy,     0xf000,   0x1000,
factory,      app,  factory, 0x10000,  0x340000,
cardid,       data, nvs,     0x356000, 0x4000,
save_restore, data, 0x40,    0x360000, 0x10000,
wifi_config,  data, nvs,     0x370000, 0x6000,
recovery,     app,  test,    0x700000, 0x100000,
```

注意 `factory` 只有 `0x340000` ≈ 3.25 MB。PokeWalk 把它列为
"三条不能改的契约"之一（**app 上限 3 MB**），因为要在后面留 recovery 分区。

> ⚠️ **别把"某个项目的契约"当成"官方限制"。**
> 官方默认给的是 7.9 MB；3 MB 是 PokeWalk 为了塞 recovery 自己定的。
> 实测基线 app 镜像约 **1,524,336 字节**（1.45 MB），
> 加上素材后到 3 MB 量级是很常见的——**按你自己的容量账来定**。

> ⚠️ **还要区分"开源基线"和"出厂固件"。**
> 上面这张三行表是**开源仓库 `folotoy/ai-passport` 的 `main` 分支**当前的样子。
> 你手上那台设备出厂时跑的是**产品固件**，它的布局不一样——有 `cardid` 保护分区、
> 有 `0x700000` 的 recovery（上键长按 5 秒进入，可通过 BLE 重装固件）。
> 网上的第三方实测贴常常把"出厂固件 / 某个 fork"的分区表当成官方基线来介绍，
> 于是你会看到"Factory 3 MB + recovery"被写成通例。**判据很简单：
> 打开你自己 clone 的 `partitions.csv` 看一眼。**
> 两套的完整对照见[附录 E.5](E-official-resources.md#e5-先分清你面对的是出厂固件还是开源基线)。

第 9 章会详细讲分区表怎么改。

## 1.7 硬件事实的边界：别把"没验证"当成"有"

社区里有一个 fork 的 README 写了这么一段（这是**该 fork 的自述**，不是官方声明，
但它提醒了一件很重要的事）：

> 仓库目前没有足够证据保证以下能力：触摸、屏幕读回、IMU、外部存储、充电控制、
> USB 插拔检测、可控功放使能、深度睡眠唤醒、任意"空闲 GPIO"、电池精确容量或
> 量产级电源指标。**ESP32-C3 芯片具备某项功能，不代表这块板已经接出、供电正确或经过验证。**

最后一句是本章最该记住的一句话。

芯片手册上写着 ESP32-C3 支持 USB、支持触摸、支持深度睡眠——
但这块板子**有没有把对应的引脚和电路做出来**，是另一回事。
写功能之前先确认它在这块板上真实存在过。

### 官方口径的"没有"

上面那份清单是 fork 的自述。官方的运行时规约里也有一句对应的话，
可以直接当作**这块板的能力黑名单**：

> 本板没有 LCD MISO / 触摸 / TE、没有功放使能脚（常通）、没有经典蓝牙；
> 不要凭"芯片好像支持"去调，需要时先改 BSP 并完成真机验证。

对照第 1.2 节（没有 MISO）和第 1.4 节（`BSP_I2S_PA_CTRL` 是 `-1`）——
**这两条在硬件定义里就能直接看到**，不需要猜。

## 1.8 小结

- 单核 160 MHz，约 400 KB SRAM，**无 PSRAM**，8 MB Flash；
- 240×320 竖屏 SPI，**没有 MISO，读不回画面**；
- 三键是**一路 ADC 分压**（0 / 300 / 595 mV），换电阻必须重新标定；
- I2C（100 kHz）上挂 ES8311（音频）和 CW2017（电量）；I2S 全双工；功放**无法通过 GPIO 控制**；
- 控制台是 **USB-Serial-JTAG**，不是 UART0；BLE 只有 **NimBLE 外设/广播**，**没有经典蓝牙**；
- 硬件事实以 `bsp_pins.h` 为准；**芯片支持 ≠ 板子接出来了**。

下一章去补 ESP-IDF 的基础——用你已经会的 C 知识去类比，不堆概念。
