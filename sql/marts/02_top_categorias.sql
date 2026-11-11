SELECT
    coalesce(t.product_category_name_english,
             pr.product_category_name,
             'sem_categoria')                  AS categoria,
    count(DISTINCT p.order_id)                 AS pedidos,
    count(*)                                   AS itens,
    sum(i.price)                               AS receita
FROM refined.itens_pedido             AS i
JOIN refined.pedidos                  AS p  ON p.order_id    = i.order_id
JOIN refined.produtos                 AS pr ON pr.product_id = i.product_id
LEFT JOIN refined.traducao_categorias AS t  ON t.product_category_name = pr.product_category_name
WHERE p.order_status NOT IN ('canceled', 'unavailable')
GROUP BY 1
ORDER BY receita DESC;