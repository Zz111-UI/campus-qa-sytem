# -*- coding: utf-8 -*-
"""考研规划引擎（信息科学与技术学院）。
数据源：data/kaoyan_rules.json（依据学生提供的考研规划资料整理）。
六大板块全部上线：自身情况概览 / 考研基本常识 / 具体考试内容 / 时间线及择校选专业 /
录取规则梳理 / 查信息防诈骗。行动清单勾选状态按账号持久化（students.json 的 ky_actions）。
"""
import json
import os

from config import DATA_DIR

RULES_PATH = os.path.join(DATA_DIR, "kaoyan_rules.json")
_rules = None

SECTIONS = ["自身情况概览", "考研基本常识", "具体考试内容",
            "时间线及择校选专业", "录取规则梳理", "查信息防诈骗"]
SECTION_ALIAS = {
    "自身情况概览": ["自身情况", "情况概览", "哪类考生", "我是哪类", "该干什么", "现在该做"],
    "考研基本常识": ["基本常识", "常识", "考研是什么", "考研到底", "什么是考研", "考研和高考", "调剂机会"],
    "具体考试内容": ["考试内容", "考什么", "分值", "科目", "数学一", "数学二", "数学三",
                     "408", "英语一", "英语二", "管综", "政治"],
    "时间线及择校选专业": ["时间线", "择校", "选专业", "院校", "选学校", "报录比", "歧视",
                           "保护一志愿", "压分", "决策顺序", "六个数据"],
    "录取规则梳理": ["录取", "复试", "调剂", "国家线", "分数线", "自划线", "单科线",
                     "总成绩", "加权", "复试权重", "录取办法"],
    "查信息防诈骗": ["防诈骗", "防骗", "诈骗", "骗局", "骗子", "保过班", "内部资料", "原题",
                     "真题", "假", "官网核实", "查询渠道", "哪里查", "权威", "踩坑", "行动清单", "清单"],
}


def load_rules():
    global _rules
    if _rules is None:
        with open(RULES_PATH, encoding="utf-8") as f:
            _rules = json.load(f)
    return _rules


def detect_section(text: str) -> str:
    """从问句识别考研板块；识别不到返回 ''。别名统一小写比较，兼容 A区/408 等。"""
    t = (text or "").lower()
    for sec, words in SECTION_ALIAS.items():
        if any(w.lower() in t for w in words):
            return sec
    return ""


def analyze_kaoyan(section: str) -> dict:
    """返回指定板块的结构化数据；未上线板块返回 pending 标记。"""
    r = load_rules()
    if section in ("考研", "总览", ""):
        return {"section": "总览", "meta": r["meta"], "sections": SECTIONS,
                "todo": r.get("todo_sections", []),
                "overview": r["overview"]}
    if section not in SECTIONS:
        return {"error": f"未知板块：{section}（可选：{'、'.join(SECTIONS)}）"}
    if section in r.get("todo_sections", []):
        return {"section": section, "pending": True, "meta": r["meta"]}
    key = {"自身情况概览": "overview", "考研基本常识": "basics",
           "具体考试内容": "exam", "时间线及择校选专业": "timeline",
           "录取规则梳理": "admission", "查信息防诈骗": "infosec"}[section]
    return {"section": section, "meta": r["meta"], "data": r[key]}


