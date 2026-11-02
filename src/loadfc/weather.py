"""Temperatura prevista na véspera para os centros de carga (Open-Meteo, Previous Runs API).

``temperature_2m_previous_day1`` é o valor que o modelo meteorológico previa para aquela hora na rodada
de um dia antes, ou seja, uma previsão com 24 a 48 horas de antecedência: é a informação que existiria na
manhã de D-1, quando a programação do dia D é feita. ``temperature_2m`` (rodada mais recente, ~análise)
entra só na variante "oráculo", claramente separada.

Sem dados antes de 2022 nessa API; o portal do INMET não estava acessível no ambiente de execução.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import pandas as pd
import requests

from loadfc.config import CIDADES

log = logging.getLogger(__name__)
API = "https://previous-runs-api.open-meteo.com/v1/forecast"
VARS = ["temperature_2m", "temperature_2m_previous_day1"]


def _get(params: dict, retries: int = 5) -> list[dict]:
    for tentativa in range(retries):
        try:
            r = requests.get(API, params=params, timeout=300)
            if r.ok:
                payload = r.json()
                return payload if isinstance(payload, list) else [payload]
            motivo = r.text[:200]
        except (requests.RequestException, ValueError) as e:  # resposta cortada também cai aqui
            motivo = str(e)[:200]
        espera = 30 * (tentativa + 1)
        log.warning("open-meteo: %s; nova tentativa em %ds", motivo, espera)
        time.sleep(espera)
    raise RuntimeError(f"open-meteo falhou: {params['start_date']}..{params['end_date']}")


def baixar_ano(ano: int, dest: Path, fim: str | None = None) -> Path:
    """Uma requisição por subsistema (todas as cidades dele) e por ano; cache em parquet."""
    out = dest / f"temperatura_{ano}.parquet"
    if out.exists():
        return out
    dest.mkdir(parents=True, exist_ok=True)
    frames = []
    for sub, cidades in CIDADES.items():
        params = {
            "latitude": ",".join(str(c[1]) for c in cidades),
            "longitude": ",".join(str(c[2]) for c in cidades),
            "start_date": f"{ano}-01-01", "end_date": fim or f"{ano}-12-31",
            "hourly": ",".join(VARS), "timezone": "America/Sao_Paulo",
        }
        for (nome, _, _, peso), loc in zip(cidades, _get(params), strict=True):
            h = loc["hourly"]
            frames.append(pd.DataFrame({"ts": pd.to_datetime(h["time"]), "temp_obs": h["temperature_2m"],
                                        "temp_prev_d1": h["temperature_2m_previous_day1"]})
                          .assign(area=sub, cidade=nome, peso=peso))
        time.sleep(2)
    df = pd.concat(frames, ignore_index=True)
    df.to_parquet(out, index=False)
    return out


def temperatura_area(df: pd.DataFrame) -> pd.DataFrame:
    """Média ponderada (por população) das cidades de cada subsistema, por hora."""
    out = []
    for col in ["temp_prev_d1", "temp_obs"]:
        d = df.dropna(subset=[col]).assign(wx=lambda d, c=col: d[c] * d.peso)
        g = d.groupby(["area", "ts"])[["wx", "peso"]].sum()
        out.append((g.wx / g.peso).rename(col))
    return pd.concat(out, axis=1).reset_index()
