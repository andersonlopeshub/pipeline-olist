Etapa 2 do pipeline Olist: passagem de raw para refined.

Execução:
    uv run python -m pipeline.refinamento

Lê de raw, escreve em refined. Nunca escreve em raw.

1. TABELAS E NOMES
   Tabelas que entram: todas as nove.
   Tabelas que ficam de fora: nenhuma.
   Nomes: mantidos os originais, com uma exceção. Em produtos, as colunas
   product_name_lenght e product_description_lenght têm erro de digitação
   ("lenght"), e são renomeadas para product_name_length e
   product_description_length. O mapa completo está em TABELAS, abaixo.
   Por quê: manter o nome do dataset original facilita conferir a fonte. A
   única renomeação é a correção de um erro de escrita, não de convenção.

2. TIPOS
   Datas com hora:   TIMESTAMP. Declarado: aceita date_trunc e extract.
                     Por quê: o dado tem hora (compra, aprovação, envio).
                     Converter para DATE jogaria a hora fora.
   Datas sem hora:   DATE. Só em order_estimated_delivery_date, em que todo
                     valor é meia-noite. Valor com hora vira falha (item 3).
                     review_creation_date é TIMESTAMP, não DATE: 85 valores
                     estão às 01:00:00 (84 em 2017-10-15, 1 em 2016-10-16),
                     dias de início do horário de verão, em que a meia-noite
                     não existiu. Decisão: mudar o tipo, não corrigir o dado.
   Dinheiro:         DECIMAL(10,2). Motivo: é o tipo do dinheiro. Valor com
                     mais de duas casas decimais vira falha, não é
                     arredondado em silêncio.
   Contagens e medidas: INTEGER. Inclui parcelas, sequências, notas, quantidade
                     de fotos, tamanhos de texto, peso (g) e dimensões (cm).
   Coordenadas (lat, lng): DOUBLE. Não é contagem nem dinheiro; é número
                     real com casas decimais.
   CEP e outros identificadores que parecem número: VARCHAR. Motivo: compara
                     e ordena letra a letra, e preserva o zero à esquerda.
   Demais textos e IDs: VARCHAR.

3. CONVERSÃO QUE FALHA
   Para tudo. Todas as conversões são validadas antes de qualquer tabela ser
   gravada. Se alguma coluna tiver valor que não converte, o script mostra
   coluna, tipo, quantidade de valores problemáticos e exemplos, não grava
   nada no refined e sai com sys.exit(1).
   Solução proposta para cada falha: decidir se o valor é erro de origem
   (corrigir na etapa e registrar) ou se o tipo declarado está errado (mudar
   o tipo e registrar). Essa decisão é sua; o script não resolve sozinho.
   Por quê: converter o que dá e descartar o resto é a corrupção silenciosa
   que a etapa 1 existe para impedir.

4. DUPLICATAS
   Chaves:
     pedidos              order_id
     itens_pedido         order_id, order_item_id
     pagamentos           order_id, payment_sequential
     avaliacoes           review_id, order_id
     clientes             customer_id
     vendedores           seller_id
     produtos             product_id
     traducao_categorias  product_category_name
     geolocalizacao       sem chave: nenhuma coluna identifica a linha
   Observação: avaliacoes.review_id sozinho se repete (789 casos), porque uma
   mesma avaliação pode estar ligada a mais de um pedido. Com review_id +
   order_id a chave é única.
   Relatório: para cada tabela, o script mostra antes de gravar: quantas linhas
   têm chave repetida, quantas com conteúdo idêntico e quantas com conteúdo
   diferente. Geolocalização: mostra quantas linhas são exatamente iguais.
   Nada é removido. Não há decisão de deduplicação nesta versão da spec.
   Por quê: a regra de dedup depende de você, e o relatório existe para
   você decidir com o número na frente.

5. NULOS
   Regra geral: NULL continua NULL. Nada é preenchido, substituído ou
   inferido.
   Exceções: nenhuma.
   Por quê: preencher nulo inventa dado. O relatório mostra a contagem de
   nulos por coluna para cada tabela.

6. SAÍDA NA TELA
   Por tabela: nome qualificado, linhas gravadas (contadas no banco), chave e
   relatório de duplicatas, e contagem de nulos das colunas que têm nulo.
   Ao final: total de linhas. stdout reconfigurado para utf-8.

7. REEXECUÇÃO E ERRO
   CREATE OR REPLACE, nunca acrescenta: rodar de novo dá o mesmo resultado.
   Faltando tabela em raw: lista quais faltam, manda rodar a ingestão
   (uv run python -m pipeline.ingestao), e sai com sys.exit(1) sem gravar.

CRITÉRIOS DE ACEITE
- Todas as nove tabelas aparecem em refined, com os tipos da seção 2.
- Nenhuma linha se perde: contagem de refined igual à de raw, tabela por
  tabela.
- Nenhuma conversão falha em silêncio: um valor ruim interrompe antes de
  qualquer gravação.
- Rodar duas vezes seguidas imprime a mesma coisa.

ASSUMIDO (não estava na spec em forma fechada)
- Nomes: manteve os originais; corrigiu só os dois erros de "lenght".
- Timestamps com hora viraram TIMESTAMP, não DATE, para não perder a hora.
- review_creation_date era DATE na spec; virou TIMESTAMP porque 85 valores
  têm hora 01:00:00 (início do horário de verão). Decidido pelo dono da spec.
- Coordenadas viraram DOUBLE, não INTEGER nem DECIMAL.
- Duplicatas: só relatório, sem remoção.
- Chaves escolhidas por mim a partir dos dados (ver seção 4).
