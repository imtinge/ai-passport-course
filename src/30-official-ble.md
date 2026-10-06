# 30. 官方 BLE 示例：NimBLE 广播

源码：`main/demo_ble.c`（279 行）+ 辅助 `main/demo_radio.c/.h`。它演示**用 NimBLE 起一个非连接广播**，
手机蓝牙扫描能搜到 `FoloPassport`。BLE 比 Wi-Fi 多一层"host 任务"的所有权管理，是官方里
**停止握手最复杂**的一个 demo。

> 行号来自官方基线 `main/demo_ble.c`。

## 30.1 它验证什么

| 操作 | 行为 |
| --- | --- |
| 打开页面 | 自动起 NimBLE host、开始广播，手机可扫到 `FoloPassport` |
| OK（短按） | 在广播态重启广播 |
| OK（长按） | 返回菜单（框架拦截） |

源码注释（`demo_ble.c:1`）：`// main/demo_ble.c —— NimBLE 广播示例；手机可扫描到 FoloPassport。`

## 30.2 NimBLE 需要自己的 host 任务

Wi-Fi 的协议栈由 ESP-IDF 托管；**NimBLE 的 host 协议栈要你自己起一个任务跑 `nimble_port_run()`**：

```c
// main/demo_ble.c:95-103
static void host_task(void *arg) {
    (void)arg;
    nimble_port_run();
    // Do not use the port wrapper: it keeps a private task handle and ignores
    // task-creation failure. This demo owns creation, acknowledgement and deletion.
    xSemaphoreGive(s_host_stopped);                  // ★ 通知 stop()："host 停了"
    for (;;) vTaskSuspend(NULL);                     // ★ 挂起，等 stop() 来 vTaskDelete
}
```

和 Audio 页（第 27 章）**同一套 worker-stop 模板**：任务跑完协议栈后 `xSemaphoreGive(s_host_stopped)`
+ `vTaskSuspend`，由 `stop()` 统一 `vTaskDelete`。源码注释特意解释**为什么不用 NimBLE 的 port 封装器
（`nimble_port_freertos_init`）**：那个封装器藏着任务句柄、且忽略任务创建失败——本 demo 要自己掌控
创建/确认/删除的全流程，所以手写 `host_task` + `xTaskCreatePinnedToCore`。

## 30.3 广播内容 + gap 回调

```c
// main/demo_ble.c:46-76
static int advertise(void) {
    struct ble_hs_adv_fields fields = { 0 };
    fields.flags = BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP;
    fields.name = (const uint8_t *)DEVICE_NAME;      // "FoloPassport"
    fields.name_len = strlen(DEVICE_NAME);
    fields.name_is_complete = 1;

    int rc = ble_gap_adv_set_fields(&fields);
    if (rc != 0) return rc;

    struct ble_gap_adv_params params = { 0 };
    params.conn_mode = BLE_GAP_CONN_MODE_NON;        // ★ 非连接（只广播，不可连）
    params.disc_mode = BLE_GAP_DISC_MODE_GEN;
    rc = ble_gap_adv_start(s_addr_type, NULL, BLE_HS_FOREVER, &params, gap_event, NULL);
    if (rc == 0) s_state = BLE_DEMO_ADVERTISING;
    return rc;
}

static int gap_event(struct ble_gap_event *event, void *arg) {
    (void)arg;
    if (event->type == BLE_GAP_EVENT_ADV_COMPLETE && s_start_requested) {
        int rc = advertise();                       // 广播自然结束 → 重新广播
        if (rc != 0) { s_error = rc; s_state = BLE_DEMO_FAILED; }
    }
    return 0;
}
```

`conn_mode = BLE_GAP_CONN_MODE_NON` 表示**只广播、不可连接**——这正是"让手机能发现设备"的最小集，
不牵扯 GATT 连接管理。广播若自然结束（`ADV_COMPLETE`），回调里重新 `advertise()`，保持持续可见。

## 30.4 `on_reset` / `on_sync`：host 同步后才广播

```c
// main/demo_ble.c:78-93
static void on_sync(void) {
    int rc = ble_hs_util_ensure_addr(0);
    if (rc == 0) rc = ble_hs_id_infer_auto(0, &s_addr_type);   // 推断本机地址类型
    if (rc == 0 && s_start_requested) rc = advertise();        // 同步完成 → 开始广播
    if (rc != 0) { s_error = rc; s_state = BLE_DEMO_FAILED; }
}
```

NimBLE 的 host 起来后有 `sync` 回调（协议栈就绪），**必须在 `on_sync` 里才调用 `advertise()`**——
协议栈没同步就广播会失败。这是 NimBLE 的固定时序，照抄即可。

## 30.5 `start`：完整的 NimBLE 启动链 + 失败清理

