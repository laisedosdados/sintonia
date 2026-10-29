"""Testes com músicas sintéticas (não precisam de internet).

Rodar:  python -m pytest -q
"""
import numpy as np
import pytest

from sintonia import banco
from sintonia.caracteristicas import extrair
from sintonia.recomendador import Recomendador
from tests.sintetico import MELODIA_PASSOS, MELODIA_SALTOS, musica


def _melodia_aleatoria(seed: int, saltos: bool) -> list[int]:
    rng = np.random.default_rng(seed)
    passos = rng.choice([-7, -5, 5, 7, 9, -9] if saltos else [-2, -1, 1, 2, 0], size=15)
    notas = [64]
    for p in passos:
        notas.append(int(np.clip(notas[-1] + p, 52, 76)))
    return notas * 3


@pytest.fixture(scope="module")
def catalogo(tmp_path_factory):
    caminho = tmp_path_factory.mktemp("db") / "catalogo.db"
    con = banco.conectar(caminho)
    configs = []
    for i, (mel, nome) in enumerate([(MELODIA_PASSOS, "passos"), (MELODIA_SALTOS, "saltos")]):
        for transpor, bpm, menor in [(0, 80, False), (3, 130, True), (-4, 100, False)]:
            configs.append((f"{nome}_{transpor}_{bpm}", mel, transpor, bpm, menor))
    for s in range(6):
        configs.append((f"aleatoria_{s}", _melodia_aleatoria(s, saltos=s % 2 == 1), 0, 90 + 10 * s, s % 2 == 0))
    for nome, mel, transpor, bpm, menor in configs:
        feats, info = extrair(musica(melodia=mel, transpor=transpor, bpm=bpm, menor=menor))
        faixa = {"id": f"teste:{nome}", "fonte": "teste", "id_externo": nome, "titulo": nome,
                 "artista": f"artista {nome}"}
        banco.salvar_musica(con, faixa, feats, info, "sintetico")
    con.close()
    return caminho


def test_melodia_nao_depende_do_tom():
    fa, _ = extrair(musica(transpor=0))
    fb, _ = extrair(musica(transpor=5))
    fc, _ = extrair(musica(melodia=MELODIA_SALTOS))
    chaves = [k for k in fa["melodia"] if k.startswith(("mel_int", "mel_ctr", "mel_fourier"))]
    v = lambda f: np.array([f["melodia"][k] for k in chaves])
    assert np.linalg.norm(v(fa) - v(fb)) < 0.2 * np.linalg.norm(v(fa) - v(fc))


def test_saltos_detectados():
    fa, _ = extrair(musica(melodia=MELODIA_PASSOS))
    fc, _ = extrair(musica(melodia=MELODIA_SALTOS))
    assert fc["melodia"]["mel_saltos"] > 0.5 > fa["melodia"]["mel_saltos"]


def test_banco_ida_e_volta(catalogo):
    con = banco.conectar(catalogo)
    assert len(banco.ler_musicas(con)) == 12
    assert banco.ler_caracteristicas(con).shape[0] == 12
    con.close()


def test_peso_na_melodia_acha_mesma_melodia(catalogo):
    rec = Recomendador.do_banco(catalogo)
    # semente: melodia "passos" num tom e andamento que não existem no catálogo
    feats, _ = extrair(musica(melodia=MELODIA_PASSOS, transpor=2, bpm=115, menor=True))
    res, avisos = rec.recomendar(feats, {"melodia": 1.0}, n=3)
    assert not avisos
    assert all(t.startswith("passos") for t in res["titulo"]), res["titulo"].tolist()
    assert res["explicacao"].str.len().min() > 0


def test_peso_no_ritmo_acha_mesmo_andamento(catalogo):
    rec = Recomendador.do_banco(catalogo)
    feats, _ = extrair(musica(melodia=MELODIA_SALTOS, transpor=1, bpm=130, menor=False))
    res, _ = rec.recomendar(feats, {"ritmo": 1.0}, n=2)
    assert any("_130" in t for t in res["titulo"]), res["titulo"].tolist()


def test_sem_voz_avisa(catalogo):
    rec = Recomendador.do_banco(catalogo)
    m = musica()
    m["voz"] = np.zeros_like(m["voz"])
    feats, info = extrair(m)
    assert not info["tem_voz"]
    res, avisos = rec.recomendar(feats, {"melodia": 1.0, "harmonia": 0.5}, n=3)
    assert avisos and len(res) == 3


