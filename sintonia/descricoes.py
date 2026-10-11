"""Textos em português simples para cada aspecto e característica.

É aqui que os números viram frases que uma pessoa leiga entende, como
"melodia com saltos grandes" ou "voz com bastante vibrato".
"""

ASPECTO_INFO = {
    "melodia": {
        "emoji": "🎵", "nome": "Melodia",
        "explica": "O “desenho” que a voz canta: se sobe e desce, dá saltos ou anda em passinhos.",
    },
    "voz": {
        "emoji": "🎤", "nome": "Voz",
        "explica": "Como a pessoa canta: grave ou aguda, com vibrato, mais brilhante ou mais aveludada.",
    },
    "ritmo": {
        "emoji": "🥁", "nome": "Ritmo",
        "explica": "A batida e o balanço: rápido ou lento, reto ou sincopado.",
    },
    "harmonia": {
        "emoji": "🎹", "nome": "Harmonia",
        "explica": "O clima dos acordes: alegre, melancólico, estável ou cheio de mudanças.",
    },
    "som": {
        "emoji": "🎚️", "nome": "Som geral",
        "explica": "Os instrumentos e a produção: brilhante ou quente, com muito grave, cheio ou leve.",
    },
}

# característica -> (texto quando o valor é ALTO, texto quando é BAIXO)
# None = esse lado não é interessante de mencionar
TEXTOS = {
    # melodia
    "mel_extensao": ("melodia que passeia por muitas notas, do grave ao agudo",
                     "melodia contida, que fica numa faixa estreita de notas"),
    "mel_passos": ("melodia que anda em passinhos, de nota vizinha em nota vizinha", None),
    "mel_saltos": ("melodia com saltos grandes entre as notas",
                   "melodia bem ligadinha, quase sem saltos"),
    "mel_repeticao": ("melodia que repete muito a mesma nota, quase falada",
                      "melodia que muda de nota o tempo todo"),
    "mel_subida": ("melodia que tende a subir", "melodia que tende a descer"),
    "mel_notas_por_seg": ("melodia rápida, com muitas notas", "melodia lenta, com notas longas"),
    "mel_duracao_nota": ("notas longas e sustentadas", "notas curtinhas e picotadas"),
    "mel_frase": ("frases melódicas longas, de fôlego", "frases curtas, com respiros frequentes"),
    # voz
    "voz_altura": ("voz que canta numa região aguda", "voz que canta numa região grave"),
    "voz_vibrato": ("voz com bastante vibrato", "voz reta, sem vibrato"),
    "voz_brilho": ("voz brilhante, de timbre claro", "voz aveludada, de timbre escuro"),
    "voz_soprosidade": ("voz soprosa, com bastante ar", "voz limpa e focada"),
    "voz_presenca": ("voz presente quase o tempo todo", "voz que aparece pouco"),
    # ritmo
    "rit_andamento": ("andamento rápido", "andamento lento"),
    "rit_ataques_por_seg": ("ritmo cheio, com muitos ataques", "ritmo espaçado e calmo"),
    "rit_regularidade": ("batida firme e regular", "ritmo solto, menos marcado"),
    "rit_sincopa": ("ritmo sincopado, com acentos no contratempo", "ritmo reto, com acentos no tempo"),
    "rit_peso_batida": ("bateria e percussão em destaque", "pouca percussão"),
    # harmonia
    "har_maior_menor": ("acordes com clima mais alegre (tonalidade maior)",
                        "acordes com clima mais melancólico (tonalidade menor)"),
    "har_clareza_tom": ("tonalidade bem definida", "tonalidade ambígua, que não se resolve"),
    "har_complexidade": ("harmonia rica, com muitas notas diferentes", "harmonia simples, com poucas notas"),
    "har_trocas": ("acordes que mudam bastante", "acordes que mudam pouco, harmonia estável"),
    # som
    "som_brilho": ("som brilhante", "som escuro e quente"),
    "som_largura": ("som cheio, ocupando muitas frequências", "som enxuto"),
    "som_aspereza": ("som áspero, com ruído e distorção", "som suave e limpo"),
    "som_dinamica": ("som com variações fortes de volume", "volume constante, som comprimido"),
    "som_graves": ("muito grave, com baixo forte", "pouco grave, som leve"),
}


# nomes curtos para gráficos e tabelas (Power BI, app)
ROTULOS = {
    "mel_extensao": "Extensão da melodia (semitons)", "mel_passos": "Melodia em passinhos",
    "mel_saltos": "Saltos na melodia", "mel_repeticao": "Notas repetidas",
    "mel_subida": "Tendência a subir", "mel_notas_por_seg": "Notas por segundo",
    "mel_duracao_nota": "Duração das notas (s)", "mel_frase": "Tamanho das frases (s)",
    "voz_altura": "Altura da voz (nota MIDI)", "voz_vibrato": "Vibrato (cents)",
    "voz_brilho": "Brilho da voz", "voz_soprosidade": "Voz soprosa", "voz_presenca": "Presença da voz",
    "rit_andamento": "Andamento (BPM)", "rit_ataques_por_seg": "Ataques por segundo",
    "rit_regularidade": "Regularidade da batida", "rit_sincopa": "Síncope",
    "rit_peso_batida": "Peso da percussão", "har_maior_menor": "Maior (+) / menor (−)",
    "har_clareza_tom": "Clareza do tom", "har_complexidade": "Complexidade harmônica",
    "har_trocas": "Trocas de acorde", "som_brilho": "Brilho do som", "som_largura": "Som cheio",
    "som_aspereza": "Aspereza", "som_dinamica": "Variação de volume", "som_graves": "Peso dos graves",
}


def aspecto_de(nome_caracteristica: str) -> str:
    prefixo = nome_caracteristica.split("_", 1)[0]
    return {"mel": "melodia", "voz": "voz", "rit": "ritmo", "har": "harmonia", "som": "som"}[prefixo]


def frase(nome: str, z: float) -> str | None:
    """Texto da característica conforme o valor padronizado (z) seja alto ou baixo."""
    if nome not in TEXTOS:
        return None
    alto, baixo = TEXTOS[nome]
    return alto if z > 0 else baixo
