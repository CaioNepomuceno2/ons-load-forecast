import numpy as np

from loadfc import metricas


def test_mape_e_mae():
    y = np.array([100.0, 200.0])
    p = np.array([110.0, 180.0])
    assert metricas.mape(y, p) == 10.0
    assert metricas.mae(y, p) == 15.0


def test_diebold_mariano_detecta_metodo_melhor():
    rng = np.random.default_rng(0)
    e1 = rng.normal(0, 1, 500)
    e2 = rng.normal(0, 2, 500)
    stat, p = metricas.diebold_mariano(e1, e2)
    assert stat < 0 and p < 0.01
    stat, p = metricas.diebold_mariano(e1, e1 + rng.normal(0, 0.001, 500))
    assert p > 0.05
