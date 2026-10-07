# -*- coding: utf-8 -*-
"""目标规划链路测试（临时脚本可删）：本地规则引擎 + 提示词组装。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import planner, advisor

ok = True
def check(label, cond, extra=""):
    global ok; ok = ok and bool(cond)
    print(("✔" if cond else "✘"), label, extra)

# 1. 知识库覆盖全部 7 个真实专业
check("1 KB专业数", len(planner.KB) == 7, str(list(planner.KB.keys())))

# 2. 目标识别
check("2a 保研", advisor.detect_goal("我想保研，帮我规划选课")[0] == "保研")
check("2b 考研", advisor.detect_goal("准备考研怎么安排课程")[0] == "考研")
check("2c 出国", advisor.detect_goal("打算出国留学规划一下")[0] == "出国")
check("2d 画像目标兜底", advisor.detect_goal("帮我做学业规划", "就业")[0] == "就业")

# 3. 提示词含三约束
p = planner.build_prompt("计算机科学与技术", 2025, "保研", "李四·计算机·2025级", 3)
check("3a 提示词学分约束", "毕业要求：162" in p and "≥" in p)
check("3b 提示词课时约束", "280-520" in p)
check("3c 提示词难度约束", "45%" in p)
check("3d 提示词含课程简介课时难度", "简介" in p and "课时" in p and "难度" in p and "操作系统" in p)
check("3e 提示词长度可控", len(p) < 20000, f"len={len(p)}")

# 4. 本地规划满足约束
data = planner.local_goal_plan("计算机科学与技术", 2025, "保研", 3)
check("4a 生成排期", data and data["schedule"], f"{len(data['schedule'])}个学期")
check("4b 总学分达标", data["planned_credit"] >= data["grad_credit"],
      f"规划{data['planned_credit']} ≥ 要求{data['grad_credit']}")
for s in data["schedule"]:
    h, hc = s["hours"], s["hard"]
    n = len(s["courses"])
    lo = 280 if s["term"] <= 6 else 60
    assert lo <= h <= 560, f"T{s['term']} hours {h} 异常"
    if n:
        assert hc <= max(1, int((n + 1) * 0.45)) + 1, f"T{s['term']} 难课超标 {hc}/{n}"
check("4c 每学期课时/难课占比", True, "逐学期断言通过")

# 5. 渲染文本
txt = planner.schedule_text(data)
check("5 渲染结构", txt.startswith("🎯") and "###" in txt and "学时" in txt and "难课" in txt)

# 6. 各目标均可出规划（不同专业抽测）
for major, goal in [("自动化", "考研"), ("人工智能", "就业"), ("电子信息工程", "出国"),
                    ("测控技术与仪器", "保研"), ("自动化（卓越工程师计划）", "暂未确定")]:
    d = planner.local_goal_plan(major, 2025, goal, 3)
    # 允许≤5学分素质类缺口（课程库不含第二课堂认定学分），需有缺口标注
    check(f"6 {major}·{goal}", d and (d["planned_credit"] >= d["grad_credit"]
          or (d["shortfall"] <= 5 and "缺口" in planner.schedule_text(d))),
          f"规划{d['planned_credit']}/要求{d['grad_credit']} 缺口{d['shortfall']}" if d else "")
# 自动化类=分流前大类平台方案，课程未列全 → 应如实报缺口而非硬凑
d = planner.local_goal_plan("自动化类", 2025, "暂未确定", 3)
check("6b 自动化类缺口如实标注", d and d["shortfall"] > 0 and d["shortfall"] == round(d["grad_credit"] - d["planned_credit"], 1),
      f"可规划{d['planned_credit']}/要求{d['grad_credit']} 缺口{d['shortfall']}")
txt2 = planner.schedule_text(d)
check("6c 缺口文案出现", "知识库缺口" in txt2)

print()
print("样例（计算机2025级·保研 前20行）:")
print("\n".join(txt.splitlines()[:20]))
print("\n", "全部通过 ✅" if ok else "存在失败 ❌")
