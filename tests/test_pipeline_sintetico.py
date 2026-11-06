"""Teste de fumaça: features -> previsão -> métrica, em dados sintéticos minúsculos, sem rede.

Um mundo de 5 meses (jan a mai de 2024), uma área, com carga que depende da hora, do dia da semana, da
temperatura e da irradiância (a MMGD tira carga ao meio-dia). Tudo sai de uma semente fixa e o LightGBM
roda com poucas árvores, então o teste é determinístico e leva poucos segundos.
"""
import numpy as np
import pandas as pd
import pytest

from loadfc import features, metricas, model, weather
from loadfc.config import CIDADES

AREA = "S"
PARAMS_RAPIDOS = {
    "objective": "l1", "learning_rate": 0.1, "num_leaves": 15, "min_child_samples": 20,
    "subsample": 0.8, "subsample_freq": 1, "colsample_bytree": 0.8, "n_estimators": 60,
    "n_jobs": 1, "verbose": -1, "random_state": 0,
}


def _mundo(dias=152):
    rng = np.random.default_rng(42)
    ts = pd.date_range("2024-01-01", periods=24 * dias, freq="h")
    hora, dow = ts.hour.to_numpy(), ts.day_of_week.to_numpy()
    nuvem_dia = rng.uniform(0.1, 1.0, dias)  # fração de céu coberto, sorteada por dia
    nuvem = np.repeat(nuvem_dia, 24)
    sol = np.clip(np.sin((hora - 6) / 12 * np.pi), 0, None) * 1000 * (1 - 0.8 * nuvem)
    temp = 24 + 5 * np.sin(np.arange(len(ts)) / (24 * 40)) + 3 * np.sin((hora - 9) / 24 * 2 * np.pi)
    carga = (5000 * (1 + 0.2 * np.sin((hora - 8) / 24 * 2 * np.pi)) * (1 - 0.12 * (dow >= 5))
             + 40 * (temp - 24) - 1.2 * sol + rng.normal(0, 25, len(ts)))
    carga_df = pd.DataFrame({"area": AREA, "ts": ts, "y": carga})
    temp_df = pd.DataFrame({"area": AREA, "ts": ts, "temp_prev_d1": temp + rng.normal(0, 0.5, len(ts)),
                            "temp_obs": temp})
    # "previsão" de irradiância e nuvens: o valor verdadeiro com um pouco de ruído; carimbo = fim da hora
    bruto = []
    for nome, _, _, peso in CIDADES[AREA]:
        ts_carimbo = ts + pd.Timedelta(hours=1)
        ruido = rng.normal(0, 30, len(ts))
        d = pd.DataFrame({"ts": ts_carimbo, "ghi_prev_d1": np.clip(sol + ruido, 0, None),
                          "ghi_prev_d2": np.clip(sol + 2 * ruido, 0, None), "ghi_obs": sol,
                          "nuv_prev_d1": nuvem * 100, "nuv_prev_d2": nuvem * 100, "nuv_obs": nuvem * 100})
        bruto.append(d.assign(area=AREA, cidade=nome, peso=peso))
    return carga_df, temp_df, weather.solar_area(pd.concat(bruto, ignore_index=True))


@pytest.fixture(scope="module")
def resultado():
    carga, temp, solar = _mundo()
    dados = {
        "sem": features.montar(carga, temp, hora_corte_d1=10),
        "irr": features.montar(carga, temp, hora_corte_d1=10, solar=solar),
    }
    saidas = {}
    mp = pytest.MonkeyPatch()
    mp.setattr(model, "PARAMS", PARAMS_RAPIDOS)
    try:
        for nome, X in dados.items():
            saidas[nome] = model.backtest(X, "2024-04-01", "2024-05-01", inicio_treino="2024-01-15")
    finally:
        mp.undo()
    return dados, saidas


def test_features_previsao_e_metrica_funcionam_de_ponta_a_ponta(resultado):
    dados, saidas = resultado
    for nome in ("sem", "irr"):
        bt = saidas[nome]
        assert len(bt) == (30 + 31) * 24  # abril e maio inteiros, 24 horas por dia
        assert bt.pred_modelo.notna().all() and np.isfinite(bt.pred_modelo).all()
        assert bt.ts.min() == pd.Timestamp("2024-04-01") and bt.ts.max() == pd.Timestamp("2024-05-31 23:00")
    # o modelo supera a regra ingênua "mesma hora na semana anterior"
    sem = saidas["sem"].merge(model.baselines(dados["sem"]), on=["area", "ts"])
    erro_modelo = metricas.mape(sem.y, sem.pred_modelo)
    erro_ingenuo = metricas.mape(sem.y, sem.pred_semana_anterior)
    assert erro_modelo < erro_ingenuo
    # e a irradiância, que explica o desvio diário da carga neste mundo, melhora o modelo
    erro_irr = metricas.mape(saidas["irr"].y, saidas["irr"].pred_modelo)
    assert erro_irr < 0.9 * erro_modelo


def test_diebold_mariano_e_tabela_sobre_a_saida_do_backtest(resultado):
    _, saidas = resultado
    a = saidas["sem"].rename(columns={"pred_modelo": "pred_sem"})
    b = saidas["irr"].rename(columns={"pred_modelo": "pred_irr"})
    df = a.merge(b[["area", "ts", "pred_irr"]], on=["area", "ts"])
    t = metricas.tabela(df, {"sem": "pred_sem", "irr": "pred_irr"}, ["area"])
    assert t.n_horas.iloc[0] == len(df)
    assert t.mape_irr.iloc[0] < t.mape_sem.iloc[0]
    diario = df.assign(ea=(df.pred_sem - df.y).abs() / df.y, eb=(df.pred_irr - df.y).abs() / df.y) \
        .groupby("dia")[["ea", "eb"]].mean()
    stat, p = metricas.diebold_mariano(diario.eb, diario.ea, h=7)
    assert stat < 0 and p < 0.05  # a irradiância melhora com significância


def test_a_matriz_com_irradiancia_so_acrescenta_colunas(resultado):
    dados, _ = resultado
    sem, irr = dados["sem"], dados["irr"]
    novas = [c for c in irr.columns if c not in sem.columns]
    assert set(novas) == {"ghi", "nuv", "ghi_media_dia", "nuv_media_dia", "ghi_lag2", "ghi_delta"}
    pd.testing.assert_frame_equal(sem, irr[sem.columns])
