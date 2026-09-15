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
    tot = trq.totals(biz_date)

    def g(d, k):
        v = d.get(k)
        return float(v) if v is not None else 0.0

    v_in, v_sold, v_void, v_remain = g(tot, "tr_in"), g(tot, "sold"), g(tot, "void_qty"), g(tot, "remain")

    def status_of(r, tr_in):
        has_status = bool(r["has_status"])
        online = r["online"]
        has_qty = tr_in > 0
        if not has_status:
            return "has" if has_qty else "empty"
        if not online:
            return "offline_stale" if has_qty else "offline"
        return "has" if has_qty else "empty"

    shops_list = []
    for r in trq.shop_status(biz_date):
        tr_in = float(r["tr_in"] or 0)
        shops_list.append({
            "shop_code": r["shop_code"], "shop_name": r["shop_name"], "dm": r["dm"],
            "status": status_of(r, tr_in),
            "online": bool(r["online"]) if r["online"] is not None else None,
            "err_msg": r["err_msg"],
            "checked_at": str(r["checked_at"]) if r["checked_at"] else None,
            "doc_cnt": int(r["doc_cnt"]) if r["doc_cnt"] is not None else None,
            "tr_in": tr_in, "tr_out": float(r["tr_out"] or 0),
            "sold": float(r["sold"] or 0), "void_qty": float(r["void_qty"] or 0),
            "remain": float(r["remain"] or 0),
        })

    n_online = sum(1 for r in shops_list if r["online"])
    n_total = len(shops_list)
    n_active = sum(1 for r in shops_list if r["tr_in"] > 0)

    return {
        "date": biz_date,
        "totals": {
            "tr_in": v_in, "sold": v_sold, "void_qty": v_void, "remain": v_remain,
            "n_online": n_online, "n_total": n_total, "n_active": n_active,
        },
        "shops": shops_list,
    }


@app.get("/api/transfer-in/shop-options")
def transfer_in_shop_options(biz_date: str = Query(...), user: str = Depends(get_current_user)):
    return {"shops": trq.shop_opts(biz_date)}


@app.get("/api/transfer-in/by-shop")
def transfer_in_by_shop(
    biz_date: str = Query(...), branch: str = Query(...),
    user: str = Depends(get_current_user),
):
    rows = trq.by_shop(biz_date, branch)
    out = [
        {"item_code": r["item_code"], "item_name": r["item_name"],
         "tr_in": float(r["tr_in"] or 0), "sold": float(r["sold"] or 0),
         "void_qty": float(r["void_qty"] or 0), "remain": float(r["remain"] or 0),
         "frm_branch": r["frm_branch"]}
        for r in rows
    ]
    return {
        "branch": branch,
        "total_tr_in": sum(r["tr_in"] for r in out),
        "total_sold": sum(r["sold"] for r in out),
        "total_void": sum(r["void_qty"] for r in out),
        "total_remain": sum(r["remain"] for r in out),
        "rows": out,
    }


@app.get("/api/transfer-in/items")
def transfer_in_items(biz_date: str = Query(...), user: str = Depends(get_current_user)):
    return {"items": trq.item_opts(biz_date)}


@app.get("/api/transfer-in/item-detail")
def transfer_in_item_detail(
    biz_date: str = Query(...), item_code: str = Query(...),
    user: str = Depends(get_current_user),
):
    rows = trq.by_item(biz_date, item_code)
    out = [
        {"shop_code": r["shop_code"], "shop_name": r["shop_name"],
         "qty": float(r["qty"] or 0), "amount": float(r["amount"] or 0),
         "frm_branch": r["frm_branch"]}
        for r in rows
    ]
    return {
        "item_code": item_code,
        "total_qty": sum(r["qty"] for r in out),
        "shop_cnt": len(out),
        "rows": out,
    }


@app.get("/api/petty-cash/filters")
def petty_cash_filters(user: str = Depends(get_current_user)):
    return {"branches": pcq.branches()}


@app.get("/api/petty-cash/available-dates")
def petty_cash_available_dates(user: str = Depends(get_current_user)):
    rows = pcq.available_dates()
    return {"dates": [str(r["doc_date"]) for r in rows]}


