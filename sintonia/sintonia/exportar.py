"""Exporta o banco para arquivos CSV que o Power BI abre direto.

Uso:  python -m sintonia.exportar
Gera em powerbi/dados/:
  musicas.csv                 uma linha por música do catálogo
  caracteristicas.csv         as características com nome amigável (formato longo)
  mapa.csv                    posição de cada música num "mapa" 2D, por aspecto
  buscas.csv, recomendacoes.csv   uso do app (se existir dados/uso.db)
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from . import banco
from .caracteristicas import ASPECTOS
from .descricoes import ASPECTO_INFO, ROTULOS, aspecto_de
from .recomendador import Recomendador

SAIDA_PADRAO = banco.RAIZ / "powerbi" / "dados"


def _projeta_2d(M: np.ndarray) -> np.ndarray:
    """Reduz muitas colunas para 2 (x, y). Usa UMAP se instalado, senão PCA."""
    if len(M) < 5:
        return np.zeros((len(M), 2))
    try:
        import umap
        return umap.UMAP(n_neighbors=min(15, len(M) - 1), random_state=42).fit_transform(M)
    except Exception:
        from sklearn.decomposition import PCA
        return PCA(n_components=2, random_state=42).fit_transform(M)


def mapa(rec: Recomendador) -> pd.DataFrame:
    partes = []
    blocos = {a: rec.colunas[a] for a in ASPECTOS}
    blocos["geral"] = [c for a in ASPECTOS for c in rec.colunas[a]]
    for nome, cols in blocos.items():
        Z = rec.Z[cols]
        ok = Z.notna().mean(axis=1) > 0.5
        if ok.sum() < 5:
            continue
        M = Z[ok].fillna(0).to_numpy() * rec.peso_coluna[cols].to_numpy()
        xy = _projeta_2d(M)
        partes.append(pd.DataFrame({"musica_id": Z.index[ok], "aspecto": nome, "x": xy[:, 0], "y": xy[:, 1]}))
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


def exportar(caminho_db=banco.CATALOGO_PADRAO, caminho_uso=banco.USO_PADRAO, saida=SAIDA_PADRAO) -> list[Path]:
    saida = Path(saida)
    saida.mkdir(parents=True, exist_ok=True)
    rec = Recomendador.do_banco(caminho_db)
    gerados = []

    m = rec.musicas.reset_index().rename(columns={"index": "id"})
    m.to_csv(saida / "musicas.csv", index=False, encoding="utf-8-sig")
    gerados.append(saida / "musicas.csv")

    cols = [c for c in ROTULOS if c in rec.X.columns]
    longo = rec.X[cols].stack().rename("valor").reset_index()
    longo.columns = ["musica_id", "nome", "valor"]
    longo["z"] = rec.Z[cols].stack().reindex(pd.MultiIndex.from_frame(longo[["musica_id", "nome"]])).to_numpy()
    longo["aspecto"] = longo["nome"].map(lambda n: ASPECTO_INFO[aspecto_de(n)]["nome"])
    longo["caracteristica"] = longo["nome"].map(ROTULOS)
    longo.to_csv(saida / "caracteristicas.csv", index=False, encoding="utf-8-sig")
    gerados.append(saida / "caracteristicas.csv")

    mp = mapa(rec)
    mp.to_csv(saida / "mapa.csv", index=False, encoding="utf-8-sig")
    gerados.append(saida / "mapa.csv")

    if Path(caminho_uso).exists():
        con = sqlite3.connect(str(caminho_uso))
        for tabela in ("buscas", "recomendacoes"):
            try:
                pd.read_sql(f"SELECT * FROM {tabela}", con).to_csv(saida / f"{tabela}.csv", index=False,
                                                                  encoding="utf-8-sig")
                gerados.append(saida / f"{tabela}.csv")
            except Exception:
                pass
        con.close()
    return gerados


def main() -> None:
    p = argparse.ArgumentParser(description="Exporta CSVs para o Power BI")
    p.add_argument("--db", default=str(banco.CATALOGO_PADRAO))
    p.add_argument("--uso", default=str(banco.USO_PADRAO))
    p.add_argument("--saida", default=str(SAIDA_PADRAO))
    a = p.parse_args()
    for g in exportar(a.db, a.uso, a.saida):
        print("gerado:", g)


if __name__ == "__main__":
    main()
