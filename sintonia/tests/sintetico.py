"""Gera "músicas" sintéticas simples para testar o código sem precisar de internet."""
from __future__ import annotations

import numpy as np

from sintonia.audio import SR


def _hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def cantar(notas: list[int], dur_nota: float = 0.35, vibrato: float = 0.3,
           harmonicos: int = 8, brilho: float = 1.0, pausa_a_cada: int = 8) -> np.ndarray:
    """Uma "voz": tom harmônico com vibrato seguindo as notas, com pausas entre frases."""
    partes = []
    for i, n in enumerate(notas):
        t = np.arange(int(dur_nota * SR)) / SR
        desvio = vibrato * np.sin(2 * np.pi * 5.5 * t)
        f = _hz(n + desvio)
        fase = 2 * np.pi * np.cumsum(f) / SR
        onda = sum((1 / k**(1.5 / brilho)) * np.sin(k * fase) for k in range(1, harmonicos + 1))
        env = np.minimum(1, np.minimum(t / 0.02, (dur_nota - t) / 0.03))
        partes.append(onda * env)
        if (i + 1) % pausa_a_cada == 0:
            partes.append(np.zeros(int(0.5 * SR)))
    y = np.concatenate(partes)
    return (y / np.max(np.abs(y)) * 0.6).astype(np.float32)


def acordes(fundamentais: list[int], menor: bool, dur_acorde: float, total: float) -> np.ndarray:
    n = int(total * SR)
    y = np.zeros(n)
    terca = 3 if menor else 4
    for i in range(int(np.ceil(total / dur_acorde))):
        r = fundamentais[i % len(fundamentais)]
        ini, fim = int(i * dur_acorde * SR), min(n, int((i + 1) * dur_acorde * SR))
        t = np.arange(fim - ini) / SR
        for nota in (r, r + terca, r + 7, r - 12):
            y[ini:fim] += np.sin(2 * np.pi * _hz(nota) * t)
    return (y / np.max(np.abs(y)) * 0.4).astype(np.float32)


def bateria(bpm: float, total: float, sincopada: bool = False, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(total * SR)
    y = np.zeros(n)
    batida = 60 / bpm
    kick_t = np.arange(int(0.15 * SR)) / SR
    kick = np.sin(2 * np.pi * 60 * kick_t) * np.exp(-kick_t * 30)
    chimbal = rng.normal(0, 1, int(0.05 * SR)) * np.exp(-np.arange(int(0.05 * SR)) / SR * 80)
    k = 0
    while k * batida < total:
        ini = int(k * batida * SR)
        if sincopada and k % 2 == 1:
            ini = int((k + 0.5) * batida * SR)  # desloca para o contratempo
        if ini + len(kick) < n:
            y[ini:ini + len(kick)] += kick
        meio = int((k + 0.5) * batida * SR)
        if meio + len(chimbal) < n:
            y[meio:meio + len(chimbal)] += 0.3 * chimbal
        k += 1
    return (y / np.max(np.abs(y)) * 0.5).astype(np.float32)


# melodias de exemplo (notas MIDI)
MELODIA_PASSOS = [60, 62, 64, 65, 64, 62, 60, 62, 64, 64, 65, 67, 65, 64, 62, 60] * 3
MELODIA_SALTOS = [60, 67, 62, 72, 64, 57, 69, 60, 65, 74, 62, 55, 67, 60, 72, 64] * 3


def musica(melodia=MELODIA_PASSOS, transpor=0, menor=False, bpm=100, sincopada=False,
           vibrato=0.3, brilho=1.0) -> dict[str, np.ndarray]:
    voz = cantar([n + transpor for n in melodia], vibrato=vibrato, brilho=brilho)
    total = len(voz) / SR
    inst = acordes([48 + transpor, 53 + transpor, 55 + transpor, 48 + transpor], menor, 60 / bpm * 4, total)
    bat = bateria(bpm, total, sincopada)
    mix = voz + inst + bat
    escala = 0.95 / np.max(np.abs(mix))
    return {"voz": voz * escala, "instrumental": inst * escala, "batida": bat * escala, "mix": mix * escala}