@app.get("/api/petty-cash/summary")
def petty_cash_summary(
    biz_date: str = Query(...), shops: str = Query(""),
    user: str = Depends(get_current_user),
):
    shop_codes = tuple(s for s in shops.split(",") if s)

    detail_rows = pcq.detail(biz_date, shop_codes)
    branch_rows = pcq.summary_by_shop(biz_date, shop_codes)
    expen_rows = pcq.by_expense(biz_date, shop_codes)

    total_amt = sum(float(r["expen_amt"] or 0) for r in detail_rows)
    total_docs = len({r["doc_no"] for r in detail_rows})
    total_shops = len(branch_rows)
    top_expen = expen_rows[0]["expen_des1"] if expen_rows else "-"

    return {
        "date": biz_date,
        "totals": {
            "total_amt": total_amt, "total_docs": total_docs,
            "total_shops": total_shops, "top_expen": top_expen,
        },
        "detail": [
            {"shop_code": r["shop_code"], "shop_name": r["shop_name"],
             "doc_no": r["doc_no"], "doc_stat": r["doc_stat"],
             "expen_code": r["expen_code"], "expen_des1": r["expen_des1"],
             "expen_amt": float(r["expen_amt"] or 0),
             "reference": r["reference"], "remark": r["remark"]}
            for r in detail_rows
        ],
        "by_branch": [
            {"shop_code": r["shop_code"], "shop_name": r["shop_name"],
             "doc_cnt": int(r["doc_cnt"] or 0), "amt": float(r["amt"] or 0)}
            for r in branch_rows
        ],
        "by_expense": [
            {"expen_code": r["expen_code"], "expen_des1": r["expen_des1"],
             "amt": float(r["amt"] or 0), "cnt": int(r["cnt"] or 0)}
            for r in expen_rows
        ],
    }


@app.get("/api/petty-cash/etl-log")
def petty_cash_etl_log(user: str = Depends(get_current_user)):
    rows = pcq.etl_log()
    return {"rows": [
        {"run_at": str(r["run_at"]) if r["run_at"] else None,
         "target_date": str(r["target_date"]) if r["target_date"] else None,
         "rows_deleted": r["rows_deleted"], "rows_inserted": r["rows_inserted"],
         "status": r["status"]}
        for r in rows
    ]}


def _ex_period(fr, to):
    p = exq.period_totals(fr, to)
    return {
        "void": float(p.get("void_amt") or 0),
        "delete": float(p.get("del_amt") or 0),
        "waste": float(p.get("waste_amt") or 0),
        "waste_cost": float(p.get("waste_cost_amt") or 0),
    }


@app.get("/api/exception/filters")
def exception_filters(user: str = Depends(get_current_user)):
    rows = exq.dm_head_options()
    heads = sorted({r["head"] for r in rows if r["head"]})
    dm_by_head = {}
    for r in rows:
        if not r["dm"]:
            continue
        dm_by_head.setdefault(r["head"] or "", set()).add(r["dm"])
    return {
        "heads": heads,
        "dm_by_head": {h: sorted(v) for h, v in dm_by_head.items()},
        "dm_all": sorted({r["dm"] for r in rows if r["dm"]}),
    }


@app.get("/api/exception/summary")
def exception_summary(
    biz_date: str = Query(...), compare_date: str = Query(...),
    dm: str = Query(""), head: str = Query(""),
    user: str = Depends(get_current_user),
):
    dm_p, head_p = (dm or None), (head or None)
    v_rows = exq.void(biz_date, dm_p, head_p)
    d_rows = exq.delete(biz_date, dm_p, head_p)
    w_rows = exq.waste(biz_date, dm_p, head_p)

    va = sum(float(r["amt"] or 0) for r in v_rows)
    da = sum(float(r["amt"] or 0) for r in d_rows)
    wa = sum(float(r["total_waste"] or 0) for r in w_rows)
    wa_cost = sum(float(r["stnd_cost"] or 0) for r in w_rows)

    cmp_p = _ex_period(compare_date, compare_date)

    return {
        "date": biz_date, "compare_date": compare_date,
        "totals": {"void": va, "delete": da, "waste": wa, "waste_cost": wa_cost,
                   "total": va + da + wa, "total_cost": va + da + wa_cost},
        "compare": cmp_p,
    }


@app.get("/api/exception/void")
def exception_void(
    biz_date: str = Query(...), dm: str = Query(""), head: str = Query(""),
    user: str = Depends(get_current_user),
):
    rows = exq.void(biz_date, dm or None, head or None)
    return {"rows": [
        {"shop_code": r["shop_code"], "shop_name": r["shop_name"], "dm": r["dm"], "head": r["head"],
         "bills": int(r["bills"] or 0), "amt": float(r["amt"] or 0)}
        for r in rows
    ]}


@app.get("/api/exception/delete")
def exception_delete(
    biz_date: str = Query(...), dm: str = Query(""), head: str = Query(""),
    user: str = Depends(get_current_user),
):
    rows = exq.delete(biz_date, dm or None, head or None)
    return {"rows": [
        {"shop_code": r["shop_code"], "shop_name": r["shop_name"], "dm": r["dm"], "head": r["head"],
         "items": int(r["items"] or 0), "amt": float(r["amt"] or 0)}
        for r in rows
    ]}


