# -*- coding: utf-8 -*-
"""保研四通道分析引擎（信息科学与技术学院）。
数据源：data/baoyan_rules.json（依据校教发〔2019〕23号、团发〔2024〕26号、
2027年推免招生工作办法及信息学院2027推免实施细则整理）。
提供：通道政策分析 analyze_baoyan / 画像自评 self_check / 文本渲染 baoyan_text / 总览 overview。
"""
import json
import os

from config import DATA_DIR

RULES_PATH = os.path.join(DATA_DIR, "baoyan_rules.json")
_rules = None

CHANNELS = ["普通学业推免", "支教保研", "行政保研", "直博推免"]
CHANNEL_ALIAS = {
    "普通学业推免": ["学业推免", "普通推免", "推免生", "保研究竟", "常规推免"],
    "支教保研": ["支教", "研究生支教团", "支教团", "西部计划"],
    "行政保研": ["行政", "辅导员", "实践锻炼", "留校工作", "管理岗"],
    "直博推免": ["直博", "直接读博", "博士", "硕博", "本博"],
    "保研": ["保研", "推免", "免试", "读研"],
}


def load_rules():
    global _rules
    if _rules is None:
        with open(RULES_PATH, encoding="utf-8") as f:
            _rules = json.load(f)
    return _rules


def detect_channel(text: str) -> str:
    """从问句识别目标通道；只提到"保研/推免"返回 '保研'（触发总览）。"""
    t = text or ""
    for ch in CHANNELS:
        if ch in t or any(a in t for a in CHANNEL_ALIAS[ch]):
            return ch
    if any(a in t for a in CHANNEL_ALIAS["保研"]):
        return "保研"
    return ""


def self_check(channel: str, p: dict) -> list:
    """按学生自评画像逐项核对硬性条件，返回 [{item, require, actual, ok, note}]。
    p: {gpa, cet6, rank_pct, cadre, party, volunteer, teacher_cert, research}"""
    rules = load_rules()
    if channel not in rules["channels"]:
        return []
    rows = []
    gpa = p.get("gpa")
    cet6 = p.get("cet6")
    rank = p.get("rank_pct")

    def _num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    g, c, r = _num(gpa), _num(cet6), _num(rank)
    if channel == "普通学业推免":
        rows.append({"item": "前三年正考 GPA", "require": "≥ 3.00",
                     "actual": gpa if g is not None else "未填写",
                     "ok": (None if g is None else g >= 3.0),
                     "note": "实验班/特长生/退役复学有降线条款，见上方特例"})
        rows.append({"item": "英语六级", "require": "≥ 425",
                     "actual": cet6 if c is not None else "未填写",
                     "ok": (None if c is None else c >= 425),
                     "note": "卓越工程师实验班可用四级≥425替代"})
        rows.append({"item": "纪律与学风", "require": "无处分、无作弊记录",
                     "actual": p.get("discipline", "默认满足"),
                     "ok": True, "note": "一票否决项"})
    elif channel == "支教保研":
        rows.append({"item": "推免基本条件", "require": "GPA≥3.00 且六级≥425",
                     "actual": f"GPA {gpa or '—'} / 六级 {cet6 or '—'}",
                     "ok": (None if (g is None or c is None) else (g >= 3.0 and c >= 425)),
                     "note": "不符合当年普通推免条件自动取消参选资格"})
        rows.append({"item": "党员身份", "require": "同等条件优先（非硬性）",
                     "actual": "是" if p.get("party") else "否",
                     "ok": None, "note": "强烈建议尽早递交入党申请"})
        rows.append({"item": "志愿服务经历", "require": "有较强的奉献精神与一定的工作经历",
                     "actual": "有" if p.get("volunteer") else "无/待积累",
                     "ok": (None if not p.get("volunteer") else True),
                     "note": "需志愿服务活动证明（附本人角色与作用）"})
        rows.append({"item": "教师资格证", "require": "持有或已报名教资考试（优先项）",
                     "actual": "有/已报名" if p.get("teacher_cert") else "暂无",
                     "ok": None, "note": "岗前见习须通过教资考试，越早越好"})
        rows.append({"item": "学生干部", "require": "担任主要学生干部（优先项）",
                     "actual": "是" if p.get("cadre") else "否", "ok": None,
                     "note": "组织管理能力是面试重点"})
    elif channel == "行政保研":
        rows.append({"item": "前三年正考 GPA", "require": "≥ 2.80（辅导员岗 ≥ 3.00）",
                     "actual": gpa if g is not None else "未填写",
                     "ok": (None if g is None else g >= 2.8),
                     "note": "瞄准辅导员岗请按 3.00 准备"})
        rows.append({"item": "综合成绩排名", "require": "专业前 30%",
                     "actual": (f"前 {rank}%" if r is not None else "未填写"),
                     "ok": (None if r is None else r <= 30),
                     "note": "综合成绩=奖学金口径，含二课与学生工作加分"})
        rows.append({"item": "英语六级", "require": "≥ 425（原则上）",
                     "actual": cet6 if c is not None else "未填写",
                     "ok": (None if c is None else c >= 425),
                     "note": "特殊情况须学校推免工作领导小组批准"})
        rows.append({"item": "学生工作履历", "require": "主要学生干部经历",
                     "actual": "有" if p.get("cadre") else "无/待积累",
                     "ok": (None if not p.get("cadre") else True),
                     "note": "岗位考核核心材料"})
    elif channel == "直博推免":
        rows.append({"item": "推免资格（前置）", "require": "GPA≥3.00 且六级≥425，取得推免名额",
                     "actual": f"GPA {gpa or '—'} / 六级 {cet6 or '—'}",
                     "ok": (None if (g is None or c is None) else (g >= 3.0 and c >= 425)),
                     "note": "直博是推免资格之上的二次选拔"})
        rows.append({"item": "报考导师", "require": "申请表须经导师亲笔签字",
                     "actual": "已联系" if p.get("advisor_contacted") else "未联系",
                     "ok": (None if not p.get("advisor_contacted") else True),
                     "note": "没有导师签字=审核不合格，第一步就是联系导师"})
        rows.append({"item": "科研经历", "require": "论文/成果/竞赛（优先项）",
                     "actual": "有" if p.get("research") else "无/待积累",
                     "ok": None, "note": "面试重点考察科研潜质与创新精神"})
        rows.append({"item": "教授推荐信", "require": "两名相关学科教授推荐",
                     "actual": p.get("ref_letters", "待准备"),
                     "ok": None, "note": "职称要求副教授以上，导师可协助落实"})
    return rows


