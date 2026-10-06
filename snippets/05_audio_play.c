// 05 播放声音：最小四步 + 分块送数据。
//
// ★ 铁律：bsp_audio_write() 是【阻塞】调用。
//   这个文件里的函数只能在【独立任务】里跑，
//   绝不能在按键回调或 LVGL 任务里调用 —— 否则按键和屏幕会卡死到播完。
//
// 完整 worker/停止握手见 06_audio_worker.c。
//
// 编译校验：snippets/check_snippets.py
#include "demo.h"

#include "bsp_audio.h"
#include "bsp_display.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <stdlib.h>

static const char *TAG = "audio";

#define SAMPLE_RATE   16000
#define TONE_HZ        1000
#define TONE_MS        1000
#define CHUNK_SAMPLES   512     // 每次送 512 采样 = 1024 字节 ≈ 32ms

// ---- 合成并播放一段 1kHz 方波（官方 demo_audio.c:45 的写法）--------------
static void play_tone(void)
{
    // 1) 定格式  2) 设音量 —— 顺序无所谓，但必须在 write 之前
    if (bsp_audio_set_format(SAMPLE_RATE, 16, 1) != ESP_OK) {
        ESP_LOGE(TAG, "set_format 失败");
        return;
    }
    bsp_audio_set_volume(80);

    int16_t *buf = malloc(CHUNK_SAMPLES * sizeof(int16_t));
    if (!buf) {
        ESP_LOGE(TAG, "分配失败");       // ★ 必须检查，别静默失败
        return;
    }

    const int period = SAMPLE_RATE / TONE_HZ;
    int total = SAMPLE_RATE * TONE_MS / 1000;
    int phase = 0;
    while (total > 0) {
        int n = total < CHUNK_SAMPLES ? total : CHUNK_SAMPLES;
        for (int i = 0; i < n; i++) {
            buf[i] = (phase < period / 2) ? 6000 : -6000;
            if (++phase >= period) phase = 0;
        }
        if (bsp_audio_write(buf, (size_t)n * sizeof(int16_t)) != ESP_OK) {
            ESP_LOGE(TAG, "write 失败");
            break;
        }
        total -= n;
    }
    free(buf);
}

// ---- 播放 Flash 里的一段裸 PCM（WAV 剥头后 EMBED_FILES 链入）--------------
// extern const uint8_t my_voice[] asm("_binary_my_voice_pcm_start");
// 长度同样写死字面量（两个 extern 符号相减不是常量表达式）。
static void play_pcm_flash(const uint8_t *pcm, uint32_t bytes)
{
#define CHUNK_BYTES 2048        // 16000*2 = 32000 B/s，2048 B = 64ms

    if (bsp_audio_set_format(SAMPLE_RATE, 16, 1) != ESP_OK) return;
    bsp_audio_set_volume(80);

    uint32_t off = 0;
    while (off < bytes) {
        uint32_t n = bytes - off;
        if (n > CHUNK_BYTES) n = CHUNK_BYTES;
        if (bsp_audio_write(pcm + off, n) != ESP_OK) break;   // pcm 指向 Flash，不占 RAM
        off += n;
    }
}

// ---- 录音 3 秒后回放（官方 demo_audio.c:72）-------------------------------
static void record_and_play(void)
{
    if (bsp_audio_set_format(SAMPLE_RATE, 16, 1) != ESP_OK) return;

    size_t total = (size_t)SAMPLE_RATE * 3;                 // 3 秒
    int16_t *rec = malloc(total * sizeof(int16_t));         // = 96 KB！
    if (!rec) {
        // ★ C3 无 PSRAM：96KB 可能分配不到。明确告知，别静默失败。
        ESP_LOGE(TAG, "录音缓冲 %u 字节分配失败（可缩短时长）",
                 (unsigned)(total * sizeof(int16_t)));
        return;
    }

    size_t got = 0;
    while (got < total) {
        size_t n = (total - got) < CHUNK_SAMPLES ? (total - got) : CHUNK_SAMPLES;
        if (bsp_audio_read(rec + got, n * sizeof(int16_t)) != ESP_OK) break;
        got += n;
    }

    bsp_audio_set_volume(80);
    size_t played = 0;
    while (played < got) {
        size_t n = (got - played) < CHUNK_SAMPLES ? (got - played) : CHUNK_SAMPLES;
        if (bsp_audio_write(rec + played, n * sizeof(int16_t)) != ESP_OK) break;
        played += n;
    }
    free(rec);
}

// ---- 任务入口：这些慢活都在这里跑 -----------------------------------------
static void audio_task(void *arg)
{
    (void)arg;
    bsp_audio_init();                       // 内部会调 bsp_i2c_init()（幂等）
    play_tone();
    (void)play_pcm_flash;
    (void)record_and_play;
    vTaskDelete(NULL);
}

void demo_audio_play_start(void)
{
    // 栈 4096 字节、优先级 4（与 LVGL 同级）
    xTaskCreate(audio_task, "audio_play", 4096, NULL, 4, NULL);
}

// ---------------------------------------------------------------------------
// 低功耗（别混用）：
//   light sleep 前 → bsp_audio_sleep()        （未播放过也有效，幂等）
//   light sleep 后 → bsp_audio_wake()         （恢复音量与格式）
//   仅 deep sleep  → bsp_audio_prepare_deep_sleep()（本次运行后 I2S 不可恢复）
