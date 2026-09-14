"""
ex_queries.py — Exception Report queries (fact_void)
"""
from db import query


def totals(biz):
    rows = query("""
        SELECT COALESCE(SUM(void_amount),0) amt, COALESCE(SUM(bill_count),0) bills,
               COUNT(DISTINCT shop_code) shops
        FROM fact_void WHERE bill_date=%s
    """, (biz,))
    return rows[0] if rows else {"amt": 0, "bills": 0, "shops": 0}


def by_shop(biz_t, biz_y):
    return query("""
        SELECT t.shop_code,
               COALESCE(sh.shop_name, t.shop_code) shop_name,
               COALESCE(sh.dm,'')                  dm,
               SUM(CASE WHEN t.bill_date=%s THEN t.amt   END) today_amt,
               SUM(CASE WHEN t.bill_date=%s THEN t.amt   END) yday_amt,
               SUM(CASE WHEN t.bill_date=%s THEN t.bills END) today_bills
        FROM (
            SELECT shop_code, bill_date, SUM(void_amount) amt, SUM(bill_count) bills
            FROM fact_void WHERE bill_date IN (%s,%s)
            GROUP BY shop_code, bill_date
        ) t
        LEFT JOIN dim_shop sh ON sh.shop_code = t.shop_code
        GROUP BY t.shop_code, sh.shop_name, sh.dm
        ORDER BY today_amt DESC
    """, (biz_t, biz_y, biz_t, biz_t, biz_y))
