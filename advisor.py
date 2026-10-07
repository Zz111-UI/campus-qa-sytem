# -*- coding: utf-8 -*-
# 本文件由团队编写为主；标注 [AI编写] 的段落为开发迭代过程中由 AI（千问工作助理）生成的代码，均已标注。
"""
学习/生活顾问的核心逻辑：
- 关键词检索（模拟 RAG，演示足够；后续可换 embedding）
- 规则引擎：先修校验、学分统计、二课达标核算
- 来源卡片构造（对应 PPT 的“信息可信机制”）
"""
import json
import os
import re
from difflib import SequenceMatcher

from config import DATA_DIR


def _load(name):
    with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
        return json.load(f)


KB = _load("knowledge_base.json")
COURSES = _load("courses.json")          # 旧示例数据（化工/计算机演示专业）
try:
    PLANS = _load("plans.json")           # 真实培养方案（信息科学与技术学院 2025 级 7 专业）
except (FileNotFoundError, json.JSONDecodeError):
    PLANS = {}


def load_colleges():
    """全校学院→专业一览（来自《北京化工大学本科专业设置情况一览表》）。"""
    try:
        return _load("colleges.json")["colleges"]
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return [{"college": "信息科学与技术学院",
                 "majors": list(PLANS.keys()) or ["计算机科学与技术"]}]


# ---- 先修关系推断：培养方案原文不含先修课，用规则引擎按课程名推断 ----
# 模式: (课程名匹配关键词, [要求已修的先修课关键词...])
PREREQ_RULES = [
    ("高等数学A（II）", ["高等数学A（I）"]), ("高等数学A(II)", ["高等数学A(I)"]),
    ("高等数学B（II）", ["高等数学B（I）"]), ("概率论与数理统计", ["高等数学A（II）", "高等数学B（II）", "高等数学"]),
    ("线性代数", ["高等数学A（I）", "高等数学"]),
    ("普通物理(Ⅱ)", ["普通物理(Ⅰ)"]), ("普通物理（Ⅱ）", ["普通物理（Ⅰ）"]),
    ("大学物理实验(II)", ["大学物理实验(I)"]),
    ("数据结构", ["程序设计基础", "高级语言程序", "C语言", "Python语言程序设计", "离散数学"]),
    ("高级语言程序实践", ["程序设计基础", "高级语言程序"]),
    ("程序设计实训", ["程序设计基础"]),
    ("数字逻辑", ["电路与模拟电子技术", "大学计算机"]),
    ("计算机组成原理", ["数据结构", "数字逻辑"]),
    ("操作系统", ["数据结构", "计算机组成原理"]),
    ("数据库原理", ["数据结构"]), ("数据库系统", ["数据结构"]),
    ("计算机网络", ["数据结构", "计算机组成原理"]),
    ("编译原理", ["数据结构", "程序设计基础", "离散数学"]),
    ("软件工程", ["数据结构", "数据库原理"]),
    ("算法设计与分析", ["数据结构"]),
    ("人工智能导论", ["高等数学", "线性代数", "程序设计基础", "数据结构", "Python"]),
    ("机器学习", ["人工智能导论", "概率论", "线性代数", "数据结构"]),
    ("深度学习", ["机器学习", "人工智能导论", "Python"]),
    ("模式识别", ["机器学习", "概率论"]),
    ("计算机视觉", ["深度学习", "机器学习", "人工智能导论"]),
    ("自然语言处理", ["深度学习", "机器学习", "人工智能导论"]),
    ("信号与线性系统", ["电路与模拟电子技术", "复变函数", "高等数学", "信号"]),
    ("自动控制原理", ["信号与线性系统", "复变函数", "模拟电子技术", "电路"]),
    ("现代控制理论", ["自动控制原理", "线性代数"]),
    ("电机与拖动", ["电路与模拟电子技术", "数字逻辑"]),
    ("电力电子技术", ["模拟电子技术", "数字逻辑", "电路"]),
    ("嵌入式系统", ["数字逻辑", "计算机组成原理", "高级语言程序", "C语言", "程序设计基础"]),
    ("微机原理", ["数字逻辑", "计算机组成原理"]),
    ("单片机", ["数字逻辑", "高级语言程序", "C语言", "程序设计基础"]),
    ("PLC", ["数字逻辑", "电工"]),
    ("过程控制", ["自动控制原理"]),
    ("运动控制", ["自动控制原理", "电力电子技术"]),
    ("机器人", ["自动控制原理", "嵌入式", "程序设计基础"]),
    ("传感器", ["电路与模拟电子技术", "数字逻辑"]),
    ("检测技术与自动化装置", ["传感器", "自动控制原理"]),
    ("电子测量", ["电路与模拟电子技术", "信号与线性系统"]),
    ("数字信号处理", ["信号与线性系统", "离散数学"]),
    ("通信原理", ["信号与线性系统", "概率论"]),
    ("电磁场与微波", ["大学物理", "普通物理", "复变函数"]),
    ("高频电子线路", ["电路与模拟电子技术", "信号与线性系统"]),
    ("图像处理", ["程序设计基础", "高等数学", "数字逻辑"]),
    ("信息安全", ["计算机网络", "操作系统", "数据结构"]),
    ("网络安全", ["计算机网络", "操作系统", "数据结构"]),
    ("大数据", ["数据结构", "数据库原理", "Python", "程序设计"]),
    ("云计算", ["计算机网络", "操作系统", "虚拟化"] if False else ["计算机网络", "操作系统"]),
    ("物联网", ["计算机网络", "传感器", "嵌入式"]),
    ("数字图像处理", ["信号与线性系统", "程序设计基础", "Python", "高等数学"]),
    ("计算机系统结构", ["计算机组成原理", "操作系统"]),
    ("汇编语言", ["高级语言程序", "程序设计基础", "数字逻辑"]),
]


