"""Visual "Vinil retrô" do app: fontes, cartões e detalhes.

As cores principais ficam em .streamlit/config.toml (tema do Streamlit).
Aqui vai o CSS extra que o tema sozinho não faz.
"""

CREME = "#F6EFE3"
PAPEL = "#FFF9F0"
AREIA = "#EFE4D2"
CAFE = "#2B2118"
CAFE_SUAVE = "#7A6A58"
TERRACOTA = "#C94A2E"
MOSTARDA = "#D9952B"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,800&family=Work+Sans:wght@400;500;600;700&display=swap');

.stApp {{ background: {CREME}; }}
.stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea, .stApp button {{
  font-family: 'Work Sans', 'Segoe UI', system-ui, sans-serif;
}}
.stApp h1, .stApp h2, .stApp h3 {{
  font-family: 'Fraunces', Georgia, 'Times New Roman', serif !important;
  color: {CAFE}; letter-spacing: -0.01em;
}}
.stApp h1 {{ font-weight: 800 !important; }}

/* cabeçalho com o disco girando */
.sint-marca {{ display: flex; align-items: center; gap: 14px; margin-bottom: 4px; }}
.sint-disco {{
  width: 52px; height: 52px; border-radius: 50%; flex: none;
  background:
    radial-gradient(circle, {CREME} 0 4px, {TERRACOTA} 5px 11px, transparent 12px),
    repeating-radial-gradient(circle, #3a2e24 0 2px, {CAFE} 2px 4px);
  animation: sint-girar 6s linear infinite;
}}
@keyframes sint-girar {{ to {{ transform: rotate(360deg); }} }}
@media (prefers-reduced-motion: reduce) {{ .sint-disco {{ animation: none; }} }}
.sint-marca h1 {{ margin: 0 !important; padding: 0 !important; font-size: 2.6rem !important; line-height: 1 !important; }}
.sint-sub {{ color: {CAFE_SUAVE}; margin: 4px 0 0; }}

/* rótulo "Passo N" acima dos títulos */
.sint-passo {{
  font: 700 0.75rem/1 'Work Sans', sans-serif; letter-spacing: 0.14em; text-transform: uppercase;
  color: {TERRACOTA}; margin: 1.6rem 0 -0.6rem;
}}

/* ajustes (sliders) */
.sint-aj-cab {{ display: flex; justify-content: space-between; align-items: center; gap: 10px; }}
.sint-aj-nome {{ font: 700 1.1rem/1.2 'Fraunces', Georgia, serif; color: {CAFE}; }}
.sint-aj-desc {{ color: {CAFE_SUAVE}; font-size: 0.92rem; margin-top: 2px; }}
.sint-nivel {{
  font-size: 0.78rem; font-weight: 700; padding: 3px 10px; border-radius: 999px; white-space: nowrap;
  background: {AREIA}; color: {CAFE_SUAVE};
}}
.sint-nivel.n2 {{ background: #F3DDB6; color: #7A4E0E; }}
.sint-nivel.n3 {{ background: #F1C9B9; color: #8A2F1A; }}
.sint-nivel.n4 {{ background: {TERRACOTA}; color: {PAPEL}; }}
.sint-escala {{ display: flex; justify-content: space-between; font-size: 0.75rem; color: {CAFE_SUAVE}; margin-top: -8px; }}

/* cartões de resultado */
.sint-res {{
  display: grid; grid-template-columns: 76px minmax(0, 1fr) 92px; gap: 16px; align-items: start; width: 100%;
}}
.sint-capa {{ width: 76px; height: 76px; border-radius: 10px; object-fit: cover; display: block;
  box-shadow: 0 2px 0 rgba(43,33,24,.12); }}
.sint-capa-vazia {{ background: linear-gradient(135deg, {TERRACOTA}, {MOSTARDA}); }}
.sint-titulo {{ font: 700 1.15rem/1.25 'Fraunces', Georgia, serif; color: {CAFE}; }}
.sint-artista {{ color: {CAFE_SUAVE}; font-size: 0.92rem; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }}
.sint-tag {{ font-size: 0.72rem; font-weight: 700; padding: 2px 8px; border-radius: 999px; background: {AREIA}; color: {CAFE_SUAVE}; }}
.sint-expl {{ margin: 8px 0 6px; font-size: 0.95rem; color: {CAFE}; }}
.sint-barras {{ display: flex; flex-wrap: wrap; gap: 4px 16px; }}
.sint-barra {{ display: flex; align-items: center; gap: 6px; font-size: 0.8rem; color: {CAFE_SUAVE}; font-variant-numeric: tabular-nums; }}
.sint-trilho {{ width: 70px; height: 6px; border-radius: 999px; background: {AREIA}; overflow: hidden; }}
.sint-trilho i {{ display: block; height: 100%; border-radius: inherit; background: {MOSTARDA}; }}
.sint-links {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0 8px; }}
.sint-links a {{
  font-size: 0.8rem; font-weight: 600; padding: 5px 10px; border-radius: 8px;
  border: 1px solid rgba(43,33,24,.18); color: {CAFE} !important; text-decoration: none !important; background: {PAPEL};
}}
.sint-links a:hover {{ border-color: {TERRACOTA}; color: {TERRACOTA} !important; }}
.sint-anel {{
  width: 88px; height: 88px; flex: none; border-radius: 50%; position: relative; display: grid; place-items: center;
  background: conic-gradient({TERRACOTA} calc(var(--p) * 1%), {AREIA} 0);
}}
.sint-anel::before {{ content: ""; position: absolute; inset: 8px; border-radius: 50%; background: {PAPEL}; }}
.sint-anel span {{ position: relative; text-align: center; line-height: 1; }}
.sint-anel b {{ display: block; font: 800 1.45rem/1 'Fraunces', Georgia, serif; color: {CAFE}; }}
.sint-anel small {{ font-size: 0.6rem; letter-spacing: 0.06em; text-transform: uppercase; color: {CAFE_SUAVE}; }}
@media (max-width: 640px) {{
  .sint-res {{ grid-template-columns: 64px minmax(0, 1fr); }}
  .sint-capa {{ width: 64px; height: 64px; }}
  .sint-anel {{ grid-column: 2; grid-row: 1; justify-self: end; width: 72px; height: 72px; }}
  .sint-res > .sint-info {{ grid-column: 1 / -1; }}
}}

/* cartões com borda do Streamlit em papel */
div[data-testid="stVerticalBlockBorderWrapper"] {{ background: {PAPEL}; }}
</style>
"""

NIVEIS = [(0, "Não importa", 0), (1, "Pouco", 1), (31, "Médio", 2), (61, "Muito", 3), (86, "Essencial", 4)]


def nivel(valor: int) -> tuple[str, int]:
    """Texto e intensidade (0 a 4) de um peso de 0 a 100."""
    texto, classe = NIVEIS[0][1], 0
    for limite, t, c in NIVEIS:
        if valor >= limite:
            texto, classe = t, c
    return texto, classe
