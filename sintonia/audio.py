"""Carrega o áudio e separa a música em partes: voz, instrumentos e batida.

Dois métodos:
- "demucs": modelo de IA (Meta) que separa muito bem. Fica rápido com GPU
  (Colab) e mais lento só com CPU. Usado para montar o catálogo.
- "leve": técnicas clássicas (REPET-SIM + HPSS do librosa). Bem mais rápido e
  sem dependências pesadas, porém menos preciso.

O ideal é usar o MESMO método no catálogo e na música da pessoa, senão as
comparações ficam menos justas. O app avisa quando isso não acontece.
"""
from __future__ import annotations

import numpy as np
import librosa

SR = 22050          # taxa de amostragem usada em todas as análises
PARTES = ("voz", "instrumental", "batida", "mix")

_modelo_demucs = None


def demucs_disponivel() -> bool:
    try:
        import demucs.pretrained  # noqa: F401
        import torch  # noqa: F401
        return True
    except Exception:
        return False


def metodo_padrao() -> str:
    return "demucs" if demucs_disponivel() else "leve"


def _normaliza(y: np.ndarray) -> np.ndarray:
    pico = float(np.max(np.abs(y))) if y.size else 0.0
    return (y / pico * 0.95).astype(np.float32) if pico > 0 else y.astype(np.float32)


def carregar(caminho: str, max_segundos: float | None = None) -> np.ndarray:
    y, _ = librosa.load(caminho, sr=SR, mono=True, duration=max_segundos)
    return _normaliza(y)


# ---------------------------------------------------------------- demucs
def _carrega_demucs():
    global _modelo_demucs
    if _modelo_demucs is None:
        import torch
        from demucs.pretrained import get_model

        modelo = get_model("htdemucs")
        modelo.eval()
        dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
        modelo.to(dispositivo)
        _modelo_demucs = (modelo, dispositivo)
    return _modelo_demucs


def _separa_demucs(caminho: str, max_segundos: float | None) -> dict[str, np.ndarray]:
    import torch
    from demucs.apply import apply_model

    modelo, dispositivo = _carrega_demucs()
    sr_m = modelo.samplerate
    y, _ = librosa.load(caminho, sr=sr_m, mono=False, duration=max_segundos)
    if y.ndim == 1:
        y = np.stack([y, y])
    y = y[: modelo.audio_channels]
    onda = torch.tensor(y, dtype=torch.float32)
    ref = onda.mean(0)
    media, desvio = ref.mean(), ref.std() + 1e-8
    onda = (onda - media) / desvio
    with torch.no_grad():
        fontes = apply_model(modelo, onda[None], device=dispositivo, split=True,
                             overlap=0.25, progress=False)[0]
    fontes = (fontes * desvio + media).cpu().numpy()
    nomes = list(modelo.sources)  # ['drums', 'bass', 'other', 'vocals']

    def mono(nome: str) -> np.ndarray:
        s = fontes[nomes.index(nome)].mean(0)
        return librosa.resample(s, orig_sr=sr_m, target_sr=SR).astype(np.float32)

    voz, batida = mono("vocals"), mono("drums")
    instrumental = mono("bass") + mono("other")
    mix = librosa.resample(y.mean(0), orig_sr=sr_m, target_sr=SR).astype(np.float32)
    # mesma escala para todas as partes: a proporção entre elas importa
    escala = 0.95 / (float(np.max(np.abs(mix))) + 1e-8)
    return {k: (v * escala).astype(np.float32) for k, v in
            {"voz": voz, "instrumental": instrumental, "batida": batida, "mix": mix}.items()}


# ---------------------------------------------------------------- leve
def _separa_leve(y: np.ndarray, bloco_s: float = 30.0) -> dict[str, np.ndarray]:
    """Voz por REPET-SIM (o acompanhamento se repete, a voz não) + HPSS."""
    n_bloco = int(bloco_s * SR)
    voz_partes, resto_partes = [], []
    for ini in range(0, len(y), n_bloco):
        trecho = y[ini: ini + n_bloco]
        if len(trecho) < SR:  # menos de 1 s: não vale separar
            voz_partes.append(np.zeros_like(trecho))
            resto_partes.append(trecho)
            continue
        S, fase = librosa.magphase(librosa.stft(trecho))
        largura = max(1, min(int(librosa.time_to_frames(2, sr=SR)), S.shape[1] // 2 - 1))
        filtro = librosa.decompose.nn_filter(S, aggregate=np.median, metric="cosine", width=largura)
        filtro = np.minimum(S, filtro)
        mascara_v = librosa.util.softmask(S - filtro, 10 * filtro, power=2)
        mascara_i = librosa.util.softmask(filtro, 2 * (S - filtro), power=2)
        voz_partes.append(librosa.istft(mascara_v * S * fase, length=len(trecho)))
        resto_partes.append(librosa.istft(mascara_i * S * fase, length=len(trecho)))
    voz = np.concatenate(voz_partes)
    resto = np.concatenate(resto_partes)
    harmonico, percussivo = librosa.effects.hpss(resto, margin=2.0)
    return {"voz": voz.astype(np.float32), "instrumental": harmonico.astype(np.float32),
            "batida": percussivo.astype(np.float32), "mix": y.astype(np.float32)}


# ---------------------------------------------------------------- principal
def separar(caminho: str, metodo: str = "auto", max_segundos: float | None = None) -> tuple[dict[str, np.ndarray], str]:
    """Devolve ({"voz", "instrumental", "batida", "mix"}, método usado)."""
    if metodo == "auto":
        metodo = metodo_padrao()
    if metodo == "demucs":
        return _separa_demucs(caminho, max_segundos), "demucs"
    if metodo == "leve":
        return _separa_leve(carregar(caminho, max_segundos)), "leve"
    raise ValueError(f"Método de separação desconhecido: {metodo}")


def separar_sinal(y: np.ndarray) -> dict[str, np.ndarray]:
    """Separação leve direto de um sinal já carregado (útil para testes)."""
    return _separa_leve(_normaliza(y))
