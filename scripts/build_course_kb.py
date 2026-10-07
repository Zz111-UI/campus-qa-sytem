# -*- coding: utf-8 -*-
"""
课程外接知识库构建器：从 data/plans.json 生成 data/course_kb.json。
每门课补充：简介 intro、学分 credit、课时 hours(按学分折算)、难易度 difficulty(易/中/难)，
并按学期时间顺序（大一上→大四下）排列。简介为规则生成通稿，以教学大纲为准。
用法：python scripts/build_course_kb.py
"""
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLANS = json.load(open(os.path.join(BASE, "data", "plans.json"), encoding="utf-8"))

# ---------- 难度判定（关键词优先级：难 > 易 > 中） ----------
HARD_KEYS = ["高等数学", "数学分析", "线性代数", "概率论", "数理统计", "复变函数", "积分变换",
             "离散数学", "大学物理", "普通物理", "物理化学", "有机化学", "无机化学", "分析化学",
             "仪器分析", "化工原理", "反应工程", "热力学", "传递过程", "电路", "模拟电子技术",
             "数字电子技术", "数字逻辑", "电磁场", "信号与", "自动控制原理", "现代控制理论",
             "运筹学", "数据结构", "编译原理", "操作系统", "计算机组成原理", "系统结构",
             "随机过程", "数值分析", "最优化", "数字信号处理", "通信原理", "毕业设计", "毕业论文",
             "模式识别", "机器学习", "深度学习"]
EASY_KEYS = ["体育", "军事", "思想道德", "马克思主义", "毛泽东", "新时代", "形势与政策", "国家安全",
             "心理健康", "就业指导", "创业基础", "伦理", "导读", "讲座", "美育", "人文", "艺术",
             "素质", "写作", "英语听力", "口语", "普法", "国情", "党性", "团", "劳动教育",
             "当代世界经济", "中国共产党", "社会主义", "法治思想", "文化思想", "精神谱系", "改革开放",
             "五百年"]
MEDIUM_FALLBACK_SECTION = {"实践环节必修": "中", "实践环节选修": "中"}

def difficulty(name, section):
    base = "中"
    if any(k in name for k in HARD_KEYS):
        base = "中" if ("导论" in name or "概论" in name or "通论" in name) else "难"
    elif any(k in name for k in EASY_KEYS):
        base = "易"
    elif section in MEDIUM_FALLBACK_SECTION:
        base = "中"
    # 实验/实习/实训/实践类：动手为主、考核较宽，较理论课降一档
    if any(k in name for k in ["实验", "实习", "实训", "实践", "训练", "观摩", "劳动"]):
        base = {"难": "中", "中": "易", "易": "易"}[base]
    return base

# ---------- 简介：高频课程人工通稿 + 分类模板兜底 ----------
INTRO_MAP = {
    "高等数学": "一元与多元微积分、级数与常微分方程，是工科最重要的数学基础。",
    "线性代数": "矩阵、向量空间与线性变换，为机器学习与控制理论提供工具。",
    "概率论": "随机现象的数学描述与统计推断基础。",
    "离散数学": "集合论、图论、组合与数理逻辑，计算机科学的数学基础。",
    "大学物理": "力学、电磁学、热学与光学的基本规律。",
    "数据结构": "线性表、树、图与排序检索算法，编程与考研核心课。",
    "算法设计与分析": "分治、动态规划、贪心等算法策略与复杂度分析。",
    "操作系统": "进程管理、内存、文件系统与并发，专业核心与考研重点。",
    "计算机组成原理": "CPU、存储与总线的工作原理，软硬件衔接核心课。",
    "计算机网络": "TCP/IP 体系结构与网络编程基础。",
    "数据库原理": "关系模型、SQL、事务与数据库设计。",
    "编译原理": "词法、语法、语义分析到代码生成的编译器全流程。",
    "软件工程": "需求、设计、测试与项目管理等软件生产方法论。",
    "面向对象程序设计": "以 C++/Java 讲解类、继承、多态与设计思维。",
    "Java程序设计": "Java 语言语法、集合、多线程与企业级开发入门。",
    "Python": "Python 语言程序设计基础与科学计算应用。",
    "机器学习": "监督/无监督学习模型原理与 sklearn 实践。",
    "深度学习": "神经网络、CNN/RNN/Transformer 原理与框架实践。",
    "人工智能导论": "人工智能发展脉络、典型问题求解方法概览。",
    "信号与线性系统": "连续与离散信号的时域频域分析，电类专业支柱课。",
    "自动控制原理": "经典控制理论的建模、稳定性判据与校正设计。",
    "现代控制理论": "状态空间方法、能控能观性与线性系统综合。",
    "传感器": "常见物理量传感原理与信号调理电路。",
    "嵌入式系统": "ARM/单片机外设接口与实时软件开发。",
    "电路": "电路定律、暂态分析与交流稳态，电类入门基础。",
    "化工原理": "流体流动、传热与分离单元操作的工程原理。",
    "物理化学": "化学热力学、动力学与电化学的定量规律。",
    "有机化学": "有机物结构、反应机理与合成路线。",
    "毕业设计": "综合运用四年所学完成课题研究与论文撰写。",
    "生产实习": "深入企业现场的工程实践环节。",
    "认识实习": "专业入门的感性认知与现场观摩环节。",
    "大学英语": "学术与日常英语听说读写能力培养。",
}

