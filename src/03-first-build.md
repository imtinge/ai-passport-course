# 3. 编译、烧录、看日志

本章把官方基线跑起来。跑通之后，后面每一章的代码你都能立刻验证。

## 3.1 先选对 ESP-IDF 版本

这是最容易在第一步就走错的地方。社区里现在有**两条主线，版本不兼容**：

| 主线 | 版本 | 代表仓库 | 说明 |
| --- | --- | --- | --- |
| 官方基线 / 社区 fork | **5.5.3** | `folotoy/ai-passport` 及多数 fork | 本书主要基于这条线 |
| 小智 AI 移植线 | **≥ 6.0.1**（推荐 6.1） | `FoloToy/folo-ai-passport-xiaozhi` | 官方已声明 5.x 不再支持 |

> 小智项目的 README 原文：
> "The project now requires ESP-IDF v6.0.1 or later. ESP-IDF v6.1 is the recommended
> SDK. **ESP-IDF 5.x is no longer supported**."

**给你的建议**：

- 如果你想学 AI Passport 本身的开发（本书的目标）→ 装 **5.5.3**；
- 如果你的目标是给设备加 AI 语音对话 → 直接上 **6.1**，别从别人的 5.x fork 起步；
- 一台机器上装多个 IDF 版本是可以的，用不同的安装目录 + 各自的 `export.sh` 切换。

从全量扫描的 172 个仓库看：明示版本的 110 个仓库里 **105 个还是 5.5**，
只有 4 个上了 6.x。**迁移窗口刚刚打开**，现在是新建项目直接上 6.x 的时机。

### 版本契约是写在文件里的，不用猜

BSP 组件的依赖清单 `components/bsp/idf_component.yml` 把整套版本钉死了：

```yaml
dependencies:
  idf: ">=5.5.3,<5.6.0"
  lvgl/lvgl: "^9.5.0"
  espressif/esp_lvgl_port: "2.9.0"
  espressif/button: "4.2.0"
  espressif/esp_codec_dev: "1.6.2"
```

| 组件 | 版本 | 它管什么 |
| --- | --- | --- |
| ESP-IDF | **≥5.5.3，<5.6.0** | 框架与工具链 |
| LVGL | **^9.5.0** | 界面（网上大量 v8 教程在这里不适用） |
| esp_lvgl_port | **2.9.0** | LVGL 任务、锁、显示接入 |
| espressif/button | **4.2.0** | ADC 按键与四类事件 |
| esp_codec_dev | **1.6.2** | ES8311 音频 codec 控制 |

`dependencies.lock` 会把实际解析到的版本连同 hash 一起锁住。
**改了 `idf_component.yml` 就必须用 v5.5.3 重新构建并提交更新后的 lock**——
普通构建不应该产生 lock 的 diff。

## 3.2 装环境

**Linux / macOS**（官方推荐，编译更快）：

```bash
mkdir -p ~/esp && cd ~/esp
git clone -b v5.5.3 --recursive https://github.com/espressif/esp-idf.git esp-idf-v5.5.3
cd esp-idf-v5.5.3 && ./install.sh esp32c3
. ~/esp/esp-idf-v5.5.3/export.sh   # 每次开新终端都要执行
```

三条全局纪律（每条都有人踩过）：

1. **必须是 `source`/`.`，不能直接 `./export.sh`。** 后者在子 shell 里配置，
   当前终端不会生效——`idf.py: command not found` 99% 就是这个原因。
2. **安装路径不要有空格和中文**，推荐 `~/esp/`。
3. **已有其他 IDF 版本就并行安装，不要覆盖。** 用 `echo $IDF_PATH` 确认当前指向。

国内网络推荐乐鑫镜像（v5.5.3 的子模块 URL 是相对地址，克隆后自动指向同一镜像，
**不需要改写 git 配置**）：

```bash
git clone -b v5.5.3 --recursive \
    https://git.espressif.com.cn/espressif/esp-idf.git esp-idf-v5.5.3
cd esp-idf-v5.5.3
IDF_GITHUB_ASSETS=dl.espressif.cn/github_assets ./install.sh esp32c3
```

**子模块拉取中断不要重新克隆，原地续传即可：**