def test_exportar(catalogo, tmp_path):
    from sintonia.exportar import exportar
    gerados = exportar(catalogo, tmp_path / "nao_existe.db", tmp_path)
    nomes = {g.name for g in gerados}
    assert {"musicas.csv", "caracteristicas.csv", "mapa.csv"} <= nomes


# ------------------------------------------------------------ idioma, links e banco antigo
def test_grupo_idioma():
    from sintonia.idioma import grupo
    assert grupo("en", 0.9, 1) == "Inglês"
    assert grupo("ko", 0.8, 1) == "Coreano"
    assert grupo("fr", 0.9, 1) == "Outros idiomas"
    assert grupo("en", 0.2, 1) == "Não identificado"
    assert grupo(None, None, 1) == "Não identificado"
    assert grupo(float("nan"), float("nan"), 1) == "Não identificado"
    assert grupo("en", 0.9, 0) == "Instrumental"


def test_filtro_por_idioma(catalogo):
    con = banco.conectar(catalogo)
    ids = [r[0] for r in con.execute("SELECT id FROM musicas ORDER BY id")]
    for i, mid in enumerate(ids):
        banco.salvar_idioma(con, mid, ["en", "ja", "pt"][i % 3], 0.95)
    con.close()
    rec = Recomendador.do_banco(catalogo)
    feats, _ = extrair(musica(melodia=MELODIA_PASSOS, transpor=2, bpm=115))
    res, _ = rec.recomendar(feats, {"melodia": 1.0}, n=10, idiomas=["Japonês"])
    assert len(res) > 0 and set(res["grupo_idioma"]) == {"Japonês"}
    res, _ = rec.recomendar(feats, {"melodia": 1.0}, n=10, idiomas=[])
    assert res.empty
    assert rec.contagem_idiomas().sum() == len(ids)


def test_links():
    from sintonia.links import plataformas
    deezer = dict(plataformas("deezer", "Blinding Lights", "The Weeknd", "https://www.deezer.com/track/1"))
    assert set(deezer) == {"YouTube", "YouTube Music", "Spotify", "Deezer"}
    assert deezer["Deezer"] == "https://www.deezer.com/track/1"
    assert "Blinding+Lights+The+Weeknd" in deezer["YouTube"]
    jam = dict(plataformas("jamendo", "Canção", "Artista", "https://www.jamendo.com/track/9"))
    assert jam["Jamendo"] == "https://www.jamendo.com/track/9" and "deezer.com/search" in jam["Deezer"]


def test_banco_antigo_ganha_coluna_idioma(tmp_path):
    import sqlite3
    caminho = tmp_path / "antigo.db"
    velho = sqlite3.connect(caminho)
    velho.execute("CREATE TABLE musicas (id TEXT PRIMARY KEY, fonte TEXT, id_externo TEXT, titulo TEXT, "
                  "artista TEXT, album TEXT, capa_url TEXT, link TEXT, duracao REAL, segundos_analisados REAL, "
                  "tem_voz INTEGER, n_notas INTEGER, tom TEXT, separador TEXT, analisado_em TEXT)")
    velho.execute("INSERT INTO musicas (id, titulo, tem_voz) VALUES ('deezer:1', 'x', 1)")
    velho.commit(); velho.close()
    con = banco.conectar(caminho)
    banco.salvar_idioma(con, "deezer:1", "es", 0.88)
    assert con.execute("SELECT idioma, idioma_conf FROM musicas").fetchone() == ("es", 0.88)


def test_gostou_por_musica(tmp_path):
    import pandas as pd
    con = banco.conectar(tmp_path / "uso.db")
    bid = banco.registrar_busca(con, {"id": "s", "titulo": "t", "artista": "a"}, ["voz"], {"melodia": 1}, ["deezer"])
    recs = pd.DataFrame({"titulo": ["A"], "artista": ["x"], "fonte": ["deezer"], "parecida": [0.8],
                         "explicacao": ["e"]}, index=["deezer:1"])
    banco.registrar_recomendacoes(con, bid, recs)
    banco.registrar_gostou(con, bid, "deezer:1", True)
    banco.registrar_gostou(con, bid, "deezer:2", False, {"titulo": "B", "parecida": 0.5})
    linhas = con.execute("SELECT posicao, musica_id, gostou FROM recomendacoes ORDER BY posicao").fetchall()
    assert linhas == [(1, "deezer:1", 1), (2, "deezer:2", 0)]
