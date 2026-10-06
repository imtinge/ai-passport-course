# 29. 官方 Wi-Fi 示例：STA 扫描（不连接、不存凭证）

源码：`main/demo_wifi.c`（246 行）+ 辅助 `main/demo_radio.c/.h`。它演示**完整的 ESP-IDF Wi-Fi
启动链**，但故意**只扫描不连接**——既验证射频能工作，又避免在示例里存任何用户凭证。

> 行号来自官方基线 `main/demo_wifi.c` 与 `main/demo_radio.c`。

## 29.1 它验证什么

| 操作 | 行为 |
| --- | --- |
| 打开页面 | 自动起 STA、扫描附近 AP，列表显示 RSSI / SSID / 信道（最多 5 条） |
| OK（短按） | 在空闲态重新扫描 |
| OK（长按） | 返回菜单（框架拦截） |

源码注释（`demo_wifi.c:1`）：`// main/demo_wifi.c —— STA 模式扫描附近 AP，不连接网络、不保存凭证。`

## 29.2 状态机：跨任务的状态要用 `volatile`

```c
// main/demo_wifi.c:20-37
typedef enum {
    WIFI_DEMO_OFF = 0, WIFI_DEMO_STARTING, WIFI_DEMO_SCANNING,
    WIFI_DEMO_READY, WIFI_DEMO_FAILED,
} wifi_demo_state_t;

static volatile wifi_demo_state_t s_state;     // ★ volatile：scan_done 回调跨任务改它
static volatile esp_err_t s_error;
```

`s_state` 标了 `volatile`——因为它会被 `scan_done` 事件回调（跑在 Wi-Fi 事件任务里）修改，
又被 `tick`（跑在 LVGL 任务里）读取，两个任务并发，编译器可能把状态缓存进寄存器导致读不到最新值。
**凡是被中断/事件回调和主逻辑同时读写的变量，都要 `volatile`**。这是第 12 章讲过的纪律，这里官方实测落地。

## 29.3 `start`：完整的 Wi-Fi 启动链（且失败不重启）

```c
// main/demo_wifi.c:65-117（节选）
esp_err_t demo_wifi_start(void) {
    if (s_sta_netif || s_wifi_initialized) return ESP_ERR_INVALID_STATE;
    s_state = WIFI_DEMO_STARTING;
    esp_err_t err = demo_radio_nvs_prepare();          // ① NVS（存 Wi-Fi 态用，不擦用户数据）
    if (err != ESP_OK) goto fail;
    err = demo_radio_network_prepare();                // ② esp_netif_init + 默认事件循环
    if (err != ESP_OK) goto fail;

    // 用"分步 checked"而非便利创建器：便利创建器在分配/挂处理失败时会 assert 重启，
    // 而这个可选 demo 要能"失败而不重启"。
    esp_netif_config_t netif_cfg = ESP_NETIF_DEFAULT_WIFI_STA();
    s_sta_netif = esp_netif_new(&netif_cfg);
    if (!s_sta_netif) { err = ESP_ERR_NO_MEM; goto fail; }
    err = esp_netif_attach_wifi_station(s_sta_netif);  if (err != ESP_OK) goto fail;
    err = esp_wifi_set_default_wifi_sta_handlers();    if (err != ESP_OK) goto fail;

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    err = esp_wifi_init(&cfg);                         if (err != ESP_OK) goto fail;
    s_wifi_initialized = true;

    err = esp_event_handler_instance_register(WIFI_EVENT, WIFI_EVENT_SCAN_DONE,
                                              scan_done, NULL, &s_scan_handler);   // ③ 注册扫描完成回调
    if (err != ESP_OK) goto fail;
    err = esp_wifi_set_storage(WIFI_STORAGE_RAM);      // ④ 凭证只存 RAM，不写 NVS
    if (err != ESP_OK) goto fail;
    err = esp_wifi_set_mode(WIFI_MODE_STA);            if (err != ESP_OK) goto fail;
    err = esp_wifi_start();                            if (err != ESP_OK) goto fail;
    s_wifi_started = true;

    err = start_scan();                                // ⑤ 发起扫描
    if (err != ESP_OK) goto fail;
    return ESP_OK;

fail:
    wifi_stack_stop();                                 // ★ 任何一步失败都逆序回滚
    s_error = err; s_state = WIFI_DEMO_FAILED;
    ESP_LOGE(TAG, "Wi-Fi 初始化失败: %s", esp_err_to_name(err));
    return err;
}
```

