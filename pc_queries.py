"""
pc_queries.py — Petty Cash queries
ยึดตาม exception_report.py (Streamlit) เดิม
"""
from db import query


def available_dates():
    return query("""
        SELECT DISTINCT doc_date
        FROM fact_petty_cash
        WHERE doc_date >= DATE_SUB(CURDATE(), INTERVAL 3 MONTH)
        ORDER BY doc_date DESC
    """)


def date_range():
    rows = query("SELECT MIN(doc_date) mn, MAX(doc_date) mx FROM fact_petty_cash")
    return rows[0] if rows else {"mn": None, "mx": None}


def branches():
    return query("""
        SELECT p.shop_code, COALESCE(s.shop_name, p.shop_code) AS shop_name
        FROM (SELECT DISTINCT shop_code FROM fact_petty_cash) p
        LEFT JOIN dim_shop s ON p.shop_code = s.shop_code
        ORDER BY p.shop_code
    """)


def _shop_in(shop_codes):
    """คืน (sql_fragment, params) สำหรับ WHERE shop_code IN (...) — ว่าง = ไม่กรอง"""
    if not shop_codes:
        return "", ()
    ph = ",".join(["%s"] * len(shop_codes))
    return f"AND shop_code IN ({ph})", tuple(shop_codes)


def detail(biz, shop_codes=()):
    frag, params = _shop_in(shop_codes)
    frag = frag.replace("shop_code", "p.shop_code")
    return query(f"""
        SELECT p.shop_code, COALESCE(s.shop_name,p.shop_code) shop_name,
               p.doc_no, p.doc_stat,
               p.expen_code, p.expen_des1,
               p.expen_amt, p.reference, p.remark
        FROM fact_petty_cash p
        LEFT JOIN dim_shop s ON p.shop_code=s.shop_code
        WHERE p.doc_date=%s {frag}
        ORDER BY p.shop_code, p.doc_no, p.expen_code DESC
    """, (biz, *params))


def summary_by_shop(biz, shop_codes=()):
    frag, params = _shop_in(shop_codes)
    frag = frag.replace("shop_code", "p.shop_code")
    return query(f"""
        SELECT p.shop_code, COALESCE(s.shop_name,p.shop_code) shop_name,
               COUNT(DISTINCT p.doc_no) doc_cnt, SUM(p.expen_amt) amt
        FROM fact_petty_cash p
        LEFT JOIN dim_shop s ON p.shop_code=s.shop_code
        WHERE p.doc_date=%s {frag}
        GROUP BY p.shop_code, s.shop_name ORDER BY amt DESC
    """, (biz, *params))


def by_expense(biz, shop_codes=()):
    frag, params = _shop_in(shop_codes)
    return query(f"""
        SELECT expen_code, expen_des1,
               SUM(expen_amt) amt, COUNT(*) cnt
        FROM fact_petty_cash
        WHERE doc_date=%s {frag}
        GROUP BY expen_code, expen_des1 ORDER BY amt DESC
    """, (biz, *params))


def etl_log():
    return query("""
        SELECT run_at, target_date, rows_deleted, rows_inserted, status
        FROM etl_petty_log ORDER BY run_at DESC LIMIT 30
    """)
