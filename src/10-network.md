# 10. 联网：Wi-Fi 全生命周期

> **可抄代码**：[D.10 Wi-Fi](D-module-cookbook.md#d10-wi-fi) · [D.11 BLE](D-module-cookbook.md#d11-ble) · [`snippets/08_wifi_sta_connect.c`](https://github.com/imtinge/ai-passport-course/tree/main/snippets)。
>
> **配套章节**：拿到网之后怎么用 → [10b 配网](10b-provisioning.md)（密码怎么进设备）、
> [10c 获取网络数据](10c-network-data.md)（HTTP / HTTPS / 长连接 / OTA）。

联网是 AI Passport 上最“重”的能力。它耗电、占内存、有失败可能，
而且**失败是常态**——设备会离开 WiFi 范围、密码会变、路由器会重启、手机热点会睡。

本章只回答一件事：**射频怎么起来、怎么知道连上了、断了怎么办。**

---

## 10.0 先决策：你的玩法真的需要联网吗

联网不是默认项。官方 `main` 的 Wi-Fi demo **只扫描、不连接**（第 29 章），
正是因为联网会一次性付出内存、功耗、复杂度和“失败要兜底”的成本。

| 你的玩法 | 需要联网吗 | 说明 |
| --- | --- | --- |
| 本地小游戏、图鉴、计时器 | **不需要** | 别为了“以后可能用”先开 Wi-Fi |
| 天气 / 行情 / 日历 | 需要 | 但要能**离线显示上次数据** |
| 语音对话（小智那类） | 需要 | 长连接 + 音频流，最吃资源（第 17 章） |
| 与手机 App 交换少量数据 | 可以只用 BLE | 不出网也能通（第 10.7 节） |
| OTA 升级 | 需要 | 还要改分区表（第 10c.7 节） |

**三条判断纪律**：

1. **没有网也要能用**——联网失败时 UI 不能卡死，功能不能整体不可用；
2. **联网任务不能挂在页面上**——页面切走就断网是常见 bug（第 10.6 节）；
3. **一个射频只能有一个主人**——两个模块各自 `esp_wifi_init()` 会互相打断。

---

## 10.1 Wi-Fi 的标准五步

ESP-IDF 的 Wi-Fi 初始化比很多人预期的长，因为要显式建立“事件循环”：

```c
// 1. 网络接口抽象层
esp_netif_init();

// 2. 默认事件循环（几乎所有事件都走它）
esp_event_loop_create_default();

// 3. 创建 STA（站点）模式的默认网络接口
esp_netif_create_default_wifi_sta();

// 4. Wi-Fi 驱动初始化
wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
esp_wifi_init(&cfg);

// 5. 配置并启动
wifi_config_t wifi_config = {
    .sta = {
        .ssid = "你的WiFi",
        .password = "密码",
    },
};
esp_wifi_set_mode(WIFI_MODE_STA);
esp_wifi_set_config(WIFI_IF_STA, &wifi_config);
esp_wifi_start();
```

这三步“看起来像废话”的前置（`esp_netif_init` / 默认事件循环 / netif）**一次也不能省**，
而且**整个进程只能做一次**。官方把它们抽成了 `main/demo_radio.c`：

```c
// main/demo_radio.c（官方源码）
esp_err_t demo_radio_nvs_prepare(void);      // nvs_flash_init（Wi-Fi/BLE 都依赖）
esp_err_t demo_radio_network_prepare(void);  // esp_netif_init + 默认事件循环
```

> 官方注释写得很直白：“**只初始化，不在失败时擦除用户数据。**
> NVS 里可能已有将来应用保存的凭据，示例无权为了起无线而清掉它。”
> 这条也适用于你自己的应用：**不要为了起 Wi-Fi 就 `nvs_flash_erase()`**。

> **生产环境别用便利创建器。** `esp_netif_create_default_wifi_sta()` 这类便利函数在
> 分配失败或挂事件处理失败时**直接 assert 重启**。想让“没射频/内存不够”只是一次
> `ESP_ERR_NO_MEM` 而不是重启循环，就走第 29.3 节那条 **checked 分步链**
> （`esp_netif_new` → `esp_netif_attach_wifi_station` → `esp_wifi_set_default_wifi_sta_handlers`，每步查返回值）。

**注意：`esp_wifi_start()` 不等于连上了。**
连接是异步的，你要注册事件处理器等结果：

```c
static void wifi_event_handler(void *arg, esp_event_base_t base,
                               int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();                       // 开始连接
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        ESP_LOGW(TAG, "断开，重连中...");
        esp_wifi_connect();                       // 断线自动重连
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *e = (ip_event_got_ip_t *)data;
        ESP_LOGI(TAG, "拿到 IP: " IPSTR, IP2STR(&e->ip_info.ip));
    }
}

esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL);
esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event_handler, NULL);
```

**或者直接用官方 demo**：官方基线的 `main/demo_wifi.c` 演示了扫描与连接，
多数 fork 还封装了 `bsp_wifi_*`（20 多个函数：connect/scan/forget/state/
ssid/ip/enabled/has_saved/radio_suspend/auto_connect……）。
**优先复用 fork 里的 `bsp_wifi`**，别自己从零写。

---

## 10.2 全部事件与“什么才算连上了”

### 事件清单（常用的就这几条）

| 事件 | 时机 | 你该做什么 |
| --- | --- | --- |
| `WIFI_EVENT_STA_START` | `esp_wifi_start()` 完成 | 调 `esp_wifi_connect()` |
| `WIFI_EVENT_STA_CONNECTED` | **关联到 AP**（认证+关联成功） | 什么都不用做，**还没拿到 IP** |
| `WIFI_EVENT_STA_DISCONNECTED` | 断开（含连接失败） | 读 `reason` 再决定重连 |
| `IP_EVENT_STA_GOT_IP` | **DHCP 拿到 IP** | ★ 这才是“联网了”的唯一标志 |
| `IP_EVENT_STA_LOST_IP` | IP 丢了（通常伴随断开） | 标记离线，停掉正在跑的请求 |
| `WIFI_EVENT_SCAN_DONE` | 扫描结束 | 取结果（第 10.4 节） |
| `WIFI_EVENT_STA_BEACON_TIMEOUT` | 连续收不到 AP 信标 | 信号太弱/走远了，可提前标记离线 |
| `WIFI_EVENT_AP_STACONNECTED` | SoftAP 下有终端连上（配网用） | 只是“加入热点” |
| `IP_EVENT_AP_STAIPASSIGNED` | SoftAP 下给终端发了 IP（配网用） | **这才算“手机能打开网页”**（第 10b.4 节） |

> 一句话：**`WIFI_EVENT_STA_CONNECTED` 只表示“和路由器握上手”，
> `IP_EVENT_STA_GOT_IP` 才表示“能发数据包”。**
> 把连接成功当联网成功的 UI，几乎必然出现“连上了但请求全超时”。

### 断开原因码（`wifi_event_sta_disconnected_t::reason`）

这是排障时最有用的一手信息，**一定要打印出来**：

```c
wifi_event_sta_disconnected_t *d = (wifi_event_sta_disconnected_t *)data;
ESP_LOGW(TAG, "断开 ssid=%s rssi=%d reason=%d",
         (char *)d->ssid, d->rssi, d->reason);
```

> v5.5.3 没有现成的 `reason → 字符串` API（第三方库才有），
> 自己按上表写一个 8 行的查表函数就够，别为了打印而引依赖。

| reason | 宏 | 含义 / 优先怀疑 |
| --- | --- | --- |
| 1 | `WIFI_REASON_UNSPECIFIED` | 通用失败，常是 AP 侧踢人或资源不足 |
| 2 / 3 | `AUTH_EXPIRE` / `AUTH_LEAVE` | AP 主动解除认证（踢设备、MAC 过滤） |
| 4 | `ASSOC_EXPIRE` | 关联超时，信号差或 AP 忙 |
| 6 / 7 | `NOT_AUTHED` / `NOT_ASSOCED` | 被 AP 拒绝认证（WPA3/黑白名单） |
| 15 | `4WAY_HANDSHAKE_TIMEOUT` | **密码错**（WPA2 四次握手超时） |
| 200 | `BEACON_TIMEOUT` | 长时间收不到信标——**信号太弱或走远了** |
| 201 | `NO_AP_FOUND` | 扫不到这个 SSID：信道不对 / **手机热点是 5 GHz** / SSID 隐藏 |
| 202 | `AUTH_FAIL` | **密码错**（认证阶段直接失败） |
| 203 | `ASSOC_FAIL` | 关联被拒（AP 满员 / 限速策略） |
| 204 / 205 | `HANDSHAKE_TIMEOUT` / `CONNECTION_FAIL` | 握手超时、综合失败 |

> 注意 15 / 202 是最常见的“用户输错密码”。**不要把 reason 藏起来**——
> 在配网界面上把 202 翻译成“密码错误，请重输”，比一句“连接失败”有用得多。

---

## 10.3 重连要有退避，还要有上限

上面那段 `esp_wifi_connect()` 是无脑重连——**别直接抄进产品**。
密码错（202）时也狂连，会把 Wi-Fi 任务占满、日志刷爆、功耗飞起。

```c
// 简化版：指数退避 + 抖动 + 上限（完整版见 snippets/08_wifi_sta_connect.c）
#define WIFI_RETRY_MAX_BACKOFF_MS 30000

static int s_retry;
static TimerHandle_t s_reconnect_timer;   // 或 esp_timer / 事件组 + 任务延时

static void schedule_reconnect(void)
{
    // 1s → 2s → 4s → 8s → ... → 30s 封顶，加 0~250 ms 抖动避免"万设备齐刷刷"
    int backoff = 1000 << (s_retry < 5 ? s_retry : 5);
    if (backoff > WIFI_RETRY_MAX_BACKOFF_MS) backoff = WIFI_RETRY_MAX_BACKOFF_MS;
    backoff += esp_random() % 250;
    s_retry++;
    xTimerChangePeriod(s_reconnect_timer, pdMS_TO_TICKS(backoff), 0);
}
```

四条纪律：

1. **永远不要在事件回调里 `while` 重试或 `vTaskDelay`**——回调跑在 Wi-Fi 事件任务，
   阻塞它会导致后续事件堆积。要重连就“投递一个信号”给自己的工作/定时器；
2. **对“密码错”这类确定性失败（2xx）不要无限重试**，回到配网界面让人重输；
3. **退避要带抖动**，否则整屋设备在同一秒集体重连；
4. **有上限 / 有放弃路径**：连不上 N 次就转“离线模式”，别让联网拖垮整个应用。

> 想省电可以开 modem sleep：`esp_wifi_set_ps(WIFI_PS_MAX_MODEM)`
> （收信标间隔由 `wifi_sta_config_t::listen_interval` 决定，默认 3 个信标周期）。
> 但它**会增加接收延迟**，做实时音频/长连接时要实测（第 8 章、第 17 章）。

---

## 10.4 扫描：能看但别滥用

```c
wifi_scan_config_t scan = {
    .ssid = NULL, .bssid = NULL, .channel = 0,   // 0 = 全信道
    .show_hidden = false,
    .scan_type = WIFI_SCAN_TYPE_ACTIVE,
    .scan_time = { .active = { .min = 100, .max = 300 } },   // 单位 ms/信道
};
esp_wifi_scan_start(&scan, false);               // ★ block=false，非阻塞
```

**五条纪律**：

1. **不要用 `block=true`**——它会阻塞调用者直到扫描完成（可能几百毫秒）。
   在按键回调 / LVGL 任务 / 事件回调里调用，轻则卡顿重则触发任务看门狗；
2. **扫描期间射频基本被独占**。正在连接（或已连接）时发扫描，要么返回
   `ESP_ERR_WIFI_STATE`，要么明显影响吞吐。要扫描就先安排好状态机：
   扫描 → 取结果 → 连接，串行进行；
3. **结果必须取走**：扫描结果存在驱动的动态内存里，
   **只有 `esp_wifi_scan_get_ap_records()` / `esp_wifi_clear_ap_list()` 会释放它**。
   内存紧张时这是很实在的一笔（IDF 注释原话：*“call any one to free the memory once the scan is done”*）；
4. **先 `get_ap_num` 再 `get_ap_records`**（IDF 规定的顺序，官方 demo 照做）；
5. **限制条数**、栈上定长数组、不 `malloc`——官方 demo 就是
   `wifi_ap_record_t records[5]`（第 29.5 节）；
6. **每信道扫描时间上限 1500 ms**：IDF 明确写了“超过 1500 ms 可能导致 STA 断开连接”，
   别为了“扫得全”把 `scan_time` 调大。

连接后想知道当前信号强度，不用再扫：

```c
wifi_ap_record_t ap;
if (esp_wifi_sta_get_ap_info(&ap) == ESP_OK) {
    ESP_LOGI(TAG, "rssi=%d ch=%d", ap.rssi, ap.primary);
}
```

> RSSI 粗判：> -60 dBm 很好，-70 左右可用，< -80 dBm 就别指望稳定跑 HTTPS 了。
> 把它做成“信号格”显示在 UI 上，比让用户猜“为什么加载不出来”友好得多。

---

## 10.5 凭据存哪里、怎么清

| 方式 | 怎么做 | 适用 |
| --- | --- | --- |
| 只存 RAM | `esp_wifi_set_storage(WIFI_STORAGE_RAM)` | **官方 demo 的选择**，零副作用 |
| 交给 IDF | `esp_wifi_set_storage(WIFI_STORAGE_FLASH)` | STA 配置自动落 NVS，上电自动重连 |
| 自己管 NVS | `nvs_set_str(handle, "wifi_ssid", ...)` | 想自己控制“保存 / 忘记”逻辑 |

三条纪律：

- **不要把密码打进日志、不要写进文档、不要提交到 Git**（官方 wifi-provisioning 文档明令禁止）；
- NVS 键名 **≤ 15 字符**（第 9 章）；
- **必须提供“忘记网络 / 清除凭据”的入口**，否则用户改了路由器密码就再也连不上，只能重刷固件。

---

## 10.6 连接失败是常态，必须有降级

设计的第一原则：**没有网也要能用。**

| 失败场景 | 降级方案 |
| --- | --- |
| 没配过网 | 显示“请先配网”引导，其他功能照常 |
| 配过但连不上 | 显示离线状态，**缓存上次的数据** |
| 连上了但服务器挂了 | 显示“服务不可用”，保留上次数据 |
| 2.4 GHz 配网失败 | 提示改用 BLE 配网 |

> 一条社区提醒：“2.4 GHz Wi-Fi 配网失败降级”被列为出行类玩法的必做项。
> ESP32-C3 **只支持 2.4 GHz**，不支持 5 GHz——如果你的手机热点是 5 GHz，
> 设备根本搜不到，这不是 bug。

## 10.7 刷新节流与“唯一所有者”

联网玩法最容易犯的错是**刷新太频繁**。PokeWalk 的后台任务里有一段专门的扫描节流逻辑：

```c
if (s_wifi_ok && scan_allowed && now >= next_scan) {
    scan_once();
    next_scan = esp_timer_get_time()
              + scan_pacing_next(&pacing, off, s_scan_stable) * 1000LL;
}
```

设计要点：

- 用 `esp_timer_get_time()` 算下次触发时间，而不是 `vTaskDelay` 硬等；
- 屏灭时不扫描（`screen_idle_is_off()` 判断）；
- 屏幕刚亮时重置计时（让用户立刻看到新数据）；
- 扫描结果稳定时可以拉长间隔。

> 作者的教训很有代表性：
> “扫描原本绑在 Collect 页的 `lv_timer` 上，离开那页就停，
> 导致一晚上的采集数据全丢。”

**联网任务不该依附于任何页面。** 这是第 16 章的核心内容。

同理，射频的所有权也要唯一。PokeWalk 的注释：

> “world 是 WiFi 的**唯一所有者**（Collect 页原本自己 bring_up，
> 两个所有者会争同一个射频）。”

**一个射频只能有一个主人。** 如果你的代码里有两个地方各自调
`esp_wifi_init()` / `esp_wifi_start()`，它们会互相打断。
把联网收敛到一个后台任务（或 BSP 封装）里，
其他模块通过“请求/订阅”的方式拿数据。

---

## 10.8 时间：SNTP 校时

设备上电后**不知道现在几点**——没有 RTC 电池。
要显示时间，联网后走 SNTP：

```c
esp_sntp_config_t cfg = ESP_NETIF_SNTP_DEFAULT_CONFIG("pool.ntp.org");
cfg.server_from_dhcp = true;
cfg.start = true;
esp_netif_sntp_init(&cfg);

// 等同步（带超时，别死等）
if (esp_netif_sntp_sync_wait(pdMS_TO_TICKS(10000)) == ESP_OK) {
    time_t now = 0; time(&now);
    ESP_LOGI(TAG, "已校时: %s", ctime(&now));
}
```

**设计要点**：

- 校时**失败要用开机时长兜底**（`esp_timer_get_time()`）；
- 不要因为校时失败就阻塞 UI；
- **HTTPS 也依赖它**——证书有效期校验靠系统时间，时间不对会直接握手失败
  （第 10c.3 节）。所以顺序是：**连上 → 校时 → 发 HTTPS 请求**。
- 有项目明确记录了这一点：

> “`is_night` 仍写死 false —— 判夜要墙钟时间，现在只有开机微秒数。”

也就是说，没校时之前，你没法判断“现在是白天还是晚上”。
这是个很典型的嵌入式约束。

---

## 10.9 BLE：另一条路

先划清边界（第 1.5 节那张表的展开）：

- 协议栈是 **NimBLE**（不是 Bluedroid）；
- 板上角色是 **peripheral / broadcaster**——设备当外设、发广播；
- **没有经典蓝牙**，A2DP / SPP 这类东西别去找。

BLE 常用于：

- **配网**（手机给设备发 WiFi 密码，比让设备开热点更好用）——见 [10b 章](10b-provisioning.md)；
- 与手机 App 通信（通知推送、ANCS）；
- 设备间通信（对讲机玩法）；
- USB/串口之外的调试通道。

初始化比 Wi-Fi 简单些，但内存开销不小。有实测记录：

> “联机占约 **73 KB 堆**，而串口截图要静态预留整屏 320×240，
> 因此默认固件带 LINK PLAY，截图工具改为可选构建。”

**73 KB 堆**——在没有 PSRAM、总可用堆约 230 KB 的板子上，这是三分之一。
所以很多项目会**砍掉 BLE 换内存**（PokeWalk 就明确说“比上游固件多 44 KB，
因为砍了 BLE”）。

> NimBLE 和 Wi-Fi **不是免费共存**的：它们共享同一个 2.4 GHz 射频，
> ESP32-C3 靠软件共存机制分时。同时跑 Wi-Fi 吞吐 + BLE 广播/连接时，
> 要实测延迟与吞吐，别只看功能是否通。

---

## 10.10 内存账：联网要花多少

| 功能 | 大致开销 |
| --- | --- |
| Wi-Fi 驱动 | 数十 KB（且碎片化风险高） |
| BLE 协议栈 | 约 73 KB 堆 |
| TLS 握手 | 需要额外缓冲（可配置动态释放） |
| HTTP 客户端 | 数 KB + 响应缓冲 |
| lwIP socket | 每个连接都要缓冲，上限 `CONFIG_LWIP_MAX_SOCKETS` |

省内存的配置（小智项目 `sdkconfig.defaults.esp32c3`）：

```text
CONFIG_ESP_WIFI_STATIC_RX_BUFFER_NUM=3
CONFIG_ESP_WIFI_DYNAMIC_RX_BUFFER_NUM=6
CONFIG_ESP_WIFI_RX_BA_WIN=3
CONFIG_LWIP_TCPIP_RECVMBOX_SIZE=16
CONFIG_MBEDTLS_DYNAMIC_FREE_CONFIG_DATA=y
CONFIG_ESP_WIFI_ENABLE_WPA3_SAE=n
CONFIG_ESP_WIFI_ESPNOW_MAX_ENCRYPT_NUM=0
CONFIG_FREERTOS_IDLE_TASK_STACKSIZE=768
CONFIG_LWIP_IPV6=n
```

最后一行 `CONFIG_LWIP_IPV6=n` 是白捡的内存——
**AI Passport 用不到 IPv6，关掉它。**

> 联网前先量一次堆：`esp_get_free_heap_size()` 看总量、
> `heap_caps_get_largest_free_block(MALLOC_CAP_8BIT)` 看最大连续块（第 11 章）。
> 官方经验文档给过一个很直观的例子：启动 SoftAP 前最大连续块约 **13 KiB**，
> 把音频改成延迟初始化并释放 codec/I2S 后升到约 **31 KiB**。
> **“延迟初始化”比“从每个网络缓冲里抠几个字节”有效得多。**

---

## 10.11 排障表

| 现象 | 优先查 |
| --- | --- |
| `esp_wifi_init()` 返回 `ESP_ERR_NO_MEM` | 先跑的 BLE/音频/大图没释放；看最大连续块 |
| 重复进页面后 `esp_wifi_init()` 失败 | `stop` 没做逆序回滚（第 29.7 节） |
| `WIFI_EVENT_STA_START` 不来 | `esp_netif_init` / 事件循环 / `esp_wifi_start()` 是否成功 |
| 一直停在 `STA_CONNECTED` 没有 `GOT_IP` | DHCP：路由器地址池满、MAC 过滤、AP 隔离 |
| reason=201 | SSID 不可见 / 5 GHz 热点 / 设备离得太远 |
| reason=15 或 202 | 密码错（含 WPA2/WPA3 混用、特殊字符被截断） |
| reason=200 | 信号弱；把设备靠近 AP 复测 |
| 连上几秒就断 | 省电模式、AP 踢人、RSSI 太低 |
| 扫描不返回结果 | 回调注册错 / 正在连接中 / 结果没取走导致下次扫描失败 |
| 请求偶尔成功 | 没设超时、socket 泄漏、堆碎片（见 10c） |

---

## 10.12 小结

- **先决策要不要联网**；不需要就别开，最大省内存省电的方式是不用；
- Wi-Fi 五步：netif → 事件循环 → 创建接口 → 初始化 → 配置启动；
- **`IP_EVENT_STA_GOT_IP` 才算联网**，`STA_CONNECTED` 不算；
- **断开 reason 一定要打印**，15/202 是密码错，201 是扫不到（想想 5 GHz）；
- 重连要**指数退避 + 抖动 + 上限**，且不在事件回调里阻塞；
- 扫描用**非阻塞**，结果**必须取走**，连接中别乱扫；
- 只支持 **2.4 GHz**；连不上是常态，**必须降级**；
- 时间靠 SNTP，未校时前只有开机微秒数（HTTPS 也依赖它）；
- **一个射频一个主人**，联网任务不要挂在页面上；
- BLE 约 73 KB 堆，和 Wi-Fi 共享 2.4 GHz 射频，要实测共存；
- 关掉 IPv6 省内存。

下一步：

- 密码怎么进设备 → [10b. 配网](10b-provisioning.md)；
- 拿到网怎么取数据 → [10c. 获取网络数据](10c-network-data.md)；
- 没有 PSRAM 怎么活 → 第 11 章。

> 官方把“STA 扫描（不连接）”和“NimBLE 非连接广播”做成健壮实例（含 Wi-Fi/BLE 栈的逆序回滚与停止握手）的逐行源码，分别见第 29 章（Wi-Fi 示例）和第 30 章（BLE 示例）。
