"""Sintonia — app para descobrir o que te pega numa música e achar outras parecidas.

Rodar no computador:   streamlit run app.py
"""
from __future__ import annotations

import io
import os
import tempfile

import altair as alt
import numpy as np
import pandas as pd
import soundfile as sf
import streamlit as st

from sintonia import audio, banco, fontes
from sintonia.analise import analisar_arquivo
from sintonia.audio import SR
from sintonia.caracteristicas import ASPECTOS
from sintonia.descricoes import ASPECTO_INFO
from sintonia.recomendador import Recomendador

st.set_page_config(page_title="Sintonia", page_icon="🎧", layout="centered")

# chave do Jamendo: pode vir dos "secrets" do Streamlit ou de variável de ambiente
try:
    if "JAMENDO_CLIENT_ID" in st.secrets:
        os.environ.setdefault("JAMENDO_CLIENT_ID", st.secrets["JAMENDO_CLIENT_ID"])
except Exception:
    pass

NOME_FONTE = {"deezer": "Deezer (músicas famosas, prévia de 30 s)",
              "jamendo": "Jamendo (música livre, completa)"}
PARTES_TESTE = [("voz", "🎤 Só a voz"), ("instrumental", "🎹 Só os instrumentos"), ("batida", "🥁 Só a batida")]
# o que cada parte marcada no teste de escuta sugere buscar
SUGESTAO = {"voz": {"melodia": 80, "voz": 45}, "instrumental": {"harmonia": 70, "som": 40},
            "batida": {"ritmo": 80, "som": 25}}
ss = st.session_state


# ================================================================ recursos
@st.cache_resource(show_spinner=False)
def carregar_catalogo() -> Recomendador | None:
    if not banco.CATALOGO_PADRAO.exists():
        return None
    rec = Recomendador.do_banco(banco.CATALOGO_PADRAO)
    return rec if len(rec) else None


@st.cache_resource(show_spinner=False)
def conexao_uso():
    return banco.conectar(banco.USO_PADRAO)


@st.cache_data(ttl=3600, show_spinner=False)
def buscar(fonte: str, termo: str) -> list[dict]:
    return [f.como_dict() for f in fontes.buscar(fonte, termo, limite=8)]


@st.cache_data(ttl=600, show_spinner=False)
def audio_atual(musica_id: str) -> str:
    """Link de áudio novo (os da Deezer expiram em poucas horas)."""
    try:
        return fontes.por_id(musica_id).audio_url
    except Exception:
        return ""


