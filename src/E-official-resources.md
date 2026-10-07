# E. 官方与社区资源地图

> 这一章不教技术，只回答一个问题：**遇到问题/想找参考时，该去哪儿查、按什么顺序查。**
>
> 每个链接后面都标了"这是什么、什么时候看它"。
> 书里正文引用过的事实，出处仍然以正文为准；本附录只负责**把门指出来**。

---

## E.1 四个官方入口

| 入口 | 链接 | 这是什么、什么时候看 |
| --- | --- | --- |
| 产品官网 | https://ai-passport.folotoy.cn/ | 产品定位与外观参数（60×95×8.5 mm / 50 g / 标称 500 mAh）。**看它确认"这块板子是什么"**，但它不写代码细节 |
| 玩法社区 | https://ai-passport.folotoy.cn/plays/ | 官方与社区发布的可安装玩法，每个都有介绍和刷机入口。**找灵感、看别人做成什么样**时逛这里 |
| 快速上手 | https://ai-passport.folotoy.cn/guides/getting-started/ | 面向**使用者**（不是开发者）的开箱指南：出厂身份卡、微信小程序同步资料与全屏图片 |
| 源码仓库 | https://github.com/FoloToy/ai-passport | **本书的事实源**。所有 BSP / demo / 分区表都在这里 |
| 国内镜像 | https://gitee.com/FoloToy/ai-passport | 同一个仓库的 Gitee 镜像，GitHub 拉不动时用（`git clone https://gitee.com/FoloToy/ai-passport.git`） |

> **微信小程序**：官网 "WEAR" 一节里有小程序入口，首次开机用它经 BLE 同步
> 名称、头像、自我介绍和全屏图片，让设备变成"身份卡"。这是**出厂固件**的能力，
> 开源基线 `main` 里没有对应代码（见 E.5）。

---

## E.2 官方 `docs/` 文档树：按"我要解决什么"查

仓库根目录**故意不放 README**（留给 fork 的人自己写），文档全在 `docs/` 下。
下面按你实际会遇到的场景排：

