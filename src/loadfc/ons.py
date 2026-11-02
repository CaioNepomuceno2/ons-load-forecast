"""Carga programada e verificada do ONS (API de carga, semi-horária, por área de carga).

* ``cargaprogramada``: carga global programada na programação diária (DESSEM), feita na véspera.
* ``cargaverificada``: carga global verificada e suas parcelas (supervisionada, não supervisionada, MMGD).

Os dois usam ``din_referenciautc`` = fim do intervalo de 30 minutos, em UTC. O dia operativo
``dat_referencia`` vai de 00:30 a 24:00 no horário de Brasília (03:30 UTC a 03:00 UTC do dia seguinte).
"""
from __future__ import annotations

import calendar
import json
import logging
import re
import time
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger(__name__)
API = "https://apicarga.ons.org.br/prd/{endpoint}"
ENDPOINTS = {"programada": "cargaprogramada", "verificada": "cargaverificada"}
_VAZIO = re.compile(r":\s*(?=[,}\]])")  # "campo": ,  -> "campo": null,


def parse_json(texto: str) -> list[dict]:
    """A API às vezes devolve campos sem valor (``"x": ,``), o que não é JSON válido."""
    return json.loads(_VAZIO.sub(": null", texto))


def baixar_mes(tipo: str, area: str, ano: int, mes: int, dest: Path, pausa: float = 0.5,
               retries: int = 4) -> Path:
    """Baixa um mês de uma área e guarda o JSON bruto em cache (não baixa de novo)."""
    out = dest / tipo / area / f"{ano}-{mes:02d}.json"
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    fim = calendar.monthrange(ano, mes)[1]
    params = {"dat_inicio": f"{ano}-{mes:02d}-01", "dat_fim": f"{ano}-{mes:02d}-{fim}", "cod_areacarga": area}
    for tentativa in range(retries):
        try:
            r = requests.get(API.format(endpoint=ENDPOINTS[tipo]), params=params, timeout=120)
            r.raise_for_status()
            parse_json(r.text)  # valida antes de gravar
            out.write_text(r.text, encoding="utf-8")
            time.sleep(pausa)
            return out
        except (requests.RequestException, json.JSONDecodeError) as e:
            espera = 2 ** (tentativa + 1)
            log.warning("%s %s %d-%02d: %s; nova tentativa em %ds", tipo, area, ano, mes, e, espera)
            time.sleep(espera)
    raise RuntimeError(f"falha ao baixar {tipo} {area} {ano}-{mes:02d}")


def ler(tipo: str, dest: Path) -> pd.DataFrame:
    """Junta os JSON em cache em um DataFrame semi-horário (UTC, fim do intervalo)."""
    linhas = []
    for p in sorted((dest / tipo).glob("*/*.json")):
        linhas.extend(parse_json(p.read_text(encoding="utf-8")))
    df = pd.DataFrame(linhas)
    if df.empty:
        return df
    df["ts_fim_utc"] = pd.to_datetime(df.din_referenciautc, utc=True)
    df = df.rename(columns={"cod_areacarga": "area"})
    return df.drop(columns=["din_referenciautc"]).drop_duplicates(["area", "ts_fim_utc"], keep="last")


def para_horario(df: pd.DataFrame, col: str, tz: str = "America/Sao_Paulo") -> pd.DataFrame:
    """Média horária (MWmed) em horário local. Hora ``h`` = intervalo [h, h+1).

    Cada valor semi-horário é rotulado pelo fim do intervalo; o início é ``fim - 30 min``.
    Só ficam horas com as duas metades presentes.
    """
    ini = (df.ts_fim_utc - pd.Timedelta(minutes=30)).dt.tz_convert(tz)
    h = df.assign(ts=ini.dt.floor("h").dt.tz_localize(None))
    g = h.groupby(["area", "ts"])[col].agg(["mean", "count"]).reset_index()
    return g[g["count"] == 2].drop(columns="count").rename(columns={"mean": col})
