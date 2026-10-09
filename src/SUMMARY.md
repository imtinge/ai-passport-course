# 目录

[前言：这本书给谁](00-preface.md)

# 第一部分 · 起步

- [0. 不懂硬件也能看懂：先认识这十几个词](00b-hardware-words.md)
- [1. 先看清这块板子](01-hardware.md)
- [2. 给 C 程序员的 ESP-IDF 速通](02-idf-crash-course.md)
- [3. 编译、烧录、看日志](03-first-build.md)

# 第二部分 · BSP 与常用功能

- [4. BSP：你和硬件之间唯一的中间人](04-bsp.md)
- [5. 屏幕与 LVGL](05-display-lvgl.md)
- [6. 三个按键怎么撑起一套交互](06-button.md)
- [7. 音频：播放、录音与开机爆音](07-audio.md)
- [8. 电量、熄屏与深睡](08-battery-power.md)
- [9. 存储：NVS、分区表与素材](09-storage.md)
- [10. 联网：Wi-Fi 全生命周期](10-network.md)
- [10b. 配网：把 Wi-Fi 密码交给设备](10b-provisioning.md)
- [10c. 获取网络数据：HTTP / HTTPS / 长连接 / OTA](10c-network-data.md)
- [11. 没有 PSRAM 怎么活：内存纪律](11-memory.md)
- [12. 并发：任务、队列与 LVGL 锁](12-concurrency.md)

# 第三部分 · 实战拆解

- [13. 实战一：DOOM（36 个文件的最小可跑项目）](13-project-doom.md)
- [14. 实战二：一个仓库装 5 个玩法（页面栈）](14-project-multipage.md)
- [15. 实战三：音效钥匙扣（音频 + 文件系统）](15-project-voice.md)
- [16. 实战四：PokeWalk（后台世界与存档）](16-project-pokewalk.md)
- [17. 实战五：小智 AI 对话（另一套架构）](17-project-xiaozhi.md)
- [18. 端到端实战：巴巴爸爸角色图鉴（你用 Trae 生成，非官方）](18-project-barbapapa.md)

# 第四部分 · 手把手三件事

> 这三章是“照着做一遍就能出结果”的专题：中文、图片、声音。
> 每章都给出 PC 端预处理、工程接入、设备端代码、故障排查表四段，
> 配套可编译文件在 `snippets/` 目录。

- [19. 手把手：让屏幕显示中文](19-tutorial-chinese-font.md)
- [20. 手把手：把一张图片画到屏幕上](20-tutorial-image.md)
- [21. 手把手：让板子发出声音](21-tutorial-audio.md)

# 第五部分 · 收尾

- [22. 调试与排错](22-debugging.md)
- [23. 下一步：练习路线](23-whats-next.md)

# 第六部分 · 官方示例源码详解（逐行拆解 main/demo_*.c）

> 这 8 章逐行读官方 `main/` 下 **7 个硬件测试 demo** + 框架，看清第 2 部分讲的概念在生产代码里怎么落地。
> （这里的“7 个 demo”是基线菜单里的测试页；另有 **11 条独立的 `demo/*` 应用分支**，见第 23.5 节，两者不是一回事。）
> 源码都在官方仓库 `folotoy/ai-passport` 的 `main/` 目录；行号均来自真实文件。
> 注意：巴巴爸爸（第 18 章）**不在**官方仓库，是你用 Trae 生成的实战项目。

- [24. 官方示例框架：菜单、生命周期与 UI 小部件](24-official-framework.md)
- [25. 官方 Display 示例：色块 + 背光调光](25-official-display.md)
- [26. 官方 Button 示例：事件流 + 实时 ADC 电压](26-official-button.md)
- [27. 官方 Audio 示例：方波 / 录音回放](27-official-audio.md)
- [28. 官方 Battery 示例：CW2017 电量与电压](28-official-battery.md)
- [29. 官方 Wi-Fi 示例：STA 扫描（不连接）](29-official-wifi.md)
- [30. 官方 BLE 示例：NimBLE 广播](30-official-ble.md)
- [31. 官方 Low Power 示例：light/deep sleep 唤醒](31-official-lowpower.md)

# 附录

- [A. API 速查表](A-api-cheatsheet.md)
- [B. 代表仓库索引](B-repo-index.md)
- [C. 术语表](C-glossary.md)
- [D. 分模块常用代码手册](D-module-cookbook.md)
- [E. 官方与社区资源地图](E-official-resources.md)
- [F. 官方规格速查：本书用到的每个数字](F-official-spec.md)
- [G. 反常识清单：PC 直觉在这块板上不成立的地方](G-anti-intuition.md)
