// 06 音频 worker：任务通知下单 + 停止握手（官方 demo_audio.c 的完整结构）。
//
// 结构：
//   按键回调（快，只发通知）──xTaskNotify──▶ audio worker（慢，阻塞也无所谓）
//   页面 stop() ────── 通知 STOP + 等信号量确认 ──────▶ worker 挂起，owner 删除
//
// 编译校验：snippets/check_snippets.py
#include "demo.h"

#include "bsp_audio.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

static const char *TAG = "audio_worker";

#define SAMPLE_RATE      16000
#define CHUNK_BYTES      2048       // 32000 B/s → 2048 B = 64ms（打断延迟上限）
#define STOP_TIMEOUT_MS  2000

typedef enum {
    AUDIO_CMD_PLAY = 1,
    AUDIO_CMD_STOP,
} audio_cmd_t;

static TaskHandle_t      s_task    = NULL;
static SemaphoreHandle_t s_stopped = NULL;
static volatile bool     s_cancel  = false;

// ---- 干活（只在 worker 里调用 bsp_audio_*）--------------------------------
static void play_pcm(const uint8_t *pcm, uint32_t bytes)
{
    if (!pcm || bytes == 0) return;                       // 防御：素材可能缺失
    if (bsp_audio_set_format(SAMPLE_RATE, 16, 1) != ESP_OK) return;
    bsp_audio_set_volume(80);

    uint32_t off = 0;
    while (off < bytes && !s_cancel) {                    // ★ 每块都检查取消
        uint32_t n = bytes - off;
        if (n > CHUNK_BYTES) n = CHUNK_BYTES;
        if (bsp_audio_write(pcm + off, n) != ESP_OK) {
            ESP_LOGE(TAG, "write 失败 @%u", (unsigned)off);
            break;
        }
        off += n;
    }
}

// ---- worker 主循环 ---------------------------------------------------------
static void audio_task(void *arg)
{
    (void)arg;
    for (;;) {
        uint32_t cmd = 0;
        if (xTaskNotifyWait(0, UINT32_MAX, &cmd, portMAX_DELAY) != pdTRUE) continue;
        if (cmd == AUDIO_CMD_STOP) break;
        if (cmd == AUDIO_CMD_PLAY) play_pcm(NULL, 0);     // 换成你的 PCM
    }

    // ★★ 不要 vTaskDelete(NULL)！
    // 先给确认，再自己挂起，等 owner 来删。
    // 这样 stop() 超时后重试也安全（handle 仍然有效）。
    xSemaphoreGive(s_stopped);
    for (;;) vTaskSuspend(NULL);
}

// ---- 页面 start()：不持 LVGL 锁 ------------------------------------------
esp_err_t demo_audio_worker_start(void)
{
    if (s_task) return ESP_OK;

    s_stopped = xSemaphoreCreateBinary();
    if (!s_stopped) return ESP_ERR_NO_MEM;

    s_cancel = false;
    // 栈 4096 字节，优先级 4（与 LVGL 同级）
    if (xTaskCreate(audio_task, "audio_w", 4096, NULL, 4, &s_task) != pdPASS) {
        vSemaphoreDelete(s_stopped);
        s_stopped = NULL;
        return ESP_ERR_NO_MEM;
    }
    return ESP_OK;
}

// ---- 页面 stop()：不持 LVGL 锁，必须等到确认 ------------------------------
esp_err_t demo_audio_worker_stop(void)
{
    TaskHandle_t task = s_task;
    if (!task) return ESP_OK;

    s_cancel = true;                                       // 让播放循环尽快退出
    xTaskNotify(task, AUDIO_CMD_STOP, eSetValueWithOverwrite);

    if (!s_stopped ||
        xSemaphoreTake(s_stopped, pdMS_TO_TICKS(STOP_TIMEOUT_MS)) != pdTRUE) {
        // ★ 超时必须返回错误：框架收到后会中止退出页面，
        //   而不是带着一个还在跑的后台任务切走。
        ESP_LOGW(TAG, "停止超时");
        return ESP_ERR_TIMEOUT;
    }

    vTaskDelete(task);              // worker 此时挂在 vTaskSuspend，安全删除
    s_task = NULL;
    vSemaphoreDelete(s_stopped);
    s_stopped = NULL;
    return ESP_OK;
}

// ---- 按键回调：只"下单"，函数立刻返回 -------------------------------------
void demo_audio_worker_key(bsp_btn_t btn, bsp_btn_ev_t ev)
{
    if (ev != BSP_BTN_CLICK || !s_task || s_cancel) return;
    if (btn == BSP_BTN_OK) {
        xTaskNotify(s_task, AUDIO_CMD_PLAY, eSetValueWithOverwrite);
    }
}
