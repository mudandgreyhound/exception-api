# Exception / Sale Monitor API — Deploy Notes

Backend (FastAPI) + frontend (static HTML) รวมอยู่ใน service เดียวกัน รันบน
เครื่อง 10.8.1.88 เอง (LAN เดียวกับ MySQL) — ไม่ได้ host บน GitHub Pages หรือ
cloud ใดๆ เพื่อไม่ให้ DB ต้องเปิดออกอินเทอร์เน็ต

```
เบราว์เซอร์ → https://exception.mobile1234.site (Cloudflare Tunnel)
                     │
              sale-monitor-api.service (uvicorn :8602, /opt/exception_api)
                ├── /api/*        → FastAPI (login ผ่าน sm_users, JWT)
                └── /  , /*.html  → static/ (index, login, exception, petty-cash, transfer-in)
                     │
              MySQL GD_Dashboard (10.8.1.88:3306, LAN เท่านั้น)
```

## ครั้งแรก (setup บน server)

```bash
cd /opt/exception_api
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

cp .env.example .env
nano .env   # ใส่ SM_MYSQL_PW จริง + SM_JWT_SECRET สุ่มค่ายาวๆ (อย่าใช้ default)

sudo cp sale-monitor-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sale-monitor-api
```

seed user (ครั้งแรก / เพิ่มกลุ่มใหม่):
```bash
set -a && source .env && set +a
export MSSQL_PW="..." MYSQL_PW="$SM_MYSQL_PW"
./venv/bin/python seed_sm_users.py --dry-run
./venv/bin/python seed_sm_users.py
```

## Deploy รอบถัดไป (หลัง push ขึ้น GitHub แล้ว)
```bash
cd /opt/exception_api && ./deploy.sh
```
(`git pull` + `pip install` + `systemctl restart sale-monitor-api`)

## เข้าใช้งาน
`https://exception.mobile1234.site/` → login.html → login ด้วย username/password
จาก `sm_users` (JWT เก็บใน localStorage ฝั่ง browser, หมดอายุตาม `SM_JWT_EXPIRE_HOURS`)

## ความปลอดภัย
- `.env` **ห้าม commit** (อยู่ใน `.gitignore` แล้ว) — DB password และ JWT secret จริง
  อยู่ในนี้เท่านั้น ค่า default ในโค้ด (`db.py`, `auth.py`, `seed_sm_users.py`) เป็นแค่
  placeholder ที่ต้อง override ผ่าน env เสมอ
- `main.py` mount `static/` เป็น root — ไฟล์ `.py`/`.env`/`requirements.txt` ที่อยู่นอก
  `static/` จะไม่ถูก serve ผ่าน HTTP (ทดสอบแล้วว่าได้ 404)
- CORS จำกัดเฉพาะ `SM_ALLOW_ORIGINS` ใน `.env` (ค่าเริ่มต้น = โดเมนจริงของแอปเอง)
- repo เป็น **private** — ต้อง login GitHub ถึงจะเห็นซอร์สโค้ด
