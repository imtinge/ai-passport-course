# 16. 实战四：PokeWalk（后台世界与存档）

| 项目 | 值 |
| --- | --- |
| 排名 | #2 |
| 下载量 | 2725 |
| 仓库 | `github.com/Luobata/ESP32-PokemonGo` |
| 规模 | `firmware/main/` **72 个 .c，17265 行** |
| IDF | 5.5.3 |
| 注意 | 固件在 **`firmware/` 子目录**，顶层没有 `main/` |

**为什么拆解它**：这是社区里**最复杂的养成类项目**（72 个源文件、17000 行）。
它展示的不是某个功能怎么实现，而是**当项目大到一定程度时，
怎么保证逻辑不随页面消失、数据不丢**。

## 16.1 工程结构（注意 firmware/ 子目录）

```text
ESP32-PokemonGo/
├── firmware/                        ← ★ 真正的 ESP-IDF 工程在这
│   ├── CMakeLists.txt  partitions.csv  sdkconfig.defaults
│   ├── bootloader_components/recovery_boot_hook/   ← 自定义 bootloader
│   ├── components/bsp/
│   └── main/  (72 个 .c)
├── assets/      ← 二进制素材（gen1.bin、palettes.bin、font16.bin ...）
├── data/        ← 原始数据
├── sim/         ← PC 端模拟器
├── tools/       ← 设备与素材工具
└── docs/  reports/
```

`main/` 里最大的几个文件：

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `world.c` | 2021 | **后台世界**（本章主角） |
| `play_battle.c` | 871 | 战斗玩法页 |
| `play_capture.c` | 617 | 捕捉玩法页 |
| `sensing.c` | 608 | 感知（环境数据） |
| `battle_fx.c` | 545 | 战斗特效 |
| `assets.c` | 492 | 素材解析 |
| `save.c` | 343 | 存档 |
| `main.c` | 227 | 入口 |

**命名规律值得学**：`play_*.c` 是页面，`*.c` 是领域逻辑。
`world.c` 不属于任何页面——这是本章的重点。

## 16.2 招牌实现：后台世界任务

> 源码：`firmware/main/world.c`

```c
    // 4096 栈：大数组都是 static，栈上只有指针与循环变量。
    // 优先级 4 —— 低于 LVGL（5），扫描不该抢画面的 CPU。
    BaseType_t ok = xTaskCreate(world_task, "world", 4096, NULL, 4, NULL);
```

```c
    for (;;) {
        int64_t now = esp_timer_get_time();

        // 养成结算。**放在这里而不是页面的 tick 里** ——
        // 页面切换不该影响宠物的时间流逝，而且 P1 不在前台时
        // 它的 lv_timer 根本不跑。
        if (lock_encounter_change()) {
            refresh_clock_locked();
            if (!s_starter_pending) nurture_tick(&s_w.pet, now, 0, false);
            unlock_encounter_change();
        }

        if (s_wifi_ok && scan_allowed && now >= next_scan) {
            scan_once();
            next_scan = esp_timer_get_time()
                      + scan_pacing_next(&pacing, off, s_scan_stable) * 1000LL;
        }

        // 节流存档
        bool save_due = false;
        if (s_lock && xSemaphoreTake(s_lock, pdMS_TO_TICKS(100)) == pdTRUE) {
            save_due = s_dirty && now - s_last_save_us >= SAVE_INTERVAL_US;
            xSemaphoreGive(s_lock);
        }
        if (save_due) save_now("定时");
    }
```

**这个任务解决了三个真实的 bug：**

**Bug 1：时间停了。** 养成结算原本挂在某个页面的 `lv_timer` 上。
玩家切走那一页，定时器不跑，宠物的时间就停了。

**Bug 2：一晚上的数据全丢了。** Wi-Fi 扫描原本绑在 Collect 页，
离开那页就停——"导致一晚上的采集数据全丢"。

**Bug 3：射频被抢。** Collect 页自己 `bring_up` Wi-Fi，
而 world 也管 Wi-Fi，"两个所有者会争同一个射频"。

**统一解法**：把时间流逝、联网采集、养成结算搬进一条**与页面无关的常驻任务**。

设计要点：

- 优先级 **4**（与官方基线的 LVGL 任务同级；源码注释写的"LVGL（5）"是
  **本项目自己的配置**）——不抢画面的 CPU；
- 栈 4096，**大数组都是 static**；
- 两把锁：`s_lock`（状态）、`s_save_lock`（存档），**取锁带超时**（100 ms）；
- 存档**节流**（`s_dirty` + `SAVE_INTERVAL_US`），不每次变化都写 flash。

## 16.3 存档的三条教训

> 源码：`firmware/main/save.c`

**教训 1：NVS 初始化是谁的责任。**

> "第一版没有这个函数——`nvs_flash_init` 藏在 `world.c` 的 `wifi_bring_up()` 里，
> 而 `world_start` 的顺序是'先读档、后起 WiFi'。于是读档时 NVS 还没挂载，
> `nvs_open` 直接失败，**表现为'每次开机都是新游戏'而写入明明成功**。
> 教训是所有权：存档不依赖 WiFi，就不该等 WiFi 顺手把 NVS 带起来。"

**教训 2：`nvs_commit()` 不能省。**