@app.get("/api/exception/waste")
def exception_waste(
    biz_date: str = Query(...), dm: str = Query(""), head: str = Query(""),
    grain: str = Query("shop"), user: str = Depends(get_current_user),
):
    dm_p, head_p = (dm or None), (head or None)
    if grain == "shop":
        rows = exq.waste(biz_date, dm_p, head_p)
        return {"rows": [
            {"shop_code": r["shop_code"], "shop_name": r["shop_name"], "dm": r["dm"], "head": r["head"],
             "reason": r["reason"], "total_waste": float(r["total_waste"] or 0),
             "stnd_cost": float(r["stnd_cost"] or 0)}
            for r in rows
        ]}
    wi = exq.waste_item(biz_date, dm_p, head_p)
    if grain == "item_detail":
        return {"rows": [
            {"shop_code": r["shop_code"], "shop_name": r["shop_name"],
             "item_code": r["item_code"], "item_name": r["item_name"], "unit": r["unit"],
             "qty": float(r["qty"] or 0)}
            for r in wi
        ]}
    # item_summary
    agg = {}
    for r in wi:
        key = (r["item_code"], r["item_name"], r["unit"])
        a = agg.setdefault(key, {"qty": 0.0, "shops": set()})
        a["qty"] += float(r["qty"] or 0)
        a["shops"].add(r["shop_code"])
    out = [
        {"item_code": k[0], "item_name": k[1], "unit": k[2],
         "qty": v["qty"], "shop_cnt": len(v["shops"])}
        for k, v in agg.items()
    ]
    out.sort(key=lambda x: x["qty"], reverse=True)
    return {"rows": out}


@app.get("/api/exception/compare")
def exception_compare(
    mode: str = Query("daily"),
    date_a: str = Query(None), date_b: str = Query(None),
    a_fr: str = Query(None), a_to: str = Query(None),
    b_fr: str = Query(None), b_to: str = Query(None),
    user: str = Depends(get_current_user),
):
    if mode in ("daily",):
        a, b = _ex_period(date_a, date_a), _ex_period(date_b, date_b)
    else:
        a, b = _ex_period(a_fr, a_to), _ex_period(b_fr, b_to)
    return {"a": a, "b": b}


@app.get("/api/exception/compare-trend")
def exception_compare_trend(
    weekday: int = Query(...), fr: str = Query(...), to: str = Query(...),
    user: str = Depends(get_current_user),
):
    d0 = date.fromisoformat(fr)
    d1 = date.fromisoformat(to)
    points = []
    d = d0
    while d <= d1:
        if d.weekday() == weekday:
            points.append(d)
        d += timedelta(days=1)
    out = []
    for d in points:
        p = _ex_period(d.isoformat(), d.isoformat())
        out.append({"date": d.isoformat(), **p, "total": p["void"] + p["delete"] + p["waste"]})
    return {"points": out}


@app.get("/api/exception/kitchen-status")
def exception_kitchen_status(user: str = Depends(get_current_user)):
    rows = exq.kitchen_status()
    today = date.today()
    out = []
    for r in rows:
        online = int(r["online"] or 0)
        sale_date = r["sale_date"]
        days_behind = (today - sale_date).days if sale_date else None
        if not online:
            state = "OFFLINE"
        elif sale_date is None:
            state = "NODATA"
        elif days_behind >= 3:
            state = "CRIT"
        elif days_behind >= 2:
            state = "WARN"
        else:
            state = "OK"
        out.append({
            "kitchen_code": r["kitchen_code"], "kitchen_name": r["kitchen_name"], "host": r["host"],
            "online": bool(online), "sale_date": str(sale_date) if sale_date else None,
            "days_behind": days_behind, "iday": r["iday"], "status": r["status"], "flage": r["flage"],
            "checked_at": str(r["checked_at"]) if r["checked_at"] else None,
            "err_msg": r["err_msg"], "state": state,
        })
    return {"rows": out}


@app.get("/api/exception/etl-log")
def exception_etl_log(biz_date: str = Query(...), user: str = Depends(get_current_user)):
    rows = exq.etl_log(biz_date)
    return {"rows": [
        {"run_at": str(r["run_at"]) if r["run_at"] else None, "table_name": r["table_name"],
         "shops_total": r["shops_total"], "shops_already": r["shops_already"],
         "shops_synced": r["shops_synced"], "shops_missing": r["shops_missing"],
         "rows_inserted": r["rows_inserted"], "status": r["status"]}
        for r in rows
    ]}


@app.get("/api/health")
def health():
    return {"ok": True}


app.mount("/", StaticFiles(directory=os.path.join(HERE, "static"), html=True), name="static")
