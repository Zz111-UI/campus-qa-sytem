"""Fictional competition accounts and opt-in personal data. No school connection."""
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, SecretStr, ConfigDict
from config import DATA_DIR
from database import get_conn
import security

router=APIRouter(prefix='/api/demo')
DB=Path(os.getenv('BAIHUA_DEMO_DATABASE', str(Path(DATA_DIR)/'demo.sqlite3')))

def connect():
    return sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True)

def available():
    return DB.is_file()

def is_user(sid):
    if not available():return False
    with connect() as c:
        return c.execute('SELECT 1 FROM students WHERE user_id=?',(sid,)).fetchone() is not None

def initialize():
    with get_conn() as c:
        c.execute('CREATE TABLE IF NOT EXISTS demo_access(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL)')
    if not available():return
    with connect() as source, get_conn() as target:
        for uid,name,college,major,year,campus,goal,interests,username,digest in source.execute('SELECT s.user_id,s.name,s.college,s.major,s.entry_year,s.campus,p.goal,p.interests,a.username,a.password_hash FROM students s JOIN preferences p USING(user_id) JOIN website_accounts a USING(user_id) WHERE a.status="active"'):
            profile=dict(student_id=uid,user_id=uid,name=name,college=college,major=major,grade=year,campus=campus,goal=goal,preference='、'.join(json.loads(interests)),phone=username,demo=True)
            target.execute('INSERT OR IGNORE INTO accounts VALUES(?,?,?,?)',(uid,username,json.dumps(profile,ensure_ascii=False),digest))

def token(request):
    return request.headers.get('X-Session-Token') or request.cookies.get('bh_session','')

def active(raw_token,sid):
    with get_conn() as c:
        return c.execute('SELECT 1 FROM demo_access WHERE token_hash=? AND user_id=?',(hashlib.sha256(raw_token.encode()).hexdigest(),sid)).fetchone() is not None

def current(request,require_active=False):
    raw=token(request);s=security.session_student(raw)
    if not s:raise HTTPException(401,'请先登录百花网站')
    if not is_user(s['student_id']):raise HTTPException(403,'当前网站账号尚未绑定模拟学业数据，请使用演示账号')
    if require_active and not active(raw,s['student_id']):raise HTTPException(403,'请在个性化服务窗口登录对应的模拟学业账号')
    return s

def snapshot(sid):
    with connect() as c:
        row=c.execute('SELECT snapshot_json FROM demo_snapshots WHERE user_id=?',(sid,)).fetchone()
        data=json.loads(row[0])
        offerings=[]
        for code,name,section,day,start,end,weeks,room,campus in c.execute('SELECT c.code,c.name,o.section_id,m.weekday,m.start_period,m.end_period,m.weeks_json,m.room,m.campus FROM offerings o JOIN courses c USING(course_id) JOIN offering_meetings m USING(offering_id) WHERE o.eligible_major=(SELECT major FROM students WHERE user_id=?) AND o.offering_id NOT LIKE "PERSONAL-%"',(sid,)):
            offerings.append(dict(code=code,name=name,section_id=section,day=day,start=start,end=end,weeks=json.loads(weeks),room=room,campus=campus))
        data.update(offerings=offerings,source='competition_demo',synced_at='2026-10-04T00:00:00Z',demo=True)
        return data

def grades(sid):
    with connect() as c:
        c.row_factory=sqlite3.Row
        records=[dict(r) for r in c.execute('SELECT a.term,a.attempt_no,a.exam_type,a.status,a.score,a.grade_label,a.grade_point,c.code,c.name,c.credits,c.gpa_included FROM course_attempts a JOIN courses c USING(course_id) WHERE a.user_id=? ORDER BY a.term,c.name,a.attempt_no',(sid,))]
        gpa=[dict(r) for r in c.execute('SELECT term,scope,weighted_points,included_credits,gpa FROM gpa_summaries WHERE user_id=?',(sid,))]
        return {'records':records,'gpa':gpa,'rule':'按北化公开换算表演示，最高4.33；正考与最高成绩分开统计。所有成绩均为虚构。'}

def erke_records(sid):
    with connect() as c:
        c.row_factory=sqlite3.Row
        return [dict(id=-r['record_id'],rule_id=r['rule_id'],detail=json.loads(r['detail_json']),term=r['term'],evidence=r['name']+'（'+{'approved':'演示已审核','pending':'演示待审核','rejected':'演示未通过'}[r['approval_status']]+'）',images=[],demo=True,approval_status=r['approval_status'],recognition_key=r['recognition_key']) for r in c.execute('SELECT r.*,a.term,a.name,a.approval_status,a.recognition_key FROM erke_records r JOIN erke_activities a USING(activity_id) WHERE a.user_id=? ORDER BY r.record_id',(sid,))]

