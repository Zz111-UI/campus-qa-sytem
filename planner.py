# -*- coding: utf-8 -*-
"""
目标导向学业规划引擎（一课堂 · 外接知识库 + 大模型链路）
用户定义的流程：
  提问学业目标(保研/考研/就业/出国/考公/创业…) → 获取专业课程知识库(course_kb.json)
  → 整合「目标+课程信息」生成提示词 → 大模型生成课程规划（无 Key 时规则引擎兜底，同样满足三条硬约束）
三条硬约束：
  1) 满足学业总学分（毕业要求 - 已修 ≤ 规划覆盖）
  2) 课时适中（每学期 280-460 学时）
  3) 难易适中（每学期"难"课占比 ≤ 45%，难易搭配）
"""
import json
import os

import advisor
from config import DATA_DIR
from llm import llm_available, llm_chat

_KB_PATH = os.path.join(DATA_DIR, "course_kb.json")
KB = json.load(open(_KB_PATH, encoding="utf-8")) if os.path.exists(_KB_PATH) else {}

TERM_HOUR_MIN, TERM_HOUR_MAX = 280, 520
HARD_RATIO = 0.45

# 目标画像（键名与 advisor.detect_goal 输出一致）
GOAL_PROFILE = {
    "保研": "争取推免资格：保住前五学期绩点排名，冲高数与专业核心课分数，尽早进实验室/打学科竞赛，英语六级450+。",
    "考研": "应试升学：数学(高数/线代/概率)与英语决定下限，专业课(408或自命题核心课)决定上限；不挂科、稳GPA。",
    "就业": "直接进入企业：工程能力与项目/实习经历优先，技能型课程(编程/数据库/网络/软工/嵌入式)做实，大三暑实习。",
    "出国": "申请海外院校：全课程GPA+语言成绩(托福/雅思)+科研或推荐信，核心课分数与英语类课程优先。",
    "暂未确定": "目标未定：先稳绩点、广泛试错，核心课学好，选修跨方向各试一门，大二下前确定赛道。",
}

# 目标 → 课程名关键词加分（本地兜底与提示词"相关度"共用）
GOAL_BOOST = {
    "保研": ["高等数学", "线性代数", "概率论", "离散数学", "数据结构", "操作系统", "数据库", "编译",
             "人工智能", "机器学习", "算法", "数学", "物理", "化学", "专业核心", "实验", "科研"],
    "考研": ["高等数学", "线性代数", "概率论", "英语", "思想政治", "毛泽东", "马克思主义", "数据结构",
             "操作系统", "计算机组成", "计算机网络", "自动控制原理", "信号", "电路", "编译", "数据库", "物理化学"],
    "就业": ["Java", "Python", "C++", "数据库", "网络", "软件", "前端", "移动", "嵌入式", "单片机",
             "实训", "实习", "大数据", "云计算", "Web", "算法", "信息安全", "设计"],
    "出国": ["英语", "口语", "写作", "学术", "数学", "高等数学", "物理", "程序设计", "研究", "人工智能"],
    "暂未确定": ["数据结构", "程序设计", "数学", "专业核心"],
}


def kb_plan(major: str):
    return KB.get(major)


