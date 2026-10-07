// 09 流式取数：用 esp_http_client 的事件回调接收响应，带硬上限、带 cleanup。
//
// 对应教材第 10c 章（10c.1–10c.3）：
//   - 用事件回调（不是 perform 一把梭），数据到达那一刻就处理掉
//   - 硬上限 + overflow 标记：响应再大也不会越界写
//   - Content-Length 可能是 -1（chunked），代码不能依赖它
//   - 无论成败都 esp_http_client_cleanup()，否则 socket 泄漏
//   - status != 200 要单独判断；HTTP_EVENT_ERROR 只说明"传输层出问题"
//
// 怎么跑起来：
//   1. 拷到官方工程的 main/ 下；
//   2. main/CMakeLists.txt 的 SRCS 里加上它，
//      并确认 main 依赖 esp_http_client（IDF 组件，一般已在 REQUIRES 里；
//      没有就加 PRIV_REQUIRES esp_http_client）；
//   3. 在联网成功后（IP_EVENT_STA_GOT_IP）调 net_fetch_text()。
//      ★ HTTPS 前必须先校时（SNTP），否则证书"尚未生效"必然握手失败。
//
// 编译校验：本文件用官方工程同一套参数编过（snippets/check_snippets.py）。
//          注意它的基准命令取自 esp_http_client 组件自己（main 默认不依赖它，
//          只有那条命令的 -I 里才有 esp_http_client.h）。
#include "esp_err.h"
#include "esp_http_client.h"
#include "esp_log.h"

#include <string.h>

static const char *TAG = "net_fetch";

// ★ 你自己定的硬上限。8 KB 是"我准备为这次请求付多少内存"的承诺，
//   不是对服务器的估计。响应超过它 → 直接判失败，绝不越界。
#define FETCH_BUF_SIZE 4096

typedef struct {
    char   *buf;
    size_t  cap;        // 可用容量（已为 '\0' 预留 1 字节）
    size_t  len;
    bool    overflow;
} fetch_body_t;

static esp_err_t http_event_cb(esp_http_client_event_t *evt)
{
    fetch_body_t *body = (fetch_body_t *)evt->user_data;

    switch (evt->event_id) {
    case HTTP_EVENT_ON_CONNECTED:
        ESP_LOGD(TAG, "TCP/TLS 已建立（还没发请求）");
        break;

    case HTTP_EVENT_ON_HEADER:
        // 每个响应头都会回调一次；想看 Content-Length 就在这里拦
        if (evt->header_key && strcasecmp(evt->header_key, "Content-Length") == 0) {
            ESP_LOGI(TAG, "Content-Length=%s", evt->header_value ? evt->header_value : "");
        }
        break;

    case HTTP_EVENT_ON_DATA: {
        if (evt->data_len == 0) break;                  // 空事件，忽略
        if (!body) break;

        // ★ 上限检查在 memcpy 之前：这是"不越界"的唯一保证
        if (body->len + evt->data_len > body->cap) {
            body->overflow = true;
            ESP_LOGW(TAG, "响应超过 %u 字节，丢弃后续数据", (unsigned)body->cap);
            break;
        }
        // evt->data 是内部缓冲，回调返回后失效——要留就拷走
        memcpy(body->buf + body->len, evt->data, evt->data_len);
        body->len += evt->data_len;
        break;
    }

    case HTTP_EVENT_ON_FINISH:
        ESP_LOGI(TAG, "接收完成，共 %u 字节", body ? (unsigned)body->len : 0);
        break;

    case HTTP_EVENT_ERROR:
        // DNS 失败、TCP 超时、TLS 握手失败都落在这里——所以要把日志写细一点
        ESP_LOGE(TAG, "传输层错误（DNS/TCP/TLS/超时，需结合 URL 与 SNTP 排查）");
        break;

    case HTTP_EVENT_DISCONNECTED:
        ESP_LOGD(TAG, "连接断开");
        break;

    default:
        break;
    }
    return ESP_OK;
}

/**
 * 取一段文本（JSON 之类）。
 * @param url      完整 URL，含 http:// 或 https://
 * @param out      调用方提供的缓冲（栈或静态都行，别在这里 malloc 大块）
 * @param out_cap  缓冲总字节数（函数会预留 1 字节放 '\0'）
 * @param out_len  实际写入长度（不含结尾 '\0'），可为 NULL
 * @return ESP_OK / 传输层错误码 / ESP_FAIL(HTTP 非 200) / ESP_ERR_NO_MEM(超限)
 */
