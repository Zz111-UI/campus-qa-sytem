# -*- coding: utf-8 -*-
# 本文件由团队编写为主；标注 [AI编写] 的段落为开发迭代过程中由 AI（千问工作助理）生成的代码，均已标注。
"""
百花学习与生活顾问系统 · FastAPI 主服务
PyCharm 直接运行本文件即可（右键 app.py → Run 'app'）。
浏览器打开 http://127.0.0.1:8000
"""
import hashlib
import io
import json
import os
import re
import secrets
import time
import uuid
import zipfile

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# [AI编写] 挂载个性化服务模块的导入（合并轮）
import security
import education
import demo_data
import advisor
import planner
from config import (ALLOWED_IMAGE_EXT, BASE_DIR, DATA_DIR, EVIDENCE_DIR,
                    MAX_IMAGES_PER_RECORD, MAX_IMAGE_BYTES)
from database import get_conn, init_db
from llm import extract_intent_by_rule, llm_available, llm_chat, llm_mode, llm_vision

app = FastAPI(title="百花学习与生活顾问系统")
# [AI编写] 注册个性化服务路由（合并轮）
app.include_router(education.router)
app.include_router(demo_data.router)


# [AI编写] 读取学生已同步的修读快照；未启用个性化服务返回 None，学分进入待同步（学分待同步轮）
def _personal_snapshot(request: Request, student: dict):
    """读取学生本人已同步的修读记录快照；未启用个性化服务或无数据返回 None（学分待同步）。

    与 education.load_snapshot 同一判定口径：演示账号必须已通过
    /api/demo/login 激活（demo_access 表命中），否则视为未同步。
    """
    try:
        sid = student.get("student_id", "")
        if not sid or student.get("guest"):
            return None
        demo_on = False
        if demo_data.is_user(sid):
            raw = request.headers.get("X-Session-Token", "")
            demo_on = bool(raw) and demo_data.active(raw, sid)
        return education.load_snapshot(sid, demo_enabled=demo_on)
    except Exception:
        return None


# [AI编写] 会话桥接函数：把本站登录令牌镜像到个性化安全层，实现一套登录贯通（合并轮）
def _mirror_session(token: str, sid: str, profile: dict):
    """把本站登录令牌镜像进个性化服务的会话表，令一套 token 贯通两套体系。"""
    try:
        import hashlib as _h
        sec_db = get_conn()
        with sec_db as conn:
            conn.execute(
                "INSERT INTO accounts VALUES(?,?,?,?) ON CONFLICT(student_id) "
                "DO UPDATE SET phone=excluded.phone, profile=excluded.profile",
                (sid, str(profile.get("phone", "") or sid),
                 json.dumps(profile, ensure_ascii=False), ""))
            conn.execute("INSERT OR REPLACE INTO sessions VALUES(?,?,?)",
                         (_h.sha256(token.encode()).hexdigest(), sid, time.time() + SESSION_TTL))
        sec_db.close()
    except Exception:
        pass


# [AI编写] 个性化服务与演示库启动初始化（合并轮）
@app.on_event("startup")
def _init_personal():
    security.ensure_accounts()
    demo_data.initialize()

# ---------------- 登录态管理（内存 session，演示够用） ----------------
_students_cache = None
_sessions = {}            # token -> {student_id, expires}
SESSION_TTL = 12 * 3600   # 12 小时

SYSTEM_PROMPT = """你是北京化工大学「百花学习与生活顾问系统」的双顾问助手。
硬规则（信息可信机制）：
1. 只允许依据我提供的【知识库检索结果】和【培养方案数据】回答学校事实，严禁编造地点、时间、流程、学分。
2. 回答末尾不要自己罗列来源（系统会单独生成来源卡片）。
3. 若检索结果与问题无关，直接说知识库暂未覆盖，建议提交问题反馈。
4. 问题缺少专业、年级等关键条件时，先反问补充，不要硬答。
5. 用中文、口语化、分点简洁回答。"""

GENERIC_SYSTEM_PROMPT = """你是北京化工大学「百花学习与生活顾问系统」的生活助手小百，
像豆包/千问那样能回答用户的各种问题（生活常识、学习技巧、心理疏导、数码、美食、运动、闲聊…）。
规则：
1. 可以用你的通用知识自由回答；与大学生生活相关时优先贴近校园场景给建议。
2. 严禁编造北京化工大学的具体事实（办事地点/电话/时间/流程/政策分数）。用户若问到这类学校具体信息，
   而你没有可靠依据时，直说"该问题以学校官方发布为准"，并建议用系统内知识库问答或提交问题反馈核实。
3. 回答口语化、分点、控制篇幅（300 字以内为宜）；结尾不需要声明来源（系统会标注 AI 建议）。
4. 涉及医疗、法律、心理危机等严肃话题：给一般性信息并建议咨询专业人士；用户若流露伤害自己的念头，
   先关心情绪，建议联系信任的人或拨打心理援助热线（如北京 010-82951332 / 全国 400-161-9995）。"""

# 生活问答会话历史（按前端 chat_id 记忆最近几轮，实现连续对话）
_chat_history = {}          # chat_id -> [{role, content}]
CHAT_HIST_MAX = 8


def load_students():
    global _students_cache
    if _students_cache is None:
        with open(os.path.join(DATA_DIR, "students.json"), encoding="utf-8") as f:
            _students_cache = json.load(f)
    return _students_cache


def _hash(pwd: str) -> str:
    return hashlib.sha256(("baihua$" + pwd).encode()).hexdigest()


def current_student(request: Request):
    """从请求头 X-Session-Token 解析登录态，所有需登录接口共用。"""
    token = request.headers.get("X-Session-Token", "")
    sess = _sessions.get(token)
    if not sess or sess["expires"] < time.time():
        _sessions.pop(token, None)
        raise HTTPException(status_code=401, detail="未登录或登录已过期，请重新登录")
    for s in load_students():
        if s["student_id"] == sess["student_id"]:
            return s
    mirrored = security.session_student(token)   # 回退：个性化服务镜像会话
    if mirrored:
        return mirrored
    raise HTTPException(status_code=401, detail="账号不存在")


GUEST = {"student_id": "", "name": "游客", "major": "", "grade": 0,
         "campus": "", "goal": "", "preference": "", "guest": True}


def optional_student(request: Request):
    """游客可用接口：已登录返回画像，未登录返回游客画像（不报错）。"""
    token = request.headers.get("X-Session-Token", "")
    sess = _sessions.get(token)
    if sess and sess["expires"] >= time.time():
        for s in load_students():
            if s["student_id"] == sess["student_id"]:
                return {k: v for k, v in s.items() if k != "password"}
        mirrored = security.session_student(token)
        if mirrored:
            return security.public_profile(mirrored)
    return dict(GUEST)


# ---------------- 学生登录（手机号 + 密码；演示账号见 data/students.json） ----------------
class LoginBody(BaseModel):
    phone: str
    password: str


@app.post("/api/login")
def login(body: LoginBody):
    student = next((s for s in load_students() if s.get("phone", "") == body.phone.strip()), None)
    ok_pwd = student is not None and _hash(body.password) == _hash(student["password"])
    if student and not ok_pwd:
        raise HTTPException(status_code=401, detail="手机号或密码错误")  # 不区分错误原因，避免账号枚举
    if not student:
        # 回退：个性化服务的演示账号（accounts 表，PBKDF2 摘要校验）
        student = next((a for a in security.load_accounts()
                        if a.get("phone", "") == body.phone.strip()), None)
        ok_pwd = student is not None and student.get("password_hash") and \
            security.verify_password(body.password, student["password_hash"])
        if not ok_pwd:
            raise HTTPException(status_code=401, detail="手机号或密码错误")
    token = secrets.token_urlsafe(24)
    _sessions[token] = {"student_id": student["student_id"], "expires": time.time() + SESSION_TTL}
    profile = {k: v for k, v in student.items() if k not in ("password", "password_hash")}
    # [AI编写] 登录成功后调用会话桥接（合并轮）
    _mirror_session(token, student["student_id"], profile)
    return {"token": token, "profile": profile}


# ---------------- 忘记密码：手机验证码重置 ----------------
# 说明：演示环境没有短信网关，验证码直接在响应中返回并显示给用户；
#       生产部署时应替换为真实短信服务（如阿里云短信），并且不外发验证码。
_reset_codes = {}               # phone -> {code, expires}
GOAL_OPTIONS = ["保研", "考研", "出国", "就业/企业", "暂未确定"]


@app.post("/api/forgot/send")
def forgot_send(body: dict):
    phone = str(body.get("phone", "")).strip()
    student = next((s for s in load_students() if s.get("phone", "") == phone), None)
    if not student:
        raise HTTPException(status_code=404, detail="该手机号未注册")
    now = time.time()
    last = _reset_codes.get(phone)
    if last and last.get("sent_at", 0) > now - 60:
        raise HTTPException(status_code=429, detail="验证码发送过于频繁，请 60 秒后再试")
    code = f"{secrets.randbelow(900000) + 100000}"
    _reset_codes[phone] = {"code": code, "expires": now + 300, "sent_at": now}
    return {"ok": True, "demo_code": code,
            "msg": "演示模式：验证码直接显示（真实环境将发送到手机，5分钟内有效）"}


