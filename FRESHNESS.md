# FRESHNESS.md — 教材事实复核清单

本教材追求"能查源码就不写据说"，但有一部分数字来自**会随时间变化的上游事实**
（官方仓库演进、社区版本分布、第三方仓库数量等）。这些数字在正文里都标了"数据截至"
注，本文件把它们集中成一份可重复的复核清单。

> 建议频率：**每 3–6 个月**复核一次，或在官方仓库有大版本发布（如 5.x→6.x 切换）时立即复核。
> 复核后把正文里的"数据截至 YYYY-MM-DD"同步更新。

---

## 1. 官方仓库状态（FoloToy/ai-passport）

| 要复核的事实 | 正文位置 | 复核命令 |
| --- | --- | --- |
| `main/` 下硬件测试页数量（现 7） | 23.2 / SUMMARY | `git clone` 后数 `main/demo_*.c` |
| `demo/*` 应用分支数量与名单（现 11） | 23.5 / E.4 | `git branch -r --list 'origin/demo/*'` |
| LVGL 绘制缓冲行数（现 40） | 5.3 / E.7 | 看 `components/bsp/` 里 `BSP_LVGL_DRAW_BUFFER_LINES` |
| 电池容量（现 520 mAh） | 8.1 | 看 BSP profile / 官方 specifications |
| 默认 `partitions.csv`（factory 偏移/长度） | 1.6 / 9.1 / 10c.6 | 看仓库根 `partitions.csv` |
| ESP-IDF 版本契约（现 5.5.3） | 02 开头 / 03.1 / 23.4 | `idf.py --version` + 看 `sdkconfig.defaults` 约束 |

## 2. 社区版本分布（会快速变化）

| 要复核的事实 | 正文位置 | 复核方法 |
| --- | --- | --- |
| 社区仓库总数 / 明示版本数 / 5.5 vs 6.x 占比（现 172 样本、105/110 在 5.5） | 23.4 / 23.5 / B.6 | 在本机或 GitHub 搜索 `ai-passport` / `FoloToy` 相关仓库，统计 `idf.py` 版本或 README 声明 |
| 第三方资源是否仍可用（TRAE 社区帖、deepseekagent Agent） | E.6 | 打开链接确认未 404、未改版 |

## 3. MicroPython 路线（FoloToy/ai-passport-micropython）

| 要复核的事实 | 正文位置 | 复核命令 |
| --- | --- | --- |
| 仓库仍维护、预编译固件版本 | B.7 / E.1 | `git ls-remote` 看最近提交；看 Release |
| 引脚定义是否与 C 版一致（关键：`mpconfigboard.h`） | B.7.2 | 比对 `ports/esp32/boards/FOLOTOY_AI_PASSPORT/mpconfigboard.h` 与 C 版 `bsp_pins.h` |
| `ST7789LVGL` 默认 `buffer_lines`（现 40） | B.7 | 看 board 驱动默认参数 |

## 4. 平台/工具链

| 要复核的事实 | 正文位置 | 复核命令 |
| --- | --- | --- |
| mdBook 版本（图标前缀 `fa-` 需 `fas/fab/far`） | book.toml | `mdbook --version` |
| 本机 IDF 安装路径 | 各章环境说明 | `echo $IDF_PATH` |

---

## 复核流程（建议）

1. 跑一遍 `mdbook build`，确认还能过（结构/链接没漂）。
2. 按上面 1–4 逐项执行命令，把新数字和旧数字对比。
3. 有变化的，回正文改数字 + 更新"数据截至"注。
4. 在 `ai-passport-course` 的提交里注明"事实复核：YYYY-MM-DD"。
5. 如有结构性变化（如官方改用新分区表、LVGL 升大版本），在 `E.7 官方源自己打架时` 追加一条。

> 本文件**不进书籍构建**（放在仓库根，不在 `src/` 下）。它只服务于维护者，不面向读者。
