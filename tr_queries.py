"""
tr_queries.py — Transfer In queries
ยึดตาม exception_report.py (Streamlit) เดิมเป๊ะ: หน่วยเป็น "ชิ้น" (v_tranin_remain)
ไม่ใช่บาท (v_tranin_shop_daily เดิมใช้ตอน prototype แรก — เลิกใช้แล้ว)
"""
from db import query


def totals(biz):
    """ยอดรวมรับเข้า/ขาย/void/เหลือ ทั้งวัน (ทุกสาขา)"""
    rows = query("""
        SELECT COALESCE(SUM(tr_in),0)    AS tr_in,
               COALESCE(SUM(sold),0)     AS sold,
               COALESCE(SUM(void_qty),0) AS void_qty,
               COALESCE(SUM(remain),0)   AS remain
        FROM v_tranin_remain WHERE doc_date=%s
    """, (biz,))
    return rows[0] if rows else {}


def shop_status(biz):
    """สถานะสาขา + ยอด รับ/ขาย/void/เหลือ ต่อสาขา
    base = สาขาที่มีสถานะ (วันนี้) ∪ สาขาที่มี activity วันนั้น (v_tranin_remain)
    """
    return query("""
        SELECT base.branch_code shop_code,
               COALESCE(sh.shop_name, '') AS shop_name,
               COALESCE(sh.dm, '') AS dm,
               s.online, s.err_msg, s.checked_at,
               CASE WHEN s.branch_code IS NOT NULL THEN 1 ELSE 0 END AS has_status,
               d.doc_cnt,
               r.tr_in, r.tr_out, r.sold, r.void_qty, r.remain
        FROM (
                SELECT branch_code FROM tranin_status WHERE doc_date = %s
                UNION
                SELECT DISTINCT branch_code FROM v_tranin_remain WHERE doc_date = %s
             ) base
        LEFT JOIN tranin_status s
               ON s.branch_code = base.branch_code AND s.doc_date = %s
        LEFT JOIN dim_shop sh ON sh.shop_code = base.branch_code
        LEFT JOIN v_tranin_shop_daily d
               ON d.branch_code = base.branch_code AND d.doc_date = %s
        LEFT JOIN (SELECT branch_code,
                          SUM(tr_in)    AS tr_in,
                          SUM(tr_out)   AS tr_out,
                          SUM(sold)     AS sold,
                          SUM(void_qty) AS void_qty,
                          SUM(remain)   AS remain
                   FROM v_tranin_remain WHERE doc_date = %s
                   GROUP BY branch_code) r
               ON r.branch_code = base.branch_code
        ORDER BY base.branch_code
    """, (biz, biz, biz, biz, biz))


# ─────────────────────────── By shop (รายสาขา) ───────────────────────────
def shop_opts(biz):
    return query("""
        SELECT DISTINCT v.branch_code shop_code,
               COALESCE(sh.shop_name, '') shop_name
        FROM v_tranin_shop_daily v
        LEFT JOIN dim_shop sh ON sh.shop_code = v.branch_code
        WHERE v.doc_date = %s ORDER BY v.branch_code
    """, (biz,))


def by_shop(biz, branch):
    return query("""
        SELECT r.item_code,
               COALESCE(NULLIF(i.item_name,''), ci.item_name, '') AS item_name,
               r.tr_in, r.sold, r.void_qty, r.remain,
               v.frm_branch
        FROM v_tranin_remain r
        LEFT JOIN dim_item i ON i.item_code = r.item_code
        LEFT JOIN connect_dim_item ci ON ci.item_code = r.item_code
        LEFT JOIN v_tranin_item_daily v
               ON  v.doc_date = r.doc_date
               AND v.branch_code = r.branch_code
               AND v.item_code = r.item_code
        WHERE r.doc_date = %s AND r.branch_code = %s
        ORDER BY r.tr_in DESC
    """, (biz, branch))


# ─────────────────────────── By item (รายสินค้า) ───────────────────────────
def item_opts(biz):
    return query("""
        SELECT DISTINCT v.item_code,
               COALESCE(NULLIF(i.item_name,''), ci.item_name, '') AS item_name
        FROM v_tranin_item_daily v
        LEFT JOIN dim_item i ON i.item_code = v.item_code
        LEFT JOIN connect_dim_item ci ON ci.item_code = v.item_code
        WHERE v.doc_date = %s ORDER BY v.item_code
    """, (biz,))


def by_item(biz, item_code):
    return query("""
        SELECT v.branch_code shop_code,
               COALESCE(sh.shop_name, '') AS shop_name,
               v.qty, v.amount, v.frm_branch
        FROM v_tranin_item_daily v
        LEFT JOIN dim_shop sh ON sh.shop_code = v.branch_code
        WHERE v.doc_date = %s AND v.item_code = %s
        ORDER BY v.qty DESC
    """, (biz, item_code))