**两个必须记的官方选择**：

1. **用"分步 checked"而非 `esp_wifi_init()` 的便利创建器**（如 `esp_netif_create_default_wifi_sta`
   那类会替你 `assert` 的）。源码注释明说：便利创建器在分配或挂处理失败时**直接 abort 重启**，
   而这个"可选 demo"要能**失败而不重启**——否则一个没天线/没射频的环境会把板子卡在重启循环。
   **复用 Wi-Fi 时，想让应用健壮就走这条 checked 链。**
2. **`WIFI_STORAGE_RAM` + 不连接**：凭证只存内存，扫描完不连任何 AP，因此这个 demo 不会在 NVS 里
   留下任何东西。`demo_radio_nvs_prepare()` 的注释（`demo_radio.c:18-22`）特别强调：NVS 初始化失败
   **不自动擦除分区**——示例不能为了起无线就抹掉你未来应用可能存的数据。这是"示例的操守"。

## 29.4 `scan_done` 事件回调：改状态，不直接刷屏

```c
// main/demo_wifi.c:40-47
static void scan_done(void *arg, esp_event_base_t base, int32_t id, void *data) {
    (void)arg; (void)base; (void)id; (void)data;
    if (s_state == WIFI_DEMO_SCANNING) s_state = WIFI_DEMO_READY;   // 只改状态
}
```

事件回调**只改 `s_state`，不碰 LVGL**。真正的列表渲染留给 `tick`（LVGL 任务内，已持锁）。
这是"**事件回调跨任务、不要直接操作 UI**"的纪律——回调跑在 Wi-Fi 事件任务，直接 `lv_label_set_text`
会和 LVGL 任务竞争，轻则花屏重则崩。

## 29.5 `show_scan_results`：取结果 + 限条数 + 格式化

```c
// main/demo_wifi.c:119-148（节选）
static void show_scan_results(void) {
    uint16_t total = 0;
    uint16_t count = WIFI_RESULT_COUNT;               // 5
    wifi_ap_record_t records[WIFI_RESULT_COUNT] = { 0 };
    esp_err_t err = esp_wifi_scan_get_ap_num(&total);              // 先拿总数
    if (err == ESP_OK) err = esp_wifi_scan_get_ap_records(&count, records);  // 再取记录
    if (err != ESP_OK) { s_error = err; s_state = WIFI_DEMO_FAILED; return; }

    for (uint16_t i = 0; i < count && used < sizeof(text); i++) {
        int written = snprintf(text + used, sizeof(text) - used,
                               "%d  %.18s  ch%u\n",                    // SSID 截断到 18 字符
                               records[i].rssi, (const char *)records[i].ssid,
                               records[i].primary);
        if (written < 0 || (size_t)written >= sizeof(text) - used) break;
        used += (size_t)written;
    }
    lv_label_set_text_fmt(s_status, "%u APs  |  OK: RESCAN", total);
    lv_label_set_text(s_results, text);
    s_state = WIFI_DEMO_OFF;                          // 回到"可重扫"空闲态
}
```

要点：① 先 `get_ap_num` 再 `get_ap_records`（ESP-IDF 规定顺序）；② 栈上固定 5 条记录数组，
**不 `malloc`**；③ `%.18s` 把 SSID 截断防溢出；④ `snprintf` 返回值做边界检查，避免写爆 `text[320]`。

## 29.6 `tick`：按状态刷屏（LVGL 任务内）

