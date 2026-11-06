# Metodologia

Este documento explica como cada número do README é calculado e como interpretá-lo. As escolhas de
tratamento de dados (definição de carga, fuso, parser, temperatura, calendário) estão em
[`dados.md`](dados.md); aqui o foco é o raciocínio, as fórmulas e o desenho da validação.

## 1. Pergunta

Um modelo feito só com dados abertos prevê a carga horária do dia seguinte, por subsistema, tão bem quanto a
carga programada do ONS? Onde cada um erra mais, e a combinação dos dois é melhor que cada um?

## 2. Dados e período

| Fonte | Uso | Período |
|---|---|---|
| API de carga do ONS, `cargaverificada` | alvo (`val_cargaglobal`) e lags | 2020 a out/2026 |
| API de carga do ONS, `cargaprogramada` | benchmark oficial | dez/2020 (SE/CO) ou mar/2021 a out/2026 |
| Open-Meteo, Previous Runs API | temperatura prevista na rodada da véspera | 2022 a out/2026 |
| Open-Meteo, Previous Runs API | irradiância e nuvens previstas na véspera (variante `modelo_irr`) | 19/01/2024 a out/2026 |
| Biblioteca `holidays` + regras próprias | feriados nacionais, Carnaval, pontes, vésperas | todo o período |

Treino a partir de 15/01/2022 (início da temperatura prevista); teste fora da amostra de jan/2024 a
out/2026, cerca de 25 mil horas por subsistema. O SIN é a soma dos quatro subsistemas, só nas horas em que os
quatro estão completos.

## 3. Pipeline

| Etapa | Script | Módulo | Saída |
|---|---|---|---|
| Download da carga (cache mensal) | `scripts/download_ons.py` | `ons.py` | `data/raw/ons/` |
| Download da temperatura, da irradiância e das nuvens previstas | `scripts/download_weather.py` | `weather.py` | `data/raw/openmeteo/`, `data/raw/openmeteo_solar/` |
| Base horária e features | `scripts/build_dataset.py` | `features.py`, `calendario.py` | `data/interim/features*.parquet` |
| Backtest (modelo, D-2, oráculo e as variantes com irradiância) | `scripts/backtest.py` | `model.py` | `data/processed/bt_*.parquet` |
| Métricas e testes | `scripts/avaliar.py` | `metricas.py` | `reports/*.csv`, `reports/resultados.json` |
| Antes/depois da irradiância (janelas, 9h-16h, Diebold-Mariano) | `scripts/comparar_irradiancia.py` | `comparacao.py` | `reports/irradiancia_*.csv` |
| Figuras | `scripts/make_figures.py` | | `reports/figures/` |
| Números de apoio à aplicação | `scripts/aplicacao.py` | | `reports/aplicacao.json` |

## 4. Modelo

**Alvo relativo.** Para cada área, hora *h* do dia D:

```
base(D)   = média da carga horária de D-8 a D-2
y_rel(D,h) = carga(D,h) / base(D)
previsão(D,h) = modelo(features) × base(D)
```

Prever a forma relativa em vez do nível absoluto deixa o modelo robusto ao crescimento da carga ao longo
dos anos.

**Algoritmo.** LightGBM com perda L1 (alinhada ao erro percentual), 900 árvores, taxa 0,03, 63 folhas
(`model.PARAMS`), um modelo por subsistema.

**Features** (`features.py`), todas conhecidas na manhã de D-1:

| Grupo | Conteúdo |
|---|---|
| Carga passada | mesma hora em D-2, D-3, D-7, D-14, D-21 e D-28; perfil médio das últimas 4 semanas |
| Manhã de D-1 | carga de 00h a 10h de D-1 (versão principal; ausente na variante D-2) |
| Temperatura | prevista para cada hora de D na rodada da véspera; máxima e média do dia; ponderada pela população dos centros de carga |
| Calendário | hora, dia da semana, feriado, ponte, véspera, pós-feriado, fim de ano, inclusive nos dias usados como lag |
| Irradiância e nuvens (só nas variantes `*_irr`) | `ghi` e `nuv` previstos na véspera para cada hora de D; `ghi_lag2` (irradiância observada em D-2) e `ghi_delta` (diferença); média do dia de cada uma; mesmos centros de carga e pesos da temperatura |

