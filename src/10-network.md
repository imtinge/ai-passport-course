# 10. 联网：Wi-Fi、HTTP 与 BLE

> **可抄代码**：[D.10 Wi-Fi](D-module-cookbook.md#d10-wi-fi) · [D.11 BLE](D-module-cookbook.md#d11-ble)。


联网是 AI Passport 上最"重"的能力。它耗电、占内存、有失败可能，
而且**失败是常态**——设备会离开 WiFi 范围、密码会变、路由器会重启。

## 10.1 Wi-Fi 的标准五步

ESP-IDF 的 Wi-Fi 初始化比很多人预期的长，因为要显式建立"事件循环"：

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

## 10.2 连接失败是常态，必须有降级

设计的第一原则：**没有网也要能用。**

| 失败场景 | 降级方案 |
| --- | --- |
| 没配过网 | 显示"请先配网"引导，其他功能照常 |
| 配过但连不上 | 显示离线状态，**缓存上次的数据** |
| 连上了但服务器挂了 | 显示"服务不可用"，保留上次数据 |
| 2.4 GHz 配网失败 | 提示改用 BLE 配网 |

> 一条社区提醒："2.4 GHz Wi-Fi 配网失败降级"被列为出行类玩法的必做项。
> ESP32-C3 **只支持 2.4 GHz**，不支持 5 GHz——如果你的手机热点是 5 GHz，
> 设备根本搜不到，这不是 bug。

## 10.3 时间：SNTP 校时

设备上电后**不知道现在几点**——没有 RTC 电池。
要显示时间，联网后走 SNTP：

```c
esp_netif_sntp_init(&(esp_sntp_config_t){
    .server_from_dhcp = true,
    .start = true,
});
// 等同步完成
// 之后用 time() / localtime()
```

**设计要点**：

- 校时**失败要用开机时长兜底**（`esp_timer_get_time()`）；
- 不要因为校时失败就阻塞 UI；
- 有项目明确记录了这一点：

> "`is_night` 仍写死 false —— 判夜要墙钟时间，现在只有开机微秒数。"

也就是说，没校时之前，你没法判断"现在是白天还是晚上"。
这是个很典型的嵌入式约束。

## 10.4 HTTP 请求

```c
esp_http_client_config_t cfg = {
    .url = "https://api.example.com/data",
    .method = HTTP_METHOD_GET,
    .timeout_ms = 5000,           // ★ 一定要设超时
};
esp_http_client_handle_t client = esp_http_client_init(&cfg);
esp_err_t err = esp_http_client_perform(client);

if (err == ESP_OK) {
    int status = esp_http_client_get_status_code(client);
    int len = esp_http_client_get_content_length(client);
    // 读响应体（分块读，不要一次 malloc 整个响应）
}
esp_http_client_cleanup(client);
```

**两条纪律：**

1. **必须设 `timeout_ms`**，否则网络不通时会挂很久；
2. **不要一次 malloc 整个响应体**——JSON 响应可能有几十 KB，
   而你的最大连续块可能不到 8 KB。分块读、流式解析（用 cJSON 的流式接口或自己扫）。

HTTPS 证书可以这样编进固件：

```cmake
EMBED_TXTFILES "certs/servercert.pem"
```

## 10.5 刷新节流：联网玩法的必修课

行情看板、天气这类玩法最容易犯的错是**刷新太频繁**。
PokeWalk 的后台任务里有一段专门的扫描节流逻辑：

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
> "扫描原本绑在 Collect 页的 `lv_timer` 上，离开那页就停，
> 导致一晚上的采集数据全丢。"

**联网任务不该依附于任何页面。** 这是第 16 章的核心内容。

## 10.6 Wi-Fi 的唯一所有者原则

同上，PokeWalk 的注释：

> "world 是 WiFi 的**唯一所有者**（Collect 页原本自己 bring_up，
> 两个所有者会争同一个射频）。"

**一个射频只能有一个主人。** 如果你的代码里有两个地方各自调
`esp_wifi_init()` / `esp_wifi_start()`，它们会互相打断。

把联网收敛到一个后台任务（或 BSP 封装）里，
其他模块通过"请求/订阅"的方式拿数据。

## 10.7 BLE：另一条路

先划清边界（第 1.5 节那张表的展开）：

- 协议栈是 **NimBLE**（不是 Bluedroid）；
- 板上角色是 **peripheral / broadcaster**——设备当外设、发广播；
- **没有经典蓝牙**，A2DP / SPP 这类东西别去找。

BLE 常用于：

- **配网**（手机给设备发 WiFi 密码，比让设备开热点更好用）；
- 与手机 App 通信（通知推送、ANCS）；
- 设备间通信（对讲机玩法）；
- USB/串口之外的调试通道。

初始化比 Wi-Fi 简单些，但内存开销不小。有实测记录：

> "联机占约 **73 KB 堆**，而串口截图要静态预留整屏 320×240，
> 因此默认固件带 LINK PLAY，截图工具改为可选构建。"

**73 KB 堆**——在没有 PSRAM、总可用堆约 230 KB 的板子上，这是三分之一。
所以很多项目会**砍掉 BLE 换内存**（PokeWalk 就明确说"比上游固件多 44 KB，
因为砍了 BLE"）。

## 10.8 内存账：联网要花多少

| 功能 | 大致开销 |
| --- | --- |
| Wi-Fi 驱动 | 数十 KB（且碎片化风险高） |
| BLE 协议栈 | 约 73 KB 堆 |
| TLS 握手 | 需要额外缓冲（可配置动态释放） |
| HTTP 客户端 | 数 KB + 响应缓冲 |

省内存的配置（小智项目 `sdkconfig.defaults.esp32c3`）：

```
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

## 10.9 小结

- Wi-Fi 五步：netif → 事件循环 → 创建接口 → 初始化 → 配置启动；
- **连接是异步的**，靠事件处理器等结果；
- 只支持 **2.4 GHz**；连不上是常态，**必须降级**；
- 时间靠 SNTP，未校时前只有开机微秒数；
- HTTP 要**设超时 + 分块读**；
- **一个射频一个主人**，联网任务不要挂在页面上；
- BLE 约 73 KB 堆，和截图功能无法共存；
- 关掉 IPv6 省内存。

下一章是全书的重点之一：没有 PSRAM 怎么活。

> 官方把"STA 扫描（不连接）"和"NimBLE 非连接广播"做成健壮实例（含 Wi-Fi/BLE 栈的逆序回滚与停止握手）的逐行源码，分别见第 29 章（Wi-Fi 示例）和第 30 章（BLE 示例）。
