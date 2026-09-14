#!/usr/bin/env python3
"""
seed_sm_users.py
─────────────────────────────────────────────────────────────────────────────
ดึง "user กลุ่ม Exclusive (EX001)" จาก CM POS (MSSQL · GD_MASTER) → hash รหัสผ่าน →
upsert เข้า sm_users (MySQL · ระบบ Sale Monitor) เพื่อให้กลุ่มนี้ login เข้า Sale Monitor ได้

Concept เดียวกับ seed_checker_users.py:
  - source user : tbuser  WHERE usgCode = 'EX001' AND usrActive = 1
  - username    : usrCode ตรงๆ (ไม่ผูกสาขา/ครัว เพราะ Sale Monitor เห็นข้อมูลทุกสาขา
                  ต่างจาก Checker ที่ต้อง join tbusershop เพื่อผูกครัว)
  - password    : hash รหัสเดิมจาก CM POS (usrPassword) ด้วย hash_pw เดียวกับ Checker
                  → login ด้วยรหัสเดิมของ CM POS ได้เลย
  - role        : viewer (ดูอย่างเดียว)

รัน:
  python seed_sm_users.py --dry-run     # preview ไม่เขียนจริง (ทำอันนี้ก่อนเสมอ)
  python seed_sm_users.py               # เขียนจริง (upsert)

ตั้ง credential ผ่าน env ก่อนรัน (อย่า hardcode รหัสในไฟล์ที่ commit):
  export MSSQL_HOST=10.8.1.51  MSSQL_USER=sa    MSSQL_PW=***
  export MYSQL_HOST=10.8.1.88  MYSQL_USER=admin MYSQL_PW=*** SM_DB=GD_Dashboard
  export USG_GROUP=EX001        # เปลี่ยนกลุ่มได้ถ้าต้องการ seed กลุ่มอื่นด้วย pattern เดียวกัน
"""
import os, sys, hashlib, secrets
import pymssql, pymysql

# ─────────────────────────── CONFIG ───────────────────────────
MSSQL = dict(
    server   = os.getenv("MSSQL_HOST", "10.8.1.51"),
    user     = os.getenv("MSSQL_USER", "sa"),
    password = os.getenv("MSSQL_PW", "CHANGE-ME-SET-IN-ENV"),
    database = os.getenv("MSSQL_DB", "GD_MASTER"),
    charset  = "CP874",   # CM POS เก็บภาษาไทยเป็น TIS-620/CP874 (กัน full_name เพี้ยน)
)
MYSQL = dict(
    host     = os.getenv("MYSQL_HOST", "10.8.1.88"),
    port     = int(os.getenv("MYSQL_PORT", "3306")),
    user     = os.getenv("MYSQL_USER", "admin"),
    password = os.getenv("MYSQL_PW", "CHANGE-ME-SET-IN-ENV"),
    database = os.getenv("SM_DB", "GD_Dashboard"),   # database ที่มี table sm_users
    charset  = "utf8mb4",
    cursorclass = pymysql.cursors.DictCursor,
)

USG_GROUP  = os.getenv("USG_GROUP", "EX001")   # กลุ่ม Exclusive
DEFAULT_PW = "changeme"                        # ใช้เมื่อ usrPassword ว่าง/NULL
ROLE       = "viewer"

# ───────────────── hash (เหมือน Checker api.py เป๊ะ — ห้ามแก้ ───────────────────
#                    เพื่อให้ login ด้วยรหัสเดิมจาก CM POS ได้)
def hash_pw(pw, salt=None, iters=200000):
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), iters)
    return f"pbkdf2$sha256${iters}${salt}${dk.hex()}"

# ─────────────────────────── EXTRACT (MSSQL) ───────────────────────────
def fetch_group_users():
    """ดึง (usrCode, usrName1, usrPassword) ของ user กลุ่ม Exclusive (usgCode=EX001)"""
    conn = pymssql.connect(**MSSQL)
    try:
        cur = conn.cursor(as_dict=True)
        # EX001 ทั้ง 5 คนถูก set usrActive=0 ใน CM POS แต่ business ต้องการให้ login
        # Sale Monitor ได้อยู่ดี เลย seed โดยไม่กรอง usrActive (ตัดสินใจ 2026-09-14)
        sql = """
            SELECT u.usrCode, u.usrName1, u.usrPassword
            FROM tbuser u
            WHERE u.usgCode = %s
            ORDER BY u.usrCode
        """
        cur.execute(sql, (USG_GROUP,))
        return cur.fetchall()
    finally:
        conn.close()

# ─────────────────────────── TRANSFORM ───────────────────────────
def build_records(rows, do_hash=True):
    seen, records, skipped = set(), [], 0
    for r in rows:
        usr  = (r.get("usrCode")  or "").strip()
        name = (r.get("usrName1") or usr).strip()
        pw   = (r.get("usrPassword") or "").strip() or DEFAULT_PW
        if not usr:
            skipped += 1
            continue
        username = usr                       # unique ต่อ user (ไม่ผูกสาขา/ครัว)
        if username in seen:                 # กัน duplicate จาก source
            continue
        seen.add(username)
        pwhash = hash_pw(pw) if do_hash else "(dry-run)"   # ข้าม hash ตอน preview
        records.append((username, pwhash, name, ROLE))
    return records, skipped

# ─────────────────────────── LOAD (MySQL upsert) ───────────────────────────
def upsert(records):
    conn = pymysql.connect(**MYSQL)
    try:
        with conn.cursor() as cur:
            cur.executemany("""
                INSERT INTO sm_users
                    (username, password, full_name, role, active)
                VALUES (%s, %s, %s, %s, 1)
                ON DUPLICATE KEY UPDATE
                    password  = VALUES(password),
                    full_name = VALUES(full_name),
                    role      = VALUES(role),
                    active    = 1
            """, records)
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()

# ─────────────────────────── MAIN ───────────────────────────
def main(dry=False):
    rows = fetch_group_users()
    print(f"► ดึงจาก CM POS กลุ่ม {USG_GROUP}: {len(rows)} รายการ")
    records, skipped = build_records(rows, do_hash=not dry)
    print(f"► เตรียม seed: {len(records)} account" + (f" (ข้าม {skipped} แถวไม่มี usrCode)" if skipped else ""))
    if not records:
        print("ไม่มีข้อมูลให้ seed — ตรวจ usgCode หรือ mapping ของกลุ่ม Exclusive")
        return
    if len(records) > 50:
        print(f"⚠️  จำนวน {len(records)} account เยอะผิดปกติสำหรับกลุ่ม Exclusive")
        print("    แนะนำตรวจ usgCode ให้แน่ใจก่อนเขียนจริง (--dry-run ก่อนเสมอ)")

    if dry:
        print("\n── DRY RUN · ไม่เขียนจริง ──")
        print(f"  {'username':16} {'role':8} full_name")
        for username, _, name, role in records[:40]:
            print(f"  {username:16} {role:8} {name}")
        if len(records) > 40:
            print(f"  ... และอีก {len(records)-40} account")
        print(f"\nรวม {len(records)} account (รหัสผ่าน = รหัสเดิมจาก CM POS, hash แล้ว)")
        return

    n = upsert(records)
    print(f"✅ upsert เข้า sm_users สำเร็จ (affected rows: {n})")

if __name__ == "__main__":
    main(dry="--dry-run" in sys.argv)
