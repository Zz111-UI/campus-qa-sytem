# -*- coding: utf-8 -*-
"""出国留学引擎（信息科学与技术学院）。

数据源：data/studyabroad_rules.json（依据《北化留学》项目册整理）。
能力：
- 三大地区（美洲/欧洲/亚太）→ 国家 → 学校 → 项目（形式/学院/专业/选拔要求/声誉）层级数据
- 搜索：关键词命中地区/国家/学校/项目形式/专业/学院，返回结构化结果
- 文本渲染：供智能问答链路输出可溯源的留学信息
"""
import io
import json
import os

_DATA = None
_PATH = os.path.join(os.path.dirname(__file__), "data", "studyabroad_rules.json")


def _load():
    global _DATA
    if _DATA is None:
        with io.open(_PATH, encoding="utf-8") as f:
            _DATA = json.load(f)
    return _DATA


def region_names():
    return [r["name"] for r in _load()["regions"]]


def _school_row(sch, country, region):
    return {"region": region, "country": country, "name": sch["name"],
            "projects": sch["projects"]}


def all_schools():
    out = []
    for r in _load()["regions"]:
        for c in r["countries"]:
            for s in c["schools"]:
                out.append(_school_row(s, c["country"], r["name"]))
    return out


def search(kw):
    """关键词搜索：命中地区/国家/学校/项目/专业/学院，返回学校列表（含命中原因）。"""
    kw = (kw or "").strip().lower()
    hits = []
    for row in all_schools():
        fields = [row["region"], row["country"], row["name"]]
        for p in row["projects"]:
            fields += [p.get("form", ""), p.get("majors", ""), p.get("colleges", "")]
        blob = " ".join(fields).lower()
        if kw and kw in blob:
            hits.append(row)
    return hits


def overview():
    """点进板块未搜索时：地区列表（收起态），附国家与学校完整信息。"""
    regs = []
    for r in _load()["regions"]:
        regs.append({
            "name": r["name"],
            "countries": [{"country": c["country"],
                           "schools": c["schools"]}
                          for c in r["countries"]],
            "school_count": sum(len(c["schools"]) for c in r["countries"]),
        })
    return regs


# 明确的留学信号词（含这些词几乎可确定是在问海外学习项目）
_STRONG = ("留学", "出国", "海外学习", "交换项目", "学生交换", "联合培养", "双学位",
           "本硕", "公派", "暑期学校", "寒暑期", "海外读研", "申请国外", "境外")
# 地区/国家/学校等可检索实体（懒加载）
_KEYS = None


def _keys():
    """构建可检索实体集合：地区名、国家名、学校全名、去掉国家前缀的学校名。"""
    global _KEYS
    if _KEYS is None:
        ks = set()
        for r in _load()["regions"]:
            ks.add(r["name"])
            for c in r["countries"]:
                ks.add(c["country"])
                for s in c["schools"]:
                    ks.add(s["name"])
                    ks.add(s["name"].replace(c["country"], "").strip())
        _KEYS = [k for k in ks if len(k) >= 2]
    return _KEYS


def detect_query(question):
    """判断是否留学问题并给出检索词：命中实体返回该实体（可被 search 检索）；
    仅泛化留学词返回空串（走地区总览）；完全无关返回 None（交回其他链路）。"""
    q = question or ""
    hits = [k for k in _keys() if k in q]
    strong = [w for w in _STRONG if w in q]
    if not hits and not strong:
        return None
    if hits:
        return max(hits, key=len)     # 取最具体的实体
    return ""                          # 只有泛化词 → 总览


def has_strong_kw(question):
    """是否含明确留学实体或强信号词（用于与考研等链路让位判断）。"""
    q = question or ""
    return any(k in q for k in _keys()) or any(w in q for w in _STRONG)


def analyze_studyabroad(query=""):
    """统一入口：query 为空返回总览；否则返回搜索结果 + 申请流程等背景。"""
    d = _load()
    q = (query or "").strip()
    total_schools = sum(len(c["schools"]) for r in d["regions"] for c in r["countries"])
    total_projects = sum(len(s["projects"]) for r in d["regions"] for c in r["countries"] for s in c["schools"])
    result = {
        "meta": {"title": d["meta"]["title"], "intro": d["meta"]["intro"],
                 "contacts": d["meta"]["contacts"], "disclaimer": d["meta"]["disclaimer"],
                 "school_count": total_schools, "project_count": total_projects,
                 "updated_at": "2026-10"},
        "project_types": d["project_types"],
        "program_modes": d["program_modes"],
        "apply_flow": d["apply_flow"],
        "query": q,
    }
    if q:
        result["mode"] = "search"
        result["results"] = search(q)
    else:
        result["mode"] = "overview"
        result["regions"] = overview()
    return result


def _proj_lines(p):
    lines = [f"  · 项目形式：{p.get('form', '——')}"]
    if p.get("term"):
        lines.append(f"    时长：{p['term']}")
    lines.append(f"    派出学院：{p.get('colleges', '——')}")
    lines.append(f"    申请专业：{p.get('majors', '——')}")
    lines.append(f"    选拔要求：{p.get('req', '以项目公告为准')}")
    lines.append(f"    学校声誉：{p.get('rep', '——')}")
    if p.get("dest"):
        lines.append(f"    学生去向：{p['dest']}")
    return lines


def studyabroad_text(a):
    """渲染为问答文本。"""
    m = a["meta"]
    out = [f"【{m['title']}】", m["intro"], ""]
    if a["mode"] == "search":
        res = a["results"]
        if not res:
            out.append(f"知识库中未收录「{a['query']}」相关的留学项目。")
            out.append("可搜索的地区：美洲（美国、加拿大）、欧洲（英国、爱尔兰、法国、德国、葡萄牙、瑞典）、亚太（新加坡、日本、韩国、马来西亚、澳大利亚、中国香港/澳门）。")
        else:
            out.append(f"搜索「{a['query']}」命中 {len(res)} 所学校：")
            for row in res:
                out.append("")
                out.append(f"◆ {row['region']} · {row['country']} —— {row['name']}")
                for p in row["projects"]:
                    out += _proj_lines(p)
    else:
        out.append("可选留学地区（点开查看该地区全部学校与要求）：")
        for r in a["regions"]:
            cs = "、".join(f"{c['country']}({len(c['schools'])}所)" for c in r["countries"])
            out.append(f"◆ {r['name']}：共 {r['school_count']} 所学校 —— {cs}")
    out += ["", "【申请流程】"]
    for i, s in enumerate(a["apply_flow"], 1):
        out.append(f"{i}. {s}")
    out += ["", "【项目形式说明】"]
    for p in a["program_modes"]:
        out.append(f"◆ {p['form']}：{p['desc']}（申请时间：{p['apply_time']}）")
    out += ["", "【咨询方式】"]
    for k, v in a["meta"]["contacts"].items():
        out.append(f"{k}：{v}")
    out.append("")
    out.append("※ " + m["disclaimer"])
    return "\n".join(out)


if __name__ == "__main__":
    ov = analyze_studyabroad()
    print(studyabroad_text(ov)[:600])
    print("...")
    r = analyze_studyabroad("伯克利")
    print("搜索[伯克利]命中:", [x["name"] for x in r["results"]])
    r2 = analyze_studyabroad("英国")
    print("搜索[英国]命中学校数:", len(r2["results"]))
