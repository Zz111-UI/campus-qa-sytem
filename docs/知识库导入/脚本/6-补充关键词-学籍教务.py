# -*- coding: utf-8 -*-
"""第二轮：补关键词，修复 1~9 章条目的漏检/竞争。

检索打分 = 关键词子串命中数 × 2 + 整句相似度，所以补对了口头说法就能命中。
只补 keywords，不动 answer / question。
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
    # 「学费能减免吗」完全无命中：只有"学费减免"，问句中间夹了"能"
    "kb100": ["学费", "减免学费", "能减免吗", "减免"],
    # 「毕业要满足什么条件」被体测条目抢走：缺宽口径的"毕业"
    "kb061": ["毕业", "毕业标准", "满足什么条件"],
    # 「期末成绩占多少」被"成绩什么时候能查"抢走
    "kb062": ["期末成绩", "成绩占", "期末占", "占比"],
    # 「什么情况会被取消考试资格」缺完整说法
    "kb065": ["取消考试资格", "考试资格"],
    # 「宿舍用违章电器什么处分」和"哪些电器不能用"打平，补足处分向说法
    "kb096": ["什么处分"],
    # 「怎么续借」被图书馆网址条目抢走（上次遗留的竞争）
    "kb031": ["怎么续借", "能续借吗", "续借几次"],
    # 「转专业需要什么条件」原来只有"转专业"1 个命中，达不到"放行知识库"的阈值
    "kb081": ["转专业需要", "转专业要什么", "转专业的条件", "转专业怎么弄", "怎么转专业"],
    # 「转专业怎么考核」同上，需要第 2 个命中才能放行
    "kb082": ["怎么考核", "考核什么", "转专业怎么考", "笔试面试考什么"],
    # 以下几组问法只有 1 个关键词命中，游客模式下会被登录提示拦下（见 5-验证脚本的游客可答性检查）
    "kb055": ["能提前毕业", "能不能提前毕业"],
    "kb056": ["重修怎么", "重修要"],
    "kb073": ["是多少绩点", "多少分是多少绩点"],
    "kb076": ["学分怎么拿", "学分要修多少", "创新创业学分"],
    "kb086": ["还能考研吗", "保研还能考研"],
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