**Combinação.** `previsão_combinada = (previsão_modelo + carga_programada_ONS) / 2`, hora a hora. Sem
pesos ajustados, para não usar o próprio teste na escolha dos pesos.

## 5. Desenho da validação

* **Retreino mensal, origem móvel:** o modelo usado no mês M é treinado com todos os dias alvo até dois dias
  antes do primeiro dia de M (`model.corte_treino`), como se fosse treinado na véspera do mês.
* **O que se sabe na manhã de D-1:** carga verificada completa até D-2, carga de D-1 até as 10h, previsão de
  temperatura, irradiância e nuvens da rodada da véspera e o calendário. Os testes em
  `tests/test_features.py` alteram a carga de D-1 depois das 10h e a de D e verificam que nenhuma feature
  muda; os de `tests/test_irradiancia.py` fazem o mesmo com a irradiância e as nuvens (ver seção 10).
* **Variantes para medir o valor de cada informação:** sem a manhã de D-1 (só até D-2) e "oráculo", com a
  temperatura observada no lugar da prevista. O oráculo não é previsão: mostra quanto se ganharia com uma
  previsão de tempo perfeita.
* **Variantes com irradiância e nuvens** (seção 10): `modelo_irr` (a principal), `modelo_d2_irr`, `oraculo_irr`,
  `modelo_irr_estrito` e `modelo_irr_embaralhado`. O plano foi commitado antes do backtest
  (`preregistro_irradiancia.md`).
* **Baselines:** mesma hora na semana anterior e média das últimas 4 semanas na mesma hora.

## 6. Métricas e testes

* **MAPE:** média de |previsto − real| / real, em %, hora a hora.
* **MAE:** média de |previsto − real|, em MW.
* **Cauda (`reports/aplicacao.json`):** percentis 95 e 99 do erro absoluto horário, e número de horas com
  erro acima de 5% da carga. É o que pesa no dimensionamento de reserva.
* **Diebold-Mariano:** compara o erro absoluto **diário** de dois métodos (média das 24 horas), com variância
  robusta a autocorrelação (Newey-West) e correção de Harvey et al. (1997) (`metricas.diebold_mariano`).
  Estatística negativa = o primeiro método erra menos; p < 0,05 = diferença estatisticamente significativa.
  Usar o erro diário evita tratar como independentes as 24 horas de um mesmo dia.
* **Janelas e faixas (irradiância):** o antes/depois é medido na janela principal (jan/2024 a out/2026), numa
  janela secundária em que todo mês de teste já tem pelo menos 12 meses de irradiância prevista no treino
  (fev/2025 a out/2026) e, nas duas, só nas horas das 9h às 16h (`comparacao.py`,
  `reports/irradiancia_*.csv`).

## 7. Premissas

| Premissa | Valor | Justificativa |
|---|---|---|
| Carga que corresponde à programada | `val_cargaglobal` (com MMGD) | é a única consistente com a programada a partir de 2023 (`dados.md`) |
| Fuso | UTC-3 fixo | sem horário de verão desde 2019 |
| Horário da previsão | manhã de D-1, com carga até 10h | o ONS programa o dia seguinte por volta do meio-dia |
| Peso de cada cidade na temperatura, na irradiância e nas nuvens | população da região metropolitana | simples e estável; `config.py`; não é a distribuição da MMGD instalada |
| Feriados | nacionais e Carnaval | regionais não entram |
| Combinação | média simples, peso 1/2 | evita ajustar pesos no teste |

## 8. Sensibilidade

