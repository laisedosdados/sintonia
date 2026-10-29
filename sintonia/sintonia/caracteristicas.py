"""Transforma cada parte da música em números ("características").

São cinco aspectos, cada um calculado na parte da música onde ele mora:

- melodia  -> na voz isolada: o "desenho" das notas cantadas
- voz      -> na voz isolada: como a pessoa canta (timbre, altura, vibrato)
- ritmo    -> na batida e na mistura: andamento, síncope, regularidade
- harmonia -> nos instrumentos: clima dos acordes (maior/menor), trocas
- som      -> na mistura completa: brilho, graves, dinâmica, textura

Detalhe importante: melodia e harmonia são medidas de um jeito que NÃO depende
do tom. A mesma melodia cantada mais aguda ou mais grave gera quase os mesmos
números, porque usamos os intervalos entre as notas e não as notas em si.
"""
from __future__ import annotations

import math
from collections import Counter

import numpy as np
import librosa

from .audio import SR

ASPECTOS = ("melodia", "voz", "ritmo", "harmonia", "som")

SR_F0 = 16000         # a detecção de notas roda numa taxa menor (mais rápido)
HOP_F0 = 256          # 16 ms por quadro
DT_F0 = HOP_F0 / SR_F0
MIN_NOTAS = 10        # menos que isso: não há melodia cantada suficiente

# perfis de Krumhansl: quanto cada grau "pesa" numa tonalidade maior e menor
_MAIOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MENOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
_CONTORNOS = [a + b for a in "SUD" for b in "SUD"]  # S=mesma nota, U=sobe, D=desce


# ================================================================ utilidades
def _media(x) -> float:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    return float(x.mean()) if x.size else float("nan")


def _fourier_pc(perfil: np.ndarray) -> np.ndarray:
    """Magnitudes da transformada de Fourier de um perfil de 12 notas.

    Não muda se a música for transposta para outro tom, e ainda assim descreve
    o "caráter" das notas usadas (diatônico, cromático, pentatônico...).
    """
    p = np.asarray(perfil, dtype=float)
    if p.sum() <= 0:
        return np.full(6, np.nan)
    p = p / p.sum()
    return np.abs(np.fft.rfft(p))[1:7]


def _tonalidade(perfil: np.ndarray) -> tuple[int, float, float]:
    """(tônica, melhor correlação com maior, melhor correlação com menor)."""
    if np.allclose(perfil, perfil.mean()):
        return 0, 0.0, 0.0
    cm = [np.corrcoef(perfil, np.roll(_MAIOR, k))[0, 1] for k in range(12)]
    cn = [np.corrcoef(perfil, np.roll(_MENOR, k))[0, 1] for k in range(12)]
    tonica = int(np.argmax(cm)) if max(cm) >= max(cn) else int(np.argmax(cn))
    return tonica, float(max(cm)), float(max(cn))


def _quadros_ativos(y: np.ndarray, hop: int = 512, rel: float = 0.15) -> np.ndarray:
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    if rms.max() <= 0:
        return np.zeros_like(rms, dtype=bool)
    return rms > rel * np.percentile(rms, 95)


# ================================================================ melodia
def contorno_melodico(voz: np.ndarray) -> np.ndarray:
    """Altura (em notas MIDI, com fração) quadro a quadro; NaN onde não há canto."""
    y = librosa.resample(voz, orig_sr=SR, target_sr=SR_F0)
    f0, vozeado, prob = librosa.pyin(y, fmin=70.0, fmax=1000.0, sr=SR_F0,
                                     frame_length=1024, hop_length=HOP_F0)
    rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=HOP_F0)[0]
    n = min(len(f0), len(rms))
    f0, vozeado, prob, rms = f0[:n], vozeado[:n], prob[:n], rms[:n]
    limiar = 0.1 * np.percentile(rms, 95) if rms.max() > 0 else np.inf
    ok = vozeado & (prob > 0.3) & (rms > limiar) & np.isfinite(f0)
    midi = np.full(n, np.nan)
    midi[ok] = librosa.hz_to_midi(f0[ok])
    return midi