```bash
git submodule update --init --recursive
./install.sh esp32c3
git status --short          # 还有 modified: components/xxx 就按路径单独更新
```

**系统依赖**（Ubuntu/Debian）：

```bash
sudo apt-get install -y git wget curl flex bison gperf python3 python3-pip \
    python3-venv cmake ninja-build ccache libffi-dev libssl-dev dfu-util \
    libusb-1.0-0 build-essential
```

Fedora 用 `dnf install`（`libffi-devel openssl-devel libusb1-devel gcc gcc-c++ make`），
Arch 用 `pacman -S --needed base-devel git wget curl flex bison gperf python cmake ninja ccache dfu-util libusb`。

**Windows**：安装 ESP-IDF 官方安装器，然后**用开始菜单里的 “ESP-IDF CMD” 终端**
（它已经帮你 source 好了环境）。不要用普通 CMD 或 PowerShell 硬来。

> 小智项目的 README 里有一句务实的提醒：
> “Linux 比 Windows 更好，编译速度快，也免去驱动问题的困扰。”

**WSL2**：可以在 WSL 里写代码和编译，但 **USB 设备默认不会出现在 WSL 里**，
要用微软的 `usbipd-win` 转发：

```powershell
usbipd list                    # 管理员 PowerShell，找到 BUSID（如 2-3）
usbipd bind --busid 2-3        # 只需一次
usbipd attach --wsl --busid 2-3
```

转发后 Ubuntu 里 `ls /dev/ttyACM0` 能看到设备即可。
**拔线/休眠会断开，重新 `attach` 就行**；不要两边同时开同一个串口。
嫌麻烦就走“WSL 编译 + Windows 烧录”——但工程要放在 WSL 的 `~/` 下，
放在 `/mnt/d/` 上构建会非常慢。

### 三个真实的坑

**坑 1：Python 缺 lzma 模块**

有开发者在 `firmware/README.md` 里记录了这件事：

> 直接 `. ~/esp/esp-idf/export.sh` 在这台机器上会失败：pyenv 把 python3 指向 3.12.0，
> 而那个 3.12 是自己编的、**缺 lzma 模块**，解不开 IDF 工具链的 `.tar.xz` 包：
> `tarfile.CompressionError: lzma module is not available`。
> 解法是**用系统 Python 3.9.6**（自带 lzma，且满足 IDF ≥ 3.9 的要求）。

**坑 2：Windows 长路径**

克隆仓库时加这个（尤其是 PokeWalk 那种深层目录）：

```bash
git clone -c core.longpaths=true <url>
```

**坑 3：串口驱动与权限（Linux 有额外的两个坑）**

ESP32-C3 用的是 USB Serial/JTAG（**不是**传统 CP210x/CH340）。
Windows 上如果设备管理器认不出来，装 CP210x 驱动通常能解决。

Linux 上设备通常枚举为 **`/dev/ttyACM0`**（不是 `ttyUSB0`，别照抄旧教程）：

```bash
ls -l /dev/ttyACM* /dev/ttyUSB* 2>/dev/null
sudo usermod -aG dialout $USER   # Ubuntu/Debian/Fedora；Arch 可能是 uucp
```

⚠️ **加组之后必须注销重登（或重启）才生效，只开新终端不够。**
用 `id` 确认组列表里已经有了。

第二个坑是 **ModemManager**：Ubuntu Desktop 默认装了它，设备插入的头几秒
它会去抢 `/dev/ttyACM0` 试拨 modem，导致第一次烧录超时。

```bash
sudo systemctl disable --now ModemManager   # 桌面机一般用不到
```

或者插上后等 10~20 秒再烧。表现为 `Connecting...` 一直卡住时，先怀疑它。

**坑 4：别把日志改回 UART0**

背光用的 GPIO21 和 UART0 的默认 TX 是同一个引脚。
控制台**固定用 USB-Serial-JTAG**，如果你在 menuconfig 里把日志输出改成 UART0，
屏幕背光就会出问题。

## 3.3 编译

> **先说官方口径**：固件编译**优先** `./tools/validate.sh --firmware`，
> `idf.py build` 和 `idf.py flash` 只是**增量开发命令，不是默认交付方式**。
> 出处：`docs/development/engineering/build-and-test.zh_CN.md`。
> 本书下面先用 `idf.py build` 讲通流程（因为它最能暴露环境问题），
> 但你**养成习惯后默认应该跑门禁脚本**。

