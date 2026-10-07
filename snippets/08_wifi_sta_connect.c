// 08 STA 联网模块：连上 Wi-Fi、断线退避重连、逆序拆除。
//
// 这不是一个页面，是一个**联网模块**。对应教材第 10 章（10.1–10.5、10.11）：
//   - 完整启动链（netif → 事件循环 → wifi_init → 注册事件 → set_mode → start）
//   - 用"checked 分步"而不是会 assert 的便利创建器，让失败不重启（第 29.3 节）
//   - IP_EVENT_STA_GOT_IP 才算联网；断开 reason 一定要打印
//   - 重连：指数退避 + 抖动 + 上限，且不在事件回调里阻塞
//   - 拆除严格逆序：stop → 注销事件 → deinit → 销毁 netif
//
// 怎么跑起来：
//   1. 拷到官方工程的 main/ 下；
//   2. main/CMakeLists.txt 的 SRCS 里加上它；
//   3. 在 app_main()（或你的应用初始化处）调 net_wifi_start()。
//      真机验证前先把下面的 SSID/密码换成你自己的（或用第 10b 章的配网）。
//
// 编译校验：本文件用官方工程同一套参数编过（snippets/check_snippets.py）。
#include "esp_err.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "nvs_flash.h"

#include <string.h>

static const char *TAG = "net_wifi";

#define WIFI_SSID "你的WiFi"          // TODO 换成你的 2.4 GHz 网络
#define WIFI_PASS "你的密码"

#define WIFI_RETRY_BACKOFF_CAP_MS 30000   // 退避上限 30 s
#define WIFI_RETRY_GIVE_UP_AFTER  10      // 重试 N 次后放弃，转离线模式

typedef struct {
    bool        started;           // 射频已起
    bool        got_ip;            // ★ 唯一"已联网"标志
    int         retry;             // 连续重试次数
    volatile int last_reason;      // 最近一次断开原因（给 UI 翻译）
} net_state_t;

static net_state_t          s_net;
static esp_netif_t         *s_sta_netif;
static esp_event_handler_instance_t s_wifi_h;
static esp_event_handler_instance_t s_ip_h;
static bool                 s_wifi_inited;
static esp_timer_handle_t   s_retry_timer;

// ---------------------------------------------------------------------------
// 重连定时器：esp_timer 回调跑在自己的任务里，可以调 Wi-Fi API（不是 ISR）
// ---------------------------------------------------------------------------
static void retry_timer_cb(void *arg)
{
    (void)arg;
    if (s_net.started && !s_net.got_ip) {
        ESP_LOGI(TAG, "退避结束，重连（第 %d 次）", s_net.retry);
        // 失败也无所谓：DISCONNECTED 事件会再排下一次
        (void)esp_wifi_connect();
    }
}

static void schedule_retry(int reason)
{
    // 密码错/认证失败是**确定性**失败：再试一万次也是错，别折磨射频和电池
    if (reason == WIFI_REASON_4WAY_HANDSHAKE_TIMEOUT ||   // 15
        reason == WIFI_REASON_AUTH_FAIL ||                // 202
        reason == WIFI_REASON_ASSOC_FAIL) {               // 203
        ESP_LOGE(TAG, "凭据错误（reason=%d），停止重连，请重新配网", reason);
        s_net.retry = 0;
        return;
    }
    if (s_net.retry >= WIFI_RETRY_GIVE_UP_AFTER) {
        ESP_LOGE(TAG, "重试 %d 次仍失败，转离线模式", WIFI_RETRY_GIVE_UP_AFTER);
        return;                                          // ★ 有放弃路径
    }

    int backoff = 1000 << (s_net.retry < 5 ? s_net.retry : 5);   // 1→2→4→8→16→32 s
    if (backoff > WIFI_RETRY_BACKOFF_CAP_MS) backoff = WIFI_RETRY_BACKOFF_CAP_MS;
    backoff += (int)(esp_random() % 250);                        // 抖动，避免齐刷刷
    s_net.retry++;

    ESP_LOGW(TAG, "断开 reason=%d，%d ms 后重连", reason, backoff);
    // ★ 只"投递"，不在回调里 vTaskDelay / while 重试
    (void)esp_timer_stop(s_retry_timer);
    (void)esp_timer_start_once(s_retry_timer, (uint64_t)backoff * 1000ULL);
}

// ---------------------------------------------------------------------------
// 事件处理器：只改状态、只排定时器，不做任何阻塞操作
// ---------------------------------------------------------------------------
static void wifi_event_cb(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg;
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        ESP_LOGI(TAG, "STA 已启动，发起连接");
        (void)esp_wifi_connect();

    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_CONNECTED) {
        ESP_LOGI(TAG, "已关联 AP（还没拿到 IP）");

    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        wifi_event_sta_disconnected_t *d = (wifi_event_sta_disconnected_t *)data;
        // ★ reason 是排障的第一手信息，一定要打出来
        ESP_LOGW(TAG, "断开 ssid=%.32s rssi=%d reason=%d",
                 (const char *)d->ssid, d->rssi, d->reason);
        s_net.got_ip = false;
        s_net.last_reason = (int)d->reason;
        schedule_retry((int)d->reason);

    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *e = (ip_event_got_ip_t *)data;
        ESP_LOGI(TAG, "★ 已联网 IP=" IPSTR, IP2STR(&e->ip_info.ip));
        s_net.got_ip = true;
        s_net.retry = 0;                                  // 成功了就重置退避计数

    } else if (base == IP_EVENT && id == IP_EVENT_STA_LOST_IP) {
        ESP_LOGW(TAG, "IP 丢失");
        s_net.got_ip = false;
    }
}

