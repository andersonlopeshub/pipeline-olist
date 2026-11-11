-- Quantas pessoas compram de cada UF?
-- Grão: uma UF. A coluna clientes não soma: 39 pessoas aparecem em mais de uma UF.
SELECT
    customer_state                     AS uf,
    count(DISTINCT customer_unique_id) AS clientes
FROM refined.clientes
GROUP BY uf
ORDER BY clientes DESC;
