# -*- coding: utf-8 -*-
"""
转专业分析引擎（依据《北京化工大学本科生转专业实施细则》及当学年教务处通知）
功能：给定 转出专业→转入专业，输出
  1) 必须达到的要求（基本条件 + 三类申请通道 + 限制/禁止情形 + 名额）
  2) 两个培养方案对比（学分/学位/必修课程差异：可认定、需补修、转出后不再需要）
  3) 需要做的工作（流程步骤 + 时间线 + 考核准备）
所有政策条款均标注来源，不含虚构内容。
"""
import json
import os

import advisor
from config import DATA_DIR

RULES = json.load(open(os.path.join(DATA_DIR, "transfer_rules.json"), encoding="utf-8"))

# 非转专业目标的官方硬要求（来源见各条 source 字段）
GOAL_REQUIREMENTS = {
    "保研": {
        "items": [
            {"req": "本科前三年课程正考成绩 GPA ≥ 3.00", "source": "学校推免政策"},
            {"req": "推免总成绩（学业成绩80% + 第二课堂20%）排名专业前 50%", "source": "学校推免政策"},
            {"req": "外语：六级 ≥ 425 分，或四级 ≥ 460 / 托福 ≥ 80 / 雅思 ≥ 6.0"
                   "（小语种过国家四级；英语专业过专四）", "source": "学校推免政策"},
            {"req": "无考试作弊、剽窃学术成果记录，无违法违纪处分", "source": "学校推免政策"},
            {"req": "建议增强竞争力：学科竞赛省部级以上获奖、论文/专利、科研经历（推免中第二课堂占20%）",
             "source": "学校推免政策（总成绩构成）"},
        ],
        "timeline": ["大一大二：稳住前三年正考 GPA≥3.0（这是生命线）",
                     "大二上：首次可报四级 → 尽早过 425，大二下-大三攻六级 425+",
                     "大一大二暑假：进实验室/大创，攒第二课堂与科研素材",
                     "大三上：学科竞赛集中出成果；关注学院推免细则",
                     "大四 9 月：推免报名与拟录取"]}
    ,
    "考研": {
        "items": [
            {"req": "报考普通统取消化无四六级要求；以同等学力报考需四级 ≥ 425", "source": "学校硕士招生章程及官方口径"},
            {"req": "不挂科、正常毕业取得本科学历学位（复试资格审查需提交毕业证书等）", "source": "学校硕士招生章程"},
            {"req": "初试科目：政治、英语、数学、专业课——数学与专业课决定上限", "source": "定性建议（备考常识）"},
            {"req": "复试资格审查提交四六级成绩单复印件（非普通考生硬门槛，但建议考出）", "source": "学校官方口径"}
        ],
        "timeline": ["大一大二：高数/线代/概率与专业核心课打满基础分",
                     "大二起：过四级，有余力冲六级（复试履历加分）",
                     "大三下：确定目标院校专业，进入基础复习",
                     "暑假：强化期；注意不挂科保毕业",
                     "大四 12 月：初试，次年 3-4 月复试"]}
    ,
    "就业": {
        "items": [
            {"req": "按《本科生学籍管理规定》，毕业与学位审核不含四六级条件；但主流企业简历普遍看重四级 425+",
             "source": "学校官方口径 + 定性建议"},
            {"req": "修满培养方案学分、完成毕业设计（论文），如期双证毕业", "source": "培养方案"},
            {"req": "关键窗口：大三暑假实习；技术岗看项目/竞赛/实习经历", "source": "定性建议"}
        ],
        "timeline": ["大一大二：编程语言与核心课打稳，参加 1-2 项竞赛",
                     "大三：技能方向选修 + 项目作品集；大三暑投实习",
                     "大四上 9-11 月：秋招黄金期；秋招不理想继续春招",
                     "毕业前：签三方，完成毕设"]}
    ,
    "出国": {
        "items": [
            {"req": "GPA：申请制核心硬件，全部课程成绩都要稳（尤其专业核心）；建议均分 80+/85+",
             "source": "定性建议（申请常识）"},
            {"req": "语言：托福/雅思尽早考出（理工科常见门槛托福 80~90 / 雅思 6.5，目标院校为准）",
             "source": "定性建议，以申请院校要求为准"},
            {"req": "GRE：部分美国研究生项目要求，以项目官网为准", "source": "定性建议"},
            {"req": "科研经历 + 推荐信：大三起进实验室，争取署名成果", "source": "定性建议"}
        ],
        "timeline": ["大一大二：保持高 GPA，大二过四级后直接准备托福/雅思",
                     "大二暑假-大三：科研/实习双积累",
                     "大三下-暑假：考出语言（+GRE），选校定文书素材",
                     "大四上 9-12 月：递交申请；次年 1-4 月补交材料办签证"]}
    ,
}


def goal_requirements(goal: str):
    return GOAL_REQUIREMENTS.get(goal)


def _norm(name: str) -> str:
    """课程名归一化用于跨方案匹配：去括号内容、空格、大小写与全半角括号。"""
    import re
    n = re.sub(r"[（(].*?[)）]", "", name)
    return n.replace(" ", "").lower()