def segmentar_notas(midi: np.ndarray, desvio_max: float = 0.75, min_dur: float = 0.06) -> list[dict]:
    """Agrupa quadros em notas. Uma nota termina quando o canto para ou quando
    a altura se afasta mais de 3/4 de semitom por 3 quadros seguidos (assim o
    vibrato não vira várias notas)."""
    notas, atual, fora = [], [], 0

    def fecha(fim_idx: int):
        if atual and len(atual) * DT_F0 >= min_dur:
            alturas = midi[atual]
            notas.append({"inicio": atual[0] * DT_F0, "fim": (atual[-1] + 1) * DT_F0,
                          "altura": float(np.median(alturas)), "quadros": list(atual)})

    for i, m in enumerate(midi):
        if not np.isfinite(m):
            fecha(i)
            atual, fora = [], 0
            continue
        if not atual:
            atual = [i]
            continue
        ref = float(np.median(midi[atual]))
        if abs(m - ref) > desvio_max:
            fora += 1
            if fora >= 3:
                novos = atual[-(fora - 1):] + [i]
                atual = atual[: -(fora - 1)]
                fecha(i)
                atual, fora = novos, 0
                continue
        else:
            fora = 0
        atual.append(i)
    fecha(len(midi))
    return notas


def caracteristicas_melodia(notas: list[dict], duracao_canto: float) -> dict[str, float]:
    nomes_int = [f"mel_int_{k:+03d}" for k in range(-12, 13)]
    nomes = (["mel_extensao", "mel_passos", "mel_saltos", "mel_repeticao", "mel_intervalo_medio",
              "mel_subida", "mel_notas_por_seg", "mel_duracao_nota", "mel_frase"]
             + nomes_int + [f"mel_ctr_{c}" for c in _CONTORNOS] + [f"mel_fourier_{k}" for k in range(1, 7)])
    if len(notas) < MIN_NOTAS:
        return {n: float("nan") for n in nomes}

    alturas = np.array([n["altura"] for n in notas])
    # intervalos só dentro da mesma frase (pausa menor que 1 s)
    intervalos, frases, frase_ini = [], [], notas[0]["inicio"]
    for a, b in zip(notas[:-1], notas[1:]):
        if b["inicio"] - a["fim"] < 1.0:
            intervalos.append(int(np.clip(round(b["altura"] - a["altura"]), -12, 12)))
        if b["inicio"] - a["fim"] >= 0.4:
            frases.append(a["fim"] - frase_ini)
            frase_ini = b["inicio"]
    frases.append(notas[-1]["fim"] - frase_ini)
    iv = np.array(intervalos) if intervalos else np.zeros(1, dtype=int)
    n_iv = max(len(iv), 1)
    nao_zero = iv[iv != 0]

    f: dict[str, float] = {
        "mel_extensao": float(np.percentile(alturas, 95) - np.percentile(alturas, 5)),
        "mel_passos": float(np.mean((np.abs(iv) >= 1) & (np.abs(iv) <= 2))),
        "mel_saltos": float(np.mean(np.abs(iv) >= 5)),
        "mel_repeticao": float(np.mean(iv == 0)),
        "mel_intervalo_medio": float(np.mean(np.abs(iv))),
        "mel_subida": float(np.mean(nao_zero > 0)) if nao_zero.size else 0.5,
        "mel_notas_por_seg": len(notas) / max(duracao_canto, 1e-3),
        "mel_duracao_nota": float(np.median([n["fim"] - n["inicio"] for n in notas])),
        "mel_frase": float(np.median(frases)),
    }
    cont = Counter(int(i) for i in iv)
    for k, nome in zip(range(-12, 13), nomes_int):
        f[nome] = cont.get(k, 0) / n_iv

    sinais = ["S" if i == 0 else ("U" if i > 0 else "D") for i in iv]
    pares = Counter(a + b for a, b in zip(sinais[:-1], sinais[1:]))
    total_pares = max(sum(pares.values()), 1)
    for c in _CONTORNOS:
        f[f"mel_ctr_{c}"] = pares.get(c, 0) / total_pares

    perfil = np.zeros(12)
    for n in notas:
        perfil[int(round(n["altura"])) % 12] += n["fim"] - n["inicio"]
    for k, v in enumerate(_fourier_pc(perfil), start=1):
        f[f"mel_fourier_{k}"] = float(v)
    return f


