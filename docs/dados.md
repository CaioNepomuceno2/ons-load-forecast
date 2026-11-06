# Decisões de dados

O raciocínio, as fórmulas e o desenho da validação estão em [`metodologia.md`](metodologia.md).

## Carga programada e verificada (ONS)

**Fonte:** API de carga do ONS (`https://apicarga.ons.org.br/prd/`), documentada no portal de dados
abertos (datasets `carga-energia-programada` e `carga-energia-verificada`).

* **Endpoints:** `cargaprogramada` e `cargaverificada`, com os parâmetros `dat_inicio`, `dat_fim` e
  `cod_areacarga`. As áreas `SECO`, `S`, `NE` e `N` coincidem com os subsistemas. Há `SIN` na verificada,
  mas não na programada; por isso o SIN do projeto é a soma dos quatro subsistemas, só nas horas em que os
  quatro estão completos.
* **Períodos:** a verificada começa em 2020. A programada começa em 01/12/2020 no SE/CO e em 01-02/03/2021
  nas demais áreas. A cobertura da programada é de 99,75% a 100% das horas por ano.
* **Dez/2020 no SE/CO:** a programada é idêntica à verificada, o que parece um preenchimento. Fica fora do
  teste.
* **Download:** um mês por requisição, com cache em `data/raw/ons/<tipo>/<area>/<ano-mes>.json`. Pedidos de
  um ano inteiro voltaram incompletos em testes (13.296 de 17.520 semi-horas do SE/CO em 2025), então o
  download é sempre mensal.
* **JSON inválido:** em anos antigos, a verificada traz campos sem valor (`"val_cargammgd": ,`). O parser
  troca esses casos por `null` antes de decodificar (`ons.parse_json`).
* **Fuso:** `din_referenciautc` é o **fim** da meia hora, em UTC. O dia operativo `dat_referencia` vai de
  03:30 UTC (00:30 local) a 03:00 UTC do dia seguinte (24:00 local). Para cada valor, calculo o início do
  intervalo, converto para `America/Sao_Paulo` (UTC-3 fixo desde o fim do horário de verão em 2019) e tiro a
  média por hora. Uma hora só entra com as duas metades presentes.

### Qual carga verificada corresponde à programada?

A verificada tem várias parcelas: `val_cargaglobal`, `val_cargaglobalcons`, `val_cargaglobalsmmgd`
(sem MMGD), `val_cargasupervisionada`, `val_carganaosupervisionada` e `val_cargammgd`. O erro percentual
médio da programada contra cada uma, nas semi-horas comuns, foi:

| Ano | Global | Global consistida | Global sem MMGD | Supervisionada |
|---|---|---|---|---|
| 2022 | 4,4% | 4,4% | 2,5% | 9,1% |
| 2023 | 3,6% | 3,5% | 6,2% | 12,9% |
| 2024 | 2,6% | 2,6% | 9,8% | 16,5% |
| 2025 | 3,0% | 3,0% | 13,0% | 19,7% |

A partir de 2023, a programada só é consistente com a **carga global com MMGD**. Ao meio-dia de 2025 no
Nordeste, por exemplo, a programada média é de 12.990 MW, a global é de 13.386 MW e a global sem MMGD é de
8.579 MW. Em 2022, a carga sem MMGD fica mais próxima, o que sugere que a definição usada na programação
mudou nesse período. O teste começa em 2024, depois dessa transição (e com dois anos de previsão de
temperatura para treinar), e a definição usada é `val_cargaglobal`.

### MMGD

A parcela de MMGD (`val_cargammgd`) ao meio-dia cresceu muito:

| Ano | N | NE | S | SE/CO |
|---|---|---|---|---|
| 2022 | 8% | 11% | 14% | 9% |
| 2024 | 20% | 26% | 27% | 20% |
| 2026 | 30% | 43% | 35% | 31% |

Essa parcela é uma estimativa do ONS, não uma medição.

## Temperatura (Open-Meteo)