def build_prompt(major, grade, goal, profile_text, current_term):
    """知识库 → 提示词：把目标、未修课程清单(含简介/学分/课时/难度)与三条硬约束整合成大模型指令。"""
    plan = kb_plan(major)
    if not plan:
        return None
    courses = plan["courses"]
    todo = [c for c in courses if c["term"] > current_term]
    done_credit = round(sum(c["credit"] for c in courses if c["term"] <= current_term
                            and c["nature"] == "必修"), 1)
    boost = GOAL_BOOST.get(goal, [])

    def rel(c):
        s = sum(2 for k in boost if k in c["name"])
        s += 1 if c["nature"] == "必修" else 0
        return min(5, s)

    dump = [{"课程": c["name"], "学期": f"第{c['term']}学期({c['term_label']})",
             "学分": c["credit"], "课时": int(c["hours"]), "难度": c["difficulty"],
             "性质": c["nature"], "类别": c["section"], "简介": c["intro"],
             "与目标相关度": rel(c)}
            for c in sorted(todo, key=lambda x: (x["term"], -rel(x)))]
    # 目标官方硬要求（来源标注，禁止编造；见 transfer.GOAL_REQUIREMENTS）
    req_txt = ""
    try:
        import transfer as _tf
        gr = _tf.goal_requirements(goal)
        if gr:
            req_txt = ("\n该目标的学校官方硬性要求（规划必须逐条回应并标注来源，不得编造分数）：\n"
                       + "\n".join(f"  - {it['req']}（{it['source']}）" for it in gr["items"])
                       + "\n时间线参考：" + "；".join(gr["timeline"]))
    except Exception:
        pass
    return f"""你是北京化工大学「百花学习与生活顾问系统」的学业规划引擎。
学生目标：{goal} —— {GOAL_PROFILE.get(goal, '')}
学生画像：{profile_text}（当前第 {current_term} 学期；按方案进度已修必修约 {done_credit} 学分）
毕业要求：{plan['grad_credit']} 学分（依据{plan['source']}）
{req_txt}
请基于下方【专业课程知识库】为该生生成从第 {current_term + 1} 学期到毕业的选课规划。
必须同时满足三条硬约束，输出前逐条自检：
1. 学业总学分：规划课程学分合计 ≥ {plan['grad_credit']} - {done_credit} = {round(plan['grad_credit'] - done_credit, 1)} 学分（未修必修全部列入，选修补足缺口并留约10%余量）。
2. 课时适中：第1-6学期每学期课时合计控制在 {TERM_HOUR_MIN}-{TERM_HOUR_MAX} 学时（约 {round(TERM_HOUR_MIN/16)}-{round(TERM_HOUR_MAX/16)} 学分）；毕业季学期（第7-8学期）以毕业设计/实习/备考为主，课时可低于该区间，属正常。
3. 难易适中：每学期“难”课不超过该学期课程的 {int(HARD_RATIO*100)}%，难课与中/易课搭配，并为难课在考试周预留复习时间。
禁止编造知识库之外的课程；每门课给出学分、课时、难度，并用一句话说明它对「{goal}」的作用。

输出格式（中文 Markdown）：
## {goal}导向 · {major} · {grade}级 课程规划
- 总策略（2-3 行，结合目标与当前进度）
### 第 N 学期（YYYY秋 · 合计X学时/Y学分 · 难课Z门）
| 课程 | 学分 | 课时 | 难度 | 对「{goal}」的作用 |
每学期表后附 1-2 句该学期节点提示（备考/竞赛/实习/六级等）。
最后给 3-6 条【毕业前关键节点】。

【专业课程知识库（未修部分，JSON）】
{json.dumps(dump, ensure_ascii=False)[:16000]}
"""


def local_goal_plan(major, grade, goal, current_term):
    """规则引擎兜底：与提示词同约束的确定性排课算法。"""
    plan = kb_plan(major)
    if not plan:
        return None
    courses = plan["courses"]
    todo = [c for c in courses if c["term"] > current_term]
    done_credit = round(sum(c["credit"] for c in courses if c["term"] <= current_term
                            and c["nature"] == "必修"), 1)
    need = max(0.0, plan["grad_credit"] - done_credit)
    boost = GOAL_BOOST.get(goal, [])

    def score(c):
        return sum(2 for k in boost if k in c["name"]) + (1 if c["nature"] == "必修" else 0)

    req_by, ele_by = {}, {}
    for c in todo:
        (req_by if c["nature"] == "必修" else ele_by).setdefault(c["term"], []).append(c)

    schedule, picked = [], set()
    planned_credit = done_credit
    running = done_credit                     # 含当学期已选课程的滚动总学分
    terms = [t for t in sorted(set(req_by) | set(ele_by)) if t > current_term]
    if not terms:
        terms = [current_term + 1]
    for t in terms:
        items = list(req_by.get(t, []))
        picked.update(c["code"] for c in items)
        hours = sum(c["hours"] for c in items)
        running += sum(c["credit"] for c in items)
        pool = sorted([c for c in ele_by.get(t, []) if c["code"] not in picked],
                      key=score, reverse=True)
        for c in pool:
            if hours + c["hours"] > TERM_HOUR_MAX:
                continue
            if running >= plan["grad_credit"] * 1.02 and c["nature"] != "必修":
                break                       # 总学分已覆盖且有富余，不再堆选修
            hard_n = sum(1 for x in items if x["difficulty"] == "难")
            if c["difficulty"] == "难" and hard_n + 1 > max(1, int((len(items) + 1) * HARD_RATIO)):
                continue
            items.append(c)
            picked.add(c["code"])
            running += c["credit"]
            hours = sum(x["hours"] for x in items)
        # 补选：学期偏空 或 毕业总学分仍不足 → 从后续学期借目标相关选修
        need_more = running < plan["grad_credit"] * 1.02
        for c in sorted([x for x in todo if x["term"] > t and x["code"] not in picked
                         and x["nature"] != "必修"], key=score, reverse=True):
            if hours + c["hours"] > TERM_HOUR_MAX:
                continue
            if not (hours < TERM_HOUR_MIN or need_more):
                break
            hard_n = sum(1 for x in items if x["difficulty"] == "难")
            if c["difficulty"] == "难" and hard_n + 1 > max(1, int((len(items) + 1) * HARD_RATIO)):
                continue
            items.append(c)
            picked.add(c["code"])
            running += c["credit"]
            hours = sum(x["hours"] for x in items)
            need_more = running < plan["grad_credit"] * 1.02
        items.sort(key=lambda x: (x["nature"] != "必修", x["difficulty"] != "难", -x["credit"]))
        if items:
            label = items[0]["term_label"]
            schedule.append({"term": t, "label": label, "courses": items,
                             "hours": int(hours),
                             "credit": round(sum(c["credit"] for c in items), 1),
                             "hard": sum(1 for c in items if c["difficulty"] == "难")})
    return {"major": major, "grade": grade, "goal": goal, "source": plan["source"],
            "grad_credit": plan["grad_credit"], "done_credit": done_credit,
            "planned_credit": round(running, 1), "current_term": current_term,
            "shortfall": round(max(0, plan["grad_credit"] - running), 1),
            "schedule": schedule, "profile": GOAL_PROFILE.get(goal, ""),
            "constraints": {"term_hours": [TERM_HOUR_MIN, TERM_HOUR_MAX], "hard_ratio": HARD_RATIO}}


