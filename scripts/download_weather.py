"""Baixa do Open-Meteo, para os centros de carga, 2022 em diante:

* a temperatura prevista na véspera (``data/raw/openmeteo``);
* a irradiância (onda curta) e a cobertura de nuvens previstas na véspera, com 24 e 48 h de antecedência,
  mais a rodada mais recente de cada uma (``data/raw/openmeteo_solar``, um arquivo por ano e subsistema).

Tudo fica em cache: uma queda no meio retoma de onde parou. Os limites de taxa do Open-Meteo são respeitados
(``weather.espera_s``). Use ``--so-temperatura`` ou ``--so-solar`` para baixar só uma das partes.
"""
import logging
import sys
from datetime import date, timedelta

from loadfc import weather
from loadfc.config import RAW

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
ontem = date.today() - timedelta(days=1)
fazer_temperatura = "--so-solar" not in sys.argv
fazer_solar = "--so-temperatura" not in sys.argv
for ano in range(2022, ontem.year + 1):
    fim = ontem.isoformat() if ano == ontem.year else None
    if fazer_temperatura:
        logging.info("%s", weather.baixar_ano(ano, RAW / "openmeteo", fim=fim))
    if fazer_solar:
        for p in weather.baixar_solar_ano(ano, RAW / "openmeteo_solar", fim=fim):
            logging.info("%s", p)
