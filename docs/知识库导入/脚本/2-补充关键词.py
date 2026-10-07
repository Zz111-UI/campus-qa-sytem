# -*- coding: utf-8 -*-
"""第二轮：补充关键词，修复检索漏检。

第一轮验证发现 4 处「无命中」，全部是 keywords 没覆盖到用户的口语说法。
只补 keywords，不动 answer。
"""
import json

from pathlib import Path


def _find_root(start):
    """从脚本位置向上查找项目根目录（含 data/knowledge_base.json）。"""
    for d in [start, *start.parents]:
        if (d / "data" / "knowledge_base.json").exists():
            return d
    raise SystemExit("未找到项目根目录，请保持压缩包内的目录结构后再运行本脚本")


_ROOT = _find_root(Path(__file__).resolve().parent)
KB = str(_ROOT / "data" / "knowledge_base.json")

ADD = {
    # 「书能借多久」无命中：缺"借多久/多久还"
    "kb031": ["借多久", "能借多久", "多久还", "什么时候还", "还书日期", "几本书"],
    # 「借的书弄坏了怎么办」无命中：只有"损坏/污损"，没有口语的"弄坏/弄丢"
    "kb032": ["弄坏", "弄丢", "赔书", "书丢了", "丢了书", "借的书"],
    # 「学校能骑车吗」无命中：缺"骑车/自行车"
    "kb043": ["骑车", "自行车", "电动车", "养宠物", "遛狗", "养狗"],
    # 「第五节课几点」命中错条目：缺"节课"
    "kb046": ["节课", "第几节课", "上课时间", "几点上课", "上课"],
    # 「身份证丢了怎么补办」被学生证条目抢走：补足限定词
    "kb035": ["身份证丢了", "迁户口", "转户口", "户口迁移"],
    # 「图书馆电话」被座位预约抢走：补"部门电话"
    "kb048": ["部门电话", "心理咨询", "联系电话", "办公电话查询"],
    # 「看病怎么报销」与 kb003 竞争：补口语说法
    "kb029": ["看病报销", "医疗报销", "能报多少"],
}


def main():
    with open(KB, encoding="utf-8") as f:
        data = json.load(f)

    by_id = {x["id"]: x for x in data}
    for kid, words in ADD.items():
        if kid not in by_id:
            print(f"  ⚠ 未找到 {kid}")
            continue
        before = len(by_id[kid]["keywords"])
        for w in words:
            if w not in by_id[kid]["keywords"]:
                by_id[kid]["keywords"].append(w)
        after = len(by_id[kid]["keywords"])
        print(f"  {kid}: {before} -> {after} 个关键词")

    with open(KB, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("完成")


if __name__ == "__main__":
    main()
