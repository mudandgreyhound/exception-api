"""
sm_queries.py — query เดิมจาก exception_report.py (sm_totals / sm_hourly / sm_shops /
sm_dm_perf / sm_tender / sm_pay_group) ย้ายมาไว้ที่นี่ทั้งชุด logic เดิมทุกจุด
"""
from db import query

# ─────────────────────────── DM options ───────────────────────────
def dm_options(biz):
    rows = query("""
        SELECT DISTINCT sh.dm
        FROM sale_monitor_rt r
        JOIN dim_shop sh ON sh.shop_code = r.shop_code
        WHERE r.biz_date=%s
          AND sh.dm IS NOT NULL AND sh.dm<>''
          AND sh.dm NOT LIKE 'ยกเลิก%%'
          AND sh.dm <> 'Not Analysed'
        ORDER BY sh.dm
    """, (biz,))
    return [r["dm"] for r in rows]


# ─────────────────────────── Totals ───────────────────────────
def totals(biz, dm=""):
    rows = query("""
        SELECT COALESCE(SUM(net_sales),0)    net_sales,
               COALESCE(SUM(gross_sales),0)  gross_sales,
               COALESCE(SUM(discount),0)     discount,
               COALESCE(SUM(bill_count),0)   bills,
               COALESCE(SUM(coupon_bills),0) coupons,
               COUNT(*)                      shops,
               MAX(snapshot_at)              snap
        FROM sale_monitor_rt r
        LEFT JOIN dim_shop sh ON sh.shop_code=r.shop_code
        WHERE r.biz_date=%s AND (%s='' OR sh.dm=%s)
    """, (biz, dm, dm))
    return rows[0] if rows else {}


def hourly(biz, dm=""):
    return query("""
        SELECT hour_slot,
               COALESCE(SUM(net_sales),0)  net_sales,
               COALESCE(SUM(discount),0)   discount,
               COALESCE(SUM(bill_count),0) bills
        FROM sale_monitor_interval i
        LEFT JOIN dim_shop sh ON sh.shop_code=i.shop_code
        WHERE i.biz_date=%s AND (%s='' OR sh.dm=%s)
        GROUP BY hour_slot ORDER BY hour_slot
    """, (biz, dm, dm))


def ytd_same_time(biz_y, cur_h, dm=""):
    rows = query("""
        SELECT COALESCE(SUM(net_sales),0) s
        FROM sale_monitor_interval i
        LEFT JOIN dim_shop sh ON sh.shop_code=i.shop_code
        WHERE i.biz_date=%s AND hour_slot<=%s AND (%s='' OR sh.dm=%s)
    """, (biz_y, cur_h, dm, dm))
    return float(rows[0]["s"] or 0) if rows else 0.0


def shops(biz_t, biz_y, dm=""):
    return query("""
        SELECT s.shop_code,
               COALESCE(sh.shop_name, s.shop_code) shop_name,
               COALESCE(sh.dm,'')                  dm,
               MAX(CASE WHEN s.biz_date=%s THEN s.net_sales     END) today,
               MAX(CASE WHEN s.biz_date=%s THEN s.net_sales     END) yday,
               MAX(CASE WHEN s.biz_date=%s THEN s.bill_count    END) bills,
               MAX(CASE WHEN s.biz_date=%s THEN s.last_bill_time END) last_bill
        FROM sale_monitor_rt s
        LEFT JOIN dim_shop sh ON sh.shop_code = s.shop_code
        WHERE s.biz_date IN (%s,%s) AND (%s='' OR sh.dm=%s)
        GROUP BY s.shop_code, sh.shop_name, sh.dm
        ORDER BY today DESC
    """, (biz_t, biz_y, biz_t, biz_t, biz_t, biz_y, dm, dm))


