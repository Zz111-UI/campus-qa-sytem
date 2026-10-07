"""账号与会话存储。密码只保存带随机盐的PBKDF2摘要。"""
import hashlib
import os
import hmac
import json
import secrets
import time
import threading
from database import get_conn
from config import DATA_DIR
from pathlib import Path

_initialization_lock = threading.Lock()
_initialized = False


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex()
    return f'pbkdf2_sha256$600000${salt}${digest}'


def verify_password(password, stored):
    try:
        kind, rounds, salt, expected = stored.split('$')
        if kind != 'pbkdf2_sha256':
            return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(rounds)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def ensure_accounts():
    global _initialized
    if _initialized:
        return
    with _initialization_lock:
        if not _initialized:
            _initialize_accounts()
            _initialized = True


def _initialize_accounts():
    with get_conn() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS accounts(student_id TEXT PRIMARY KEY, phone TEXT UNIQUE NOT NULL,
            profile TEXT NOT NULL, password_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, student_id TEXT NOT NULL,
            expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS private_education(student_id TEXT PRIMARY KEY, snapshot TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS image_owners(fname TEXT PRIMARY KEY, student_id TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS auth_attempts(key TEXT PRIMARY KEY, count INTEGER NOT NULL,
            reset_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS demo_access(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL);
        ''')
        seed = Path(DATA_DIR) / 'students.json'
        if seed.exists() and os.getenv('BAIHUA_LOAD_SEED_ACCOUNTS', '0') == '1':
            sanitized = []
            for student in json.loads(seed.read_text(encoding='utf-8')):
                s = dict(student)
                old = s.pop('password', None)
                digest = s.pop('password_hash', '') or (hash_password(old) if old else '')
                conn.execute('INSERT OR IGNORE INTO accounts VALUES(?,?,?,?)',
                             (s['student_id'], s['phone'], json.dumps(s, ensure_ascii=False), digest))
                sanitized.append({**s, 'password_hash': digest})
            # 首次迁移时清除旧JSON中的明文密码，保留摘要与画像作为迁移备份。
            if any('password' in item for item in json.loads(seed.read_text(encoding='utf-8'))):
                temp = seed.with_suffix('.migration.tmp')
                temp.write_text(json.dumps(sanitized, ensure_ascii=False, indent=2), encoding='utf-8')
                os.replace(temp, seed)
        # 旧图片只向其记录所属账号开放；无归属的文件默认不可读取。
        try:
            for r in conn.execute('SELECT student_id,images FROM erke_records2'):
                for name in json.loads(r['images'] or '[]'):
                    conn.execute('INSERT OR IGNORE INTO image_owners VALUES(?,?)', (name, r['student_id']))
        except Exception:
            pass


def load_accounts():
    ensure_accounts()
    with get_conn() as conn:
        return [{**json.loads(r['profile']), 'password_hash': r['password_hash']}
                for r in conn.execute('SELECT * FROM accounts')]


def public_profile(student):
    return {k: v for k, v in student.items() if k not in ('password', 'password_hash')}


def add_account(student, password):
    with get_conn() as conn:
        conn.execute('INSERT INTO accounts VALUES(?,?,?,?)',
                     (student['student_id'], student['phone'], json.dumps(student, ensure_ascii=False), hash_password(password)))


def update_account(sid, fields):
    with get_conn() as conn:
        conn.execute('BEGIN IMMEDIATE')
        r = conn.execute('SELECT profile FROM accounts WHERE student_id=?', (sid,)).fetchone()
        if not r:
            raise ValueError('账号不存在')
        s = json.loads(r[0])
        s.update(fields)
        conn.execute('UPDATE accounts SET phone=?,profile=? WHERE student_id=?',
                     (s['phone'], json.dumps(s, ensure_ascii=False), sid))
        return s


def create_session(sid, ttl=43200):
    token = secrets.token_urlsafe(32)
    with get_conn() as conn:
        conn.execute('DELETE FROM sessions WHERE expires<?', (time.time(),))
        conn.execute('INSERT INTO sessions VALUES(?,?,?)',
                     (hashlib.sha256(token.encode()).hexdigest(), sid, time.time()+ttl))
    return token


def session_student(token):
    if not token:
        return None
    with get_conn() as conn:
        r = conn.execute('SELECT a.profile FROM sessions s JOIN accounts a ON a.student_id=s.student_id '
                         'WHERE s.token_hash=? AND s.expires>?',
                         (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
        if not r:
            return None
        profile=json.loads(r[0])
        profile['demo_personalized']=conn.execute('SELECT 1 FROM demo_access WHERE token_hash=? AND user_id=?',
            (hashlib.sha256(token.encode()).hexdigest(),profile['student_id'])).fetchone() is not None
        return profile


def remove_session(token):
    with get_conn() as conn:
        conn.execute('DELETE FROM demo_access WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),))
        conn.execute('DELETE FROM sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),))


def rate_limit(key, limit=10, window=600):
    now = time.time()
    with get_conn() as conn:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('DELETE FROM auth_attempts WHERE reset_at<?', (now,))
        r = conn.execute('SELECT count FROM auth_attempts WHERE key=?', (key,)).fetchone()
        if r and r[0] >= limit:
            return False
        conn.execute('INSERT INTO auth_attempts VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1',
                     (key, now+window))
    return True
