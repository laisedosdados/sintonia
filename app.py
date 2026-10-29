"""Sintonia — app para descobrir o que te pega numa música e achar outras parecidas.

Rodar no computador:   streamlit run app.py
"""
from __future__ import annotations

import html
import io
import os
import tempfile

import altair as alt
import numpy as np
import pandas as pd
import soundfile as sf
import streamlit as st

from sintonia import audio, banco, estilo, fontes
from sintonia.idioma import GRUPOS as GRUPOS_IDIOMA
from sintonia.links import plataformas
from sintonia.analise import analisar_arquivo
from sintonia.audio import SR
from sintonia.caracteristicas import ASPECTOS
from sintonia.descricoes import ASPECTO_INFO
from sintonia.recomendador import Recomendador

st.set_page_config(page_title="Sintonia", page_icon="🎧", layout="centered")
st.markdown(estilo.CSS, unsafe_allow_html=True)

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
    ss.pop("pesquisa", None)
    for p, _ in PARTES_TESTE:
        ss[f"parte_{p}"] = False
    aplicar_sugestao()


# ================================================================ tela
rec = carregar_catalogo()

st.markdown(
    '<div class="sint-marca"><div class="sint-disco"></div><div><h1>Sintonia</h1>'
    '<p class="sint-sub">Descubra o que te pega numa música e encontre outras com a mesma coisa.</p>'
    '</div></div>', unsafe_allow_html=True)
st.write("Sabe quando uma música tem *alguma coisa* que te pega, mas você não sabe explicar o quê? "
         "Aqui você descobre ouvindo.")


def passo(numero: int, titulo: str) -> None:
    st.markdown(f'<div class="sint-passo">Passo {numero}</div>', unsafe_allow_html=True)
    st.header(titulo)

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
passo(1, "Qual música tem aquilo?")
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
passo(2, "Ouça cada parte separada")
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
passo(3, "O que você quer encontrar?")
st.write("Cada controle diz **o quanto aquele aspecto importa** na busca. "
         "Já ajustei conforme o teste de escuta, mas pode mexer à vontade.")
for a in ASPECTOS:
    info = ASPECTO_INFO[a]
    chave = f"peso_{a}"
    ss.setdefault(chave, 30)
    texto_nivel, classe = estilo.nivel(int(ss[chave]))
    with st.container(border=True):
        st.markdown(
            f'<div class="sint-aj-cab"><span class="sint-aj-nome">{info["emoji"]} {info["nome"]}</span>'
            f'<span class="sint-nivel n{classe}">{texto_nivel}</span></div>'
            f'<div class="sint-aj-desc">{info["explica"]}</div>', unsafe_allow_html=True)
        st.slider(f"Importância de {info['nome'].lower()}", 0, 100, key=chave, label_visibility="collapsed")
        st.markdown('<div class="sint-escala"><span>0 · não importa</span><span>100 · essencial</span></div>',
                    unsafe_allow_html=True)

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
        busca_id = None
        try:
            recs, _ = rec.recomendar(an["feats"], pesos, n=10, fontes=fontes_rec, excluir=m)
            con = conexao_uso()
            partes = [p for p, _ in PARTES_TESTE if ss.get(f"parte_{p}")]
            busca_id = banco.registrar_busca(con, m, partes, pesos, fontes_rec)
            banco.registrar_recomendacoes(con, busca_id, recs)
        except Exception:
            pass  # registrar o uso é opcional
        ss.pesquisa = {"pesos": pesos, "fontes": fontes_rec, "busca_id": busca_id}
        ss.pop("filtro_idioma", None)


def cartao(pos: int, linha: pd.Series, usados: list[str]) -> str:
    e = html.escape
    capa = (f'<img class="sint-capa" src="{e(linha["capa_url"])}" alt="">' if linha.get("capa_url")
            else '<div class="sint-capa sint-capa-vazia"></div>')
    barras = "".join(
        f'<span class="sint-barra">{ASPECTO_INFO[a]["nome"]}<span class="sint-trilho">'
        f'<i style="width:{float(linha[f"parecida_{a}"]) * 100:.0f}%"></i></span>'
        f'{float(linha[f"parecida_{a}"]) * 100:.0f}%</span>'
        for a in usados if pd.notna(linha.get(f"parecida_{a}")))
    links = "".join(f'<a href="{e(url)}" target="_blank" rel="noopener">{nome}</a>'
                    for nome, url in plataformas(linha["fonte"], linha["titulo"], linha["artista"],
                                                 linha.get("link") or ""))
    pct = round(float(linha["parecida"]) * 100)
    return (f'<div class="sint-res">{capa}<div class="sint-info">'
            f'<div class="sint-titulo">{pos}. {e(str(linha["titulo"]))}</div>'
            f'<div class="sint-artista">{e(str(linha["artista"]))}'
            f'<span class="sint-tag">{e(str(linha["grupo_idioma"]))}</span></div>'
            f'<p class="sint-expl">{e(str(linha["explicacao"]))}.</p>'
            f'<div class="sint-barras">{barras}</div><div class="sint-links">{links}</div></div>'
            f'<div class="sint-anel" style="--p:{pct}" role="img" aria-label="{pct}% de compatibilidade">'
            f'<span><b>{pct}%</b><small>compatível</small></span></div></div>')


# ---------------------------------------------------------------- 4. resultado
b = ss.get("pesquisa")
if b:
    st.divider()
    passo(4, "Músicas com aquilo que te pega")

    contagem = rec.contagem_idiomas(b["fontes"])
    opcoes = [g for g in GRUPOS_IDIOMA if g in contagem.index]
    idiomas = st.multiselect(
        "Idioma das músicas", opcoes, default=opcoes, key="filtro_idioma",
        format_func=lambda g: f"{g} ({contagem[g]})",
        help="Tire os idiomas que você não quer nas recomendações.")
    if opcoes == ["Não identificado"] or set(opcoes) <= {"Não identificado", "Instrumental"}:
        st.caption("O idioma das músicas deste catálogo ainda não foi identificado. "
                   "Rode o passo de idiomas no notebook 01 para ativar esse filtro.")

    recs, avisos = rec.recomendar(an["feats"], b["pesos"], n=10, fontes=b["fontes"], excluir=m, idiomas=idiomas)
    for aviso in avisos:
        st.warning(aviso)
    if not idiomas:
        st.info("Escolha pelo menos um idioma para ver as recomendações.")
    elif recs.empty:
        st.info("Não encontrei músicas para comparar com esses ajustes.")

    usados = [a for a, w in b["pesos"].items() if w > 0]
    for pos, (mid, linha) in enumerate(recs.iterrows(), start=1):
        with st.container(border=True):
            st.markdown(cartao(pos, linha, usados), unsafe_allow_html=True)
            url = audio_atual(mid)
            if url:
                st.audio(url)
            if b["busca_id"]:
                b1, b2 = st.columns(2)
                dados = {"titulo": linha["titulo"], "artista": linha["artista"], "fonte": linha["fonte"],
                         "parecida": float(linha["parecida"]), "explicacao": linha["explicacao"]}
                if b1.button("👍 Tem aquilo", key=f"sim_{b['busca_id']}_{mid}", width="stretch"):
                    banco.registrar_gostou(conexao_uso(), b["busca_id"], mid, True, dados)
                    st.toast("Valeu! Isso ajuda a melhorar as recomendações.")
                if b2.button("👎 Não tem", key=f"nao_{b['busca_id']}_{mid}", width="stretch"):
                    banco.registrar_gostou(conexao_uso(), b["busca_id"], mid, False, dados)
                    st.toast("Anotado!")
