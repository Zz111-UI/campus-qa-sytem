# -*- coding: utf-8 -*-
"""目标规划引擎单元验证（临时脚本）。"""
import advisor

print("GOAL_RULES:", list(advisor.GOAL_RULES.keys()))
print("detect 问题优先:", advisor.detect_goal("我想保研，该选哪些课", "考研"))
print("detect 画像兜底:", advisor.detect_goal("推荐我选课", "就业"))
print("detect 未确定:", advisor.detect_goal("我该学什么", ""))

for goal in ("保研", "考研", "出国", "就业", "转专业", "暂未确定"):
    gp = advisor.goal_plan("计算机科学与技术", 2025, goal)
    tops = [c["name"] for c in gp["by_term"].get(gp["by_term"] and sorted(gp["by_term"])[0], [])][:4] if gp["by_term"] else []
    print(f"\n### {goal}: 待选{gp['pending_count']}门 | 近两学期分组{list(gp['by_term'].keys())} | 首组样例{tops}")
    print("   二课建议:", [t["hint"][:22] for t in gp["erke_tips"]])

txt = advisor.goal_text(advisor.goal_plan("计算机科学与技术", 2025, "考研"), "来自你的提问")
print("\n=== 考研规划渲染（节选） ===")
print(txt[:800])