def analyze_transfer(from_major: str, to_major: str, grade: int):
    """转专业对比分析：政策要求 + 两方案课程差异 + 要做的工作。数据缺失如实说明。"""
    src = advisor._unified_plan(from_major)
    dst = advisor._unified_plan(to_major)
    both = bool(src and dst and src.get("real") and dst.get("real"))
    quota = RULES["quotas"].get(to_major)
    year_now = advisor_current_year()
    entered_grade = int(grade or 0)
    now_grade_no = (year_now - entered_grade) if entered_grade else 0
    eligibility = []
    for r in RULES["not_allowed"]:
        eligibility.append({"text": r, "hit": False})
    if now_grade_no >= 4:
        eligibility[3]["hit"] = True
        eligibility[3]["text"] += f"（你 {entered_grade} 级，按当前为第 {now_grade_no+1} 年）"
    diff = None
    if both:
        s_req = {c["name"]: c for c in src["courses"] if c["nature"] == "必修"}
        d_req = {c["name"]: c for c in dst["courses"] if c["nature"] == "必修"}
        s_norm = {}
        for c in src["courses"]:
            s_norm.setdefault(_norm(c["name"]), c)
        shared, to_make, from_only = [], [], []
        for name, c in d_req.items():
            hit = s_norm.get(_norm(name))
            if hit:
                shared.append({"name": name, "credit": c["credit"],
                               "term_from": hit.get("term_label", ""), "term_to": c["term_label"]})
            else:
                to_make.append({"name": name, "credit": c["credit"], "term": c["term_label"]})
        for name, c in s_req.items():
            dnorms = {_norm(x) for x in d_req}
            if _norm(name) not in dnorms:
                from_only.append({"name": name, "credit": c["credit"]})
        diff = {
            "from_credit_required": src["grad_credit"], "to_credit_required": dst["grad_credit"],
            "from_degree": src.get("degree", ""), "to_degree": dst.get("degree", ""),
            "from_courses": len(src["courses"]), "to_courses": len(dst["courses"]),
            "shared_required": sorted(shared, key=lambda x: -x["credit"]),
            "to_make_required": sorted(to_make, key=lambda x: x["term"]),
            "from_only_required": sorted(from_only, key=lambda x: -x["credit"]),
            "to_make_credit": round(sum(x["credit"] for x in to_make), 1),
            "shared_credit": round(sum(x["credit"] for x in shared), 1),
        }
    return {
        "from_major": from_major, "to_major": to_major, "grade": grade,
        "has_plans": both, "quota": quota,
        "basic_conditions": RULES["basic_conditions"],
        "channels": RULES["channels"], "restrictions": RULES["restrictions"],
        "eligibility": eligibility, "process": RULES["process"],
        "official_basis": RULES["official_basis"], "source": RULES["source"],
        "diff": diff,
        "notes": [
            "三年级学生原则上需降级转入；最多申报 2 个志愿",
            "原专业课程与转入专业课程相同或相近者可申请学分认定/转换，以转入学院通知为准",
            "大类招生未分流学生仅可转本大类之外专业（自动化类、化工与制药类等注意此条）",
        ],
    }


def advisor_current_year():
    import time
    t = time.localtime()
    return t.tm_year if t.tm_mon >= 8 else t.tm_year - 1


def transfer_text(a):
    """转专业分析 → 有序文本（本地模式直接回答用）。"""
    L = [f"🔁 转专业分析：{a['from_major']} → {a['to_major']}",
         f"政策依据：{a['source']}", ""]
    L.append("【一】你必须达到的要求")
    L.append("  基本条件：" + "；".join(a["basic_conditions"]))
    for i, c in enumerate(a["channels"], 1):
        L.append(f"  通道{['①','②','③'][i-1]} {c['name']}：{c['requirement']}（{c['proof']}）")
    if a["quota"] is not None:
        L.append(f"  该院系统计学年《{a['to_major']}》可接收 {a['quota']} 人（以当年通知为准）")
    hits = [e["text"] for e in a["eligibility"] if e["hit"]]
    if hits:
        L.append("  ⚠ 你已命中不予考虑情形：" + "；".join(hits))
    L.append("")
    L.append("【二】两个专业的培养方案对比")
    if a["diff"]:
        d = a["diff"]
        L.append(f"  学分要求：{a['from_major']} {d['from_credit_required']} 分（{d['from_degree']}）"
                 f" vs {a['to_major']} {d['to_credit_required']} 分（{d['to_degree']}）")
        L.append(f"  ✔ 两专业必修同名课程 {len(d['shared_required'])} 门 / {d['shared_credit']} 分——可申请学分认定，免修")
        L.append(f"  ✚ 转入后需补修必修 {len(d['to_make_required'])} 门 / {d['to_make_credit']} 分："
                 + "、".join(f"{x['name']}({x['term']})" for x in d["to_make_required"][:12])
                 + ("…" if len(d["to_make_required"]) > 12 else ""))
        L.append(f"  ➖ 转出后不再需要的原必修 {len(d['from_only_required'])} 门："
                 + "、".join(x["name"] for x in d["from_only_required"][:10])
                 + ("…" if len(d["from_only_required"]) > 10 else ""))
    else:
        L.append("  ⚠ 系统尚未收录两个专业的完整培养方案，无法自动对比课程；可先参考课程库已有专业。")
    L.append("")
    L.append("【三】你需要做的工作（按时间线）")
    for i, s in enumerate(a["process"], 1):
        L.append(f"  {i}. {s}")
    for n in a["notes"]:
        L.append(f"  · 注意：{n}")
    L.append("")
    L.append("【四】考核准备建议（定性）：关注转入学院考核方案（通常含笔试+面试，"
             "热门院考查数学/专业基础）；准备专业认知与学习规划陈述；如走学业优秀类，保持正考 GPA≥3.0 是第一要务。")
    return "\n".join(L)