@app.post("/api/forgot/reset")
def forgot_reset(body: dict):
    phone = str(body.get("phone", "")).strip()
    code = str(body.get("code", "")).strip()
    new_pwd = str(body.get("new_password", ""))
    rec = _reset_codes.get(phone)
    if not rec or rec["expires"] < time.time():
        raise HTTPException(status_code=400, detail="验证码已过期，请重新获取")
    if code != rec["code"]:
        raise HTTPException(status_code=400, detail="验证码错误")
    if len(new_pwd) < 6:
        raise HTTPException(status_code=400, detail="新密码至少 6 位")
    students = load_students()
    student = next((s for s in students if s.get("phone", "") == phone), None)
    if not student:
        raise HTTPException(status_code=404, detail="账号不存在")
    student["password"] = new_pwd
    path = os.path.join(DATA_DIR, "students.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(students, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    global _students_cache
    _students_cache = None
    _reset_codes.pop(phone, None)
    return {"ok": True, "msg": "密码已重置，请用新密码登录"}


# ---------------- 学生自助注册（写入 students.json 持久保存） ----------------
COLLEGES_ALL = advisor.load_colleges()


class RegisterBody(BaseModel):
    student_id: str
    name: str
    phone: str
    password: str
    confirm: str = ""
    college: str = ""
    major: str
    grade: int
    campus: str = ""
    goal: str = ""
    preference: str = ""


@app.get("/api/register/meta")
def register_meta():
    """注册页选项：全校学院→专业一览（公开接口，无需登录）；年级由用户手动输入，仅给建议。"""
    year = time.localtime().tm_year
    colleges = COLLEGES_ALL
    # 标注哪些专业已有真实培养方案（选课规划可用）
    have_plan = set(advisor.all_majors())
    for c in colleges:
        c["planned"] = [m for m in c["majors"] if m in have_plan]
    return {"colleges": colleges, "source": "北京化工大学本科专业设置情况一览表",
            "grade_suggest": year, "grade_range": [year - 4, year + 1],
            "campuses": ["东校区", "西校区", "昌平校区"],
            "goals": GOAL_OPTIONS}


@app.post("/api/register")
def register(body: RegisterBody):
    sid = body.student_id.strip()
    if not sid.isdigit() or not (6 <= len(sid) <= 12):
        raise HTTPException(status_code=400, detail="学号须为 6-12 位数字")
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="姓名不能为空")
    phone = body.phone.strip()
    if not re.fullmatch(r"1[3-9]\d{9}", phone):
        raise HTTPException(status_code=400, detail="请填写正确的 11 位手机号")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")
    if body.confirm and body.confirm != body.password:
        raise HTTPException(status_code=400, detail="两次输入的密码不一致")
    if not body.college.strip():
        raise HTTPException(status_code=400, detail="请选择学院")
    if not body.major.strip():
        raise HTTPException(status_code=400, detail="请选择专业")
    year = time.localtime().tm_year
    if not (year - 6 <= body.grade <= year + 1):
        raise HTTPException(status_code=400, detail="入学年级不合理")
    if body.campus.strip() not in ("东校区", "西校区", "昌平校区"):
        raise HTTPException(status_code=400, detail="请选择校区")
    if body.goal.strip() not in GOAL_OPTIONS:
        raise HTTPException(status_code=400, detail="请选择学业目标")
    students = load_students()
    if any(s["student_id"] == sid for s in students):
        raise HTTPException(status_code=400, detail="该学号已注册，请直接登录")
    if any(s.get("phone") == phone for s in students):
        raise HTTPException(status_code=400, detail="该手机号已注册，请直接登录或用「忘记密码」找回")
    college = body.college.strip()
    new_student = {
        "student_id": sid,
        "phone": phone,
        "password": body.password,
        "name": body.name.strip(),
        "college": college,
        "major": body.major.strip(),
        "grade": body.grade,
        "campus": body.campus.strip(),
        "goal": body.goal.strip(),
        "preference": body.preference.strip(),
    }
    students.append(new_student)
    # 先写临时文件再替换，避免写一半损坏账号库；重启后数据仍在
    path = os.path.join(DATA_DIR, "students.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(students, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    global _students_cache
    _students_cache = None  # 使内存缓存失效，下次从文件重新加载
    token = secrets.token_urlsafe(24)
    _sessions[token] = {"student_id": sid, "expires": time.time() + SESSION_TTL}
    profile = {k: v for k, v in new_student.items() if k != "password"}
    return {"token": token, "profile": profile}


@app.post("/api/logout")
def logout(request: Request):
    _sessions.pop(request.headers.get("X-Session-Token", ""), None)
    return {"ok": True}


@app.get("/api/profile")
def profile(request: Request):
    student = current_student(request)
    return {k: v for k, v in student.items() if k != "password"}


class ProfileUpdateBody(BaseModel):
    name: str = ""
    phone: str = ""
    college: str = ""
    major: str = ""
    grade: int = 0
    campus: str = ""
    goal: str = ""
    preference: str = ""


@app.post("/api/profile/update")
def profile_update(body: ProfileUpdateBody, request: Request):
    """修改注册信息（填错了可纠正）：校验规则与注册一致；学号作为账号身份不可改。"""
    student = current_student(request)
    sid = student["student_id"]
    name = body.name.strip() or student.get("name", "")
    if not name:
        raise HTTPException(status_code=400, detail="姓名不能为空")
    phone = body.phone.strip() or student.get("phone", "")
    if not re.fullmatch(r"1[3-9]\d{9}", phone):
        raise HTTPException(status_code=400, detail="请填写正确的 11 位手机号")
    college = body.college.strip() or student.get("college", "")
    major = body.major.strip() or student.get("major", "")
    grade = int(body.grade or student.get("grade") or 0)
    campus = body.campus.strip() or student.get("campus", "")
    goal = body.goal.strip() or student.get("goal", "")
    year = time.localtime().tm_year
    colleges = {c["college"]: c["majors"] for c in advisor.load_colleges()}
    if college not in colleges:
        raise HTTPException(status_code=400, detail="请选择有效学院")
    if major not in colleges[college]:
        raise HTTPException(status_code=400, detail=f"《{major}》不属于《{college}》，请重新选择")
    if not (year - 6 <= grade <= year + 1):
        raise HTTPException(status_code=400, detail="入学年级不合理")
    if campus not in ("东校区", "西校区", "昌平校区"):
        raise HTTPException(status_code=400, detail="请选择校区")
    if goal not in GOAL_OPTIONS:
        raise HTTPException(status_code=400, detail="请选择学业目标")
    students = load_students()
    if any(s.get("phone") == phone and s["student_id"] != sid for s in students):
        raise HTTPException(status_code=400, detail="该手机号已被其他账号使用")
    updated = None
    for s in students:
        if s["student_id"] == sid:
            s.update({"name": name, "phone": phone, "college": college, "major": major,
                      "grade": grade, "campus": campus, "goal": goal,
                      "preference": body.preference.strip()})
            updated = {k: v for k, v in s.items() if k != "password"}
            break
    if updated is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    path = os.path.join(DATA_DIR, "students.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(students, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    global _students_cache
    _students_cache = None      # 画像即时生效：学业规划/图谱/课表都按新专业年级计算
    return {"ok": True, "profile": updated,
            "msg": "资料已更新，学业规划与选课推荐将按新的专业/年级/目标即时生效"}


# ---------------- 顾问对话（一个入口 → 双顾问分诊） ----------------
class ChatBody(BaseModel):
    question: str
    chat_id: str = ""


@app.post("/api/chat")
def chat(body: ChatBody, request: Request):
    student = optional_student(request)
    guest = bool(student.get("guest"))
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    # 1) 分诊：有 Key 用大模型判断，无 Key 用关键词规则
    route = "other"
    if llm_available():
        try:
            raw = llm_chat([
                {"role": "system", "content":
                    "判断这个学生问题属于哪类，只输出一个词：study(选课/培养方案/先修/转专业/学业规划)、"
                    "life(校园服务/办事/场所/生活)、mixed(两者都有)、other(都不属于)。不要解释。"},
                {"role": "user", "content": question}], temperature=0.0) or ""
            route = next((w for w in ("mixed", "study", "life") if w in raw.lower()), "other")
        except RuntimeError:
            route = extract_intent_by_rule(question)["route"]
    else:
        route = extract_intent_by_rule(question)["route"]

    # 1.5) 保研政策问答：命中具体通道或政策类提问 → 直接出政策解读（游客亦可查）
    import baoyan as _by
    # 1.2) 系统入口/网址类问题：知识库能强命中时按“生活服务”回答，
    #      否则“课表、选课”等词会被分诊成学业规划，反而答不出网址
    _kb_top = advisor.search_kb(question)
    if _kb_top and route in ("study", "mixed"):
        _hit_n = sum(1 for k in _kb_top[0].get("keywords", []) if k in question)
        if _hit_n >= 2 and any(w in question for w in
                               ("网址", "网站", "入口", "系统", "平台", "登录", "地址", "在哪", "是什么")):
            route = "life"
    _by_ch = _by.detect_channel(question)
    _policy_kw = ("政策", "条件", "要求", "名额", "流程", "材料", "申请", "资格",
                  "通道", "选拔", "怎么报", "能保研吗", "保研要", "支教", "直博",
                  "辅导员", "实践锻炼", "GPA", "绩点要", "六级要")
    _course_kw = ("选课", "选哪些课", "选什么课", "课程", "课表", "规划", "推荐")
    if _by_ch and (_by_ch != "保研"
                   or any(k in question for k in _policy_kw)
                   or not any(w in question for w in _course_kw)):
        prof = _baoyan_profile(student) if not guest else None
        a = _by.analyze_baoyan(_by_ch, prof)
        hint = "" if not guest else "\n\n（提示：登录后在「学业规划 → 目标导向规划 → 保研」下方填写你的 GPA、六级、学生工作等自评数据，我可以直接帮你核对每一条硬性条件）"
        return {"answer": _by.baoyan_text(a) + hint,
                "sources": advisor.build_source_cards([{
                    "doc_name": s, "source": "学校/学院正式发文",
                    "scope": "信息科学与技术学院 · 本科应届推免",
                    "updated_at": _by.load_rules()["meta"]["updated_at"], "verified": True}
                    for s in _by.load_rules()["meta"]["sources"][:3]]),
                    "route": route, "goal": _by_ch, "mode": "rules-policy",
                    "baoyan": a}

# 1.6) 考研板块问答：命中考研板块词 → 直接出对应内容（游客亦可查）
    import kaoyan as _ky
    _ky_sec = _ky.detect_section(question)
    if _ky_sec and ("考研" in question or _ky_sec != "自身情况概览"):
        a = _ky.analyze_kaoyan(_ky_sec)
        return {"answer": _ky.kaoyan_text(a),
                "sources": advisor.build_source_cards([{
                    "doc_name": s, "source": "学生自制考研规划资料（以研招网/教育部公告为准）",
                    "scope": "考研规划 · 信息科学与技术学院",
                    "updated_at": _ky.load_rules()["meta"]["updated_at"], "verified": False}
                    for s in _ky.load_rules()["meta"]["sources"]]),
                "route": route, "goal": "考研", "mode": "rules-policy",
                "kaoyan": a}

    # 1.7) 出国留学问答：命中留学渠道词 → 返回北化留学项目数据（游客亦可查）
    import studyabroad as _sa
    _sa_kw = _sa.detect_query(question)
    if _sa_kw is not None and not ("考研" in question and not _sa.has_strong_kw(question)):
        a = _sa.analyze_studyabroad(_sa_kw)
        return {"answer": _sa.studyabroad_text(a),
                "sources": advisor.build_source_cards([{
                    "doc_name": "《北化留学》学生海外学习项目册",
                    "source": "北京化工大学国际交流与合作处",
                    "scope": "出国留学 · 海外学习项目",
                    "updated_at": "2026-10", "verified": False}]),
                "route": route, "goal": "出国", "mode": "rules-policy",
                "studyabroad": a}

    # 1.8) 就业任务清单问答：命中年级任务/招聘节点词 → 返回四年清单（游客亦可查）
    import career as _cr
    if _cr.detect(question):
        a = _cr.analyze_career()
        return {"answer": _cr.career_text(a),
                "sources": advisor.build_source_cards([{
                    "doc_name": "《本科生各年级就业任务清单》",
                    "source": "学生自制就业规划资料（招聘节奏以企业公告为准）",
                    "scope": "就业规划 · 全体本科生",
                    "updated_at": _cr.analyze_career()["meta"]["updated_at"], "verified": False}]),
                "route": route, "goal": "就业", "mode": "rules-policy",
                "career": a}

    # 2) 信息不足时主动追问；游客问学业规划 → 引导注册登录
    #    例外：知识库能强命中（关键词命中≥2）时直接走知识库回答。
    #    转专业条件、处分标准这类政策性问题是公开信息，不依赖用户画像；
    #    否则这批手册条目会被"请先登录"拦在前面，永远答不出来。
    if route in ("study", "mixed"):
        _kb_strong = False
        if _kb_top:
            _strong_hit = sum(1 for k in _kb_top[0].get("keywords", []) if k in question)
            # 关键词命中≥2，或命中≥1 且整句高度相似（如"毕业设计有什么要求"）
            _kb_strong = _strong_hit >= 2 or (
                _strong_hit >= 1 and advisor._similarity(question, _kb_top[0]) >= 0.45)
        if _kb_strong and (guest or not student.get("major")):
            # 改走知识库：这类提问不依赖画像，也不需要"转专业面板"那套目标专业识别
            route = "life"
        elif guest:
            return {"answer": "选课推荐与学业规划需要结合你的专业、年级等画像信息。\n"
                              "请先「注册 / 登录」——选择学院、年级和专业后，我就能依据真实培养方案为你生成个性化选课建议。",
                    "sources": [], "route": route, "need_login": True}
        elif not student.get("major"):
            return {"answer": "为了给你准确的学业建议，请先补充你的专业。", "sources": [], "route": route}

    # 3) 检索知识库 + 组装培养方案上下文
    hits = advisor.search_kb(question)
    sources = advisor.build_source_cards(hits)
    context_parts = []
    if hits:
        context_parts.append("【知识库检索结果】\n" + "\n\n".join(
            f"- 问: {h['question']}\n  答: {h['answer']}\n  (来源: {h.get('doc_name') or h.get('source')}, 适用: {h.get('scope')})"
            for h in hits))
    # 3.5) 目标识别：问题文本目标词优先，其次注册时填写的学业目标
    goal, goal_note = advisor.detect_goal(question, student.get("goal", ""))
    gp = None          # 目标导向规划结果（planner 链路产出）

    if route in ("study", "mixed"):
        major = student.get("major", "")
        grade = student.get("grade") or 0
        q_has_term = any(w in question for w in ("学期", "这学期", "本学期", "大")) and \
            any(w in question for w in ("课", "上什么", "有什么", "选什么"))
        q_has_goal = any(w in question for gwords in advisor.GOAL_ALIAS.values() for w in gwords)

        # ===== 转专业：识别转出→转入，给政策要求+方案对比+要做的工作 =====
        if goal == "转专业":
            import re as _re
            import transfer as _tf
            majors = advisor.all_majors()
            to_major = next((m for m in majors if m != major and (m in question
                          or _re.search(m[:2] + r"[^\s，。？]*专业", question))), "")
            if not to_major and major.startswith("自动化"):
                for alt in ("计算机科学与技术", "人工智能", "电子信息工程"):
                    if any(k in question for k in (alt[:2], "计算机", "AI", "人工智能")):
                        to_major = alt if alt != major else ""
                        break
            if not to_major:
                return {"answer": f"识别到你有意转专业（当前：{major}）。请告诉我目标专业——"
                                  f"系统已收录培养方案的专业有：{'、'.join(majors)}。\n"
                                  "例如：“我想从自动化转到计算机科学与技术”，我会给出政策要求、两方案课程对比与准备清单。",
                        "sources": [], "route": route, "goal": goal, "need_major": True}
            a = _tf.analyze_transfer(major, to_major, grade)
            body = _tf.transfer_text(a)
            # 若命中不予考虑情形等硬伤，前置强调
            ans = body
            return {"answer": ans + "\n\n（政策条款均出自《北京化工大学本科生转专业实施细则》及当学年通知附件；"
                                    "课程对比基于两专业 2025 执行计划原文；具体考核方案与学分认定以转入学院当年通知为准）",
                    "sources": advisor.build_source_cards([{
                        "doc_name": "北京化工大学本科生转专业实施细则（校教发〔2022〕24号）及转专业通知附件",
                        "source": "教务处/学生处官网发布文件", "scope": "全校本科一至三年级",
                        "updated_at": "2025-2026学年", "verified": True}]),
                    "route": route, "goal": goal, "mode": "rules-policy"}
        # 目标导向规划：命中目标词，或有目标且在求规划 → 知识库→提示词→大模型链路
        if major and (q_has_goal or (goal != "暂未确定" and (q_has_term or "规划" in question or "推荐" in question))):
            profile_text = (f"{student['name']}，{student.get('college','')}{major}，"
                            f"{grade}级，{student.get('campus','')}，"
                            f"目标：{goal}（{goal_note}），偏好：{student.get('preference','无')}")
            gp = planner.generate_plan(major, grade, goal, profile_text)
            if not gp or not gp[0]:
                gp = None
        if gp:
            ans, prompt, mode, _sched = gp
            # [AI编写] 目标规划回答追加待同步提示（学分待同步轮）
            if not _personal_snapshot(request, student):
                ans += ("\n\n⏳ 注：以上\"已修学分\"按培养方案排课顺序推算，你尚未开启个性化服务同步修读记录，"
                        "实际已获学分为待同步状态；可在首页右侧「个性化服务」登录后自动更新。")
            extra = ""
            if q_has_term:
                scq = advisor.term_schedule(major, grade, question)
                if scq and "error" not in scq:
                    extra = "\n\n——附：你问的 " + scq["target_label"] + " 方案课表——\n" + advisor.schedule_text(scq)
            src = ("（本规划由大模型基于专业课程知识库+提示词生成，遵循学分/课时/难度三条硬约束）"
                   if mode == "llm" else
                   "（本地规则引擎按同一提示词约束生成；已接入大模型后此环节由大模型完成）")
            kbsrc = planner.kb_plan(major)
            cards = advisor.build_source_cards([{
                "doc_name": kbsrc["source"].strip("《》"),
                "source": "专业课程知识库（培养方案+课时/难度标注）",
                "scope": f"{major} · {grade}级", "updated_at": "2025版", "verified": True}]) if kbsrc else []
            return {"answer": ans + "\n" + src + extra, "sources": cards,
                    "route": route, "goal": goal, "mode": mode,
                    "prompt_preview": (prompt[:300] + "…") if prompt else ""}
        # 未走目标规划：按 年级+专业 精确定位目标学期，有序读取课表
        sc = advisor.term_schedule(major, grade, question)
        # [AI编写] 问答链路准备学分待同步说明（学分待同步轮）
        _snap = _personal_snapshot(request, student)
        # [AI编写] 课表类回答追加待同步口径，防止引用推算学分冒充实绩（学分待同步轮）
        _credit_note = ("" if _snap else
                        "\n\n⏳ 注：以上\"距毕业还剩\"按培养方案排课顺序推算，你尚未开启个性化服务同步修读记录，"
                        "实际已获学分为待同步状态；可在首页右侧「个性化服务」登录后自动更新。")
        if sc and "error" not in sc:
            context_parts.append(advisor.schedule_text(sc) + _credit_note)
            plan = advisor.get_major_graph(major)
            if plan:
                later = [n["name"] for n in plan["nodes"]
                         if n["term"] > sc["target_term"] and n["ctype"] == "必修"][:12]
                if later:
                    context_parts.append(
                        f"【后续学期必修预告（暂不选课，仅供规划参考）】"
                        + "、".join(later) + " 等；如需查询其他学期，请说明'第N学期'或'大X下'")
        elif sc and "error" in sc:
            context_parts.append(f"【培养方案·{major}】{sc['error']}；来源：{sc['source']}")
        else:
            plan = advisor.get_major_graph(major)
            # [AI编写] 问答上下文接入学分待同步状态（学分待同步轮）
            overview = advisor.plan_overview(major, grade, snapshot=_personal_snapshot(request, student))
            if overview:
                if overview.get("credit_synced"):
                    prog = "；".join(f"{p['section']} {p['done_required']}/{p['required']}分" for p in overview["progress"])
                    context_parts.append(
                        f"【培养方案·{major}】来源：{overview['source']}；最低毕业学分 {overview['grad_credit']}。"
                        f"当前第 {overview['current_term']} 学期，已获 {overview['done_credit']} 分（{overview['pct']}%）。"
                        f"各模块完成度：{prog}")
                else:
                    context_parts.append(
                        f"【培养方案·{major}】来源：{overview['source']}；最低毕业学分 {overview['grad_credit']}。"
                        f"当前第 {overview['current_term']} 学期。注意：该学生尚未开启个性化服务同步修读记录，"
                        "实际已获学分待同步，严禁按方案排课顺序推算或编造其已修学分与完成度；"
                        "如需学分信息，请提示其在首页右侧「个性化服务」登录同步。")
            elif plan:
                name_of = {n["id"]: n["name"] for n in plan["nodes"]}
                prereq_of = {n["id"]: [] for n in plan["nodes"]}
                for l in plan["links"]:
                    prereq_of.setdefault(l["target"], []).append(name_of.get(l["source"], l["source"]))
                course_lines = "\n".join(
                    f"  - {n['name']}（{n['credit']}学分, {n['semester']}, {n['ctype']}）先修: "
                    + ("、".join(prereq_of[n["id"]]) or "无")
                    for n in plan["nodes"])
                context_parts.append(f"【培养方案数据·{plan['major']}】总学分要求 {plan['total_required']}：\n{course_lines}")
            else:
                context_parts.append(
                    f"【培养方案】系统当前仅收录专业：{'、'.join(advisor.all_majors())}；"
                    f"该学生专业未收录，请如实说明并建议查阅学院官方文件。")
        context_parts.append(
            f"【学生画像】{student['name']}，{student.get('college','')}{major}，{grade}级，"
            f"{student.get('campus','')}，目标：{student.get('goal','未填写')}，偏好：{student.get('preference','无')}")

    # 4) 生成回答：知识库/方案内 → 事实约束模式；任意生活问题 → 通用问答模式（像豆包）
    user_prompt = (("\n".join(context_parts) + "\n\n" if context_parts else "") + f"学生问题：{question}")
    generic = False
    if llm_available():
        try:
            if not hits and route not in ("study", "mixed"):
                generic = True
                cid = (body.chat_id or "").strip()[:64]
                msgs = [{"role": "system", "content": GENERIC_SYSTEM_PROMPT}]
                msgs += _chat_history.get(cid, [])[-CHAT_HIST_MAX:]
                msgs.append({"role": "user", "content": question})
                answer = llm_chat(msgs, temperature=0.7) or ""
                if cid and answer:      # 会话记忆：保留最近 8 条
                    h = _chat_history.setdefault(cid, [])
                    h += [{"role": "user", "content": question},
                          {"role": "assistant", "content": answer}]
                    _chat_history[cid] = h[-CHAT_HIST_MAX:]
                if answer and not answer.endswith("（AI"):
                    answer += "\n\n（以上为 AI 通用建议，非学校官方口径；校园具体事务以学校发布为准，可用下方反馈入口帮我们收录进知识库）"
            else:
                answer = llm_chat([{"role": "system", "content": SYSTEM_PROMPT},
                                   {"role": "user", "content": user_prompt}])
        except RuntimeError as exc:
            generic = False
            answer = advisor.fallback_answer(question, route, hits) + f"\n\n（大模型暂时不可用：{exc}）"
    else:
        if route in ("study", "mixed"):
            if sc and "error" not in sc:
                answer = advisor.schedule_text(sc) + _credit_note + \
                    "\n\n（本地演示模式：以上为规则引擎按培养方案直接读取的有序课表；配置百炼 API Key 后，大模型会在此数据之上做个性化解读与答疑）"
            else:
                # [AI编写] 本地兜底回答接入学分待同步状态（学分待同步轮）
                ov = advisor.plan_overview(major, grade, snapshot=_personal_snapshot(request, student))
                answer = (advisor.local_study_answer(ov) if ov
                          else advisor.fallback_answer(question, route, hits))
        else:
            answer = advisor.fallback_answer(question, route, hits)

    return {"answer": answer, "sources": sources, "route": route, "generic": generic,
            "needs_feedback": (not hits and route in ("life", "mixed", "other", "unknown") and not generic),
            "llm_mode": llm_mode() if llm_available() else "local-demo"}


# ---------------- 课程图谱 ----------------
@app.get("/api/majors")
def majors(request: Request):
    optional_student(request)
    return {"majors": advisor.all_majors()}


@app.get("/api/plan")
def plan(request: Request, major: str = "", grade: int = 0):
    """学业规划（个性化选课推荐）：需登录，按年级推算培养进度 + 下学期推荐。

    已获学分只在学生启用个性化服务并同步修读记录后展示；
    未同步时相关字段返回 None（前端显示"待同步"），不用方案排课冒充实际成绩。
    """
    student = current_student(request)
    major = major or student.get("major", "")
    grade = grade or student.get("grade") or 0
    # [AI编写] 学业规划接口按同步状态返回学分（学分待同步轮）
    snap = _personal_snapshot(request, student)
    ov = advisor.plan_overview(major, int(grade), snapshot=snap)
    if not ov:
        raise HTTPException(status_code=404,
                            detail=f"专业《{major}》暂无培养方案规划数据（可选：{'、'.join(advisor.all_majors())}）")
    return ov


@app.get("/api/term-schedule")
def term_schedule_api(request: Request, major: str = "", grade: int = 0, term: int = 0):
    """按学期有序查询课表：定位年级+专业对应方案的目标学期，分组返回必修/选修。"""
    student = optional_student(request)
    major = major or student.get("major", "")
    grade = grade or student.get("grade") or 0
    if not major:
        raise HTTPException(status_code=400, detail="请指定专业（或登录后自动匹配）")
    CN = {1: "第一学期", 2: "第二学期", 3: "第三学期", 4: "第四学期",
          5: "第五学期", 6: "第六学期", 7: "第七学期", 8: "第八学期"}
    q = "" if term <= 0 else CN.get(term, "")
    if term > 0 and not q:
        raise HTTPException(status_code=400, detail="学期须为 1-8")
    sc = advisor.term_schedule(major, int(grade), q)   # 不传 term → 默认下学期
    if not sc:
        raise HTTPException(status_code=404,
                            detail=f"专业《{major}》无培养方案数据（可选：{'、'.join(advisor.all_majors())}）")
    if "error" in sc:
        raise HTTPException(status_code=400, detail=sc["error"])
    return sc


# ---------------- 实时课程表（本学期 · 周一~周日 周课表） ----------------
# 作息时间放在 data/timetable_config.json，拿到学校正式作息表后替换该文件的 periods 即可，
# 不用改代码。个人课表按学号存在 data/timetables.json（服务器端保存，换设备/浏览器都在）。
TIMETABLE_PATH = os.path.join(DATA_DIR, "timetables.json")
TT_CONFIG_PATH = os.path.join(DATA_DIR, "timetable_config.json")

DEFAULT_TT_CONFIG = {
    "note": "占位作息时间：请以学校教务发布的作息表为准，替换 periods 即可。",
    "days": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"],
    "periods": [
        {"no": 1, "label": "第1节", "time": "08:00-08:45"},
        {"no": 2, "label": "第2节", "time": "08:55-09:40"},
        {"no": 3, "label": "第3节", "time": "10:00-10:45"},
        {"no": 4, "label": "第4节", "time": "10:55-11:40"},
        {"no": 5, "label": "第5节", "time": "13:30-14:15"},
        {"no": 6, "label": "第6节", "time": "14:25-15:10"},
        {"no": 7, "label": "第7节", "time": "15:30-16:15"},
        {"no": 8, "label": "第8节", "time": "16:25-17:10"},
        {"no": 9, "label": "第9节", "time": "18:00-18:45"},
        {"no": 10, "label": "第10节", "time": "18:55-19:40"},
        {"no": 11, "label": "第11节", "time": "19:50-20:35"},
        {"no": 12, "label": "第12节", "time": "20:45-21:30"},
    ],
}


def load_tt_config():
    """作息时间配置：优先读 data/timetable_config.json，缺失或损坏时用内置默认值。"""
    try:
        with open(TT_CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        if cfg.get("days") and cfg.get("periods"):
            return cfg
    except Exception:
        pass
    return DEFAULT_TT_CONFIG


def load_timetables():
    try:
        with open(TIMETABLE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_timetables(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = TIMETABLE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, TIMETABLE_PATH)


def current_term_info(grade: int):
    """按今天的日期推算当前学期，并换算成『进入大学后的第几学期』。
    例：2026-10 查 2025 级 → 2026年秋 · 大二上学期（第 3 学期）。"""
    import datetime
    today = datetime.date.today()
    ay = today.year if today.month >= 8 else today.year - 1
    season = "秋" if today.month >= 8 else "春"
    term = advisor.current_term_index(int(grade)) if grade else 0
    if not term:
        return {"term": 0, "label": f"{ay}年{season}", "sub": "未填写入学年级"}
    grade_no, _ = advisor.term_naming(term)
    return {"term": term, "label": f"{ay}年{season} · {grade_no}{'上' if term % 2 else '下'}学期",
            "sub": f"进入大学后第 {term} 学期"}


def _plan_grade(major: str) -> int:
    """培养方案自带的年级（如 2025 级）：游客没填年级时用它推算当前学期。"""
    g = advisor.get_major_graph(major) or {}
    for n in g.get("nodes", []):
        m = re.match(r"(\d{4})", str(n.get("semester", "")))
        if m:
            return int(m.group(1))
    return 0


def _clean_tt_courses(raw, max_periods: int, no_day_ok: bool = False):
    """校验并规整前端提交的课程块（课程名必填；星期/节次越界丢弃）。
    no_day_ok=True 用于识别导入：识别不到星期时允许 day=0（等用户在预览里补选）。"""
    out = []
    if not isinstance(raw, list):
        return out
    for it in raw[:80]:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name", "")).strip()[:60]
        if not name:
            continue
        try:
            day, start, span = int(it.get("day", 1)), int(it.get("start", 1)), int(it.get("span", 1))
        except (TypeError, ValueError):
            continue
        if not (0 <= day <= 7) or not (1 <= start <= max_periods):
            continue
        if day == 0 and not no_day_ok:
            continue
        span = max(1, min(span, max_periods - start + 1))
        out.append({"name": name,
                    "teacher": str(it.get("teacher", "")).strip()[:30],
                    "room": str(it.get("room", "")).strip()[:40],
                    "weeks": str(it.get("weeks", "")).strip()[:30],
                    "day": day, "start": start, "span": span})
    out.sort(key=lambda c: (c["day"] or 9, c["start"]))
    return out


@app.get("/api/timetable")
def timetable_get(request: Request, major: str = "", grade: int = 0):
    """实时课程表：作息配置 + 本学期标签 + 个人课表（未导入则为空框架）+ 培养方案本学期课程。
    游客/未导入时 courses 为空，前端只显示空框架与培养方案参考清单。"""
    student = optional_student(request)
    logged = bool(student.get("student_id"))
    major = major or student.get("major", "")
    grade = int(grade or student.get("grade") or 0)
    grade_assumed = False
    if not grade and major:                 # 未填年级（游客）：按培养方案自带年级推算学期
        grade = _plan_grade(major)
        grade_assumed = bool(grade)
    cfg = load_tt_config()
    info = current_term_info(grade)
    courses = []
    if logged:
        courses = load_timetables().get(student["student_id"], {}).get("courses", []) or []
        courses = _clean_tt_courses(courses, len(cfg["periods"]))
    plan_courses, plan_source = [], ""
    if major and info["term"]:
        sc = advisor.term_schedule(major, grade, "本学期")
        if sc and not sc.get("error"):
            plan_source = sc.get("source", "")
            plan_courses = [{"name": c["name"], "credit": c["credit"],
                             "nature": c["nature"], "section": c.get("section", "")}
                            for c in (sc.get("required", []) + sc.get("electives", []))]
    return {"logged_in": logged, "config": cfg, "term": info, "courses": courses,
            "grade": grade, "grade_assumed": grade_assumed,
            "plan_courses": plan_courses, "plan_source": plan_source}


class TimetableBody(BaseModel):
    courses: list = []


@app.post("/api/timetable")
def timetable_save(body: TimetableBody, request: Request):
    """保存个人课表（需登录）：整体覆盖式保存，按学号存在 data/timetables.json。"""
    student = current_student(request)
    cfg = load_tt_config()
    courses = _clean_tt_courses(body.courses, len(cfg["periods"]))
    data = load_timetables()
    data[student["student_id"]] = {"courses": courses,
                                   "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    save_timetables(data)
    return {"ok": True, "count": len(courses), "courses": courses}


@app.delete("/api/timetable")
def timetable_clear(request: Request):
    """清空自己的课表（需登录）。"""
    student = current_student(request)
    data = load_timetables()
    data.pop(student["student_id"], None)
    save_timetables(data)
    return {"ok": True, "courses": []}


# ---------------- 课表识别导入（复制粘贴 / 课表截图识别） ----------------
CN_WEEK = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7,
           "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7}

# 教务系统课表文本里常见的字段名，抽课程名时先抹掉，避免把标签当成课程名
TT_LABEL_NOISE = ("课程名称", "课程名", "上课时间", "上课地点", "任课教师", "教师姓名",
                  "教学班", "课程号", "课程代码", "备注", "序号", "教室", "教师", "周次",
                  "节次", "校区", "学分", "星期", "时间", "地点", "课程")

TT_LLM_PROMPT = """你是课表结构化助手：把课表内容抽成 JSON 数组，每门课一个对象，字段固定为
name(课程名)、teacher(教师，未知留空)、room(上课地点，未知留空)、weeks(周次，如"1-16周"，未知留空)、
day(星期几，1=周一 … 7=周日)、start(起始节次，整数)、span(连堂节数，整数，未知填1)。
同一门课有多个上课时间就拆成多条；只输出 JSON 数组，不要解释，不要 markdown 代码块。"""


def _tt_norm(s: str) -> str:
    """全角转半角 + 压掉制表符，便于写规则。"""
    buf = []
    for ch in s:
        code = ord(ch)
        if code == 0x3000:
            buf.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:
            buf.append(chr(code - 0xFEE0))
        else:
            buf.append(ch)
    return re.sub(r"[\t\r\f\v]+", " ", "".join(buf)).replace("\u00a0", " ")


def _tt_weekday(text: str):
    m = re.search(r"(?:周|星期|礼拜)\s*([一二三四五六日天1-7])", text)
    return CN_WEEK.get(m.group(1)) if m else None


def _tt_period(text: str):
    """解析节次 → (起始节, 节数)；取不到返回 None。"""
    m = re.search(r"第?\s*(\d{1,2})\s*[-~到至、,，]\s*(\d{1,2})\s*节", text)
    if m and 1 <= min(int(m.group(1)), int(m.group(2))) <= 12:
        a, b = int(m.group(1)), int(m.group(2))
        return min(a, b), min(6, abs(b - a) + 1)
    m = re.search(r"第?\s*(\d{1,2})\s*节", text)
    if m and 1 <= int(m.group(1)) <= 12:
        return int(m.group(1)), 1
    for m in re.finditer(r"(\d{1,2})\s*[-~]\s*(\d{1,2})", text):      # 无“节”字，且右邻不是“周”
        a, b = int(m.group(1)), int(m.group(2))
        if a < b <= 12 and "周" not in text[m.end():m.end() + 2]:
            return a, b - a + 1
    return None


def _tt_weeks(text: str) -> str:
    m = re.search(r"第?\s*([0-9][0-9,\-~至到]*)\s*周", text)
    if m:
        return m.group(1).replace("，", ",") + "周"
    m = re.search(r"(单周|双周)", text)
    return m.group(1) if m else ""


ROOM_RE = re.compile(r"[\u4e00-\u9fa5A-Za-z]{1,8}(?:教|楼|室|馆|区|园|阶|场)[\u4e00-\u9fa5A-Za-z0-9\-]{0,10}\d{1,4}[A-Za-z0-9\-]{0,4}"
                     r"|[A-Z]{1,4}[-]?\d{2,4}(?:室|教室)?")
TEACHER_RE = re.compile(r"(?:任课教师|教师姓名|教师|老师)\s*[:：]?\s*([\u4e00-\u9fa5]{1,4})"
                        r"|([\u4e00-\u9fa5]{1,4})\s*(?:老师|教授)")


def _tt_parse_blob(blob: str, day=None):
    """从一段文字里抽出一门课；day 为表格列推出的星期（文本里没有星期时使用）。"""
    txt = " ".join(_tt_norm(blob).split())
    if not txt:
        return None
    wd = _tt_weekday(txt) or day
    per = _tt_period(txt)
    if not wd or not per:
        return None
    weeks = _tt_weeks(txt)
    room_m = ROOM_RE.search(txt)
    room = room_m.group(0).strip() if room_m else ""
    teacher = ""
    tm = TEACHER_RE.search(txt)
    if tm:
        teacher = (tm.group(1) or tm.group(2) or "").strip()
        teacher = re.sub(r"(老师|教授)$", "", teacher)
    rest = txt
    for piece in (room, teacher):
        if piece:
            rest = rest.replace(piece, " ")
    rest = re.sub(r"(?:周|星期|礼拜)\s*[一二三四五六日天1-7]", " ", rest)
    rest = re.sub(r"第?\s*\d{1,2}\s*[-~到至、,，]?\s*\d{0,2}\s*节", " ", rest)
    rest = re.sub(r"第?\s*[0-9][0-9,\-~至到]*\s*周", " ", rest)
    rest = re.sub(r"\d{1,2}:\d{2}\s*[-~]\s*\d{1,2}:\d{2}", " ", rest)
    for word in TT_LABEL_NOISE:
        rest = rest.replace(word, " ")
    cands = [c.strip() for c in re.findall(r"[\u4e00-\u9fa5A-Za-z][\u4e00-\u9fa5A-Za-z0-9（）()·]{1,29}", rest)]
    cands = [c for c in cands if len(c) >= 2 and not c.isdigit()]
    if not cands:
        return None
    name = max(cands, key=len)
    return {"name": name, "teacher": teacher, "room": room, "weeks": weeks,
            "day": wd, "start": per[0], "span": per[1]}


def _tt_parse_grid(text: str):
    """解析“课表页整页复制”出来的表格文本：表头是星期，行首是节次。"""
    courses, col2day = [], {}
    for line in text.split("\n"):                      # 逐行处理，保留制表符用于分列
        if not line.strip():
            continue
        # 有制表符时只按制表符分列（连续制表符=空单元格，代表这一天没课）；
        # 没有制表符（从 PDF/文本里复制的）时再按 2 个以上空格分列
        cells = ([c.strip() for c in line.split("\t")] if "\t" in line
                 else [c.strip() for c in re.split(r"\s{2,}", line.strip())])
        if len(cells) < 2:
            continue
        heads = [_tt_weekday(c) if c else None for c in cells]
        if sum(1 for h in heads if h) >= 3:            # 表头行
            col2day = {i: h for i, h in enumerate(heads) if h}
            continue
        per = _tt_period(cells[0])
        if not per:
            continue
        for i, cell in enumerate(cells[1:], start=1):
            if not cell:
                continue
            day = col2day.get(i) or (i if 1 <= i <= 7 else None)
            if not day:
                continue
            item = _tt_parse_blob(cells[0] + " " + cell, day=day)
            if item:
                item["day"] = day
                courses.append(item)
    return courses


TT_TYPE_SYMBOLS = "★☆◇◆●○◎□■"          # 课表里课程类型标记：★讲课 ◇上机 ●实践 ○实验
CAMPUS_WORDS = ("北区", "东区", "西区", "昌平", "南口", "昌平校区")
_TEACHER_LINE_RE = re.compile(r"^[\u4e00-\u9fa5]{2,4}(?:\s*[,，、]\s*[\u4e00-\u9fa5]{2,4})*$")
_TT_NOISE_BITS = ("考试", "考查", "未安排", "讲课", "上机", "实践", "实验", "周学时")


def _tt_block_to_course(lines):
    """把“强智课表网页”里一门课的多行文本转成一门课（星期可能为空，由用户补选）。"""
    name = lines[0].rstrip(TT_TYPE_SYMBOLS).strip()
    if len(name) < 2:
        return None
    per, weeks, room, teacher, day = None, "", "", "", 0
    for idx, s in enumerate(lines[1:], start=1):
        m = re.search(r"\((\d{1,2})\s*[-~]\s*(\d{1,2})\s*节\)", s)
        if m and not per:
            per = (int(m.group(1)), min(6, int(m.group(2)) - int(m.group(1)) + 1))
            weeks = s[m.end():].strip()
            continue
        m = re.search(r"\((\d{1,2})\s*节\)", s)
        if m and not per:
            per = (int(m.group(1)), 1)
            weeks = s[m.end():].strip()
            continue
        if not day:
            d = _tt_weekday(s)
            if d:
                day = d
        if not room and (any(w in s for w in CAMPUS_WORDS)
                         or re.search(r"(?:教|楼|室|馆|阶|场)[A-Za-z]?\d", s)):
            room = s
            continue
        if not teacher and room and idx >= 2 and _TEACHER_LINE_RE.match(s) \
                and not any(w in s for w in _TT_NOISE_BITS):
            teacher = s
    if not per:
        return None
    return {"name": name, "teacher": teacher, "room": room, "weeks": weeks,
            "day": day, "start": per[0], "span": per[1]}


def _tt_parse_blocks(text: str):
    """解析“课表网页整页复制”的通用格式：每门课一段，段首是『课程名+类型符号』行。
    这类复制结果里通常没有“星期”，星期留 0 由用户在预览里补选。"""
    blocks, cur = [], None
    for line in text.split("\n"):
        s = line.strip().strip("\ufffc").strip()
        if not s or s in TT_TYPE_SYMBOLS:
            continue
        if s[-1] in TT_TYPE_SYMBOLS and len(s) > 2 and "-" not in s[:2]:
            if cur:
                blocks.append(cur)
            cur = [s]
            continue
        if cur is not None:
            cur.append(s)
    if cur:
        blocks.append(cur)
    out = []
    for b in blocks:
        c = _tt_block_to_course(b)
        if c:
            out.append(c)
    return out


def _tt_parse_rules(text: str):
    """规则解析：表格文本 → 逐行 → 课程块（强智网页复制）→ 短文本整段；
    最后去重并把连堂合并成一个课程块。解析不到的字段（多为星期）留给用户补。"""
    courses = _tt_parse_grid(text)
    if not courses:                                   # 复制出来的文本大多是“一行一门课”
        for line in text.split("\n"):
            item = _tt_parse_blob(line)
            if item:
                courses.append(item)
    if not courses:                                   # 强智课表网页整页复制：每门课一段
        courses = _tt_parse_blocks(text)
    if not courses:                                   # 一个课程块占多行，且块里只有一个星期词
        for block in re.split(r"\n\s*\n", text):
            if len(re.findall(r"(?:周|星期|礼拜)\s*[一二三四五六日天1-7]", block)) <= 1:
                item = _tt_parse_blob(block)
                if item:
                    courses.append(item)
    if not courses and len(text) <= 200:              # 兜底：短文本整段当成一门课
        item = _tt_parse_blob(text)
        if item:
            courses.append(item)

    seen, uniq = set(), []
    for c in courses:
        # 星期未知时，同名同节次也可能是不同时段（不同周次/地点），不能当重复删掉
        key = ((c["name"], c["day"], c["start"]) if c["day"]
               else (c["name"], c["start"], c["room"], c["weeks"], c["teacher"]))
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    # 课表页里跨节次的课会被复制成多行（rowspan 展开）：同一天、地点周次一致、
    # 节次首尾相接的合并成一个连堂；中间有间隔的保留为两条。
    groups = {}
    for c in uniq:
        groups.setdefault((c["name"], c["day"], c["room"], c["weeks"], c["teacher"]), []).append(c)
    merged = []
    for items in groups.values():
        if not items[0]["day"]:            # 星期没定的课不做连堂合并（无从判断是不是同一天）
            merged.extend(items)
            continue
        items.sort(key=lambda x: x["start"])
        cur = dict(items[0])
        for nxt in items[1:]:
            if nxt["start"] <= cur["start"] + cur["span"]:
                cur["span"] = max(cur["span"], nxt["start"] + nxt["span"] - cur["start"])
            else:
                merged.append(cur)
                cur = dict(nxt)
        merged.append(cur)
    merged.sort(key=lambda c: (c["day"] or 9, c["start"]))
    return merged


def _tt_json_list(out: str):
    """从大模型输出里取出 JSON 数组（容忍 ```json 包裹与前后废话）。"""
    s = (out or "").strip()
    i, j = s.find("["), s.rfind("]")
    if i < 0 or j <= i:
        return []
    try:
        data = json.loads(s[i:j + 1])
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _tt_parse_by_llm(text: str):
    out = llm_chat([{"role": "system", "content": TT_LLM_PROMPT},
                    {"role": "user", "content": text[:6000]}], temperature=0.0, timeout=90)
    return _tt_json_list(out)


def _tt_parse_by_vision(image_data_url: str):
    messages = [{"role": "user", "content": [
        {"type": "text", "text": "这是学生从教务系统截的课表图片。请按要求抽取：\n" + TT_LLM_PROMPT},
        {"type": "image_url", "image_url": {"url": image_data_url}},
    ]}]
    return _tt_json_list(llm_vision(messages, timeout=120))


class TTImportBody(BaseModel):
    text: str = ""
    image: str = ""          # dataURL 或纯 base64
    save: bool = False


@app.post("/api/timetable/import")
def timetable_import(body: TTImportBody, request: Request):
    """课表识别导入：粘贴课表文本（规则优先、大模型兜底）或上传课表截图（qwen-vl 识别）。
    默认只返回解析结果做预览，save=true 时直接写入个人课表。"""
    student = current_student(request)
    cfg = load_tt_config()
    warnings, raw_items, source = [], [], ""

    if body.image.strip():
        url = body.image.strip()
        if not url.startswith("data:"):
            url = "data:image/jpeg;base64," + url
        if len(url) > 8 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="图片太大，请压缩到 8MB 以内再上传")
        try:
            raw_items = _tt_parse_by_vision(url)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"图片识别失败：{exc}")
        source = "vision"
    elif body.text.strip():
        raw_items = _tt_parse_rules(body.text)
        source = "rules"
        if not raw_items:
            if llm_available():
                try:
                    raw_items = _tt_parse_by_llm(body.text)
                    source = "llm"
                except Exception as exc:
                    warnings.append(f"大模型兜底失败：{exc}")
            else:
                warnings.append("未配置大模型，只用了规则解析")
        if not raw_items:
            raise HTTPException(status_code=400, detail="没识别出课程：请确认复制的是课表内容"
                                "（或配置 DASHSCOPE_API_KEY 后用大模型兜底）")
    else:
        raise HTTPException(status_code=400, detail="请粘贴课表内容，或上传课表截图")

    courses = _clean_tt_courses(raw_items, len(cfg["periods"]), no_day_ok=True)
    if not courses:
        raise HTTPException(status_code=400, detail="识别到了内容，但缺课程名/星期/节次，无法填入课表")
    need_day = sum(1 for c in courses if not c["day"])
    if body.save and need_day:
        raise HTTPException(status_code=400,
                            detail=f"还有 {need_day} 门课没指定星期，请先选好星期再导入")
    if body.save:
        data = load_timetables()
        data[student["student_id"]] = {"courses": courses,
                                       "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        save_timetables(data)
    if need_day:
        warnings.append(f"有 {need_day} 门课在复制内容里找不到星期，请在下面选一下星期再导入")
    return {"ok": True, "source": source, "count": len(courses), "courses": courses,
            "need_day": need_day, "warnings": warnings, "saved": bool(body.save)}


# ---------------- 保研四通道（政策要求 + 画像自评） ----------------
class BaoyanSelfBody(BaseModel):
    gpa: str = ""
    cet6: str = ""
    rank_pct: str = ""
    discipline: str = ""
    cadre: bool = False
    party: bool = False
    volunteer: bool = False
    teacher_cert: bool = False
    research: bool = False
    advisor_contacted: bool = False


def _baoyan_profile(student: dict) -> dict:
    """从学生记录取出保研自评画像（未填过则为空，由前端表单提交）。"""
    return dict(student.get("baoyan_self") or {})


@app.post("/api/baoyan/self")
def baoyan_self_save(body: BaoyanSelfBody, request: Request):
    """保存保研自评数据（GPA/六级/排名/学生工作等），写入 students.json 持久保存。"""
    student = current_student(request)
    sid = student["student_id"]
    data = body.model_dump()
    for k in ("gpa", "cet6", "rank_pct", "discipline"):
        data[k] = str(data[k]).strip()
    if data["gpa"]:
        try:
            g = float(data["gpa"])
            if not (0 <= g <= 4.0):
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=400, detail="GPA 需为 0~4.0 之间的数字")
    if data["cet6"]:
        try:
            c = int(float(data["cet6"]))
            if not (0 <= c <= 710):
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=400, detail="英语成绩需为有效分数（如 425）")
    if data["rank_pct"]:
        try:
            r = float(data["rank_pct"])
            if not (0 < r <= 100):
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=400, detail="排名百分比需在 1~100 之间")
    students = load_students()
    updated = None
    for s in students:
        if s["student_id"] == sid:
            s["baoyan_self"] = data
            updated = {k: v for k, v in s.items() if k != "password"}
            break
    if updated is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    path = os.path.join(DATA_DIR, "students.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(students, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    global _students_cache
    _students_cache = None
    return {"ok": True, "msg": "自评数据已保存，保研通道核对结果将按此即时更新",
            "baoyan_self": data, "profile": updated}


@app.get("/api/baoyan")
def baoyan_api(request: Request, channel: str = ""):
    """保研四通道：channel 留空返回总览；指定通道返回该通道政策+画像自评。"""
    import baoyan as _by
    student = optional_student(request)
    ch = (channel or "").strip() or "保研"
    prof = _baoyan_profile(student) if not student.get("guest") else None
    a = _by.analyze_baoyan(ch, prof)
    if a.get("error"):
        raise HTTPException(status_code=400, detail=a["error"])
    return {"baoyan": a, "answer": _by.baoyan_text(a),
            "channels": _by.CHANNELS, "logged_in": not student.get("guest")}


@app.get("/api/kaoyan")
def kaoyan_api(request: Request, section: str = ""):
    """考研六大板块：section 留空返回总览；指定板块返回该板块结构化内容。"""
    import kaoyan as _ky
    student = optional_student(request)
    sec = (section or "").strip() or "总览"
    a = _ky.analyze_kaoyan(sec)
    if a.get("error"):
        raise HTTPException(status_code=400, detail=a["error"])
    actions = (student.get("ky_actions") or []) if not student.get("guest") else []
    return {"kaoyan": a, "answer": _ky.kaoyan_text(a), "sections": _ky.SECTIONS,
            "logged_in": not student.get("guest"), "actions": actions}


@app.get("/api/studyabroad")
def studyabroad_api(request: Request, query: str = ""):
    """出国留学板块：query 为空返回地区总览；带关键词返回命中学校与全部要求。"""
    import studyabroad as _sa
    optional_student(request)
    a = _sa.analyze_studyabroad(query)
    return {"studyabroad": a, "answer": _sa.studyabroad_text(a),
            "regions": _sa.region_names()}


@app.get("/api/career")
def career_api(request: Request):
    """就业板块：返回四年任务清单与一页速查（结构化数据 + 前端 HTML）。"""
    import career as _cr
    optional_student(request)
    a = _cr.analyze_career()
    return {"career": a, "html": _cr.career_html(a), "answer": _cr.career_text(a)}


class KyActionsBody(BaseModel):
    checked: list[str] = []          # 已完成的行动项，格式 "阶段序号-条目序号"


@app.post("/api/kaoyan/actions")
def kaoyan_actions_save(body: KyActionsBody, request: Request):
    """保存考研行动清单勾选状态到账号，登录后跨设备可见。"""
    student = current_student(request)
    sid = student["student_id"]
    import kaoyan as _ky
    _stages = _ky.load_rules()["infosec"]["action"]["stages"]
    _maxsi = len(_stages) - 1
    _maxii = max(len(s["items"]) for s in _stages) - 1
    def _vk(k):
        m = re.fullmatch(r"(\d{1,2})-(\d{1,2})", str(k))
        return bool(m) and int(m.group(1)) <= _maxsi and int(m.group(2)) <= _maxii
    keys = sorted({k for k in body.checked if _vk(k)})
    students = load_students()
    updated = None
    for s in students:
        if s.get("student_id") == sid:
            s["ky_actions"] = keys
            updated = keys
            break
    if updated is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    path = os.path.join(DATA_DIR, "students.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(students, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    global _students_cache
    _students_cache = None
    return {"ok": True, "msg": f"已保存 {len(updated)} 项完成标记", "actions": updated}


@app.get("/api/goal-plan")
def goal_plan_api(request: Request, major: str = "", grade: int = 0, goal: str = "",
                  to_major: str = "", by_channel: str = "", view: str = ""):
    """目标导向课程规划：识别目标→外接课程知识库→整合生成提示词→大模型生成（无Key时规则引擎兜底）。
    goal=转专业 时走政策+方案对比分支（需 to_major）；
    goal=保研 且 view=policy 时走四通道政策解读分支（by_channel 指定通道，留空为总览）。"""
    import transfer as _tf
    student = optional_student(request)
    major = major or student.get("major", "")
    grade = grade or student.get("grade") or 0
    goal = goal.strip() or advisor.detect_goal("", student.get("goal", ""))[0]
    g, note = advisor.detect_goal("", goal)

    # ===== 保研：四通道政策解读（支教/行政/普通学业推免/直博） =====
    if g == "保研" and (view == "policy" or by_channel):
        import baoyan as _by
        ch = (by_channel or "").strip() or "保研"
        prof = _baoyan_profile(student) if not student.get("guest") else None
        a = _by.analyze_baoyan(ch, prof)
        if a.get("error"):
            raise HTTPException(status_code=400, detail=a["error"])
        return {"goal": g, "note": note, "mode": "rules-policy", "view": "policy",
                "baoyan": a, "answer": _by.baoyan_text(a),
                "channels": ["保研"] + _by.CHANNELS}

    if not major:
        raise HTTPException(status_code=400, detail="请指定专业（或登录后自动匹配）")

    if g == "转专业":
        if not to_major:
            return {"goal": g, "need_to_major": True,
                    "options": advisor.all_majors(), "from_major": major,
                    "answer": "请先选择你要转入的目标专业，系统将调取转专业政策并对比两个培养方案。"}
        a = _tf.analyze_transfer(major, to_major, grade)
        return {"goal": g, "note": note, "mode": "rules-policy",
                "transfer": a, "answer": _tf.transfer_text(a)}

    if not planner.kb_plan(major):
        raise HTTPException(status_code=404,
                            detail=f"专业《{major}》暂无课程知识库（可选：{'、'.join(planner.KB)}）")
    profile_text = (f"{student.get('name','游客')}，{student.get('college','')}{major}，{grade}级，"
                    f"目标：{g}（{note}）")
    ans, prompt, mode, sched = planner.generate_plan(major, grade, g, profile_text)
    gp = advisor.goal_plan(major, int(grade), g)   # 附：逐门匹配度打分明细（规则引擎）
    if not ans and not gp:
        raise HTTPException(status_code=404, detail="未能生成规划")
    return {"goal": g, "note": note, "mode": mode, "answer": ans,
            "prompt": prompt, "plan": gp, "schedule": sched,
            "text": advisor.goal_text(gp, "面板查询") if gp else ""}


@app.get("/api/graph")
def graph(request: Request, major: str = ""):
    optional_student(request)
    major = major or (advisor.all_majors() or [""])[0]
    data = advisor.get_major_graph(major)
    if not data:
        raise HTTPException(status_code=404, detail=f"未收录专业《{major}》，可选：{'、'.join(advisor.all_majors())}")
    return data


class PathBody(BaseModel):
    major: str
    course: str


@app.post("/api/course-path")
def course_path(body: PathBody, request: Request):
    optional_student(request)
    result = advisor.find_course_path(body.major, body.course)
    if not result:
        raise HTTPException(status_code=404, detail="未找到该课程")
    plan = advisor.get_major_graph(body.major)
    name_of = {n["id"]: n["name"] for n in plan["nodes"]}
    result["prereq_chain"] = [
        {**c, "prereq_names": [name_of.get(p, p) for p in c["prereq"]]}
        for c in result["prereq_chain"]]
    return result


@app.get("/api/goal-options")
def goal_options(request: Request):
    """目标规划面板：返回六类目标与其策略说明（游客可用）。"""
    optional_student(request)
    return {"goals": [{"goal": g, "focus": r["focus"]} for g, r in advisor.GOAL_RULES.items()
                      if g != "暂未确定"]}


class SelectBody(BaseModel):
    major: str
    courses: list
    max_credit: float = 25.0


@app.post("/api/check-selection")
def check_selection(body: SelectBody, request: Request):
    """模拟排课校验：先修缺失 + 学分上限。"""
    optional_student(request)
    return advisor.check_selection(body.major, body.courses, body.max_credit)


# ---------------- 二课堂积分（依据校《第二课堂成绩评定实施办法》规则引擎） ----------------
class ErkeBody(BaseModel):
    rule_id: str
    detail: dict = {}
    term: str = ""
    evidence: str = ""
    images: list = []          # 已上传的图片文件名列表


IMAGE_MAGIC = (b"\xff\xd8\xff", b"\x89PNG", b"GIF8", b"RIFF", b"BM")


def _safe_image_name(name: str) -> bool:
    """仅接受本服务生成的文件名：<32位hex>[_n]<扩展名>，防目录穿越。"""
    import re
    return bool(re.fullmatch(r"[0-9a-f]{32}(_\d+)?\.[a-z]{3,4}", name))


@app.post("/api/erke/upload")
async def erke_upload(request: Request, file: UploadFile = File(...)):
    """导入佐证图片：校验真实图片格式与大小后存入 data/evidence/。"""
    student = current_student(request)
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_IMAGE_EXT:
        raise HTTPException(status_code=400,
                            detail=f"仅支持图片格式：{'、'.join(sorted(ALLOWED_IMAGE_EXT))}")
    data = await file.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail=f"单张图片不能超过 {MAX_IMAGE_BYTES // 1024 // 1024}MB")
    if not data[:8].startswith(IMAGE_MAGIC):      # 魔数校验：防止改扩展名的非图片文件
        raise HTTPException(status_code=400, detail="文件内容不是有效图片")
    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    fname = uuid.uuid4().hex + ext
    with open(os.path.join(EVIDENCE_DIR, fname), "wb") as f:
        f.write(data)
    return {"ok": True, "name": fname, "size": len(data)}


@app.get("/api/erke/image/{fname}")
def erke_image(request: Request, fname: str):
    """查看/下载单张佐证图片（需登录，文件名白名单校验）。"""
    current_student(request)
    if not _safe_image_name(fname):
        raise HTTPException(status_code=400, detail="非法文件名")
    path = os.path.join(EVIDENCE_DIR, fname)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="图片不存在")
    return FileResponse(path, headers={"Content-Disposition": f"inline; filename={fname}"})


@app.get("/api/erke/export")
def erke_export(request: Request):
    """导出当前学生的二课记录 + 佐证图片为 zip 压缩包。"""
    student = current_student(request)
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM erke_records2 WHERE student_id=? ORDER BY id", (student["student_id"],))]
    conn.close()

    import csv
    buf = io.BytesIO()
    zf = zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED)
    # 1) 记录清单 CSV（Excel 可直接打开）
    buf_csv = io.StringIO()
    w = csv.writer(buf_csv)
    w.writerow(["记录ID", "条款", "计分条目", "维度", "参数", "原始分", "学期", "佐证文字说明", "佐证图片", "录入时间"])
    for r in rows:
        info = advisor.RULE_INDEX.get(r["rule_id"])
        imgs = json.loads(r.get("images") or "[]")
        detail = json.loads(r.get("detail") or "{}")
        if info:
            cat, rule = info
            w.writerow([r["id"], rule["article"], rule["title"], cat["name"],
                        json.dumps(detail, ensure_ascii=False),
                        round(advisor.score_record(rule, detail), 1),
                        r.get("term", ""), r.get("evidence", ""),
                        ";".join(imgs), r.get("created_at", "")])
    content = "\ufeff" + buf_csv.getvalue()     # BOM 让 Excel 正确识别中文
    zf.writestr("二课记录.csv", content)
    # 2) 佐证图片
    img_count = 0
    for r in rows:
        for fname in json.loads(r.get("images") or "[]"):
            path = os.path.join(EVIDENCE_DIR, fname)
            if _safe_image_name(fname) and os.path.isfile(path):
                zf.write(path, f"佐证图片/{fname}")
                img_count += 1
    zf.writestr("说明.txt", f"百花学习与生活顾问系统导出\n"
                            f"学号：{student['student_id']}  姓名：{student['name']}\n"
                            f"记录数：{len(rows)}  佐证图片数：{img_count}\n"
                            f"规则依据：{advisor.ERKE_RULES['source']}\n")
    zf.close()
    buf.seek(0)
    fname = f"二课记录_{student['student_id']}.zip"
    from urllib.parse import quote
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=erke_export.zip; filename*=UTF-8''{quote(fname)}"})


