# 10b. 配网：把 Wi-Fi 密码交给设备

> **可抄代码**：[D.10 Wi-Fi](D-module-cookbook.md#d10-wi-fi)（含“配网骨架”子节）。
> **上手顺序**：[第 10 章](10-network.md)（射频怎么起来）→ 本章（密码怎么进去）→
> [10c 章](10c-network-data.md)（拿到网怎么取数据）。

第 10 章讲 Wi-Fi 怎么连——但有个前置问题没解决：
**SSID 和密码从哪儿来？**

AI Passport 只有三个按键、一块 240×320 的屏，没有键盘、没有输入法。
在屏幕上用三键选字母输 20 位密码，是能给用户体验直接判死刑的设计。
所以联网应用必须额外做一件事：**配网（provisioning）**。

---

## 10b.0 先认清：配网是一个“临时运行的网络产品”

很多人的第一版配网是“起个热点 → 收个表单 → 完事”，然后在真机上随机重启。
官方经验文档那句话点得很准：

> **把配网当成固件内部一个临时运行的网络产品。**
> 它需要明确的启动和停止归属、严格的输入上限，
> 并且要分别验证 DHCP 与弹窗认证，不能把“已经连上 Wi-Fi”当成整个流程成功。

它有五个不亚于主功能的难点：内存（和音频/UI 抢 RAM）、状态机（进入/退出/超时/失败）、
安全（密码不能泄露）、持久化（凭据保存与清除）、清理（退出后 socket/netif/任务要归零）。
**这五件事，每一件都要在主流程之外单独设计。**

---

## 10b.1 五条路，先选一条

| 方式 | 密码怎么进去 | 代价 | 适合 |
| --- | --- | --- | --- |
| **编译期硬编码** | 写死在 `wifi_config_t` 里 | 改密码要重编译刷机 | 只有开发调试 |
| **串口 / NVS 写入** | 连 USB 用命令写入 NVS | 需要电脑，用户做不到 | 只有开发调试 |
| **BLUFI（BLE）** | 手机经 BLE 发 SSID/密码 | 要开 BLE（约 73 KB 堆），有库要接 | **官方路线、产品化** |
| **SoftAP + 网页** | 设备开热点，手机浏览器填表单 | 最吃内存（APSTA + httpd + DNS + socket） | 需要自定义配置页、上传素材 |
| **SmartConfig** | 手机 App 把密码编进 UDP 广播 | 依赖第三方 App，成功率受网络环境影响 | 兼容旧生态，新项目基本不用 |

**决策建议**：

- 只是想让设备上网 → **BLUFI**（官方有现成小程序，用户不用装 App）；
- 还要让用户传图片/音频/填昵称之类 → **SoftAP 网页**（但要认真做内存预算）；
- 调试阶段 → 硬编码 + 串口，够了就别上 UI。

> 官方立场很清楚：“**当前 `main` 的 Wi-Fi demo 仅扫描网络，并未实现联网或蓝牙配网；
> 没有联网需求的应用不必启用网络功能。**”
> 别把配网当成“联网的附赠品”——它是要收费的（内存 + 复杂度）。

---

## 10b.2 官方路线：BLUFI over BLE

### 官方给了什么

| 项目 | 内容 |
| --- | --- |
| 参考分支 | [`demo/blufi-provisioning`](https://github.com/FoloToy/ai-passport/tree/demo/blufi-provisioning) |
| 配套小程序 | **蓝牙配网-FoloToy AI PASSPORT**（完整名称，不要自行翻译或改写） |
| 设备广播名 | `BLUFI_FoloPassport`（参考固件的 BLE 广播名，不是小程序名） |
| 协议 | 手机经 BLE 上的 **BLUFI** 协议发 SSID/密码 → 设备以 STA 连接 → 回报状态 |
| 关键源码 | `main/demo_blufi.c`（回调/扫描/连接/凭据/状态回报/生命周期）、`main/demo_blufi_security.c(.h)`（安全协商回调）、`main/demo_radio.c`（NVS/netif/事件循环共享初始化）、`main/CMakeLists.txt` + `sdkconfig.defaults`（源文件注册、依赖、NimBLE/BLUFI 与加密配置） |

> **蓝牙只负责“传配网信息”，不承载应用的互联网流量。**
> 配完网就该把 BLE 停掉，把堆还给应用——BLE 那 73 KB 不是白拿的。

### 接入纪律（官方原话整理）

- 从**你当前的基线**出发，记录参考提交，**只移植适用的联网逻辑**；
- **不要直接合并整个 demo**，也不要用该分支的**旧版 BSP / 分区表 / sdkconfig** 覆盖当前版本；
- **重新实现你自己的界面**：配网状态、任务、Wi-Fi/BLE 服务都放应用层；
- **禁止记录或提交 Wi-Fi 密码**（日志、文档、Git 都不行）；
- 保留 LVGL 锁、非阻塞回调、任务与事件处理器的清理机制；
- 评估 Wi-Fi + BLE + UI 同时跑时的 **内部 RAM** 占用；
- 示例**不等于**完整的生产环境授权或安全设计。

### 用 IDF 自带的 `wifi_provisioning` 组件（推荐给新代码）

不想直接抄 BLUFI 回调，可以用 IDF 官方组件 `wifi_provisioning`（它自带 BLE /
SoftAP / console 三种 scheme，`ble` 方案底层就是 BLUFI）：

```cmake
# main/CMakeLists.txt
idf_component_register(SRCS "main.c" "..."
                       INCLUDE_DIRS "."
                       PRIV_REQUIRES wifi_provisioning nvs_flash ...)
```

```c
#include "wifi_provisioning/manager.h"
#include "wifi_provisioning/scheme_ble.h"   // 走 BLE/BLUFI；换 SoftAP 就改 scheme_softap.h

static void prov_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base != WIFI_PROV_EVENT) return;
    switch (id) {
    case WIFI_PROV_START:      ESP_LOGI(TAG, "配网开始");   break;
    case WIFI_PROV_CRED_RECV:  {   // 收到凭据，还没连
        wifi_sta_config_t *c = (wifi_sta_config_t *)data;
        ESP_LOGI(TAG, "收到 SSID: %s", (const char *)c->ssid);   // ★ 别打密码
        break;
    }
    case WIFI_PROV_CRED_FAIL: {    // ★ 失败原因：区分密码错 / 扫不到 AP
        wifi_prov_sta_fail_reason_t *r = (wifi_prov_sta_fail_reason_t *)data;
        ESP_LOGE(TAG, "连接失败 reason=%d", *r);
        break;
    }
    case WIFI_PROV_CRED_SUCCESS: ESP_LOGI(TAG, "连上并拿到 IP"); break;
    case WIFI_PROV_END:          s_prov_done = true; /* 通知主流程 */ break;
    default: break;
    }
}

void start_provisioning(void)
{
    wifi_prov_mgr_config_t cfg = {
        .scheme = wifi_prov_scheme_ble,
        .scheme_event_handler = WIFI_PROV_SCHEME_BLE_EVENT_HANDLER_FREE_BLE, // 配完网释放 BLE
    };
    ESP_ERROR_CHECK(wifi_prov_mgr_init(cfg));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_PROV_EVENT, ESP_EVENT_ANY_ID,
                                               &prov_event, NULL));

    bool provisioned = false;
    ESP_ERROR_CHECK(wifi_prov_mgr_is_provisioned(&provisioned));
    if (!provisioned) {
        const char *pop = "abcd1234";    // proof of possession（产品里别硬编码，也从屏上读不出来）
        ESP_ERROR_CHECK(wifi_prov_mgr_start_provisioning(
            WIFI_PROV_SECURITY_1,        // X25519 密钥交换 + PoP
            pop,                         // sec_params：SECURITY_1 时就是 PoP 字符串
            "BLUFI_FoloPassport",        // service_name = BLE 广播名
            NULL));                      // service_key
    }
}

void forget_wifi(void)
{
    wifi_prov_mgr_reset_provisioning();   // 清凭据，下次开机重新配网
}
```

安全等级（`WIFI_PROV_SECURITY_*`，v5.5.3 `manager.h:218-235`）：

| 级别 | 含义 |
| --- | --- |
| `WIFI_PROV_SECURITY_0` | 明文，无加密——**只用于调试** |
| `WIFI_PROV_SECURITY_1` | X25519 密钥交换 + PoP（proof of possession） |
| `WIFI_PROV_SECURITY_2` | SRP6a（更强，需传 `wifi_prov_security2_params_t`） |

> **小屏设备的现实**：PoP 要让用户从包装/丝印上抄一串字符。
> 如果用官方小程序那条路，PoP 由小程序与固件约定，用户不感知；
> 自己实现时，别设计成“让用户在 240×320 的屏上输入 8 位 PoP”。

---

## 10b.3 配网的完整时序（通用，任何方案都适用）

```text
[进入配网]
   ↓  释放可选子系统（音频/大图/解码器），量一次最大连续块
[起承载] SoftAP：起 AP + httpd + DNS   |   BLE：起广播 + BLUFI 服务
   ↓
[等手机] SoftAP：等 AP_STACONNECTED + IP_EVENT_AP_STAIPASSIGNED
         BLE：等小程序连接 + 安全协商
   ↓
[收凭据] 校验 SSID/密码长度与字符集（超限直接拒绝）
   ↓
[试连接] 切 STA → esp_wifi_connect() → 等 IP_EVENT_STA_GOT_IP（带超时，如 15 s）
   ↓
   ├─ 成功 → ①保存凭据 ②回报"已联网" ③停承载（关 AP/httpd 或停 BLE 广播）
   │         ④恢复被延迟初始化的子系统 ⑤退出配网，进主流程
   └─ 失败 → ①**不覆盖旧凭据** ②把 reason 翻译成人话显示（密码错 / 扫不到 / 超时）
             ③允许重试（有上限）④超时或用户退出 → 停承载、清理、回主菜单
```

**四条硬纪律**：

1. **STA 连接验证成功前，不要覆盖持久化的凭据**——保留上一组可用凭据，
   只有新凭据验证成功后才替换。否则一次输错就让设备再也连不上；
2. **每一步都要有超时**：等手机、收凭据、试连接，任何一个卡住都要能自己退出来；
3. **退出路径只有一条**：不管成功、失败、超时还是用户长按返回，
   都走同一个 `provisioning_stop()`，把 socket / DNS / httpd / netif / 事件处理器 / 任务全部归零；
4. **反复进出要能回到同一条内存基线**——这是判断你清理干净没的唯一标准
   （第 22 章有量法）。

---

## 10b.4 自己做 SoftAP 配网：资源与兼容性

如果要自定义网页（传图片、填昵称、选角色），就得自己开热点。
下面这份清单来自官方收录的社区经验（`docs/reference/phoenixzhc/softap-provisioning-and-resource-budget.zh_CN.md`），每一条都是真机踩出来的。

### ① 先定工作模式

| 模式 | 推荐行为 |
| --- | --- |
| **短时配网** | 用 **APSTA**，收凭据 → 验证 STA 连接 → 成功后保存 → 停 AP 和网页服务 |
| **长期开启的本地管理** | 不需要上游网络时优先 **AP-only**；提供稳定本地地址，为反复重连和浏览器探测预留资源 |

**长期保持 APSTA 会持续占用更多堆、socket 和无线调度时间。**
不能只因为开发阶段方便就一直开着。

### ② 起 Wi-Fi 前先释放可选子系统

一份基于 AI Passport 的固件实测：启动 SoftAP 前最大连续空闲块约 **13 KiB**；
把音频改成**延迟初始化**并释放不用的 codec/I2S 资源后，升到约 **31 KiB**。

> 结论可复用：**延迟初始化通常比从每个网络缓冲里零散省几个字节更有效。**

进配网页前应停掉/延迟：音频任务、解码状态、大图片、临时 JSON 文档、重复界面。
并在**四个时刻**分别记录空闲堆与最大连续块：Wi-Fi 启动前 / AP 启动后 / HTTP 启动后 / 手机接入后。

### ③ 分清“连上热点”和“拿到 IP”

创建 ESP-IDF 默认 SoftAP 网络接口，让框架管 DHCP（除非你有定制地址规划）。
只允许一个用户配网时，`max_connection = 1` 是一份保守的实测起点。

```text
WIFI_EVENT_AP_STACONNECTED     → 终端已加入热点
IP_EVENT_AP_STAIPASSIGNED      → DHCP 已分配地址  ★ 界面想显示"可以打开网页"要看这个
```

**不要把 Wi-Fi 关联成功误当成 DHCP 完成。** 同时记录这两个事件、分配的地址、
断开原因和当前堆，才能区分“认证问题 / DHCP 问题 / HTTP 问题”。

### ④ 弹窗认证（captive portal）是兼容性功能

弹窗通常由**通配 DNS + HTTP 重定向 + 可选的 DHCP 门户信息**组合实现。
不同 Android / iOS / 桌面系统会访问**不同探测地址**——
**在一台手机上成功 ≠ 功能验证完整。**

短时配网可用流程：

1. DNS 查询统一返回 AP 地址；
2. 对已知联网探测路径直接响应或重定向到本地页面；
3. 平台支持时可考虑 **DHCP Option 114**，但**必须抓包或真机确认后**才能宣称已部署；
4. 配网完成后**完整停止 DNS 和 HTTP 服务**。

> 对长期管理热点，自动弹窗可能反而打扰用户。
> 印在界面上的本地地址或二维码 + 少量重定向，可能更合适。
> 通配 DNS 还会产生后台流量，要限制解析长度、请求频率并正确释放 socket。

### ⑤ 限制每一份 HTTP 输入

**小表单和文件上传一样可能溢出。** 接收表单前：

- `Content-Length` 超过接口上限时**立即拒绝**；
- 为字符串结尾的 `\0` **预留空间**；
- **循环接收**直到达到声明长度或超时；
- 把**返回零、超时、断开**都算作明确失败；
- 完整收到受限长度正文后再做 **URL 解码**；
- 写入存储前**再次校验**解码后的字段长度。

大文件用**固定大小分块**（实测实现用 **1024 字节**）接收，不能按完整正文申请内存。
先写**临时目标** → 校验大小和格式 → 处理并发访问 → 全部成功后替换正式资源；
任何失败路径都要删除或标记临时目标无效。

### ⑥ 有意控制网页服务规模

一份**单客户端**配置服务的实测参数（起点，不是通用默认值）：

```text
HTTP socket 数 3      backlog 2        接收重试 2      发送重试 10
LRU 清理 开           服务任务栈 6144   TCP 收发窗口 2880
```

增大传输缓冲之前，先缩减网页资源：

- 构建时 **gzip** 压缩静态页面；
- 大型 JSON / 文件列表**分块发送**；
- 缩小缩略图，限制**同时解码数量**；
- 请求失败后立即关闭并释放上下文；
- 避免网页同时发起多个请求。

> **即使只打开一个页面，浏览器也可能建立多个连接。**
> DNS、HTTP、STA 验证、遥测和仍在运行的音频服务所用 socket 必须**合并计算**。

### ⑦ SoftAP 故障特征表

| 现象 | 优先检查 |
| --- | --- |
| 手机连上热点但不弹页面 | DHCP 分配事件、DNS 响应、探测路径处理、HTTP socket 是否可用 |
| 提交表单时随机重启 | 声明长度、结尾空间、接收循环、任务栈、最大连续空闲块 |
| 上传中途停止 | 接收超时、分块写入结果、存储空间、并发读写 |
| 第一次成功，重试后失败 | socket / DNS 任务 / 事件处理器 / netif / 临时缓冲是否泄漏 |
| 运行过其他功能后 AP 才启动失败 | 最大连续空闲块、可选子系统是否仍占用资源 |

---

## 10b.5 SmartConfig：知道就行

```c
smartconfig_start_config_t cfg = SMARTCONFIG_START_CONFIG_DEFAULT();
esp_smartconfig_set_type(SC_TYPE_ESPTOUCH_V2);   // 或 ESPTOUCH / ESPTOUCH_AIRKISS
esp_smartconfig_start(&cfg);
// 事件：SC_EVENT_SCAN_DONE → SC_EVENT_FOUND_CHANNEL → SC_EVENT_GOT_SSID_PSWD → SC_EVENT_SEND_ACK_DONE
```

手机把密码编进 UDP 广播，设备抓包解出来。
**ESP32-C3 只支持 2.4 GHz**，且手机侧需要乐鑫的 EspTouch App 或你自己实现广播端——
在“官方已有小程序”的前提下，新项目基本没必要走这条路。列出来是为了让你在
旧教程里见到它时不至于困惑。

---

## 10b.6 凭据：保存、验证、清除

| 动作 | 做法 |
| --- | --- |
| 保存 | 自管 NVS（`nvs_set_str`，键名 ≤ 15 字符）或交给 IDF（`WIFI_STORAGE_FLASH`） |
| 验证 | **STA 真正 `GOT_IP` 之后**才算验证通过，之前一律不覆盖旧凭据 |
| 清除 | 提供“忘记网络”入口：`wifi_prov_mgr_reset_provisioning()` 或自己 `nvs_erase_key` |
| 保护 | **不打印密码、不写进日志/文档、不提交 Git；日志里只打 SSID** |

> 一个很实在的细节：凭据**先验证后覆盖**。
> 用户在咖啡馆配网失败，如果旧的家庭 Wi-Fi 凭据被覆盖了，设备就变砖（对用户而言）。
> 保留上一组可用凭据，是成本最低的容错。

---

## 10b.7 配网 UI：状态机 + 单点渲染

配网界面天然是异步的（等手机、等 DHCP、等 IP），
照第 29 章那个模式写就不会错：

```c
typedef enum {
    PROV_IDLE, PROV_WAITING_PHONE, PROV_GOT_CRED, PROV_CONNECTING,
    PROV_GOT_IP, PROV_FAILED, PROV_CANCELLED,
} prov_state_t;

static volatile prov_state_t s_state;          // 事件回调改，LVGL 任务读
static volatile int          s_reason;         // 失败原因（给 UI 翻译）
```

**纪律**：

- **事件回调只改 `volatile` 状态**，绝不直接 `lv_label_set_text`
  （回调跑在 Wi-Fi/Prov 事件任务，直接碰 LVGL 会竞争）；
- UI 由 `lv_timer` 的 `tick` **单点渲染**（第 29.6 节）；
- **长按返回 = 取消**，要能立刻走 `provisioning_stop()`；
- 失败信息要**翻成用户语言**：202 → “密码错误”、201 → “找不到这个 Wi-Fi（只支持 2.4 GHz）”、
  超时 → “连接超时，请重试”。打印 reason 是给开发者看的，显示 reason 是偷懒。

---

## 10b.8 验收清单

官方要求的真机验证项（编译通过**不能**证明小程序兼容性或实机联网正常）：

- [ ] 发现设备（BLE 广播名 / 热点的 SSID 与文档一致）
- [ ] 成功配网并**拿到 IP**
- [ ] **密码错误**时的表现（要能重输，不能卡死）
- [ ] **网络不可用**（路由器拔线）时的表现
- [ ] 重连、重启后自动连回上次的网络
- [ ] 清除凭据后回到“待配网”
- [ ] **反复进出配网**（内存/任务/socket/netif 回到基线）
- [ ] **应用实际需要的网络请求**能成功
- [ ] Android / iOS / Windows，以及**至少一种不会自动弹窗的客户端**（SoftAP 方案）
- [ ] 每个阶段记录：空闲堆、最大连续块、任务栈高水位

> 官方特别强调一句：**“仅蓝牙连接成功不能证明能够访问互联网。”**
> 配网流程的最后一步，永远是一次**真实的应用请求**，不是“BLE 连上了”。

---

## 10b.9 排障表

| 现象 | 优先查 |
| --- | --- |
| 手机搜不到设备的 BLE 广播 | NimBLE 是否 init、host 任务是否起、广播名是否与小程序期望一致、BLE 是否被别的模块占用 |
| 小程序显示配网成功，但设备没网 | 凭据是否真的保存、STA 是否 `GOT_IP`、**有没有做真实请求验证** |
| 密码正确却一直失败 | 2.4 GHz？WPA2/WPA3 混用？特殊字符被表单截断？`Content-Length` 处理错导致密码被截断 |
| 配完网应用内存不够了 | BLE/AP/httpd 没停干净；用 `heap_caps_get_largest_free_block` 对比配网前后 |
| 退出配网后再进入失败 | 逆序回滚漏了一步（socket / DNS task / 事件处理器 / netif） |
| 手机连上热点不弹页面 | 见 10b.4 ⑦ |

---

## 10b.10 小结

- **配网是独立功能，不是联网的附赠品**：内存、状态机、安全、持久化、清理，五项都要单独设计；
- 路线选择：**BLUFI（官方，有小程序）** > SoftAP（要自定义网页时） > SmartConfig（兼容旧生态）；
- **STA 拿到 IP 才算配网成功**——“BLE 连上”“手机连上热点”都不算；
- **凭据先验证后覆盖**，必须提供清除入口，**密码绝不进日志**；
- SoftAP 方案：起 Wi-Fi 前**释放可选子系统**、分清 AP 关联与 DHCP 、
  限制 HTTP 输入、控制 httpd 规模、退出后一切归零；
- 验收的**最后一步是一次真实应用请求**，不是“连接成功”。

下一步：[10c. 获取网络数据](10c-network-data.md)——HTTP / HTTPS / 长连接 / OTA。