def analyze_baoyan(channel: str, profile: dict = None) -> dict:
    """返回指定通道的完整分析 +（可选）画像自评。channel='保研' 时返回四通道总览。"""
    rules = load_rules()
    if channel in ("保研", ""):
        boards = []
        for name in CHANNELS:
            c = rules["channels"][name]
            boards.append({
                "name": name, "essence": c["essence"], "quota": c["quota"],
                "hard_simple": [[h[0], h[1]] for h in c["hard"][:3]],
                "priority_n": len(c["priority"]), "process_n": len(c["process"]),
                "has_materials": bool(c.get("materials")), "risk": c["risk"],
            })
        return {"channel": "保研", "meta": rules["meta"], "common": rules["common"],
                "compare_rows": rules["compare_rows"], "channels": CHANNELS,
                "boards": boards, "year_plan": rules["year_plan"]}
    if channel not in rules["channels"]:
        return {"error": f"未知通道：{channel}（可选：{'、'.join(CHANNELS)}）"}
    ch = rules["channels"][channel]
    out = {"channel": channel, "meta": rules["meta"], "common": rules["common"],
           "essence": ch["essence"], "quota": ch["quota"], "hard": ch["hard"],
           "priority": ch["priority"], "process": ch["process"],
           "risk": ch["risk"], "official_basis": rules["meta"]["sources"]}
    for k in ("checklist", "materials", "benefit"):
        if k in ch:
            out[k] = ch[k]
    if profile and any(v not in (None, "", False) for v in profile.values()):
        out["self_check"] = self_check(channel, profile)
    return out


def baoyan_text(a: dict) -> str:
    """把 analyze_baoyan 结果渲染为纯文本（问答链路/兜底展示用）。"""
    r = load_rules()
    if a.get("channel") == "保研":
        lines = ["# 信息科学与技术学院 · 保研四通道总览", ""]
        lines += ["## 四条通道共用的地基"] + [f"- {p}" for p in r["common"]["points"]]
        lines += ["", "## 通道对比"]
        head = ["维度", "普通学业推免", "支教保研", "行政保研", "直博推免"]
        lines.append(" | ".join(head))
        for row in r["compare_rows"]:
            lines.append(" | ".join(row))
        lines += ["", "## 按学年的准备路线"]
        for yr, items in r["year_plan"].items():
            lines.append(f"- {yr}：" + "；".join(items))
        lines.append("\n（可分别询问某一通道，如“支教保研怎么选上”，获取详细条件与流程）")
        return "\n".join(lines)
    ch = a["channel"]
    lines = [f"# 保研通道 · {ch}", a["essence"], "", "## 名额", a["quota"], "",
             "## 硬性条件"]
    for it, req, note in a["hard"]:
        lines.append(f"- {it}：{req}" + (f"（{note}）" if note else ""))
    lines += ["", "## 优先/加分项"] + [f"- {p}" for p in a["priority"]]
    lines += ["", "## 流程与时间"] + [f"{i+1}. {s}" for i, s in enumerate(a["process"])]
    if "materials" in a:
        lines += ["", "## 报名材料"] + [f"{i+1}. {m}" for i, m in enumerate(a["materials"])]
    if "checklist" in a:
        lines += ["", "## 要做的工作"] + [f"□ {c}" for c in a["checklist"]]
    if "benefit" in a:
        lines += ["", "## 直博待遇"] + [f"- {b}" for b in a["benefit"]]
    lines += ["", f"## ⚠️ 最大风险：{a['risk']}"]
    if a.get("self_check"):
        lines += ["", "## 你的画像自评核对"]
        for sc in a["self_check"]:
            mark = {True: "✅", False: "❌", None: "⚪"}[sc["ok"]]
            lines.append(f"{mark} {sc['item']}（要求 {sc['require']}，你填 {sc['actual']}）"
                         + (f" — {sc['note']}" if sc["note"] else ""))
    lines.append("\n（条件与流程出自校教发〔2019〕23号、团发〔2024〕26号、"
                 "2027年推免招生工作办法及信息学院实施细则；名额每年以最新通知为准）")
    return "\n".join(lines)


if __name__ == "__main__":
    print(baoyan_text(analyze_baoyan("保研"))[:600])
    print("---")
    print(baoyan_text(analyze_baoyan("支教保研", {"gpa": 3.4, "cet6": 451, "party": True,
          "volunteer": True, "teacher_cert": False, "cadre": True}))[:800])
