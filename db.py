"""
db.py — เชื่อม MySQL GD_Dashboard (10.8.1.88) เดียวกับ exception_report.py
credential override ได้ผ่าน env — อย่า commit ค่าจริงลง GitHub
"""
import os
import pymysql

MYSQL_CFG = dict(
    host=os.getenv("SM_MYSQL_HOST", "10.8.1.88"),
    port=int(os.getenv("SM_MYSQL_PORT", "3306")),
    user=os.getenv("SM_MYSQL_USER", "admin"),
    password=os.getenv("SM_MYSQL_PW", "CHANGE-ME-SET-IN-ENV"),
    database=os.getenv("SM_MYSQL_DB", "GD_Dashboard"),
    charset="utf8mb4",
    cursorclass=pymysql.cursors.DictCursor,
)


def query(sql: str, params=None):
    conn = pymysql.connect(**MYSQL_CFG)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()
    finally:
        conn.close()


def execute(sql: str, params=None):
    conn = pymysql.connect(**MYSQL_CFG)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
        conn.commit()
    finally:
        conn.close()
