# -*- coding: utf-8 -*-
"""就业规划引擎（本科生各年级任务清单）。

数据源：data/career_rules.json（依据学生提供的《工作》文档整理）。
四年（大一探索 / 大二积累 / 大三关键 / 大四收割）每年一行可折叠，一页速查表格。
"""
import io
import json
import os

_DATA = None
_PATH = os.path.join(os.path.dirname(__file__), "data", "career_rules.json")

# 问答里命中就业任务清单的信号词（问年级任务与招聘节点；泛问"就业怎么选课"仍走选课规划）
_KW = ("任务清单", "每个年级", "各年级", "年级该做", "年级该干", "该做什么", "该干什么",
       "一页速查", "秋招", "春招", "暑期实习", "转正", "简历", "签约", "找工作",
       "大一该", "大二该", "大三该", "大四该", "大一应", "大二应", "大三应", "大四应",
       "几年该")


def _load():
    global _DATA
    if _DATA is None:
        with io.open(_PATH, encoding="utf-8") as f:
            _DATA = json.load(f)
    return _DATA


def detect(query):
    """问题含就业任务信号词则命中（返回 True 走本模块，False 交回选课规划链路）。
    但"怎么选课/选什么课"属于选课规划意图，即便带"找工作"也不走任务清单。"""
    q = query or ""
    if any(w in q for w in ("选课", "选什么课", "选哪些课", "该选", "课程推荐", "课表")):
        return False
    return any(w in q for w in _KW)


def analyze_career():
    """返回四年清单与一页速查的全部结构化数据。"""
    return _load()


def _year_body(y):
    """单一年份的正文：清单 or 表格。"""
    if "items" in y:
        rows = "".join(f"<li>☐ {t}</li>" for t in y["items"])
        return f'<p class="cr-label">{y["list_label"]}</p><ul class="cr-list">{rows}</ul>'
    tb = y["table"]
    head = "".join(f"<th>{c}</th>" for c in tb["columns"])
    body = "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in tb["rows"])
    return (f'<p class="cr-label">{y["table_label"]}</p>'
            f'<table class="gp-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>')


def _callout(c):
    if not c:
        return ""
    tone = "warn" if c.get("tone") == "warn" else "info"
    return f'<div class="cr-callout cr-{tone}"><b>{c["label"]}</b>{c["text"]}</div>'


def career_html(a):
    """面板用 HTML：四年可折叠行（默认合上）+ 一页速查表。"""
    years = ""
    for y in a["years"]:
        years += f'''<details class="cr-year">
          <summary><span class="cr-theme">{y["theme"]}</span>
            <b>{y["key"]}</b><span class="cr-tag">{y["tag"]}</span>
            <span class="cr-brief">{y["goal"]}</span></summary>
          <div class="cr-body">{_year_body(y)}{_callout(y.get("callout"))}</div>
        </details>'''
    q = a["quick"]
    head = "".join(f"<th>{c}</th>" for c in q["columns"])
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in q["rows"])
    quick = (f'<div class="ts-block"><h4>⚡ {q["title"]}</h4>'
             f'<table class="gp-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>')
    return f'''<div class="ts-head by-head">💼 {a["meta"]["title"]}<span class="ts-tag ghost">更新至 {a["meta"]["updated_at"]}</span></div>
      <p class="muted">{a["meta"]["intro"]} · {a["meta"]["scope"]}</p>
      <h4 class="sa-h">四个学年 · 点开看每一年该做什么（默认合上）</h4>
      {years}
      {quick}'''


def career_text(a):
    """纯文本渲染（问答链路用）。"""
    L = [f"# {a['meta']['title']}", f"> {a['meta']['intro']}（{a['meta']['scope']}）", ""]
    for y in a["years"]:
        L.append(f"## {y['key']} · {y['tag']}")
        L.append(f"目标：{y['goal']}")
        if "items" in y:
            L += [f"☐ {t}" for t in y["items"]]
        else:
            L.append("| " + " | ".join(y["table"]["columns"]) + " |")
            L += ["| " + " | ".join(r) + " |" for r in y["table"]["rows"]]
        if y.get("callout"):
            L.append(f"【{y['callout']['label']}】{y['callout']['text']}")
        L.append("")
    q = a["quick"]
    L.append(f"## {q['title']}")
    L.append("| " + " | ".join(q["columns"]) + " |")
    L += ["| " + " | ".join(r) + " |" for r in q["rows"]]
    L.append("")
    L.append("※ " + a["meta"]["disclaimer"])
    return "\n".join(L)


if __name__ == "__main__":
    a = analyze_career()
    print(career_text(a)[:500])
