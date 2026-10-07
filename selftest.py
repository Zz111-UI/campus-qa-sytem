# -*- coding: utf-8 -*-
"""接口自测脚本（不属于交付功能，可随时删除）：python selftest.py"""
import json
import urllib.parse
import urllib.request
import urllib.error

B = "http://127.0.0.1:8000"


def call(path, data=None, token=None, method=None):
    req = urllib.request.Request(
        B + urllib.parse.quote(path, safe="/?=&"),
        method=method or ("POST" if data else "GET"),
        data=json.dumps(data).encode() if data else None,
        headers={"Content-Type": "application/json",
                 **({"X-Session-Token": token} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


print("1 错误密码被拒:", call("/api/login", {"student_id": "2024500001", "password": "bad"})[0] == 401)
s, d = call("/api/login", {"student_id": "2024500001", "password": "123456"})
print("2 登录:", s, d["profile"]["name"], d["profile"]["major"])
t = d["token"]
print("3 未登录访问被拦:", call("/api/profile")[0] == 401)
print("4 学生画像:", call("/api/profile", token=t)[1])
print("5 资讯推送:", call("/api/notice", token=t)[1]["notice"][:30])
s, d = call("/api/chat", {"question": "校园卡丢了怎么办"}, t)
print("6 问答: 状态", s, "路由", d["route"], "来源卡片", len(d["sources"]), "条")
print("   回答:", d["answer"][:60].replace("\n", " "))
s, d = call("/api/graph?major=计算机科学与技术", token=t)
print("7 图谱:", s, len(d["nodes"]), "节点", len(d["links"]), "条先修边")
s, d = call("/api/course-path", {"major": "计算机科学与技术", "course": "机器学习"}, t)
print("8 先修链:", " → ".join(c["name"] for c in d["prereq_chain"]))
s, d = call("/api/check-selection", {"major": "计算机科学与技术", "courses": ["CS2001", "XN3001"]}, t)
print("9 排课校验问题:", d["problems"], "| 总学分", d["total_credit"])
s, d = call("/api/erke", {"activity_name": "科创项目", "activity_type": "科技创业",
                          "join_date": "2026-09-10", "evidence": "计划书"}, t)
print("10 二课录入:", s, d)
s, d = call("/api/erke", token=t)
print("11 二课核算:", d["summary"]["total"], "分", d["summary"]["status"], "未达标:",
      [g["type"] for g in d["summary"]["gaps"]])
print("12 FAQ:", len(call("/api/faq", token=t)[1]["items"]), "条")
print("13 反馈:", call("/api/feedback", {"question": "宿舍报修电话"}, t)[1]["msg"])
s, d = call("/api/chat", {"question": "宿舍热水卡充值在哪"}, t)
print("14 未覆盖问题引导反馈:", d["needs_feedback"])
print("15 首页可访问:", urllib.request.urlopen(B + "/", timeout=10).status == 200)
print("全部通过")