def _match_codes(cmap, keyword):
    """按关键词在课程表里找课程号（取学分最高的一条，避免选中习题课）。"""
    hits = [c for c in cmap.values() if keyword in c["name"]
            and "习题" not in c["name"] and "实践" not in c["name"][-2:]]
    if not hits:
        return None
    hits.sort(key=lambda c: -c["credit"])
    return hits[0]["code"]


def infer_prereqs(plan):
    """给一门专业的全部课程推断 prereq 列表（只连本专业内存在的课）。"""
    cmap = {c["code"]: c for c in plan["courses"]}
    for c in plan["courses"]:
        c["prereq"] = []
    for c in plan["courses"]:
        for name_kw, prereq_kws in PREREQ_RULES:
            if name_kw in c["name"]:
                for pk in prereq_kws:
                    pc = _match_codes(cmap, pk)
                    if pc and pc != c["code"] and pc not in c["prereq"]:
                        # 先修课必须排在本课程之前（按学期序），否则不成立
                        if course_term_index(pc, plan) < course_term_index(c["code"], plan):
                            c["prereq"].append(pc)
                break  # 一条规则命中即可，避免过度叠加
    return plan


def term_key(course):
    """1-based 全局学期序（2025级第1学期=1；暑期小学期并入该学年第2学期）。"""
    y = int(course["year"].split("-")[0])
    return (y - 2025) * 2 + (1 if course["sem"] == 1 else 2)


_TERM_CACHE = {}


def course_term_index(code, plan):
    key = id(plan)
    if key not in _TERM_CACHE:
        _TERM_CACHE[key] = {c["code"]: term_key(c) for c in plan["courses"]}
    return _TERM_CACHE[key].get(code, 999)


for _p in PLANS.values():
    infer_prereqs(_p)


# ---------------- 知识库检索 ----------------
def _similarity(question: str, item: dict) -> float:
    """关键词命中为主，整句相似度为辅，避免同义词漏检。"""
    kw = item.get("keywords", [])
    hit = sum(1 for k in kw if k in question)
    ratio = SequenceMatcher(None, question, item["question"]).ratio()
    score = hit * 2.0 + ratio
    if item.get("category") and item["category"] in question:
        score += 1.0
    if item.get("answer") and any(k in question for k in kw if len(k) >= 3):
        score += 0.5
    return score


def search_kb(question: str, top_k: int = 3):
    scored = [(_similarity(question, it), it) for it in KB]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [it for s, it in scored[:top_k] if s > 0.8]


def build_source_cards(items):
    """把命中的知识条目转成前端可渲染的来源卡片（同一出处只保留一张）。"""
    cards, seen = [], set()
    for it in items:
        key = (it.get("doc_name") or it.get("source"), it.get("source"))
        if key in seen:
            continue
        seen.add(key)
        cards.append({
            "title": it.get("doc_name") or it.get("source"),
            "source": it.get("source"),
            "scope": it.get("scope"),
            "updated_at": it.get("updated_at"),
            "verified": bool(it.get("verified")),
            "category": it.get("category"),
        })
    return cards


# ---------------- 统一方案访问（真实 plans.json + 旧示例 courses.json） ----------------
def _term_label(school_year, sem):
    """学年+学期 → 日历标签：秋在学当年，春季跨年（2025-2026学年第2学期=2026春）。"""
    if sem == 3:
        return f"{school_year + 1}夏"
    return f"{school_year}秋" if sem == 1 else f"{school_year + 1}春"


def _unify_codes(courses):
    """培养方案原文存在同课程号对应多门课的情况，为图谱节点做唯一化：保留首条原号，其余加 _n 后缀。"""
    seen = {}
    for c in courses:
        code = c["code"]
        if code in seen:
            seen[code] += 1
            c["code"] = f"{code}#{seen[code]}"
        else:
            seen[code] = 1
    return courses


def _unified_plan(major):
    """把两种格式统一为 {major,college,grade,grad_credit,duration,degree,courses[+term_idx]}。"""
    if major in PLANS:
        p = PLANS[major]
        courses = []
        for c in p["courses"]:
            c2 = dict(c)
            c2["term_idx"] = term_key(c)              # 1-based 全局学期序（2025级第1学期=1）
            c2["term_label"] = _term_label(int(c["year"].split("-")[0]), c["sem"])
            courses.append(c2)
        _unify_codes(courses)
        return {"major": major, "college": p.get("college", ""), "grade": p.get("grade", 2025),
                "grad_credit": p["grad_credit"], "duration": p.get("duration", ""),
                "degree": p.get("degree", ""), "section_req": p.get("section_req", {}),
                "source": f"《2025{major}执行计划》", "courses": courses, "real": True}
    if major in COURSES:
        p = COURSES[major]
        courses = []
        for c in p["courses"]:
            c2 = dict(c)
            m = re.search(r"第(\d+)学期", c.get("semester", ""))
            n = int(m.group(1)) if m else 99
            c2["term_idx"] = n
            c2["term_label"] = c.get("semester", "")
            c2["nature"] = c.get("type", "必修")
            c2["section"] = c.get("type", "")
            c2.setdefault("prereq", [])
            courses.append(c2)
        return {"major": major, "college": "示例数据", "grade": 0,
                "grad_credit": p["total_credit_required"], "duration": "4年",
                "degree": "", "section_req": {}, "source": "内置示例培养方案",
                "courses": courses, "real": False}
    return None