* **Por que não o INMET:** o portal do INMET recusou conexões do ambiente de execução.
* **Previsão da véspera:** a [Previous Runs API](https://open-meteo.com/en/docs/previous-runs-api) devolve,
  para cada hora, o valor previsto um dia antes (`temperature_2m_previous_day1`: "o valor previsto 24 horas
  antes do instante de validade", segundo a documentação). Não é uma rodada única: o Open-Meteo descarta as
  primeiras 24 horas de cada rodada e junta o resto
  ([blog](https://openmeteo.substack.com/p/weather-forecasts-from-previous-model-runs)). Para uma hora de D,
  a rodada foi emitida em D-1 ou antes, nunca em D. É o que o modelo usa para o dia D. A série `temperature_2m` (rodada mais
  recente, próxima do observado) só entra na variante "oráculo" e na temperatura de D-2, que já é passado.
* **Disponibilidade:** a API tem dados a partir de 2022. Cerca de 5% das horas de 2024 não têm a previsão
  da véspera.
* **Agregação:** a temperatura de cada subsistema é a média ponderada de 3 a 6 centros de carga, com peso
  pela população da região metropolitana (`src/loadfc/config.py`). Campo Grande entra no SE/CO.
* **Limites de uso:** a API gratuita tem limite diário; o download faz uma requisição por subsistema e ano,
  com cache e novas tentativas espaçadas.

## Irradiância e nuvens (Open-Meteo)

Mesma API, mesmos centros de carga e mesmos pesos de população da temperatura. Os pesos são de população, não
de onde há MMGD instalada; isso é uma limitação (ver README).

* **Variáveis:** `shortwave_radiation` (radiação de onda curta, W/m²) e `cloud_cover` (cobertura total de
  nuvens, %). `scripts/download_weather.py` baixa, de cada uma, `*_previous_day1` (previsão com cerca de 24 h
  de antecedência, a usada no modelo), `*_previous_day2` (cerca de 48 h, usada na versão estrita) e a rodada
  mais recente, sem sufixo (usada só no oráculo e na irradiância observada de D-2, que já é passado).
  Nunca se usa `previous_day0`.
* **Disponibilidade:** a Previous Runs API só guarda a irradiância e as nuvens previstas **a partir de
  19/01/2024, 09h** (verificado em 06/11/2026 no modelo padrão, no GFS e no ICON; o ECMWF começa em março de
  2024). A temperatura prevista começa em 2022. Em 2024 faltam cerca de 5% das horas. O treino de 2022 e 2023
  não tem a irradiância prevista (o LightGBM trata como ausente). A rodada recente, sem sufixo, existe desde
  2022.
* **Alinhamento horário:** a radiação do Open-Meteo é a média da hora **anterior** ao carimbo, então a hora de
  carga `h`, que vai de `h` a `h+1`, usa o carimbo `h+1`. O deslocamento nunca atravessa a meia-noite: o
  carimbo 00:00 de D+1 viria de uma rodada emitida em D (24 h antes), então a hora 23 fica sem valor (é noite).
  Nuvens são instantâneas e ficam no carimbo. Os testes em `tests/test_irradiancia.py` conferem isso.
* **Ressalva sobre a hora da emissão:** `previous_day1` garante só que a rodada foi emitida em D-1 ou antes.
  Para as horas da tarde de D, essa rodada foi emitida e publicada na tarde ou na noite de D-1, depois do
  meio-dia, quando o ONS programa. A temperatura prevista tem a mesma propriedade. A versão estrita
  (`previous_day2`, rodada de cerca de 48 h antes) é seguramente anterior à programação; o README mostra
  quanto do ganho sobra com ela.
* **Colunas no modelo:** por hora, `ghi` e `nuv` (previstas), `ghi_lag2` (irradiância observada em D-2 na mesma
  hora) e `ghi_delta` (`ghi - ghi_lag2`), como a temperatura; por dia, `ghi_media_dia` e `nuv_media_dia`.

## Calendário

Feriados nacionais da biblioteca `holidays` (categorias pública e opcional), o que inclui a segunda e a
terça de Carnaval e o Corpus Christi, que derrubam a carga como feriados. A Quarta-feira de Cinzas fica de
fora (é captada como pós-feriado). Ponte = segunda antes de feriado na terça, ou sexta depois de feriado na
quinta. Feriados estaduais e municipais não entram.
