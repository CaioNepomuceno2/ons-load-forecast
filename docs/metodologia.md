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
| Biblioteca `holidays` + regras próprias | feriados nacionais, Carnaval, pontes, vésperas | todo o período |

Treino a partir de 15/01/2022 (início da temperatura prevista); teste fora da amostra de jan/2024 a
out/2026, cerca de 25 mil horas por subsistema. O SIN é a soma dos quatro subsistemas, só nas horas em que os
quatro estão completos.

## 3. Pipeline

| Etapa | Script | Módulo | Saída |
|---|---|---|---|
| Download da carga (cache mensal) | `scripts/download_ons.py` | `ons.py` | `data/raw/ons/` |
| Download da temperatura prevista | `scripts/download_weather.py` | `weather.py` | `data/raw/openmeteo/` |
| Base horária e features | `scripts/build_dataset.py` | `features.py`, `calendario.py` | `data/interim/features*.parquet` |
| Backtest (modelo, D-2, oráculo) | `scripts/backtest.py` | `model.py` | `data/processed/bt_*.parquet` |
| Métricas e testes | `scripts/avaliar.py` | `metricas.py` | `reports/*.csv`, `reports/resultados.json` |
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

**Combinação.** `previsão_combinada = (previsão_modelo + carga_programada_ONS) / 2`, hora a hora. Sem
pesos ajustados, para não usar o próprio teste na escolha dos pesos.

## 5. Desenho da validação

* **Retreino mensal, origem móvel:** o modelo usado no mês M é treinado com todos os dias alvo até dois dias
  antes do primeiro dia de M (`model.corte_treino`), como se fosse treinado na véspera do mês.
* **O que se sabe na manhã de D-1:** carga verificada completa até D-2, carga de D-1 até as 10h, previsão de
  temperatura da rodada da véspera e o calendário. Os testes em `tests/test_features.py` alteram a carga de
  D-1 depois das 10h e a de D e verificam que nenhuma feature muda.
* **Variantes para medir o valor de cada informação:** sem a manhã de D-1 (só até D-2) e "oráculo", com a
  temperatura observada no lugar da prevista. O oráculo não é previsão: mostra quanto se ganharia com uma
  previsão de tempo perfeita.
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

## 7. Premissas

| Premissa | Valor | Justificativa |
|---|---|---|
| Carga que corresponde à programada | `val_cargaglobal` (com MMGD) | é a única consistente com a programada a partir de 2023 (`dados.md`) |
| Fuso | UTC-3 fixo | sem horário de verão desde 2019 |
| Horário da previsão | manhã de D-1, com carga até 10h | o ONS programa o dia seguinte por volta do meio-dia |
| Peso de cada cidade na temperatura | população da região metropolitana | simples e estável; `config.py` |
| Feriados | nacionais e Carnaval | regionais não entram |
| Combinação | média simples, peso 1/2 | evita ajustar pesos no teste |

## 8. Sensibilidade

| SIN, MAPE | |
|---|---|
| Só até D-2 | 1,97% |
| Com a manhã de D-1 (principal) | 1,84% |
| Oráculo de temperatura | 1,67% |
| Média modelo + ONS | 1,68% |

## 9. Como interpretar

* **Empate no SIN, vitória nas áreas menores.** No SIN e no SE/CO a diferença entre modelo e ONS não é
  significativa; no Sul, Nordeste e Norte, o modelo erra menos com significância.
* **A combinação é o resultado prático.** Ela é melhor que o ONS em todas as áreas e reduz as horas de erro
  grande no SIN em 42%. Isso indica que o modelo traz informação que a programação não usa,
  principalmente no meio do dia.
* **Feriados são o ponto fraco do modelo.** Há poucos exemplos de cada feriado no treino; quem programa
  compensa com experiência. Num uso real, a previsão oficial deve prevalecer nesses dias.
* **O erro do ONS no meio do dia** pode vir em parte de revisões da estimativa de MMGD, e não só de erro de
  previsão. A leitura correta é "é ali que a previsão está mais difícil", não "o ONS está errando mais".
