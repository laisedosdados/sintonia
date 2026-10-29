"""Busca de músicas no Deezer e no Jamendo.

- Deezer: API pública e gratuita, sem cadastro. Tem músicas famosas, mas só
  libera uma prévia de 30 segundos de cada uma.
- Jamendo: músicas completas com licença livre (Creative Commons), de artistas
  independentes. Precisa de um "client_id" gratuito, criado em
  https://devportal.jamendo.com
"""
from __future__ import annotations

import os
import tempfile
import time
from dataclasses import asdict, dataclass

import requests

DEEZER = "https://api.deezer.com"
JAMENDO = "https://api.jamendo.com/v3.0"
TIMEOUT = 30
FONTES = ("deezer", "jamendo")


class ErroFonte(RuntimeError):
    """Erro ao falar com o Deezer ou o Jamendo."""


@dataclass
class Faixa:
    fonte: str          # "deezer" ou "jamendo"
    id_externo: str     # id da música dentro da fonte
    titulo: str
    artista: str
    album: str = ""
    capa_url: str = ""
    link: str = ""
    duracao: float = 0.0
    audio_url: str = ""  # prévia (Deezer) ou música inteira (Jamendo)

    @property
    def id(self) -> str:
        return f"{self.fonte}:{self.id_externo}"

    @property
    def nome(self) -> str:
        return f"{self.titulo} — {self.artista}"

    def como_dict(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        return d


# ---------------------------------------------------------------- utilidades
def _get(url: str, params: dict | None = None, tentativas: int = 3) -> dict:
    ultimo_erro = None
    for i in range(tentativas):
        try:
            r = requests.get(url, params=params, timeout=TIMEOUT)
            if r.status_code == 429:  # muitas requisições: espera e tenta de novo
                time.sleep(2 * (i + 1))
                continue
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            ultimo_erro = e
            time.sleep(1 + i)
    raise ErroFonte(f"Falha ao acessar {url}: {ultimo_erro}")


def jamendo_client_id() -> str:
    cid = os.environ.get("JAMENDO_CLIENT_ID", "").strip()
    if not cid:
        raise ErroFonte(
            "Falta o JAMENDO_CLIENT_ID. Crie um grátis em https://devportal.jamendo.com "
            "e defina a variável de ambiente JAMENDO_CLIENT_ID."
        )
    return cid


# ---------------------------------------------------------------- Deezer
def _checa_deezer(dados: dict) -> dict:
    if isinstance(dados, dict) and "error" in dados:
        erro = dados["error"]
        # código 4 = limite de requisições do Deezer: espera um pouco
        raise ErroFonte(f"Deezer respondeu com erro: {erro}")
    return dados


def _faixa_deezer(d: dict) -> Faixa:
    album = d.get("album") or {}
    return Faixa(
        fonte="deezer",
        id_externo=str(d["id"]),
        titulo=d.get("title", ""),
        artista=(d.get("artist") or {}).get("name", ""),
        album=album.get("title", ""),
        capa_url=album.get("cover_medium", "") or album.get("cover", ""),
        link=d.get("link", ""),
        duracao=float(d.get("duration") or 0),
        audio_url=d.get("preview", "") or "",
    )


def buscar_deezer(termo: str, limite: int = 10) -> list[Faixa]:
    dados = _checa_deezer(_get(f"{DEEZER}/search/track", {"q": termo, "limit": limite}))
    return [_faixa_deezer(d) for d in dados.get("data", []) if d.get("preview")]


def deezer_por_id(id_externo: str) -> Faixa:
    """Busca a música de novo para pegar um link de prévia válido (eles expiram)."""
    return _faixa_deezer(_checa_deezer(_get(f"{DEEZER}/track/{id_externo}")))


def candidatos_deezer(termos: list[str], por_termo: int = 40, playlists_por_termo: int = 1) -> list[Faixa]:
    """Monta candidatos ao catálogo a partir de playlists do Deezer.

    Para cada termo (ex.: "MPB", "sertanejo", "indie"), procura as playlists
    mais relevantes e pega as músicas delas. Termos variados = catálogo variado.
    """
    vistas: dict[str, Faixa] = {}
    for termo in termos:
        try:
            pls = _checa_deezer(_get(f"{DEEZER}/search/playlist", {"q": termo, "limit": playlists_por_termo}))
        except ErroFonte as e:
            print(f"[deezer] pulei '{termo}': {e}")
            continue
        for pl in pls.get("data", [])[:playlists_por_termo]:
            try:
                faixas = _checa_deezer(_get(f"{DEEZER}/playlist/{pl['id']}/tracks", {"limit": por_termo}))
            except ErroFonte as e:
                print(f"[deezer] pulei playlist {pl.get('title')}: {e}")
                continue
            for d in faixas.get("data", []):
                if d.get("preview") and d.get("readable", True):
                    f = _faixa_deezer(d)
                    vistas.setdefault(f.id, f)
            time.sleep(0.2)  # gentileza com a API
    return list(vistas.values())


# ---------------------------------------------------------------- Jamendo
def _checa_jamendo(dados: dict) -> list[dict]:
    cab = dados.get("headers", {})
    if cab.get("status") != "success":
        raise ErroFonte(f"Jamendo respondeu com erro: {cab.get('error_message') or cab}")
    return dados.get("results", [])


def _faixa_jamendo(d: dict) -> Faixa:
    return Faixa(
        fonte="jamendo",
        id_externo=str(d["id"]),
        titulo=d.get("name", ""),
        artista=d.get("artist_name", ""),
        album=d.get("album_name", ""),
        capa_url=d.get("image", "") or d.get("album_image", ""),
        link=d.get("shareurl", "") or d.get("shorturl", ""),
        duracao=float(d.get("duration") or 0),
        audio_url=d.get("audio", ""),
    )


def _jamendo_params(**extra) -> dict:
    p = {"client_id": jamendo_client_id(), "format": "json", "audioformat": "mp32"}
    p.update(extra)
    return p


def buscar_jamendo(termo: str, limite: int = 10) -> list[Faixa]:
    res = _checa_jamendo(_get(f"{JAMENDO}/tracks/", _jamendo_params(search=termo, limit=limite)))
    return [_faixa_jamendo(d) for d in res if d.get("audio")]


def jamendo_por_id(id_externo: str) -> Faixa:
    res = _checa_jamendo(_get(f"{JAMENDO}/tracks/", _jamendo_params(id=id_externo)))
    if not res:
        raise ErroFonte(f"Música {id_externo} não encontrada no Jamendo")
    return _faixa_jamendo(res[0])


def candidatos_jamendo(tags: list[str], por_tag: int = 40, so_com_voz: bool = True) -> list[Faixa]:
    """Músicas mais populares do Jamendo em cada estilo (tag)."""
    vistas: dict[str, Faixa] = {}
    for tag in tags:
        extra = {"tags": tag, "limit": min(por_tag, 200), "order": "popularity_total"}
        if so_com_voz:
            extra["vocalinstrumental"] = "vocal"
        try:
            res = _checa_jamendo(_get(f"{JAMENDO}/tracks/", _jamendo_params(**extra)))
        except ErroFonte as e:
            print(f"[jamendo] pulei '{tag}': {e}")
            continue
        for d in res:
            if d.get("audio"):
                f = _faixa_jamendo(d)
                vistas.setdefault(f.id, f)
        time.sleep(0.2)
    return list(vistas.values())


# ---------------------------------------------------------------- comuns
def buscar(fonte: str, termo: str, limite: int = 10) -> list[Faixa]:
    if fonte == "deezer":
        return buscar_deezer(termo, limite)
    if fonte == "jamendo":
        return buscar_jamendo(termo, limite)
    raise ValueError(f"Fonte desconhecida: {fonte}")


def por_id(id_completo: str) -> Faixa:
    fonte, ide = id_completo.split(":", 1)
    return deezer_por_id(ide) if fonte == "deezer" else jamendo_por_id(ide)


def baixar_audio(url: str, pasta: str | None = None) -> str:
    """Baixa o áudio para um arquivo temporário e devolve o caminho.

    O arquivo é só para análise: quem chama deve apagá-lo depois.
    """
    if not url:
        raise ErroFonte("Essa música não tem áudio disponível")
    fd, caminho = tempfile.mkstemp(suffix=".mp3", dir=pasta)
    os.close(fd)
    try:
        with requests.get(url, stream=True, timeout=TIMEOUT) as r:
            r.raise_for_status()
            with open(caminho, "wb") as f:
                for bloco in r.iter_content(1 << 16):
                    f.write(bloco)
    except requests.RequestException as e:
        os.remove(caminho)
        raise ErroFonte(f"Não consegui baixar o áudio: {e}") from e
    return caminho
