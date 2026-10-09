# -*- coding: utf-8 -*-
"""物联网五层模型覆盖度扫描：查书中每层的关键排查要素是否讲到。"""
import os, re, io, collections

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src')

LAYERS = collections.OrderedDict([
    ("L1 物理层（供电/地线/干扰/天线/温度）", [
        "供电", "电压跌落", "纹波", "地线", "共地", "干扰", "天线", "阻抗匹配",
        "RSSI", "信号强度", "温度", "接触不良", "线缆", "屏蔽", "退耦", "去耦",
        "上电时序", "复位", "看门狗", "brownout", "Brownout", "欠压",
    ]),
    ("L2 链路层（波特率/帧格式/校验/信道）", [
        "波特率", "baud", "帧格式", "校验", "CRC", "奇偶", "停止位", "数据位",
        "信道", "channel", "拥塞", "同频", "重传", "MTU", "MAC", "phy", "PHY",
        "速率", "调制",
    ]),
    ("L3 协议层（超时/重传/幂等/握手/TLS）", [
        "超时", "timeout", "重试", "retry", "退避", "backoff", "心跳", "keepalive",
        "幂等", "序号", "seq", "握手", "TLS", "证书", "cert", "校验和",
        "MQTT", "HTTP", "HTTPS", "WebSocket", "DNS", "DHCP", "NTP", "SNTP",
    ]),
    ("L4 应用层（时间同步/断网缓存/补传/状态机）", [
        "时间同步", "SNTP", "校时", "断网", "缓存", "补传", "离线", "重连",
        "状态机", "降级", "队列", "环形缓冲", "掉电保护", "原子",
    ]),
    ("L5 云端（鉴权/限流/连接数/灰度/回滚）", [
        "鉴权", "token", "Token", "密钥", "有效期", "过期", "限流", "429",
        "连接数", "证书过期", "OTA", "灰度", "回滚", "版本", "回滚分区",
    ]),
])

# 取证与排查方法要素
METHOD = [
    "万用表", "示波器", "抓包", "Wireshark", "逻辑分析仪", "复现", "频率",
    "日志", "时间戳", "报文", "现场", "对比实验", "最小复现", "对照组",
    "判定", "判据", "阈值", "基线", "长时间", "压力测试", "老化",
]


def read(fn):
    return io.open(os.path.join(BASE, fn), encoding='utf-8').read()


def main():
    files = sorted(f for f in os.listdir(BASE) if f.endswith('.md'))
    corpus = {f: read(f) for f in files}

    print("=" * 72)
    print("物联网五层模型覆盖度扫描（全书 %d 篇）" % len(files))
    print("=" * 72)

    for layer, kws in LAYERS.items():
        print("\n### %s" % layer)
        hit = collections.Counter()
        for kw in kws:
            total = 0
            where = []
            for f, t in corpus.items():
                n = t.count(kw)
                if n:
                    total += n
                    where.append(f)
            hit[kw] = total
        present = {k: v for k, v in hit.items() if v}
        absent = [k for k, v in hit.items() if not v]
        print("  已有(%d): %s" % (len(present),
              " ".join("%s(%d)" % (k, v) for k, v in sorted(present.items(), key=lambda x: -x[1])[:16])))
        if absent:
            print("  【零覆盖】%s" % "、".join(absent))

    print("\n" + "=" * 72)
    print("取证与排查方法要素")
    print("=" * 72)
    pres, ab = [], []
    for kw in METHOD:
        total = sum(t.count(kw) for t in corpus.values())
        (pres if total else ab).append((kw, total))
    print("  已有: %s" % " ".join("%s(%d)" % (k, v) for k, v in sorted(pres, key=lambda x: -x[1])))
    print("  【零覆盖】%s" % "、".join(k for k, _ in ab))


if __name__ == '__main__':
    main()
