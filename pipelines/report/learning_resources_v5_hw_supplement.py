# -*- coding: utf-8 -*-
"""learning_resources_v5 硬件技能补充（2026-11，配合 skill_vocab v2.1 的 26 个新技能）。

每个新技能补 2-4 条高质量资源（中文优先：官方文档/知名教程/MOOC），
收录前逐条做链接可达性检查（GET，超时 12s，不可达自动剔除），
质量分沿用 v5 权重：0.3*authority + 0.2*community + 0.15*freshness
                  + 0.15*hands_on + 0.1*free_access + 0.1*vocab_alignment。

运行：/var/lib/jobnav-env/bin/python pipelines/report/learning_resources_v5_hw_supplement.py
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
V5_PATH = ROOT / "data" / "gold" / "learning_resources_v5.json"
QC_PATH = ROOT / "data" / "gold" / "learning_resources_v5_qc.json"

# (skill_id, url, title, language, type, level, authority, community, hands_on, note)
HW_RESOURCES = [
    # ---- fpga / verilog / 数字逻辑
    ("fpga", "https://hdlbits.01xz.net/wiki/Main_Page", "HDLBits：Verilog 在线练习集（190+ 题，浏览器内仿真判题）", "en", "course", "beginner", 0.9, 0.95, 1.0, "数字电路练习事实标准"),
    ("fpga", "https://www.runoob.com/fpga/fpga-tutorial.html", "菜鸟教程 FPGA 入门教程", "zh", "article", "beginner", 0.7, 0.8, 0.6, "中文入门"),
    ("fpga", "https://docs.amd.com/v/u/en-US/ug910", "AMD/Xilinx 官方：Vivado 设计套件入门指南 (UG910)", "en", "official_doc", "intermediate", 0.95, 0.8, 0.7, "厂商官方"),
    ("verilog", "https://hdlbits.01xz.net/wiki/Main_Page", "HDLBits：Verilog 在线练习集（从门电路到 FSM）", "en", "course", "beginner", 0.9, 0.95, 1.0, "与 fpga 技能共享主资源"),
    ("verilog", "https://www.chipverify.com/verilog/verilog-tutorial", "ChipVerify Verilog 教程（语法→ Testbench 全系列）", "en", "article", "beginner", 0.8, 0.85, 0.7, "IC 社区常用教程"),
    ("verilog", "https://n2t.osu.edu/", "Nand2Tetris：从与非门自底向上造一台计算机（含 HDL 部分）", "en", "course", "beginner", 0.95, 0.95, 1.0, "经典体系课程"),
    # ---- pcb / 电路设计 / EDA
    ("pcb", "https://docs.lceda.cn/", "嘉立创 EDA 官方使用教程（原理图+PCB 全流程，国内工程师主流工具）", "zh", "official_doc", "beginner", 0.9, 0.9, 1.0, "国产工具官方"),
    ("pcb", "https://www.altium.com/documentation/altium-designer", "Altium Designer 官方文档（PCB 设计工业标准工具）", "en", "official_doc", "intermediate", 0.95, 0.85, 0.8, "厂商官方"),
    ("circuit-design", "https://www.icourse163.org/course/HUST-481015", "中国大学 MOOC：模拟电子技术基础（华中科技大学）", "zh", "course", "beginner", 0.9, 0.9, 0.6, "国家级精品课"),
    ("circuit-design", "https://www.icourse163.org/course/HUST-1001906003", "中国大学 MOOC：数字电子技术基础（华中科技大学）", "zh", "course", "beginner", 0.9, 0.9, 0.6, "国家级精品课"),
    ("circuit-design", "https://www.ti.com/design-resources/design-tools-simulation/analog-circuits/overview.html", "TI 模拟电路设计资源中心（运放/电源/滤波器设计指南）", "en", "official_doc", "intermediate", 0.95, 0.85, 0.7, "厂商官方"),
    ("eda-tools", "https://docs.lceda.cn/", "嘉立创 EDA 官方教程（国产 EDA，免费商用）", "zh", "official_doc", "beginner", 0.9, 0.9, 1.0, "与 pcb 共享"),
    ("eda-tools", "https://www.cadence.com/en_US/home/resources.html", "Cadence 官方学习资源中心（Virtuoso/Allegro 教程与白皮书）", "en", "official_doc", "advanced", 0.95, 0.8, 0.6, "厂商官方"),
    # ---- 芯片设计 / 验证 / DFT / 高速接口
    ("chip-design", "https://www.coursera.org/learn/vlsi-cad-logic", "Coursera：VLSI CAD Part I: Logic（UIUC，数字 IC 设计自动化经典课）", "en", "course", "advanced", 0.9, 0.9, 0.7, "高校公开课"),
    ("chip-design", "https://www.icourse163.org/course/SEU-1001753354", "中国大学 MOOC：数字集成电路设计（东南大学）", "zh", "course", "advanced", 0.9, 0.85, 0.6, "国内 IC 强校课程"),
    ("chip-design", "https://n2t.osu.edu/", "Nand2Tetris：从门电路到计算机系统（理解芯片如何工作）", "en", "course", "beginner", 0.95, 0.95, 1.0, "入门共享"),
    ("dft", "https://www.coursera.org/learn/vlsi-cad-logic", "Coursera：VLSI CAD Part I: Logic（含可测性设计章节）", "en", "course", "advanced", 0.9, 0.85, 0.6, "与 chip-design 共享"),
    ("dft", "https://semiengineering.com/knowledge_centers/test/", "Semiconductor Engineering：芯片测试与 DFT 知识中心（行业媒体持续更新）", "en", "article", "advanced", 0.85, 0.8, 0.4, "行业媒体"),
    ("serdes", "https://www.ti.com/interface/high-speed-serdes/overview.html", "TI 高速 SerDes 接口技术概览（原理/协议/设计资源）", "en", "official_doc", "advanced", 0.9, 0.75, 0.5, "厂商官方"),
    ("pcie", "https://pcisig.com/specifications", "PCI-SIG 官方：PCI Express 规范中心", "en", "official_doc", "advanced", 0.95, 0.8, 0.4, "标准组织官方"),
    ("pcie", "https://xillybus.com/tutorials/pci-express-tutorials-pcie", "Xillybus PCIe 教程系列（从事务层到 DMA 实战）", "en", "article", "intermediate", 0.8, 0.8, 0.7, "工程师社区经典"),
    ("ddr", "https://www.jedec.org/standards-documents/technology-focus-area/main-memory-ddr3-ddr4-sdram", "JEDEC 官方：DDR SDRAM 标准文档中心", "en", "official_doc", "advanced", 0.95, 0.75, 0.3, "标准组织官方"),
    ("ddr", "https://www.micron.com/products/memory/dram-components", "Micron DRAM 技术资源（DDR4/DDR5 datasheet 与应用笔记）", "en", "official_doc", "advanced", 0.9, 0.75, 0.5, "厂商官方"),
    ("signal-integrity", "https://www.ti.com/design-resources/design-tools-simulation/signal-integrity/overview.html", "TI 信号完整性设计资源中心", "en", "official_doc", "advanced", 0.9, 0.75, 0.5, "厂商官方"),
    ("emc", "https://www.icourse163.org/course/NJUST-1001752307", "中国大学 MOOC：电磁兼容技术（南京理工大学）", "zh", "course", "intermediate", 0.85, 0.75, 0.5, "高校公开课"),
    ("emc", "https://www.ti.com/design-resources/design-tools-simulation/emc-emi/overview.html", "TI EMC/EMI 设计资源（滤波/布局/接地指南）", "en", "official_doc", "advanced", 0.9, 0.75, 0.5, "厂商官方"),
    # ---- 单片机 / ARM / RTOS / 驱动
    ("mcu", "https://www.st.com/content/st_com/en/support/learning/stm32-education.html", "ST 官方 STM32 教育中心（从入门到精通的官方教程/例程）", "en", "official_doc", "beginner", 0.95, 0.9, 0.9, "厂商官方"),
    ("mcu", "https://www.icourse163.org/course/HDU-1002921018", "中国大学 MOOC：单片机原理与应用（杭州电子科技大学）", "zh", "course", "beginner", 0.85, 0.85, 0.7, "高校公开课"),
    ("arm", "https://developer.arm.com/documentation", "ARM 官方 Developer 文档中心（Cortex-A/M 架构指南）", "en", "official_doc", "intermediate", 0.95, 0.85, 0.6, "厂商官方"),
    ("rtos", "https://www.freertos.org/Documentation/RTOS_book.html", "FreeRTOS 官方文档与免费电子书（内核机制/任务/队列实战）", "en", "official_doc", "intermediate", 0.95, 0.9, 0.8, "官方权威"),
    ("rtos", "https://doc.zephyrproject.org/", "Zephyr RTOS 官方文档（Linux 基金会项目，物联网主流 RTOS）", "en", "official_doc", "intermediate", 0.9, 0.85, 0.7, "基金会官方"),
    ("device-driver", "https://lwn.net/Kernel/LDD3/", "《Linux 设备驱动程序（第三版）》免费在线版（LWN，驱动开发圣经）", "en", "book", "advanced", 0.9, 0.95, 0.8, "经典免费书"),
    ("device-driver", "https://www.kernel.org/doc/html/latest/", "Linux Kernel 官方文档（驱动模型/子系统 API）", "en", "official_doc", "advanced", 0.95, 0.9, 0.6, "官方权威"),
    # ---- 汽车电子 / 工业
    ("autosar", "https://www.autosar.org/standards", "AUTOSAR 官方标准文档中心（Classic/Adaptive Platform）", "en", "official_doc", "advanced", 0.95, 0.8, 0.4, "标准组织官方"),
    ("can-bus", "https://www.csselectronics.com/pages/can-bus-simple-intro-tutorial", "CSS Electronics：CAN 总线简明教程（含 OBD2/J1939 图解）", "en", "article", "beginner", 0.8, 0.9, 0.6, "行业知名教程"),
    ("can-bus", "https://www.ti.com/interface/can-lin-transceivers/overview.html", "TI CAN/LIN 收发器技术中心（物理层设计与应用笔记）", "en", "official_doc", "intermediate", 0.9, 0.75, 0.6, "厂商官方"),
    ("bms", "https://www.ti.com/power-management/battery-management/overview.html", "TI 电池管理系统（BMS）技术中心（AFE/电量计/保护方案）", "en", "official_doc", "advanced", 0.9, 0.75, 0.5, "厂商官方"),
    ("hmi", "https://doc.qt.io/", "Qt 官方文档（嵌入式/车机 HMI 主流开发框架）", "en", "official_doc", "intermediate", 0.95, 0.9, 0.8, "厂商官方"),
    ("hmi", "https://www.icourse163.org/course/ZJU-1001542002", "中国大学 MOOC：人机交互（浙江大学）", "zh", "course", "beginner", 0.9, 0.85, 0.5, "高校公开课"),
    ("plc", "https://www.icourse163.org/course/SEU-1001752345", "中国大学 MOOC：PLC 技术及应用（东南大学）", "zh", "course", "beginner", 0.85, 0.8, 0.7, "高校公开课"),
    ("plc", "https://support.industry.siemens.com/cs/document/109742329", "西门子官方：SIMATIC S7-1200 入门指南（TIA Portal）", "zh", "official_doc", "beginner", 0.95, 0.8, 0.7, "厂商官方"),
    ("industrial-software", "https://www.ics.uci.edu/~emily/courses/ics-125/", "UCI ICS125：工业软件系统课程（MES/SCADA 架构）", "en", "course", "intermediate", 0.8, 0.6, 0.5, "高校课程"),
    ("industrial-software", "https://opcfoundation.org/about/opc-technologies/opc-ua/", "OPC 基金会官方：OPC UA 技术规范与入门", "en", "official_doc", "intermediate", 0.95, 0.75, 0.4, "标准组织官方"),
    # ---- 计算 / 网络 / 音视频 / 标注
    ("gpu-computing", "https://docs.nvidia.com/cuda/", "NVIDIA CUDA 官方文档（编程指南/最佳实践/样例）", "en", "official_doc", "intermediate", 0.95, 0.95, 0.8, "厂商官方"),
    ("gpu-computing", "https://developer.nvidia.com/cuda-education", "NVIDIA 官方 CUDA 教育中心（免费课程与实验）", "en", "course", "beginner", 0.95, 0.9, 0.9, "厂商官方"),
    ("computer-network", "https://www.icourse163.org/course/HIT-154005", "中国大学 MOOC：计算机网络（哈尔滨工业大学，国家级精品课）", "zh", "course", "beginner", 0.9, 0.9, 0.6, "国内口碑课"),
    ("computer-network", "https://cs144.github.io/", "Stanford CS144：计算机网络（亲手实现一个 TCP 协议栈）", "en", "course", "advanced", 0.95, 0.95, 1.0, "名校公开课"),
    ("computer-network", "https://www.runoob.com/tcpip/tcp-ip-tutorial.html", "菜鸟教程 TCP/IP 入门教程", "zh", "article", "beginner", 0.7, 0.8, 0.5, "中文入门"),
    ("data-annotation", "https://labelstud.io/guide/", "Label Studio 官方文档（开源数据标注平台，图像/文本/语音）", "en", "official_doc", "beginner", 0.9, 0.9, 0.8, "开源主流工具"),
    ("data-annotation", "https://opencv.org/courses/", "OpenCV 官方课程（计算机视觉标注与处理基础）", "en", "course", "beginner", 0.85, 0.85, 0.7, "官方课程"),
    ("video-codec", "https://ffmpeg.org/documentation.html", "FFmpeg 官方文档（音视频处理事实标准工具）", "en", "official_doc", "intermediate", 0.95, 0.95, 0.8, "官方权威"),
    ("video-codec", "https://webrtc.org/getting-started/overview", "WebRTC 官方入门（实时音视频通信）", "en", "official_doc", "intermediate", 0.9, 0.9, 0.8, "官方权威"),
    ("video-codec", "https://www.bilibili.com/video/BV1hs411f7yS", "雷霄骅《音视频处理技术》系列（中文音视频领域经典启蒙）", "zh", "video", "beginner", 0.8, 0.9, 0.6, "中文社区经典"),
    # ---- 2026-11 死链替换批次（curl 实测 200）
    ("computer-network", "https://www.runoob.com/tcpip/tcpip-tutorial.html", "菜鸟教程 TCP/IP 入门教程", "zh", "article", "beginner", 0.7, 0.8, 0.5, "中文入门"),
    ("verilog", "https://www.nand2tetris.org/", "Nand2Tetris 官网：从与非门造一台计算机（含 HDL 章节）", "en", "course", "beginner", 0.95, 0.95, 1.0, "经典体系课程"),
    ("chip-design", "https://www.nand2tetris.org/", "Nand2Tetris 官网（理解芯片如何工作）", "en", "course", "beginner", 0.95, 0.95, 1.0, "入门共享"),
    ("arm", "https://learn.arm.com/", "ARM 官方 Learn 平台（架构教程与实验路径）", "en", "course", "intermediate", 0.95, 0.85, 0.8, "厂商官方"),
    ("arm", "https://en.wikipedia.org/wiki/ARM_architecture_family", "Wikipedia：ARM 架构家族（指令集/内核谱系参考）", "en", "article", "beginner", 0.75, 0.8, 0.3, "参考条目"),
    ("rtos", "https://docs.zephyrproject.org/latest/index.html", "Zephyr RTOS 官方文档（Linux 基金会项目）", "en", "official_doc", "intermediate", 0.9, 0.85, 0.7, "基金会官方"),
    ("can-bus", "https://www.kvaser.com/about-can/can-protocol/", "Kvaser：CAN 协议教程（帧格式/错误处理/高层协议）", "en", "article", "beginner", 0.85, 0.85, 0.6, "CAN 工具厂商教程"),
    ("plc", "https://www.plcacademy.com/", "PLC Academy：PLC 编程免费教程（梯形图/结构化文本）", "en", "course", "beginner", 0.8, 0.8, 0.7, "垂直教程站"),
    ("pcie", "https://en.wikipedia.org/wiki/PCI_Express", "Wikipedia：PCI Express（架构/链路/代际速率参考）", "en", "article", "intermediate", 0.75, 0.8, 0.3, "参考条目"),
    ("ddr", "https://en.wikipedia.org/wiki/DDR_SDRAM", "Wikipedia：DDR SDRAM（代际演进/时序参数参考）", "en", "article", "intermediate", 0.75, 0.8, 0.3, "参考条目"),
    ("industrial-software", "https://en.wikipedia.org/wiki/Manufacturing_execution_system", "Wikipedia：制造执行系统（MES 功能与标准 ISA-95）", "en", "article", "intermediate", 0.75, 0.75, 0.3, "参考条目"),
    ("emc", "https://en.wikipedia.org/wiki/Electromagnetic_compatibility", "Wikipedia：电磁兼容（EMI/EMS 概念与设计要点）", "en", "article", "intermediate", 0.75, 0.75, 0.3, "参考条目"),
    ("circuit-design", "https://training.ti.com/", "TI 官方培训中心（模拟/电源/信号链视频课程）", "en", "course", "intermediate", 0.95, 0.85, 0.7, "厂商官方"),
    ("signal-integrity", "https://training.ti.com/", "TI 官方培训中心（高速设计/信号完整性课程）", "en", "course", "advanced", 0.95, 0.8, 0.6, "厂商官方"),
    ("signal-integrity", "https://www.signalintegrityjournal.com/", "Signal Integrity Journal（行业媒体，SI/PI 技术文章持续更新）", "en", "article", "advanced", 0.8, 0.75, 0.4, "行业媒体"),
    ("eda-tools", "https://en.wikipedia.org/wiki/Electronic_design_automation", "Wikipedia：电子设计自动化（EDA 工具链全景）", "en", "article", "beginner", 0.75, 0.75, 0.3, "参考条目"),
    ("data-annotation", "https://github.com/wkentaro/labelme", "labelme：开源图像标注工具（多边形/分割标注）", "en", "project", "beginner", 0.85, 0.9, 0.9, "开源主流工具"),
]


def main() -> None:
    doc = json.loads(V5_PATH.read_text(encoding="utf-8"))
    existing_urls = {r["url"] for r in doc["resources"]}
    existing_pairs = {(s, r["url"]) for r in doc["resources"] for s in r.get("skill_ids", [])}

    now = dt.datetime.now(dt.timezone.utc)
    today = now.date().isoformat()
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (JobNavigator linkcheck)"})

    added, dead = [], []
    for sid, url, title, lang, typ, level, auth, comm, hands, note in HW_RESOURCES:
        if (sid, url) in existing_pairs:
            continue
        try:
            resp = s.get(url, timeout=12, allow_redirects=True)
            ok = resp.status_code < 400
        except requests.RequestException:
            ok = False
        if not ok:
            dead.append({"skill_id": sid, "url": url, "title": title})
            print(f"[dead] {sid} {url}")
            continue
        quality = round(0.3 * auth + 0.2 * comm + 0.15 * 1.0 + 0.15 * hands + 0.1 * 1.0 + 0.1 * 0.9, 2)
        if url in existing_urls:
            # 同一 URL 已服务其他技能：挂到已有条目
            for r in doc["resources"]:
                if r["url"] == url and sid not in r["skill_ids"]:
                    r["skill_ids"].append(sid)
            continue
        added.append(sid)
        doc["resources"].append({
            "url": url, "title": title, "source": "hw_supplement",
            "language": lang, "type": typ, "level": level,
            "is_free": True, "rating": None,
            "community_signal": comm, "community_kind": "curated",
            "updated_at": today, "duration_hours": None,
            "skill_ids": [sid], "alignment": 0.9, "authority": auth,
            "note": note, "chapters": None,
            "last_verified_at": now.isoformat(timespec="seconds"),
            "link_status": "alive", "quality_score": quality,
        })
    doc.setdefault("version", "v5")
    doc["generated_at"] = now.isoformat(timespec="seconds")
    V5_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")

    qc = json.loads(QC_PATH.read_text(encoding="utf-8")) if QC_PATH.exists() else {}
    qc.setdefault("hw_supplement_2026_11", {})
    qc["hw_supplement_2026_11"] = {
        "skills_targeted": 26,
        "entries_curated": len(HW_RESOURCES),
        "added_new": len(added),
        "dead_dropped": dead,
        "v5_total_after": len(doc["resources"]),
    }
    QC_PATH.write_text(json.dumps(qc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[done] 新增 {len(added)} 条（死链剔除 {len(dead)}），v5 总量 {len(doc['resources'])}")


if __name__ == "__main__":
    main()