```bash
git clone https://github.com/folotoy/ai-passport
cd ai-passport
idf.py set-target esp32c3     # 第一次必须做
idf.py build

# 官方推荐的默认动作（会另起干净的临时构建目录做完整校验）
./tools/validate.sh --firmware
```

`set-target` 会生成 `sdkconfig` 并设定目标芯片。
**它只需要在第一次或切换过芯片目标时执行。**

> **⚠️ 坑：`sdkconfig.defaults` 改了，已有 `sdkconfig` 不会自动同步。**
> 你改了 `sdkconfig.defaults`（或拉了上游更新），直接 `idf.py build`
> **不会**把新默认值灌进已经存在的 `sdkconfig`——配置项会静默保持旧值，
> 于是“我明明开了这个选项啊”。`idf.py fullclean` 也做不到。
> 正确做法：**先备份有意的本地设置，再跑一次 `idf.py set-target esp32c3`**。
> 第 19 章的 `CONFIG_LV_TXT_ENC_UTF8=y` 就是这个坑的高频受害者。

首次构建会联网拉取托管组件（LVGL、esp_lvgl_port、button、esp_codec_dev），
慢是正常的。拉完之后会出现 `managed_components/` 目录——**不要改它**。

编译成功的尾巴长这样：

```text
Project build complete. To flash, run:
 idf.py -p (PORT) flash
```

### 3.3.1 当 `idf.py build` 在你机器上跑不起来（Windows 实战）

Windows 上 `idf.py build` 有时会这样失败——注意**它甚至没进 CMake**：

```text
CreateProcess failed: ...
```

这时不要去改代码，**直接绕过 `idf.py`，用 ninja 构建**。
`idf.py build` 本身只是 CMake + ninja 的包装，而 CMake 配置已经在
`set-target` 阶段生成好了（`build/build.ninja` 里写死了工具链绝对路径），
所以绕开包装层完全可行：

```powershell
$env:IDF_PATH = 'D:/esp/espressif/frameworks/esp-idf-v5.5.3'
& 'D:/esp/mingw64/bin/ninja.exe' -j4 -C D:/路径/到/项目/build *> build\build.log
Write-Host ('NINJA_EXIT=' + $LASTEXITCODE)
```

三个都是踩出来的要点：

**① ninja 要用绝对路径。**
直觉做法是先 dot-source 官方的 `Initialize-Idf.ps1` / `export.ps1` 把 ninja 放进 PATH，
再 `& ninja`。但这套脚本在某些机器上会因 `idf-env` 查询返回 null 而**静默装配失败**——
脚本不报错，可 PATH 里既没有 ninja 也没有 Python。
结果是下一行 `& ninja` 根本没执行，日志是空的、二进制时间戳还是上一次的，
看起来却像“构建成功”。判据：**构建完看一眼 `.log` 有没有内容、二进制 mtime 有没有变。**

**② 重定向用 `*>`，不要用 `|`。**

```powershell
# ✅ 所有流写文件
& ninja -j4 -C build *> build\build.log
# ❌ 管道写法可能在满屏 Git/msys 噪声下中断脚本
& ninja -j4 -C build | Tee-Object build\build.log
```

原因是 Windows PowerShell 在收到 native 命令写到 stderr 的内容时会触发
`NativeCommandError`，而 IDF 工具链（尤其 msys 的 `git-submodule` 之类）
往 stderr 写东西很正常。用 `*>` 全流重定向到文件就绕开了这个行为。
**作为方法论：Windows 上跑长构建，一律“命令 + `*>` 落盘 + 回来读日志”，
不要指望管道回显。**

**③ 校验退出码，别只看“跑完了”。**

```powershell
& $ninja -j4 -C build *> build\build.log
Write-Host ('NINJA_EXIT=' + $LASTEXITCODE)     # 必须是 0
```

然后回头 grep 日志：

```bash
grep -c -iE "error:|warning:" build/build.log   # 期望 0
tail -5 build/build.log
```

> 这套“ninja 绝对路径 + `*>` 落盘 + 查退出码”的组合，
> 本质是把不确定环节收敛到一个地方：**日志**。
> 编译这个动作本身不难，难的是“你以为它在编译，其实它没有”。

