CREATE VIEW member_summary_views AS
    SELECT all_date.date,
           partner.id AS partner_id,
           IFNULL(deposit_orders.total_amount, 0) AS deposit_amount,
           IFNULL(deposit_orders.order_count, 0) AS deposit_count,
           IFNULL(withdraw_orders.total_amount, 0) AS withdraw_amount,
           IFNULL(withdraw_orders.order_count, 0) AS withdraw_count,
           IFNULL(partner_levels.new_member_count, 0) AS new_member_count
    FROM (
             SELECT ADDDATE('1970-01-01', t4.i * 10000 + t3.i * 1000 + t2.i * 100 + t1.i * 10 + t0.i) AS date
             FROM
                 (SELECT 0 AS i UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) t0,
                 (SELECT 0 AS i UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) t1,
                 (SELECT 0 AS i UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) t2,
                 (SELECT 0 AS i UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) t3,
                 (SELECT 0 AS i UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) t4
         ) AS all_date
             CROSS JOIN (SELECT id FROM partner) AS partner
        LEFT JOIN (SELECT  partner_id,
                           SUM(amount) AS total_amount,
                           COUNT(orders_df.id)    AS order_count,
                           DATE(orders_df.time_create) AS created_order_date
                    FROM orders_df
                    WHERE status = 4
                    GROUP BY id, partner_id) AS deposit_orders
            ON deposit_orders.partner_id = partner.id AND deposit_orders.created_order_date = date
        LEFT JOIN (SELECT partner_id,
                       SUM(amount)            AS total_amount,
                       COUNT(orders_ds.id)    AS order_count,
                       DATE(orders_ds.time_create) AS created_order_date
                    FROM orders_ds
                    WHERE status = 4
                    GROUP BY id, partner_id) AS withdraw_orders
            ON withdraw_orders.partner_id = partner.id AND withdraw_orders.created_order_date = date
        LEFT JOIN (SELECT partner_tree.parent,
                       COUNT(partner_tree.child) AS new_member_count,
                       DATE(p.time_create) AS register_date
                   FROM partner_tree
                        LEFT JOIN partner p ON p.id = partner_tree.child AND partner_tree.distance != 0
                   GROUP BY partner_tree.parent, register_date
                ) AS partner_levels ON partner_levels.parent = partner.id AND register_date = date
    WHERE all_date.date BETWEEN DATE(DATE_SUB(CURDATE(), INTERVAL 3 MONTH)) AND DATE(CURDATE());