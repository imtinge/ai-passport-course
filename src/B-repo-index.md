# B. 代表仓库索引

本书拆解的 5 个仓库，加上官方基线。

## B.1 五个实战仓库

| # | 仓库 | 下载量 | GitHub | 学什么 |
|---:|---|---:|---|---|
| 1 | `FoloToy/folo-ai-passport-xiaozhi` | 7244 | `github.com/FoloToy/folo-ai-passport-xiaozhi` | 单线程事件循环架构、Board 抽象、IDF 6 |
| 2 | `Luobata/ESP32-PokemonGo` | 2725 | `github.com/Luobata/ESP32-PokemonGo` | 后台世界任务、存档、开机自检、recovery |
| 5 | `Shinku-Chen/ai-passport` | 2299 | `github.com/Shinku-Chen/ai-passport` | 一仓多玩法（11 条 feature 分支）、音频播放、SPIFFS |
| 8 | `pax-zhang/ai-passport` | 1101 | `github.com/pax-zhang/ai-passport` | **页面栈架构**、18 步启动模板、扩展 BSP |
| 18 | `YeatsLiao/ai-passport-doom` | 511 | `github.com/YeatsLiao/ai-passport-doom` | 最小的可跑项目、分条刷屏、--wrap 技巧 |

**官方基线**（不在排名里，但是一切的基础）：

| 仓库 | GitHub | 说明 |
|---|---|---|
| `folotoy/ai-passport` | `github.com/folotoy/ai-passport` | BSP 与 demo 的源头，`bsp_pins.h` 在这里 |

> 上面表格里的 `GitHub` 列是**可直接 clone 的地址**，读者照抄即可。
> 作者本机为了批量扫描，把这些仓库镜像在 `D:\passport\<平台>\X__Y` 下
>（`__` 是平台名与仓库名之间的分隔），那套本地路径**不在书上、也不该出现在你的机器**。

### 官方收录的应用档案（找灵感的第一站）

官方 `docs/reference/<用户名>/<应用名>/` 下还归档了 **10 个成品应用**。
它们和 B.1 的定位不同：不是"能 clone 的仓库"，而是**带设计说明的成品档案**
（纯文本，不存固件 `.bin`）。**找灵感、看别人怎么拆解需求时先看这里。**

