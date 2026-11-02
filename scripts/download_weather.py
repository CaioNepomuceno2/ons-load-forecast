"""Baixa a temperatura prevista na véspera (Open-Meteo) para os centros de carga, 2022 em diante."""
import logging
from datetime import date, timedelta

from loadfc import weather
from loadfc.config import RAW

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
ontem = date.today() - timedelta(days=1)
for ano in range(2022, ontem.year + 1):
    fim = ontem.isoformat() if ano == ontem.year else None
    p = weather.baixar_ano(ano, RAW / "openmeteo", fim=fim)
    logging.info("%s", p)
