"""
pc_queries.py — Petty Cash queries (fact_petty_cash)
"""
from db import query


def totals(biz):
    rows = query("""
        SELECT COALESCE(SUM(expen_amt),0) amt, COUNT(*) cnt, COUNT(DISTINCT shop_code) shops
        FROM fact_petty_cash WHERE doc_date=%s
    """, (biz,))
    return rows[0] if rows else {"amt": 0, "cnt": 0, "shops": 0}


def by_category(biz):
    return query("""
        SELECT expen_code, expen_des1,
               COALESCE(SUM(expen_amt),0) amt, COUNT(*) cnt
        FROM fact_petty_cash
        WHERE doc_date=%s
        GROUP BY expen_code, expen_des1
        ORDER BY amt DESC
    """, (biz,))


def by_shop(biz_t, biz_y):
    return query("""
        SELECT t.shop_code,
               COALESCE(sh.shop_name, t.shop_code) shop_name,
               COALESCE(sh.dm,'')                  dm,
               SUM(CASE WHEN t.doc_date=%s THEN t.amt END) today_amt,
               SUM(CASE WHEN t.doc_date=%s THEN t.amt END) yday_amt,
               SUM(CASE WHEN t.doc_date=%s THEN t.cnt END) today_cnt
        FROM (
            SELECT shop_code, doc_date, SUM(expen_amt) amt, COUNT(*) cnt
            FROM fact_petty_cash WHERE doc_date IN (%s,%s)
            GROUP BY shop_code, doc_date
        ) t
        LEFT JOIN dim_shop sh ON sh.shop_code = t.shop_code
        GROUP BY t.shop_code, sh.shop_name, sh.dm
        ORDER BY today_amt DESC
    """, (biz_t, biz_y, biz_t, biz_t, biz_y))


def recent(biz, limit=300):
    return query("""
        SELECT p.doc_date, p.shop_code,
               COALESCE(sh.shop_name, p.shop_code) shop_name,
               p.doc_no, p.expen_des1, p.expen_amt, p.remark
        FROM fact_petty_cash p
        LEFT JOIN dim_shop sh ON sh.shop_code = p.shop_code
        WHERE p.doc_date=%s
        ORDER BY p.doc_no DESC
        LIMIT %s
    """, (biz, limit))
