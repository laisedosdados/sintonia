"""Gênero musical e informações de cada música (álbum, ano, gravadora...).

O gênero vem do próprio Deezer ou Jamendo, que classificam cada álbum.
Quando a música não tem essa informação (ex.: um arquivo enviado), o app
estima o gênero pelo som, olhando as músicas mais parecidas do catálogo.

Para preencher o gênero das músicas do catálogo:

    python -m sintonia.generos --db dados/catalogo.db
"""
from __future__ import annotations

import argparse
import time

from . import banco, fontes

SEM_GENERO = "Sem gênero informado"

# nomes que o Deezer e o Jamendo usam -> nome em português
TRADUCAO = {
    "alternative": "Alternativo", "alternativo": "Alternativo", "indie": "Indie",
    "electro": "Eletrônica", "electronic": "Eletrônica", "eletrônica": "Eletrônica", "dance": "Dance",
    "rap/hip hop": "Rap/Hip Hop", "hiphop": "Rap/Hip Hop", "hip hop": "Rap/Hip Hop", "rap": "Rap/Hip Hop",
    "r&b": "R&B", "rnb": "R&B", "soul & funk": "Soul & Funk", "soul": "Soul & Funk", "funk": "Soul & Funk",
    "brazilian music": "Música brasileira", "música brasileira": "Música brasileira", "mpb": "MPB",
    "latin music": "Música latina", "latin": "Música latina", "latino": "Música latina",
    "asian music": "Música asiática", "k-pop": "K-pop", "j-pop": "J-pop",
    "african music": "Música africana", "world": "World music",
    "films/games": "Trilhas sonoras", "soundtrack": "Trilhas sonoras", "film scores": "Trilhas sonoras",
    "classical": "Clássica", "classical music": "Clássica", "kids": "Infantil", "children": "Infantil",
    "singersongwriter": "Cantor e compositor", "acoustic": "Acústico", "ambient": "Ambiente",
    "chillout": "Chillout", "lounge": "Lounge", "relaxation": "Relaxante", "religious": "Religiosa",
    "christian": "Gospel", "gospel": "Gospel", "metal": "Metal", "punk": "Punk", "rock": "Rock",
    "pop": "Pop", "folk": "Folk", "country": "Country", "reggae": "Reggae", "jazz": "Jazz",
    "blues": "Blues", "sertanejo": "Sertanejo", "samba/pagode": "Samba/Pagode", "forró": "Forró",
    "axé": "Axé", "bossa nova": "Bossa nova",
}


def traduzir(nome: str | None) -> str | None:
    if not nome:
        return None
    nome = str(nome).strip()
    return TRADUCAO.get(nome.lower(), nome[:1].upper() + nome[1:])


def _sem_repetir(itens) -> list[str]:
    vistos, saida = set(), []
    for i in itens:
        if i and i not in vistos:
            vistos.add(i)
            saida.append(i)
    return saida


# ---------------------------------------------------------------- informações
_cache_album: dict[str, dict] = {}


def _album_deezer(album_id) -> dict:
    chave = str(album_id)
    if chave not in _cache_album:
        _cache_album[chave] = fontes._checa_deezer(fontes._get(f"{fontes.DEEZER}/album/{album_id}"))
    return _cache_album[chave]


def info_deezer(id_externo: str) -> dict:
    faixa = fontes._checa_deezer(fontes._get(f"{fontes.DEEZER}/track/{id_externo}"))
    album_resumo = faixa.get("album") or {}
    album = _album_deezer(album_resumo["id"]) if album_resumo.get("id") else {}
    generos = _sem_repetir(traduzir(g.get("name")) for g in (album.get("genres") or {}).get("data", []))
    data = faixa.get("release_date") or album.get("release_date") or ""
    return {
        "generos": generos,
        "album": album_resumo.get("title") or album.get("title") or "",
        "ano": data[:4] if data and not data.startswith("0000") else "",
        "gravadora": album.get("label") or "",
        "duracao": float(faixa.get("duration") or 0),
        "capa_url": album_resumo.get("cover_medium") or "",
        "link": faixa.get("link") or "",
    }


def info_jamendo(id_externo: str) -> dict:
    res = fontes._checa_jamendo(fontes._get(f"{fontes.JAMENDO}/tracks/",
                                            fontes._jamendo_params(id=id_externo, include="musicinfo")))
    if not res:
        return {"generos": []}
    d = res[0]
    tags = ((d.get("musicinfo") or {}).get("tags") or {}).get("genres") or []
    data = d.get("releasedate") or ""
    return {
        "generos": _sem_repetir(traduzir(t) for t in tags),
        "album": d.get("album_name") or "",
        "ano": data[:4],
        "gravadora": "Licença livre (Jamendo)",
        "duracao": float(d.get("duration") or 0),
        "capa_url": d.get("image") or d.get("album_image") or "",
        "link": d.get("shareurl") or "",
    }


def info_por_id(musica_id: str, silencioso: bool = True) -> dict:
    """Informações da música pela fonte; {} se não der (ex.: arquivo enviado).

    Com silencioso=False, um erro de conexão é repassado em vez de virar {}.
    """
    fonte, ide = musica_id.split(":", 1) if ":" in musica_id else ("", musica_id)
    try:
        if fonte == "deezer":
            return info_deezer(ide)
        if fonte == "jamendo":
            return info_jamendo(ide)
    except fontes.ErroFonte:
        if not silencioso:
            raise
    return {}


# ---------------------------------------------------------------- catálogo
def completar_catalogo(caminho_db: str, pausa: float = 0.12) -> None:
    """Preenche o gênero das músicas do catálogo que ainda não têm.

    Músicas do Jamendo precisam do JAMENDO_CLIENT_ID; sem ele, são puladas.
    Pode rodar de novo quando quiser: só busca o que falta.
    """
    import os

    con = banco.conectar(caminho_db)
    ids = [r[0] for r in con.execute("SELECT id FROM musicas WHERE genero IS NULL")]
    tem_jamendo = bool(os.environ.get("JAMENDO_CLIENT_ID", "").strip())
    print(f"{len(ids)} músicas sem gênero.")
    feitas, falhas = 0, 0
    for i, mid in enumerate(ids, start=1):
        if mid.startswith("jamendo:") and not tem_jamendo:
            continue
        info = None
        for tentativa in range(2):
            try:
                info = info_por_id(mid, silencioso=False)
                break
            except fontes.ErroFonte:
                time.sleep(5)  # limite de pedidos da API: espera e tenta de novo
        if info is None:
            falhas += 1  # fica sem gênero por enquanto; a próxima rodada tenta de novo
            continue
        generos = info.get("generos") or []
        banco.salvar_genero(con, mid, generos[0] if generos else SEM_GENERO, " | ".join(generos))
        feitas += 1
        if i % 50 == 0:
            print(f"  {i}/{len(ids)}")
        time.sleep(pausa)  # o Deezer limita a 50 pedidos a cada 5 segundos
    resumo = con.execute("SELECT genero, COUNT(*) FROM musicas GROUP BY genero ORDER BY 2 DESC").fetchall()
    print(f"Pronto: {feitas} músicas atualizadas" + (f", {falhas} ficaram para a próxima." if falhas else "."))
    print("Gêneros:", ", ".join(f"{g or 'pendente'}: {n}" for g, n in resumo))
    con.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Preenche o gênero das músicas do catálogo")
    p.add_argument("--db", default=str(banco.CATALOGO_PADRAO))
    a = p.parse_args()
    completar_catalogo(a.db)


if __name__ == "__main__":
    main()
