-- 002: views do motor de saldo. Nada aqui é gravado.

-- Cada assunto, de qualquer árvore, resolvido para o(s) assunto(s) da árvore
-- ativa pelo topic_map. Assunto sem caminho até a árvore ativa fica com ele
-- mesmo e ativo = 0. Se um assunto foi dividido em dois, aparece duas vezes.
CREATE VIEW v_topico_atual AS
WITH RECURSIVE r(origem_id, topic_id, profundidade) AS (
  SELECT id, id, 0 FROM topics
  UNION
  SELECT r.origem_id, m.to_topic_id, r.profundidade + 1
  FROM r JOIN topic_map m ON m.from_topic_id = r.topic_id
  WHERE r.profundidade < 20
),
ativos AS (
  SELECT DISTINCT r.origem_id, r.topic_id AS atual_id
  FROM r
  JOIN topics t ON t.id = r.topic_id
  JOIN topic_trees tt ON tt.id = t.tree_id
  WHERE tt.ativa = 1
)
SELECT origem_id, atual_id, 1 AS ativo FROM ativos
UNION ALL
SELECT id, id, 0 FROM topics WHERE id NOT IN (SELECT origem_id FROM ativos);

-- Tentativa com tudo o que é derivado: acerto (do gabarito, nulo em branco),
-- pontos no modelo Cebraspe (+1, -1, 0) e se conta como erro para revisão
-- (errado ou chute_certo).
CREATE VIEW v_tentativas AS
SELECT
  a.id                    AS attempt_id,
  a.item_id,
  i.fonte,
  i.referencia,
  a.data,
  a.resposta,
  i.gabarito,
  a.confianca,
  a.confianca_explicita,
  a.tipo_erro,
  a.tempo_s,
  a.tempo_origem,
  i.topic_id              AS topico_original,
  ta.atual_id             AS topico,
  tc.atual_id             AS topico_confundido,
  CASE WHEN a.resposta = 'B' THEN NULL
       WHEN a.resposta = i.gabarito THEN 1 ELSE 0 END AS acerto,
  CASE WHEN a.resposta = 'B' THEN 0
       WHEN a.resposta = i.gabarito THEN 1 ELSE -1 END AS pontos,
  CASE WHEN a.resposta = 'B' THEN NULL
       WHEN a.resposta <> i.gabarito OR a.tipo_erro = 'chute_certo' THEN 1
       ELSE 0 END AS erro_revisao
FROM attempts a
JOIN items i ON i.id = a.item_id
LEFT JOIN v_topico_atual ta ON ta.origem_id = i.topic_id
LEFT JOIN v_topico_atual tc ON tc.origem_id = a.topic_id_confundido;

-- Par perigoso simétrico: (A, B) e (B, A) são o mesmo par.
CREATE VIEW v_pares AS
WITH pares AS (
  SELECT MIN(topico, topico_confundido) AS topico_a,
         MAX(topico, topico_confundido) AS topico_b,
         COUNT(*) AS erros_confusao,
         MAX(data) AS ultimo_erro
  FROM v_tentativas
  WHERE tipo_erro = 'confusao' AND topico IS NOT NULL
  GROUP BY 1, 2
)
SELECT p.topico_a, p.topico_b, p.erros_confusao, p.ultimo_erro,
       (SELECT COUNT(*) FROM v_tentativas t
         WHERE t.topico IN (p.topico_a, p.topico_b)) AS tentativas_no_par
FROM pares p;