esp_err_t net_fetch_text(const char *url, char *out, size_t out_cap, size_t *out_len)
{
    if (!url || !out || out_cap < 2) return ESP_ERR_INVALID_ARG;

    fetch_body_t body = {
        .buf = out,
        .cap = out_cap - 1,        // ★ 预留结尾 '\0'
        .len = 0,
        .overflow = false,
    };

    esp_http_client_config_t cfg = {
        .url = url,
        .method = HTTP_METHOD_GET,
        .timeout_ms = 8000,        // ★ 必设：不设的话网络不通会挂很久
        .event_handler = http_event_cb,
        .user_data = &body,
        .buffer_size = 1024,       // 内部单次接收缓冲，调大 ≠ 能收更大响应
    };

    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    if (!client) return ESP_ERR_NO_MEM;

    esp_err_t err = esp_http_client_perform(client);
    int  status   = esp_http_client_get_status_code(client);
    int64_t clen  = esp_http_client_get_content_length(client);   // 可能是 -1（chunked）

    esp_http_client_cleanup(client);      // ★ 成败都要调：socket 和缓冲在这里释放

    if (err != ESP_OK) {
        ESP_LOGE(TAG, "perform 失败: %s", esp_err_to_name(err));
        return err;                       // DNS/TCP/TLS/超时
    }
    if (status != 200) {
        ESP_LOGW(TAG, "HTTP %d（301/302 看下 max_redirection_count）", status);
        return ESP_FAIL;
    }
    if (body.overflow) {
        ESP_LOGE(TAG, "响应超过上限 %u 字节（要么调大缓冲，要么改流式解析）",
                 (unsigned)body.cap);
        return ESP_ERR_NO_MEM;
    }

    out[body.len] = '\0';
    if (out_len) *out_len = body.len;
    ESP_LOGI(TAG, "OK: %u 字节（声明长度 %lld）", (unsigned)body.len, (long long)clen);
    return ESP_OK;
}

// ---------------------------------------------------------------------------
// 下载大文件（固件/音频/图片）：看到响应头之后边收边写，绝不攒在内存里
// ---------------------------------------------------------------------------
// 参数 write_chunk 由调用方实现（写 Flash / 喂解码器 / 推给屏幕）
esp_err_t net_download_stream(const char *url,
                              esp_err_t (*write_chunk)(const void *data, size_t len, void *ctx),
                              void *ctx)
{
    if (!url || !write_chunk) return ESP_ERR_INVALID_ARG;

    esp_http_client_config_t cfg = {
        .url = url,
        .method = HTTP_METHOD_GET,
        .timeout_ms = 30000,               // 下载给长一点，但依然要有上限
    };
    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    if (!client) return ESP_ERR_NO_MEM;

    esp_err_t err = esp_http_client_open(client, 0);
    if (err != ESP_OK) { esp_http_client_cleanup(client); return err; }

    int64_t total = esp_http_client_fetch_headers(client);
    ESP_LOGI(TAG, "响应长度=%lld（-1 表示 chunked，按流式处理）", (long long)total);

    char buf[1024];                        // 固定分块，和 total 无关
    int  got;
    while ((got = esp_http_client_read(client, buf, sizeof(buf))) > 0) {
        esp_err_t werr = write_chunk(buf, (size_t)got, ctx);
        if (werr != ESP_OK) { err = werr; break; }   // 写入失败也要走完整清理
    }
    if (got < 0) err = ESP_FAIL;                     // 读出错（不是读到 0）

    esp_http_client_close(client);
    esp_http_client_cleanup(client);
    return err;
}

// 一个用起来的样子
static char s_body[FETCH_BUF_SIZE];

void net_fetch_demo(void)
{
    size_t len = 0;
    esp_err_t err = net_fetch_text("https://api.example.com/data", s_body, sizeof(s_body), &len);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "取数失败: %s —— 显示缓存/离线文案，别把 UI 卡死", esp_err_to_name(err));
        return;
    }
    ESP_LOGI(TAG, "拿到 %u 字节，前 64 字节：%.64s", (unsigned)len, s_body);
}