```c
// main/demo_ble.c:105-167（节选）
esp_err_t demo_ble_start(void) {
    if (s_initialized) { ... return ESP_ERR_INVALID_STATE; }
    s_state = BLE_DEMO_STARTING;
    s_stop_in_progress = false; s_host_done = false;
    esp_err_t err = demo_radio_nvs_prepare();                 // NVS（不擦用户数据）
    if (err != ESP_OK) { ... return err; }
    err = nimble_port_init();
    if (err != ESP_OK) { ... return err; }
    s_initialized = true;
    s_host_stopped = xSemaphoreCreateBinary();
    if (!s_host_stopped) { err = ESP_ERR_NO_MEM; goto failed_start; }

    ble_svc_gap_init(); ble_svc_gatt_init();
    int rc = ble_svc_gap_device_name_set(DEVICE_NAME);        // 设广播名
    if (rc != 0) { ... err = ESP_FAIL; goto failed_start; }
    ble_hs_cfg.reset_cb = on_reset;
    ble_hs_cfg.sync_cb = on_sync;
    s_start_requested = true;
    if (xTaskCreatePinnedToCore(host_task, "nimble_host", NIMBLE_HS_STACK_SIZE,
                                NULL, configMAX_PRIORITIES - 4, &s_host_task,
                                NIMBLE_CORE) != pdPASS) {
        err = ESP_ERR_NO_MEM; goto failed_start;
    }
    return ESP_OK;

failed_start:
    // No host task exists, so nimble_port_stop() would return BLE_HS_EALREADY.
    // Directly deinitialize; retain ownership if cleanup itself needs a retry.
    s_start_requested = false;
    esp_err_t cleanup = demo_ble_stop();                       // ★ 失败也走停止链
    ...
    return err;
}
```

注意 `failed_start` 里**即使启动中途失败也调 `demo_ble_stop()` 做逆序清理**——和 Wi-Fi 页（第 29 章）
的 `goto fail → wifi_stack_stop()` 同一纪律。`NIMBLE_CORE` 把 host 任务绑到特定核，优先级
`configMAX_PRIORITIES - 4`（较高，因为协议栈要及时）。

## 30.6 `stop`：防重入的三段式停止握手

```c
// main/demo_ble.c:169-218（节选）
esp_err_t demo_ble_stop(void) {
    s_start_requested = false;
    if (!s_initialized) return ESP_OK;
    if (s_host_task && !s_stop_in_progress) {
        (void)ble_gap_adv_stop();                             // ① 停广播
        int rc = nimble_port_stop();                          // ② 停 host
        if (rc != 0) { ... return ESP_FAIL; }
        s_stop_in_progress = true;
    }
    if (s_host_task && !s_host_done) {
        if (!s_host_stopped ||
            xSemaphoreTake(s_host_stopped, pdMS_TO_TICKS(BLE_STOP_TIMEOUT_MS)) != pdTRUE) {
            ... return ESP_ERR_TIMEOUT;                       // ③ 等 host 任务确认挂起
        }
        s_host_done = true;
    }
    if (s_host_task) { vTaskDelete(s_host_task); s_host_task = NULL; }   // ④ 删任务
    esp_err_t err = nimble_port_deinit();                     // ⑤ 反初始化
    ...
    s_initialized = false;
    if (s_host_stopped) { vSemaphoreDelete(s_host_stopped); s_host_stopped = NULL; }
    s_state = BLE_DEMO_OFF;
    return ESP_OK;
}
```

比 Audio 页更复杂的点：**`s_stop_in_progress` / `s_host_done` 两个标志防止重复进入停止流程**。
因为 `demo_ble_stop()` 在 `start` 的 `failed_start` 里也会被调用（半初始化状态），必须保证多次调用安全。
① 停广播 → ② `nimble_port_stop` 让 `host_task` 跑完并 `give(s_host_stopped)` → ③ 等信号量确认
→ ④ `vTaskDelete` → ⑤ `nimble_port_deinit`。**这套"停协议栈 + 等任务确认 + 删任务 + 反初始化"的顺序不能乱。**

## 30.7 `tick` / `enter` / `exit` / `key`

```c
// main/demo_ble.c:220-278（节选）
static void tick(lv_timer_t *timer) {
    (void)timer;
    switch (s_state) {
    case BLE_DEMO_STARTING:     lv_label_set_text(s_status, "Starting NimBLE..."); break;
    case BLE_DEMO_ADVERTISING:  lv_label_set_text(s_status,
        "ADVERTISING\n\nName: FoloPassport\n\nUse a BLE scanner\non your phone.\n\nOK: RESTART ADV"); break;
    case BLE_DEMO_FAILED:       lv_label_set_text_fmt(s_status, "BLE failed: %d", s_error);
                                s_state = BLE_DEMO_OFF; break;
    default: break;
    }
}
```

`tick` 单点渲染（和 Wi-Fi 同款状态机模式）；`enter` 建屏 + 起 timer + 置 `STARTING`；`exit` 删 timer + 删屏；
`key` 只在 `ADVERTISING` 态响应 OK 重启广播（`ble_gap_adv_stop()` 再 `advertise()`）。

## 30.8 这个 demo 能抄什么

- **NimBLE 非连接广播最小集**：`adv_fields`（name + flags）→ `adv_start(CONN_MODE_NON)`；
- **host 任务所有权 + 停止握手**：手写 `host_task` + `xSemaphoreGive` + `vTaskSuspend`，不用封装器；
- **`on_sync` 之后才广播**的 NimBLE 固定时序；
- **防重入的 `s_stop_in_progress` / `s_host_done`**：`stop` 可能被失败清理路径重复调用；
- **失败也走 `stop` 逆序清理**（和 Wi-Fi 同纪律）。

和第 10 章、第 29 章的关系：第 10 章讲 BLE 原理；第 29 章是同样的"进页面起栈、出页面逆序回滚"思路，
只是 BLE 多了一层 host 任务所有权。把这两章对照读，你就掌握了"官方怎么安全地开关一个协议栈"。
