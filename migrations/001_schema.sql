-- 001: tabelas e constraints.
-- Regra 5 do SPEC: nenhuma coluna guarda métrica derivada. Acerto, saldo,
-- reincidência e prioridade saem de views (002) ou de consulta.

-- Árvore de assuntos versionada. Edital novo = árvore nova + topic_map.
CREATE TABLE topic_trees (
  id         INTEGER PRIMARY KEY,
  nome       TEXT NOT NULL UNIQUE,
  criada_em  TEXT NOT NULL,
  ativa      INTEGER NOT NULL CHECK (ativa IN (0, 1))
) STRICT;
CREATE UNIQUE INDEX uma_arvore_ativa ON topic_trees(ativa) WHERE ativa = 1;

CREATE TABLE topics (
  id          INTEGER PRIMARY KEY,
  tree_id     INTEGER NOT NULL REFERENCES topic_trees(id),
  disciplina  TEXT NOT NULL,
  codigo      TEXT NOT NULL,
  nome        TEXT NOT NULL,
  parent_id   INTEGER REFERENCES topics(id),
  UNIQUE (tree_id, codigo)
) STRICT;

CREATE TABLE topic_aliases (
  topic_id  INTEGER NOT NULL REFERENCES topics(id),
  alias     TEXT NOT NULL COLLATE NOCASE,
  PRIMARY KEY (topic_id, alias)
) STRICT;

-- Mapeamento entre árvores. As tentativas antigas nunca são reescritas.
CREATE TABLE topic_map (
  from_topic_id  INTEGER NOT NULL REFERENCES topics(id),
  to_topic_id    INTEGER NOT NULL REFERENCES topics(id),
  PRIMARY KEY (from_topic_id, to_topic_id),
  CHECK (from_topic_id <> to_topic_id)
) STRICT;

CREATE TABLE items (
  id          INTEGER PRIMARY KEY,
  fonte       TEXT NOT NULL,                    -- identificador da prova
  referencia  TEXT NOT NULL,                    -- número do item na prova
  banca       TEXT NOT NULL DEFAULT 'cebraspe',
  ano         INTEGER CHECK (ano BETWEEN 1990 AND 2100),
  orgao       TEXT,
  cargo       TEXT,
  gabarito    TEXT NOT NULL CHECK (gabarito IN ('C', 'E')),
  topic_id    INTEGER REFERENCES topics(id),    -- nulo = fila de classificação
  enunciado   TEXT,                             -- nulo = item em esboço
  criado_em   TEXT NOT NULL,
  UNIQUE (fonte, referencia)
) STRICT;

CREATE TABLE attempts (
  id                   INTEGER PRIMARY KEY,
  item_id              INTEGER NOT NULL REFERENCES items(id),
  data                 TEXT NOT NULL,
  resposta             TEXT NOT NULL CHECK (resposta IN ('C', 'E', 'B')),  -- B = branco
  confianca            INTEGER NOT NULL CHECK (confianca BETWEEN 0 AND 3),
  confianca_explicita  INTEGER NOT NULL CHECK (confianca_explicita IN (0, 1)),
  tempo_s              INTEGER CHECK (tempo_s > 0),
  tempo_origem         TEXT CHECK (tempo_origem IN ('cli_intervalo', 'cronometro', 'estimado')),
  tipo_erro            TEXT CHECK (tipo_erro IN
                         ('nao_sabia', 'confusao', 'enunciado', 'pressa', 'chute_certo')),
  topic_id_confundido  INTEGER REFERENCES topics(id),
  nota                 TEXT,
  CHECK ((tempo_s IS NULL) = (tempo_origem IS NULL)),
  CHECK ((COALESCE(tipo_erro, '') = 'confusao') = (topic_id_confundido IS NOT NULL))
) STRICT;
CREATE INDEX attempts_item ON attempts(item_id);

-- Coerência entre resposta, gabarito e tipo de erro. CHECK não lê outra
-- tabela, por isso trigger. Branco: sem tipo. Certo: sem tipo ou chute_certo.
-- Errado: tipo obrigatório e diferente de chute_certo.
CREATE TRIGGER attempts_tipo_coerente_ins BEFORE INSERT ON attempts
BEGIN
  SELECT RAISE(ABORT, 'tipo_erro incompatível com resposta e gabarito')
  FROM items i WHERE i.id = NEW.item_id AND (
       (NEW.resposta = 'B' AND NEW.tipo_erro IS NOT NULL)
    OR (NEW.resposta = i.gabarito AND NEW.tipo_erro IS NOT NULL
        AND NEW.tipo_erro <> 'chute_certo')
    OR (NEW.resposta NOT IN ('B', i.gabarito)
        AND (NEW.tipo_erro IS NULL OR NEW.tipo_erro = 'chute_certo')));
END;

CREATE TRIGGER attempts_tipo_coerente_upd BEFORE UPDATE ON attempts
BEGIN
  SELECT RAISE(ABORT, 'tipo_erro incompatível com resposta e gabarito')
  FROM items i WHERE i.id = NEW.item_id AND (
       (NEW.resposta = 'B' AND NEW.tipo_erro IS NOT NULL)
    OR (NEW.resposta = i.gabarito AND NEW.tipo_erro IS NOT NULL
        AND NEW.tipo_erro <> 'chute_certo')
    OR (NEW.resposta NOT IN ('B', i.gabarito)
        AND (NEW.tipo_erro IS NULL OR NEW.tipo_erro = 'chute_certo')));
END;
