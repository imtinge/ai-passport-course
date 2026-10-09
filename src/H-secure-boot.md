# H. 安全启动与固件防护方案

> 适用对象：已经把第 1~12 章、第 10c 章（OTA）读过一遍，想把这台
> 「可联网、可 OTA、带专有素材」的可穿戴设备**送上产品化**的人。
> 本章不假设你懂密码学，只要求你会 `idf.py` 和命令行。
>
> 前置事实：本章所有结论都针对 **ESP32-C3 + ESP-IDF v5.5.3**，
> 用官方 `secure-boot-v2.rst` / `flash-encryption.rst` 核对过。
> 芯片本身的引脚、电流、eFuse 数字见附录 F.4。

## H.1 安全启动能挡什么、挡不住什么

先泼一盆冷水：**安全启动不是「设备安全」的万能药**，它只解决
「固件来源可信」这一件事。一张表说清边界：

| 它能挡 | 它挡不住 |
| --- | --- |
| 别人把**未签名**的固件刷进你的设备（bootloader 验签失败直接不启动） | **运行时** RAM 里的漏洞、缓冲区溢出、ROP——验签只发生在启动那一刻 |
| 别人**读出 flash 里的明文固件**（配合 Flash 加密，见 H.2） | 应用层**鉴权**（HTTPS 证书、登录态），那是第 10c 章的事，安全启动不替代 |
| 别人**回滚**到旧版本（配合防降级，见 H.5） | 物理拆解、探针直接读芯片（防不了，只能提高门槛） |
| 别人**篡改**固件分区（哈希对不上） | 你自己的代码写得烂——安全启动不修 bug |

**结论**：安全启动 + Flash 加密 + 防降级，三者一起才构成「固件防护」的基本盘。
它**不替代**第 10c 章讲的证书校验和鉴权，也不替代你写安全的应用代码。

## H.2 C3 的三大硬约束（开搞之前必读）

ESP32-C3 在安全启动上有三个和别的芯片不一样的坑，**尤其第三个会直接打到本板脸上**：

### 约束 1：只支持 Secure Boot v2，不支持 v1

- ESP32（初代）用的是 v1（ECDSA）。**C3 砍掉了 v1**，只认 **v2（RSA-PSS，3072 位）**。
- 所以生成密钥的命令必须带 `--version 2`，否则签名 bootloader 根本起不来。
- 芯片版本要求 **rev ≥ v0.3（ECO3）**。早期 ECO2 硅片有安全启动相关的硬件缺陷，
  量产前务必确认你手上的批次是 ECO3（`esptool.py chip_id` 会报 `Chip is ESP32-C3 (revision 3)`）。

### 约束 2：Secure Boot 与 Flash Encryption 共用一个 eFuse 密钥块

- C3 **只有一个** eFuse key block 同时被「安全启动摘要」和「Flash 加密密钥」使用。
- 后果：**这两件事必须一起规划、一次性烧录**，事后不能「先只开安全启动、过两个月再加加密」。
- 反过来，如果你只想做 Flash 加密而不开安全启动，C3 也允许，但**签名校验和加密的密钥槽是同一个**，
  一旦烧了 `ABS_DONE_0`（安全启动完成位），bootloader 就只认签名镜像了——和约束 2 是同一个 eFuse 在起作用。

### 约束 3：开了之后，**JTAG 和内置 USB 烧录路直接废掉** ⚠️

这是本板最致命的一条，必须写在最前面：

- 启用安全启动后，**首次启动即烧 eFuse 禁用 JTAG**。
- 同时启用会**禁用 ROM 的 USB-OTG / DFU 栈**——也就是说，那根你平时「插 USB、`idf.py flash`」的
  **内置 USB-Serial-JTAG（GPIO18/19）烧录 / 调试通路，开了安全启动就断了**。

**这对 AI Passport 意味着什么**：你日常开发 100% 依赖 GPIO18/19 的 USB-JTAG。
一旦不可逆位烧下去，这条口不能再走 `idf.py flash`，也不能再进 JTAG 调试。
所以**开安全启动之前，必须先规划好替代烧录 / 恢复通道**：

- **方案甲（推荐量产）**：改用 **UART0 下载模式**，接线为
  `GPIO21 = U0TXD`、`GPIO20 = U0RXD`（见附录 F.4 的管脚表），
  配合 `BOOT` 键（拉 GPIO9 为 0 进下载模式）——这就是经典的 `esptool` 串口烧录路，
  不受安全启动影响。