def dm_perf(biz_t, biz_y, cur_h):
    today = query("""
        SELECT COALESCE(sh.dm,'(ไม่ระบุ)') dm,
               SUM(r.net_sales) today, SUM(r.bill_count) bills,
               COUNT(*) shops
        FROM sale_monitor_rt r
        LEFT JOIN dim_shop sh ON sh.shop_code=r.shop_code
        WHERE r.biz_date=%s
          AND COALESCE(sh.dm,'') NOT LIKE 'ยกเลิก%%'
          AND COALESCE(sh.dm,'') <> 'Not Analysed'
        GROUP BY sh.dm
    """, (biz_t,))
    yday = query("""
        SELECT COALESCE(sh.dm,'(ไม่ระบุ)') dm, SUM(i.net_sales) yday
        FROM sale_monitor_interval i
        LEFT JOIN dim_shop sh ON sh.shop_code=i.shop_code
        WHERE i.biz_date=%s AND i.hour_slot<=%s
          AND COALESCE(sh.dm,'') NOT LIKE 'ยกเลิก%%'
          AND COALESCE(sh.dm,'') <> 'Not Analysed'
        GROUP BY sh.dm
    """, (biz_y, cur_h))
    ymap = {r["dm"]: float(r["yday"] or 0) for r in yday}
    out = []
    for r in today:
        out.append({
            "dm": r["dm"],
            "today": float(r["today"] or 0),
            "bills": int(r["bills"] or 0),
            "shops": int(r["shops"] or 0),
            "yday": ymap.get(r["dm"], 0.0),
        })
    out.sort(key=lambda x: x["today"], reverse=True)
    return out


def tender(biz):
    return query("""
        SELECT tend_code, tendtype, card_name, net_amt, bills
        FROM sale_monitor_tender WHERE biz_date=%s
    """, (biz,))


def items(biz, top_n=8):
    return query("""
        SELECT item_code, item_name, qty, net_amt, bills
        FROM sale_monitor_item WHERE biz_date=%s
        ORDER BY net_amt DESC LIMIT %s
    """, (biz, top_n))


def flavors(biz, top_n=8):
    return query("""
        SELECT flavor_code, flavor_name, pick_count, boxes
        FROM sale_monitor_flavor WHERE biz_date=%s
        ORDER BY pick_count DESC LIMIT %s
    """, (biz, top_n))


# จัดกลุ่มวิธีจ่ายเงิน — logic เดิมจาก sm_pay_group ใน exception_report.py
# (เฉพาะ "เงินรับจริง" = CSH+CRD ; คูปอง/ส่วนลดแยกต่างหาก)
def pay_group(tender_rows):
    groups_raw = {}
    csh = 0.0
    chg = 0.0
    promo_map = {}

    for r in tender_rows:
        tt = (r.get("tendtype") or "").strip()
        net_amt = float(r.get("net_amt") or 0)
        bills = float(r.get("bills") or 0)
        tc = (r.get("tend_code") or "").upper()
        cn = (r.get("card_name") or "").upper()

        if tt == "CSH":
            csh += net_amt
            continue
        if tt == "CHG":
            chg += net_amt
            continue
        if tt == "CPN":
            key = r.get("card_name") or ""
            slot = promo_map.setdefault(key, {"card_name": key, "net_amt": 0.0, "bills": 0.0})
            slot["net_amt"] += net_amt
            slot["bills"] += bills
            continue
        if tt != "CRD":
            continue  # ITD/MEM/BDP/VC = ส่วนลด ไม่ใช่เงินรับ

        if tc == "T056" or "QR" in cn or "PROMPT" in cn:
            grp = "QR PromptPay"
        elif any(k in cn for k in ("GRAB", "LINE MAN", "LINEMAN", "SHOPEE", "ROBINHOOD", "FOODPANDA")):
            grp = "Delivery"
        elif "TRUEMONEY" in cn or tc == "1TRM" or "WALLET" in cn:
            grp = "e-Wallet"
        else:
            grp = "บัตรเครดิต"
        groups_raw[grp] = groups_raw.get(grp, 0.0) + net_amt

    groups = {"เงินสด": csh - chg}
    for g in ("QR PromptPay", "บัตรเครดิต", "Delivery", "e-Wallet"):
        v = groups_raw.get(g, 0.0)
        if v:
            groups[g] = v

    promo = sorted(promo_map.values(), key=lambda x: x["net_amt"], reverse=True)
    return groups, promo
