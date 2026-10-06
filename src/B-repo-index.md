# B. 代表仓库索引

本书拆解的 5 个仓库，加上官方基线。

## B.1 五个实战仓库

| # | 仓库 | 下载量 | GitHub | 学什么 |
|---:|---|---:|---|---|
| 1 | `FoloToy/folo-ai-passport-xiaozhi` | 7244 | `github.com/FoloToy/folo-ai-passport-xiaozhi` | 单线程事件循环架构、Board 抽象、IDF 6 |
| 2 | `Luobata/ESP32-PokemonGo` | 2725 | `github.com/Luobata/ESP32-PokemonGo` | 后台世界任务、存档、开机自检、recovery |
| 5 | `Shinku-Chen/ai-passport` | 2299 | `github.com/Shinku-Chen/ai-passport` | 一仓多玩法（11 条 feature 分支）、音频播放、SPIFFS |
| 8 | `pax-zhang/ai-passport` | 1101 | `github.com/pax-zhang/ai-passport` | **页面栈架构**、18 步启动模板、扩展 BSP |
| 18 | `YeatsLiao/ai-passport-doom` | 511 | `github.com/YeatsLiao/ai-passport-doom` | 最小的可跑项目、分条刷屏、--wrap 技巧 |

**官方基线**（不在排名里，但是一切的基础）：

| 仓库 | GitHub | 说明 |
|---|---|---|
| `folotoy/ai-passport` | `github.com/folotoy/ai-passport` | BSP 与 demo 的源头，`bsp_pins.h` 在这里 |

> 上面表格里的 `GitHub` 列是**可直接 clone 的地址**，读者照抄即可。
> 作者本机为了批量扫描，把这些仓库镜像在 `D:\passport\<平台>\X__Y` 下
>（`__` 是平台名与仓库名之间的分隔），那套本地路径**不在书上、也不该出现在你的机器**。

## B.2 五个仓库的一张对照表

| | DOOM(#18) | pax-zhang(#8) | Shinku(#5) | PokeWalk(#2) | 小智(#1) |
|---|---|---|---|---|---|
| 语言 | C | C | C | C | **C++** |
| `main/` 位置 | 顶层 | 顶层 | 顶层 | **`firmware/`** | 顶层 |
| 源文件数 / 行数 | 1 / 80 | 36 / 12630 | 12 / 1715 | 67 / 17265 | 8 .cc / 3625（+47） |
| `components/bsp` | ❌（`bsp_doom`） | ✅ | ✅ | ✅ | ❌（自己的 `boards/`） |
| `partitions.csv` | ✅ | ✅ | ✅ | ✅ | ❌（`partitions/v2/`） |
| LVGL | **❌ 完全不用** | ✅ | ✅ | ✅ | ✅ (9.5) |
| IDF | 5.5.3+ | 5.5.3 | 5.5.3 | 5.5.3 | **≥6.0.1** |
| 素材存储 | 自定义分区 + mmap | NVS + EMBED 证书 | NVS / SPIFFS `voicefs` | NVS + EMBED（7 bin） | assets 分区 + mmap |
| 音频 | **禁用** | 播放 + 录音 | Opus 播放 | sfx/music/cry | Opus + 唤醒词 |
| 深睡 | ❌ | GPIO 唤醒 | ✅ `esp_deep_sleep_start` | 只查唤醒原因 | 未在主流程用 |
| 构建 | `idf.py build` | `idf.py build` | `validate.sh` | `fw.sh build` | `scripts/build.py` |
| 本书章节 | 13 | 14 | 15 | 16 | 17 |

## B.3 按"我想学什么"找仓库

| 你想做 | 去看 |
| --- | --- |
| 第一个能读懂的项目 | #18 DOOM（第 13 章） |
| 一个设备装多个玩法 | #8 pax-zhang 页面栈（第 14 章） |
| 播音效 / 语音 | #5 Shinku `feature/voice-keychain`（第 15 章） |
| 后台任务与存档 | #2 PokeWalk `world.c` / `save.c`（第 16 章） |
| AI 语音对话 | #1 小智（第 17 章） |
| 裸屏直推（不用 LVGL） | #18 DOOM `components/bsp_doom` |
| OTA 升级 | #1 小智 `partitions/v2/16m_c3.csv` |
| 自定义 bootloader / recovery | #2 PokeWalk `bootloader_components/` |
| 中文字体接入 | #8 pax-zhang `main/fonts/` |
| PC 侧素材处理管线 | #5 Shinku `tools/encode_voice.py`、#2 PokeWalk `tools/` |
| 主机端单元测试 | 官方基线 `tests/` |

## B.4 怎么读一个陌生仓库（5 步）

1. **读 README 的硬件/契约部分**——先知道它假设什么；
2. **`ls main/`**——看文件命名规律（有没有 `app_*.c`/`play_*.c` 的分组）；
3. **找 `app_main`**——`grep -rn "void app_main" main/`，读它的初始化顺序；
4. **找最大的文件**——领域逻辑通常在那里；
5. **读 `partitions.csv` 和 `sdkconfig.defaults`**——知道它的资源边界。

**不要从上往下通读。** 一个 17000 行的项目是无法通读的，
但你能用这 5 步在 20 分钟内知道它的骨架。

## B.5 使用社区的规矩

- **只提取需要的模式，不要把整个分支合并进来**——
  官方明确要求避免带入旧 BSP 和旧配置；
- **优先复用 `components/bsp/` 里的 `bsp_*` API**，不要重写驱动；
- **必须重新设计 UI**，不能沿用官方 demo 的外壳（第 20.2 节）；
- 引用别人的代码时保留出处。

## B.6 数据说明

本书中的统计数字来自**作者本地扫描**（截至 2026-10-05，来源：玩法社区公开数据，
非官方；路径以作者本机为准，读者无法复现同一路径）：**172 个仓库**样本。

- 平台分布：GitHub 155 / CNB 9 / Gitee 6 / GitCode 2
  （注意：样本中 CNB 只有 9 个，但**实际生态里 CNB 托管约 31 个**；本书样本偏重 GitHub，
  上面的比例不能当生态全景。）
- 126 位作者，328 个玩法条目
- 73,484 个受版本控制文件，单仓文件数中位数 **181**
- `components/bsp` 采用率 83%，自定义分区表 87%，`AGENTS.md` 70%
- 明示 IDF 版本的 110 个仓库里：5.5 有 105 个，6.x 只有 4 个

> **仓库可达性（截至 2026-10-05）**：玩法社区共 **334** 个带仓库链接的玩法，
> 对应 **239** 个有效仓库；其中约 **6** 个已 404 失效，例如
> `suikay/snack-rush`（零食冲刺）、`CoderSu/easy-go-home`（公路之王）。
> 书里引导你去社区找仓库时，遇到失效链接先换关键词或看 fork，能省时间。

全量清单在作者本地技能目录（`_仓库总索引.csv`、`reference-apps.md`）——
那是作者的工作素材，**不随本书发布**；上面这些聚合数字才是本书划定的范围。
