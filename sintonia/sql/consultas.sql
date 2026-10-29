-- Consultas de exemplo para explorar o catálogo e o uso do app.
-- Rode no notebook 02 (sqlite3 + pandas) ou em qualquer cliente SQLite (ex.: DB Browser for SQLite).

-- 1) Quantas músicas de cada fonte, e quantas têm voz cantada
SELECT fonte,
       COUNT(*)                         AS musicas,
       SUM(tem_voz)                     AS com_voz,
       ROUND(AVG(segundos_analisados))  AS segundos_medios
FROM musicas
GROUP BY fonte;

-- 2) Os artistas com mais músicas no catálogo
SELECT artista, COUNT(*) AS musicas
FROM musicas
GROUP BY artista
ORDER BY musicas DESC
LIMIT 15;

-- 3) Média de algumas características por fonte (Deezer x Jamendo)
SELECT m.fonte,
       ROUND(AVG(CASE WHEN c.nome = 'rit_andamento'   THEN c.valor END), 1) AS andamento_bpm,
       ROUND(AVG(CASE WHEN c.nome = 'mel_saltos'      THEN c.valor END), 3) AS saltos_melodia,
       ROUND(AVG(CASE WHEN c.nome = 'voz_vibrato'     THEN c.valor END), 1) AS vibrato_cents,
       ROUND(AVG(CASE WHEN c.nome = 'har_maior_menor' THEN c.valor END), 3) AS maior_menos_menor
FROM caracteristicas c
JOIN musicas m ON m.id = c.musica_id
GROUP BY m.fonte;

-- 4) As 10 músicas com melodia mais "saltitante"
SELECT m.titulo, m.artista, ROUND(c.valor, 2) AS proporcao_de_saltos
FROM caracteristicas c
JOIN musicas m ON m.id = c.musica_id
WHERE c.nome = 'mel_saltos' AND c.valor IS NOT NULL
ORDER BY c.valor DESC
LIMIT 10;

-- 5) Tons mais comuns no catálogo
SELECT tom, COUNT(*) AS musicas
FROM musicas
GROUP BY tom
ORDER BY musicas DESC;

-- ---------------------------------------------------------- uso do app (dados/uso.db)

-- 6) O que as pessoas mais marcam no teste de escuta
SELECT partes_marcadas, COUNT(*) AS buscas
FROM buscas
GROUP BY partes_marcadas
ORDER BY buscas DESC;

-- 7) Peso médio que as pessoas dão a cada aspecto
SELECT ROUND(AVG(peso_melodia), 2)  AS melodia,
       ROUND(AVG(peso_voz), 2)      AS voz,
       ROUND(AVG(peso_ritmo), 2)    AS ritmo,
       ROUND(AVG(peso_harmonia), 2) AS harmonia,
       ROUND(AVG(peso_som), 2)      AS som
FROM buscas;

-- 8) Taxa de acerto: das recomendações avaliadas, quantas tinham "aquilo"?
--    (por posição na lista: as primeiras deveriam acertar mais)
SELECT posicao,
       COUNT(gostou)                    AS avaliadas,
       ROUND(AVG(gostou) * 100, 1)      AS acerto_pct
FROM recomendacoes
WHERE gostou IS NOT NULL
GROUP BY posicao
ORDER BY posicao;