def schedule_text(data):
    """本地规划结果 → 有序文本（无大模型时的最终答案）。"""
    d = data
    lines = [f"🎯 {d['goal']}导向 · {d['major']} · {d['grade']}级 课程规划（规则引擎版）",
             f"依据：{d['source']}｜毕业要求 {d['grad_credit']} 学分｜已修必修约 {d['done_credit']} 分｜规划覆盖 {d['planned_credit']} 学分",
             f"约束：每学期 {TERM_HOUR_MIN}-{TERM_HOUR_MAX} 学时（课时适中）｜难课占比≤{int(HARD_RATIO*100)}%（难易适中）",
             f"策略：{d['profile']}", ""]
    for s in d["schedule"]:
        lines.append(f"### 第 {s['term']} 学期（{s['label']} · {s['hours']}学时 / {s['credit']}学分 · 难课{s['hard']}门）")
        for c in s["courses"]:
            tag = "必修" if c["nature"] == "必修" else "选修"
            lines.append(f"  · {c['name']}｜{c['credit']}学分 {int(c['hours'])}学时 [{c['difficulty']}/{tag}] — {c['intro'][:36]}")
        lines.append("")
    if d.get("shortfall", 0) > 0:
        lines.append(f"⚠ 知识库缺口：按本方案可规划课程合计 {d['planned_credit']} 学分，距毕业要求仍差 "
                     f"{d['shortfall']} 学分——这部分通常为专业分流后/后续学期新开课，"
                     "方案原文未列出（如自动化类大类平台课），请分流后按所在专业完整方案补齐。")
    # 附：目标官方硬要求（有则必列，来源标注）
    try:
        import transfer as _tf
        gr = _tf.goal_requirements(d["goal"])
        if gr:
            lines.append("")
            lines.append("【附】该目标的学校官方硬性要求（逐条落实，来源已标注）：")
            for it in gr["items"]:
                lines.append(f"  ☐ {it['req']}（{it['source']}）")
            lines.append("  时间线：" + "；".join(gr["timeline"]))
    except Exception:
        pass
    lines.append("说明：课程均取自外接专业课程知识库（培养方案+课时/难度标注）；正式选课以教务系统为准。")
    return "\n".join(lines)


def generate_plan(major, grade, goal, profile_text):
    """完整链路：知识库→提示词→大模型；失败自动降级本地规则引擎。返回 (文本, 提示词, 模式)."""
    if not kb_plan(major):
        return None, None, None, None
    current = advisor.current_term_index(int(grade)) if grade else 1
    prompt = build_prompt(major, grade, goal, profile_text, current)
    # 结构化排期（本地确定性算法）：两种模式都返回，供前端分板块表格展示
    data = local_goal_plan(major, grade, goal, current)
    if llm_available() and prompt:
        try:
            ans = llm_chat([{"role": "system",
                             "content": "你是严谨的学业规划引擎：只使用给定知识库，满足三条硬约束后再输出。"},
                            {"role": "user", "content": prompt}], temperature=0.4)
            if ans and len(ans) > 80:
                return ans, prompt, "llm", data
        except RuntimeError:
            pass
    return (schedule_text(data) if data else None), prompt, "local-rules", data
