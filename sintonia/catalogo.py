"""Monta o catálogo: busca músicas, analisa cada uma e guarda no banco.

Uso (no Colab, com GPU, ou no seu computador):

    python -m sintonia.catalogo --fonte deezer --max 600
    python -m sintonia.catalogo --fonte jamendo --max 400

Pode parar e rodar de novo quando quiser: as músicas já analisadas são puladas.
"""
from __future__ import annotations

import argparse
import time

from tqdm.auto import tqdm

from . import audio, banco, fontes, generos, idioma
from .analise import analisar_faixa

# termos usados para achar playlists variadas no Deezer
TERMOS_DEEZER = [
    "MPB", "bossa nova", "samba", "pagode", "sertanejo", "forró", "axé", "funk brasileiro",
    "rock nacional", "indie brasileiro", "gospel", "rap nacional", "piseiro", "brega",
    "pop", "rock", "indie", "folk", "soul", "R&B", "jazz", "blues", "country", "reggae",
    "hip hop", "eletrônica", "k-pop", "latin", "anos 80", "anos 90", "acústico", "baladas românticas",
]

# estilos (tags) do Jamendo
TAGS_JAMENDO = [
    "pop", "rock", "indie", "folk", "acoustic", "singersongwriter", "soul", "rnb", "jazz", "blues",
    "country", "reggae", "hiphop", "electronic", "latin", "world", "chillout", "lounge", "metal", "punk",
]


def construir(fonte: str, maximo: int, caminho_db: str, metodo: str = "auto",
              por_termo: int = 40, termos: list[str] | None = None) -> None:
    con = banco.conectar(caminho_db)
    print(f"Procurando candidatos no {fonte}...")
    if fonte == "deezer":
        candidatos = fontes.candidatos_deezer(termos or TERMOS_DEEZER, por_termo=por_termo)
    elif fonte == "jamendo":
        candidatos = fontes.candidatos_jamendo(termos or TAGS_JAMENDO, por_tag=por_termo)
    else:
        raise ValueError("fonte deve ser deezer ou jamendo")

    pendentes = [f for f in candidatos if not banco.ja_processada(con, f.id)]
    ja = con.execute("SELECT COUNT(*) FROM musicas WHERE fonte=?", (fonte,)).fetchone()[0]
    faltam = max(0, maximo - ja)
    print(f"{len(candidatos)} candidatos, {ja} já no catálogo, vou analisar até {faltam}.")

    detectar_idioma = idioma.whisper_disponivel()
    if not detectar_idioma:
        print("Whisper não instalado: o idioma das músicas não será detectado agora.")
    ok = 0
    barra = tqdm(total=faltam, desc=f"Analisando ({fonte})")
    for faixa in pendentes:
        if ok >= faltam:
            break
        try:
            if fonte == "deezer":
                faixa = fontes.deezer_por_id(faixa.id_externo)  # prévia nova (os links expiram)
            feats, info, partes, metodo_usado = analisar_faixa(faixa, metodo, manter_partes=detectar_idioma)
            if detectar_idioma and info["tem_voz"]:
                info["idioma"], info["idioma_conf"] = idioma.detectar(partes["voz"], audio.SR)
            banco.salvar_musica(con, faixa.como_dict(), feats, info, metodo_usado)
            gens = generos.info_por_id(faixa.id).get("generos") or []
            banco.salvar_genero(con, faixa.id, gens[0] if gens else generos.SEM_GENERO, " | ".join(gens))
            ok += 1
            barra.update(1)
            barra.set_postfix_str(faixa.nome[:40])
        except KeyboardInterrupt:
            break
        except Exception as e:  # uma música com problema não para o resto
            banco.registrar_falha(con, faixa.id, f"{type(e).__name__}: {e}")
            time.sleep(0.5)
    barra.close()
    total = con.execute("SELECT COUNT(*) FROM musicas").fetchone()[0]
    com_voz = con.execute("SELECT COUNT(*) FROM musicas WHERE tem_voz=1").fetchone()[0]
    print(f"Pronto: +{ok} músicas. Catálogo agora tem {total} ({com_voz} com voz cantada).")
    con.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Monta o catálogo do Sintonia")
    p.add_argument("--fonte", choices=fontes.FONTES, required=True)
    p.add_argument("--max", type=int, default=500, help="quantas músicas dessa fonte no catálogo")
    p.add_argument("--db", default=str(banco.CATALOGO_PADRAO))
    p.add_argument("--metodo", default="auto", choices=["auto", "demucs", "leve"])
    p.add_argument("--por-termo", type=int, default=40)
    p.add_argument("--termos", nargs="*", help="substitui a lista padrão de estilos")
    a = p.parse_args()
    construir(a.fonte, a.max, a.db, a.metodo, a.por_termo, a.termos)


if __name__ == "__main__":
    main()