| SIN, MAPE, jan/2024 a out/2026 | |
|---|---|
| Só até D-2, sem irradiância | 1,97% |
| Só até D-2, com irradiância | 1,89% |
| Com a manhã de D-1, sem irradiância | 1,84% |
| **Com a manhã de D-1 e irradiância (principal)** | **1,76%** |
| Idem, com a previsão `previous_day2` (estrita) | 1,76% |
| Idem, com a irradiância de outro dia (controle) | 1,82% |
| Oráculo de temperatura | 1,67% |
| Oráculo de temperatura, irradiância e nuvens | 1,62% |
| Média modelo sem irradiância + ONS | 1,68% |
| Média modelo com irradiância + ONS | 1,63% |

## 9. Como interpretar

* **Empate no SIN, vitória nas áreas menores.** No SIN (p = 0,086) e no SE/CO (p = 0,68) a diferença entre
  modelo e ONS não é significativa; no Sul, Nordeste e Norte, o modelo erra menos com significância.
* **A combinação é o resultado prático.** Ela é melhor que o ONS em todas as áreas e reduz as horas de erro
  grande no SIN em 48%. Isso indica que o modelo traz informação que a programação não usa,
  principalmente no meio do dia.
* **Feriados são o ponto fraco do modelo.** Há poucos exemplos de cada feriado no treino; quem programa
  compensa com experiência. Num uso real, a previsão oficial deve prevalecer nesses dias.
* **O erro do ONS no meio do dia** pode vir em parte de revisões da estimativa de MMGD, e não só de erro de
  previsão. A leitura correta é "é ali que a previsão está mais difícil", não "o ONS está errando mais".

## 10. Irradiância e nuvens previstas

**Dados.** `shortwave_radiation` e `cloud_cover` da Previous Runs API do Open-Meteo, nos mesmos centros de
carga e com os mesmos pesos de população da temperatura (detalhes em `dados.md`). A previsão só existe a
partir de 19/01/2024; antes disso a coluna fica ausente.

**Colunas.** Por hora: `ghi` e `nuv` (previstas para D), `ghi_lag2` (irradiância observada em D-2, na mesma
hora) e `ghi_delta = ghi - ghi_lag2`. Por dia: `ghi_media_dia` e `nuv_media_dia`. Nenhuma coluna foi
acrescentada depois de ver resultados.

**Variantes.**

| Variante | O que muda em relação à base |
|---|---|
| `modelo_irr` | previsão `previous_day1` (principal) |
| `modelo_d2_irr` | idem, sem a carga da manhã de D-1 |
| `oraculo_irr` | irradiância e nuvens observadas de D (limite superior) |
| `modelo_irr_estrito` | previsão `previous_day2` (cerca de 48 h antes), seguramente anterior à programação |
| `modelo_irr_embaralhado` | controle: as mesmas colunas, com a irradiância de 37 dias antes |

**Regra de decisão** (commitada antes do backtest): `modelo_irr` vira o padrão se o MAPE do SIN cair, o
Diebold-Mariano contra `modelo` no SIN der p < 0,05 e nenhum subsistema piorar com p < 0,05. O ganho só é
atribuído à irradiância se for maior que o dobro da variação do controle embaralhado. Resultado: todas as
condições foram cumpridas (`reports/irradiancia_diebold_mariano.csv`). No SIN, o ganho foi de 0,075 ponto
(1,835% para 1,760%), contra 0,018 do controle.

**Leitura.** O ganho aparece em todas as horas, é maior entre 9h e 14h e cresce com o tempo, porque o treino
de 2022 e 2023 não tem a previsão. O controle embaralhado não é nulo em todo recorte (das 9h às 16h do SIN, p =
0,038), então o número a citar é o do modelo real menos o do controle, não o do modelo real isolado.
`modelo_irr_estrito` dá o mesmo MAPE que `modelo_irr`, o que afasta a hipótese de que o ganho viesse de
previsões publicadas depois da programação. Quanto do ganho é efeito da MMGD, quanto é tipo de tempo e quanto é
a estimativa de MMGD do próprio ONS não foi separado.
