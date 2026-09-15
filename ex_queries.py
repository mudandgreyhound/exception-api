"""
ex_queries.py — Exception Report queries
ยึดตาม exception_report.py (Streamlit) เดิม: VOID / DELETE / WASTE(+item) / ETL LOG / KITCHEN STATUS
"""
from db import query


def dm_head_options():
    return query("SELECT DISTINCT dm, head FROM dim_shop WHERE dm IS NOT NULL ORDER BY dm, head")


def void(biz, dm=None, head=None):
    return query("""
        SELECT v.shop_code, COALESCE(s.shop_name, v.shop_code) shop_name,
               s.dm, s.head,
               v.bill_count bills, v.void_amount amt
        FROM fact_void v JOIN dim_shop s ON v.shop_code=s.shop_code
        WHERE v.bill_date=%s AND (%s IS NULL OR s.dm=%s) AND (%s IS NULL OR s.head=%s)
        ORDER BY v.void_amount DESC
    """, (biz, dm, dm, head, head))


def delete(biz, dm=None, head=None):
    return query("""
        SELECT d.shop_code, COALESCE(s.shop_name, d.shop_code) shop_name,
               s.dm, s.head,
               d.item_count items, d.delete_amount amt
        FROM fact_delete d JOIN dim_shop s ON d.shop_code=s.shop_code
        WHERE d.entry_date=%s AND (%s IS NULL OR s.dm=%s) AND (%s IS NULL OR s.head=%s)
        ORDER BY d.delete_amount DESC
    """, (biz, dm, dm, head, head))


def waste(biz, dm=None, head=None):
    return query("""
        SELECT w.shop_code, COALESCE(s.shop_name, w.shop_code) shop_name,
               s.dm, s.head,
               w.reason_label reason,
               w.waste_amount total_waste,
               w.stnd_cost_amt stnd_cost
        FROM fact_waste w JOIN dim_shop s ON w.shop_code=s.shop_code
        WHERE w.waste_date=%s AND (%s IS NULL OR s.dm=%s) AND (%s IS NULL OR s.head=%s)
        ORDER BY w.waste_amount DESC
    """, (biz, dm, dm, head, head))


def waste_item(biz, dm=None, head=None):
    return query("""
        SELECT wi.shop_code, COALESCE(s.shop_name, wi.shop_code) shop_name,
               s.dm, s.head,
               wi.item_code,
               COALESCE(di.item_name, wi.item_code) item_name,
               COALESCE(di.unit, '') unit,
               wi.waste_qty qty
        FROM fact_waste_item wi
        JOIN dim_shop s ON wi.shop_code = s.shop_code
        LEFT JOIN dim_item di ON wi.item_code = di.item_code
        WHERE wi.waste_date=%s AND (%s IS NULL OR s.dm=%s) AND (%s IS NULL OR s.head=%s)
        ORDER BY wi.waste_qty DESC
    """, (biz, dm, dm, head, head))


def etl_log(biz):
    return query("""
        SELECT run_at, table_name,
               shops_total, shops_already, shops_synced, shops_missing,
               rows_inserted, status
        FROM etl_run_log WHERE target_date=%s ORDER BY run_at DESC LIMIT 20
    """, (biz,))


def period_totals(fr, to):
    """รวมยอด void/delete/waste/waste_cost แบบช่วงวันที่ (inclusive)"""
    sql = """
        SELECT
            COALESCE((SELECT SUM(void_amount)   FROM fact_void   WHERE bill_date  BETWEEN %s AND %s), 0) AS void_amt,
            COALESCE((SELECT SUM(delete_amount) FROM fact_delete WHERE entry_date BETWEEN %s AND %s), 0) AS del_amt,
            COALESCE((SELECT SUM(waste_amount)  FROM fact_waste  WHERE waste_date BETWEEN %s AND %s), 0) AS waste_amt,
            COALESCE((SELECT SUM(stnd_cost_amt) FROM fact_waste  WHERE waste_date BETWEEN %s AND %s), 0) AS waste_cost_amt
    """
    rows = query(sql, (fr, to, fr, to, fr, to, fr, to))
    return rows[0] if rows else {"void_amt": 0, "del_amt": 0, "waste_amt": 0, "waste_cost_amt": 0}


def kitchen_status():
    return query("""
        SELECT k.kitchen_code,
               COALESCE(s.shop_name, k.kitchen_code) AS kitchen_name,
               k.host, k.online, k.sale_date, k.iday, k.status,
               k.flage, k.days_behind, k.checked_at, k.err_msg
        FROM kitchen_status k
        LEFT JOIN dim_shop s ON s.shop_code = k.kitchen_code
        ORDER BY k.kitchen_code
    """)
