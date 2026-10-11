"""Compara a música escolhida com o catálogo e explica as recomendações.

Como funciona, em três passos:

1. Padronização (z-score): cada característica vira "quantos desvios acima ou
   abaixo da média do catálogo". Assim, andamento (em BPM) e vibrato (em
   cents) ficam na mesma escala e dá para dizer o que é "alto" ou "baixo".
2. Semelhança por aspecto: para cada aspecto (melodia, voz...) calculamos a
   similaridade de cosseno entre a música escolhida e cada música do catálogo,
   convertida para uma nota de 0 a 1.
3. Mistura com pesos: a nota final é a média ponderada das notas dos aspectos,
   usando os pesos que a pessoa escolheu nos controles deslizantes.
"""
from __future__ import annotations

import re
import sqlite3
import unicodedata

import numpy as np
import pandas as pd

from . import banco
from .caracteristicas import ASPECTOS
from .descricoes import ASPECTO_INFO, TEXTOS, aspecto_de, frase

# grupos de características que formam um "vetor" (ex.: os 25 intervalos da melodia).
# Cada grupo pesa o mesmo dentro do aspecto, para um vetor grande não abafar o resto.
VETORES = ("mel_int_", "mel_ctr_", "mel_fourier_", "voz_mfcc_", "rit_tgr_",
           "har_fourier_", "har_tonnetz_", "som_contraste_", "som_mfcc_")


def _grupo(nome: str) -> str:
    return next((p for p in VETORES if nome.startswith(p)), "escalares")