// ---------------------------------------------------------------------------
// 启动 / 停止
// ---------------------------------------------------------------------------
static void wifi_stack_stop(void);

esp_err_t net_wifi_start(void)
{
    if (s_net.started || s_wifi_inited) return ESP_ERR_INVALID_STATE;

    esp_err_t err = nvs_flash_init();
    if (err != ESP_OK) {
        // ★ 不为了起无线而擦除 NVS：里面可能已经有用户数据（官方 demo_radio.c 的操守）
        ESP_LOGE(TAG, "NVS 初始化失败: %s（未自动擦除分区）", esp_err_to_name(err));
        return err;
    }

    // 这两步全局只能做一次；第二次调用会返回 ESP_ERR_INVALID_STATE，可以容忍
    (void)esp_netif_init();
    (void)esp_event_loop_create_default();

    // ★ 用检查过的分步链，不用 esp_netif_create_default_wifi_sta()：
    //   便利创建器在分配/挂处理失败时会直接 abort 重启。
    esp_netif_config_t netif_cfg = ESP_NETIF_DEFAULT_WIFI_STA();
    s_sta_netif = esp_netif_new(&netif_cfg);
    if (!s_sta_netif) { err = ESP_ERR_NO_MEM; goto fail; }
    err = esp_netif_attach_wifi_station(s_sta_netif);
    if (err != ESP_OK) goto fail;
    err = esp_wifi_set_default_wifi_sta_handlers();
    if (err != ESP_OK) goto fail;

    wifi_init_config_t wcfg = WIFI_INIT_CONFIG_DEFAULT();
    err = esp_wifi_init(&wcfg);
    if (err != ESP_OK) goto fail;
    s_wifi_inited = true;

    err = esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID,
                                              &wifi_event_cb, NULL, &s_wifi_h);
    if (err != ESP_OK) goto fail;
    err = esp_event_handler_instance_register(IP_EVENT, ESP_EVENT_ANY_ID,
                                              &wifi_event_cb, NULL, &s_ip_h);
    if (err != ESP_OK) goto fail;

    wifi_config_t cfg = { 0 };
    strncpy((char *)cfg.sta.ssid, WIFI_SSID, sizeof(cfg.sta.ssid) - 1);
    strncpy((char *)cfg.sta.password, WIFI_PASS, sizeof(cfg.sta.password) - 1);
    cfg.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;      // 低于此安全级不连

    err = esp_wifi_set_mode(WIFI_MODE_STA);
    if (err != ESP_OK) goto fail;
    err = esp_wifi_set_config(WIFI_IF_STA, &cfg);
    if (err != ESP_OK) goto fail;
    err = esp_wifi_start();                               // ★ 不等于连上了
    if (err != ESP_OK) goto fail;

    esp_timer_create_args_t tcfg = {
        .callback = &retry_timer_cb,
        .arg = NULL,
        .name = "wifi_retry",
    };
    if (esp_timer_create(&tcfg, &s_retry_timer) != ESP_OK) {
        ESP_LOGW(TAG, "重连定时器创建失败，将不做自动重连");
    }

    s_net.started = true;
    return ESP_OK;

fail:
    wifi_stack_stop();
    ESP_LOGE(TAG, "Wi-Fi 启动失败: %s", esp_err_to_name(err));
    return err;
}

// ★ 拆除顺序和启动严格相反、一步不漏
static void wifi_stack_stop(void)
{
    if (s_net.started) {
        (void)esp_wifi_disconnect();
        (void)esp_wifi_stop();                 // 会触发 STA_STOP，但事件处理器还没注销
        s_net.started = false;
    }
    if (s_wifi_h) {
        (void)esp_event_handler_instance_unregister(WIFI_EVENT, ESP_EVENT_ANY_ID, s_wifi_h);
        s_wifi_h = NULL;
    }
    if (s_ip_h) {
        (void)esp_event_handler_instance_unregister(IP_EVENT, ESP_EVENT_ANY_ID, s_ip_h);
        s_ip_h = NULL;
    }
    if (s_wifi_inited) {
        (void)esp_wifi_deinit();
        s_wifi_inited = false;
    }
    if (s_sta_netif) {
        esp_netif_destroy_default_wifi(s_sta_netif);
        s_sta_netif = NULL;
    }
    if (s_retry_timer) {
        (void)esp_timer_stop(s_retry_timer);
        (void)esp_timer_delete(s_retry_timer);
        s_retry_timer = NULL;
    }
    s_net.got_ip = false;
}

void net_wifi_stop(void)
{
    wifi_stack_stop();
}

bool net_wifi_is_up(void)
{
    return s_net.got_ip;                       // ★ 只有 GOT_IP 才是真的能发数据
}

int net_wifi_last_reason(void)
{
    return s_net.last_reason;
}

// 连上之后想看信号强度，不用再扫一次（扫描会打断射频）
int net_wifi_rssi(void)
{
    wifi_ap_record_t ap;
    if (!s_net.got_ip) return 0;
    if (esp_wifi_sta_get_ap_info(&ap) != ESP_OK) return 0;
    return ap.rssi;
}