同样的思路适用于烧录：`python -m esptool ... write_flash` 之后也要确认
日志里有 `Hash of data verified` 和 `Hard resetting`，
而不是只看命令“跑完了”。

### 3.3.2 加速重复编译：ccache

ESP-IDF 5.5.3 **默认不启用** ccache。改一行代码就等几分钟时，先把它开上：

```bash
ccache --version          # 先确认可用
idf.py --ccache build     # 单次构建启用
```

或者在 Linux/macOS shell 里导出，让 `validate.sh` 一起受益：

```bash
export IDF_CCACHE_ENABLE=1
idf.py build
```

**这是 `idf.py` 的命令行选项，不是 `sdkconfig` / menuconfig 配置**——
别去 menuconfig 里找它。要在项目或 CI 里长期启用，就显式传 `--ccache`
或在构建环境里设 `IDF_CCACHE_ENABLE=1`（别擅自改别人的 shell 启动文件）。

两个细节：

- 缓存目录**不总是** `~/.ccache`，取决于版本、`CCACHE_DIR` 等。
  用 `ccache --show-config` / `ccache --show-stats` 看真实的 `cache_dir`；
  确保它不在 `build/` 和临时验证目录里，否则一清理就白缓存了；
- 清缓存**不是日常步骤**。真要清，用保留配置文件的 `ccache --clear`，
  不要整个删目录——那会连累共用同一缓存的其他项目。

### 3.3.3 Windows 上构建特别慢：先诊断，别急着加杀软排除项

官方明确写了这条，**而且措辞很谨慎**：杀毒/终端安全软件的实时扫描**可能**拖慢构建，
但**应先诊断瓶颈**。

- Microsoft Defender 有官方的**性能分析器**，用它定位到底是不是它在扫；
- **分析结果 ≠ 自动建议加排除项**。排除项会降低防护能力，是可选措施，
  必须按适用安全策略取得用户/管理员批准，且只把例外限制在**已确认问题的最小范围**；
- **不要例行把整个 ESP-IDF 安装目录、工具链目录或工程加进排除列表，
  也不要关闭实时防护。**

也就是说：先量，再改；别把“构建慢”默认归因于杀软。
真正常见的慢因其实是首次拉托管组件、没有 ccache、以及 3.3.1 那种“命令根本没跑起来”。

## 3.4 烧录与监控

```bash
idf.py -p /dev/ttyUSB0 flash monitor   # Linux
idf.py -p COM4 flash monitor           # Windows
```

`monitor` 进入串口监视器。**退出是按 `Ctrl+]`**（不是 Ctrl+C）。

监视器里最常用的几个键：

| 按键 | 作用 |
| --- | --- |
| `Ctrl+]` | 退出监视器 |
| `Ctrl+T` 然后 `Ctrl+R` | 重启设备 |
| 设备上的 EN/RST 键 | 硬件重启 |

## 3.5 生成可直刷的合并镜像

`idf.py build` 产出的是**分段的** bin（bootloader、partition table、app 各自一个，
各自有烧录地址）。如果要给别人一个文件直接刷，用：

```bash
idf.py merge-bin -o build/ai-passport-firmware.bin
```

产出的 `merged-binary.bin` 烧录地址是 `0x0`。

> ⚠️ 小智项目对合并镜像有一条明确警告：
> "A raw merged image overwrites the gaps between segments and
> **may overwrite NVS configuration**; for an existing device, use the
> segmented addresses in `build/flash_args` and preserve identity/configuration
> partitions. **This project does not back up existing firmware before flashing.**"

翻译：**合并镜像会把分区之间的空隙也写掉，可能擦掉 NVS 里存的配置（比如 WiFi 密码）。**
给自己的设备刷之前先想清楚。

### 3.5.1 Flash 布局：8 MB 里到底装了什么

```text
偏移        内容                            来源（build/）
0x000000    bootloader（二级引导）           bootloader/bootloader.bin
0x008000    分区表（含 MD5 校验）            partition_table/partition-table.bin
0x009000    NVS 数据区 0x6000（你的设置）     不由构建产物提供
0x00F000    PHY 校准数据 0x1000               不由构建产物提供
0x010000    应用镜像 factory（占满剩余）       FoloToy-AI-Passport.bin
```