# ---------------- 课程图谱 ----------------
def get_major_graph(major: str):
    """返回 ECharts 关系图所需的 nodes/links。"""
    plan = _unified_plan(major)
    if not plan:
        return None
    nodes, links = [], []
    for c in plan["courses"]:
        nodes.append({
            "id": c["code"], "name": c["name"], "credit": c["credit"],
            "semester": c["term_label"], "ctype": c["nature"],
            "section": c.get("section", ""),
            "term": c["term_idx"],
            "symbolSize": 16 + c["credit"] * 2.2,
            "category": 0 if c["nature"] == "必修" else 1,
        })
        for p in c.get("prereq", []):
            links.append({"source": p, "target": c["code"]})
    return {"major": major, "total_required": plan["grad_credit"], "real": plan["real"],
            "source": plan["source"], "nodes": nodes, "links": links}


def all_majors():
    return list(PLANS.keys()) + [m for m in COURSES.keys() if m not in PLANS]


def colleges_meta():
    """注册页二级选项：学院 → 专业（含年级）。"""
    out = []
    by_college = {}
    for m, p in PLANS.items():
        by_college.setdefault(p.get("college", "其他"), []).append(m)
    for college, majors in by_college.items():
        grades = sorted({p.get("grade") for p in PLANS.values() if p.get("college") == college and p.get("grade")})
        out.append({"college": college, "majors": majors, "grades": grades or [2025]})
    out.append({"college": "其他学院", "majors": [m for m in COURSES if m not in PLANS],
                "grades": [2023, 2024, 2025, 2026]})
    return out


def find_course_path(major: str, target_code: str):
    """图遍历：求出达成某门课所需的全部先修链（BFS 上游闭包）。"""
    plan = _unified_plan(major)
    if not plan:
        return None
    cmap = {c["code"]: c for c in plan["courses"]}
    if target_code not in cmap:
        for c in plan["courses"]:
            if target_code in c["name"]:
                target_code = c["code"]
                break
        else:
            return None
    needed, stack = set(), [target_code]
    while stack:
        cur = stack.pop()
        for p in cmap[cur].get("prereq", []):
            if p not in needed and p in cmap:
                needed.add(p)
                stack.append(p)
    chain = [cmap[c] for c in sorted(needed | {target_code}, key=lambda x: cmap[x]["term_idx"])]
    return {"target": cmap[target_code], "prereq_chain": chain,
            "total_credit": sum(c["credit"] for c in chain)}


# ---------------- 规则引擎：选课校验 ----------------
def check_selection(major: str, selected_codes: list, max_credit: float = 25.0):
    """校验：先修课是否缺失、总学分是否超上限。规则引擎实现。"""
    plan = _unified_plan(major)
    problems = []
    if not plan:
        return {"ok": False, "problems": [f"未找到专业《{major}》的培养方案数据"]}
    cmap = {c["code"]: c for c in plan["courses"]}
    sel = [c for c in selected_codes if c in cmap]
    total = sum(cmap[c]["credit"] for c in sel)
    for code in sel:
        for p in cmap[code].get("prereq", []):
            if p not in sel:
                problems.append(f"选《{cmap[code]['name']}》需要先修课《{cmap[p]['name']}》，请确认已通过")
    if total > max_credit:
        problems.append(f"本学期总学分 {total} 超过建议上限 {max_credit}，课业可能过重")
    return {"ok": not problems, "total_credit": round(total, 1),
            "max_credit": max_credit, "problems": problems,
            "courses": [cmap[c]["name"] for c in sel]}


# ---------------- 学业规划：按年级推算进度 + 下学期选课推荐 ----------------
def current_term_index(grade: int) -> int:
    """当前处于该年级培养序列的第几个学期（1-based）。8 月后算秋季学期。"""
    from datetime import date
    today = date.today()
    ay = today.year if today.month >= 8 else today.year - 1
    term_in_year = 1 if today.month >= 8 else 2
    return max(1, (ay - grade) * 2 + term_in_year)


