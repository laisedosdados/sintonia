"""Sintonia — app para descobrir o que te cativa numa música e achar outras parecidas.

Rodar no computador:   streamlit run app.py
"""
from __future__ import annotations

import html
import io
import os
import tempfile
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import soundfile as sf
import streamlit as st

from sintonia import audio, banco, estilo, fontes, generos
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
def versao_catalogo() -> tuple:
    """Muda quando o catálogo ou o código do projeto mudam (ex.: depois de subir
    algo novo no GitHub). Assim o app recarrega em vez de usar a versão antiga
    que ficou guardada na memória."""
    import sintonia
    arquivos = [banco.CATALOGO_PADRAO, *sorted(Path(sintonia.__file__).parent.glob("*.py"))]
    return tuple(os.path.getmtime(a) if os.path.exists(a) else 0.0 for a in arquivos)


@st.cache_resource(show_spinner=False, max_entries=1)
def carregar_catalogo(versao: tuple) -> Recomendador | None:
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
    sobre = generos.info_por_id(musica["id"])
    if sobre.get("generos"):
        sobre["genero"], sobre["genero_estimado"] = sobre["generos"][0], False
    elif rec is not None:
        sobre["genero"], sobre["genero_estimado"] = rec.genero_provavel(feats), True
    ss.analise = {"musica": musica, "feats": feats, "info": info, "metodo": metodo_usado,
                  "trechos": trechos_para_ouvir(partes), "aviso": aviso, "sobre": sobre}
    for chave in ("pesquisa", "filtro_genero", "modo_genero", "filtro_idioma"):
        ss.pop(chave, None)
    for p, _ in PARTES_TESTE:
        ss[f"parte_{p}"] = False
    aplicar_sugestao()


# ================================================================ tela
rec = carregar_catalogo(versao_catalogo())

st.markdown(
    '<div class="sint-marca"><div class="sint-disco"></div><div><h1>Sintonia</h1>'
    '<p class="sint-sub">Descubra o que te cativa numa música e encontre outras com a mesma coisa.</p>'
    '</div></div>', unsafe_allow_html=True)
