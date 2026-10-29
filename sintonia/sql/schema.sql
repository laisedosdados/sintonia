-- Estrutura do banco de dados do Sintonia (SQLite)
-- Dois arquivos: dados/catalogo.db (músicas analisadas) e dados/uso.db (buscas no app)

-- ============================================================ catálogo
-- Uma linha por música analisada
CREATE TABLE IF NOT EXISTS musicas (
    id                  TEXT PRIMARY KEY,      -- "deezer:123" ou "jamendo:456"
    fonte               TEXT NOT NULL,         -- deezer | jamendo
    id_externo          TEXT NOT NULL,
    titulo              TEXT,
    artista             TEXT,
    album               TEXT,
    capa_url            TEXT,
    link                TEXT,
    duracao             REAL,                  -- duração da música inteira (s)
    segundos_analisados REAL,                  -- 30 no Deezer; inteira no Jamendo
    tem_voz             INTEGER,               -- 1 se achou melodia cantada
    n_notas             INTEGER,
    tom                 TEXT,                  -- ex.: "Lá menor" (estimado)
    separador           TEXT,                  -- demucs | leve
    analisado_em        TEXT,
    idioma              TEXT,                  -- código do Whisper: pt, en, es, ja, ko... (NULL = não detectado)
    idioma_conf         REAL                   -- confiança da detecção, de 0 a 1
);

-- Formato "longo": uma linha por (música, característica).
-- Facilita consultas SQL e gráficos no Power BI.
CREATE TABLE IF NOT EXISTS caracteristicas (
    musica_id TEXT NOT NULL REFERENCES musicas(id),
    aspecto   TEXT NOT NULL,                   -- melodia | voz | ritmo | harmonia | som
    nome      TEXT NOT NULL,                   -- ex.: mel_saltos
    valor     REAL,
    PRIMARY KEY (musica_id, nome)
);
CREATE INDEX IF NOT EXISTS idx_carac_aspecto ON caracteristicas(aspecto, nome);

-- Músicas que falharam (sem áudio, erro de download...), para não tentar de novo
CREATE TABLE IF NOT EXISTS falhas (
    id     TEXT PRIMARY KEY,
    motivo TEXT,
    quando TEXT
);

-- ============================================================ uso do app
CREATE TABLE IF NOT EXISTS buscas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    quando          TEXT,
    musica_id       TEXT,                      -- música escolhida pela pessoa
    titulo          TEXT,
    artista         TEXT,
    partes_marcadas TEXT,                      -- partes do teste de escuta: "voz,batida"
    peso_melodia    REAL,
    peso_voz        REAL,
    peso_ritmo      REAL,
    peso_harmonia   REAL,
    peso_som        REAL,
    fontes          TEXT                       -- de onde vieram as recomendações
);

CREATE TABLE IF NOT EXISTS recomendacoes (
    busca_id        INTEGER REFERENCES buscas(id),
    posicao         INTEGER,
    musica_id       TEXT,
    titulo          TEXT,
    artista         TEXT,
    fonte           TEXT,
    parecida        REAL,                      -- 0 a 1
    parecida_melodia  REAL,
    parecida_voz      REAL,
    parecida_ritmo    REAL,
    parecida_harmonia REAL,
    parecida_som      REAL,
    explicacao      TEXT,
    gostou          INTEGER,                   -- 1 = 👍, 0 = 👎, NULL = sem resposta
    PRIMARY KEY (busca_id, posicao)
);