- **方案乙（无物理接口）**：完全走 **签名 OTA**（第 10c 章），新固件由你签名后推送到设备，
  设备本地验签后自更新。适合「出厂封壳、不预留串口」的产品形态。

> 一句话：**在 AI Passport 上做安全启动，第一课不是「怎么签名」，而是「烧完之后你靠哪条路继续烧」。**

## H.3 密钥管理：私钥不上构建机

安全启动的安全边界，最终落在「**签名私钥有没有泄露**」这件事上。

- 生成密钥：**离线**在一台不联网的机器上跑
  ```bash
  espsecure.py generate_signing_key --version 2 ./keys/sb_signing_key.pem
  ```
  （可选 `--scheme RSA3072`，v2 默认就是 RSA-PSS 3072。）
- **私钥 `sb_signing_key.pem` 绝不能进 Git、绝不能放 CI 构建机明文**。
- 两条实践路线：
  - **构建机签名**（简单）：把私钥放构建机，`CONFIG_SECURE_BOOT_BUILD_SIGNED_BINARIES=y`，
    `idf.py build` 直接产出签名好的 bin。缺点：私钥在构建环境里。
  - **远程 / HSM 签名**（产品化）：`CONFIG_SECURE_BOOT_BUILD_SIGNED_BINARIES=n`，
    构建机只产出**未签名**的 bin，再把 bin 送到隔离的签名服务（或 HSM）用私钥签名。
    私钥永不离开保险箱。
- **丢失即灾难**：私钥一旦泄露，别人能签任意固件，安全启动形同虚设；
  私钥一旦丢失，你将**永远无法再给设备发新固件**（除非走 UART0/OTA 且旧密钥仍有效）。
  所以密钥要有备份、有访问控制、有轮换计划（见 H.5）。

## H.4 工厂烧录流程（一次性、不可逆）

量产时，每台设备只做一次「上锁」操作。步骤（以「方案甲 UART0 + 同时开加密」为例）：

1. **生成密钥**（每台**独立**或**同批共用**，视你的密钥策略而定）：
   ```bash
   espsecure.py generate_signing_key --version 2 ./keys/sb_key.pem
   espsecure.py generate_flash_encryption_key ./keys/fe_key.bin
   ```
2. **烧录安全启动摘要 + Flash 加密密钥到 eFuse**（用 UART0，`espefuse.py`）：
   ```bash
   espefuse.py --port COMx burn_key SECURE_BOOT_DIGEST0 ./keys/sb_key.pem
   espefuse.py --port COMx burn_key FLASH_CRYPT_CONFIG       ./keys/fe_key.bin
   ```
   > 实际量产通常用 `idf.py flash` 在「首次启动自动生成并烧录加密密钥」的模式，
   > 即 `CONFIG_SECURE_FLASH_ENCRYPTION_MODE_RELEASE` + 让设备自生成 FE key。
   > 上面的 `burn_key` 写法适合你要**预置固定密钥**的场景。
3. **预吊销空的防回滚槽**（为将来轮换密钥留余地，见 H.5）：
   ```bash
   espefuse.py --port COMx burn_efuse KEY_REVOKEx 0   # 把所有未用的密钥摘要槽先烧 0
   ```
4. **写保护摘要块**，防止后续误烧：
   ```bash
   espefuse.py --port COMx read_protect_efuse \
       SECURE_BOOT_DIGEST0 FLASH_CRYPT_CONFIG
   ```
5. **最后烧不可逆位** `ABS_DONE_0`——这一步之后设备**只认签名镜像**，eFuse 不可回退。
   多数流程把它留给设备首次上电由 bootloader 自动烧，避免人工误操作锁死。

> 关键提醒：第 5 步之前的任何一步都可重来；**第 5 步之后不可回退**。
> 先在几台样机上跑通整套，再上产线。

## H.5 OTA 防降级：SECURE_VERSION + 密钥轮换

只防篡改还不够——攻击者可能把你**上一个有漏洞的版本**重新刷回去（回滚攻击）。
C3 的防降级靠两样东西：

- **`SECURE_VERSION`（防回滚版本号）**：你的 `app` 分区每发一版，版本号 `+1`。
  设备启动时会比对镜像里的版本号和 eFuse 里记录的「最低可接受版本」，
  **低于它的固件一律拒绝启动**。配置项：`CONFIG_BOOTLOADER_APP_SEC_VER` 系列。