# ================================================================ voz
def caracteristicas_voz(voz: np.ndarray, midi: np.ndarray, notas: list[dict], duracao: float) -> dict[str, float]:
    nomes = (["voz_altura", "voz_vibrato", "voz_brilho", "voz_soprosidade", "voz_presenca"]
             + [f"voz_mfcc_{k:02d}_{s}" for k in range(1, 13) for s in ("media", "desvio")])
    canto = np.isfinite(midi)
    presenca = float(canto.sum() * DT_F0 / max(duracao, 1e-3))
    if len(notas) < MIN_NOTAS:
        f = {n: float("nan") for n in nomes}
        f["voz_presenca"] = presenca
        return f

    vibratos = []
    for n in notas:
        if n["fim"] - n["inicio"] >= 0.3:
            alt = midi[n["quadros"]]
            t = np.arange(len(alt))
            resid = alt - np.polyval(np.polyfit(t, alt, 1), t)  # tira a "rampa"
            vibratos.append(float(np.std(resid)) * 100)  # em cents
    ativos = _quadros_ativos(voz)
    S = np.abs(librosa.stft(voz))
    n = min(S.shape[1], len(ativos))
    S, ativos = S[:, :n], ativos[:n]
    if ativos.sum() < 5:
        ativos = np.ones(n, dtype=bool)
    centroide = librosa.feature.spectral_centroid(S=S, sr=SR)[0][ativos]
    planicidade = librosa.feature.spectral_flatness(S=S)[0][ativos]
    mfcc = librosa.feature.mfcc(S=librosa.power_to_db(librosa.feature.melspectrogram(S=S**2, sr=SR)),
                                n_mfcc=13)[1:, ativos]  # sem o coef. 0 (volume)
    f = {
        "voz_altura": float(np.nanmedian(midi)),
        "voz_vibrato": float(np.median(vibratos)) if vibratos else 0.0,
        "voz_brilho": float(np.log(np.median(centroide) + 1)),
        "voz_soprosidade": float(np.median(planicidade)),
        "voz_presenca": presenca,
    }
    for k in range(12):
        f[f"voz_mfcc_{k + 1:02d}_media"] = float(mfcc[k].mean())
        f[f"voz_mfcc_{k + 1:02d}_desvio"] = float(mfcc[k].std())
    return f


