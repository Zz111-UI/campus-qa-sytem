# -*- coding: utf-8 -*-
import os
# 本文件由团队编写为主；标注 [AI编写] 的段落为开发迭代过程中由 AI（千问工作助理）生成的代码，均已标注。
"""
全局配置。
把你在阿里云百炼控制台申请的 API Key 填到 DASHSCOPE_API_KEY。
没有 Key 也能跑：系统会自动切换为“本地规则兜底回复”，
所有功能（登录/问答框架/图谱/二课）照常演示，只是回答质量下降。
"""

# ===== 大模型（两条通道，任选或都配）=====
# 通道A 本地模型（推荐先启用）：llama.cpp 跑 Qwen3-4B，免费无需Key
#   启动方法见 local-llm\start_server.ps1；启用后 llm_available()=True
USE_LOCAL_LLM = False   # 如需本地模型兜底，启动 llama-server 后置 True
LOCAL_LLM_BASE_URL = "http://127.0.0.1:8080/v1"
LOCAL_LLM_MODEL = "qwen3-4b"
# 通道B 百炼云端（更强，需API Key；留空则不启用）
# [AI编写] 云端部署版：密钥改为环境变量读取，代码不含明文 Key，留空自动走本地规则引擎（部署安全轮）
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")   # 公网部署版：留空自动走本地规则引擎
LLM_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
LLM_CHAT_MODEL = "qwen-plus"    # 对话模型
LLM_EMBED_MODEL = "text-embedding-v3"  # 向量模型（本项目演示用关键词检索，可不配）

# ===== 服务 =====
HOST = "0.0.0.0"   # 监听所有网卡：本机 + 同一 WiFi 下的手机都能访问
PORT = 8000

# ===== 数据文件路径 =====
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "app.db")
EVIDENCE_DIR = os.path.join(DATA_DIR, "evidence")   # 二课佐证图片存储目录

# 佐证图片限制
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024     # 单张最大 8MB
MAX_IMAGES_PER_RECORD = 6             # 每条记录最多 6 张

# 二课堂计分规则已迁移至 data/erke_rules.json
# （依据《北京化工大学本科生第二课堂成绩评定实施办法（试行）》，由 advisor.py 规则引擎加载）