def intro_of(name, section, nature):
    for k, v in INTRO_MAP.items():
        if k in name:
            return v
    if section.startswith("公共基础"):
        return "公共基础课程，为专业学习与综合素质发展夯实基础。"
    if section == "专业必修":
        return f"专业核心必修课程，系统讲授「{name}」的基本概念、原理与典型应用，是后续课程与毕业设计的重要支撑。"
    if section == "专业选修":
        return f"专业拓展选修课，围绕「{name}」方向作专题讲授，适合有相关兴趣或生涯规划的同学选修。"
    if section.startswith("实践环节"):
        return f"集中实践教学环节，通过「{name}」的动手训练与综合应用强化工程实践能力。"
    return f"围绕「{name}」主题的通识拓展课程，开阔视野、完善知识结构。"


def hours_of(credit, section):
    """课时按学分折算：理论课 1学分≈16学时，实践环节 1学分≈20学时（估计值）。"""
    return round(credit * (20 if "实践" in section else 16), 0)


def term_order(year, sem):
    y = int(str(year).split("-")[0])
    return (y - 2025) * 2 + (1 if sem == 1 else 2)


def term_label(t):
    cal = 2025 + ((t - 1) // 2)
    return f"{cal}{'秋' if t % 2 == 1 else '春'}"


kb = {}
for major, p in PLANS.items():
    courses = []
    for c in p["courses"]:
        t = term_order(c["year"], c["sem"])
        d = difficulty(c["name"], c["section"])
        courses.append({
            "code": c["code"], "name": c["name"], "credit": c["credit"],
            "hours": hours_of(c["credit"], c["section"]), "difficulty": d,
            "nature": c["nature"], "section": c["section"],
            "term": t, "term_label": term_label(t),
            "summer": c["sem"] == 3,
            "intro": intro_of(c["name"], c["section"], c["nature"]),
        })
    courses.sort(key=lambda x: (x["term"], x["nature"] != "必修", -x["credit"]))
    kb[major] = {
        "college": p.get("college", ""), "grade_plan": p.get("grade", 2025),
        "grad_credit": p["grad_credit"], "duration": p.get("duration", ""),
        "degree": p.get("degree", ""), "source": f"《2025{major}执行计划》",
        "terms": 8, "courses": courses,
        "note": "课程介绍与难易度为系统按规则生成的通稿，课时按学分折算估计；选课以教务系统与教学大纲为准。",
    }

out = os.path.join(BASE, "data", "course_kb.json")
json.dump(kb, open(out, "w", encoding="utf-8"), ensure_ascii=False)
print("written:", out, os.path.getsize(out), "bytes")
for m, v in kb.items():
    dc = {}
    for c in v["courses"]:
        dc[c["difficulty"]] = dc.get(c["difficulty"], 0) + 1
    print(f"  {m}: {len(v['courses'])} 门课, 难度分布 {dc}")
