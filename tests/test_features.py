import numpy as np
import pandas as pd
import pytest

from loadfc import features, model
from loadfc.calendario import features_calendario


def _carga(dias=60, area="S"):
    ts = pd.date_range("2024-01-01", periods=24 * dias, freq="h")
    y = 1000 + 100 * np.sin(np.arange(len(ts)) / 24 * 2 * np.pi) + np.arange(len(ts)) * 0.1
    return pd.DataFrame({"area": area, "ts": ts, "y": y})


def test_nenhuma_feature_usa_carga_de_d_menos_1_ou_d():
    c = _carga()
    X = features.montar(c, None)
    alvo = pd.Timestamp("2024-02-10")
    # altera a carga de D-1 e D: as features do dia D não podem mudar
    c2 = c.copy()
    mask = c2.ts.dt.normalize().isin([alvo, alvo - pd.Timedelta(days=1)])
    c2.loc[mask, "y"] *= 10
    X2 = features.montar(c2, None)
    cols = [col for col in features.colunas_modelo(X) if col in X.columns]
    a = X[X.dia == alvo][cols].reset_index(drop=True)
    b = X2[X2.dia == alvo][cols].reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b)
    # e o alvo, claro, muda
    assert not np.allclose(X[X.dia == alvo].y, X2[X2.dia == alvo].y)


def test_lag7_e_a_mesma_hora_uma_semana_antes():
    c = _carga()
    X = features.montar(c, None)
    r = X[(X.dia == "2024-02-10") & (X.hora == 15)].iloc[0]
    esperado = c[c.ts == pd.Timestamp("2024-02-03 15:00")].y.iloc[0]
    assert r.lag7 == pytest.approx(esperado)


def test_corte_de_treino_respeita_a_vespera():
    ini = pd.Timestamp("2025-03-01")
    assert model.corte_treino(ini) == pd.Timestamp("2025-02-27")


def test_feriados_e_ponte():
    cal = features_calendario(pd.Series(pd.to_datetime(
        ["2025-12-25", "2025-11-21", "2025-03-04", "2025-03-05", "2025-04-21"])))
    cal = cal.set_index("dia")
    assert cal.loc["2025-12-25", "feriado"] == 1
    # 20/11 (Consciência Negra) caiu numa quinta em 2025: sexta 21/11 é ponte
    assert cal.loc["2025-11-21", "ponte"] == 1
    assert cal.loc["2025-03-04", "feriado"] == 1  # terça de Carnaval
    assert cal.loc["2025-03-05", "feriado"] == 0  # quarta de Cinzas não conta
    assert cal.loc["2025-04-21", "feriado"] == 1  # Tiradentes


def test_variante_manha_de_d1_so_usa_horas_antes_do_corte():
    c = _carga()
    alvo = pd.Timestamp("2024-02-10")
    X = features.montar(c, None, hora_corte_d1=10)
    c2 = c.copy()
    d1 = alvo - pd.Timedelta(days=1)
    # mudar a tarde de D-1 (depois do corte) e o dia D não pode mudar as features
    mask = ((c2.ts.dt.normalize() == d1) & (c2.ts.dt.hour >= 10)) | (c2.ts.dt.normalize() == alvo)
    c2.loc[mask, "y"] *= 10
    X2 = features.montar(c2, None, hora_corte_d1=10)
    cols = [col for col in features.colunas_modelo(X) if col in X.columns]
    pd.testing.assert_frame_equal(X[X.dia == alvo][cols].reset_index(drop=True),
                                  X2[X2.dia == alvo][cols].reset_index(drop=True))
    # mas mudar a manhã de D-1 muda
    c3 = c.copy()
    c3.loc[(c3.ts.dt.normalize() == d1) & (c3.ts.dt.hour < 10), "y"] *= 2
    X3 = features.montar(c3, None, hora_corte_d1=10)
    assert not np.allclose(X[X.dia == alvo].d1_manha_media, X3[X3.dia == alvo].d1_manha_media)
