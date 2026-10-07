# -*- coding: utf-8 -*-
"""大模型调用封装：双通道。
  通道A 本地模型（llama.cpp llama-server，OpenAI 兼容，免费无需 Key）
  通道B 阿里云百炼（OpenAI 兼容，需 API Key）
两通道都不可用时返回失败，由上层降级为规则引擎/本地模板。
"""
import json

import requests

from config import (DASHSCOPE_API_KEY, LLM_BASE_URL, LLM_CHAT_MODEL,
                    LOCAL_LLM_BASE_URL, LOCAL_LLM_MODEL, USE_LOCAL_LLM)

_probe_cache = {"ok": None, "at": 0.0}


def _local_up(max_age: float = 15.0) -> bool:
    """探活本地 llama-server（结果缓存 15 秒，避免每次请求都探测）。"""
    import time as _t
    now = _t.time()
    if _probe_cache["ok"] is not None and now - _probe_cache["at"] < max_age:
        return _probe_cache["ok"]
    ok = False
    try:
        r = requests.get(LOCAL_LLM_BASE_URL.rstrip("/") + "/models", timeout=2)
        ok = r.status_code == 200
    except Exception:
        ok = False
    _probe_cache["ok"], _probe_cache["at"] = ok, now
    return ok


def llm_available() -> bool:
    """任一通道可用即可启用大模型链路。"""
    return (USE_LOCAL_LLM and _local_up()) or bool(DASHSCOPE_API_KEY)


def llm_mode() -> str:
    """当前生效通道：bailian / local / none（云端优先，本地兜底）。"""
    if DASHSCOPE_API_KEY:
        return "bailian"
    if USE_LOCAL_LLM and _local_up():
        return "local"
    return "none"


def _call(base_url: str, key: str, model: str, messages: list, temperature: float, timeout: int,
          extra: dict = None) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    payload = {"model": model, "messages": messages, "temperature": temperature}
    if extra:
        payload.update(extra)
    resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=timeout)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def llm_chat(messages: list, temperature: float = 0.3, timeout: int = 60) -> str:
    """优先百炼云端（快、强），失败或未配 Key 时回退本地模型（免费）。"""
    if DASHSCOPE_API_KEY:
        try:
            return _call(LLM_BASE_URL, DASHSCOPE_API_KEY, LLM_CHAT_MODEL, messages,
                         temperature, timeout)
        except Exception as exc:
            if not (USE_LOCAL_LLM and _local_up()):
                raise RuntimeError(f"大模型调用失败: {exc}") from exc
    if USE_LOCAL_LLM and _local_up():
        try:
            # CPU 推理较慢：本地超时至少 240s；关闭 Qwen3 思考模式直接作答
            return _call(LOCAL_LLM_BASE_URL, "", LOCAL_LLM_MODEL, messages,
                         temperature, max(timeout, 240),
                         extra={"chat_template_kwargs": {"enable_thinking": False},
                                "max_tokens": 900})
        except Exception as exc:
            raise RuntimeError(f"本地大模型调用失败: {exc}") from exc
    raise RuntimeError("未配置可用大模型通道")


def llm_vision(messages: list, timeout: int = 120) -> str:
    """视觉通道（课表截图识别）：阿里云百炼的 qwen-vl 系列，OpenAI 兼容协议、
    图像以 image_url + base64 dataURL 传入。本地 llama.cpp 文本模型不支持图片，故只走云端。"""
    import config as _cfg
    if not DASHSCOPE_API_KEY:
        raise RuntimeError("图片识别需要大模型：请在 config.py 填入 DASHSCOPE_API_KEY（百炼 qwen-vl 系列）")
    model = getattr(_cfg, "LLM_VL_MODEL", "qwen-vl-max")
    return _call(LLM_BASE_URL, DASHSCOPE_API_KEY, model, messages, 0.0, timeout)


def extract_intent_by_rule(question: str) -> dict:
    """兜底模式下的规则分诊：返回 route(study/life/mixed) 与缺失槽位。"""
    q = question
    study_words = ["选课", "选什么课", "选哪些课", "该选", "下学期", "这学期", "本学期", "下学年",
                   "课程", "培养方案", "先修", "学分", "转专业", "转到", "转入", "换专业",
                   "补修", "绩点", "学业", "路径", "保研", "考研", "出国", "留学",
                   "课表", "排课", "必修", "选修", "毕业", "重修",
                   "学期", "什么课", "有哪些课", "上什么", "学什么", "该上"]
    life_words = ["校园卡", "食堂", "图书馆", "快递", "看病", "就医", "报销", "成绩单",
                  "证明", "奖学金", "骗", "考试", "自习", "办事", "挂失"]
    hit_study = any(w in q for w in study_words)
    hit_life = any(w in q for w in life_words)
    if hit_study and hit_life:
        route = "mixed"
    elif hit_study:
        route = "study"
    elif hit_life:
        route = "life"
    else:
        route = "unknown"
    missing = []
    if route in ("study", "mixed") and not any(str(y) in q for y in (2022, 2023, 2024, 2025, 2026)):
        missing.append("年级")
    return {"route": route, "missing": missing}