def kaoyan_text(a: dict) -> str:
    """板块数据 → 纯文本（问答链路/兜底展示用）。"""
    r = load_rules()
    sec = a.get("section")
    L = [f"# 考研规划 · {sec}", ""]
    if sec == "总览":
        L += ["> " + a["overview"]["intro"], ""]
        L.append("| " + " | ".join(a["overview"]["columns"]) + " |")
        for row in a["overview"]["rows"]:
            L.append("| " + " | ".join(row) + " |")
        L.append("")
        L.append("六大板块：" + " / ".join(a["sections"]))
        if a.get("todo"):
            L.append("（" + "、".join(a["todo"]) + " 正在整理中，稍后可用）")
        L.append("\n" + a["meta"]["disclaimer"])
        return "\n".join(L)
    if a.get("pending"):
        return (f"# 考研规划 · {sec}\n\n该板块正在按你的资料整理中，暂未上线。\n"
                "目前已开放：自身情况概览、考研基本常识、具体考试内容、时间线及择校选专业。")
    if sec == "自身情况概览":
        d = a["data"]
        L.append("> " + d["intro"] + "\n")
        L.append("| " + " | ".join(d["columns"]) + " |")
        for row in d["rows"]:
            L.append("| " + " | ".join(row) + " |")
        L.append("\n【重要提醒】")
        L += [f"{i}. {t}" for i, t in enumerate(d["reminders"], 1)]
    elif sec == "考研基本常识":
        d = a["data"]
        L.append("## " + d["title"])
        for p in d["paras"]:
            L.append(f"**{p['b']}**{p['t']}")
        L.append("")
        L.append(d["core_label"])
        L.append("> **" + d["core_quote"] + "**")
        L.append("")
        L.append(d["diff_title"])
        for i, x in enumerate(d["diffs"], 1):
            L.append(f"{i}. **{x['b']}**{x['t']}")
    elif sec == "时间线及择校选专业":
        d = a["data"]
        f = d["flow"]
        L.append("## " + f["title"])
        L.append("| " + " | ".join(f["columns"]) + " |")
        for row in f["rows"]:
            L.append("| " + " | ".join(row) + " |")
        ch = d["choice"]
        for lay in ch["layers"]:
            L.append(f"\n## {lay['title']}")
            if lay["type"] == "flow":
                L.append(" → ".join(f"{i+1}. {s['name']}" for i, s in enumerate(lay["steps"])))
                for s in lay["steps"]:
                    if s.get("desc"):
                        L.append(f"- {s['name']}：{s['desc']}")
            elif lay["type"] == "table":
                L.append("| " + " | ".join(lay["columns"]) + " |")
                for row in lay["rows"]:
                    L.append("| " + " | ".join(row) + " |")
            else:
                L += [f"{i}. {x}" for i, x in enumerate(lay["items"], 1)]
                L += [f"· {n}" for n in lay.get("notes", [])]
    elif sec == "录取规则梳理":
        d = a["data"]
        ln = d["lines"]
        L.append("## " + ln["title"])
        L.append("| " + " | ".join(ln["columns"]) + " |")
        for row in ln["rows"]:
            L.append("| " + " | ".join(row) + " |")
        L.append("\n【重要提醒】")
        L += [f"{i}. {t}" for i, t in enumerate(ln["reminders"], 1)]
        sc = d["score"]
        L.append(f"\n## {sc['title']}")
        L.append(f"{sc['formula_label']}**{sc['formula']}**")
        L += [f"- {t}" for t in sc["bullets"]]
        L += [f"> {q}" for q in sc["quotes"]]
    elif sec == "查信息防诈骗":
        d = a["data"]
        L.append("> " + d["purpose"] + "\n")
        inf = d["info"]
        L.append("## " + inf["title"])
        L.append("| " + " | ".join(inf["columns"]) + " |")
        for row in inf["rows"]:
            L.append("| " + " | ".join(row) + " |")
        L.append("\n## " + inf["pitfalls_title"])
        L += [f"{i}. {t}" for i, t in enumerate(inf["pitfalls"], 1)]
        an = d["anti"]
        L.append("\n## " + an["title"])
        L += [f"{i}. {t}" for i, t in enumerate(an["items"], 1)]
        ac = d["action"]
        L.append("\n## " + ac["title"] + "（□ 为待办，做完自己打勾）")
        for st in ac["stages"]:
            L.append(f"\n【{st['name']}】")
            L += [f"□ {t}" for t in st["items"]]
    elif sec == "具体考试内容":
        d = a["data"]
        for p in d["parts"]:
            L.append(f"## {p['title']}")
            if p.get("intro"):
                L.append(p["intro"] + "\n")
            for tb in p["tables"]:
                L.append("| " + " | ".join(tb["columns"]) + " |")
                for row in tb["rows"]:
                    L.append("| " + " | ".join(row) + " |")
                L.append("")
            sub = p.get("sub")
            if sub:
                L.append(f"### {sub['title']}")
                L += [f"{i}. {t}" for i, t in enumerate(sub["items"], 1)]
                L.append("")
            if p.get("note"):
                L.append(f"（{p['note']}）")
    L.append("\n" + a["meta"]["disclaimer"])
    return "\n".join(L)


if __name__ == "__main__":
    print(kaoyan_text(analyze_kaoyan("自身情况概览"))[:400])
    print("----")
    print(kaoyan_text(analyze_kaoyan("具体考试内容"))[:400])
