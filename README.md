# Previsão de carga do dia seguinte: modelo aberto × ONS

[![CI](https://github.com/CaioNepomuceno2/ons-load-forecast/actions/workflows/ci.yml/badge.svg)](https://github.com/CaioNepomuceno2/ons-load-forecast/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)

**Um modelo feito só com dados abertos consegue prever a carga de amanhã tão bem quanto o ONS?**

Toda manhã o Operador Nacional do Sistema Elétrico programa a operação do dia seguinte a partir de uma
carga programada, hora a hora, para cada subsistema. Comparei essa carga programada com um modelo
LightGBM que usa apenas o que estaria disponível na véspera: carga verificada, previsão de temperatura e
calendário. O teste cobre **34 meses fora da amostra (jan/2024 a out/2026), cerca de 25 mil horas por
subsistema**, com o modelo retreinado mês a mês.

## Resultado

| MAPE horário, jan/2024 a out/2026 | Modelo aberto | ONS (programada) | Média modelo + ONS | Mesma hora na semana anterior |
|---|---|---|---|---|
| **SIN** | **1,84%** | 1,91% | **1,68%** | 3,85% |
| Sudeste/Centro-Oeste | 2,42% | **2,32%** | **2,08%** | 5,09% |
| Sul | **3,51%** | 3,92% | **3,31%** | 6,55% |
| Nordeste | **2,33%** | 2,71% | **2,27%** | 3,61% |
| Norte | **2,08%** | 2,63% | 2,16% | 3,15% |

![MAPE por subsistema](reports/figures/01_mape_subsistema.png)

* **No SIN, o modelo empata com o ONS.** A diferença de 1,84% para 1,91% não é estatisticamente
  significativa (Diebold-Mariano sobre o erro diário, p = 0,37). No Sudeste/Centro-Oeste, o ONS fica um
  pouco à frente, também sem significância (p = 0,27).
* **No Sul, no Nordeste e no Norte, o modelo erra menos que o ONS**, com significância (p < 0,01 nos três).
* **A média simples entre modelo e ONS é o melhor resultado em quatro das cinco áreas**: no SIN, o erro cai
  12% em relação ao ONS sozinho (1,68% contra 1,91%; p < 10⁻⁸). Os dois erram em lugares diferentes, então
  a combinação aproveita o melhor de cada um. Na prática, a carga programada poderia entrar como mais uma
  feature ou numa média, sem trocar o processo do ONS.
* Os dois ficam muito à frente da regra ingênua "repetir a semana passada" (3,85% no SIN).

**O que isso significa:** com uma carga média de 81,5 GW no SIN, cada ponto de MAPE é da ordem de 800 MW.
A média modelo + ONS erra, em média, **192 MW a menos por hora** que o ONS sozinho (1.397 contra 1.589 MW).
Um modelo aberto, que roda em um notebook, já serve como segunda opinião útil para a programação.

### Onde cada um erra

![Tipo de dia](reports/figures/03_tipo_de_dia.png)

* **O ONS ganha nos feriados e pontes** (2,5% contra 3,9% no SIN). O modelo viu poucos exemplos de cada
  feriado (de dois a quatro de cada no treino), e é aí que a experiência de quem programa faz diferença.
* **O modelo ganha nos fins de semana e nos dias quentes.** Nos 10% de dias com a maior máxima prevista, o
  erro do SIN é de 1,9% contra 2,3% do ONS.
* **O ONS ganha de madrugada e no fim da noite; o modelo ganha no meio do dia.**

![MAPE por hora](reports/figures/02_mape_por_hora.png)

### No meio do dia, o erro do ONS cresce com a geração distribuída

A carga global inclui a estimativa de micro e minigeração distribuída (MMGD, basicamente solar nos
telhados). Entre 10h e 14h, a MMGD saiu de 21% da carga do SIN em 2024 para 32% em 2026. No mesmo período,
o MAPE do ONS nesse horário subiu de 2,3% para 3,4%, enquanto o do modelo ficou entre 2,1% e 2,5%:

| SIN, 10h-14h | MMGD / carga | Modelo | ONS |
|---|---|---|---|
| 2024 | 21% | 2,23% | 2,27% |
| 2025 | 28% | 2,14% | 3,04% |
| 2026 (jan-out) | 32% | 2,47% | 3,36% |

![Meio do dia e MMGD](reports/figures/06_meio_dia_mmgd.png)

Leia isso com cuidado: a parcela de MMGD da carga verificada também é uma **estimativa** do ONS, revisada
depois do fato. Parte desse erro pode vir de mudanças na estimativa, e não da previsão em si (ver
Limitações). Mesmo assim, é no horário solar que o ONS mais perdeu precisão, e foi esse ganho que tirou o
modelo do empate.

### Exemplo: Carnaval de 2025

![Carnaval](reports/figures/05_carnaval_2025.png)

A regra "repetir a semana passada" erra 11,5% na segunda e 14,3% na terça de Carnaval (MAPE do dia). O
modelo erra 1,2% e 2,1%, e o ONS, 2,8% e 3,1%. Na Quarta-feira de Cinzas, que tem meia jornada, o ONS acerta
em cheio (0,5%) e o modelo erra 2,7%.

## Na prática: o que muda para quem decide

### O problema hoje
* **Quem programa a operação (ONS e agentes):** a carga programada erra mais justamente onde o sistema está
  mudando. Entre 10h e 14h, o MAPE do ONS no SIN subiu de 2,3% (2024) para 3,4% (2026), enquanto a geração
  distribuída foi de 21% para 32% da carga nesse horário. Em 2026, o erro médio do ONS nesse horário foi de
  2.943 MW por hora.
* **Distribuidoras:** precisam prever a própria carga para comprar energia, contratar uso da rede e operar.
  A MMGD dos telhados, que elas não medem em tempo real, torna a carga do meio do dia mais difícil de prever.
* **Comercializadoras e consumidores livres:** a carga do sistema move o preço de curto prazo; prever melhor
  a carga é prever melhor o despacho.

### O que se ganha

| Ganho | Quanto (SIN, jan/2024 a out/2026) | De onde vem o número |
|---|---|---|
| Erro médio menor usando a média modelo + ONS | **1.397 contra 1.589 MW por hora (−192 MW, −12%)** | **Medido** fora da amostra (`reports/mape_geral.csv`, `reports/aplicacao.json`) |
| Menos horas de erro grande (acima de 5% da carga) | **853 contra 1.471 horas (−42%)** | **Medido** (`reports/aplicacao.json`) |
| Erro de cauda menor (percentil 95 do erro horário) | **3.915 contra 4.522 MW (−607 MW)** | **Medido** (`reports/aplicacao.json`) |
| Erro menor no meio do dia, onde a MMGD pesa | 2026, 10h-14h: modelo 2.162 MW contra ONS 2.943 MW por hora | **Medido** (`reports/aplicacao.json`) |
| Erro menor no Sul, Nordeste e Norte com o modelo sozinho | MAPE de 3,51%, 2,33% e 2,08% contra 3,92%, 2,71% e 2,63% do ONS, com significância | **Medido** (Diebold-Mariano em `reports/diebold_mariano.csv`) |

O ganho está em MW, não em R$: converter erro de previsão em custo exige o custo de reserva e de
redespacho de cada hora, que não estão nos dados usados aqui. O que dá para dizer é a direção: erro de
cauda menor reduz a reserva necessária para cobrir os desvios, e menos horas de erro grande significam menos
ajustes de despacho fora da programação.

### Por que aplicar
* **O problema vai crescer:** a MMGD ao meio-dia já é estimada em 30% a 43% da carga dos subsistemas em 2026
  (`docs/dados.md`). O erro do ONS no meio do dia acompanha esse crescimento.
* **Os dois métodos erram em lugares diferentes:** o ONS ganha em feriados e de madrugada; o modelo ganha nos
  fins de semana, nos dias quentes e no meio do dia. Por isso a média dos dois é melhor que qualquer um em
  quatro das cinco áreas. Combinar não exige trocar o processo de quem programa, só acrescentar uma previsão.
* **Custo baixo e auditável:** dados abertos, código aberto, retreino mensal em minutos por subsistema.

### Como aplicar (roteiro de adoção)
1. **Dados que melhoram o resultado:** medição de carga em tempo real (em vez da série revisada), previsão
   meteorológica comercial com irradiância e nebulosidade (que movem a MMGD), uma estimativa própria de
   MMGD e os feriados estaduais e municipais da área. Para uma distribuidora, a carga da própria área de
   concessão substitui a do subsistema.
2. **Recalibrar:** rodar `scripts/build_dataset.py` e `scripts/backtest.py` com a nova série; o retreino é
   mensal e por área.
3. **Piloto de 3 meses em paralelo:** gerar a previsão todo dia, sem mudar nada no processo, e comparar o
   MAPE e as horas de erro acima de 5% do modelo, da previsão atual e da média dos dois.
4. **Rotina diária:** às 10h de D-1, o robô baixa a carga verificada até aquele horário e a previsão de
   temperatura, gera a previsão hora a hora de D, grava em Parquet e publica num painel (Power BI ou
   Streamlit) ao lado da previsão oficial, com alerta nas horas em que as duas divergem muito. Quem usa:
   programação da operação, compra de energia e trading.
5. **Critério de sucesso:** a média modelo + previsão atual reduz o MAPE e as horas de erro grande no
   piloto, como reduziu no backtest (−12% e −42% no SIN).

### Limites de uso
* Não usar o modelo sozinho em feriados e pontes: ali o ONS é bem melhor (2,5% contra 3,9% no SIN).
* O modelo sozinho tem cauda pior que o ONS no percentil 99 (7.844 contra 6.629 MW no SIN), por causa dos
  feriados. A versão recomendada é a média com a previsão oficial, que fica melhor também na cauda
  (6.159 MW).
* O backtest usa a carga verificada já revisada; em produção, com dados preliminares, o ganho tende a ser
  menor (ver Limitações).
* Não é uma previsão de preço nem de despacho; é a entrada desses processos.

A metodologia completa, com fórmulas, desenho do backtest e premissas, está em
[`docs/metodologia.md`](docs/metodologia.md).

## Quanto vale cada informação

| SIN, MAPE | |
|---|---|
| Modelo só com carga até D-2, temperatura prevista e calendário | 1,97% |
| **+ carga da madrugada e da manhã de D-1 (00h-10h)** | **1,84%** |
| Com a temperatura observada no lugar da prevista (oráculo, não é previsão) | 1,67% |

A carga da manhã de D-1 vale 0,13 ponto percentual. Ela entra na versão principal porque o ONS também a tem
quando programa o dia seguinte, por volta do meio-dia. Sem ela, o modelo fica a 0,06 ponto do ONS no SIN.
A diferença para o oráculo (0,17 ponto) mostra quanto se ganharia com uma previsão de tempo perfeita.

## Como funciona

```
API de carga do ONS ─► carga verificada (semi-horária) ─┐
Open-Meteo, rodada da véspera ─► temperatura prevista ──┼─► features do dia D vistas na manhã de D-1 ─► LightGBM por subsistema
feriados nacionais, pontes, Carnaval ───────────────────┘                (retreino mensal)                     │
API de carga do ONS ─► carga programada ─────────────────────────────────────────────────────────────► comparação hora a hora
```

* **Alvo:** carga global verificada (`val_cargaglobal`), em média horária, dividida pela média dos 7 dias
  de D-8 a D-2. O modelo aprende a forma relativa e não o nível absoluto, o que ajuda com o crescimento da
  carga ao longo dos anos. A perda é L1, alinhada ao erro percentual.
* **Features:** mesma hora em D-2, D-3, D-7, D-14, D-21 e D-28; média das últimas 4 semanas; carga de 00h a
  10h de D-1; temperatura prevista hora a hora e máxima e média do dia, ponderadas pela população dos
  centros de carga de cada subsistema; feriado, ponte, véspera, pós-feriado e fim de ano, inclusive nos dias
  usados como lag.
* **Sem vazamento:** o modelo usado no mês M é treinado só com dias alvo até dois dias antes do início de
  M. Os testes em [`tests/test_features.py`](tests/test_features.py) alteram a carga de D-1 (depois das
  10h) e de D e verificam que nenhuma feature muda.

## Decisões de dados

Os detalhes estão em [`docs/dados.md`](docs/dados.md). Os principais:

* **Mesma definição de carga.** A carga programada corresponde à **carga global com MMGD**
  (`val_cargaglobal`), e não à parcela supervisionada nem à carga sem MMGD. Comparada com a carga sem MMGD,
  a programada erraria 13% em 2025; com a carga global, erra 3% na média semi-horária.
* **Fuso e intervalo.** A API marca o **fim** de cada meia hora em UTC. Converti para o início do intervalo
  em horário de Brasília (UTC-3, sem horário de verão desde 2019) e só usei horas com as duas metades
  presentes.
* **JSON inválido.** A API devolve campos vazios (`"val_cargammgd": ,`) em anos antigos. O parser trata
  isso explicitamente, com teste.
* **Temperatura prevista, não observada.** O INMET não estava acessível do ambiente de execução. Usei a
  [Previous Runs API do Open-Meteo](https://open-meteo.com/en/docs/previous-runs-api)
  (`temperature_2m_previous_day1`): o valor previsto para cada hora na rodada de um dia antes, com 24 a 48
  horas de antecedência.

## Reproduzir

```bash
pip install -e ".[dev]"
python scripts/download_ons.py        # carga programada e verificada, 2020 em diante (cache mensal)
python scripts/download_weather.py    # temperatura prevista na véspera, 2022 em diante
python scripts/build_dataset.py       # base horária e matriz de features
python scripts/backtest.py            # três variantes, retreino mensal (~20 min cada, 1 thread)
python scripts/avaliar.py             # métricas, Diebold-Mariano, tabelas em reports/
python scripts/make_figures.py
python scripts/aplicacao.py           # números de apoio da seção "Na prática"
pytest
```

## Estrutura

```
src/loadfc/
  ons.py          API de carga do ONS: download com cache, parser tolerante, semi-hora -> hora local
  weather.py      temperatura prevista na véspera (Open-Meteo) e média ponderada por subsistema
  calendario.py   feriados nacionais, Carnaval, pontes, vésperas, fim de ano
  features.py     matriz do dia D com o que se sabe na manhã de D-1
  model.py        LightGBM por subsistema, backtest com retreino mensal, baselines
  metricas.py     MAPE, MAE e Diebold-Mariano com variância HAC
scripts/          download_ons, download_weather, build_dataset, backtest, avaliar, make_figures, aplicacao
reports/          tabelas (CSV/JSON) e figuras
```

## Limitações

* **A carga programada não é uma previsão pura.** Ela é o insumo da programação diária e pode incorporar
  ajustes operativos. Mesmo assim, é a referência oficial de carga para o dia seguinte e o benchmark natural.
* **Dados revisados.** A carga verificada é revisada depois do fato (há registros de 2025 atualizados em
  2026). O modelo usa a série revisada como lag, enquanto o ONS programou com dados preliminares. Isso
  favorece o modelo, numa medida que não dá para quantificar com os dados públicos.
* **A MMGD é estimada.** A parcela de geração distribuída na carga verificada é uma estimativa do ONS. Parte
  do erro do ONS no meio do dia pode refletir mudanças nessa estimativa, e não erro de previsão.
* **A carga da manhã de D-1** entra como se já estivesse disponível às 10h. O ONS tem a carga supervisionada
  em tempo real, mas a carga global completa (com a não supervisionada e a MMGD) só é consolidada depois.
* **Sem irradiância nem nebulosidade.** O modelo não vê a previsão de sol, que move a MMGD. É o próximo
  passo natural, assim como previsões de umidade e vento.
* **Temperatura:** cerca de 5% das horas de 2024 não têm a previsão da véspera no Open-Meteo (o LightGBM
  trata como ausente). A ponderação por população é simples e fixa.
* **Feriados regionais** não entram, só os nacionais e o Carnaval.

---
Autor: **Caio Nepomuceno**. Dados públicos do ONS e previsões do Open-Meteo (CC BY 4.0). Projeto
independente, sem vínculo com o ONS.
