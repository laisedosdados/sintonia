"""Descobre em que idioma cada música é cantada.

Usa o Whisper (modelo de reconhecimento de fala da OpenAI, aberto) ouvindo a
VOZ ISOLADA, sem os instrumentos, o que deixa a detecção bem mais confiável.
O Whisper é pesado, então roda só no Colab, na hora de montar o catálogo. O
app não precisa dele: só lê o idioma já guardado no banco.
"""
from __future__ import annotations

import math
import os

import numpy as np

# rótulos mostrados no filtro do app, nesta ordem
GRUPOS = ["Português", "Inglês", "Espanhol", "Japonês", "Coreano",
          "Outros idiomas", "Instrumental", "Não identificado"]
NOMES = {"pt": "Português", "en": "Inglês", "es": "Espanhol", "ja": "Japonês", "ko": "Coreano"}
CONFIANCA_MIN = 0.5   # abaixo disso o Whisper está "chutando"
SR_WHISPER = 16000

_modelo = None


def grupo(codigo, confianca, tem_voz) -> str:
    """Converte o resultado do Whisper no rótulo do filtro."""
    if tem_voz is not None and not _vazio(tem_voz) and int(tem_voz) == 0:
        return "Instrumental"
    if _vazio(codigo) or codigo == "erro":
        return "Não identificado"
    if _vazio(confianca) or float(confianca) < CONFIANCA_MIN:
        return "Não identificado"
    return NOMES.get(str(codigo), "Outros idiomas")


def _vazio(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def whisper_disponivel() -> bool:
    try:
        import whisper  # noqa: F401
        return True
    except Exception:
        return False


def _carrega(nome: str = "small"):
    global _modelo
    if _modelo is None:
        import torch
        import whisper

        _modelo = whisper.load_model(nome, device="cuda" if torch.cuda.is_available() else "cpu")
    return _modelo


def _trecho_com_mais_voz(y: np.ndarray, segundos: float = 30) -> np.ndarray:
    n = int(segundos * SR_WHISPER)
    if len(y) <= n:
        return y
    passo = SR_WHISPER // 4
    energia = np.add.reduceat(y.astype(np.float64) ** 2, np.arange(0, len(y), passo))
    janela = int(segundos * 4)
    soma = np.convolve(energia, np.ones(janela), mode="valid")
    ini = int(np.argmax(soma)) * passo
    return y[ini: ini + n]


def detectar(voz: np.ndarray, sr: int) -> tuple[str | None, float]:
    """(código do idioma, confiança de 0 a 1). (None, 0) se não houver voz."""
    import librosa
    import whisper

    y = librosa.resample(np.asarray(voz, dtype=np.float32), orig_sr=sr, target_sr=SR_WHISPER)
    y = _trecho_com_mais_voz(y)
    pico = float(np.max(np.abs(y))) if y.size else 0.0
    if pico < 1e-4:
        return None, 0.0
    y = (y / pico * 0.9).astype(np.float32)
    modelo = _carrega()
    mel = whisper.log_mel_spectrogram(whisper.pad_or_trim(y), n_mels=modelo.dims.n_mels).to(modelo.device)
    _, probs = modelo.detect_language(mel)
    codigo = max(probs, key=probs.get)
    return codigo, float(probs[codigo])


def completar_catalogo(caminho_db: str, metodo: str = "demucs") -> None:
    """Detecta o idioma das músicas do catálogo que ainda não têm.

    Precisa baixar o áudio de novo (ele não é guardado). Pode parar e rodar
    de novo: as músicas que já têm idioma são puladas.
    """
    from tqdm.auto import tqdm

    from . import audio, banco, fontes

    con = banco.conectar(caminho_db)
    ids = [r[0] for r in con.execute("SELECT id FROM musicas WHERE idioma IS NULL AND tem_voz = 1")]
    print(f"{len(ids)} músicas com voz ainda sem idioma.")
    for mid in tqdm(ids, desc="Detectando idiomas"):
        caminho = None
        try:
            faixa = fontes.por_id(mid)  # link novo (os da Deezer expiram)
            caminho = fontes.baixar_audio(faixa.audio_url)
            partes, _ = audio.separar(caminho, metodo)
            codigo, conf = detectar(partes["voz"], audio.SR)
            banco.salvar_idioma(con, mid, codigo or "erro", conf)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[idioma] {mid}: {type(e).__name__}: {e}")
            banco.salvar_idioma(con, mid, "erro", 0.0)
        finally:
            if caminho and os.path.exists(caminho):
                os.remove(caminho)
    resumo = con.execute("SELECT idioma, COUNT(*) FROM musicas GROUP BY idioma ORDER BY 2 DESC").fetchall()
    print("Idiomas no catálogo:", ", ".join(f"{i or 'sem voz'}: {n}" for i, n in resumo))
    con.close()
