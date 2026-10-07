# 10c. 获取网络数据：HTTP / HTTPS / 长连接 / OTA

> **可抄代码**：[D.10 Wi-Fi](D-module-cookbook.md#d10-wi-fi)（含"HTTP 流式取数"子节） ·
> [`snippets/09_http_get_stream.c`](https://github.com/imtinge/ai-passport-course/tree/main/snippets)。
> **前置**：[第 10 章](10-network.md)（连上网）· [10b 章](10b-provisioning.md)（配好网）。

连上 Wi-Fi 只解决了"路通了"。这一章讲**路上怎么运货**：发一次请求、
流式收下响应、解析它、以及失败时该怎么办。

---

## 10c.0 一次请求的七个步骤，和每一步的失败点

```text
① DNS 解析      api.example.com → IP        失败：ESP_ERR_ESP_TLS_.../ 查不到
② TCP 连接      三次握手                    失败：超时 / 端口被墙
③ TLS 握手      证书 + 密钥交换（HTTPS）     失败：证书错 / 时间不对 / 内存不够
④ 发请求        GET / POST + header         失败：连接被服务端断开
⑤ 收响应头      status + Content-Length      失败：301/302、401、429、5xx
⑥ 收响应体      可能分多次、可能没有长度      失败：中途断开 / 缓冲溢出
⑦ 解析 + 释放   JSON/图片/音频 → 释放 client 失败：容量不够 / 忘了 cleanup
```

**第 ⑦ 步最容易被忽略**：`esp_http_client_cleanup()` 不调，socket 和缓冲就一直挂着。
反复请求几次后"第一次成功、后面全失败"，十有八九是这个。

> 一个很实用的诊断习惯：**把失败发生在第几步打印出来**。
> "请求失败"四个字没有任何排障价值；"TLS 握手失败"直接指向证书或时间。

---

## 10c.1 esp_http_client 的三档用法

### 档位一：`perform` 一把梭（响应小于几 KB 时用）

```c
esp_http_client_config_t cfg = {
    .url = "https://api.example.com/data",
    .method = HTTP_METHOD_GET,
    .timeout_ms = 5000,           // ★ 一定要设超时
};
esp_http_client_handle_t client = esp_http_client_init(&cfg);
esp_err_t err = esp_http_client_perform(client);

if (err == ESP_OK) {
    int     status = esp_http_client_get_status_code(client);
    int64_t len    = esp_http_client_get_content_length(client);   // 可能 -1（chunked）
    // 读响应体（分块读，不要一次 malloc 整个响应）
}
esp_http_client_cleanup(client);
```

**两条纪律：**

1. **必须设 `timeout_ms`**，否则网络不通时会挂很久（默认可能长达数十秒，
   足以让 UI 卡住甚至触发任务看门狗）；
2. **不要一次 `malloc` 整个响应体**——JSON 响应可能有几十 KB，
   而你的最大连续块可能不到 8 KB。分块读、流式解析（用 cJSON 的流式接口或自己扫）。

### 档位二：事件回调流式（**推荐**，绝大多数场景都用它）

`perform` 会把整段响应"推"进内部缓冲再交给你；
**回调模式让你在数据到达的那一刻就处理掉**，顺手就能做上限控制。

```c
#define MAX_BODY 8192                 // ★ 你自己定的硬上限

typedef struct {
    char  *buf;        // 调用方提供的缓冲（栈或静态，别 malloc 大块）
    size_t cap;
    size_t len;
    bool   overflow;
} body_t;

static esp_err_t on_http_event(esp_http_client_event_t *evt)
{
    body_t *body = (body_t *)evt->user_data;

    switch (evt->event_id) {
    case HTTP_EVENT_ON_CONNECTED:
        ESP_LOGI(TAG, "已连接（还没发请求）");
        break;

    case HTTP_EVENT_ON_HEADER:                       // 每个响应头都会回调一次
        if (strcasecmp(evt->header_key, "Content-Length") == 0) {
            ESP_LOGI(TAG, "Content-Length=%s", evt->header_value);
        }
        break;

    case HTTP_EVENT_ON_DATA: {                       // ★ 数据分多次到达
        if (evt->data_len == 0) break;               // 空事件，忽略
        // 超过硬上限就丢弃后续数据，并打标记——绝不越界写
        if (body->len + evt->data_len > body->cap) {
            body->overflow = true;
            ESP_LOGW(TAG, "响应超过 %u 字节，截断", (unsigned)body->cap);
            break;
        }
        memcpy(body->buf + body->len, evt->data, evt->data_len);
        body->len += evt->data_len;
        break;
    }

    case HTTP_EVENT_ON_FINISH:
        ESP_LOGI(TAG, "收完，共 %u 字节", (unsigned)body->len);
        break;

    case HTTP_EVENT_ERROR:
        ESP_LOGE(TAG, "HTTP 错误（DNS/TCP/TLS/超时都可能落在这里）");
        break;

    case HTTP_EVENT_DISCONNECTED:
        ESP_LOGI(TAG, "连接断开");
        break;

    default: break;
    }
    return ESP_OK;
}

esp_err_t fetch_json(const char *url, char *out, size_t cap, size_t *out_len)
{
    body_t body = { .buf = out, .cap = cap - 1 };    // ★ 预留结尾 '\0'
    esp_http_client_config_t cfg = {
        .url = url,
        .method = HTTP_METHOD_GET,
        .timeout_ms = 8000,
        .event_handler = on_http_event,
        .user_data = &body,
        .buffer_size = 1024,                         // 内部接收缓冲，别设太大
    };

    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    if (!client) return ESP_ERR_NO_MEM;

    esp_err_t err = esp_http_client_perform(client);
    int status = esp_http_client_get_status_code(client);
    esp_http_client_cleanup(client);                 // ★ 无论成败都要 cleanup

    if (err != ESP_OK)  return err;                  // 传输层失败
    if (status != 200)  { ESP_LOGW(TAG, "HTTP %d", status); return ESP_FAIL; }
    if (body.overflow)  return ESP_ERR_NO_MEM;       // 响应超出我的上限
    out[body.len] = '\0';
    *out_len = body.len;
    return ESP_OK;
}
```

**要点**：

- `buffer_size` 是内部**单次**接收缓冲（默认 512 字节左右），
  调大它不等于"能收更大的响应"，只会多占内存；
- `evt->data` 是**只读**的内部缓冲，回调返回后失效——要留就拷走；
- `HTTP_EVENT_ON_DATA` 会被调用多次，`data_len == 0` 的空事件要跳过；
- 上限 + `overflow` 标记，比"希望它别超"可靠。

### 档位三：手动 `open` / `fetch_headers` / `read`（完全控制）

下载大文件（固件、音频、图片）时，你需要在**看到响应头之后**再决定怎么收：

```c
esp_http_client_open(client, 0);                       // 只连、只发请求
int64_t len = esp_http_client_fetch_headers(client);   // 拿到头，返回 body 长度或 -1
if (len < 0) { /* chunked，没有 Content-Length —— 按"边读边写"处理 */ }

char buf[1024];
int total = 0, r;
while ((r = esp_http_client_read(client, buf, sizeof(buf))) > 0) {
    write_to_flash_or_decoder(buf, r);                 // ★ 边收边写，绝不攒着
    total += r;
}
esp_http_client_close(client);
esp_http_client_cleanup(client);
```

> **`Content-Length` 可能是 `-1`**（分块传输 chunked）。
> 任何 `len > 0` 才分配、`len < 0` 就报错的代码，都会在某个 CDN 上随机失效。

---

## 10c.2 HTTPS：证书、时间和内存，三件事一个都不能漏

### ① 证书怎么来

```c
// 方案 A：只信你自己的服务器证书（最省内存）
extern const char servercert_pem_start[] asm("_binary_servercert_pem_start");
extern const char servercert_pem_end[]   asm("_binary_servercert_pem_end");

esp_http_client_config_t cfg = {
    .url = "https://api.example.com/data",
    .cert_pem = servercert_pem_start,
    .cert_len = servercert_pem_end - servercert_pem_start,
};
```

```cmake
# main/CMakeLists.txt：把证书编进固件
idf_component_register(... EMBED_TXTFILES "certs/servercert.pem")
```

| 方案 | 做法 | 取舍 |
| --- | --- | --- |
| 单证书嵌入 | `.cert_pem = ...` + `EMBED_TXTFILES` | 最省内存；**证书轮换要重刷固件** |
| 证书包 | `.crt_bundle_attach = esp_crt_bundle_attach` | 通用（能访问多数公网 HTTPS）；**更占 Flash/RAM** |
| 全局 CA store | `.use_global_ca_store = true`（需先配置） | 多连接共享 |
| 跳过校验 | `.skip_cert_common_name_check = true` / 不校验证书 | **等于把明文密码写在链路上**，仅调试可用 |

### ② ★ TLS 依赖系统时间，这是最阴的坑

证书有效期校验要用"现在几点"。设备**上电不知道时间**（无 RTC 电池），
时间若停在 1970 年，**任何证书都是"尚未生效"，握手必然失败**。

所以顺序必须是：

```text
esp_wifi_connect() → IP_EVENT_STA_GOT_IP → esp_netif_sntp_init() + sync_wait()
                                        → 确认时间合理 → 发 HTTPS 请求
```

> 现象很迷惑：Wi-Fi 明明连上了、HTTP 明文能通、只有 HTTPS 全部失败。
> **先校时再请求**（第 10.8 节）。

### ③ 内存

TLS 握手是整条链路的内存峰值。可以开的省内存配置：

```text
CONFIG_MBEDTLS_DYNAMIC_BUFFER=y                 # 动态申请/释放 TLS 缓冲
CONFIG_MBEDTLS_DYNAMIC_FREE_CONFIG_DATA=y       # 用完释放配置数据
CONFIG_MBEDTLS_DYNAMIC_FREE_CA_CERT=y           # 用完释放 CA 证书
```

> 握手前后各打一次 `heap_caps_get_largest_free_block(MALLOC_CAP_8BIT)`，
> 你才知道这次 HTTPS 到底吃掉了多少连续内存。

---

## 10c.3 JSON：容量要按"响应"算，不是按"请求"算

一个真实的死机案例（官方收录的社区经验）：

> **固定 4096 字节的 JSON 文档去解析实际约需 6971 字节的响应。**
> 请求本身很小，因此只测试请求大小发现不了问题。

规则：

- 已知响应长度时，**解析前拒绝超限数据**；
- 长度未知时，**只允许累计到明确上限**（10c.1 档位二的 `MAX_BODY`）；
- **JSON 解析容量按允许的最大响应推导**——上限 8 KB 的响应，
  cJSON 的缓冲就要按 8 KB（而不是"估计 2 KB 够了"）来给；
- 检查反序列化错误，**失败后不能继续读字段**；
- 大型元数据响应**不要放在播放/网络工作任务里**解析（栈不够）。

```c
cJSON *root = cJSON_ParseWithLength(body, len);   // 传长度，别让它自己 strlen
if (!root) { ESP_LOGE(TAG, "JSON 解析失败"); return ESP_FAIL; }
cJSON *item = cJSON_GetObjectItem(root, "temp");
if (cJSON_IsNumber(item)) { ... }
cJSON_Delete(root);                               // ★ 一定删
```

> 可选做法：用一个**中转服务**把庞大/不稳定的上游接口收敛成小型设备协议。
> 但这不能掩盖固件限制——**即使有中转，设备端仍要保留大小上限、超时和错误处理**。

---

## 10c.4 长连接：MQTT / WebSocket / 裸 socket

HTTP 是"一问一答"。要做实时推送（行情、消息、语音流），得换协议。

| 协议 | 来源 | 适用 |
| --- | --- | --- |
| **MQTT** | IDF 自带组件 `mqtt`（`PRIV_REQUIRES mqtt`） | 物联网消息、QoS、保留消息、遗嘱 |
| **WebSocket** | 组件注册表：`espressif/esp_websocket_client`（**v5.5.3 基础组件里没有**） | 需要双向文本/二进制帧、走 443 端口穿透 |
| **裸 TCP/UDP** | lwIP socket | 自定义协议；小智那类语音流用 **UDP + Opus** |

```c
// MQTT 最小骨架（esp-mqtt）
esp_mqtt_client_config_t cfg = {
    .broker.address.uri = "mqtts://broker.example.com",
    .credentials.username = "dev",
    .credentials.authentication.password = "...",   // 别硬编码进 Git
    .session.keepalive = 60,
    .network.timeout_ms = 10000,
};
esp_mqtt_client_handle_t c = esp_mqtt_client_init(&cfg);
esp_mqtt_client_register_event(c, ESP_EVENT_ANY_ID, mqtt_event_cb, NULL);
esp_mqtt_client_start(c);
```

长连接的**五条纪律**：

1. **必须有心跳**（MQTT keepalive / 自定义 ping）——路由器会静默掉长时间空闲的连接；
2. **必须有重连退避**——和第 10.3 节 Wi-Fi 重连同一套逻辑（指数退避 + 抖动 + 上限）；
3. **`MQTT_EVENT_DISCONNECTED` / 连接断开后要停掉相关 UI 刷新**，别让界面显示一个不再更新的"实时数据"；
4. **payload 也要设上限**——"消息"和"HTTP 响应"一样可能把你撑爆；
5. **socket 数量有限**（`CONFIG_LWIP_MAX_SOCKETS`）：MQTT + HTTP + OTA + 网页服务要**合并计算**。

---

## 10c.5 最苛刻的场景：流式音频

播放网络音频是"取数"里压力最大的一种：网络、解码、I2S、UI 四条流水线同时跑
（完整设计见官方收录的 `docs/reference/phoenixzhc/network-audio-streaming-and-memory.zh_CN.md`）。

稳定的播放链路：

1. 控制器校验请求，**只启动一个**播放工作任务；
2. 工作任务打开 HTTP 流，**同时支持固定长度和未知长度**；
3. **有上限的输入缓冲增量喂给解码器**，绝不把完整文件堆进 RAM；
4. 解码后的 PCM 转成 BSP 已打开的格式，再写入 I2S；
5. 成功、取消、超时、解码失败**都走同一条清理路径**。

实测起点参数（某份固件，不是硬件默认值）：

```text
MP3 解码输入缓冲 24 KiB     PCM 缓冲 2304 采样     播放任务栈 8 KiB
```

**一个能算出来的硬边界**（源码 + 硬件指南都对得上）：

```text
I2S DMA = 6 个 descriptor × 240 frame
16 kHz 且缓冲填满时，最多容纳 6 × 240 / 16000 = 90 ms 音频
```

也就是说：**你的网络/解码任务只要停顿超过 90 ms，声音就断了。**
"UI 一卡、音频就爆"不是玄学，是这个数被超了。
官方给的两条对策：给音频工作任务**相对刷屏任务足够的优先级**，
以及播放与 Flash 写入并行时开 `CONFIG_I2S_ISR_IRAM_SAFE=y`
（Flash 擦写会关 cache，延后 I2S 中断）。

**四条经验**：

- **不要假设音频帧等于目标输出格式**：按音源采样率打开 codec，需要单声道就明确转换；
- **进度按已解码 PCM 采样数算**——按网络字节数算，在可变码率/分块传输下会跳；
- **音频设备只能有一个持有者**：新请求要么拒绝，要么先取消并等旧任务退出，
  绝不能在按键回调里跑 DNS/HTTP/解码/PCM 写入（第 7 章、第 12 章）；
- **日志没告警 ≠ 并发播放没杂音**：单独播放成功不代表"播放 + 刷屏 + 存档"并行没问题，
  要按官方那句要求——**持续播放 BGM、反复切换选项、确认真的写了 NVS，再实机试听**。

---

## 10c.6 OTA：先改分区表

```c
esp_http_client_config_t http = { .url = "https://.../firmware.bin", .timeout_ms = 30000 };
esp_https_ota_config_t ota = { .http_config = &http };
esp_err_t err = esp_https_ota(&ota);
if (err == ESP_OK) esp_restart();
```

**但先看清一件事**：官方默认 `partitions.csv` 只有三行——

```csv
nvs,      data, nvs,     0x9000,   0x6000,
phy_init, data, phy,     0xf000,   0x1000,
factory,  app,  factory, 0x10000,  0x7f0000,
```

**默认布局没有 OTA 槽。** 要做 OTA 你得自己改分区表：
加 `otadata` + 至少两个 app 槽（每槽要装得下你的固件），
**并且留够 8 MB 边界、不得重叠**。官方明确说：

> "默认布局没有 OTA 槽；它只是起点，不限制用户固件。"

**一份可直接抄的双槽示例**（`partitions-ota.csv`，8 MB Flash，两槽各约 3.4 MB，留足边界）：

```csv
# Name,   Type, SubType,  Offset,   Size,    Flags
nvs,      data, nvs,      0x9000,   0x6000,
phy_init, data, phy,      0xf000,   0x1000,
factory,  app,  factory,  0x10000,  0x340000,
ota_0,    app,  ota_0,    0x350000, 0x340000,
ota_1,    app,  ota_1,    0x690000, 0x340000,
otadata,  data, ota,      0x9d0000, 0x2000,
```

几个**必须算对**的点：

- `factory` + `ota_0` + `ota_1` 三个 app 槽各 `0x340000` ≈ 3.37 MB，要**大于你编译出的 `.bin`**；
  拿不准就先 `idf.py build` 看 `Project build complete, the maximum ... size` 再回头填。
- 末尾 `0x9d0000 + 0x2000 = 0x9d2000` ≈ 10.0 MB，已**越过 8 MB（0x800000）**——
  所以这份表只适用于更大的 Flash；**8 MB 板子上做 OTA 几乎挤不下**，要么精简固件，要么接受单槽 + 外部烧录。
- `otadata` 的 `SubType` 必须是 `ota`，且**只需占一小块**；它记下"当前跑哪个槽"，丢了就回 factory。
- 改完把 `sdkconfig` 的 `CONFIG_PARTITION_TABLE_CUSTOM=y` + `CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions-ota.csv"`，
  再跑 `./tools/validate.sh --firmware` 门禁（分区重叠/越界会被它拦下）。

> 8 MB 上 OTA 的真实代价：双槽直接吃掉约 6.7 MB，留给素材和 NVS 的空间被大幅压缩。
> 很多社区项目因此**放弃空中升级**，改用"插电脑烧录"或"出厂预烧 + 手动升级"。
> 动手前先用 [A.12 红线清单](A-api-cheatsheet.md#a12-动手前红线清单一页纸) 算一遍再决定。

OTA 的四条纪律：

1. **先改分区表再写 OTA 代码**，改完跑 `./tools/validate.sh --firmware` 门禁；
2. **OTA 期间不要同时跑 BLE / 音频 / 大图**——内存峰值叠加最容易在这里翻车；
3. **校验与回滚**：`esp_ota_mark_app_valid_cancel_rollback()` 要在确认新固件能正常启动后调用，
   否则下次上电自动回滚；
4. **失败要能说清**：把 HTTP 状态、写入偏移、镜像校验结果打印出来，
   "升级失败"四个字救不了现场。

---

## 10c.7 断网降级：让用户看到"最后更新的数据"

联网应用必须回答一个问题：**没网的时候屏幕上显示什么？**

```c
typedef struct {
    char     payload[512];      // 上次成功取到的数据（精简后）
    int64_t  updated_at_us;     // esp_timer_get_time() 记的时间戳
    bool     valid;             // 有没有缓存
} cache_t;
```

| 状态 | 屏幕显示 |
| --- | --- |
| 有缓存、正在刷新 | 显示缓存 + 小图标表示"刷新中" |
| 有缓存、刷新失败 | 显示缓存 + "最后更新 xx 分钟前" |
| 无缓存、连不上 | 显示"未联网"，引导配网，**其他功能照常可用** |
| 已配网但服务器 5xx | 显示"服务暂时不可用" |

**三条纪律**：

- **缓存要落 NVS**（第 9 章），否则重启后第一次进页面是空白；
- **缓存也要设长度上限**——它是写进 Flash 的，不是内存里随便放；
- **屏灭时不刷新、亮屏立即刷一次**（第 10.7 节节流），省电也省流量。

---

## 10c.8 排障表

| 现象 | 优先查 |
| --- | --- |
| `HTTP_EVENT_ERROR` 但 Wi-Fi 正常 | DNS？URL 写错（含 `http` / `https` 混用）？`timeout_ms` 太短？ |
| HTTPS 全失败、HTTP 正常 | **系统时间没校（SNTP）**、证书过期/域名不符、证书包没开 |
| 第一次成功，之后都失败 | 忘了 `esp_http_client_cleanup()`；socket / 缓冲泄漏 |
| 收到 301/302 | `disable_auto_redirect` 被设了，或 `max_redirection_count` 太小 |
| 拿到 `-1` 的长度 | 分块传输（chunked），按流式处理，别按长度分配 |
| 解析 JSON 时随机重启 | JSON 缓冲容量 < 实际响应（那个 4096 vs 6971 的坑） |
| 下载大文件中途停 | 写入超时、分区空间、缓冲溢出、并发访问 |
| 跑音频流时崩 | 输入缓冲/PCM/任务栈/最大连续块——按 10c.5 五项一起算 |
| 内存越来越少 | 每次请求前后打 `esp_get_free_heap_size()` 对比，找没释放的那一环 |

---

## 10c.9 小结

- 一次请求 = **DNS → TCP → TLS → 发 → 收头 → 收体 → 解析 → 释放**，
  排障时先定位到第几步；
- 用**事件回调流式**接数据，`buffer_size` 保持小，**上限 + overflow 标记**；
- **必须设 `timeout_ms`**、`cleanup()` 一定调、`Content-Length` 可能是 `-1`；
- HTTPS：**证书 + 时间（SNTP）+ 内存**三件事，缺一个就握手失败；
- JSON 容量**按响应算**，解析失败后不要再读字段；
- 长连接要有**心跳 + 退避重连 + payload 上限**，socket 数量合并计算；
- 流式音频：网络/解码/I2S/UI 是**一条受限流水线**，按最坏情况一起算内存；
- **OTA 先改分区表**（默认没有 OTA 槽），并做校验与回滚；
- 断网时**显示缓存 + 最后更新时间**，没有网也要能用。

到这里，联网这条线就完整了：
[10 章连上网](10-network.md) → [10b 章配好网](10b-provisioning.md) → 本章取到数据。
下一步回到最硬的约束：[第 11 章 没有 PSRAM 怎么活](11-memory.md)。