@app.get("/api/erke/rules")
def erke_rules(request: Request):
    """返回完整规则库（前端渲染录入表单与规则说明用）。"""
    current_student(request)
    return advisor.ERKE_RULES


@app.get("/api/erke")
def erke_list(request: Request):
    student = current_student(request)
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM erke_records2 WHERE student_id=? ORDER BY id DESC", (student["student_id"],))]
    conn.close()
    for r in rows:
        r["detail"] = json.loads(r.get("detail") or "{}")
        r["images"] = json.loads(r.get("images") or "[]")
        info = advisor.RULE_INDEX.get(r["rule_id"])
        if info:
            cat, rule = info
            r["rule_title"] = rule["title"]
            r["rule_article"] = rule["article"]
            r["category"] = cat["name"]
            r["score"] = round(advisor.score_record(rule, r["detail"]), 1)
    return {"records": rows, "summary": advisor.calc_erke_v2(rows)}


@app.post("/api/erke")
def erke_add(body: ErkeBody, request: Request):
    student = current_student(request)
    info = advisor.RULE_INDEX.get(body.rule_id)
    if not info:
        raise HTTPException(status_code=400, detail="未知的计分规则编号")
    cat, rule = info
    detail = body.detail or {}
    kind = rule["kind"]
    # 参数校验（按规则类型检查必填字段）
    if kind in ("times",) and "role_map" in rule and detail.get("role") not in rule["role_map"]:
        raise HTTPException(status_code=400, detail=f"参与身份须为：{'、'.join(rule['role_map'])}")
    if kind == "times" and int(detail.get("times", 0) or 0) < 1:
        raise HTTPException(status_code=400, detail="请填写参加次数（≥1）")
    if kind in ("hours_rate", "hours_threshold", "hours_extra") and float(detail.get("hours", -1)) < 0:
        raise HTTPException(status_code=400, detail="请填写有效时长")
    if kind == "base_minus" and int(detail.get("param", -1)) < 0:
        raise HTTPException(status_code=400, detail="请填写缺勤/违纪次数")
    if kind == "choice" and detail.get("option") not in [o["label"] for o in rule["options"]]:
        raise HTTPException(status_code=400, detail=f"请选择：{'、'.join(o['label'] for o in rule['options'])}")
    if kind == "level" and detail.get("level") not in rule["levels"]:
        raise HTTPException(status_code=400, detail=f"获奖级别须为：{'、'.join(rule['levels'])}")
    if kind == "matrix" and not detail.get("major"):
        if detail.get("level") not in rule["levels"]:
            raise HTTPException(status_code=400, detail=f"赛事级别须为：{'、'.join(rule['levels'])}")
        if detail.get("award") not in rule["awards"]:
            raise HTTPException(status_code=400, detail=f"奖项须为：{'、'.join(rule['awards'])}")
    # 佐证图片：只接受本服务生成且真实存在的文件名
    imgs = [n for n in (body.images or []) if _safe_image_name(n)
            and os.path.isfile(os.path.join(EVIDENCE_DIR, n))][:MAX_IMAGES_PER_RECORD]
    score = round(advisor.score_record(rule, detail), 1)
    conn = get_conn()
    conn.execute(
        "INSERT INTO erke_records2(student_id, rule_id, detail, term, evidence, images) VALUES (?,?,?,?,?,?)",
        (student["student_id"], body.rule_id, json.dumps(detail, ensure_ascii=False),
         body.term.strip(), body.evidence.strip(), json.dumps(imgs, ensure_ascii=False)))
    conn.commit()
    conn.close()
    return {"ok": True, "score": score, "rule": rule["title"], "images": len(imgs)}