st.write("Sabe quando uma música tem *alguma coisa* que te chama atenção, mas você não sabe explicar o quê? "
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
             "3. Você marca o que te chama atenção e ajusta o que quer encontrar.\n\n"
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
sobre = an.get("sobre") or {}


def tempo(segundos) -> str:
    segundos = int(round(float(segundos or 0)))
    return f"{segundos // 60}:{segundos % 60:02d}" if segundos else ""


def texto_genero() -> tuple[str, str]:
    """(gênero, observação) da música analisada."""
    g = sobre.get("genero")
    if not g:
        return "Não identificado", ""
    return g, ("estimado pelo som" if sobre.get("genero_estimado") else "")


def tags_semente() -> str:
    g, obs = texto_genero()
    return f'<span class="sint-tag">{html.escape(g)}{" · " + obs if obs else ""}</span>'


st.divider()
st.subheader("Sobre essa música")
fatos = []
g, obs = texto_genero()
fatos.append(("Gênero", g, obs))
outros = [x for x in sobre.get("generos", [])[1:]]
if outros:
    fatos.append(("Também classificada como", ", ".join(outros), ""))
for rotulo, chave in (("Álbum", "album"), ("Lançamento", "ano"), ("Gravadora", "gravadora")):
    if sobre.get(chave):
        fatos.append((rotulo, str(sobre[chave]), ""))
duracao = tempo(sobre.get("duracao") or m.get("duracao"))
if duracao:
    fatos.append(("Duração", duracao, ""))
fatos.append(("Tom", an["info"].get("tom") or "?", "estimado pelo Sintonia"))
bpm = an["feats"].get("ritmo", {}).get("rit_andamento")
if bpm and np.isfinite(bpm):
    fatos.append(("Andamento", f"{bpm:.0f} BPM", "medido pelo Sintonia"))
fatos.append(("Voz cantada", "Sim" if an["info"]["tem_voz"] else "Pouca ou nenhuma", ""))

e = html.escape
capa_url = sobre.get("capa_url") or m.get("capa_url")
capa = (f'<img class="sint-sobre-capa" src="{e(capa_url)}" alt="">' if capa_url
        else '<div class="sint-sobre-capa sint-capa-vazia"></div>')
st.markdown(
    f'<div class="sint-sobre">{capa}<div class="sint-sobre-info">'
    f'<div class="sint-titulo">{e(m["titulo"])}</div>'
    f'<div class="sint-artista">{e(m.get("artista") or "")}</div>'
    '<div class="sint-fatos">'
    + "".join(f'<div class="sint-fato"><small>{e(r)}</small><b>{e(v)}</b>'
              + (f'<i>{e(o)}</i>' if o else "") + "</div>" for r, v, o in fatos)
    + "</div></div></div>", unsafe_allow_html=True)
if sobre.get("genero_estimado"):
    st.caption("Essa música não veio com gênero, então estimei pelo som, olhando as músicas mais parecidas do catálogo.")

st.divider()
passo(2, "Ouça cada parte separada")
if an.get("aviso"):
    st.warning(an["aviso"])
st.write("Ouça cada parte separada. Marque as que têm **“aquilo”** que te chama atenção. "
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
pesos = {a: ss[f"peso_{a}"] / 100 for a in ASPECTOS}

# gênero das recomendações
generos_escolhidos = None
contagem_g = rec.contagem_generos()
with st.container(border=True):
    st.markdown('<div class="sint-aj-cab"><span class="sint-aj-nome">🎼 Gênero musical</span></div>'
                '<div class="sint-aj-desc">De quais gêneros você quer receber músicas.</div>',
                unsafe_allow_html=True)
    if contagem_g.drop(generos.SEM_GENERO, errors="ignore").empty:
        st.caption("O gênero das músicas do catálogo ainda não foi preenchido.")
    else:
        genero_musica, _ = texto_genero()
        prox = rec.generos_proximos(an["feats"], pesos, excluir=m) if any(pesos.values()) else None
        parecido = {} if prox is None else dict(zip(prox["genero"], prox["parecida"]))
        ordem = ([genero_musica] if genero_musica in contagem_g.index else []) + \
                [g for g in (prox["genero"] if prox is not None else []) if g != genero_musica]
        ordem += [g for g in contagem_g.index if g not in ordem]
        if parecido:
            top = [g for g in ordem if g != genero_musica and g in parecido][:3]
            st.caption("Os gêneros que mais soam parecidos com essa música, pelo que você ajustou acima: "
                       + ", ".join(f"**{g}** ({parecido[g] * 100:.0f}%)" for g in top) + ".")
        MODOS = {
            "todos": "Não usar gênero: recomendar só pelo som",
            "preferir": "Dar preferência a alguns gêneros, sem excluir os outros",
            "so": "Só músicas dos gêneros que eu escolher",
        }
        modo = st.radio("Como o gênero entra na busca?", list(MODOS), format_func=MODOS.get, key="modo_genero")
        if modo != "todos":
            if "filtro_genero" not in ss:
                inicio = [g for g in ordem if g == genero_musica]
                inicio += [g for g in ordem if g != genero_musica and g in parecido][:2]
                ss.filtro_genero = inicio or ordem[:1]

            def rotulo_genero(g: str) -> str:
                partes_r = [g]
                if g == genero_musica:
                    partes_r.append("gênero da música")
                elif g in parecido:
                    partes_r.append(f"{parecido[g] * 100:.0f}% parecido")
                return " · ".join(partes_r) + f" ({contagem_g.get(g, 0)})"

            generos_escolhidos = st.multiselect(
                "Gêneros", ordem, key="filtro_genero", format_func=rotulo_genero,
                help="Já marquei o gênero da música e os dois mais parecidos. O número entre parênteses "
                     "é quantas músicas desse gênero tem no catálogo.")
            st.caption("As músicas desses gêneros sobem na lista, mas as de outros gêneros continuam aparecendo."
                       if modo == "preferir" else "Só vão aparecer músicas desses gêneros.")
            if genero_musica not in contagem_g.index and genero_musica != "Não identificado":
                st.caption(f"Não há músicas de {genero_musica} no catálogo, então sugeri os gêneros mais parecidos.")

fontes_rec = rec.fontes
if len(fontes_rec) > 1:
    fontes_rec = st.multiselect("Recomendar músicas de:", rec.fontes, default=rec.fontes,
                                format_func=lambda f: f.capitalize())

if st.button("🎧 Encontrar músicas parecidas", type="primary", width="stretch"):
    if not any(pesos.values()):
        st.error("Coloque pelo menos um aspecto acima de zero.")
    elif not fontes_rec:
        st.error("Escolha pelo menos uma fonte.")
    elif generos_escolhidos is not None and not generos_escolhidos:
        st.error("Escolha pelo menos um gênero, ou marque “Não usar gênero”.")
    else:
        busca_id = None
        try:
            filtro_g, pref_g = ((generos_escolhidos, None) if ss.get("modo_genero") == "so"
                                else (None, generos_escolhidos))
            recs, _ = rec.recomendar(an["feats"], pesos, n=10, fontes=fontes_rec, excluir=m,
                                     generos=filtro_g, preferir_generos=pref_g)
            con = conexao_uso()
            partes = [p for p, _ in PARTES_TESTE if ss.get(f"parte_{p}")]
            busca_id = banco.registrar_busca(con, m, partes, pesos, fontes_rec)
            banco.registrar_recomendacoes(con, busca_id, recs)
        except Exception:
            pass  # registrar o uso é opcional
        ss.pesquisa = {"pesos": pesos, "fontes": fontes_rec, "busca_id": busca_id,
                       "generos": generos_escolhidos, "modo_genero": ss.get("modo_genero", "todos")}
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
            f'<span class="sint-tag">{e(str(linha["genero"]))}</span>'
            f'<span class="sint-tag">{e(str(linha["grupo_idioma"]))}</span></div>'
            f'<p class="sint-expl">{e(str(linha["explicacao"]))}.</p>'
            f'<div class="sint-barras">{barras}</div><div class="sint-links">{links}</div></div>'
            f'<div class="sint-anel" style="--p:{pct}" role="img" aria-label="{pct}% de compatibilidade">'
            f'<span><b>{pct}%</b><small>compatível</small></span></div></div>')


# ---------------------------------------------------------------- 4. resultado
b = ss.get("pesquisa")
if b:
    st.divider()
    passo(4, "Músicas com aquilo que te chama atenção")

    usados = [a for a, w in b["pesos"].items() if w > 0]
    capa_url = sobre.get("capa_url") or m.get("capa_url")
    capa = (f'<img class="sint-capa" src="{e(capa_url)}" alt="">' if capa_url
            else '<div class="sint-capa sint-capa-vazia"></div>')
    busca_txt = ", ".join(f'{ASPECTO_INFO[a]["nome"]} {b["pesos"][a] * 100:.0f}' for a in usados)
    modo_b = b.get("modo_genero", "todos")
    if modo_b == "todos" or not b.get("generos"):
        gen_txt = "Gêneros: todos (só pelo som)"
    elif modo_b == "preferir":
        gen_txt = "Preferência para: " + ", ".join(b["generos"])
    else:
        gen_txt = "Só: " + ", ".join(b["generos"])
    st.markdown(
        f'<div class="sint-semente">{capa}<div class="sint-info">'
        '<div class="sint-olho">Você analisou</div>'
        f'<div class="sint-titulo">{e(m["titulo"])}</div>'
        f'<div class="sint-artista">{e(m.get("artista") or "")}{tags_semente()}</div>'
        f'<div class="sint-busca">Buscando por: {e(busca_txt)} · {e(gen_txt)}</div>'
        '</div></div>', unsafe_allow_html=True)

    contagem = rec.contagem_idiomas(b["fontes"])
    opcoes = [g for g in GRUPOS_IDIOMA if g in contagem.index]
    idiomas = st.multiselect(
        "Idioma das músicas", opcoes, default=opcoes, key="filtro_idioma",
        format_func=lambda g: f"{g} ({contagem[g]})",
        help="Tire os idiomas que você não quer nas recomendações.")
    if opcoes == ["Não identificado"] or set(opcoes) <= {"Não identificado", "Instrumental"}:
        st.caption("O idioma das músicas deste catálogo ainda não foi identificado. "
                   "Rode o passo de idiomas no notebook 01 para ativar esse filtro.")

    so_g = b.get("generos") if modo_b == "so" else None
    pref_g = b.get("generos") if modo_b == "preferir" else None
    recs, avisos = rec.recomendar(an["feats"], b["pesos"], n=10, fontes=b["fontes"], excluir=m,
                                  idiomas=idiomas, generos=so_g, preferir_generos=pref_g)
    for aviso in avisos:
        st.warning(aviso)
    if not idiomas:
        st.info("Escolha pelo menos um idioma para ver as recomendações.")
    elif recs.empty:
        st.info("Não encontrei músicas com esses ajustes. Tente incluir mais gêneros ou idiomas.")
    else:
        st.markdown('<div class="sint-olho" style="margin-top:8px">Recomendações</div>', unsafe_allow_html=True)

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
                if b1.button("👍 Gostei", key=f"sim_{b['busca_id']}_{mid}", width="stretch"):
                    banco.registrar_gostou(conexao_uso(), b["busca_id"], mid, True, dados)
                    st.toast("Que bom! Isso ajuda a melhorar as recomendações.")
                if b2.button("👎 Não gostei", key=f"nao_{b['busca_id']}_{mid}", width="stretch"):
                    banco.registrar_gostou(conexao_uso(), b["busca_id"], mid, False, dados)
                    st.toast("Anotado! Isso também ajuda.")
