"""Leitura e gravação no banco SQLite (veja sql/schema.sql)."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
SCHEMA = RAIZ / "sql" / "schema.sql"
CATALOGO_PADRAO = RAIZ / "dados" / "catalogo.db"
USO_PADRAO = RAIZ / "dados" / "uso.db"


def agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def conectar(caminho: str | Path = CATALOGO_PADRAO) -> sqlite3.Connection:
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(caminho), check_same_thread=False)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    _migrar(con)
    return con


def _migrar(con: sqlite3.Connection) -> None:
    """Adiciona colunas novas em bancos criados por versões antigas do projeto."""
    colunas = {linha[1] for linha in con.execute("PRAGMA table_info(musicas)")}
    for nome, tipo in (("idioma", "TEXT"), ("idioma_conf", "REAL"), ("genero", "TEXT"), ("generos", "TEXT")):
        if nome not in colunas:
            con.execute(f"ALTER TABLE musicas ADD COLUMN {nome} {tipo}")
    con.commit()


# ---------------------------------------------------------------- catálogo
def ja_processada(con: sqlite3.Connection, musica_id: str) -> bool:
    q = "SELECT 1 FROM musicas WHERE id=? UNION SELECT 1 FROM falhas WHERE id=?"
    return con.execute(q, (musica_id, musica_id)).fetchone() is not None


def salvar_musica(con: sqlite3.Connection, faixa: dict, feats: dict[str, dict[str, float]],
                  info: dict, separador: str) -> None:
    con.execute(
        """INSERT OR REPLACE INTO musicas (id, fonte, id_externo, titulo, artista, album, capa_url,
           link, duracao, segundos_analisados, tem_voz, n_notas, tom, separador, analisado_em,
           idioma, idioma_conf)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (faixa["id"], faixa["fonte"], faixa["id_externo"], faixa["titulo"], faixa["artista"],
         faixa.get("album", ""), faixa.get("capa_url", ""), faixa.get("link", ""),
         faixa.get("duracao", 0), info["duracao"], int(info["tem_voz"]), info["n_notas"],
         info.get("tom", ""), separador, agora(), info.get("idioma"), info.get("idioma_conf")),
    )
    con.execute("DELETE FROM caracteristicas WHERE musica_id=?", (faixa["id"],))
    linhas = [(faixa["id"], aspecto, nome, None if valor != valor else float(valor))  # NaN -> NULL
              for aspecto, d in feats.items() for nome, valor in d.items()]
    con.executemany("INSERT INTO caracteristicas VALUES (?,?,?,?)", linhas)
    con.commit()


def salvar_idioma(con: sqlite3.Connection, musica_id: str, codigo: str, confianca: float) -> None:
    con.execute("UPDATE musicas SET idioma=?, idioma_conf=? WHERE id=?", (codigo, float(confianca), musica_id))
    con.commit()


def salvar_genero(con: sqlite3.Connection, musica_id: str, genero: str, generos: str = "") -> None:
    con.execute("UPDATE musicas SET genero=?, generos=? WHERE id=?", (genero, generos, musica_id))
    con.commit()


def registrar_falha(con: sqlite3.Connection, musica_id: str, motivo: str) -> None:
    con.execute("INSERT OR REPLACE INTO falhas VALUES (?,?,?)", (musica_id, motivo[:500], agora()))
    con.commit()


def ler_musicas(con: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql("SELECT * FROM musicas", con).set_index("id")


def ler_caracteristicas(con: sqlite3.Connection) -> pd.DataFrame:
    """Tabela "larga": uma linha por música, uma coluna por característica."""
    longo = pd.read_sql("SELECT musica_id, nome, valor FROM caracteristicas", con)
    if longo.empty:
        return pd.DataFrame()
    return longo.pivot(index="musica_id", columns="nome", values="valor").astype(float)


# ---------------------------------------------------------------- uso do app
def registrar_busca(con: sqlite3.Connection, musica: dict, partes: list[str],
                    pesos: dict[str, float], fontes: list[str]) -> int:
    cur = con.execute(
        """INSERT INTO buscas (quando, musica_id, titulo, artista, partes_marcadas, peso_melodia,
           peso_voz, peso_ritmo, peso_harmonia, peso_som, fontes) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (agora(), musica.get("id"), musica.get("titulo"), musica.get("artista"), ",".join(partes),
         pesos.get("melodia", 0), pesos.get("voz", 0), pesos.get("ritmo", 0),
         pesos.get("harmonia", 0), pesos.get("som", 0), ",".join(fontes)),
    )
    con.commit()
    return int(cur.lastrowid)


def registrar_recomendacoes(con: sqlite3.Connection, busca_id: int, recs: pd.DataFrame) -> None:
    linhas = []
    for pos, (mid, r) in enumerate(recs.iterrows(), start=1):
        linhas.append((busca_id, pos, mid, r.get("titulo"), r.get("artista"), r.get("fonte"),
                       float(r["parecida"]),
                       *[None if pd.isna(r.get(f"parecida_{a}")) else float(r.get(f"parecida_{a}"))
                         for a in ("melodia", "voz", "ritmo", "harmonia", "som")],
                       r.get("explicacao"), None))
    con.executemany("INSERT OR REPLACE INTO recomendacoes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", linhas)
    con.commit()


def registrar_gostou(con: sqlite3.Connection, busca_id: int, musica_id: str, gostou: bool,
                     linha: dict | None = None) -> None:
    """Guarda o 👍/👎. Se a música não estava na lista registrada (ex.: apareceu
    depois de filtrar por idioma), ela é acrescentada no fim."""
    cur = con.execute("UPDATE recomendacoes SET gostou=? WHERE busca_id=? AND musica_id=?",
                      (int(gostou), busca_id, musica_id))
    if cur.rowcount == 0:
        linha = linha or {}
        pos = con.execute("SELECT COALESCE(MAX(posicao), 0) + 1 FROM recomendacoes WHERE busca_id=?",
                          (busca_id,)).fetchone()[0]
        con.execute("""INSERT INTO recomendacoes (busca_id, posicao, musica_id, titulo, artista, fonte,
                       parecida, explicacao, gostou) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (busca_id, pos, musica_id, linha.get("titulo"), linha.get("artista"), linha.get("fonte"),
                     linha.get("parecida"), linha.get("explicacao"), int(gostou)))
    con.commit()
