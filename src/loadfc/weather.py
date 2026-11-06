"""Temperatura, irradiância e nuvens previstas na véspera para os centros de carga (Open-Meteo).

``temperature_2m_previous_day1`` é o valor que o modelo meteorológico previa para aquela hora na rodada
de um dia antes, ou seja, uma previsão com 24 a 48 horas de antecedência: é a informação que existiria na
manhã de D-1, quando a programação do dia D é feita. ``temperature_2m`` (rodada mais recente, ~análise)
entra só na variante "oráculo", claramente separada.

A irradiância (``shortwave_radiation``) e a cobertura de nuvens (``cloud_cover``) seguem a mesma lógica:
``*_previous_day1`` é o valor previsto para a hora com pelo menos 24 h de antecedência (o Open-Meteo
descarta as primeiras 24 h de cada rodada), logo vindo de uma rodada emitida em D-1 ou antes;
``*_previous_day2`` usa 48 h e é a versão estrita. Os valores sem sufixo (rodada mais recente) servem ao
oráculo e à irradiância observada em D-2.

Sem dados de temperatura antes de 2022 nessa API; a irradiância e as nuvens previstas só existem a partir de
19/01/2024. O portal do INMET não estava acessível no ambiente de execução.
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

# Irradiância e nuvens: variável da API -> nome da coluna.
# ``prev_d1``/``prev_d2``: previsão com 24/48 h de antecedência. ``obs``: rodada mais recente (~análise).
VARS_SOLAR = {
    "shortwave_radiation_previous_day1": "ghi_prev_d1",
    "cloud_cover_previous_day1": "nuv_prev_d1",
    "shortwave_radiation_previous_day2": "ghi_prev_d2",
    "cloud_cover_previous_day2": "nuv_prev_d2",
    "shortwave_radiation": "ghi_obs",
    "cloud_cover": "nuv_obs",
}
FONTES_SOLAR = ("prev_d1", "prev_d2", "obs")


def espera_s(motivo: str, tentativa: int) -> int:
    """Segundos de espera antes de tentar de novo. Respeita os limites de taxa do Open-Meteo.

    Limite por minuto: espera pouco mais de um minuto. Por hora: espera pouco mais de uma hora, no máximo
    duas vezes. Diário: levanta, porque não adianta insistir hoje.
    """
    m = motivo.lower()
    if "daily" in m:
        raise RuntimeError(f"limite diário do open-meteo atingido: {motivo}")
    if "hourly" in m:
        if tentativa >= 2:
            raise RuntimeError(f"limite por hora do open-meteo persiste: {motivo}")
        return 3660
    if "minutely" in m:
        return 65
    return 30 * (tentativa + 1)


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
        espera = espera_s(motivo, tentativa)
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


# --------------------------------------------------------------------------- irradiância e nuvens

def quadro_solar(payload: list[dict], sub: str) -> pd.DataFrame:
    """Resposta da API (uma entrada por cidade, na ordem de ``CIDADES[sub]``) -> quadro por cidade e hora.

    Só as colunas de ``VARS_SOLAR`` são lidas: previsões ``previous_day1``/``previous_day2`` e os valores
    sem sufixo (oráculo). Nunca ``previous_day0`` nem outra variável.
    """
    cidades = CIDADES[sub]
    frames = []
    for (nome, _, _, peso), loc in zip(cidades, payload, strict=True):
        h = loc["hourly"]
        cols = {novo: h[api] for api, novo in VARS_SOLAR.items()}
        frames.append(pd.DataFrame({"ts": pd.to_datetime(h["time"]), **cols})
                      .assign(area=sub, cidade=nome, peso=peso))
    return pd.concat(frames, ignore_index=True)


def baixar_solar_ano(ano: int, dest: Path, fim: str | None = None, pausa: float = 3.0) -> list[Path]:
    """Irradiância e nuvens do ano, um arquivo por subsistema (``sol_<ano>_<sub>.parquet``).

    O cache é por subsistema e ano: se o processo cair no meio, o que já foi baixado é reaproveitado.
    """
    dest.mkdir(parents=True, exist_ok=True)
    saidas = []
    for sub, cidades in CIDADES.items():
        out = dest / f"sol_{ano}_{sub}.parquet"
        saidas.append(out)
        if out.exists():
            continue
        params = {
            "latitude": ",".join(str(c[1]) for c in cidades),
            "longitude": ",".join(str(c[2]) for c in cidades),
            "start_date": f"{ano}-01-01", "end_date": fim or f"{ano}-12-31",
            "hourly": ",".join(VARS_SOLAR), "timezone": "America/Sao_Paulo",
        }
        df = quadro_solar(_get(params), sub)
        df.to_parquet(out.with_suffix(".tmp"), index=False)
        out.with_suffix(".tmp").replace(out)  # só aparece com o nome final se foi gravado inteiro
        time.sleep(pausa)
    return saidas


def solar_area(df: pd.DataFrame) -> pd.DataFrame:
    """Média ponderada (por população) das cidades de cada subsistema, por hora de carga.

    A radiação de onda curta do Open-Meteo é a média da hora **anterior** ao carimbo, então a hora de
    carga ``h`` (intervalo [h, h+1)) usa o carimbo ``h+1``. O carimbo 00:00 de um dia é descartado: ele
    viraria a hora 23 do dia anterior, mas a previsão ``previous_day1`` desse carimbo vem de uma rodada
    emitida 24 h antes, ou seja, no próprio dia D e não na véspera. A hora 23 fica sem valor (é noite).
    Nuvens são instantâneas e ficam no carimbo.
    """
    cols = list(VARS_SOLAR.values())
    out = []
    for col in cols:
        d = df.dropna(subset=[col])
        if col.startswith("ghi_"):
            d = d[d.ts.dt.hour != 0].assign(ts=lambda x: x.ts - pd.Timedelta(hours=1))
        d = d.assign(wx=d[col] * d.peso)
        g = d.groupby(["area", "ts"])[["wx", "peso"]].sum()
        out.append((g.wx / g.peso).rename(col))
    return pd.concat(out, axis=1).reset_index()
