# C. 术语表

给“会 C 但没做过嵌入式”的人准备的一份对照表。
按你在书里**大概什么时候会撞见**排序，不必一次读完。

## 平台与框架

| 术语 | 解释 |
| --- | --- |
| **ESP-IDF** | Espressif IoT Development Framework，乐鑫官方 C 开发框架（本书用 v5.5.3） |
| **FreeRTOS** | 实时操作系统内核：任务、队列、信号量、抢占式调度 |
| **BSP** | Board Support Package，板级支持包（本仓库 `components/bsp`，全部 `bsp_*` 函数） |
| **SoC** | 系统级芯片，这里指 ESP32-C3 |
| **Kconfig / sdkconfig** | 编译期开关体系；`CONFIG_XXX` 宏的来源（第 2.9 节） |
| **menuconfig** | 改这些开关的图形界面（`idf.py menuconfig`） |
| **组件 component** | ESP-IDF 的库单位；`main/` 和 `components/bsp/` 都是组件 |
| **managed_components** | 联网拉取的第三方组件（LVGL、esp_lvgl_port 等），**不要改** |

## 内存与存储

| 术语 | 解释 |
| --- | --- |
| **PSRAM** | 外接伪静态 RAM。**本设备没有**，这是全书最重要的约束 |
| **内部 RAM / SRAM** | 芯片自带约 400 KB；可用堆约 230 KB，最大连续块 < 8 KB |
| **largest free block** | 最大连续空闲块——**比“总空闲”更重要**，DMA 和大缓冲只看它 |
| **rodata** | 只读数据段；`const` 数组留在 Flash，**不占 RAM**（第 11 章纪律 6） |
| **Flash** | 断电不丢的存储器，本设备 8 MB；放固件与 `const` 数据 |
| **NVS** | Non-Volatile Storage，Flash 上的键值数据库（设置、计数），键名 ≤15 字符 |
| **分区表** | Flash 的“房型图”：bootloader / nvs / phy / app 各在哪、多大 |
| **factory 分区** | 默认应用所在分区（偏移 `0x10000`），官方默认约 7.9 MB |
| **bootloader** | 上电先跑、负责引导 app 的二级程序（`0x0`） |
| **full.bin** | bootloader + 分区表 + app 的合并镜像，`0x0` 整片烧 |
| **OTA** | 空中升级；需要 otadata + 两个 app 槽 + 回滚逻辑，**不是加个分区就算** |
| **MMU 页** | Flash 映射窗口，ESP32-C3 只有 128 个（mmap 用掉一个少一个） |

## 总线与外设

| 术语 | 解释 |
| --- | --- |
| **I2C** | 两线低速总线（SDA=10 / SCL=7，100 kHz），挂 ES8311 与 CW2017 |
| **I2S** | 数字音频总线（MCLK/BCLK/WS/DIN/DOUT），对接 codec |
| **SPI** | 高速串行总线，本板用于屏幕（80 MHz，无 MISO） |
| **codec** | 编解码芯片，本板为 ES8311（DAC + ADC，I2C 地址 0x18） |
| **DMA** | 直接内存访问；数据搬运不经 CPU，**操作会阻塞到传输完成** |
| **PCM** | 未压缩音频采样裸数据；本板基线 16 kHz / 16 bit / 单声道 |
| **采样率 / 位深** | 每秒采样数（Hz）/ 每样本位数；两者共同决定音频格式 |
| **ADC 分压** | 三个按键共用 GPIO0，靠不同电阻分出三档电压（第 1.3 节） |
| **PWM / LEDC** | 脉宽调光；背光 GPIO21 走 LEDC 5 kHz / 10-bit |
| **RTC_DATA_ATTR** | 深睡后仍然保留的变量修饰符（配合魔数区分冷启动） |

## 显示与字体

| 术语 | 解释 |
| --- | --- |
| **LVGL** | 轻量图形库，本工程 **9.5**（API 与网上大量 v8 教程不同） |
| **esp_lvgl_port** | LVGL 与 ESP-IDF 的粘合层（2.9.0）；提供任务、锁、显示接入 |
| **ST7789** | 屏幕驱动 IC；本板为 ST7789P3，**出厂 INVON 反色** |
| **RGB565** | 16 位像素格式（红 5 绿 6 蓝 5） |
| **swap_bytes** | LVGL 输出小端、ST7789 要大端；**由 port 统一处理，你别自己换** |
| **flush** | 把绘制缓冲推给屏幕的动作；BSP 在 `FLUSH_START` 里做圆角遮罩 |
| **脏区域 / 局部刷新** | 只重画变化的部分；无 PSRAM 下的必选项 |
| **绘制缓冲** | 40 行 × 240 宽 × 2 字节 ≈ **19.2 KB** 内部 RAM（单缓冲） |
| **LVGL 池** | LVGL 自己的静态内存池，`CONFIG_LV_MEM_SIZE_KILOBYTES=24` |
| **控件 / widget** | LVGL 的 UI 元素（label、image、obj…） |
| **bpp** | bits per pixel，字形抗锯齿位数（1 最省 Flash，4 更平滑） |
| **字库子集** | 只包含指定字符的字体文件，省 Flash（推荐方案） |
| **码点 codepoint** | 字符的 Unicode 编号；缺字检查必须按码点，不能“看一眼” |
| **fallback** | 字体回退链：主字体查不到的码点沿 `fallback` 指针继续查 |
| **placeholder** | 缺字占位符（`CONFIG_LV_USE_FONT_PLACEHOLDER`），保留它让问题可见 |
| **binfont** | LVGL 的二进制字体格式，可从内存 buffer 加载 |