> "**commit 不能省**——`nvs_set_blob` 只写进缓存，
> 不 commit 的话拔电就丢了，**而函数返回值是成功的**。"

**教训 3：整块存比分开存原子性好。**

> "整块约 2.2 KiB，NVS 的 blob 上限是 508000 字节——绰绰有余。
> **原子性也更好**：要么整块新的，要么整块旧的，不会出现
> '图鉴是新的而队列是旧的'这种半更新状态。"

（完整的 NVS 用法见第 9 章。）

## 16.4 开机自检：一个值得抄的习惯

`app_main` 里有一段"自检五连"，放在**最前面**：

```c
    // 资产自检 —— 数字要与 PC 侧 inventory_assets.py 对得上。
    // 放在最前面：资产错了后面全是错的，早报早知道。
    if (assets_init()) assets_selftest();
    sens_selftest();
    nurture_selftest();
    enc_selftest();
    if (render_init()) render_selftest();
```

**思路**：素材是 PC 侧生成的二进制文件，和固件代码天然不同步。
与其等到游戏里出现"错误的宝可梦"，不如开机就校验一遍。

这个习惯在嵌入式开发里很值钱：**数据错了要早报错**。
（素材解析的三条纪律见第 9.5 节。）

## 16.5 入口的第一个动作：静音

```c
void app_main(void) {
    // First app action: silence a connected PA and, in silent builds, the
    // codec before scans, display initialization, gameplay or debug tasks.
    esp_err_t quiet = bsp_audio_boot_quiet();
    if (quiet != ESP_OK) ESP_LOGE(TAG, "Early audio shutdown failed: %s",
                                  esp_err_to_name(quiet));
    // ...
}
```

（详见第 7.6 节。）

## 16.6 三条不能改的契约

`firmware/README.md` 里明确写了：

> - app 分区上限 **3 MB**
> - `cardid` @ `0x356000`
> - `recovery` @ `0x700000` 永久保留，**上键长按 5 秒**进入
>
> `CMakeLists.txt` 里那段 `BOOTLOADER_EXTRA_COMPONENT_DIRS` 就是保证第三条的，
> 删了会让 USB 开发把设备卡在小程序安装路径之外。

**这是一个"产品级"项目的标志**：它不只是能跑，还考虑了
"万一固件坏了怎么救回来"（recovery 分区）。

## 16.7 一段罕见的自我检讨

`main.c` 里有一段注释，坦白了一个已经修掉的越界 bug：

```c
    // ⚠️ 这里曾经写到 s_ok[6]，而 s_ok 是 [DEMO_COUNT] = [4] ——
    // **越界写 2 字节**。上游有 7 个 demo，我把 DEMOS 表砍到 4 项时
    // 忘了跟着改。没炸只是运气（那两字节后面恰好不是活跃数据）。
    // 现在按 DEMO_COUNT 循环，改表时不会再漏。
```

**这是本书最喜欢的一段注释。** 它说明三件事：

1. 数组越界在嵌入式上经常"不炸"，只是运气好；
2. 从上游 fork 代码时，删表项要同步删数组大小；
3. **把 bug 的原因写进注释**，比默默修掉有价值得多。

## 16.8 真机实测数据

README 里有一组实测，是很好的参考基线：

```text
固件 1.22 MB → factory 3MB 分区的 41%，余量 1.78 MB
可用堆 231 KB（101+113+10+7）—— 比上游固件多 44 KB，因为砍了 BLE
电池 优特利 520mAh（文档原写 500mAh）
I2C  0x18 ES8311 音频 codec · 0x63 CW2017 电量计
```

**231 KB 可用堆**，和第 11 章的数字对上了。
**"砍了 BLE 多 44 KB"**——这是做取舍时的具体依据。

## 16.9 构建方式（不走裸 idf.py）

```bash
source tools/device/idf-env.sh     # 进 ESP-IDF 环境
tools/device/fw.sh backup          # ★ 备份设备当前 flash（首次必做）
tools/device/fw.sh build
tools/device/fw.sh flash           # 没备份会拒绝烧写
python3 tools/device/monitor.py
```

**"没备份会拒绝烧写"**——这是本项目的一个设计决定。
它和小智项目"不备份"的态度相反（第 3.5 节提过）。
**开发你自己的项目时，建议学 PokeWalk：先备份再烧。**

## 16.10 你能从它抄走什么

| 想抄的东西 | 在哪 |
| --- | --- |
| 后台常驻任务（与页面解耦） | `firmware/main/world.c` |
| 存档节流 + 双锁 | `world.c` + `save.c` |
| 开机自检 | `main.c` 的自检五连 |
| 素材 PC 生成 + 设备解析 + 校验 | `assets.c` + `tools/` |
| recovery 分区与 bootloader hook | `bootloader_components/` |
| 备份优先的烧写流程 | `tools/device/fw.sh` |

## 16.11 小结

- **逻辑不该挂在页面上**：时间流逝、联网采集要放进常驻任务；
- 一个射频一个主人；存档不依赖 Wi-Fi；
- 开机自检：数据错了要早报；
- 存档要 `commit`、要节流、整块存更原子；
- **把 bug 的原因写进注释**；
- 231 KB 可用堆是实测基线，砍 BLE 能换回 44 KB。
