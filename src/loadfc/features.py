"""Matriz de features do dia seguinte, respeitando o que se sabe na véspera.

A programação do dia D é feita na manhã de D-1. Nesse momento:

* a carga verificada conhecida vai até o fim de **D-2** (o dia D-1 ainda está acontecendo);
* a temperatura de D é uma **previsão** (rodada de um dia antes, ``temp_prev_d1``);
* o calendário de D é conhecido.

``LAG_MIN_DIAS = 2`` garante isso: nenhuma carga de D-1 ou D entra nas features. A variante
``hora_corte_d1`` (ex.: 10) acrescenta a carga da madrugada e da manhã de D-1, de 00h até a hora de
corte, que o ONS já tem em tempo real quando roda a programação (por volta do meio-dia de D-1).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from loadfc.calendario import features_calendario

LAG_MIN_DIAS = 2
LAGS_DIAS = [2, 3, 7, 14, 21, 28]


def _pivot_dia_hora(carga: pd.DataFrame) -> pd.DataFrame:
    """carga horária (area, ts, y) -> índice (area, dia), colunas = hora 0..23."""
    c = carga.assign(dia=carga.ts.dt.normalize(), hora=carga.ts.dt.hour)
    return c.pivot_table(index=["area", "dia"], columns="hora", values="y")


def montar(carga: pd.DataFrame, temp: pd.DataFrame | None, temp_col: str = "temp_prev_d1",
           hora_corte_d1: int | None = None) -> pd.DataFrame:
    """Uma linha por área x dia alvo x hora, com alvo ``y`` e features disponíveis na véspera.

    ``carga``: colunas area, ts (hora local, início do intervalo), y (MWmed).
    ``temp``: colunas area, ts, temp_prev_d1 / temp_obs (horário local).
    """
    dh = _pivot_dia_hora(carga)
    diario = dh.mean(axis=1).rename("media_dia")
    linhas = []
    for area, g in dh.groupby(level="area"):
        g = g.droplevel("area").asfreq("D")
        md = diario.loc[area].asfreq("D")
        base = pd.concat([md.shift(k) for k in range(LAG_MIN_DIAS, LAG_MIN_DIAS + 7)], axis=1).mean(axis=1)
        if hora_corte_d1:
            manha = g[list(range(hora_corte_d1))].mean(axis=1)  # média de 00h até o corte, por dia
            d1_manha = manha.shift(1)                            # manhã de D-1
            d1_manha_rel = d1_manha / manha.shift(8)             # contra a manhã de uma semana antes
        for h in range(24):
            df = pd.DataFrame({"dia": g.index, "hora": h, "y": g[h].values}, index=g.index)
            for k in LAGS_DIAS:
                df[f"lag{k}"] = g[h].shift(k).values
            df["lag2_dia_media"] = md.shift(2).values
            df["base"] = base.values  # média dos 7 dias de D-8 a D-2
            df["perfil_4sem"] = df[["lag7", "lag14", "lag21", "lag28"]].mean(axis=1)
            if hora_corte_d1:
                df["d1_manha_media"] = d1_manha.values
                df["d1_manha_rel_semana"] = d1_manha_rel.values
            df["area"] = area
            linhas.append(df.reset_index(drop=True))
    X = pd.concat(linhas, ignore_index=True)
    X["ts"] = X.dia + pd.to_timedelta(X.hora, unit="h")
    X = X.merge(features_calendario(pd.Series(X.dia.unique())), on="dia", how="left")
    # calendário do dia de cada lag: um feriado na semana passada distorce o lag de 7 dias
    cal = features_calendario(pd.Series(X.dia.unique()))[["dia", "feriado"]]
    for k in (7, 14):
        X = X.merge(cal.rename(columns={"dia": "dia_lag", "feriado": f"feriado_lag{k}"})
                    .assign(dia=lambda d, k=k: d.dia_lag + pd.Timedelta(days=k)).drop(columns="dia_lag"),
                    on="dia", how="left")
    if temp is not None:
        t = temp[["area", "ts", temp_col]].rename(columns={temp_col: "temp"})
        X = X.merge(t, on=["area", "ts"], how="left")
        td = X.groupby(["area", "dia"]).temp.agg(temp_max_dia="max", temp_media_dia="mean").reset_index()
        X = X.merge(td, on=["area", "dia"], how="left")
        # temperatura observada em D-2 (já conhecida), para o modelo ver a variação prevista
        t2 = temp[["area", "ts", "temp_obs"]].assign(ts=lambda d: d.ts + pd.Timedelta(days=LAG_MIN_DIAS))
        X = X.merge(t2.rename(columns={"temp_obs": "temp_lag2"}), on=["area", "ts"], how="left")
        X["temp_delta"] = X.temp - X.temp_lag2
    X["y_rel"] = X.y / X.base
    return X.sort_values(["area", "ts"]).reset_index(drop=True)


FEATURES_EXCLUIR = {"dia", "ts", "y", "y_rel", "area"}


def colunas_modelo(X: pd.DataFrame) -> list[str]:
    cols = [c for c in X.columns if c not in FEATURES_EXCLUIR]
    rel = [c for c in cols if c.startswith("lag") or c in {"perfil_4sem", "d1_manha_media"}]
    return cols + [f"{c}_rel" for c in rel]


def design(X: pd.DataFrame) -> pd.DataFrame:
    """Lags também como razão sobre ``base``: o modelo aprende formas, não níveis absolutos."""
    D = X.copy()
    for c in [c for c in X.columns if c.startswith("lag") or c in {"perfil_4sem", "d1_manha_media"}]:
        D[f"{c}_rel"] = D[c] / D["base"]
    return D[colunas_modelo(X)].astype("float64").replace([np.inf, -np.inf], np.nan)
