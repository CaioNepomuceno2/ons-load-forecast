"""Métricas de erro e teste de Diebold-Mariano."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def mape(y, p) -> float:
    y, p = np.asarray(y, float), np.asarray(p, float)
    ok = np.isfinite(y) & np.isfinite(p) & (y != 0)
    return float(np.mean(np.abs(p[ok] - y[ok]) / np.abs(y[ok])) * 100)


def mae(y, p) -> float:
    y, p = np.asarray(y, float), np.asarray(p, float)
    ok = np.isfinite(y) & np.isfinite(p)
    return float(np.mean(np.abs(p[ok] - y[ok])))


def diebold_mariano(e1, e2, h: int = 1, potencia: int = 1) -> tuple[float, float]:
    """DM com variância HAC (Newey-West, ``h-1`` defasagens) e correção de Harvey et al. (1997).

    ``e1``/``e2``: séries de erros dos dois métodos. Estatística negativa = método 1 melhor.
    Devolve (estatística, p-valor bicaudal).
    """
    d = np.abs(np.asarray(e1, float)) ** potencia - np.abs(np.asarray(e2, float)) ** potencia
    d = d[np.isfinite(d)]
    n = len(d)
    dbar = d.mean()
    gamma = [np.mean((d[k:] - dbar) * (d[: n - k] - dbar)) for k in range(h)]
    var = (gamma[0] + 2 * sum(gamma[1:])) / n
    dm = dbar / np.sqrt(var)
    corr = np.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    stat = dm * corr
    p = 2 * stats.t.sf(abs(stat), df=n - 1)
    return float(stat), float(p)


def tabela(df: pd.DataFrame, metodos: dict[str, str], por: list[str] | None = None) -> pd.DataFrame:
    """MAPE e MAE de cada método, opcionalmente por grupo."""
    def calc(g: pd.DataFrame) -> pd.Series:
        out = {}
        for nome, col in metodos.items():
            out[f"mape_{nome}"] = mape(g.y, g[col])
            out[f"mae_{nome}"] = mae(g.y, g[col])
        out["n_horas"] = len(g)
        return pd.Series(out)
    if not por:
        return calc(df).to_frame().T
    return df.groupby(por, observed=True).apply(calc, include_groups=False).reset_index()