# [AI编写] 函数签名与同步判定为“学分待同步”轮改造：未同步时实际学分返回 None（学分待同步轮）
def plan_overview(major: str, grade: int, snapshot=None):
    """学业规划总览：培养进度、各节要求完成度、下学期推荐课表。

    snapshot 为 None 表示学生尚未启用个性化服务：实际已获学分无从得知，
    done_credit/remaining/pct 与各节 done_required 返回 None，
    由前端与问答链路显示"待同步"，不得用方案排课推算冒充实绩。
    """
    import academic
    plan = _unified_plan(major)
    if not plan or not plan["real"]:
        return None
    cur = current_term_index(grade) if grade else 1
    done_all = [c for c in plan["courses"] if c["term_idx"] < cur]
    synced = snapshot is not None
    if synced:
        state = academic.progress(plan, snapshot)
        done_credit = state["done_credit"]
        section_done = state["sections"]
    else:
        done_credit = None
        section_done = {}
    progress = []
    for sec, req in plan["section_req"].items():
        got = section_done.get(sec, 0) if synced else None
        progress.append({"section": sec, "required": req, "done_required": got,
                         "pct": (min(100, round(got / req * 100)) if req else 100) if synced else None})

    # 下学期推荐：方案排在下一学期的课；必修全列，选修列出该学期可选池
    nxt = cur + 1
    nxt_courses = [c for c in plan["courses"] if c["term_idx"] == nxt]
    # 先修是否满足：已同步时按本人实际已通过课程判断，未同步时只能按方案排课顺序参考
    term_done_codes = set(state["passed"]) if synced else {c["code"] for c in done_all}
    rec = []
    for c in sorted(nxt_courses, key=lambda x: (x["nature"] != "必修", -x["credit"])):
        missing = [advisor_name(plan, p) for p in c.get("prereq", [])
                   if p not in term_done_codes and p not in {x["code"] for x in nxt_courses}]
        rec.append({"code": c["code"], "name": c["name"], "credit": c["credit"],
                    "nature": c["nature"], "section": c["section"],
                    "prereq_missing": missing})
    rec_required = round(sum(x["credit"] for x in rec if x["nature"] == "必修"), 1)
    return {
        "major": major, "college": plan["college"], "grade": grade,
        "grad_credit": plan["grad_credit"], "degree": plan["degree"],
        "duration": plan["duration"], "source": plan["source"],
        "current_term": cur, "total_terms": int(float(plan["duration"].rstrip("年") or 4) * 2),
        "credit_synced": synced,
        "done_credit": done_credit,
        "remaining": round(max(0, plan["grad_credit"] - done_credit), 1) if synced else None,
        "pct": min(100, round(done_credit / plan["grad_credit"] * 100, 1)) if synced else None,
        "progress": progress,
        "next_term_label": _term_label(grade + (nxt - 1) // 2, ((nxt - 1) % 2) + 1),
        "next_courses": rec, "next_required_credit": rec_required,
        "next_all_credit": round(sum(x["credit"] for x in rec), 1),
    }


def advisor_name(plan, code):
    for c in plan["courses"]:
        if c["code"] == code:
            return c["name"]
    return code


# [AI编写] 回答模板按“学分待同步”轮改造：未授权时显示待同步与开启引导（学分待同步轮）
def local_study_answer(ov):
    """无大模型时，直接用真实培养方案数据生成结构化学业规划回答。"""
    lines = [f"📚 依据《{ov['source']}》为你自动规划（{ov['college']} · {ov['major']} · {ov['grade']}级）：", ""]
    lines.append(f"· 毕业要求 {ov['grad_credit']} 学分，学制 {ov['duration']}，授予{ov['degree']}学位")
    if ov.get("credit_synced"):
        lines.append(f"· 当前第 {ov['current_term']} 学期（共 {ov['total_terms']} 学期），已同步实际修读记录：已获 {ov['done_credit']} 分（{ov['pct']}%），剩余 {ov['remaining']} 分")
    else:
        lines.append(f"· 当前第 {ov['current_term']} 学期（共 {ov['total_terms']} 学期），已获学分：待同步"
                     "（尚未开启个性化服务，实际修读学分以你同步的记录为准；可在首页右侧「个性化服务」登录后自动更新）")
    gap = [p for p in ov["progress"] if p["required"] and p["done_required"] is not None
           and p["done_required"] < p["required"] and p["section"].endswith("必修")]
    if gap:
        lines.append("· 必修模块缺口：" + "、".join(f"{p['section']}还差{round(p['required'] - p['done_required'], 1)}分" for p in gap))
    elif not ov.get("credit_synced"):
        lines.append("· 必修模块完成度：待同步后核算")
    nx = ov["next_courses"]
    lines.append(f"· 下学期（{ov['next_term_label']}）方案安排 {len(nx)} 门课，必修合计 {ov['next_required_credit']} 分：")
    for c in nx[:12]:
        warn = ("（⚠先修待确认：" + "、".join(c["prereq_missing"]) + "）") if c["prereq_missing"] else ""
        lines.append(f"   - {c['name']} {c['credit']}分 [{c['nature']}]{warn}")
    if len(nx) > 12:
        lines.append(f"   …等共 {len(nx)} 门，完整清单见「培养方案图谱」页")
    lines.append("")
    lines.append("说明：课程与学分均来自执行计划原文；先修关系由规则引擎按课程依赖推断，正式选课以教务系统校验为准。")
    return "\n".join(lines)


# ---------------- 规则引擎：二课堂核算（依据校《第二课堂成绩评定实施办法》） ----------------
ERKE_RULES = _load("erke_rules.json")
RULE_INDEX = {}          # rule_id -> (category, rule)
for _cat in ERKE_RULES["categories"]:
    for _r in _cat["items"]:
        RULE_INDEX[_r["id"]] = (_cat, _r)


def score_record(rule: dict, rec: dict) -> float:
    """按规则类型计算单条记录得分（封顶在聚合阶段处理）。"""
    kind = rule["kind"]
    if kind == "fixed":
        return rule["score"] * max(1, int(rec.get("times", 1)))
    if kind == "times":
        per = rule.get("per", 0)
        if "role_map" in rule:
            per = rule["role_map"].get(rec.get("role"), 0)
        return per * max(1, int(rec.get("times", 1)))
    if kind == "hours_rate":
        return rule["per"] * float(rec.get("hours", 0))
    if kind == "hours_threshold":
        return rule["score"] if float(rec.get("hours", 0)) >= rule["threshold"] else 0
    if kind == "hours_extra":
        return max(0.0, float(rec.get("hours", 0)) - rule["threshold"]) * rule["per"]
    if kind == "base_minus":
        return max(0, rule["base"] - rule["deduct"] * int(rec.get("param", 0)))
    if kind == "choice":
        return next((o["score"] for o in rule["options"] if o["label"] == rec.get("option")), 0)
    if kind == "level":
        s = rule["levels"].get(rec.get("level"), 0)
        return s / 2 if rec.get("group") else s
    if kind == "matrix":
        if rec.get("major") and rule.get("major"):
            return rule["major"]["score"]
        awards = rule["awards"]
        idx = awards.index(rec["award"]) if rec.get("award") in awards else 0
        lv = rule["levels"].get(rec.get("level"), [0] * len(awards))
        s = lv[idx] if idx < len(lv) else 0
        return s / 2 if rec.get("group") else s
    return 0


def calc_erke_v2(records):
    """三层封顶：单条规则上限 → 基础/拓展小节上限 → 维度满分。"""
    cats = {c["id"]: {"name": c["name"], "full": c["full"], "base_cap": c["base_cap"],
                      "ext_cap": c["ext_cap"], "rules": {}} for c in ERKE_RULES["categories"]}
    for r in records:
        info = RULE_INDEX.get(r["rule_id"])
        if not info:
            continue
        cat, rule = info
        raw = score_record(rule, r.get("detail", {}))
        entry = cats[cat["id"]]["rules"].setdefault(
            rule["id"], {"rule": rule, "raw": 0.0, "records": []})
        entry["raw"] += raw
        entry["records"].append(r)
    total = 0.0
    cat_summary = []
    for cid, c in cats.items():
        sec_sum = {"base": 0.0, "ext": 0.0}
        rules_out = []
        for rid, e in c["rules"].items():
            capped = min(e["raw"], e["rule"]["cap"])
            sec_sum[e["rule"]["sec"]] += capped
            rules_out.append({
                "rule_id": rid, "title": e["rule"]["title"], "article": e["rule"]["article"],
                "sec": e["rule"]["sec"], "raw": round(e["raw"], 1), "score": round(capped, 1),
                "cap": e["rule"]["cap"], "count": len(e["records"]),
            })
        base = min(sec_sum["base"], c["base_cap"])
        ext = min(sec_sum["ext"], c["ext_cap"])
        cat_score = round(max(0, min(base + ext, c["full"])), 1)
        total += cat_score
        cat_summary.append({
            "id": cid, "name": c["name"], "full": c["full"],
            "base": round(base, 1), "ext": round(ext, 1), "score": cat_score,
            "rules": sorted(rules_out, key=lambda x: (x["sec"], x["rule_id"])),
        })
    return {"total": round(total, 1), "total_full": ERKE_RULES["total_full"],
            "categories": cat_summary, "note": ERKE_RULES["note"], "source": ERKE_RULES["source"]}


# ---- 兼容旧接口名（保留但不再使用旧表） ----
def calc_erke(records):  # pragma: no cover - 旧数据格式兼容
    return calc_erke_v2([{"rule_id": r.get("rule_id"), "detail": r} for r in records])


# ---------------- 学期课表查询引擎（按年级+专业精确定位学期，有序输出） ----------------
CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8,
          "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8}
GRADE_NAME = {1: "大一", 2: "大二", 3: "大三", 4: "大四"}


def term_naming(term_idx: int):
    """全局学期序(1-8) → (年级序, 秋/春/夏)；夏为小学期。"""
    if term_idx <= 8:
        return GRADE_NAME.get((term_idx + 1) // 2, f"第{(term_idx + 1) // 2}年"), ("秋" if term_idx % 2 else "春")
    return "小学期", "夏"


def parse_term_query(question: str, cur_term: int):
    """从自然语言定位目标学期：本学期/下学期/下学期+学期名/第N学期/大X上(下)。"""
    q = question
    if any(w in q for w in ("下学期", "下学年", "下一个学期", "下步", "秋季要", "明年春")):
        return cur_term + 1
    if any(w in q for w in ("这学期", "本学期", "当前学期", "这学年")):
        return cur_term
    m = re.search(r"第([一二三四五六七八]|\d{1,2})学期", q)
    if m:
        raw = m.group(1)
        n = int(raw) if raw.isdigit() else CN_NUM[raw]
        return n
    m = re.search(r"(大[一二三四])[上下](?:学期)?", q)
    if m:
        g = {"大一": 1, "大二": 2, "大三": 3, "大四": 4}[m.group(1)]
        return (g - 1) * 2 + (1 if m.group(0)[2] == "上" else 2)
    # 没提学期 → 默认下学期（选课决策通常面向下一学期）
    return cur_term + 1


def term_schedule(major: str, grade: int, question: str = ""):
    """核心：定位学生学期 → 有序调取该学期培养安排（必修/实践/选修池 + 先修与排序检查）。"""
    plan = _unified_plan(major)
    if not plan or not plan["real"]:
        return None
    cur = current_term_index(grade) if grade else 1
    target = parse_term_query(question, cur) if question else cur + 1
    total_terms = int(float(str(plan["duration"]).rstrip("年") or 4) * 2)
    if not (1 <= target <= total_terms):
        return {"error": f"该专业学制 {total_terms} 学期，所问学期超出范围"}
    grade_no, season = term_naming(target)

    courses = plan["courses"]
    cmap = {c["code"]: c for c in courses}
    # 假设按方案正常进度：目标学期之前的课程均已通过
    done_codes = {c["code"] for c in courses if c["term_idx"] < target}
    same_term = {c["code"] for c in courses if c["term_idx"] == target}

    def term_row(c):
        miss = []
        for p in c.get("prereq", []):
            if p not in done_codes:
                pc = cmap.get(p)
                if pc is None:
                    continue
                if p in same_term:
                    miss.append(pc["name"] + "（与本课同学期，注意先后衔接）")
                elif pc["term_idx"] >= target:
                    miss.append(pc["name"] + f"（方案排在{_term_label(pc['year'], pc['sem'])}，晚于本课）")
                else:
                    miss.append(pc["name"] + "（假设尚未通过）")
        return {"code": c["code"], "name": c["name"], "credit": c["credit"],
                "section": c["section"], "nature": c["nature"], "prereq_missing": miss}

    term_courses = [c for c in courses if c["term_idx"] == target]
    required = [term_row(c) for c in term_courses if c["nature"] == "必修"]
    electives = [term_row(c) for c in term_courses if c["nature"] != "必修"]
    by_section = {}
    for c in required:
        by_section.setdefault(c["section"], []).append(c)
    req_credit = round(sum(c["credit"] for c in required), 1)
    # 日历学期标签按学生入学年换算（方案课程序列与年级无关）：第t学期 = 入学年 + (t-1)//2，奇数秋 / 偶数春
    eff_grade = int(grade) if grade else (plan.get("grade") or 2025)
    cal_year = eff_grade + (target // 2 if target % 2 == 0 else (target - 1) // 2)
    term_year_label = f"{cal_year}{'秋' if target % 2 else '春'}"
    return {
        "major": major, "grade": grade, "college": plan["college"], "source": plan["source"],
        "current_term": cur, "target_term": target,
        "target_label": f"{grade_no}{season}（第 {target} 学期）",
        "term_year_label": term_year_label,
        "required_by_section": by_section, "required": required,
        "required_credit": req_credit,
        "electives": electives, "elective_credit": round(sum(c["credit"] for c in electives), 1),
        "remaining_after": round(max(0, plan["grad_credit"] -
                              sum(c["credit"] for c in courses if c["term_idx"] <= target)), 1),
    }


def schedule_text(sc):
    """把学期课表渲染成有序的分块文本（本地演示与 LLM 引用共用）。"""
    src = sc["source"].strip("《》")
    lines = [f"📖 依据《{src}》定位：{sc['college']} · {sc['major']} · {sc['grade']}级",
             f"你问的是 {sc['target_label']}（{sc['term_year_label']}），当前你在第 {sc['current_term']} 学期。", ""]
    if not sc["required"] and not sc["electives"]:
        lines.append("【本学期方案未安排课堂课程】大四下学期通常进入毕业设计(论文)/生产实习/求职阶段，")
        lines.append("     请按学院通知完成毕业环节，学分缺口见下条。")
    else:
        lines.append(f"【一】本学期必修安排（方案固定，共 {len(sc['required'])} 门 {sc['required_credit']} 学分）")
        for sec, cs in sc["required_by_section"].items():
            lines.append(f"  ◆ {sec}")
            for c in cs:
                warn = ""
                if c["prereq_missing"]:
                    warn = " ⚠" + "；".join(c["prereq_missing"])
                lines.append(f"     · {c['name']}（{c['credit']}学分）{warn}")
        if sc["electives"]:
            lines.append(f"【二】本学期开课的选修池（共 {len(sc['electives'])} 门可选，合计 {sc['elective_credit']} 分，按兴趣与学分缺口选择）")
            for c in sc["electives"]:
                lines.append(f"     · {c['name']}（{c['credit']}学分 · {c['section']}）")
        else:
            lines.append("【二】本学期方案未安排选修课（选修请从其他学期池中选择）")
    lines.append(f"【三】按方案进度：修完本学期后距最低毕业学分还剩约 {sc['remaining_after']} 学分")
    return "\n".join(lines)


# ---------------- 目标导向学业规划（保研/考研/出国/就业/转专业） ----------------
# 规则来源说明：课程全部取自学生专业的真实培养方案；打分依据是课程在方案中的
# 模块属性（必修/选修/学分高低/课程类别）与目标所需能力的公开常识映射，属于
# “规划建议”，不改变任何学校硬性要求；正式选课仍以教务系统与学院意见为准。
GOAL_RULES = {
    "保研": {
        "focus": "保研（推免）看的是专业排名+科研潜力：绩点是生命线，核心课必须冲高；尽早进实验室、打竞赛。",
        "boost": [("专业必修", 3, "专业核心课，直接决定专业排名"),
                  ("数学", 2, "数学基础课学分高、影响排名大"),
                  ("机器学习|人工智能|编译|算法|高级|前沿|科研", 2, "高阶课程，体现专业深度，复试/面试加分"),
                  ("实践", 1, "科研训练与项目经历素材")],
        "min_credit": (3.0, 1, "高学分课程对绩点影响更大"),
        "erke": [("m5", "争取德育类荣誉（第十一条）"), ("s5", "学科竞赛获奖（第二十条，集体按半数）"),
                 ("s6", "发表论文/专利等学术成果（第二十一条，记20分）")],
    },
    "考研": {
        "focus": "考研是应试战：数学与英语决定下限，专业课决定上限；把统考/初试相关课程学到高分，同时别挂科影响报考。",
        "boost": [("高等数学|线性代数|概率论", 3, "数学统考科目，务必打牢"),
                  ("英语", 2, "英语统考必考"),
                  ("思想政治|毛泽东|中国近现代|马克思主义|思想道德|形势与政策", 2, "政治统考科目"),
                  ("数据结构|操作系统|计算机组成|计算机网络|编译|数据库|自动控制原理|信号与|电路|模拟电子|数字逻辑|物理化学|化工原理", 3, "初试/复试专业课重点"),
                  ("专业必修", 1, "专业基础")],
        "min_credit": (3.0, 1, "重点科目多为高学分，投入产出比高"),
        "erke": [("m2", "德育活动按第七条计分，别占用备考时间但保持达标"),
                 ("s2", "学术讲座（第十八条）可补充复试专业知识")],
    },
    "出国": {
        "focus": "申请制看硬件：GPA、语言成绩、科研/实习经历三线并进；核心课分数与推荐信最重要。",
        "boost": [("英语", 3, "语言基础课，与雅思/托福同步准备"),
                  ("数学", 2, "海外院校重点看数学与核心课成绩"),
                  ("专业必修", 2, "GPA 主体，分数不能低"),
                  ("机器学习|人工智能|科研|研究|设计", 2, "科研方向经历，用于个人陈述与推荐信"),
                  ("实践", 1, "项目经历素材")],
        "min_credit": (3.0, 1, "高学分核心课对 GPA 影响大"),
        "erke": [("s6", "学术成果（第二十一条）是申请材料硬通货"),
                 ("m5", "荣誉奖项（第十一条）丰富简历")],
    },
    "就业": {
        "focus": "企业招聘看项目与技能：把工程实践类课程做实，攒可展示的作品集；技术栈课程优先。",
        "boost": [(r"Java|Python|C\+\+|数据库|网络|虚拟|云|大数据|算法|软件|嵌入式|单片机|前端|Web|程序设计|编程", 3, "岗位技能直接对口"),
                  ("实践|实习|设计|实训|课程实验", 3, "可写进简历的项目/实习经历"),
                  ("专业必修", 2, "技术底座"),
                  ("管理|经济|营销|会计|沟通|写作", 1, "团队协作与职场素养")],
        "min_credit": (2.0, 1, "学分明示投入度，优先能撑学时的技能课"),
        "erke": [("l2", "志愿服务与劳动实践（第四十条）体现稳定性"),
                 ("s5", "竞赛奖项（第二十条）技术岗加分明显")],
    },
    "暂未确定": {
        "focus": "目标未定时建议先稳住绩点、广泛试错：核心课学好，选修跨两个方向各试一门，大二下前确定赛道。",
        "boost": [("专业必修", 2, "无论走哪条路，核心课分数都重要"),
                  ("数学", 1, "基础课影响后续所有方向")],
        "min_credit": (3.0, 1, "高学分课优先投入"),
        "erke": [("m2", "德育活动保持达标（第七条）"), ("l2", "志愿服务满10小时（第四十条）")],
    },
    "转专业": {
        "focus": "转专业看通道条件：正考 GPA≥3.0（学业优秀类）或竞赛/论文/预修 5 学分 B/78 分以上（兴趣专长类）；"
                 "一至三年级春季学期申报，最多 2 志愿，三年级原则上降级。详见「转专业分析」面板。",
        "boost": [("专业必修", 2, "转出专业成绩要保住 GPA≥3.0 这条线"),
                  ("数学", 1, "转入考核常笔试数学/专业基础")],
        "min_credit": (3.0, 1, "优先保住高学分核心课成绩"),
        "erke": [("s5", "学科竞赛省部级以上奖励是兴趣专长类材料（第二十条）"),
                 ("s6", "论文/专利等成果同样可作证明材料（第二十一条）")],
    },
}

GOAL_ALIAS = {
    "保研": ["保研", "推免", "推荐免试", "保送研究生", "支教保研", "研究生支教团", "支教团",
             "行政保研", "实践锻炼岗位", "直博", "直接读博", "保研通道", "推免资格"],
    "考研": ["考研", "考研究生", "读研", "上岸", "研究生考试", "初试"],
    "出国": ["出国", "留学", "雅思", "托福", "海外读研", "申请国外", "交换"],
    "就业": ["就业", "工作", "找工作", "上班", "进企业", "直接工作", "求职", "大厂"],
    "转专业": ["转专业", "转到", "转去", "换专业", "转出到", "申请转入"],
}


def detect_goal(question: str, profile_goal: str = ""):
    """目标识别：问题文本中的目标词优先，其次用注册时填写的学业目标。"""
    q = question or ""
    for goal, words in GOAL_ALIAS.items():
        if any(w in q for w in words):
            return goal, "来自你的提问"
    pg = (profile_goal or "").strip()
    if pg in GOAL_RULES:
        return pg, "来自注册时填写的学业目标"
    for goal, words in GOAL_ALIAS.items():
        if any(w in pg for w in words):
            return goal, "来自注册时填写的学业目标"
    return "暂未确定", "未识别到明确目标，按通用策略规划"


def goal_plan(major: str, grade: int, goal: str):
    """核心：按目标对培养方案中尚未修读的课程打分，输出有序推荐。"""
    plan = _unified_plan(major)
    if not plan or not plan["real"]:
        return None
    rule = GOAL_RULES.get(goal, GOAL_RULES["暂未确定"])
    cur = current_term_index(grade) if grade else 1
    courses = plan["courses"]
    done = {c["code"] for c in courses if c["term_idx"] <= cur}
    cmap = {c["code"]: c for c in courses}

    scored = []
    for c in courses:
        if c["code"] in done:
            continue
        score, reasons = 0.0, []
        for pat, pts, why in rule["boost"]:
            if re.search(pat, c["name"]) or re.search(pat, c.get("section", "")):
                score += pts
                reasons.append(why)
        mc, mp, mwhy = rule.get("min_credit", (99, 0, ""))
        if c["credit"] >= mc:
            score += mp
            reasons.append(mwhy or f"{c['credit']}学分权重高")
        if c["nature"] != "必修":
            score += 0.5          # 必修必上，选修才是“可选空间”
            reasons.append("选修课，可自主决策")
        prereq_ok = all(p in done or cmap.get(p, {}).get("term_idx", 99) <= c["term_idx"]
                        for p in c.get("prereq", []))
        scored.append({"code": c["code"], "name": c["name"], "credit": c["credit"],
                       "nature": c["nature"], "section": c.get("section", ""),
                       "term": c["term_idx"], "term_label": c["term_label"],
                       "score": round(score, 1), "reasons": list(dict.fromkeys(reasons)),
                       "prereq_ok": prereq_ok})

    scored.sort(key=lambda x: (-x["score"], x["term"], -x["credit"]))
    near = [s for s in scored if s["term"] in (cur + 1, cur + 2)]
    by_term = {}
    for s in near[:10]:
        by_term.setdefault(s["term_label"], []).append(s)
    tips = [{"article": RULE_INDEX[rid][1]["article"], "title": RULE_INDEX[rid][1]["title"],
             "hint": h} for rid, h in rule.get("erke", []) if rid in RULE_INDEX]
    return {"major": major, "grade": grade, "college": plan["college"], "source": plan["source"],
            "goal": goal, "focus": rule["focus"], "current_term": cur,
            "top": scored[:8], "by_term": by_term,
            "pending_count": len(scored), "erke_tips": tips,
            "degree": plan["degree"], "grad_credit": plan["grad_credit"]}


def goal_text(gp, note=""):
    """渲染目标导向规划文本（有序、带理由、可溯源）。"""
    src = gp["source"].strip("《》")
    lines = [f"🎯 目标：{gp['goal']}（{note}）｜{gp['college']} · {gp['major']} · {gp['grade']}级",
             f"策略：{gp['focus']}",
             f"依据：《{src}》，你当前在第 {gp['current_term']} 学期，还有 {gp['pending_count']} 门课程未修。", ""]
    lines.append("【一】未来两学期建议优先选择的课程（按目标匹配度排序）")
    for label, items in gp["by_term"].items():
        lines.append(f"  ◆ {label}")
        for c in items:
            flag = "" if c["prereq_ok"] else "（⚠先修未过）"
            lines.append(f"     · {c['name']}（{c['credit']}学分 · {c['nature']}）匹配度{c['score']} {flag}")
            if c["reasons"]:
                lines.append(f"        理由：{'；'.join(c['reasons'][:3])}")
    lines.append("")
    lines.append("【二】全程优先清单（未来学期中匹配度最高的课程，提前规划先修链）")
    for c in gp["top"][:6]:
        lines.append(f"     · {c['name']}（{c['term_label']} · {c['credit']}学分 · {c['nature']}）匹配度{c['score']}")
    if gp["erke_tips"]:
        lines.append("")
        lines.append("【三】第二课堂配套建议（依据《第二课堂成绩评定实施办法》条款）")
        for t in gp["erke_tips"]:
            lines.append(f"     · {t['article']} {t['hint']}")
    lines.append("")
    lines.append("说明：课程名称/学分/开课学期均取自培养方案原文；匹配度为规则引擎按目标打分，属规划建议，"
                 "正式选课以教务系统校验与学院教师意见为准。")
    return "\n".join(lines)


# ---------------- 兜底回答（无 API Key 时） ----------------
def fallback_answer(question: str, route: str, hits):
    if hits:
        top = hits[0]
        body = f"根据《{top.get('doc_name') or top.get('source')}》，为你找到最相关的答案：\n\n{top['answer']}"
        if len(hits) > 1:
            body += "\n\n相关问题还有：" + "、".join(h["question"] for h in hits[1:])
        return body
    if route == "study":
        return ("（本地演示模式）学习顾问已收到你的问题。请补充你的专业与年级，"
                "我会在培养方案库中为你检索课程路径。配置百炼 API Key 后可获得自然语言个性化解读。")
    return ("（本地演示模式）知识库暂未收录该问题。配置百炼 API Key 后，生活助手即可像豆包/千问一样"
            "回答各类通用问题（当前仅能回答知识库内的校园事务）。"
            "你也可以点击下方「提交问题反馈」，我们会把高频问题收录进知识库。")