```c
// main/demo_wifi.c:150-170
static void tick(lv_timer_t *timer) {
    (void)timer;
    switch (s_state) {
    case WIFI_DEMO_STARTING:  lv_label_set_text(s_status, "Starting Wi-Fi..."); break;
    case WIFI_DEMO_SCANNING:  lv_label_set_text(s_status, "Scanning 2.4 GHz..."); break;
    case WIFI_DEMO_READY:     show_scan_results(); break;        // 状态机驱动渲染
    case WIFI_DEMO_FAILED:    lv_label_set_text_fmt(s_status, "Wi-Fi failed: %s", esp_err_to_name(s_error));
                               s_state = WIFI_DEMO_OFF; break;
    default: break;
    }
}
```

`tick` 把 `s_state` 翻译成屏幕文字——UI 永远由 LVGL 任务单方面驱动，事件回调只喂状态。
这就是"**状态机 + 单点渲染**"模式，比"哪个回调都去刷屏"干净得多。

## 29.7 `wifi_stack_stop`：逆序回滚（和启动链对称）

```c
// main/demo_wifi.c:172-193（节选）
static void wifi_stack_stop(void) {
    if (s_wifi_started)     { esp_wifi_scan_stop(); esp_wifi_stop(); s_wifi_started = false; }
    if (s_handler_registered) { esp_event_handler_instance_unregister(...); s_handler_registered = false; }
    if (s_wifi_initialized) { esp_wifi_deinit(); s_wifi_initialized = false; }
    if (s_sta_netif)        { esp_netif_destroy_default_wifi(s_sta_netif); s_sta_netif = NULL; }
    s_state = WIFI_DEMO_OFF;
}
```

**资源清理顺序和启动严格对称、逆序**：先停扫描/停 Wi-Fi → 注销事件处理 → deinit → 销毁 netif。
`demo_wifi_stop()` 直接调它（`:195-199`）。凡是"进页面初始化了一整套栈"的 demo（Wi-Fi、BLE），
`stop` 都要做这种逆序回滚——漏一步就会留下半初始化状态，下次进页面 `esp_wifi_init` 直接报
`ESP_ERR_WIFI_MODE` 之类。

## 29.8 `enter` / `exit` / `key`

`enter`（`:201-223`）建屏 + 起 `tick` timer（100 ms）+ 置 `STARTING`；`exit`（`:225-236`）删 timer + 删屏；
`key`（`:238-245`）只在 `OFF` 空闲态响应 OK 重扫：

```c
// main/demo_wifi.c:238-245
void demo_wifi_key(bsp_btn_t btn, bsp_btn_ev_t ev) {
    if (btn != BSP_BTN_OK || ev != BSP_BTN_CLICK || s_state != WIFI_DEMO_OFF) return;
    if (!bsp_lvgl_lock(250)) return;
    lv_label_set_text(s_results, "RSSI  SSID  CHANNEL");
    bsp_lvgl_unlock();
    (void)start_scan();                                // 重新发起扫描
}
```

注意 `key` 里**先持锁清屏、再发起扫描**——`start_scan` 本身不碰 LVGL，放在锁外也行，但清屏属于 UI 操作必须锁内。

## 29.9 这个 demo 能抄什么

- **完整的 STA 启动链**（NVS → netif → wifi_init → 注册事件 → set_mode → start → scan）；
- **用 checked 分步而非便利创建器**，让无线失败不重启；
- **`WIFI_STORAGE_RAM` + 不连接**，示例零副作用；
- **事件回调只改 `volatile` 状态，UI 交给 `tick` 单点渲染**；
- **`stop` 逆序回滚**整套栈。

和第 10 章的关系：第 10 章讲 Wi-Fi / HTTP / BLE 的原理与坑，本章是官方把"STA 扫描"做成健壮实例。
想看"连接 + 联网取数据"，第 10 章有通用骨架；但官方 demo 刻意止步于扫描，正是为了避免在示例里处理凭证。
