"""
tr_queries.py — Transfer In queries (v_tranin_overview / v_tranin_shop_daily / tranin_status)
"""
from db import query


def overview(biz):
    rows = query("SELECT * FROM v_tranin_overview WHERE doc_date=%s", (biz,))
    return rows[0] if rows else {}


def shops(biz_t, biz_y):
    return query("""
        SELECT s.branch_code shop_code,
               COALESCE(sh.shop_name, s.branch_code) shop_name,
               COALESCE(sh.dm,'')                    dm,
               MAX(CASE WHEN s.doc_date=%s THEN s.doc_cnt   END) today_docs,
               MAX(CASE WHEN s.doc_date=%s THEN s.total_qty END) today_qty,
               MAX(CASE WHEN s.doc_date=%s THEN s.total_amt END) today_amt,
               MAX(CASE WHEN s.doc_date=%s THEN s.total_amt END) yday_amt
        FROM v_tranin_shop_daily s
        LEFT JOIN dim_shop sh ON sh.shop_code = s.branch_code
        WHERE s.doc_date IN (%s,%s)
        GROUP BY s.branch_code, sh.shop_name, sh.dm
        ORDER BY today_amt DESC
    """, (biz_t, biz_t, biz_t, biz_y, biz_t, biz_y))


def shop_status(biz):
    """สถานะ sync ทุกสาขา วันนั้น — offline/error ขึ้นก่อน"""
    return query("""
        SELECT t.branch_code shop_code,
               COALESCE(sh.shop_name, t.branch_code) shop_name,
               t.online, t.doc_cnt, t.err_msg, t.checked_at
        FROM tranin_status t
        LEFT JOIN dim_shop sh ON sh.shop_code = t.branch_code
        WHERE t.doc_date=%s
        ORDER BY t.online ASC, t.branch_code
    """, (biz,))


# ─────────────────────────── By item (รายสินค้า) ───────────────────────────
def item_options(biz):
    return query("""
        SELECT DISTINCT v.item_code, COALESCE(d.item_name, v.item_code) item_name
        FROM v_tranin_item_daily v
        LEFT JOIN dim_item d ON TRIM(d.item_code) = TRIM(v.item_code)
        WHERE v.doc_date=%s
        ORDER BY item_name
    """, (biz,))


def item_total(biz, item_code):
    rows = query("""
        SELECT * FROM v_tranin_item_total WHERE doc_date=%s AND item_code=%s
    """, (biz, item_code))
    return rows[0] if rows else {}


def item_detail(biz, item_code):
    return query("""
        SELECT v.branch_code shop_code, COALESCE(sh.shop_name, v.branch_code) shop_name,
               v.qty, v.amount, v.frm_branch
        FROM v_tranin_item_daily v
        LEFT JOIN dim_shop sh ON sh.shop_code = v.branch_code
        WHERE v.doc_date=%s AND v.item_code=%s
        ORDER BY v.qty DESC
    """, (biz, item_code))
