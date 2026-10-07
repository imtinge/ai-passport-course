// 07 音频收尾：让最后一段语音【真的说完】再关设备。
//
// ★ 本书要纠正的一个常见误解：
//     bsp_audio_write() 返回 ≠ 声音已经响完。
//
//   它只阻塞到【I2S 的 DMA 缓冲收下数据】，此刻声音还在队列里排队，
//   喇叭可能一个字都没出。而 bsp_audio_prepare_deep_sleep() 内部会
//   i2s_channel_disable() —— **不等 DMA 排空**，队列里剩下的数据直接丢弃。
//
//   典型故障：长按关机要播"再见"，用户一个字都听不到。
//   排查时先分清两种根因（第 7.2 / 21.8 节）：
//     一个字都听不到  → write 之前就失败了（格式没设 / codec 被 sleep）
//     听到开头就断    → DMA 没排空就被掐断 ← 本文件解决这个
//
//   同时演示另一个坑：bsp_audio_sleep() 是【单向门】，
//   sleep 之后 set_format()/write() 全部静默失败，必须 wake() 才恢复。
//
// 怎么用：把 wait_audio_drained() 拷进你的工程，
//   凡是"下一步要关 I2S / 停 codec / 断电"的地方，写在最后一次 write 之后。
//   只是接着播下一段则【不要等】—— DMA 会自己续上，等待反而造成断续。
//
// 编译校验：snippets/check_snippets.py
#include "demo.h"

#include "bsp_audio.h"
#include "bsp_battery.h"
#include "bsp_display.h"
#include "bsp_i2c.h"
#include "esp_log.h"
#include "esp_sleep.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <stddef.h>

static const char *TAG = "audio_drain";

#define SAMPLE_RATE  16000
#define DRAIN_MARGIN_MS 120     // 覆盖 PA 上电斜坡与最后一块 DMA 描述符的尾段

// ---- 核心：按字节数算出时长，显式等 DMA 排空 ------------------------------
// 16 kHz / 16 bit / 单声道：每秒 = 16000 × 2 = 32000 字节
//   时长(ms) = bytes * 1000 / 32000 = bytes / 32
// 用整数除法即可，不需要 uint64_t（几万字节远在 32 位范围内）。
static void wait_audio_drained(size_t bytes_written)
{
    uint32_t ms = (uint32_t)(bytes_written / 32u) + DRAIN_MARGIN_MS;
    ESP_LOGI(TAG, "等待 %u 字节排空：%u ms", (unsigned)bytes_written, (unsigned)ms);
    vTaskDelay(pdMS_TO_TICKS(ms));
}

// ---- 播一段 Flash 里的裸 PCM（EMBED_FILES 链入，不占 RAM）-----------------
#define CHUNK_BYTES 2048        // = 1024 采样 = 64 ms

static void play_pcm_flash(const uint8_t *pcm, size_t bytes)
{
    if (bsp_audio_set_format(SAMPLE_RATE, 16, 1) != ESP_OK) {
        ESP_LOGE(TAG, "set_format 失败——素材格式必须是 16000/16/1");
        return;
    }
    bsp_audio_set_volume(75);

    size_t off = 0;
    while (off < bytes) {
        size_t n = bytes - off;
        if (n > CHUNK_BYTES) n = CHUNK_BYTES;
        if (bsp_audio_write(pcm + off, n) != ESP_OK) {
            ESP_LOGE(TAG, "write 失败（codec 是否已被 sleep？见下方单向门）");
            return;
        }
        off += n;
    }
}

// ---- 场景 A：播完道别语再关机（没有这一步，语音会被掐断）------------------
// 调用后设备进 deep sleep，【不会返回】。
static void say_goodbye_then_shutdown(const uint8_t *bye_pcm, size_t bye_bytes)
{
    bsp_audio_init();
    play_pcm_flash(bye_pcm, bye_bytes);

    // ★★★ 关键一行：没有它，下面的 prepare_deep_sleep 会把队尾直接丢掉 ★★★
    wait_audio_drained(bye_bytes);

    // 外设收尾顺序即依赖（第 7.8 节）：电量计 → codec → I2S 引脚 → I2C
    bsp_battery_sleep();
    bsp_audio_sleep();
    bsp_audio_prepare_deep_sleep();
    bsp_i2c_prepare_deep_sleep();
    // bsp_display_prepare_deep_sleep();   // 需要 UI 时再关屏，注意要先持 LVGL 锁

    esp_deep_sleep_start();     // 不返回；醒来 = 应用重启
}

// ---- 场景 B：bsp_audio_sleep() 是单向门，之后再播必须先 wake() ------------
static void play_again(const uint8_t *pcm, size_t bytes);

static void demo_sleep_gate(const uint8_t *pcm, size_t bytes)
{
    bsp_audio_init();
    play_pcm_flash(pcm, bytes);

    // ❌ 错误写法：sleep 之后还想接着播
    bsp_audio_sleep();                  // 为了省电 suspend codec
    // bsp_audio_set_format(...)  → 直接返回 ESP_ERR_INVALID_STATE
    // bsp_audio_write(...)       → 内部 s_dev 为 NULL，一个字节都写不出去
    // 而且这些都是【静默失败】：UI 看不出异常，只表现为"突然没声音了"。

    // ✅ 正确写法：用之前一定先 wake（幂等，重复调用无害）
    if (bsp_audio_wake() != ESP_OK) {
        ESP_LOGE(TAG, "wake 失败");
        return;
    }
    play_again(pcm, bytes);
}

static void play_again(const uint8_t *pcm, size_t bytes)
{
    play_pcm_flash(pcm, bytes);
    // 注意这里【不】调 wait_audio_drained：页面照常运行、不关 I2S，
    // 让它自然播完就好。只有"要断电/停 I2S"时才需要等。
}

// ---- 任务入口：这些慢活必须在独立任务里跑 ---------------------------------
static void audio_task(void *arg)
{
    (void)arg;
    bsp_audio_init();           // 内部会调 bsp_i2c_init()（幂等）
    (void)say_goodbye_then_shutdown;
    (void)demo_sleep_gate;
    vTaskDelete(NULL);
}

void demo_audio_drain_start(void)
{
    xTaskCreate(audio_task, "audio_drain", 4096, NULL, 4, NULL);
}
