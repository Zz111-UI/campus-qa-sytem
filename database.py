# -*- coding: utf-8 -*-
"""SQLite 轻量数据层：二课记录、问题反馈。自动建表，零配置。"""
import json
import os
import sqlite3

from config import DATA_DIR, DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS erke_records2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            rule_id TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '{}',
            term TEXT DEFAULT '',
            evidence TEXT DEFAULT '',
            images TEXT DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT,
            question TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        """
    )
    # 旧库补列：images 字段（佐证图片文件名列表 JSON）
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(erke_records2)").fetchall()]
    if "images" not in cols:
        conn.execute("ALTER TABLE erke_records2 ADD COLUMN images TEXT DEFAULT '[]'")
    # 首次运行给张三塞两条示例记录（按官方规则库），方便演示
    cur = conn.execute("SELECT COUNT(*) AS c FROM erke_records2")
    if cur.fetchone()["c"] == 0:
        students_file = os.path.join(DATA_DIR, "students.json")
        demo_id = ""
        if os.path.exists(students_file):
            with open(students_file, encoding="utf-8") as f:
                students = json.load(f)
            if students:
                demo_id = students[0]["student_id"]
        if demo_id:
            conn.execute(
                "INSERT INTO erke_records2(student_id, rule_id, detail, term, evidence) VALUES (?,?,?,?,?)",
                (demo_id, "m2", json.dumps({"times": 3}, ensure_ascii=False), "2025-2026秋", "活动签到截图"))
            conn.execute(
                "INSERT INTO erke_records2(student_id, rule_id, detail, term, evidence) VALUES (?,?,?,?,?)",
                (demo_id, "l2", json.dumps({"hours": 12}), "2025-2026秋", "志愿北京时长记录"))
            conn.execute(
                "INSERT INTO erke_records2(student_id, rule_id, detail, term, evidence) VALUES (?,?,?,?,?)",
                (demo_id, "s5", json.dumps({"level": "校级", "award": "二等奖", "group": False}),
                 "2025-2026秋", "获奖证书照片"))
    conn.commit()
    conn.close()
