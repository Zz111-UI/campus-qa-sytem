"""教务数据契约、授权同步入口及个人数据管理。

真实登录由管理员配置的学校适配器完成，不猜测接口、不绕过验证码。
接口与导入均不保存教务密码或原始网页；只保存选课需要的课程状态和课表。
"""
import importlib
import json
import os
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlparse
from pydantic import BaseModel, Field, SecretStr, ConfigDict
from fastapi import APIRouter, HTTPException, Request, Response
from database import get_conn
import security
import buct_sync
import demo_data

router = APIRouter(prefix='/api/education')


class CourseRecord(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    code: str = Field(default='', max_length=80)
    name: str = Field(min_length=1, max_length=160)
    credit: float = Field(ge=0, le=50)
    status: Literal['passed', 'enrolled', 'failed', 'pending', 'withdrawn', 'not_taken', 'completed', 'unknown']
    term: str = Field(default='', max_length=40)
    school_status: str = Field(default='', max_length=100)
    status_origin: Literal['school_explicit', 'school_code', 'student_review', 'student_import'] = 'student_import'


class Meeting(BaseModel):
    model_config = ConfigDict(extra='forbid')
    code: str = Field(default='', max_length=80)
    name: str = Field(min_length=1, max_length=160)
    section_id: str = Field(default='', max_length=80)
    day: int = Field(ge=1, le=7)
    start: int = Field(ge=1, le=20)
    end: int = Field(ge=1, le=20)
    weeks: list[int] = Field(min_length=1, max_length=40)
    room: str = Field(default='', max_length=100)
    campus: str = Field(default='', max_length=60)


class Snapshot(BaseModel):
    model_config = ConfigDict(extra='forbid')
    term: str = Field(pattern=r'^\d{4}-\d{4}-[123]$')
    records: list[CourseRecord] = Field(default_factory=list, max_length=2000)
    meetings: list[Meeting] = Field(default_factory=list, max_length=1000)
    offerings: list[Meeting] = Field(default_factory=list, max_length=2000)
    history_complete: bool = False
    timetable_complete: bool = False
    offerings_complete: bool = False


class ImportBody(BaseModel):
    snapshot: Snapshot
    consent: bool = False


class SyncBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    student_id: str = Field(min_length=6, max_length=20, pattern=r'^\d+$')
    password: SecretStr | None = Field(default=None, min_length=1, max_length=256)
    consent: bool = False
    challenge: str = Field(default='', max_length=128)
    term: str = Field(default='', max_length=20)
    mode: Literal['automatic', 'manual'] = 'automatic'


class ConfirmBody(BaseModel):
    snapshot: Snapshot
    consent: bool = False
    identity_confirmed: bool = False


class SchoolAction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['click', 'drag', 'text', 'key', 'scroll']
    revision: int = Field(ge=1)
    x: int = Field(default=0, ge=0, lt=1000)
    y: int = Field(default=0, ge=0, lt=700)
    end_x: int = Field(default=0, ge=0, lt=1000)
    end_y: int = Field(default=0, ge=0, lt=700)
    text: SecretStr = Field(default=SecretStr(''), max_length=256, repr=False)
    key: Literal['Enter', 'Tab', 'Backspace', 'Escape', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Space'] = 'Tab'
    delta: int = Field(default=0, ge=-700, le=700)


def current(request):
    token = request.headers.get('X-Session-Token') or request.cookies.get('bh_session', '')
    s = security.session_student(token)
    if not s:
        raise HTTPException(401, '请先登录百花账号')
    return s


def load_snapshot(sid, demo_enabled=False):
    if not sid:
        return None
    if demo_data.is_user(sid):
        if not demo_enabled:return None
        with get_conn() as conn:
            r=conn.execute('SELECT snapshot FROM private_education WHERE student_id=?',(sid,)).fetchone()
        if r:
            data=json.loads(r[0]);data['demo']=True
            return data
        return demo_data.snapshot(sid)
    with get_conn() as conn:
        r = conn.execute('SELECT snapshot FROM private_education WHERE student_id=?', (sid,)).fetchone()
        return json.loads(r[0]) if r else None


def validate_snapshot(snapshot):
    for m in [*snapshot.meetings, *snapshot.offerings]:
        if m.end < m.start or any(w < 1 or w > 40 for w in m.weeks):
            raise HTTPException(422, '课表节次或周次无效')
    a, b, _ = snapshot.term.split('-')
    if int(b) != int(a)+1:
        raise HTTPException(422, '学年必须是连续两年，如2026-2027-1')


def save_snapshot(sid, snapshot, source):
    validate_snapshot(snapshot)
    data = snapshot.model_dump()
    # 不接受客户端伪造的来源、同步时间或身份；原始成绩、密码、Cookie均不属于契约。
    data.update(source=source, synced_at=datetime.now(timezone.utc).isoformat())
    with get_conn() as conn:
        conn.execute('INSERT INTO private_education VALUES(?,?) ON CONFLICT(student_id) '
                     'DO UPDATE SET snapshot=excluded.snapshot', (sid, json.dumps(data, ensure_ascii=False)))
    return data


def connector_settings():
    return {'ready':demo_data.available(),'login_url':'','module':'','mode':'competition_demo','message':'竞赛演示数据库已就绪；请登录独立的模拟学业账号，数据全部虚构' if demo_data.available() else '演示数据库暂不可用，请联系管理员'}
    # 以下历史学校适配器配置不会执行，真实学校路由也被主服务停用。


def require_secure_connection(request):
    if request.url.scheme != 'https' and not (
            request.url.hostname in ('127.0.0.1', 'localhost', '::1')
            and request.client and request.client.host in ('127.0.0.1', '::1')):
        raise HTTPException(400, '教务接入需要HTTPS安全连接，请通过网站的HTTPS地址访问')


@router.get('/status')
def status(request: Request):
    s = current(request)
    config = connector_settings()
    data = load_snapshot(s['student_id'],s.get('demo_personalized',False))
    with buct_sync.jobs.lock:
        buct_sync.jobs.prune()
        active_job = next((key for key, job in reversed(list(buct_sync.jobs.jobs.items()))
                           if job['_owner'] == s['student_id'] and not job.get('_expired')
                           and job['status'] in {*buct_sync.ACTIVE, 'needs_review'}), None)
    return {'connector_ready': config['ready'], 'login_url': config['login_url'],
            'has_data': data is not None, 'term': data.get('term') if data else None,
            'synced_at': data.get('synced_at') if data else None,
            'source': data.get('source') if data else None,
            'record_count': len(data.get('records', [])) if data else 0,
            'privacy': '只使用虚构数据库，真实教务连接已停用。模拟登录输入不自动回填，只存预设虚构密码摘要。',
            'mode': config['mode'], 'message': config['message'], 'active_job': active_job}


@router.get('/data')
def data(request: Request):
    s=current(request)
    return {'snapshot': load_snapshot(s['student_id'],s.get('demo_personalized',False))}


@router.post('/import')
def import_data(body: ImportBody, request: Request):
    s = current(request)
    if not body.consent:
        raise HTTPException(400, '请先确认导入并保存课程状态和课表')
    for row in body.snapshot.records:
        row.status_origin = 'student_import'
    d = save_snapshot(s['student_id'], body.snapshot, 'student_import')
    return {'ok': True, 'snapshot': d, 'message': '已导入。学生导入数据尚未通过教务在线核验，请核对完整性。'}


@router.post('/sync')
def sync(body: SyncBody, request: Request):
    s = current(request)
    if not body.consent:
        raise HTTPException(400, '请先明确授权本次教务登录和数据读取')
    if body.student_id != s['student_id']:
        raise HTTPException(400, '教务学号须与当前百花账号学号一致')
    require_secure_connection(request)
    if not security.rate_limit('edu:'+s['student_id'], limit=3, window=300):
        raise HTTPException(429, '连接请求过于频繁，请稍后重试')
    config = connector_settings()
    if not config['ready']:
        raise HTTPException(503, config['message']+'；未向学校发送凭据')
    if config['mode'] == 'web_browser':
        if not re_term(body.term):
            raise HTTPException(422, '请填写要读取的学期，如2026-2027-1')
        if body.mode == 'automatic' and not body.password:
            raise HTTPException(400, '请填写密码，或选择在网页内完成学校验证')
        try:
            job_id = buct_sync.jobs.start(s['student_id'], body.term,
                body.password.get_secret_value() if body.mode == 'automatic' and body.password else None)
            return {'ok': True, 'job_id': job_id, 'message': '已启动教务连接；学校验证窗口将在本网页显示，无需安装软件。采集后核对确认才保存'}
        except ValueError as error:
            raise HTTPException(409, str(error)) from None
        finally:
            body.password = None
            body.challenge = ''
    if request.url.scheme != 'https' and request.url.hostname not in ('127.0.0.1', 'localhost'):
        raise HTTPException(400, '教务凭据只能通过HTTPS或本机连接提交')
    if not body.password:
        raise HTTPException(400, '该外部适配器需要填写学校密码')
    password = body.password.get_secret_value()
    try:
        adapter = importlib.import_module(config['module'])
        result = adapter.fetch_snapshot(student_id=body.student_id, password=password,
                                        challenge=body.challenge, login_url=config['login_url'])
        if str(result.get('student_id', '')) != body.student_id:
            raise ValueError('identity mismatch')
        snapshot = Snapshot.model_validate(result['snapshot'])
        stored = save_snapshot(s['student_id'], snapshot, 'official_connector')
        return {'ok': True, 'snapshot': stored, 'message': '课程状态与课表已同步'}
    except HTTPException:
        raise
    except Exception:
        # 不输出第三方异常，避免异常对象携带密码、Cookie或教务响应。
        raise HTTPException(502, '教务连接未完成：请检查登录、验证码及适配器配置。未覆盖原数据。') from None
    finally:
        password = None
        body.password = SecretStr('')
        body.challenge = ''


def re_term(term):
    import re
    return bool(re.fullmatch(r'\d{4}-\d{4}-[123]', term) and int(term[5:9]) == int(term[:4])+1)


@router.get('/jobs/{job_id}')
def job_status(job_id: str, request: Request):
    job = buct_sync.jobs.get(job_id, current(request)['student_id'])
    if not job:
        raise HTTPException(404, '采集任务不存在或已过期')
    return job


@router.post('/jobs/{job_id}/finish')
def finish_job(job_id: str, request: Request):
    if not buct_sync.jobs.finish(job_id, current(request)['student_id']):
        raise HTTPException(404, '采集任务不存在或已过期')
    return {'ok': True}


@router.get('/jobs/{job_id}/screen')
def school_screen(job_id: str, request: Request):
    owner = current(request)['student_id']
    require_secure_connection(request)
    if buct_sync.jobs.get(job_id, owner) is None:
        raise HTTPException(404, '采集任务不存在或已过期')
    frame = buct_sync.jobs.screen(job_id, owner)
    headers = {'Cache-Control': 'no-store, private', 'X-Content-Type-Options': 'nosniff'}
    if not frame:
        return Response(status_code=204, headers=headers)
    image, revision = frame
    return Response(image, media_type='image/jpeg', headers={**headers, 'X-School-Revision': str(revision)})


@router.post('/jobs/{job_id}/action')
def school_action(job_id: str, body: SchoolAction, request: Request):
    owner = current(request)['student_id']
    require_secure_connection(request)
    if buct_sync.jobs.get(job_id, owner) is None:
        raise HTTPException(404, '采集任务不存在或已过期')
    if not security.rate_limit('edu-action:'+owner, limit=180, window=60):
        raise HTTPException(429, '操作过于频繁，请稍后重试')
    command = body.model_dump(exclude={'text'})
    if body.kind == 'text':
        command['text'] = body.text.get_secret_value()
    try:
        buct_sync.jobs.enqueue(job_id, owner, command)
        return {'ok': True}
    except ValueError as error:
        raise HTTPException(409, str(error)) from None
    finally:
        body.text = SecretStr('')
        command.clear()


@router.post('/jobs/{job_id}/cancel')
def cancel_job(job_id: str, request: Request):
    if not buct_sync.jobs.cancel(job_id, current(request)['student_id']):
        raise HTTPException(404, '采集任务不存在或已过期')
    return {'ok': True, 'message': '采集已取消，未保存预览数据'}


@router.post('/jobs/{job_id}/confirm')
def confirm_job(job_id: str, body: ConfirmBody, request: Request):
    s = current(request)
    if not body.consent or not body.identity_confirmed:
        raise HTTPException(400, '请确认学校账号属于本人，并同意保存核对后的数据')
    with buct_sync.jobs.lock:
        job = buct_sync.jobs.get(job_id, s['student_id'])
        if not job:
            raise HTTPException(404, '采集任务不存在或已过期')
        if job['status'] != 'needs_review' or not job['result']:
            raise HTTPException(409, '任务尚未进入预览或已经处理')
        base = Snapshot.model_validate(job['result'])
        snapshot = body.snapshot
        if (snapshot.term != base.term or snapshot.meetings != base.meetings or snapshot.offerings != base.offerings
                or len(snapshot.records) != len(base.records) or snapshot.offerings_complete):
            raise HTTPException(400, '采集确认只允许核对课程状态和完整性；其他修改请使用学生导入')
        for edited, original in zip(snapshot.records, base.records):
            if any(getattr(edited, key) != getattr(original, key) for key in ('code', 'name', 'credit', 'term')):
                raise HTTPException(400, '课程身份或学分与采集预览不一致')
            edited.school_status = original.school_status
            edited.status_origin = original.status_origin if edited.status == original.status else 'student_review'
        saved = save_snapshot(s['student_id'], snapshot, 'school_page_reviewed')
        buct_sync.jobs.update(job_id, status='saved', result=None, message='核对后的课程状态和课表已保存')
        return {'ok': True, 'snapshot': saved, 'message': '已保存学校页面采集并经本人核对的数据；人工修改状态已单独标记'}


@router.delete('/data')
def clear(request: Request):
    s = current(request)
    with buct_sync.jobs.lock:
        for key, job in list(buct_sync.jobs.jobs.items()):
            if job['_owner'] == s['student_id']:
                buct_sync.jobs.discard(key, s['student_id'])
    with get_conn() as conn:
        conn.execute('DELETE FROM demo_access WHERE token_hash=?',(__import__('hashlib').sha256(demo_data.token(request).encode()).hexdigest(),))
        conn.execute('DELETE FROM private_education WHERE student_id=?', (s['student_id'],))
    return {'ok': True, 'message': '已从百花清除课程状态与课表，未修改教务系统'}


def clashes(meetings):
    out = []
    for i, a in enumerate(meetings):
        for b in meetings[i+1:]:
            if (a['day'] == b['day'] and max(a['start'], b['start']) <= min(a['end'], b['end'])
                    and set(a['weeks']) & set(b['weeks'])
                    and (a.get('code'), a.get('name'), a.get('section_id')) != (b.get('code'), b.get('name'), b.get('section_id'))):
                out.append({'a': a['name'], 'b': b['name'], 'day': a['day'],
                            'weeks': sorted(set(a['weeks']) & set(b['weeks']))})
    return out


@router.get('/timetable')
def timetable(request: Request, week: int = 1):
    if not 1 <= week <= 40:
        raise HTTPException(422, '周次须为1—40')
    s=current(request)
    snapshot = load_snapshot(s['student_id'],s.get('demo_personalized',False))
    if not snapshot:
        return {'meetings': [], 'has_data': False, 'message': '请先同步或导入教务课表'}
    return {'has_data': True, 'term': snapshot['term'], 'week': week,
            'meetings': [m for m in snapshot['meetings'] if week in m['weeks']],
            'conflicts': clashes(snapshot['meetings']), 'source': snapshot['source'],
            'complete': snapshot['timetable_complete'], 'synced_at': snapshot['synced_at']}