- **密钥轮换（应对私钥疑似泄露）**：v2 支持多个密钥摘要槽（`KEY_REVOKEX`，最多若干槽）。
  当你要换签名密钥时：
  1. 用**新密钥**签名的新固件里，写入更高的 `SECURE_VERSION`；
  2. OTA 成功后，设备（或工厂）**吊销旧密钥摘要槽** `burn_efuse KEY_REVOKEX 1`（假定旧槽是 0）；
  3. 此后旧密钥签的任何固件（无论版本号高低）都验签失败。
  这样即使旧私钥泄露，已部署设备也不会认旧密钥签的恶意固件。

> 这就是为什么 H.4 第 3 步要「预吊销空槽」：把还没用到的摘要槽先烧成无效，
> 将来轮换密钥时只点亮新槽，旧槽已是不可逆的「已吊销」状态。

## H.6 开发态 vs 量产态：别在样机上直接锁死

`menuconfig` 里有两个模式，搞混了会让你手里的样机变砖：

| 模式 | 配置 | 行为 | 适用 |
| --- | --- | --- | --- |
| 开发模式 | `CONFIG_SECURE_FLASH_ENCRYPTION_MODE_DEVELOPMENT` | 允许**重新烧录**明文 / 可反复烧写，eFuse 不锁死 | 研发、调代码 |
| 量产模式 | `CONFIG_SECURE_FLASH_ENCRYPTION_MODE_RELEASE` | 烧完即锁，不可逆 | 出厂、发货 |

**铁律**：研发期用开发模式反复验证整套签名 + 加密 + OTA 流程；
**确认硬件冻结、流程跑通、密钥备份齐全后**，再切到量产模式烧不可逆位。
很多人栽在「样机上一把梭把量产位烧了，结果想改一行代码都刷不进去」。

`menuconfig` 里需要打开的总清单（ESP32-C3 + IDF v5.5.3）：

```text
Security features  --->
  [ ] Enable ROM DBG (keep JTAG)        # 量产建议关，见 H.2 约束 3
  [*] Enable hardware Secure Boot in bootloader
      (X) Secure Boot v2 (RSA)          # C3 只支持 v2
  [*] Enable flash encryption on boot
      (X) Release mode                  # 量产；研发期选 Development
  [ ] Check secure boot signing key during build   # 想远程签名就关掉
Bootloader config  --->
  [*] App version for anti-rollback
      (N) Minimum acceptable app version
```

## H.7 本板落地清单（AI Passport 专属）

把前面几节浓缩成一份「在这块板上真正要做的动作」：

1. **先决定烧录后靠谁**：默认 GPIO18/19 的 USB-JTAG 在安全启动后失效。
   量产 / 封壳产品走**签名 OTA**（第 10c 章）；要留物理口的走 **UART0（GPIO21/20）**。
2. **确认芯片是 ECO3**（`esptool.py chip_id` 看 revision），否则 v2 起不来。
3. **离线生成 RSA-3072 签名密钥**，私钥进保险箱、不进 Git、不进 CI 明文。
4. **`menuconfig` 开 Secure Boot v2 + Flash 加密**，先选 Development 模式跑通整套。
5. **样机验证**：签名 `idf.py build` → 烧录 → 看 bootloader 验签日志 → 跑一次真实 OTA 自更新 → 验防回滚。
6. **预吊销空密钥槽、写保护摘要块**（H.4 第 3、4 步）。
7. **硬件冻结后**切 Release 模式、烧 `ABS_DONE_0` 不可逆位，再上产线。
8. **私钥轮换预案**：保留旧槽、用 `SECURE_VERSION` 抬版本、OTA 后吊销旧槽（H.5）。

> 一句话收口：**安全启动在 C3 上是个「开弓没有回头箭」的操作，
> 而它偏偏会切断你最习惯的那根 USB 烧录线——想清楚恢复通道，再烧那一下。**

## H.8 相关章节

- 引脚 / 电流 / eFuse 数字：附录 F.4
- eFuse 总量与「内置 USB-JTAG 脚」：附录 F.1、F.4
- 启动模式（GPIO9/GPIO8 Strapping）：第 1 章
- 签名在排错里的蛛丝马迹：第 22 章（看日志判复位原因）
- 固件怎么安全地从云端下来：第 10c 章（HTTPS / OTA）