## 并发

| 术语 | 解释 |
| --- | --- |
| **任务 task** | FreeRTOS 执行单元；栈大小**以字节计**，溢出会直接重启 |
| **句柄 handle** | 对象引用（`TaskHandle_t`、`QueueHandle_t`…） |
| **优先级** | 数字越大越优先。官方：LVGL=4、输入派发=5、慢活 worker=4 |
| **队列 Queue** | 任务间传消息的缓冲通道（按键事件用它） |
| **信号量 Semaphore** | 同步/互斥原语；本书最常用于“worker 已停止”的握手 |
| **任务通知 Notify** | 轻量 32 位任务间消息，比队列省资源 |
| **递归锁** | LVGL 的锁是递归的：同任务可重复加，跨任务互斥 |
| **栈水位线** | 任务历史上剩余栈的最小值，用来定栈大小 |
| **看门狗 WDT** | 检测任务饿死/死锁并复位的计时器 |
| **事件循环** | IDF 事件分发机制（Wi-Fi/IP 事件靠它） |
| **esp_timer** | 按键回调就跑在 button 组件的共享 esp_timer 任务里 |

## 无线

| 术语 | 解释 |
| --- | --- |
| **NimBLE** | BLE 协议栈实现（比 Bluedroid 省资源） |
| **BLE / GATT** | 低功耗蓝牙 / 通用属性配置（服务—特征值数据模型） |
| **GAP** | BLE 广播、连接、设备名相关协议层 |
| **peripheral / broadcaster** | 本板配置的 BLE 角色；**没有 central / observer，没有经典蓝牙** |
| **STA / AP** | Wi-Fi 站点模式（连路由器）/ 接入点模式（设备当热点，常用于配网） |
| **APSTA** | 同时开 AP 和 STA（配网时收密码 + 试连路由器）；比 AP-only 更吃资源 |
| **RSSI** | 信号强度（dBm，负数）；> -60 很好，-70 可用，< -80 别指望稳定 HTTPS |
| **DHCP** | 路由器给设备分配 IP 的服务；`IP_EVENT_STA_GOT_IP` 就是它完成的标志 |
| **2.4 GHz** | ESP32-C3 **只支持**这个频段；手机热点开 5 GHz 时设备搜不到（不是 bug） |
| **TLS / HTTPS** | 加密传输层 / 其上的 HTTP；握手是内存峰值，且**依赖系统时间** |
| **证书 / CA** | 证明“你连的服务器是真的”的凭据；可单证书嵌入或用证书包 |
| **证书包 crt bundle** | 内置一批公共 CA，能访问多数公网 HTTPS，代价是 Flash/RAM |
| **SNTP** | 网络授时；拿到 IP 之后才能用。**没校时先发 HTTPS 必然失败**（第 10c.2 节） |
| **配网 provisioning** | 把 Wi-Fi 密码交给设备的过程（第 10b 章） |
| **BLUFI** | 乐鑫的 BLE 配网协议；官方分支 `demo/blufi-provisioning`，配套小程序“蓝牙配网-FoloToy AI PASSPORT” |
| **SoftAP 配网** | 设备开热点 → 手机浏览器填表单；最灵活也最吃内存 |
| **captive portal** | 连上热点后自动弹配置页；靠通配 DNS + HTTP 重定向实现，兼容性要实测 |
| **SmartConfig** | 手机把密码编进 UDP 广播、设备抓包解出；依赖第三方 App，新项目很少用 |
| **PoP** | Proof of Possession，配网时证明“我有权限配这台设备”的口令（SECURITY_1） |
| **content-length = -1** | 分块传输（chunked）：响应没有声明长度，必须边收边处理 |
| **MQTT** | 轻量级发布/订阅消息协议；IDF 自带 `mqtt` 组件，适合长连接推送 |
| **WebSocket** | 双向长连接；v5.5.3 基础组件里没有，需加 `espressif/esp_websocket_client` |
| **keep-alive / 心跳** | 定期发包维持长连接，否则路由器会静默掉空闲连接 |
| **OTA** | 见“内存与存储”；**默认分区表没有 OTA 槽**，要自己改 |

## 工程与验证

| 术语 | 解释 |
| --- | --- |
| **门禁 gate** | 交付前必须通过的自动检查（`tools/validate.sh`） |
| **主机测试 host test** | 不需要设备、在电脑上 `cc` 编译跑的测试（第 22 章） |
| **桩件 stub** | 主机测试中替代硬件头文件/API 的精简实现 |
| **Build / Host / Device / Unverified** | 四段交付汇报格式；**编译通过只能写 Build: PASS** |
| **merge-bin** | 把分段镜像合成一个整片镜像（`full.bin`） |
| **esptool** | 烧录工具；v4.x 子命令用**下划线**（`write_flash`），idf.py 用连字符 |
| **EMBED_FILES** | 把文件编进固件，用 `_binary_xxx_start` 访问（第 9 章） |
| **mmap** | 把 Flash 映射到地址空间直接读；代价是 MMU 页，不是 RAM |

## 缩写速查

```text
BSP     板级支持包        NVS     非易失键值存储
LVGL    图形库            RTC     实时时钟/低功耗域
SoC     系统级芯片        DMA     直接内存访问
PSRAM   外接 RAM          PCM     裸音频采样
STA     Wi-Fi 站点        AP      接入点
WDT     看门狗            OTA     空中升级
bpp     每像素位数        cf      LVGL 图片的颜色格式字段
RSSI    信号强度          DHCP    自动分配 IP
SNTP    网络授时          TLS     传输层加密
BLUFI   BLE 配网协议      PoP     配网口令
```