def _normaliza_texto(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\(.*?\)|\[.*?\]| - .*$", "", s)  # tira "(Ao Vivo)", "- Remastered" etc.
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def achatar(feats: dict[str, dict[str, float]]) -> pd.Series:
    return pd.Series({n: v for d in feats.values() for n, v in d.items()}, dtype=float)


class Recomendador:
    def __init__(self, musicas: pd.DataFrame, X: pd.DataFrame):
        ids = musicas.index.intersection(X.index)
        self.musicas = musicas.loc[ids].copy()
        self.X = X.loc[ids]
        self.media = self.X.mean()
        self.desvio = self.X.std().replace(0, 1).fillna(1)
        self.Z = ((self.X - self.media) / self.desvio).clip(-4, 4)
        self.colunas = {a: [c for c in self.X.columns if aspecto_de(c) == a] for a in ASPECTOS}
        tamanho = pd.Series([_grupo(c) for c in self.X.columns], index=self.X.columns).value_counts()
        self.peso_coluna = pd.Series({c: 1 / np.sqrt(tamanho[_grupo(c)]) for c in self.X.columns})
        self._chave = (self.musicas["titulo"].map(_normaliza_texto) + "|"
                       + self.musicas["artista"].map(_normaliza_texto))

    # ------------------------------------------------------------ construção
    @classmethod
    def do_banco(cls, caminho=banco.CATALOGO_PADRAO) -> "Recomendador":
        con = banco.conectar(caminho)
        try:
            return cls(banco.ler_musicas(con), banco.ler_caracteristicas(con))
        finally:
            con.close()

    def __len__(self) -> int:
        return len(self.musicas)

    @property
    def fontes(self) -> list[str]:
        return sorted(self.musicas["fonte"].dropna().unique().tolist())

    @property
    def separadores(self) -> list[str]:
        return sorted(self.musicas["separador"].dropna().unique().tolist())

    # ------------------------------------------------------------ cálculo
    def padronizar(self, feats: dict[str, dict[str, float]]) -> pd.Series:
        s = achatar(feats).reindex(self.X.columns)
        return ((s - self.media) / self.desvio).clip(-4, 4)

    def semelhanca(self, z: pd.Series, aspecto: str) -> pd.Series:
        """Nota de 0 a 1 de cada música do catálogo neste aspecto (NaN se não dá para comparar)."""
        cols = [c for c in self.colunas[aspecto] if np.isfinite(z[c])]
        if not cols:
            return pd.Series(np.nan, index=self.Z.index)
        M = self.Z[cols]
        faltando = M.isna().mean(axis=1)
        M = M.fillna(0.0)  # um ou outro buraco vira "na média"
        w = self.peso_coluna[cols].to_numpy()
        a = M.to_numpy() * w
        b = z[cols].to_numpy() * w
        normas = np.linalg.norm(a, axis=1) * np.linalg.norm(b)
        cos = np.divide(a @ b, normas, out=np.zeros(len(a)), where=normas > 0)
        # compatibilidade de 0 a 1: 0 = nada a ver (ou oposta), 1 = idêntica
        nota = pd.Series(np.clip(cos, 0.0, 1.0), index=self.Z.index)
        nota[faltando > 0.5] = np.nan  # ex.: música sem voz não tem melodia para comparar
        return nota

    def recomendar(self, feats: dict[str, dict[str, float]], pesos: dict[str, float], n: int = 10,
                   fontes: list[str] | None = None, excluir: dict | None = None) -> tuple[pd.DataFrame, list[str]]:
        avisos: list[str] = []
        z = self.padronizar(feats)
        usados = {a: float(w) for a, w in pesos.items() if w and w > 0}
        if not usados:
            raise ValueError("Escolha pelo menos um aspecto com peso maior que zero.")

        notas = {}
        for a in list(usados):
            s = self.semelhanca(z, a)
            if s.isna().all():
                avisos.append(f"Não deu para comparar {ASPECTO_INFO[a]['nome'].lower()}: "
                              + ("a música escolhida parece não ter voz cantada."
                                 if a in ("melodia", "voz") else "faltaram dados."))
                usados.pop(a)
            else:
                notas[a] = s
        if not usados:
            return self.musicas.iloc[:0].assign(parecida=[]), avisos

        tabela = pd.DataFrame(notas)
        soma_pesos = sum(usados.values())
        final = sum(tabela[a] * w for a, w in usados.items()) / soma_pesos  # NaN se faltar algum
        res = self.musicas.copy()
        res["parecida"] = final
        for a in ASPECTOS:
            res[f"parecida_{a}"] = tabela[a] if a in tabela else np.nan

        if fontes:
            res = res[res["fonte"].isin(fontes)]
        if excluir:
            chave = _normaliza_texto(excluir.get("titulo")) + "|" + _normaliza_texto(excluir.get("artista"))
            res = res[(res.index != excluir.get("id")) & (self._chave.loc[res.index] != chave)]
        res = res.dropna(subset=["parecida"]).sort_values("parecida", ascending=False)

        # no máximo 2 músicas do mesmo artista, para variar as sugestões
        res = res[res.groupby(res["artista"].map(_normaliza_texto)).cumcount() < 2].head(n)
        res["explicacao"] = [self.explicar(z, self.Z.loc[i], usados) for i in res.index]
        return res, avisos

    # ------------------------------------------------------------ explicações
    def explicar(self, z_semente: pd.Series, z_outra: pd.Series, pesos: dict[str, float], maximo: int = 3) -> str:
        candidatos = []
        for nome in TEXTOS:
            if nome not in z_semente.index:
                continue
            a = aspecto_de(nome)
            zs, zo = z_semente[nome], z_outra[nome]
            if a not in pesos or not (np.isfinite(zs) and np.isfinite(zo)):
                continue
            if np.sign(zs) == np.sign(zo) and min(abs(zs), abs(zo)) >= 0.5:
                texto = frase(nome, zs)
                if texto:
                    candidatos.append((min(abs(zs), abs(zo)) * pesos[a], texto))
        candidatos.sort(reverse=True)
        if not candidatos:
            nomes = [ASPECTO_INFO[a]["nome"].lower() for a in pesos]
            return "Parecida no conjunto de " + ", ".join(nomes)
        return "As duas têm " + "; ".join(t for _, t in candidatos[:maximo])

    def destaques(self, feats: dict[str, dict[str, float]], aspectos=None, n: int = 6) -> list[dict]:
        """O que mais diferencia a música escolhida do resto do catálogo."""
        z = self.padronizar(feats)
        itens = []
        for nome in TEXTOS:
            if nome not in z.index or not np.isfinite(z[nome]) or abs(z[nome]) < 0.8:
                continue
            a = aspecto_de(nome)
            if aspectos and a not in aspectos:
                continue
            texto = frase(nome, z[nome])
            if texto:
                itens.append({"aspecto": a, "texto": texto, "forca": float(abs(z[nome])), "nome": nome})
        return sorted(itens, key=lambda d: -d["forca"])[:n]
