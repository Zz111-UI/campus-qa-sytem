# -*- coding: utf-8 -*-
"""校验 1~9 章新导入条目能否被自然问法命中，同时回归上次生活部分的用例。"""
import sys
from pathlib import Path


def _find_root(start):
    """从脚本位置向上查找项目根目录（含 advisor.py）。"""
    for d in [start, *start.parents]:
        if (d / "advisor.py").exists():
            return d
    raise SystemExit("未找到项目根目录，请保持压缩包内的目录结构后再运行本脚本")


sys.path.insert(0, str(_find_root(Path(__file__).resolve().parent)))
import advisor  # noqa
import app as _app  # 分诊函数 extract_intent_by_rule 在 app.py

# (期望命中的条目 id, [用户可能的问法...])
CASES_LIFE = [
    ("kb025", ["宿舍几点断电", "公寓几点关门", "晚上几点熄灯"]),
    ("kb026", ["宿舍里哪些电器不能用", "违章电器有哪些"]),
    ("kb031", ["图书馆一次能借几本书", "书能借多久", "怎么续借"]),
    ("kb032", ["书弄丢了怎么赔", "借的书弄坏了怎么办"]),
    ("kb037", ["着火了怎么逃生", "灭火器怎么用"]),
    ("kb043", ["校园里能吸烟吗", "学校能骑车吗"]),
    ("kb046", ["上课时间怎么安排的", "第五节课几点"]),
    ("kb047", ["学校有几个校区", "昌平校区在哪"]),
    ("kb050", ["学校无线网络叫什么", "wifi怎么连"]),
    ("kb051", ["校园卡初始密码是什么", "怎么给校园卡充值"]),
    ("kb002", ["图书馆怎么预约座位"]),
    ("kb004", ["食堂几点开饭"]),
]

CASES_1to9 = [
    # 学校概况
    ("kb052", ["学校校训是什么", "北化是一所什么样的学校"]),
    ("kb053", ["大学生有哪些权利", "学生有什么义务"]),
    # 学籍管理
    ("kb054", ["新生入学要办什么", "怎么注册", "绿色通道是什么"]),
    ("kb055", ["大学要读几年", "能提前毕业吗"]),
    ("kb056", ["每学期要修多少学分", "重修怎么修"]),
    ("kb057", ["怎么休学", "休学后怎么复学"]),
    ("kb058", ["学业警示是什么", "什么时候会留级"]),
    ("kb059", ["什么情况下会被退学"]),
    ("kb060", ["请假怎么请", "事假能请多久"]),
    ("kb061", ["毕业要满足什么条件", "结业和肄业的区别"]),
    # 考试管理
    ("kb062", ["期末成绩占多少", "什么时候有期中考试"]),
    ("kb063", ["缓考怎么申请", "生病考不了试怎么办"]),
    ("kb064", ["补考怎么报名", "哪些课没有补考"]),
    ("kb065", ["什么情况会被取消考试资格"]),
    ("kb066", ["考试要带什么", "迟到还能进考场吗"]),
    ("kb067", ["哪些行为算作弊", "考试违纪包括哪些行为"]),
    ("kb068", ["教室几点开门", "可以在教室占座吗", "怎么借教室"]),
    ("kb069", ["北化在线怎么进", "优慕课怎么用"]),
    ("kb070", ["实验室设备弄坏了怎么赔"]),
    # 成绩与GPA
    ("kb071", ["成绩什么时候能查", "对成绩有异议怎么办"]),
    ("kb072", ["缺考成绩怎么记", "重修成绩怎么记"]),
    ("kb073", ["成绩怎么换算成绩点", "90分是多少绩点"]),
    ("kb074", ["四级能换英语成绩吗", "英语免修条件是什么"]),
    ("kb075", ["GPA是怎么算的", "哪些课不算GPA"]),
    # 创新学分 / 体育
    ("kb076", ["创新创业学分要修多少", "创新学分怎么拿"]),
    ("kb077", ["竞赛能拿多少学分", "大创能拿多少学分"]),
    ("kb080", ["本科生导师制是什么", "SRTP是什么"]),
    ("kb078", ["体测考什么项目", "体测不及格会怎样"]),
    ("kb079", ["体测及格线是多少", "引体向上多少个及格"]),
    # 转专业
    ("kb081", ["转专业需要什么条件", "怎么转专业"]),
    ("kb082", ["什么情况不能转专业", "转专业怎么考核"]),
    # 毕业学位
    ("kb083", ["论文查重多少算通过", "查重率多少能答辩"]),
    ("kb084", ["毕业设计有什么要求", "答辩怎么评分"]),
    ("kb087", ["什么情况拿不到学位证"]),
    ("kb088", ["辅修怎么申请", "辅修要多少钱"]),
    # 推免保研
    ("kb085", ["保研需要什么条件", "推免要六级吗"]),
    ("kb086", ["推免成绩怎么算", "保研了还能考研吗"]),
    # 纪律处分
    ("kb089", ["处分有哪几级", "处分多久能解除"]),
    ("kb090", ["打架会受到什么处分"]),
    ("kb091", ["偷东西会有什么处分", "诈骗同学怎么处分"]),
    ("kb092", ["考试作弊的处分有多重", "替考会开除吗"]),
    ("kb093", ["抄袭论文会怎么处理", "代写论文怎么处理"]),
    ("kb094", ["旷课多少节会被处分"]),
    ("kb095", ["对处分不服怎么办", "处分怎么申诉"]),
    ("kb096", ["宿舍用违章电器什么处分", "夜不归宿会处分吗"]),
    # 资助体系
    ("kb097", ["困难生怎么认定", "家庭经济困难认定流程"]),
    ("kb098", ["国家助学金有多少钱", "助学金怎么发"]),
    ("kb099", ["助学贷款能贷多少", "贷款利息怎么算"]),
    ("kb100", ["勤工助学多少钱一小时", "学费能减免吗"]),
    ("kb101", ["去基层就业学费能补偿吗", "当兵学费补偿"]),
    ("kb102", ["火车票优惠卡怎么用", "学生票要充磁吗"]),
    # 修订条目回归
    ("kb006", ["国家奖学金多少钱", "奖学金可以同时拿吗"]),
    ("kb010", ["考试周要带什么"]),
    ("kb022", ["奔跑在北化有什么要求"]),
]

