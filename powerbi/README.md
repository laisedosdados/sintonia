# Painel no Power BI

O Power BI Desktop é gratuito, mas só funciona no **Windows**. Baixe pela Microsoft Store.

## 1. Gerar os arquivos

No notebook (ou no terminal), rode:

```
python -m sintonia.exportar
```

Isso cria em `powerbi/dados/`:

| Arquivo | O que tem |
|---|---|
| `musicas.csv` | uma linha por música: título, artista, fonte, tom, se tem voz |
| `caracteristicas.csv` | as características com nome amigável, em formato longo (`musica_id`, `aspecto`, `caracteristica`, `valor`, `z`) |
| `mapa.csv` | posição `x`, `y` de cada música num mapa 2D, por aspecto (`geral`, `melodia`, `voz`...) |
| `buscas.csv` | cada busca feita no app: partes marcadas no teste de escuta e pesos |
| `recomendacoes.csv` | o que foi recomendado em cada busca e se a pessoa gostou |

## 2. Importar

1. **Página Inicial → Obter dados → Texto/CSV**, e abra cada arquivo.
2. Em **Modelo**, ligue as tabelas:
   - `musicas[id]` → `caracteristicas[musica_id]` (um para muitos)
   - `musicas[id]` → `mapa[musica_id]` (um para muitos)
   - `buscas[id]` → `recomendacoes[busca_id]` (um para muitos)

## 3. Visuais sugeridos

**Página "Mapa musical"**
- *Gráfico de dispersão* com `mapa[x]` e `mapa[y]`, legenda `musicas[fonte]`, dica de ferramenta com título e artista.
- *Segmentação* por `mapa[aspecto]`: troque entre "melodia", "voz", "geral"... Músicas perto uma da outra são parecidas naquele aspecto.

**Página "Características"**
- *Segmentação* por `caracteristicas[aspecto]` e por `musicas[artista]`.
- *Gráfico de barras*: eixo `caracteristicas[caracteristica]`, valor = média de `z`. Mostra o "perfil" de um artista: barras para a direita = acima da média do catálogo.
- *Histograma* (gráfico de colunas) de `valor` para uma característica, como "Andamento (BPM)".

**Página "Uso do app"**
- *Cartão*: número de buscas.
- *Barras*: contagem por `buscas[partes_marcadas]` — o que as pessoas descobrem que as atrai.
- *Linha*: `recomendacoes[posicao]` × média de `gostou` — se a primeira sugestão acerta mais que a décima, o recomendador está funcionando.

## Medida DAX útil

```DAX
Taxa de acerto = AVERAGE(recomendacoes[gostou])
```

Formate como porcentagem.
