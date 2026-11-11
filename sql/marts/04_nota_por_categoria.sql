WITH nota_pedido AS (
    SELECT order_id, avg(review_score) AS nota
    FROM refined.avaliacoes
    GROUP BY order_id
),
categoria_pedido AS (
    SELECT DISTINCT
        i.order_id,
        coalesce(t.product_category_name_english,
                 pr.product_category_name,
                 'sem_categoria') AS categoria
    FROM refined.itens_pedido             AS i
    JOIN refined.produtos                 AS pr ON pr.product_id = i.product_id
    LEFT JOIN refined.traducao_categorias AS t  ON t.product_category_name = pr.product_category_name
),
por_categoria AS (
    SELECT
        c.categoria,
        count(*)              AS pedidos_avaliados,
        round(avg(n.nota), 2) AS nota_media
    FROM categoria_pedido AS c
    JOIN nota_pedido      AS n ON n.order_id = c.order_id
    GROUP BY c.categoria
    HAVING count(*) >= 100
)
SELECT
    categoria,
    pedidos_avaliados,
    nota_media,
    rank() OVER (ORDER BY nota_media) AS posicao_pior
FROM por_categoria
ORDER BY posicao_pior;
