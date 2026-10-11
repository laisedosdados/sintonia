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
