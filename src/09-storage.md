# 9. 存储：NVS、分区表与素材

> **可抄代码**：[D.9 NVS](D-module-cookbook.md#d9-存储nvs) · [D.16 素材进固件](D-module-cookbook.md#d16-素材进固件)。


这一章回答三个问题：配置存哪、大素材放哪、怎么选。

## 9.1 先看清 8 MB Flash 的格局

```text
0x0000   ┌──────────────────┐
         │ bootloader       │  约 28 KB
0x8000   ├──────────────────┤
         │ partition table  │  4 KB
0x9000   ├──────────────────┤
         │ nvs      (24 KB) │  ← 你的设置、WiFi 密码
0xf000   ├──────────────────┤
         │ phy_init (4 KB)  │  ← 射频校准，别动
0x10000  ├──────────────────┤
         │                  │
         │ factory (app)    │  ← 你的固件，通常 3 MB 左右
         │                  │
         ├──────────────────┤
         │ 自定义数据分区    │  ← 素材、文件系统（可选）
         └──────────────────┘
```

分区表就是一张 CSV：

```csv
# Name,   Type, SubType, Offset,   Size,     Flags
nvs,      data, nvs,     0x9000,   0x6000,
phy_init, data, phy,     0xf000,   0x1000,
factory,  app,  factory, 0x10000,  0x7f0000,
```

规则：

- `Offset` 必须 **4 KB 对齐**（`0x1000` 的倍数）；
- app 分区的 offset 必须是 `0x10000` 起步；
- `Size` 可以留空，表示“剩下的都给它”（只能有一个留空）；
- 自定义子类型可以用 `0x40`–`0xFE`。

**社区契约：app 分区上限 3 MB。** PokeWalk 的 `firmware/README.md` 把它列为
“三条不能改的契约”之一，因为后面要留 recovery 分区。

## 9.2 NVS：键值对存储

NVS（Non-Volatile Storage）用来存**小量的配置数据**：WiFi 密码、音量、
亮度、你的存档。它本身只有 24 KB（可以改分区表加大）。

### 初始化（含标准的容错写法）

```c
esp_err_t e = nvs_flash_init();
if (e == ESP_ERR_NVS_NO_FREE_PAGES || e == ESP_ERR_NVS_NEW_VERSION_FOUND) {
    nvs_flash_erase();
    nvs_flash_init();
}
```

**这个 if 是必须的**，几乎所有项目都这么写。
NVS 分区满了或者版本变了，不擦一次就打不开。

### 读写

```c
nvs_handle_t h;
nvs_open("myapp", NVS_READWRITE, &h);

nvs_set_u8(h, "volume", 80);        // 写
nvs_get_u8(h, "volume", &vol);      // 读
nvs_set_str(h, "ssid", "home");
nvs_set_blob(h, "state", &save, sizeof(save));

nvs_commit(h);                      // ★ 不 commit 就丢
nvs_close(h);
```

支持的类型：`u8` / `u16` / `u32` / `i32` / `u64` / `str` / `blob`。

### 两条真实的教训

**教训 1：`nvs_commit()` 不能省。**

> 源码注释（PokeWalk `main/save.c`）：
> “**commit 不能省**——`nvs_set_blob` 只写进缓存，
> 不 commit 的话拔电就丢了，而函数返回值是成功的。”

注意后半句：**返回值是成功的**。这让它成为一个极隐蔽的 bug。

**教训 2：NVS 初始化是谁的责任要分清。**

> 源码注释（同上）：
> “第一版没有这个函数——`nvs_flash_init` 藏在 `world.c` 的 `wifi_bring_up()` 里，
> 而 `world_start` 的顺序是‘先读档、后起 WiFi’。于是读档时 NVS 还没挂载，
> `nvs_open` 直接失败，**表现为‘每次开机都是新游戏’而写入明明成功**。
> 教训是所有权：存档不依赖 WiFi，就不该等 WiFi 顺手把 NVS 带起来。”

这是本书里最好的一段“架构教训”：**不要依赖别人的副作用来初始化你的依赖。**
你的模块需要什么，就自己初始化什么。

### 整块存 vs 分开存

PokeWalk 的存档是**整个结构体当一个 blob**（约 2.2 KB）：

```c
#define NS  "pokewalk"   // NVS 命名空间
#define KEY "state"      // 整个 save_t 当一个 blob 存
```

> 作者的理由：
> “整块约 2.2 KiB，NVS 的 blob 上限是 508000 字节——绰绰有余。
> **原子性也更好**：要么整块新的，要么整块旧的，不会出现
> ‘图鉴是新的而队列是旧的’这种半更新状态。”

如果你的状态字段之间有内在一致性要求，**整块存比分开存更不容易错**。

## 9.3 素材：四种方案怎么选

| 方案 | 适合 | 上限 | 复杂度 |
| --- | --- | --- | --- |
| `EMBED_FILES` 编进固件 | 小图标、字库、证书 | app 分区剩余空间 | 低 |
| 自定义分区 + mmap | 大只读素材（WAD、图集） | 分区大小 | 中 |
| SPIFFS / LittleFS | 需要“文件”概念的音效、图片 | 分区大小 | 中 |
| NVS blob | 结构化小数据 | 508 KB/条 | 低 |

### 方案 A：EMBED_FILES

```cmake
idf_component_register(
    SRCS "main.c"
    EMBED_FILES "${CMAKE_CURRENT_LIST_DIR}/../../assets/gen1.bin"
                "${CMAKE_CURRENT_LIST_DIR}/../../assets/palettes.bin"
    EMBED_TXTFILES "certs/servercert.pem"
)
```

```c
extern const uint8_t _binary_gen1_bin_start[] asm("_binary_gen1_bin_start");
extern const uint8_t _binary_gen1_bin_end[]   asm("_binary_gen1_bin_end");
size_t len = _binary_gen1_bin_end - _binary_gen1_bin_start;
```

PokeWalk 用这招嵌了 7 个二进制素材（共 158.8 KB）：

> “资产直接嵌进 app 分区（158.8 KB，占 3 MB 的 5%）——
> 不另开数据分区：那要多一套分区表与烧写步骤，而这点体积完全放得下。”

**这是个很好的判断标准**：素材不到 app 分区的 10%，就用 EMBED，
别为了“规范”去搞一套分区和烧写流程。

### 方案 B：自定义分区 + mmap（零拷贝）

大素材的正确做法：**不读进内存，直接把 Flash 映射到地址空间**。

```c
const esp_partition_t *part = esp_partition_find_first(
        ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_ANY, "wad");
if (!part) return -1;

const void *addr = NULL;
spi_flash_mmap_handle_t handle;
esp_partition_mmap(part, 0, part->size, SPI_FLASH_MMAP_DATA, &addr, &handle);

// 之后 addr 就能当指针直接用，不占 RAM
const uint8_t *data = (const uint8_t *)addr;
```

DOOM 项目用它加载 4 MB 的 WAD 游戏数据：

```csv
wad,      data, 0x40,    0x310000, 0x4F0000,
```

**mmap 的代价不是 RAM，是 MMU 页。** ESP32-C3 只有 128 个 flash-MMU 页。
有项目实测记录：

> “无 PSRAM 也能铺满全屏美术——背景是内存映射分区里的 LVGL 索引图，
> 直接从 flash 绘制、按行解码（约 960 字节），而不是 150 KB 的帧缓冲；
> 占用芯片 128 个 flash-MMU 页中的 **83 个**。”

**83/128**——这是个惊人的数字。mmap 好用但不能滥用，页面会用完。

### 方案 C：SPIFFS（需要“文件”概念时）

音效钥匙扣项目给语音片段单独开了一个 3 MB 的 `voicefs` 分区：

```csv
voicefs,  data, spiffs,  ...,  0x300000,
```

```c
static bool fs_mount(void) {
    esp_vfs_spiffs_conf_t cfg = {
        .base_path = VOICE_FS_MOUNT,        // "/voices"
        .partition_label = VOICE_FS_PARTITION,
        .max_files = 8,
        .format_if_mount_failed = true,
    };
    esp_err_t err = esp_vfs_spiffs_register(&cfg);
    // ...
}
```

挂上之后就能用标准 C 文件 API 了：

```c
FILE *fp = fopen("/voices/001.opus", "rb");
fread(pkt, 1, plen, fp);
fclose(fp);
```

选 SPIFFS 的理由：素材数量多、需要按名字索引、需要单独烧写更新。
它的代价是要多维护一个分区镜像和烧写步骤。

## 9.4 素材是怎么“做出来”的

音效钥匙扣项目的 README 里有一条完整管线，值得参考：

> “语音片段存放在挂载于 `/voices` 的 `voicefs` SPIFFS 数据分区，
> 由 `tools/encode_voice.py` 生成（**解码 → 重采样到 8 kHz 单声道 →
> IMA-ADPCM 4bit → 生成 `main/voice_index.h` + `voicefs.img`**）。
> 应用分别烧录合并固件镜像与该数据分区。”

三个关键动作：**重采样到设备支持的采样率 → 压缩编码 → 生成索引头文件**。
索引头文件（`voice_index.h`）里是文件名到偏移的映射，
这样固件不用真的去列目录。

**这是社区的标准套路**：PC 侧用 Python 预处理，设备侧只做解码和播放。

## 9.5 解析二进制素材时的三条纪律

> 源码注释（PokeWalk `main/assets.c`）

**纪律 1：字段长度从文件头读，不要写死。**

> “上一轮踩过的坑：`convert_gen1.py` 的注释把记录长度写成 28（实际 32），
> 照那个数写固件会让第 2 条记录起整体错位 4 字节——而错位后读出的
> **仍是合法数值**（种族值、属性 id 都在 0~255 内），**不崩，只是全错**。”

这是最可怕的一类 bug：**静默错误**。所以要自洽校验：

```c
// 自洽校验：头部声明的三段长度加起来必须正好等于文件长度。
// 不校验的后果是越界读——而 flash 上越界读不会崩，
// 只会读到隔壁资产的字节当成种族值。
if (16u + cnt * rsz + pool_sz != len) { /* 报错 */ }
```

**纪律 2：不要强转指针做结构体解析。**

> “小端读取。资产全是小端……而 C3 也是小端，理论上可以直接强转指针——
> **但不要那么做**：记录不保证 2/4 字节对齐……未对齐访问在 RISC-V 上是
> **异常而非静默慢速**。”

在 x86 上未对齐访问只是慢，在 RISC-V 上直接崩。**老老实实按字节组装。**

**纪律 3：越界读不会崩。**

Flash 上越界读不会段错误，只会读到隔壁数据。
所以**每一条解析都要做范围校验**。

## 9.6 小结

- NVS 存小配置；**`nvs_commit()` 不能省**；初始化责任要分清；
- 素材 < app 分区 10% → `EMBED_FILES`；
- 大只读素材 → 自定义分区 + **mmap**（注意 MMU 页只有 128 个）；
- 需要文件语义 → SPIFFS 独立分区；
- 解析二进制：长度从文件头读、不强转指针、每段都校验范围；
- **越界读在 flash 上不崩，只会静默出错**。

下一章讲联网：先[连上 Wi-Fi](10-network.md)，再解决
[密码怎么进设备（配网）](10b-provisioning.md)，最后[拿到网怎么取数据](10c-network-data.md)。

> **延伸阅读 · 官方经验条目**：
> [视觉小说剧本包预算](https://github.com/FoloToy/ai-passport/blob/main/docs/reference/shinku-chen/vn-script-pack-budget-and-failure-modes.zh_CN.md)
> ——5.06 MB 剧本压到 1.45 MB，**块大小由“最大连续块 7.7 KB”而非空闲堆决定**（第 11 章的核心论据就来自这里）