# ================================================================ ritmo
def caracteristicas_ritmo(mix: np.ndarray, batida: np.ndarray) -> tuple[dict[str, float], np.ndarray]:
    duracao = len(mix) / SR
    env = librosa.onset.onset_strength(y=mix, sr=SR)
    env_b = librosa.onset.onset_strength(y=batida, sr=SR)
    env_total = env + env_b
    bpm, batidas = librosa.beat.beat_track(onset_envelope=env_total, sr=SR)
    bpm = float(np.atleast_1d(bpm)[0])
    while 0 < bpm < 60:
        bpm *= 2
    while bpm >= 180:
        bpm /= 2

    ac = librosa.autocorrelate(env_total - env_total.mean())
    if ac[0] > 0:
        ac = ac / ac[0]
        quadro_s = 512 / SR
        lo, hi = int(60 / 200 / quadro_s), int(60 / 40 / quadro_s)
        regularidade = float(ac[lo:hi].max()) if hi > lo and len(ac) > hi else 0.0
    else:
        regularidade = 0.0

    if len(batidas) >= 4:
        meios = ((batidas[:-1] + batidas[1:]) // 2).astype(int)
        no_tempo = env_total[batidas[batidas < len(env_total)]].mean()
        fora_tempo = env_total[meios[meios < len(env_total)]].mean()
        sincopa = float(fora_tempo / (no_tempo + 1e-8))
    else:
        sincopa = float("nan")

    ataques = librosa.onset.onset_detect(onset_envelope=env_total, sr=SR)
    f = {
        "rit_andamento": bpm,
        "rit_ataques_por_seg": len(ataques) / max(duracao, 1e-3),
        "rit_regularidade": regularidade,
        "rit_sincopa": sincopa,
        "rit_peso_batida": float(np.sqrt(np.mean(batida**2)) / (np.sqrt(np.mean(mix**2)) + 1e-8)),
    }
    try:
        tg = librosa.feature.tempogram(onset_envelope=env_total, sr=SR)
        razoes = librosa.feature.tempogram_ratio(tg=tg, sr=SR, bpm=bpm or None).mean(axis=1)
    except Exception:
        razoes = np.full(13, np.nan)
    for k, v in enumerate(razoes):
        f[f"rit_tgr_{k:02d}"] = float(v)
    return f, np.asarray(batidas)


# ================================================================ harmonia
def caracteristicas_harmonia(instrumental: np.ndarray) -> tuple[dict[str, float], dict]:
    croma = librosa.feature.chroma_cqt(y=instrumental, sr=SR)
    ativos = _quadros_ativos(instrumental)
    n = min(len(ativos), croma.shape[1])
    croma_ativo = croma[:, :n][:, ativos[:n]] if ativos[:n].sum() >= 5 else croma
    perfil = croma_ativo.mean(axis=1)
    tonica, c_maior, c_menor = _tonalidade(perfil)
    p = perfil / (perfil.sum() + 1e-8)
    entropia = float(-(p * np.log(p + 1e-12)).sum() / math.log(12))

    # trocas de acorde: compara blocos de ~0,5 s
    q = max(1, int(0.5 * SR / 512))
    blocos = [croma[:, i:i + q].mean(axis=1) for i in range(0, croma.shape[1] - q + 1, q)]
    dists = []
    for a, b in zip(blocos[:-1], blocos[1:]):
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na > 0 and nb > 0:
            dists.append(1 - float(a @ b / (na * nb)))

    f = {
        "har_maior_menor": c_maior - c_menor,
        "har_clareza_tom": max(c_maior, c_menor),
        "har_complexidade": entropia,
        "har_trocas": _media(dists) if dists else 0.0,
    }
    for k, v in enumerate(_fourier_pc(perfil), start=1):
        f[f"har_fourier_{k}"] = float(v)
    tonnetz = librosa.feature.tonnetz(chroma=croma, sr=SR)
    for k in range(6):
        f[f"har_tonnetz_{k}_desvio"] = float(tonnetz[k].std())
    nomes_notas = ["Dó", "Dó#", "Ré", "Ré#", "Mi", "Fá", "Fá#", "Sol", "Sol#", "Lá", "Lá#", "Si"]
    info = {"tom": f"{nomes_notas[tonica]} {'maior' if c_maior >= c_menor else 'menor'}"}
    return f, info


# ================================================================ som geral
def caracteristicas_som(mix: np.ndarray) -> dict[str, float]:
    S = np.abs(librosa.stft(mix))
    ativos = _quadros_ativos(mix)[: S.shape[1]]
    if ativos.sum() < 5:
        ativos = np.ones(S.shape[1], dtype=bool)
    S_a = S[:, ativos]
    freqs = librosa.fft_frequencies(sr=SR)
    potencia = (S_a**2).sum(axis=1)
    rms_db = librosa.amplitude_to_db(librosa.feature.rms(S=S)[0][ativos] + 1e-8)
    mfcc = librosa.feature.mfcc(S=librosa.power_to_db(librosa.feature.melspectrogram(S=S_a**2, sr=SR)), n_mfcc=20)[1:]
    contraste = librosa.feature.spectral_contrast(S=S_a, sr=SR)
    f = {
        "som_brilho": float(np.log(np.median(librosa.feature.spectral_centroid(S=S_a, sr=SR)[0]) + 1)),
        "som_largura": float(np.log(np.median(librosa.feature.spectral_bandwidth(S=S_a, sr=SR)[0]) + 1)),
        "som_aspereza": float(np.median(librosa.feature.zero_crossing_rate(mix)[0])),
        "som_dinamica": float(np.std(rms_db)),
        "som_graves": float(potencia[freqs < 250].sum() / (potencia.sum() + 1e-12)),
    }
    for k in range(contraste.shape[0]):
        f[f"som_contraste_{k}"] = float(contraste[k].mean())
    for k in range(19):
        f[f"som_mfcc_{k + 1:02d}_media"] = float(mfcc[k].mean())
        f[f"som_mfcc_{k + 1:02d}_desvio"] = float(mfcc[k].std())
    return f


# ================================================================ tudo junto
def extrair(partes: dict[str, np.ndarray]) -> tuple[dict[str, dict[str, float]], dict]:
    """Recebe as partes separadas e devolve ({aspecto: {nome: valor}}, info).

    `info` traz coisas úteis para mostrar na tela: as notas da melodia, o tom,
    se a música tem voz etc.
    """
    duracao = len(partes["mix"]) / SR
    midi = contorno_melodico(partes["voz"])
    notas = segmentar_notas(midi)
    duracao_canto = float(np.isfinite(midi).sum() * DT_F0)

    ritmo, _ = caracteristicas_ritmo(partes["mix"], partes["batida"])
    harmonia, info_h = caracteristicas_harmonia(partes["instrumental"])
    feats = {
        "melodia": caracteristicas_melodia(notas, duracao_canto),
        "voz": caracteristicas_voz(partes["voz"], midi, notas, duracao),
        "ritmo": ritmo,
        "harmonia": harmonia,
        "som": caracteristicas_som(partes["mix"]),
    }
    info = {
        "duracao": duracao,
        "tem_voz": len(notas) >= MIN_NOTAS,
        "n_notas": len(notas),
        "notas": [{k: v for k, v in n.items() if k != "quadros"} for n in notas],
        **info_h,
    }
    return feats, info