CASES = CASES_LIFE + CASES_1to9

hit_top1 = 0
total = 0
no_hit = []
wrong = []

for expect_id, queries in CASES:
    for q in queries:
        total += 1
        res = advisor.search_kb(q, top_k=3)
        top = res[0]["id"] if res else None
        if top == expect_id:
            hit_top1 += 1
        else:
            got = ", ".join(f'{r["id"]}({r["question"][:12]})' for r in res) or "无命中"
            (no_hit if not res else wrong).append((q, expect_id, top, got))

print(f"用例总数：{total}     Top1 命中：{hit_top1}     "
      f"命中率：{hit_top1 / total * 100:.1f}%")
print()
if no_hit:
    print(f"【无命中】{len(no_hit)} 条（关键词缺失，必修）：")
    for q, exp, top, got in no_hit:
        print(f"  问「{q}」  期望 {exp}")
    print()
if wrong:
    print(f"【命中错条目】{len(wrong)} 条（多为条目竞争，可接受）：")
    for q, exp, top, got in wrong:
        print(f"  问「{q}」  期望 {exp}  实际 top1={top}")
        print(f"      返回: {got}")
if not no_hit and not wrong:
    print("全部用例 Top1 命中 ✅")

# 游客可答性：被分诊成 study/mixed 且关键词命中不足 2 个的问法，
# 在未登录状态下会被"请先注册/登录"拦下（见 app.py 的 _kb_strong 放行条件）
blocked = []
for expect_id, queries in CASES:
    for q in queries:
        route = _app.extract_intent_by_rule(q)["route"]
        if route not in ("study", "mixed"):
            continue
        top = advisor.search_kb(q, top_k=1)
        if not top:
            blocked.append((q, expect_id, route, 0))
            continue
        n = sum(1 for k in top[0].get("keywords", []) if k in q)
        sim = advisor._similarity(q, top[0])
        # 与 app.py 的 _kb_strong 规则保持一致
        if not (n >= 2 or (n >= 1 and sim >= 0.45)):
            blocked.append((q, expect_id, route, n))

print()
if blocked:
    print(f"【游客模式会被要求登录】{len(blocked)} 条：")
    for q, exp, route, n in blocked:
        print(f"  「{q}」 期望 {exp}  route={route}  关键词命中={n}")
else:
    print("游客可答性检查通过：无被登录提示拦截的问法 ✅")