| 我要…… | 看哪一份 | 说明 |
| --- | --- | --- |
| 装环境 | [`docs/development/engineering/environment-setup.zh_CN.md`](https://github.com/FoloToy/ai-passport/blob/main/docs/development/engineering/environment-setup.zh_CN.md) | ESP-IDF v5.5.3 安装；有中国大陆专属线路（乐鑫镜像 `git.espressif.com.cn`、离线 release 包兜底）。**第 3 章的官方版** |
| 编译 / 测试 / 出固件 | [`docs/development/engineering/build-and-test.zh_CN.md`](https://github.com/FoloToy/ai-passport/blob/main/docs/development/engineering/build-and-test.zh_CN.md) | `idf.py build`、`merge-bin` 出 `full.bin`、门禁校验 |
| 改分区表 / 算容量 | [`docs/development/engineering/firmware-layout.zh_CN.md`](https://github.com/FoloToy/ai-passport/blob/main/docs/development/engineering/firmware-layout.zh_CN.md) | 分区布局、烧录与已存数据的关系。**第 1.6 / 9 章的官方版** |
| 查引脚 / 时序 / 电气边界 | [`docs/hardware-design/AI_HARDWARE_DEVELOPMENT_GUIDE.zh_CN.md`](https://github.com/FoloToy/ai-passport/blob/main/docs/hardware-design/AI_HARDWARE_DEVELOPMENT_GUIDE.zh_CN.md) | **最该收藏的一份**：引脚表、SPI/I2C/I2S 参数、按键时序、低功耗收尾顺序、各外设的"必须遵守的边界" |
| 让 AI 帮我写 | [`docs/development/ai-guide.zh_CN.md`](https://github.com/FoloToy/ai-passport/blob/main/docs/development/ai-guide.zh_CN.md) | AI 开发工作流；含"二次开发 UI 强制重新设计"规则（第 24 章提过的那条） |
| 看最近改了什么 | [`docs/CHANGELOG.zh_CN.md`](https://github.com/FoloToy/ai-passport/blob/main/docs/CHANGELOG.zh_CN.md) | `Unreleased` 段是下次发布的待核对内容，**不是已发布的定稿**——引用时说清这一点 |
| fork 之后怎么办 | [`docs/fork-guide.zh_CN.md`](https://github.com/FoloToy/ai-passport/blob/main/docs/fork-guide.zh_CN.md) | 为什么根目录没 README、`main` 保持干净的策略 |
| 找别人的应用档案 | [`docs/reference/README.zh_CN.md`](https://github.com/FoloToy/ai-passport/blob/main/docs/reference/README.zh_CN.md) | 官方收录的应用与开发经验（`plays/` + `experiences/`）。**附录 B 的官方版** |
| 提 PR | [`.github/CONTRIBUTING.zh_CN.md`](https://github.com/FoloToy/ai-passport/blob/main/.github/CONTRIBUTING.zh_CN.md) | 贡献指南；含 commit / PR 标题用英文的规范 |

> 官方文档是**双语成对**的：`.md` 是英文默认页，`.zh_CN.md` 是中文页，
> 两边顶部有语言切换链接。看到英文页时把文件名改成 `.zh_CN.md` 就能切到中文。

---

## E.3 给 AI 看的契约文件（第 23.8 节的入口）

官方把"怎么让 AI 在这个仓库里干活"也写进了仓库，这三处是一套：

| 文件 | 作用 |
| --- | --- |
| [`AGENTS.md` / `AGENTS.zh_CN.md`](https://github.com/FoloToy/ai-passport/blob/main/AGENTS.zh_CN.md) | 薄路由：硬约束 + 任务路由，AI 进仓库**先读它** |
| [`CLAUDE.md` / `CLAUDE.zh_CN.md`](https://github.com/FoloToy/ai-passport/blob/main/CLAUDE.zh_CN.md) | 给 Claude Code 的同类入口 |
| [`skills/README.zh_CN.md`](https://github.com/FoloToy/ai-passport/blob/main/skills/README.zh_CN.md) | **五个必需技能**，AI 需自行检查并安装 |

> 官方 README 里给了一句可直接复制的提需求模板（含"必须重新设计 UI、
> 禁止使用当前 demo 菜单"等约束）。想让 AI 接手开发时，直接照它的格式写需求，
> 比自己从零描述省很多来回。详见第 23.8 节。

---

## E.4 官方 `demo/*` 示例分支

`main` 只有 7 个硬件测试页；真正的**应用级**参考在 `demo/*` 分支上（第 23 章有详解）：

| 分支 | 应用 | 值得抄的模式 |
| --- | --- | --- |
| `demo/stopwatch` | 秒表 | 最小应用；纯逻辑与 UI 分离；主机测试 |
| `demo/cat-themed-pomodoro-timer` | 猫主题番茄钟 | 单调时钟、暂停/恢复、NVS 持久化 |
| `demo/rock-paper-scissors` | 石头剪刀布 | RGB565 素材生成脚本、Flash 预算（配合第 20 章） |
| `demo/tetris-game` | 三键俄罗斯方块 | 实时游戏循环、`PRESS` 低延迟输入、局部刷新、音效 |
| `demo/claude-buddy-port` | 桌面 AI 伴侣 | 用完整应用替换 demo 菜单、加密 BLE、状态归约 |

不用切换工作区就能读：

```bash
git branch -r --list 'origin/demo/*'
git show origin/demo/tetris-game:main/main.c
git diff main...origin/demo/tetris-game -- main components
```

> 官方提醒：**示例分支是设计案例，不是功能堆叠。**
> 新应用从 `main` 建 `feature/*` 分支，按需参考，不要把多个 demo 整体合并。

---

## E.5 先分清：你面对的是"出厂固件"还是"开源基线"

这是新手最容易混的一件事，也是网上很多矛盾说法的根源。

| | 出厂（产品）固件 | 开源仓库 `main` 分支 |
| --- | --- | --- |
| 定位 | 给用户用的成品 | **最小可运行的硬件测试基线** |
| 开机 | 身份卡 / 已装玩法 | 七卡片测试菜单（Display…Low Power） |
| 微信小程序同步 | 有 | 无 |
| `recovery` 分区（`0x700000`，上键长按 5 s 进） | 有，可经 BLE 重装固件 | 无（当前 `partitions.csv` 只有 nvs / phy / factory 三行） |
| `cardid` 保护分区 | 有 | 无 |
| NFC（NTAG213 被动标签） | 硬件存在，手机可碰读 | **不连 MCU**，固件里没有任何 NFC 代码 |
| 二次开发 | 不用于开发 | BSP API 可复用，**UI 必须重新设计** |

> 所以：看到"按住上键 5 秒进 recovery""Factory 3 MB""小程序同步头像"这类说法，
> 先问一句它讲的是**哪一套**。两套都是真的，只是不是同一个东西。

---

## E.6 第三方资源：能抄什么、要打折什么

### TRAE 社区：设备全解析 · 实操经验和技巧分享

- 链接：https://forum.trae.cn/t/topic/180446
- 是什么：一篇带**真机实测**的长帖。作者刷入 MicroPython 后用 REPL 直读
  芯片 / Flash / I2C 设备 / 按键电压 / MAC，逐项与官方规格对表，
  最后给了 8 条踩坑记录。
- **最值得看的四段**：
  1. ST7789P3 **不是通用 ST7789**——需要厂商专属初始化序列（PORCTRL/GCTRL/伽马等），
     写像素前必须发 `RAMWR (0x2C)`。漏了就表现为"屏幕一直显示上一帧原厂画面"。
  2. **无 PSRAM 的量化影响**：free 内存约 170 KB，整屏 RGB565（约 150 KB）
     必须**分块读、分块送显**，不能一次性 `read()` 进内存。
  3. **独立硬件电源键**：关机后 USB 不再枚举，COM 口直接消失
     （区别于 deep sleep 的"口在但读不出"，见第 22.8 节）。
  4. **GPIO 几乎全占用**：SPI 占 1/8/9/20，I2S 占 2/3/4/5/6，I2C 占 7/10，
     想扩展外设要先做规划。
- **要打折的地方**：帖里的分区表写的是"Factory 3 MB + cardid + recovery 0x700000"，
  那是**出厂固件/PokeWalk 那套布局**，不是开源基线当前的 `partitions.csv`
  （见 E.5 与第 1.6 节）；屏幕 SPI 写 40 MHz，也是抄了官方 README 摘要表
  （源码是 80 MHz，见第 5.1 节）。

> 顺带：这条 MicroPython 路线本身也是一条可选路径（ESP32-C3 通用固件即可跑），
> 但**本书讲的是 C / ESP-IDF**，两者的 LVGL API 不能混用（第 5.1 节）。

### deepseekagent：AI Passport Firmware Agent

- 收录页：https://deepseekagent.io/zh/agents/ai-passport
- 源码：https://github.com/iCurrer/ai-passport-agent （MIT）
- 是什么：一个 DeepSeek Harness 的 **agent preset**，把官方那套"让 AI 开发固件"的纪律
  固化成了十步流程：`READ → PLAN → MODIFY → BUILD → UI → FUNCTION → HARDWARE
  → DOCUMENT → COMMIT → STOP`，每步必须能编译。
- **值得抄的不是代码，是两条纪律**：
  1. **硬件写死、产品引导**：板级事实（MCU/屏幕/按键/音频/电池/总线）当作权威不重复推导，
     页面、交互、配色这些软规格一律用提问引导得出。
  2. **诚实报告**：绝不为写代码编 PASS——没连板子就写 `Hardware: NOT TESTED`，
     只编译过就写 `Build: PASS`，UI 只做了代码审查就写 `UI: STATIC REVIEW PASS`。
     这一条和官方 `AGENTS.md` 的交付要求是同一个精神。
- **要打折的地方**：它自带的"固定硬件"表同样写着 **SPI2 @40 MHz**，与源码的 80 MHz 不一致；
  另外它要求本机装 **ESP-IDF 5.5.x**，与本书的 5.5.3 一致，但路径要自己在
  `agent.cordis.yml` 里改（`$IDFHome` / `$IDFVersion`）。

> 官方（AGENTS.md + skills）和这个第三方 preset 是**两条并行的路**：
> 前者是官方维护、跟着仓库走；后者把流程固化得更死、适合不想自己立规矩的人。
> 选一条走到底就行，别混着用。

---

## E.7 官方源自己打架时，按这个顺序判

本书第 1.7 节讲过"别把没验证当成有"，这里给一个可执行的排序：

```
1. 源码       components/bsp/include/bsp_pins.h  ← 板级事实的单一权威
2. 硬件开发指南 docs/hardware-design/AI_HARDWARE_DEVELOPMENT_GUIDE.zh_CN.md
3. demo 源码   main/demo_*.c                      ← "官方怎么做"的活样本
4. README/摘要表 docs/README.zh_CN.md             ← 更新滞后，摘要表尤其容易漂移
5. 第三方帖子/预设                                 ← 可能抄了上面第 4 层
```

**已经在本书里抓到的两处漂移**（都是第 4 层没跟上第 1 层）：

| 数字 | 摘要表/第三方 | 源码实际 | 出处 |
| --- | --- | --- | --- |
| 屏幕 SPI 时钟 | 40 MHz | **80 MHz** | `bsp_pins.h` 的 `BSP_LCD_PCLK_HZ` |
| app 分区大小 | 3 MB | **约 7.9 MB**（`0x7f0000`） | `partitions.csv`（3 MB 是 PokeWalk 的契约） |

还有一个**不是漂移、只是口径不同**的：电池 500 mAh（商品页标称）vs
520 mAh（CW2017 profile 用的电芯容量）。两个数都对，别当成笔误去"修"。

---

## E.8 一句话总结

**看硬件事实 → `bsp_pins.h`；看官方怎么做 → `main/demo_*.c`；
看边界与禁区 → 硬件开发指南；看应用级参考 → `demo/*` 分支；
看别人的成品 → 玩法社区和附录 B；剩下的摘要表和第三方帖子，
可以读，但数字要回源码确认一遍。**
