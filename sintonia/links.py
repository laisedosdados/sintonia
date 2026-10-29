"""Links para ouvir cada música nas plataformas.

Para Deezer e Jamendo, quando a música veio de lá, usamos o link direto.
Para as outras, o link abre a busca da plataforma já com título e artista;
a música costuma ser o primeiro resultado. Links diretos do Spotify
precisariam da API deles, com cadastro.
"""
from __future__ import annotations

from urllib.parse import quote, quote_plus


def plataformas(fonte: str, titulo: str, artista: str, link_original: str = "") -> list[tuple[str, str]]:
    termo = f"{titulo} {artista}".strip()
    lista = [
        ("YouTube", f"https://www.youtube.com/results?search_query={quote_plus(termo)}"),
        ("YouTube Music", f"https://music.youtube.com/search?q={quote_plus(termo)}"),
        ("Spotify", f"https://open.spotify.com/search/{quote(termo, safe='')}"),
        ("Deezer", link_original if fonte == "deezer" and link_original
         else f"https://www.deezer.com/search/{quote(termo, safe='')}"),
    ]
    # o Jamendo só tem música livre de artistas independentes:
    # para as músicas famosas (Deezer), uma busca lá não encontraria nada
    if fonte == "jamendo" and link_original:
        lista.append(("Jamendo", link_original))
    return lista