def wav(y: np.ndarray) -> bytes:
    pico = float(np.max(np.abs(y))) or 1.0
    buf = io.BytesIO()
    sf.write(buf, (y / pico * 0.9).astype(np.float32), SR, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def trechos_para_ouvir(partes: dict[str, np.ndarray], segundos: float = 30) -> dict[str, bytes]:
    """Pega os 30 s onde a voz aparece mais, para o teste de escuta não ficar pesado."""
    n = int(segundos * SR)
    voz = partes["voz"]
    if len(voz) > n:
        energia = np.convolve(voz.astype(np.float64) ** 2, np.ones(SR) / SR, mode="valid")[::SR // 4]
        janela = int(segundos * 4)
        soma = np.convolve(energia, np.ones(janela), mode="valid")
        ini = int(np.argmax(soma)) * (SR // 4) if soma.size else 0
    else:
        ini = 0
    return {p: wav(partes[p][ini:ini + n]) for p, _ in PARTES_TESTE}


def metodo_separacao(rec: Recomendador | None) -> tuple[str, str | None]:
    """Usa o mesmo método do catálogo, se possível (comparação mais justa)."""
    desejado = rec.separadores[0] if rec and rec.separadores else "auto"
    if desejado == "demucs" and not audio.demucs_disponivel():
        return "leve", ("O catálogo foi analisado com o Demucs, mas ele não está instalado aqui; "
                        "usei a separação leve, então as comparações podem ficar menos precisas.")
    return (desejado if desejado in ("demucs", "leve") else "auto"), None


def aplicar_sugestao():
    marcadas = [p for p, _ in PARTES_TESTE if ss.get(f"parte_{p}")]
    novos = {a: 0 for a in ASPECTOS}
    for p in marcadas:
        for a, v in SUGESTAO[p].items():
            novos[a] = max(novos[a], v)
    if not marcadas:
        novos = {a: 30 for a in ASPECTOS}
    for a, v in novos.items():
        ss[f"peso_{a}"] = v


def analisar(musica: dict, caminho_local: str | None, rec: Recomendador | None):
    metodo, aviso = metodo_separacao(rec)
    with st.status("Analisando a música...", expanded=True) as status:
        caminho = caminho_local
        try:
            if caminho is None:
                st.write("⬇️ Baixando o áudio")
                caminho = fontes.baixar_audio(audio_atual(musica["id"]) or musica.get("audio_url", ""))
            st.write("✂️ Separando voz, instrumentos e batida (pode levar um tempinho)")
            st.write("📏 Medindo melodia, voz, ritmo, harmonia e som")
            feats, info, partes, metodo_usado = analisar_arquivo(caminho, metodo)
        finally:
            if caminho and os.path.exists(caminho):
                os.remove(caminho)  # não guardamos o áudio
        status.update(label="Análise pronta!", state="complete", expanded=False)
    ss.analise = {"musica": musica, "feats": feats, "info": info, "metodo": metodo_usado,
                  "trechos": trechos_para_ouvir(partes), "aviso": aviso}
    ss.pop("recs", None)
    for p, _ in PARTES_TESTE:
        ss[f"parte_{p}"] = False
    aplicar_sugestao()


# ================================================================ tela
rec = carregar_catalogo()

st.title("🎧 Sintonia")
st.write("Sabe quando uma música tem *alguma coisa* que te pega, mas você não sabe explicar o quê? "
         "Aqui você descobre ouvindo, e depois encontra outras músicas com essa mesma coisa.")

if rec is None:
    st.warning("O catálogo ainda está vazio. Monte-o com o notebook `notebooks/01_montar_catalogo.ipynb` "
               "(ou `python -m sintonia.catalogo --fonte deezer`) e coloque o arquivo em `dados/catalogo.db`.")

with st.sidebar:
    st.header("Como funciona")
    st.write("1. Você escolhe uma música.\n\n"
             "2. O app separa a voz, os instrumentos e a batida, e você ouve cada parte.\n\n"
             "3. Você marca o que te pega e ajusta o que quer encontrar.\n\n"
             "4. O app compara com o catálogo e explica por que cada música parece com a sua.")
    if rec is not None:
        contagem = rec.musicas["fonte"].value_counts()
        st.caption("Catálogo: " + ", ".join(f"{v} do {k.capitalize()}" for k, v in contagem.items()))
    st.caption("Nenhum áudio é guardado: o app analisa e apaga.")

# ---------------------------------------------------------------- 1. escolher
st.header("1. Escolha uma música")
fonte = st.radio("Onde procurar?", list(fontes.FONTES), format_func=NOME_FONTE.get, horizontal=True)
with st.form("busca", border=False):
    termo = st.text_input("Nome da música", placeholder="ex.: Evidências Chitãozinho e Xororó")
    if st.form_submit_button("🔍 Buscar", width="stretch") and termo.strip():
        try:
            ss.resultados = buscar(fonte, termo.strip())
            if not ss.resultados:
                st.info("Não achei nada. Tente escrever de outro jeito ou incluir o nome do artista.")
        except fontes.ErroFonte as e:
            ss.resultados = []
            st.error(str(e))

if ss.get("resultados"):
    por_id = {r["id"]: r for r in ss.resultados}
    escolha = st.radio("Qual delas?", list(por_id),
                       format_func=lambda i: f"{por_id[i]['titulo']} — {por_id[i]['artista']}")
    musica = por_id[escolha]
    if musica.get("capa_url"):
        st.image(musica["capa_url"], width=140)
    if st.button("✨ Analisar essa música", type="primary", width="stretch"):
        try:
            analisar(musica, None, rec)
        except Exception as e:
            st.error(f"Não consegui analisar essa música: {e}")

with st.expander("Tenho o arquivo da música (analisa ela inteira)"):
    arquivo = st.file_uploader("Envie um MP3, WAV, OGG ou FLAC", type=["mp3", "wav", "ogg", "flac", "m4a"])
    if arquivo and st.button("Analisar arquivo", width="stretch"):
        sufixo = os.path.splitext(arquivo.name)[1] or ".mp3"
        fd, caminho = tempfile.mkstemp(suffix=sufixo)
        with os.fdopen(fd, "wb") as f:
            f.write(arquivo.getvalue())
        nome = os.path.splitext(arquivo.name)[0]
        try:
            analisar({"id": f"arquivo:{nome}", "titulo": nome, "artista": "", "fonte": "arquivo"}, caminho, rec)
        except Exception as e:
            st.error(f"Não consegui analisar esse arquivo: {e}")

an = ss.get("analise")
if not an:
    st.stop()

# ---------------------------------------------------------------- 2. teste de escuta
m = an["musica"]
st.divider()
st.header("2. Teste de escuta")
st.write(f"**{m['titulo']}**" + (f" — {m['artista']}" if m.get("artista") else "")
         + f"  ·  tom estimado: {an['info'].get('tom', '?')}")
if an.get("aviso"):
    st.warning(an["aviso"])
st.write("Ouça cada parte separada. Marque as que têm **“aquilo”** que te pega. "
         "Pode marcar mais de uma.")
for p, rotulo in PARTES_TESTE:
    st.markdown(f"**{rotulo}**")
    st.audio(an["trechos"][p], format="audio/wav")
    st.checkbox("Essa parte tem aquilo", key=f"parte_{p}", on_change=aplicar_sugestao)
st.caption("A separação é feita por IA e pode vazar um pouco de uma parte na outra.")

if not an["info"]["tem_voz"]:
    st.info("Não encontrei voz cantada suficiente nessa música, então melodia e voz não vão entrar na comparação.")

if an["info"]["notas"]:
    with st.expander("🎵 Ver o desenho da melodia"):
        notas = pd.DataFrame(an["info"]["notas"])
        grafico = alt.Chart(notas).mark_bar(height=6, cornerRadius=2).encode(
            x=alt.X("inicio:Q", title="tempo (s)"), x2="fim:Q",
            y=alt.Y("altura:Q", title="altura da nota", scale=alt.Scale(zero=False)),
            tooltip=[alt.Tooltip("altura:Q", format=".1f")],
        ).properties(height=220)
        st.altair_chart(grafico, width="stretch")
        st.caption("Cada traço é uma nota cantada. Subidas, descidas e saltos formam o “desenho”.")

if rec is not None:
    destaques = rec.destaques(an["feats"])
    if destaques:
        st.subheader("O que se destaca nessa música")
        st.caption("Comparada com as outras músicas do catálogo, ela tem:")
        for d in destaques:
            st.write(f"{ASPECTO_INFO[d['aspecto']]['emoji']} {d['texto'].capitalize()}")

# ---------------------------------------------------------------- 3. o que buscar
st.divider()
st.header("3. O que você quer encontrar?")
st.write("Já ajustei conforme o teste de escuta, mas pode mexer à vontade. "
         "Quanto mais alto, mais aquilo pesa na busca.")
for a in ASPECTOS:
    info = ASPECTO_INFO[a]
    ss.setdefault(f"peso_{a}", 30)
    st.slider(f"{info['emoji']} {info['nome']}", 0, 100, key=f"peso_{a}", help=info["explica"])
    st.caption(info["explica"])

if rec is None:
    st.stop()
fontes_rec = rec.fontes
if len(fontes_rec) > 1:
    fontes_rec = st.multiselect("Recomendar músicas de:", rec.fontes, default=rec.fontes,
                                format_func=lambda f: f.capitalize())
pesos = {a: ss[f"peso_{a}"] / 100 for a in ASPECTOS}

if st.button("🎧 Encontrar músicas parecidas", type="primary", width="stretch"):
    if not any(pesos.values()):
        st.error("Coloque pelo menos um aspecto acima de zero.")
    elif not fontes_rec:
        st.error("Escolha pelo menos uma fonte.")
    else:
        recs, avisos = rec.recomendar(an["feats"], pesos, n=10, fontes=fontes_rec, excluir=m)
        busca_id = None
        try:
            con = conexao_uso()
            partes = [p for p, _ in PARTES_TESTE if ss.get(f"parte_{p}")]
            busca_id = banco.registrar_busca(con, m, partes, pesos, fontes_rec)
            banco.registrar_recomendacoes(con, busca_id, recs)
        except Exception:
            pass  # registrar o uso é opcional
        ss.recs = {"tabela": recs, "avisos": avisos, "busca_id": busca_id, "pesos": pesos}

# ---------------------------------------------------------------- 4. resultado
r = ss.get("recs")
if r:
    st.divider()
    st.header("4. Músicas com aquilo que te pega")
    for aviso in r["avisos"]:
        st.warning(aviso)
    if r["tabela"].empty:
        st.info("Não encontrei músicas para comparar com esses ajustes.")
    usados = [a for a, w in r["pesos"].items() if w > 0]
    for pos, (mid, linha) in enumerate(r["tabela"].iterrows(), start=1):
        with st.container(border=True):
            topo = st.columns([1, 3])
            if linha.get("capa_url"):
                topo[0].image(linha["capa_url"], width="stretch")
            topo[1].markdown(f"**{pos}. {linha['titulo']}**  \n{linha['artista']}")
            compat = float(linha["parecida"])
            topo[1].markdown(f"### 🎯 {compat * 100:.0f}% de compatibilidade")
            topo[1].progress(min(max(compat, 0.0), 1.0))
            st.write(linha["explicacao"] + ".")
            # compatibilidade em cada aspecto que a pessoa escolheu
            for a in usados:
                valor = linha.get(f"parecida_{a}")
                if pd.notna(valor):
                    info = ASPECTO_INFO[a]
                    st.progress(min(max(float(valor), 0.0), 1.0),
                                text=f"{info['emoji']} {info['nome']}: {float(valor) * 100:.0f}%")
            url = audio_atual(mid)
            if url:
                st.audio(url)
            if linha.get("link"):
                st.markdown(f"[Abrir no {linha['fonte'].capitalize()}]({linha['link']})")
            if r["busca_id"]:
                b1, b2 = st.columns(2)
                if b1.button("👍 Tem aquilo", key=f"sim_{r['busca_id']}_{pos}", width="stretch"):
                    banco.registrar_gostou(conexao_uso(), r["busca_id"], pos, True)
                    st.toast("Valeu! Isso ajuda a melhorar as recomendações.")
                if b2.button("👎 Não tem", key=f"nao_{r['busca_id']}_{pos}", width="stretch"):
                    banco.registrar_gostou(conexao_uso(), r["busca_id"], pos, False)
                    st.toast("Anotado!")