| 应用 | 形态 / 规模 | 值得看的点 |
| --- | --- | --- |
| [音效钥匙扣](https://github.com/FoloToy/ai-passport/blob/main/docs/reference/shinku-chen/voice-keychain/README.zh_CN.md) | 口袋音频播放器 | 音频播放应用的完整形态（第 15 章的原型） |
| [今天吃啥](https://github.com/FoloToy/ai-passport/blob/main/docs/reference/shinku-chen/eat-what/README.zh_CN.md) | 按键驱动的食物轮盘 | 最小玩法：三键如何撑起一个完整交互 |
| [四子棋](https://github.com/FoloToy/ai-passport/blob/main/docs/reference/shinku-chen/connect-four/README.zh_CN.md) | 横屏 10×7、三档 AI、双人、空闲自动深睡 | 横屏 + 对弈 AI + 深睡三件事一起做 |
| [飞鸟会长不肯认输](https://github.com/FoloToy/ai-passport/blob/main/docs/reference/shinku-chen/asunabi/README.zh_CN.md) | 竖屏视觉小说，30 章、六存档位、选章、自动阅读 | 竖屏阅读器骨架 |
| [沙耶之歌](https://github.com/FoloToy/ai-passport/blob/main/docs/reference/shinku-chen/saya-no-uta/README.zh_CN.md) | 横屏，44 章 / 3,828 段对白 / 3 结局 | 全程离线的大文本组织 |
| [亚托莉阅读器](https://github.com/FoloToy/ai-passport/blob/main/docs/reference/shinku-chen/atri-reader/README.zh_CN.md) | 竖屏，34 章 / 1,069 幕 / 12,188 句 | 立绘跟随说话人、多结局分支 |
| [星空列车与白的旅行](https://github.com/FoloToy/ai-passport/blob/main/docs/reference/shinku-chen/starry-sky-railroad/README.zh_CN.md) | 竖屏，39 章同人移植剧本 | 换场景自动存档 |
| [千恋＊万花](https://github.com/FoloToy/ai-passport/blob/main/docs/reference/shinku-chen/senren-banka/README.zh_CN.md) | 竖屏，背景 + 立绘 + 事件插图 | 自动阅读 / 快进 / 跳章 / 多档存档 |
| [魔女的夜宴](https://github.com/FoloToy/ai-passport/blob/main/docs/reference/shinku-chen/sanoba-witch/README.zh_CN.md) | 竖屏，101 章、五线五结局全装进 Flash | **极限容量**：全部素材塞进分区 |
| [离线宝可梦图鉴](https://github.com/FoloToy/ai-passport/blob/main/docs/reference/sunny0826/offline-pokedex/README.zh_CN.md) | 1025 只 + 精灵 + 叫声内嵌，全离线 | 大规模只读素材的索引与检索 |

> 视觉小说这一族反复出现的工程主题是"**剧本包预算**"——
> 5.06 MB 压到 1.45 MB，块大小由**最大连续块 7.7 KB** 而非空闲堆决定。
> 详见第 9 章与第 11 章，官方条目在
> [`vn-script-pack-budget-and-failure-modes`](https://github.com/FoloToy/ai-passport/blob/main/docs/reference/shinku-chen/vn-script-pack-budget-and-failure-modes.zh_CN.md)。

## B.2 五个仓库的一张对照表

| | DOOM(#18) | pax-zhang(#8) | Shinku(#5) | PokeWalk(#2) | 小智(#1) |
|---|---|---|---|---|---|
| 语言 | C | C | C | C | **C++** |
| `main/` 位置 | 顶层 | 顶层 | 顶层 | **`firmware/`** | 顶层 |
| 源文件数 / 行数 | 1 / 80 | 36 / 12630 | 12 / 1715 | 67 / 17265 | 8 .cc / 3625（+47） |
| `components/bsp` | ❌（`bsp_doom`） | ✅ | ✅ | ✅ | ❌（自己的 `boards/`） |
| `partitions.csv` | ✅ | ✅ | ✅ | ✅ | ❌（`partitions/v2/`） |
| LVGL | **❌ 完全不用** | ✅ | ✅ | ✅ | ✅ (9.5) |
| IDF | 5.5.3+ | 5.5.3 | 5.5.3 | 5.5.3 | **≥6.0.1** |
| 素材存储 | 自定义分区 + mmap | NVS + EMBED 证书 | NVS / SPIFFS `voicefs` | NVS + EMBED（7 bin） | assets 分区 + mmap |
| 音频 | **禁用** | 播放 + 录音 | Opus 播放 | sfx/music/cry | Opus + 唤醒词 |
| 深睡 | ❌ | GPIO 唤醒 | ✅ `esp_deep_sleep_start` | 只查唤醒原因 | 未在主流程用 |
| 构建 | `idf.py build` | `idf.py build` | `validate.sh` | `fw.sh build` | `scripts/build.py` |
| 本书章节 | 13 | 14 | 15 | 16 | 17 |

## B.3 按"我想学什么"找仓库

| 你想做 | 去看 |
| --- | --- |
| 第一个能读懂的项目 | #18 DOOM（第 13 章） |
| 一个设备装多个玩法 | #8 pax-zhang 页面栈（第 14 章） |
| 播音效 / 语音 | #5 Shinku `feature/voice-keychain`（第 15 章） |
| 后台任务与存档 | #2 PokeWalk `world.c` / `save.c`（第 16 章） |
| AI 语音对话 | #1 小智（第 17 章） |
| 裸屏直推（不用 LVGL） | #18 DOOM `components/bsp_doom` |
| OTA 升级 | #1 小智 `partitions/v2/16m_c3.csv` |
| 自定义 bootloader / recovery | #2 PokeWalk `bootloader_components/` |
| 中文字体接入 | #8 pax-zhang `main/fonts/` |
| PC 侧素材处理管线 | #5 Shinku `tools/encode_voice.py`、#2 PokeWalk `tools/` |
| 主机端单元测试 | 官方基线 `tests/` |

## B.4 怎么读一个陌生仓库（5 步）

1. **读 README 的硬件/契约部分**——先知道它假设什么；
2. **`ls main/`**——看文件命名规律（有没有 `app_*.c`/`play_*.c` 的分组）；
3. **找 `app_main`**——`grep -rn "void app_main" main/`，读它的初始化顺序；
4. **找最大的文件**——领域逻辑通常在那里；
5. **读 `partitions.csv` 和 `sdkconfig.defaults`**——知道它的资源边界。

**不要从上往下通读。** 一个 17000 行的项目是无法通读的，
但你能用这 5 步在 20 分钟内知道它的骨架。

## B.5 使用社区的规矩

- **只提取需要的模式，不要把整个分支合并进来**——
  官方明确要求避免带入旧 BSP 和旧配置；
- **优先复用 `components/bsp/` 里的 `bsp_*` API**，不要重写驱动；
- **必须重新设计 UI**，不能沿用官方 demo 的外壳（第 20.2 节）；
- 引用别人的代码时保留出处。

## B.6 数据说明

本书中的统计数字来自**作者本地扫描**（截至 2026-10-05，来源：玩法社区公开数据，
非官方；路径以作者本机为准，读者无法复现同一路径）：**172 个仓库**样本。

- 平台分布：GitHub 155 / CNB 9 / Gitee 6 / GitCode 2
  （注意：样本中 CNB 只有 9 个，但**实际生态里 CNB 托管约 31 个**；本书样本偏重 GitHub，
  上面的比例不能当生态全景。）
- 126 位作者，328 个玩法条目
- 73,484 个受版本控制文件，单仓文件数中位数 **181**
- `components/bsp` 采用率 83%，自定义分区表 87%，`AGENTS.md` 70%
- 明示 IDF 版本的 110 个仓库里：5.5 有 105 个，6.x 只有 4 个

> **仓库可达性（截至 2026-10-05）**：玩法社区共 **334** 个带仓库链接的玩法，
> 对应 **239** 个有效仓库；其中约 **6** 个已 404 失效，例如
> `suikay/snack-rush`（零食冲刺）、`CoderSu/easy-go-home`（公路之王）。
> 书里引导你去社区找仓库时，遇到失效链接先换关键词或看 fork，能省时间。

全量清单在作者本地技能目录（`_仓库总索引.csv`、`reference-apps.md`）——
那是作者的工作素材，**不随本书发布**；上面这些聚合数字才是本书划定的范围。

---

## B.7 如果你不想写 C：MicroPython 路线

本书从头到尾讲的是 **C + ESP-IDF**，那是官方主线（`folotoy/ai-passport`）的做法。
但官方还有**第二个仓库**：

```bash
git clone --recursive https://github.com/FoloToy/ai-passport-micropython
```

它是 **AI Passport 的 MicroPython 固件与开发工作区**——同一块 ESP32-C3 板，
刷一个预编译好的 MicroPython 固件，然后**用 Python 写 `main.py`**。
官方给它的定位写得很直白：**没有编程基础的人**用一句话把想法说给 AI，
回答几个简单问题，就能变成一个能跑的可穿戴应用。

> 仓库是 MicroPython 的一个 board port（`ports/esp32/boards/FOLOTOY_AI_PASSPORT/`），
> 不是从零造的解释器；许可跟随上游 MicroPython。它自带完整的 MicroPython 源码，
> 所以仓库很大（超过 50 MB），clone 时记得 `--recursive` 带子模块。

**先说结论，免得你走错路：**

- **本书第 1、4 章的板级事实（引脚、时钟、I²C 地址）在这里完全通用**，一个数字都不用改；
- **内存和深睡比 C 版更紧、更简陋**，本书第 11、8 章的约束在这里只会更严重；
- 想做产品级低功耗、要改分区/I²S MCLK/LVGL 内部 → **还是得回到 C**。

### B.7.1 两条路线的分界

官方把开发明确分成两条，判定标准只有一句：
**你要动的东西，Python 层够不够得着？**

| | 用户脚本（**默认**） | 自定义固件（高级） |
| --- | --- | --- |
| 适用 | 新页面、游戏、交互、音效、电池显示、Wi-Fi、BLE | 新 C API、I²S MCLK、LVGL 内部、驱动、启动流程、内存布局、分区 |
| 动作 | 保留官方固件，只替换 `/main.py` | 用 ESP-IDF 5.5.3 重新构建整个固件 |
| 命令 | `python -m pip install --upgrade mpremote esptool`<br>`tools/upload_main.sh ./main.py` | `tools/build_default_firmware.sh`<br>`tools/flash_firmware.sh ports/esp32/build-FOLOTOY_AI_PASSPORT-merged.bin` |
| 迭代速度 | 改一行、传一次、复位就跑 | 每次都是完整固件构建 |
| Windows | 脚本上传与串口测试**原生完全支持** | **必须用 WSL2 Ubuntu**（官方明确要求） |

`/main.py` 存在时**优先于**固件内置的冻结示例执行；用户文件放在 FAT 分区。
`tools/remove_user_main.sh` 可恢复内置示例。

> **USB 不是 U 盘。** ESP32-C3 提供的是 USB Serial/JTAG（GPIO18/19），
> 不是 USB OTG 大容量存储——**不能拖拽拷贝**，一切上传走 `mpremote`。
> 这一点官方在 `AGENTS.md` 里专门写了"不要承诺拖拽 U 盘模式"。

### B.7.2 引脚事实通用：本书的数字照抄

这是 MicroPython 路线最省事的地方——**同一块板，引脚一个都没变**。
官方 `AGENTS.md` 的 Hardware facts 与本书 `bsp_pins.h` 逐条对齐：

| | C 版（本书第 1/4 章） | MicroPython 版 |
| --- | --- | --- |
| MCU | ESP32-C3、8 MB flash、**无 PSRAM** | 同 |
| LCD | SPI2，SCLK 8 / MOSI 9 / CS 1 / DC 20 / BL 21，240×320 RGB565 | 同（MicroPython `SPI(1)` 即 ESP-IDF SPI2） |
| I²C | SCL 7 / SDA 10；ES8311 `0x18`、CW2017 `0x63` | 同 |
| I²S | MCLK 6 / BCLK 5 / WS 3 / DOUT 2 / DIN 4 | 同 |
| 按键 | GPIO0 电阻阶梯 ADC | 同，**连判定窗口都注明"与 `BSP_BTN_MV_TABLE` 保持一致"** |
| 音频默认 | 16 kHz / 16 bit / 单声道 | `codec.configure_slave(16000, 16)` + `I2S.MONO` |
| 电量算法 | SOC 取 `0x04` 高字节；VCELL `0x02` & `0x3FFF`，`×312.5 µV` | **完全一致**，见下方代码 |

MicroPython 版的单一事实源是
`ports/esp32/boards/FOLOTOY_AI_PASSPORT/mpconfigboard.h`，
官方同样警告：**不要从网上的例子猜引脚**。

内置冻结示例还是**同样的 7 页**——Display / Button / Audio / Battery /
Wi-Fi / BLE / Low Power，正是本书第 24–31 章逐个拆解的那 7 个硬件测试 demo。
所以你可以把它当成"同一套硬件事实的 Python 版注解"来读。

### B.7.3 模块地图与最小骨架

固件里可用的模块：`machine`（Pin / PWM / ADC / I²C / I2S / SPI / Timer / RTC / WDT）、
`network`、`bluetooth`、`lvgl`、`st7789`、`lvgl_st7789`、`es8311`。

下面这段是**板级初始化的最小骨架**，可以和本书第 4、5、6 章的 C 版对照看：

```python
from machine import ADC, I2C, I2S, PWM, Pin, Timer
import lvgl as lv
from lvgl_st7789 import ST7789LVGL

display = ST7789LVGL(buffer_lines=32)        # 默认其实是 40，示例主动降到 32
adc     = ADC(Pin(0))                        # 三键电阻阶梯
adc.atten(ADC.ATTN_11DB)
i2c     = I2C(0, scl=Pin(7), sda=Pin(10), freq=400_000)   # ES8311 + CW2017 共用
bl      = PWM(Pin(21), freq=5000, duty_u16=65535)         # 背光，5 kHz
```

常见的 MicroPython ESP32 端 API（`docs.micropython.org` 的 ESP32 quickref），
按本书的用法挑几条最相关的：

```python
import machine, esp32, network

machine.freq()                      # 读/写 CPU 频率
machine.reset_cause() == machine.DEEPSLEEP_RESET   # 判断是否深睡唤醒
machine.lightsleep(2000)            # light sleep，毫秒
machine.deepsleep(5000)             # deep sleep，毫秒；不带参数 = 无限期
esp32.mcu_temperature()             # C3 上返回摄氏度

adc.read_uv()                       # 推荐用这个读电压，而不是 read_u16()
pwm.freq(5000); pwm.duty_u16(32768) # duty 是 0–65535；频率越高分辨率越低

wlan = network.WLAN(network.STA_IF)
wlan.active(True); wlan.connect('ssid', 'key')
wlan.config(reconnects=3)           # ★ 默认是"永远重试"，见下
```

> **★ `wlan.config(reconnects=n)` 这条要特别记**：MicroPython 的 WLAN
> **默认会无限重连**，即使密码错误或 AP 不在范围内也一直试，
> 期间 `wlan.status()` 一直是 `STAT_CONNECTING`。
> 这正是本书第 10 章"密码错这类确定性失败不该狂连"要治的病——
> 在 Python 侧，`reconnects=0` 就是不重试，`-1` 恢复默认。

### B.7.4 更紧的地方：内存、深睡、按键、中文

这是 MicroPython 路线**真正要小心**的部分，也是它与 C 版的差距所在。

**① 内存（本书第 11 章的约束在这里更严重）**

同样是 400 KB SRAM、无 PSRAM，但解释器本身还要占一份。
内置示例的注释直接写明了后果：

```python
# Stream a small repeating chunk instead of allocating a full
# second of PCM, which can fail with ENOMEM beside LVGL buffers.
sample = bytearray(1024)
```

对应纪律：

- 录音缓冲区**分块处理**，别一次 `bytearray(几万)`（示例录 2 秒是 64 KB，前面先 `gc.collect()`）；
- 绘制缓冲可以调：模块默认 `buffer_lines=40`（**与 C 版的 40 行一致**），
  内置示例主动降到 **32** 省内存——这是你可以拧的旋钮；
- 不确定就 `import gc; gc.collect()` 再看 `gc.mem_free()`。

**② 深睡（比 C 版简化很多，是最大的差距）**

内置示例的 `_prepare_sleep_peripherals()` 只做了四件事：
停 BLE 扫描 → `WLAN.active(False)` → `ES8311.sleep()` → `panel.sleep()` + 背光置 0，
然后 `machine.deepsleep(5000)`。

**对比本书 8.4 节那套官方 C 版契约，它缺了：**

- CW2017 睡眠写入 + 5 ms 回读重试；
- ES8311 六个寄存器回读校验；
- I2S / I²C 引脚释放为"关闭上下拉的输入"；
- LCD 的 deep-sleep hold 与安全电平。

所以**待机电流会明显高于 C 版**。真要做低功耗产品，这几步得自己补。
能用的工具是 MicroPython 侧的 pad hold：

```python
from machine import Pin, deepsleep
import esp32

pin = Pin(2, Pin.IN, Pin.PULL_UP)
pin.init(pull=None)                    # 睡前进掉上下拉，避免漏电
esp32.gpio_deep_sleep_hold(True)       # 让非 RTC 引脚在深睡期间保持配置
deepsleep(10000)
```

> 上面 `hold` / `gpio_deep_sleep_hold` 是 MicroPython 通用 API，
> **在 C3 上的具体行为要实测**——官方文档的引脚举例（如 GPIO19/21）来自 ESP32 经典款，
> 不能直接套到本板。

**③ 按键：用硬件 Timer，不要用 LVGL timer**

内置示例用 `Timer(1)` 以 70 ms 周期轮询 ADC，再用 `micropython.schedule()` 把
Python 处理踢出中断上下文，注释解释了原因：
**用 LVGL timer 会让输入依赖 LVGL 回调桥，在某些构建上会静默丢按键。**

这就是本书 6.4 节"回调只入队"的 Python 版对应物——
慢活（录音、播放、扫描、网络请求）一律开 `_thread` 工作线程，
再用 `micropython.schedule()` 回到主线程更新 UI。

**④ 中文仍是字体任务**

默认 ASCII 字体**不能**显示中文，官方明确要求"确认所选字体包含每一个字形"。
而且 LVGL 绑定的默认字体是**配置相关**的，内置示例显式固定字号避免行高乱跳：

```python
font = getattr(lv, "font_montserrat_%d" % size, None)
obj.set_style_text_font(font, 0)
```

本书第 19 章的缺字检查（`lv_font_get_glyph_dsc()` + `is_placeholder`）
在这里**一样要做**，只是换成 Python 侧调用。

**⑤ 电量是"自己读寄存器"，而且比 C 版简单**

```python
soc_raw   = int.from_bytes(i2c.readfrom_mem(0x63, 0x04, 2), "big")
vcell_raw = int.from_bytes(i2c.readfrom_mem(0x63, 0x02, 2), "big") & 0x3FFF
mv  = (vcell_raw * 3125) // 10000        # 312.5 uV/LSB，整数运算
soc = max(0, min(100, soc_raw // 256))   # 取高字节
```

算法**和本书 8.1 节讲的完全一致**；差别是它没有 C 版那套
80 字节 profile 加载与"SOC > 100 返回 -1"的校验，只是简单地 clamp 到 0–100。
异常时返回 `(None, None)`，界面显示 `--%`——
**这正好是本书 8.1 节说的"优雅降级"和"首帧不要虚构百分比"**。

### B.7.5 工作流：一句话 → main.py → 真机

官方把这套流程整个写给了 AI（`docs/ai-workflow.md` + `requirements-template.md`），
八个问题依次问：做什么 → 开机显示什么 → 三个键分别做什么 → 屏幕上有什么（要中文吗）
→ 要不要声音 → 要不要联网 → 要不要电量/多久休眠 → **做到什么现象算完成**。

```bash
# 1. 环境（Python 3.10+）
python -m pip install --upgrade mpremote esptool

# 2. 确认连通（Windows 用 COMx，Linux 通常 /dev/ttyACM0）
python -m mpremote connect COM3 exec "print('MicroPython ready')"

# 3. 上传并复位
tools/upload_main.sh ./main.py
python -m mpremote connect COM3 reset

# 4. 回到内置示例
tools/remove_user_main.sh
```

Windows 找不到 `python` 时用 `py -m`；端口也可以用环境变量固定：
`$env:AI_PASSPORT_PORT = "COM3"`。

**两条和 C 版完全一样的铁律**：

1. **不许照抄硬件测试菜单当产品 UI**——内置 7 页只是学习参考，
   "改名换色"不算完成（本书 4.9 节第 5 条、E.4 节）；
2. **交付四段分开写**：`Build / Host tests / Device tests / Unverified`，
   **编译通过 ≠ 硬件验证通过**（本书 4.9 节配套约定）。

发布：打 `v*` tag 推上去，GitHub Actions 自动构建板级固件、
生成从 `0x0` 烧录的合并镜像与 SHA-256 校验和，挂到 Release。

### B.7.6 什么时候还是要用 C

遇到下面任意一条，就别在 Python 层硬撑了，回本书的主线：

- 要做**产品级低功耗**（需要 CW2017 睡眠、引脚释放、LCD hold 那套完整契约）；
- 要改**分区表 / I²S MCLK / LVGL 内部 / 启动流程 / 内存布局**；
- 要写新的 **C 驱动或 BSP API**；
- 内存已经卡到 `gc.collect()` 也救不回来；
- 需要 **OTA**（本书 10c.9 节：默认分区表没有 OTA 槽，MicroPython 侧同样要改分区）。

### B.7.7 本书章节 → MicroPython 对照表

| 本书章节 | C 版做法 | MicroPython 对应 |
| --- | --- | --- |
| 1 / 4 硬件与 BSP | `bsp_pins.h` | `mpconfigboard.h`，**数字通用** |
| 5 显示与 LVGL | `bsp_display_*` + `esp_lvgl_port` | `lvgl` + `lvgl_st7789.ST7789LVGL` |
| 6 按键 | ADC + 回调入队 | `ADC(Pin(0))` + `Timer` 轮询 + `micropython.schedule` |
| 7 音频 | `bsp_audio_*` + `esp_codec_dev` | `es8311.ES8311` + `machine.I2S` |
| 8 电量与深睡 | `bsp_battery_*` + 五步深睡契约 | 直接 `i2c.readfrom_mem(0x63,...)` + `machine.deepsleep()`（**更简**） |
| 10 / 10b / 10c 联网 | `esp_wifi` + `esp_http_client` | `network.WLAN`（**注意默认无限重连**） |
| 11 内存 | `heap_caps_get_largest_free_block()` | `gc.mem_free()`；**约束更紧** |
| 12 并发 | FreeRTOS 任务 + 停止握手 | `_thread` + `micropython.schedule()` |
| 19 中文字体 | lv_font_conv 子集 + 缺字检查 | 同样要做；显式 `set_style_text_font()` |
| 30 BLE | NimBLE host 任务所有权 | `bluetooth.BLE()` |

> 一句话选型：**想快速做出能玩的东西 → MicroPython；
> 想把它做成省电、可控、能长期维护的产品 → C。**
> 两者的板级事实是同一套，所以你在本书学到的"为什么"，
> 在 Python 侧一个字都不用改。
