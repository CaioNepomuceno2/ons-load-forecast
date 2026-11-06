import numpy as np
import pandas as pd
import pytest

from loadfc import comparacao


def _avaliacao():
    rng = np.random.default_rng(1)
    ts = pd.date_range("2024-06-01", "2025-06-30 23:00", freq="h")
    y = 1000 + 50 * rng.standard_normal(len(ts))
    ruido = rng.standard_normal(len(ts))
    df = pd.DataFrame({"area": "SIN", "ts": ts, "y": y, "pred_modelo": y + 40 * ruido,
                       "pred_modelo_irr": y + 20 * ruido, "pred_ons": y + 30 * rng.standard_normal(len(ts))})
    return df.assign(dia=df.ts.dt.normalize(), hora=df.ts.dt.hour)


METODOS = {"modelo": "pred_modelo", "modelo_irr": "pred_modelo_irr", "ons": "pred_ons"}


def test_geral_respeita_janela_e_faixa():
    df = _avaliacao()
    g = comparacao.geral(df, METODOS)
    # 2 janelas x 2 faixas x 1 área x 3 métodos
    assert len(g) == 12
    a = g[(g.janela == "principal") & (g.faixa == "todas as horas") & (g.metodo == "modelo")].iloc[0]
    b = g[(g.janela == "fev2025_em_diante") & (g.faixa == "todas as horas") & (g.metodo == "modelo")].iloc[0]
    c = g[(g.janela == "principal") & (g.faixa == "9h-16h") & (g.metodo == "modelo")].iloc[0]
    assert a.n_horas == len(df)
    assert b.n_horas == (df.ts >= "2025-02-01").sum()
    assert c.n_horas == df.hora.between(9, 16).sum()
    # a variante com metade do ruído tem metade do erro
    irr = g[(g.janela == "principal") & (g.faixa == "todas as horas") & (g.metodo == "modelo_irr")].iloc[0]
    assert irr.mape == pytest.approx(a.mape / 2, rel=0.05)


def test_por_hora_tem_24_horas_por_janela():
    t = comparacao.por_hora(_avaliacao(), METODOS)
    assert set(t.janela) == {"principal", "fev2025_em_diante"}
    assert t[t.janela == "principal"].hora.nunique() == 24
    assert (t.mape_modelo_irr < t.mape_modelo).all()


def test_diebold_mariano_so_compara_pares_existentes_e_aponta_o_melhor():
    dm = comparacao.diebold_mariano(_avaliacao(), METODOS)
    assert set(dm.comparacao) == {"modelo_irr vs modelo", "modelo_irr vs ons", "modelo vs ons"}
    r = dm[(dm.comparacao == "modelo_irr vs modelo") & (dm.janela == "principal")
           & (dm.faixa == "todas as horas")].iloc[0]
    assert r.dm < 0 and r.p_valor < 0.01  # estatística negativa = a variante nova erra menos
    assert r.mape_a < r.mape_b
    assert r.n_dias == 395  # jun/2024 a jun/2025
