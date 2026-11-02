"""LightGBM por subsistema, com retreino mensal (origem móvel).

O alvo é ``y / base`` (carga relativa à média dos 7 dias até D-2), com perda L1: o erro em razão é
aproximadamente o erro percentual, que é a métrica do benchmark (MAPE).
"""
from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd

from loadfc.features import LAG_MIN_DIAS, design

PARAMS = {
    "objective": "l1", "learning_rate": 0.03, "num_leaves": 63, "min_child_samples": 30,
    "subsample": 0.8, "subsample_freq": 1, "colsample_bytree": 0.8, "reg_lambda": 1.0,
    "n_estimators": 900, "n_jobs": 1, "verbose": -1, "random_state": 0,
}


def treinar(X: pd.DataFrame) -> lgb.LGBMRegressor:
    ok = X.y_rel.notna() & X.base.notna()
    m = lgb.LGBMRegressor(**PARAMS)
    m.fit(design(X[ok]), X.loc[ok, "y_rel"])
    return m


def corte_treino(inicio_teste: pd.Timestamp) -> pd.Timestamp:
    """Último dia alvo que pode estar no treino de um modelo usado a partir de ``inicio_teste``.

    O modelo do mês M é treinado na véspera do primeiro dia de M; o alvo mais recente com carga
    verificada completa é ``inicio - LAG_MIN_DIAS``.
    """
    return inicio_teste - pd.Timedelta(days=LAG_MIN_DIAS)


def backtest(X: pd.DataFrame, inicio: str, fim: str, inicio_treino: str | None = None) -> pd.DataFrame:
    """Previsões fora da amostra mês a mês, por área. Devolve area, ts, y, pred_modelo."""
    saidas = []
    meses = pd.date_range(inicio, fim, freq="MS")
    for _area, g in X.groupby("area"):
        if inicio_treino:
            g = g[g.dia >= inicio_treino]
        for ini in meses:
            fim_mes = ini + pd.offsets.MonthEnd(0)
            tr = g[g.dia <= corte_treino(ini)]
            te = g[(g.dia >= ini) & (g.dia <= fim_mes) & g.y.notna() & g.base.notna()].copy()
            if te.empty:
                continue
            m = treinar(tr)
            te["pred_modelo"] = m.predict(design(te)) * te.base
            saidas.append(te[["area", "ts", "dia", "hora", "y", "pred_modelo"]])
    return pd.concat(saidas, ignore_index=True)


def baselines(X: pd.DataFrame) -> pd.DataFrame:
    """Baselines ingênuos: mesma hora uma semana antes e média das últimas 4 semanas."""
    return X[["area", "ts"]].assign(pred_semana_anterior=X.lag7, pred_media_4sem=X.perfil_4sem)


def importancia(m: lgb.LGBMRegressor, cols: list[str]) -> pd.Series:
    return pd.Series(m.booster_.feature_importance("gain"), index=cols).sort_values(ascending=False) / \
        np.sum(m.booster_.feature_importance("gain"))
