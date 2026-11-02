"""Baixa a carga programada e a verificada do ONS, mês a mês, com cache em data/raw/ons."""
import logging
import sys
from datetime import date

from loadfc import ons
from loadfc.config import RAW, SUBSISTEMAS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
INICIO = (2020, 1)
hoje = date.today()
fim = (hoje.year, hoje.month - 1) if hoje.month > 1 else (hoje.year - 1, 12)  # só meses fechados
meses = [(a, m) for a in range(INICIO[0], fim[0] + 1) for m in range(1, 13)
         if INICIO <= (a, m) <= fim]
areas = sys.argv[1:] or list(SUBSISTEMAS)
for area in areas:
    for a, m in meses:
        ons.baixar_mes("programada", area, a, m, RAW / "ons")
        ons.baixar_mes("verificada", area, a, m, RAW / "ons")
    logging.info("%s: %d meses", area, len(meses))