### 3.5.2 两个 `.bin` 别搞混（这是能烧“砖”的坑）

| 产物 | 内容 | 烧录地址 | 用途 |
| --- | --- | --- | --- |
| `FoloToy-AI-Passport.bin`（**没有** full） | **只有 app** | **只能 0x10000** | 分段烧录用 |
| `FoloToy-AI-Passport-full.bin` | bootloader + 分区表 + app（空隙已填充） | **0x0 整片** | 空白板、出厂、发布 |

> ⚠️ **`FoloToy-AI-Passport.bin` 绝对不能烧到 `0x0`。**
> 它只是应用，缺 bootloader 和分区表。烧错的表现是“烧完反复重启、日志乱码”——
> 这时整片重刷 `full.bin` 就能救回来。

官方门禁产出的就是 `full.bin`（`tools/validate.sh` → `merge-bin` →
`verify_firmware.py` 校验布局 → `archive_firmware.py` 归档），
**发布只上传 full.bin，不要自己拼镜像。**

### 3.5.3 esptool 用下划线，idf.py 用连字符

这是 v5.5.3 自带的 esptool 4.x 的一个拼写陷阱，两套命令**不要混**：

```bash
# esptool 直接调用：子命令是【下划线】
python -m esptool --chip esp32c3 -p PORT write_flash 0x0 build/FoloToy-AI-Passport-full.bin
python -m esptool --chip esp32c3 -p PORT erase_region 0x9000 0x6000   # 只擦 NVS
python -m esptool --chip esp32c3 -p PORT flash_id                     # 探测芯片
```

```bash
# idf.py 的动作名仍是【连字符】
idf.py flash            idf.py erase-flash            idf.py merge-bin
```

网上 esptool v5 教程里的 `write-flash`（连字符）在这个版本会报 usage 错误。

### 3.5.4 救砖：先别慌，也别乱按

ESP32-C3 **几乎不可能真正变砖**——bootloader 在出厂 ROM 里，芯片永远能响应下载。
按这个顺序排查：

1. **换线、直连电脑**（80% 的“砖”是数据线或 Hub 的问题）；
2. 手动进下载模式的 strapping 脚是 **GPIO9**（上电/复位时拉低）。
   ⚠️ **三个功能键接在 GPIO0 的 ADC 分压网络上，不能当 BOOT 键用**——
   别照抄“按住 BOOT 再按 EN”的老教程；
   正常情况 esptool 会通过原生 USB-Serial-JTAG 自动复位进下载模式，无需手动操作；
3. 整片刷 `full.bin` 让三个镜像回到一致状态；
4. 还不行就降波特率：`-b 115200`；
5. 用 `flash_id` 判断芯片本身是否活着——能打印 `Flash size: 8MB` 就说明
   硬件和连线正常，问题在固件内容。

## 3.6 常用命令速查

**默认用这些**（官方口径，`validate.sh` 是完整门禁）：

```bash
./tools/validate.sh             # 完整验证：静态 + 固件（需先激活 ESP-IDF 5.5.3）
./tools/validate.sh --static    # 仓库一致性 + workflow + 文档链接 + 敏感信息 + host tests
./tools/validate.sh --firmware  # 干净构建 + merge-bin + 偏移/分区布局校验
idf.py --ccache build           # 增量开发（开 ccache）
```

**日常开发用这些**：

```bash
idf.py set-target esp32c3   # 设定芯片（首次 / 换过 defaults 后重新同步 sdkconfig）
idf.py build                # 增量编译
idf.py -p COM4 flash        # 烧录
idf.py -p COM4 monitor      # 看日志
idf.py -p COM4 flash monitor# 烧完接着看
idf.py menuconfig           # 改配置（图形界面）
idf.py fullclean            # 只清过期生成状态（勿用于清理源码改动）
idf.py size                 # 看固件体积
idf.py size-components      # 看每个组件占多少
idf.py merge-bin -o out.bin # 合并镜像
idf.py erase-flash          # 全片擦除（谨慎）
```