@app.delete("/api/erke/{rec_id}")
def erke_delete(rec_id: int, request: Request):
    student = current_student(request)
    conn = get_conn()
    row = conn.execute("SELECT images FROM erke_records2 WHERE id=? AND student_id=?",
                       (rec_id, student["student_id"])).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="记录不存在")
    # 记录删除时一并清理其佐证图片文件
    for fname in json.loads(row["images"] or "[]"):
        if _safe_image_name(fname):
            try:
                os.remove(os.path.join(EVIDENCE_DIR, fname))
            except OSError:
                pass
    conn.execute("DELETE FROM erke_records2 WHERE id=?", (rec_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


# ---------------- 问题反馈（知识底座迭代闭环） ----------------
class FeedbackBody(BaseModel):
    question: str


@app.post("/api/feedback")
def feedback(body: FeedbackBody, request: Request):
    student = optional_student(request)
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="请填写问题内容")
    conn = get_conn()
    conn.execute("INSERT INTO feedback(student_id, question) VALUES (?,?)",
                 (student["student_id"], body.question.strip()))
    conn.commit()
    conn.close()
    return {"ok": True, "msg": "已收到反馈，知识库将据此迭代更新"}


# ---------------- FAQ 高频问题板块 ----------------
@app.get("/api/faq")
def faq(request: Request):
    optional_student(request)
    hot = ["校园卡丢了怎么办", "图书馆怎么预约座位", "选课什么时候开始，错过怎么办",
           "学校常用的信息系统和网址都有哪些", "教务管理系统的网址是什么，能干什么",
           "奖学金怎么评，什么时候申请", "校园常见的诈骗手段有哪些", "生病了在校内怎么就医报销"]
    items = [{"question": h, "answer": next(k["answer"] for k in advisor.KB if k["question"] == h)}
             for h in hot]
    return {"items": items}


# ---------------- 资讯推送（按月份规则匹配时间节点） ----------------
@app.get("/api/notice")
def notice(request: Request):
    optional_student(request)
    month = time.localtime().tm_mon
    rules = {
        (3, 4): "【学期初】选课补退选在第3-4周进行；二课积分第一季度录入截止前记得上传佐证材料。",
        (6, 12): "【考试周】图书馆延时开放；考场禁带手机，违纪将影响学位授予。祝考试顺利。",
        (9,): "【开学季】新生防骗提醒：任何索要验证码、要求屏幕共享或转账的“老师/客服”都是诈骗。",
    }
    text = "【日常】校园服务全年开放：一卡通挂失补办、成绩单自助打印入口可咨询生活顾问。"
    for months, t in rules.items():
        if month in months:
            text = t
            break
    return {"notice": text}


# ---------------- 静态页面 ----------------
WEB_DIR = os.path.join(BASE_DIR, "web")


@app.on_event("startup")
def _startup():
    init_db()


@app.get("/")
def index():
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


if __name__ == "__main__":
    import uvicorn
    from config import HOST, PORT
    # 探测本机局域网 IP，方便手机访问
    lan_ip = "127.0.0.1"
    try:
        import socket
        _s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        _s.settimeout(1)
        _s.connect(("8.8.8.8", 80))
        lan_ip = _s.getsockname()[0]
        _s.close()
    except Exception:
        pass
    print("=" * 52)
    print("百花学习与生活顾问系统 已启动")
    print(f"电脑访问:    http://127.0.0.1:{PORT}")
    print(f"手机访问:    http://{lan_ip}:{PORT}  （手机需与电脑连同一 WiFi）")
    print("演示账号:    学号 2024500001 / 密码 123456")
    print("大模型模式:  " + ("百炼 API" if llm_available() else "本地演示（未配置 API Key，功能照常）"))
    print("=" * 52)
    uvicorn.run(app, host=HOST, port=PORT)
