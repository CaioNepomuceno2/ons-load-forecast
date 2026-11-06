# Pré-registro: irradiância e nebulosidade

Este arquivo foi escrito e commitado **antes** de rodar qualquer backtest com a irradiância. Ele fixa a
pergunta, as variantes, as janelas de avaliação e a regra para decidir se a variante nova vira o padrão.
Resultados e desvios em relação a este plano ficam no README.

## Pergunta

A previsão de radiação de onda curta e de cobertura de nuvens, emitida na véspera, reduz o erro do modelo no
meio do dia, onde a MMGD pesa? E reduz o erro a ponto de superar a carga programada do ONS nessas horas?

## Restrição dos dados (verificada em 06/11/2026)

A Previous Runs API do Open-Meteo só guarda `shortwave_radiation_previous_day1` e
`cloud_cover_previous_day1` **a partir de 19/01/2024 às 09h**, em qualquer modelo testado. A temperatura
prevista começa em 2022. Logo, o treino de 2022 e 2023 não tem a irradiância prevista (fica ausente), e o
modelo de cada mês de 2024 aprende com pouca ou nenhuma amostra dela. O ganho, se existir, deve crescer
com o tempo. Por isso há duas janelas.

## Variantes

Todas retreinam todo mês, com os mesmos parâmetros do LightGBM e a mesma semente. Só mudam as colunas.

| Variante | Base | Colunas acrescentadas |
|---|---|---|
| `modelo_irr` | `modelo` | irradiância e nuvens previstas na véspera (`*_previous_day1`) |
| `modelo_d2_irr` | `modelo_d2` | idem |
| `oraculo_irr` | `oraculo` | irradiância e nuvens observadas (rodada mais recente) no dia D; limite superior |
| `modelo_irr_estrito` | `modelo` | irradiância e nuvens `*_previous_day2` (48 h antes), disponíveis com folga na manhã de D-1 |
| `modelo_irr_embaralhado` | `modelo` | as mesmas colunas de `modelo_irr`, mas com a irradiância de outro dia (deslocada 37 dias); controle do efeito de simplesmente ter mais colunas |

Colunas acrescentadas, por hora (como a temperatura): `ghi`, `nuv`, `ghi_lag2` (irradiância observada em D-2),
`ghi_delta` (`ghi - ghi_lag2`); por dia: `ghi_media_dia`, `nuv_media_dia`. Não serão acrescentadas outras
colunas depois de ver os resultados.

## Janelas de avaliação

* **Principal (manchete): jan/2024 a out/2026**, a mesma do README.
* **Secundária: fev/2025 a out/2026.** Em todo mês dessa janela o treino já tem pelo menos 12 meses de
  irradiância prevista. Será reportada de qualquer forma, ao lado da principal, e não substitui a principal.
* Horas de 9h às 16h do SIN, nas duas janelas.

## Regra para a variante virar o padrão

`modelo_irr` substitui `modelo` como padrão do README **somente se**, na janela principal:

1. o MAPE do SIN de `modelo_irr` for menor que o de `modelo`;
2. o teste de Diebold-Mariano (erro diário, h = 7) de `modelo_irr` contra `modelo` no SIN der p < 0,05, a favor
   de `modelo_irr`;
3. nenhum subsistema piorar com p < 0,05.

Se alguma condição falhar, o padrão continua o mesmo e a variante fica documentada como opção, com o
resultado publicado.

**Leitura do ganho.** Um ganho só é atribuído à irradiância se o MAPE do SIN de `modelo_irr` melhorar, em
relação a `modelo`, mais que o dobro do valor absoluto da variação de `modelo_irr_embaralhado`.

## Reprodução da linha de base

Os dados do ONS são revisados depois do fato, e o Open-Meteo pode trocar o modelo por trás da previsão. Antes de
mudar código, o pipeline completo roda com o código inalterado. A linha de base conta como reproduzida se:

* o MAPE do SIN de `modelo`, ONS e média modelo + ONS ficar a no máximo 0,05 ponto percentual do commitado;
* o MAPE de cada subsistema ficar a no máximo 0,10 ponto percentual do commitado;
* nenhuma conclusão de significância (p < 0,05) do Diebold-Mariano mudar de lado;
* o número de horas avaliadas variar menos de 1%.

Se isso falhar, o trabalho para e o relatório diz por quê. A diferença entre os CSV commitados e os
regenerados é tratada como efeito de **revisão dos dados** (ONS e Open-Meteo, sem como separar os dois),
separada do efeito da irradiância.

## Alinhamento e ausência de vazamento

* `shortwave_radiation` é a média da hora **anterior** ao carimbo. A hora de carga `h` ([h, h+1)) usa o
  carimbo `h+1`. Esse deslocamento nunca atravessa a meia-noite: a hora 23 fica sem valor (é noite).
* `*_previous_day1` é o valor previsto para o carimbo `T` por uma rodada com pelo menos 24 h de antecedência
  (o Open-Meteo descarta as primeiras 24 h de cada rodada). Todo valor usado em D vem de rodada emitida em D-1
  ou antes, nunca de D.
* Ressalva: para as horas da tarde de D, essa rodada de D-1 pode ter sido publicada **depois** do meio-dia de
  D-1, quando o ONS programa. A temperatura já tem essa propriedade. A variante `modelo_irr_estrito`
  (`*_previous_day2`) mede quanto do ganho sobra quando a previsão é seguramente anterior à programação.
* `val_cargaglobal` inclui a estimativa de MMGD do ONS, que o próprio ONS calcula a partir de irradiância. Parte
  do ganho pode ser o modelo prevendo essa estimativa, e não o consumo.