def erke_summary(records):
    import advisor
    term='2026-2027-1'
    grouped={}
    for r in records:
        if r.get('approval_status','approved')!='approved' or r.get('term')!=term:continue
        grouped.setdefault(r['rule_id'],[]).append(r)
    raw={}
    for rid,rows in grouped.items():
        if rid not in advisor.RULE_INDEX:continue
        _,rule=advisor.RULE_INDEX[rid]
        if rule['kind']=='hours_threshold':
            hours=sum(float(r['detail'].get('hours',0)) for r in rows)
            raw[rid]=rule['score'] if hours>=rule['threshold'] else 0
            extra={'l1':'l10','l2':'l9'}.get(rid)
            if extra:raw[extra]=max(0,hours-rule['threshold'])*0.5
            continue
        if rule['kind']=='base_minus':
            raw[rid]=max(0,rule['base']-rule['deduct']*sum(int(r['detail'].get('param',0)) for r in rows));continue
        if rule['kind']=='hours_extra' and {'l9':'l2','l10':'l1'}.get(rid) in grouped:continue
        values={}
        for r in rows:
            value=advisor.score_record(rule,r['detail'])
            key=r.get('recognition_key',str(r['id']))
            values[key]=max(values.get(key,float('-inf')),value)
        raw[rid]=max(values.values()) if rid in ('m1','m5','m6','p3','p4','p6','l5','l6','l7','l8') else sum(values.values())
    cats=[]
    for cat in advisor.ERKE_RULES['categories']:
        totals={'base':0,'ext':0};rules=[]
        for rule in cat['items']:
            rid=rule['id']
            if rid not in raw:continue
            score=min(raw[rid],rule['cap']);totals[rule['sec']]+=score
            rules.append(dict(rule_id=rid,title=rule['title'],article=rule['article'],sec=rule['sec'],raw=raw[rid],score=score,cap=rule['cap'],count=len(grouped.get(rid,[]))))
        base=max(0,min(totals['base'],cat['base_cap']));ext=max(0,min(totals['ext'],cat['ext_cap']))
        cats.append(dict(id=cat['id'],name=cat['name'],full=cat['full'],base_cap=cat['base_cap'],ext_cap=cat['ext_cap'],base=base,ext=ext,score=min(cat['full'],base+ext),rules=rules))
    return dict(total=sum(c['score'] for c in cats),total_full=600,categories=cats,source='项目已有规则库（竞赛演示）',note=term+'学期；所有活动均为虚构，待审核不计分。同一作品最高奖、志愿时长合并后计分。其他学期录入的记录单独保留。')

class DemoLogin(BaseModel):
    model_config=ConfigDict(extra='forbid')
    username:str=Field(min_length=1,max_length=50,repr=False)
    password:SecretStr=Field(min_length=1,max_length=256,repr=False)
    consent:bool=False

@router.post('/login')
def login(body:DemoLogin,request:Request):
    try:
        s=current(request)
        if not body.consent:raise HTTPException(400,'请确认使用全部虚构的竞赛演示学业数据')
        if request.url.scheme!='https' and request.url.hostname not in ('127.0.0.1','localhost','::1'):raise HTTPException(400,'模拟登录需使用HTTPS')
        if not security.rate_limit('demo-login:'+s['student_id'],limit=10,window=300):raise HTTPException(429,'尝试过于频繁，请稍后再试')
        with connect() as c:
            row=c.execute('SELECT user_id,password_hash FROM personal_service_accounts WHERE username=? AND status="active"',(body.username.strip(),)).fetchone()
        if not row or row[0]!=s['student_id'] or not security.verify_password(body.password.get_secret_value(),row[1]):raise HTTPException(403,'模拟账号或密码错误，或未绑定当前网站用户')
        with get_conn() as c:
            c.execute('INSERT OR REPLACE INTO demo_access VALUES(?,?)',(hashlib.sha256(token(request).encode()).hexdigest(),s['student_id']))
        return {'ok':True,'message':'已启用本人的竞赛演示学业数据；全部信息均为虚构'}
    finally:
        body.username='';body.password=SecretStr('')

@router.get('/data')
def data(request:Request):
    s=current(request,True)
    return {'demo':True,'user_id':s['student_id'],'snapshot':snapshot(s['student_id']),'grades':grades(s['student_id'])}

@router.post('/logout')
def logout(request:Request):
    current(request)
    with get_conn() as c:c.execute('DELETE FROM demo_access WHERE token_hash=?',(hashlib.sha256(token(request).encode()).hexdigest(),))
    return {'ok':True,'message':'已退出个性化服务，网站登录仍保留'}
