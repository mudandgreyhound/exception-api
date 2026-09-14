"""
main.py — Sale Monitor API (FastAPI)
  POST /api/login                     → {access_token, token_type, full_name}
  GET  /api/sale-monitor/dm-options    (auth) → {dm: [...]}
  GET  /api/sale-monitor/summary       (auth) → payload เดียวครบทุกส่วนของหน้า Sale Monitor
  GET  /api/health

รัน dev:   uvicorn main:app --reload --port 8602
รัน prod:  uvicorn main:app --host 0.0.0.0 --port 8602   (แนะนำผูกกับ systemd service)
"""
import os
from datetime import date, timedelta, datetime as dtm

import jwt
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from db import query, execute
from auth import verify_pw, create_token, decode_token
import sm_queries as smq
import tr_queries as trq
import pc_queries as pcq
import ex_queries as exq

HERE = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="Sale Monitor API")

ALLOW_ORIGINS = os.getenv(
    "SM_ALLOW_ORIGINS", "https://exception.mobile1234.site"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOW_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()


class LoginBody(BaseModel):
    username: str
    password: str


def get_current_user(cred: HTTPAuthorizationCredentials = Depends(security)) -> str:
    try:
        payload = decode_token(cred.credentials)
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token หมดอายุ กรุณา login ใหม่")
    except Exception:
        raise HTTPException(401, "Token ไม่ถูกต้อง")


@app.post("/api/login")
def login(body: LoginBody):
    rows = query(
        "SELECT username, password, full_name, active FROM sm_users WHERE username=%s",
        (body.username,),
    )
    if not rows or not rows[0]["active"]:
        raise HTTPException(401, "Username หรือ Password ไม่ถูกต้อง")
    user = rows[0]
    if not verify_pw(body.password, user["password"]):
        raise HTTPException(401, "Username หรือ Password ไม่ถูกต้อง")

    execute("UPDATE sm_users SET last_login_at=NOW() WHERE username=%s", (user["username"],))
    token = create_token(user["username"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "full_name": user["full_name"] or user["username"],
    }


@app.get("/api/sale-monitor/dm-options")
def dm_options(biz_date: str = Query(...), user: str = Depends(get_current_user)):
    return {"dm": smq.dm_options(biz_date)}


@app.get("/api/sale-monitor/summary")
def summary(
    biz_date: str = Query(...),
    dm: str = Query(""),
    top_n: int = Query(15),
    user: str = Depends(get_current_user),
):
    today_str = biz_date
    yday_str = (date.fromisoformat(today_str) - timedelta(days=1)).isoformat()
    is_today = today_str == date.today().isoformat()
    now_h = dtm.now().hour if is_today else 23

    tot = smq.totals(today_str, dm)
    tot_y = smq.totals(yday_str, dm)
    hourt = smq.hourly(today_str, dm)
    shops_rows = smq.shops(today_str, yday_str, dm)
    net_y_same = smq.ytd_same_time(yday_str, now_h, dm)

    def g(d, k):
        v = d.get(k)
        return float(v) if v is not None else 0.0

    net = g(tot, "net_sales")
    disc = g(tot, "discount")
    gross = g(tot, "gross_sales")
    bills = int(g(tot, "bills"))
    coupons = int(g(tot, "coupons"))
    nshop = int(g(tot, "shops"))
    net_y_full = g(tot_y, "net_sales")
    snap = tot.get("snap")
    snap_str = str(snap)[11:16] if snap else None

    avg_bill = net / bills if bills else 0
    disc_pct = disc / net * 100 if net else 0
    disc_per_bill = disc / bills if bills else 0
    pace_pct = (net - net_y_same) / net_y_same * 100 if net_y_same else 0

    hmap_net = {int(r["hour_slot"]): float(r["net_sales"] or 0) for r in hourt}
    hmap_disc = {int(r["hour_slot"]): float(r["discount"] or 0) for r in hourt}
    hourly_out = [
        {"hour": h, "net_sales": hmap_net.get(h, 0), "discount": hmap_disc.get(h, 0)}
        for h in range(6, 24)
    ]

    shops_list = []
    for r in shops_rows:
        today_v = float(r.get("today") or 0)
        yday_v = float(r.get("yday") or 0)
        b = float(r.get("bills") or 0)
        shops_list.append({
            "shop_code": r["shop_code"],
            "shop_name": r["shop_name"],
            "dm": r["dm"],
            "today": today_v,
            "yday": yday_v,
            "bills": b,
            "avg": today_v / b if b else 0,
            "diff_pct": (today_v - yday_v) / yday_v * 100 if yday_v else None,
            "last_bill": str(r.get("last_bill")) if r.get("last_bill") else None,
        })
    shops_list.sort(key=lambda x: x["today"], reverse=True)

    tender_rows = smq.tender(today_str)
    pay_groups, promo = smq.pay_group(tender_rows)

    dm_performance = [] if dm else smq.dm_perf(today_str, yday_str, now_h)

    return {
        "date": today_str,
        "is_today": is_today,
        "snapshot_time": snap_str,
        "totals": {
            "gross": gross, "discount": disc, "net": net,
            "bills": bills, "coupons": coupons, "shops": nshop,
            "avg_bill": avg_bill, "disc_pct": disc_pct, "disc_per_bill": disc_per_bill,
        },
        "compare": {
            "net_yesterday_full": net_y_full,
            "net_yesterday_same_time": net_y_same,
            "pace_pct": pace_pct,
        },
        "hourly": hourly_out,
        "top_shops": shops_list[:top_n],
        "shops_ranking": shops_list,
        "payment": {"groups": pay_groups, "total": sum(pay_groups.values()), "promo": promo[:15]},
        "dm_performance": dm_performance,
    }


@app.get("/api/transfer-in/summary")
def transfer_in_summary(biz_date: str = Query(...), user: str = Depends(get_current_user)):
    yday_str = (date.fromisoformat(biz_date) - timedelta(days=1)).isoformat()

    ov = trq.overview(biz_date)
    ov_y = trq.overview(yday_str)

    def g(d, k):
        v = d.get(k)
        return float(v) if v is not None else 0.0

    today_amt = g(ov, "total_amt")
    yday_amt = g(ov_y, "total_amt")
    diff_pct = (today_amt - yday_amt) / yday_amt * 100 if yday_amt else 0

    shops_list = []
    for r in trq.shops(biz_date, yday_str):
        t_amt = float(r.get("today_amt") or 0)
        y_amt = float(r.get("yday_amt") or 0)
        shops_list.append({
            "shop_code": r["shop_code"], "shop_name": r["shop_name"], "dm": r["dm"],
            "today_docs": int(r.get("today_docs") or 0),
            "today_qty": float(r.get("today_qty") or 0),
            "today_amt": t_amt, "yday_amt": y_amt,
            "diff_pct": (t_amt - y_amt) / y_amt * 100 if y_amt else None,
        })

    return {
        "date": biz_date,
        "totals": {
            "today_amt": today_amt, "yday_amt": yday_amt, "diff_pct": diff_pct,
            "total_docs": int(g(ov, "total_docs")), "total_lines": int(g(ov, "total_lines")),
            "total_qty": g(ov, "total_qty"), "shops_with_data": int(g(ov, "shops_with_data")),
            "distinct_items": int(g(ov, "distinct_items")),
        },
        "shops": shops_list,
        "status": trq.shop_status(biz_date),
    }


@app.get("/api/transfer-in/items")
def transfer_in_items(biz_date: str = Query(...), user: str = Depends(get_current_user)):
    return {"items": trq.item_options(biz_date)}


@app.get("/api/transfer-in/item-detail")
def transfer_in_item_detail(
    biz_date: str = Query(...), item_code: str = Query(...),
    user: str = Depends(get_current_user),
):
    tot = trq.item_total(biz_date, item_code)
    rows = trq.item_detail(biz_date, item_code)
    return {
        "item_code": item_code,
        "total_qty": float(tot.get("total_qty") or 0),
        "shop_cnt": int(tot.get("shop_cnt") or 0),
        "rows": [
            {"shop_code": r["shop_code"], "shop_name": r["shop_name"],
             "qty": float(r["qty"] or 0), "amount": float(r["amount"] or 0),
             "frm_branch": r["frm_branch"]}
            for r in rows
        ],
    }


@app.get("/api/petty-cash/summary")
def petty_cash_summary(biz_date: str = Query(...), user: str = Depends(get_current_user)):
    yday_str = (date.fromisoformat(biz_date) - timedelta(days=1)).isoformat()

    tot = pcq.totals(biz_date)
    tot_y = pcq.totals(yday_str)

    shops_list = []
    for r in pcq.by_shop(biz_date, yday_str):
        t = float(r.get("today_amt") or 0)
        y = float(r.get("yday_amt") or 0)
        shops_list.append({
            "shop_code": r["shop_code"], "shop_name": r["shop_name"], "dm": r["dm"],
            "today_amt": t, "yday_amt": y, "today_cnt": int(r.get("today_cnt") or 0),
            "diff_pct": (t - y) / y * 100 if y else None,
        })

    return {
        "date": biz_date,
        "totals": {
            "today_amt": float(tot.get("amt") or 0), "today_cnt": int(tot.get("cnt") or 0),
            "today_shops": int(tot.get("shops") or 0),
            "yday_amt": float(tot_y.get("amt") or 0),
        },
        "categories": [
            {"code": c["expen_code"], "name": c["expen_des1"],
             "amt": float(c["amt"] or 0), "cnt": int(c["cnt"] or 0)}
            for c in pcq.by_category(biz_date)
        ],
        "shops": shops_list,
        "recent": [
            {"doc_date": str(r["doc_date"]), "shop_code": r["shop_code"], "shop_name": r["shop_name"],
             "doc_no": r["doc_no"], "expen_des1": r["expen_des1"],
             "expen_amt": float(r["expen_amt"] or 0), "remark": r["remark"]}
            for r in pcq.recent(biz_date)
        ],
    }


@app.get("/api/exception/summary")
def exception_summary(biz_date: str = Query(...), user: str = Depends(get_current_user)):
    yday_str = (date.fromisoformat(biz_date) - timedelta(days=1)).isoformat()

    tot = exq.totals(biz_date)
    tot_y = exq.totals(yday_str)

    shops_list = []
    for r in exq.by_shop(biz_date, yday_str):
        t = float(r.get("today_amt") or 0)
        y = float(r.get("yday_amt") or 0)
        shops_list.append({
            "shop_code": r["shop_code"], "shop_name": r["shop_name"], "dm": r["dm"],
            "today_amt": t, "yday_amt": y, "today_bills": int(r.get("today_bills") or 0),
            "diff_pct": (t - y) / y * 100 if y else None,
        })

    return {
        "date": biz_date,
        "totals": {
            "today_amt": float(tot.get("amt") or 0), "today_bills": int(tot.get("bills") or 0),
            "today_shops": int(tot.get("shops") or 0), "yday_amt": float(tot_y.get("amt") or 0),
        },
        "shops": shops_list,
    }


@app.get("/api/health")
def health():
    return {"ok": True}


app.mount("/", StaticFiles(directory=os.path.join(HERE, "static"), html=True), name="static")
