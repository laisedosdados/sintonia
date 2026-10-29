"""Junta as etapas: baixar -> separar -> extrair características."""
from __future__ import annotations

import os

from . import audio, fontes
from .caracteristicas import extrair


def analisar_arquivo(caminho: str, metodo: str = "auto", max_segundos: float | None = None):
    """Devolve (características, info, partes separadas, método usado)."""
    partes, metodo_usado = audio.separar(caminho, metodo, max_segundos)
    feats, info = extrair(partes)
    return feats, info, partes, metodo_usado


def analisar_faixa(faixa: fontes.Faixa, metodo: str = "auto", max_segundos: float | None = None,
                   manter_partes: bool = False):
    """Baixa o áudio, analisa e APAGA o arquivo (não guardamos áudio de ninguém)."""
    caminho = fontes.baixar_audio(faixa.audio_url)
    try:
        feats, info, partes, metodo_usado = analisar_arquivo(caminho, metodo, max_segundos)
    finally:
        os.remove(caminho)
    return feats, info, (partes if manter_partes else None), metodo_usado
