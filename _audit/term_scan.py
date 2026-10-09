# -*- coding: utf-8 -*-
"""术语变体扫描：同一概念在全书中用了几种说法"""
import os, re, json, collections

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src')

# 概念组：规范说法 -> 所有可能写法
GROUPS = {
    '烧录/下载': ['烧录', '下载', '刷机', '烧写', '下载到', '刷入'],
    '引脚': ['引脚', '管脚', 'IO 口', 'IO口', '管脚', 'Pin', 'pin'],
    '串口': ['串口', 'UART', '串行口', 'COM 口', '串口终端'],
    '任务/线程': ['任务', '线程', 'Task', 'task', 'Thread'],
    '固件/程序': ['固件', '程序', '固件程序'],
    '句柄': ['句柄', 'handle', 'Handle', '描述符'],
    '缓冲区': ['缓冲区', '缓存', '缓冲', 'buffer', 'Buffer', 'BUFF'],
    '回调': ['回调', 'callback', 'Callback', '回掉'],
    '中断': ['中断', 'ISR', 'irq', 'IRQ'],
    '轮询': ['轮询', '查询', 'poll', 'Poll', '轮循'],
    '阻塞/挂起': ['阻塞', '挂起', '卡住', '堵住'],
    '栈/堆': ['栈', '堆', '堆栈', 'stack', 'heap'],
    '编译/构建': ['编译', '构建', 'build', 'Build'],
    '组件': ['组件', 'component', 'Component', '模块'],
    '示例/例程': ['例程', '示例', 'demo', 'Demo', '样例', 'sample'],
    '终端/监视器': ['终端', '控制台', 'monitor', '监视器', '命令行'],
    '屏幕/显示屏': ['屏幕', '显示屏', '显示器', 'LCD', '屏'],
    '熄屏': ['熄屏', '关屏', '息屏', '灭屏', '关掉屏幕', '关闭屏幕'],
    '初始化': ['初始化', '初始话', 'init', 'Init'],
    '释放内存': ['释放', '回收', 'free', 'Free', '释放掉'],
    '芯片': ['芯片', 'MCU', 'SoC', '单片机', '主控'],
    '开发板': ['开发板', '板子', '板卡', '这块板'],
    '配网/联网': ['配网', '联网', 'provisioning', 'Provisioning', ' provisioning'],
    '唤醒': ['唤醒', '唤酲', 'wakeup', 'Wakeup'],
    '掉电': ['掉电', '断电', '掉电保存', 'power down'],
    '分区表': ['分区表', 'partition table', '分区'],
    '帧率': ['帧率', 'FPS', 'fps', '刷新率'],
    '字库/字体': ['字库', '字体', 'font', 'Font'],
    '锁': ['互斥锁', '互斥量', 'mutex', 'Mutex', '信号量', 'semaphore'],
    '队列': ['队列', 'queue', 'Queue', '消息队列'],
    '看门狗': ['看门狗', 'watchdog', 'Watchdog', 'WDT', '喂狗'],
    '深睡/浅睡': ['深睡', '深度睡眠', 'deep sleep', '浅睡', 'light sleep', '轻度睡眠'],
    '头文件': ['头文件', '.h 文件', 'header'],
    '宏': ['宏', '宏定义', 'macro', 'define'],
    '波特率': ['波特率', 'baud', 'baudrate'],
    '驱动': ['驱动', 'driver', 'Driver', '驱动程序'],
    'SDK/框架': ['SDK', '框架', 'framework', 'IDF'],
    '板级支持包': ['BSP', '板级支持包', '板载支持包'],
}

def strip_code(text):
    """剥离围栏代码块与行内代码，避免把代码里的标识符当正文统计"""
    text = re.sub(r'```.*?```', '', text, flags=re.S)
    text = re.sub(r'`[^`\n]*`', '', text)
    return text

def main():
    files = sorted(f for f in os.listdir(SRC) if f.endswith('.md'))
    # group -> variant -> {file: count}
    result = {}
    for g, variants in GROUPS.items():
        per_variant = {}
        for fn in files:
            path = os.path.join(SRC, fn)
            raw = open(path, encoding='utf-8').read()
            body = strip_code(raw)
            for v in variants:
                # 中文直接计数；英文用词边界
                if re.search(r'[a-zA-Z]', v):
                    n = len(re.findall(r'\b' + re.escape(v) + r'\b', body))
                else:
                    n = body.count(v)
                if n:
                    per_variant.setdefault(v, {})[fn] = n
        if per_variant:
            result[g] = per_variant

    # 输出：只显示"一个概念出现 2 种以上说法"的组
    print('=' * 70)
    print('术语变体扫描结果（概念 -> 说法 -> 总次数 / 分布文件数）')
    print('=' * 70)
    flagged = []
    for g, per_variant in result.items():
        total = {v: sum(d.values()) for v, d in per_variant.items()}
        kinds = len(total)
        if kinds < 2:
            continue
        # 按总次数排序
        items = sorted(total.items(), key=lambda x: -x[1])
        dominant, dcount = items[0]
        # 计算"次要用法"占比
        others = sum(c for _, c in items[1:])
        ratio = others / (dcount + others) if (dcount + others) else 0
        mark = '!!' if (kinds >= 3 or ratio > 0.25) else '  '
        print(f'\n{mark} [{g}]  共 {kinds} 种说法')
        for v, c in items:
            nfiles = len(per_variant[v])
            print(f'     {v:<16} {c:>5} 次 / {nfiles:>2} 篇')
        flagged.append({
            'group': g, 'kinds': kinds,
            'variants': [{'v': v, 'c': c, 'files': sorted(per_variant[v].keys())} for v, c in items],
            'other_ratio': round(ratio, 3),
        })

    json.dump(flagged, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'term_variants.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(f'\n\n共标记 {len(flagged)} 组需要人工判定')

if __name__ == '__main__':
    main()