> CI 与本地**用同一个脚本**。若 CI 和本地行为不同，应修脚本或环境，
> 而不是维护两份命令。
> 另：`dependencies.lock` 锁定了托管组件版本，改了 `idf_component.yml`
> 必须用 IDF 5.5.3 重新生成锁文件并**随 manifest 一起提交**；
> 普通构建不该产生未提交的锁文件差异。

> `idf.py size` 值得经常跑。官方默认 `factory` 约 **7.9 MB**（不是 3 MB——
> 那是 PokeWalk 为了塞 recovery 自己定的契约，见第 1.6 节）；
> 但 Wi-Fi + LVGL + 中文字库很容易把固件顶到 1.5 MB 以上，
> 所以**按你自己的分区表算容量账**，别拿别人的数字当上限。

## 3.7 跑起来之后你会看到什么

**官方基线（仓库 `folotoy/ai-passport`）开机进「测试菜单」——七张卡片，不是直达某个玩法。**
这是设计如此：这个菜单是用来**验证硬件**的（见下方“衍生应用规则”），不是给你套壳的应用模板。

`main/main.c` 里有一个 `DEMOS[]` 数组，注册了 **7 项**（下标 0~6）：

| 下标 | 菜单项 | 验证什么 | 源码 |
| --- | --- | --- | --- |
| 0 | Display | 屏幕（色块、刷新、背光） | `main/demo_display.c` |
| 1 | Button | 按键（**实时显示 ADC 电压**，标定时用它） | `main/demo_button.c` |
| 2 | Audio | 1 kHz 方波播放 / 录 3 秒回放 | `main/demo_audio.c` |
| 3 | Battery | CW2017 电量与电池电压 | `main/demo_battery.c` |
| 4 | Wi-Fi | 扫描附近 AP（**只扫描不连接**，不存凭证） | `main/demo_wifi.c` |
| 5 | BLE | 蓝牙广播（手机可扫到 `FoloPassport`） | `main/demo_ble.c` |
| 6 | Low Power | light / deep sleep + RTC 定时器唤醒 | `main/demo_low_power.c` |

> 第 24–31 章会**逐行拆解这 7 个官方 demo** 的源码（`main/demo_*.c`），
> 看它们怎么用 BSP、LVGL 和 FreeRTOS 把这些功能落地。

> ⚠️ **关于 Barbapapa**：本书第 18 章的「巴巴爸爸角色图鉴」**不在官方仓库里**。
> 它是作者（你）用 **Trae** 在自己的工作副本中生成的实战项目（图片 + 中文 + 语音三件套），
> 被放在「实战拆解」部分当范例。官方 `folotoy/ai-passport` 既没有 `demo_barbapapa.c`，
> 也没有 `BOOT_DEMO_INDEX` / `boot_into_demo()` 这类开机直达宏——那些只存在于作者自己的工作副本。
> 所以你 clone 到官方仓库看到的是七卡片菜单，不是巴巴爸爸；这完全正常。

进任意页面后**长按 OK** 都走 EXIT 流程回到菜单——这是 `main.c` 的全局拦截，你的页面不需要自己处理。

交互约定（社区通用，你写自己的应用时也要遵守）：

```text
上 / 下 短按   = 移动选中项
确定 短按      = 进入
确定 长按      = 返回
```

> 官方《衍生应用必须重新设计 UI》规则：
> "Reusing the current demo test menu, screens, or visual shell is prohibited;
> renaming, recoloring, or adding a feature to that shell does not count as a
> redesign."

也就是说：**这个菜单是用来验证硬件的，不是给你套壳的。**
做自己的应用必须自己画界面。但 BSP 和非 UI 的逻辑可以随便复用。

## 3.8 小结

- 版本：**学开发用 5.5.3，做 AI 语音直接上 6.1**；
- Windows 用 “ESP-IDF CMD” 终端，Linux 记得 `source export.sh`；
- `idf.py build` 跑不起来时用 **ninja 绝对路径 + `*>` 落盘**（3.3.1），并校验退出码；
- `set-target esp32c3` 只在首次/换芯片时跑；
- 监视器退出是 `Ctrl+]`；
- 合并镜像可能覆盖 NVS，刷之前想清楚；
- 官方 demo 菜单是**验证工具**，不是应用模板。

下一章开始讲 BSP——你今后 90% 的硬件操作都要通过它。
