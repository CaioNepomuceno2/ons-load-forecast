"""Cadeia de relatórios (avaliar -> aplicacao -> comparar_irradiancia -> make_figures) em dados sintéticos.

Cria uma pasta temporária com os parquet que o backtest deixaria em ``data/`` e roda os quatro scripts de
verdade, apontados para ela por ``LOADFC_ROOT``. Sem rede e com poucos dias de dados.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
AREAS = {"SECO": 40000, "S": 12000, "NE": 11000, "N": 7000}
VARIANTES = ["modelo", "modelo_d2", "oraculo", "modelo_irr", "modelo_irr_estrito", "modelo_irr_embaralhado"]
RUIDO = {"modelo": 0.030, "modelo_d2": 0.034, "oraculo": 0.025, "modelo_irr": 0.020,
         "modelo_irr_estrito": 0.021, "modelo_irr_embaralhado": 0.029}


def _criar_dados(raiz: Path) -> None:
    rng = np.random.default_rng(7)
    ts = pd.date_range("2025-02-01", "2025-03-31 23:00", freq="h")
    interim, processed = raiz / "data" / "interim", raiz / "data" / "processed"
    interim.mkdir(parents=True), processed.mkdir(parents=True)
    carga, baselines, bts = [], [], {v: [] for v in VARIANTES}
    for area, nivel in AREAS.items():
        forma = 1 + 0.2 * np.sin((ts.hour.to_numpy() - 8) / 24 * 2 * np.pi)
        y = nivel * forma * (1 + 0.01 * rng.standard_normal(len(ts)))
        mmgd = 0.25 * y * np.clip(np.sin((ts.hour.to_numpy() - 6) / 12 * np.pi), 0, None)
        carga.append(pd.DataFrame({"area": area, "ts": ts, "y": y, "mmgd": mmgd,
                                   "pred_ons": y * (1 + 0.03 * rng.standard_normal(len(ts)))}))
        baselines.append(pd.DataFrame({"area": area, "ts": ts, "pred_semana_anterior": np.roll(y, 168),
                                       "pred_media_4sem": np.roll(y, 168 * 2)}))
        for v in VARIANTES:
            ruido = RUIDO[v] * rng.standard_normal(len(ts))
            bts[v].append(pd.DataFrame({"area": area, "ts": ts, "dia": ts.normalize(), "hora": ts.hour,
                                        "y": y, f"pred_{v}": y * (1 + ruido)}))
    pd.concat(carga).to_parquet(interim / "carga_horaria.parquet", index=False)
    pd.concat(baselines).to_parquet(processed / "baselines.parquet", index=False)
    for v, lista in bts.items():
        pd.concat(lista).to_parquet(processed / f"bt_{v}.parquet", index=False)
    dias = pd.DataFrame({"dia": ts.normalize().unique()})
    dias = dias.assign(temp_max_dia=25 + 5 * rng.random(len(dias)), feriado=0, ponte=0,
                       dow=dias.dia.dt.day_of_week)
    dias.loc[dias.dia.isin(pd.to_datetime(["2025-03-03", "2025-03-04"])), "feriado"] = 1
    pd.concat([dias.assign(area=a) for a in AREAS]).to_parquet(processed / "dias.parquet", index=False)


@pytest.fixture(scope="module")
def raiz(tmp_path_factory):
    raiz = tmp_path_factory.mktemp("relatorio")
    _criar_dados(raiz)
    env = {**os.environ, "LOADFC_ROOT": str(raiz), "PYTHONUTF8": "1", "MPLBACKEND": "Agg"}
    for script in ["avaliar", "aplicacao", "comparar_irradiancia", "make_figures"]:
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / f"{script}.py")], env=env, cwd=raiz,
                           capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, f"{script}: {r.stderr[-1500:]}"
    return raiz


def test_avaliar_gera_tabelas_com_as_variantes_novas(raiz):
    g = pd.read_csv(raiz / "reports" / "mape_geral.csv").set_index("area")
    assert list(g.index) == ["SIN", "SECO", "S", "NE", "N"]
    for m in ["modelo", "ons", "combinado", "modelo_irr", "combinado_irr", "modelo_irr_embaralhado"]:
        assert f"mape_{m}" in g.columns
    # o ruído sintético de modelo_irr é menor que o de modelo: o MAPE tem de refletir isso
    assert (g.mape_modelo_irr < g.mape_modelo).all()
    dm = pd.read_csv(raiz / "reports" / "diebold_mariano.csv")
    assert {"modelo_irr vs modelo", "modelo_irr vs ons", "modelo_irr vs semana_anterior",
            "combinado_irr vs combinado"} <= set(dm.comparacao)
    r = dm[(dm.area == "SIN") & (dm.comparacao == "modelo_irr vs modelo")].iloc[0]
    assert r.dm < 0 and r.p_valor < 0.05


def test_carnaval_e_meio_dia(raiz):
    c = pd.read_csv(raiz / "reports" / "carnaval_2025.csv")
    assert len(c) == 3 and "mape_modelo_irr" in c.columns  # segunda, terça e quarta de Cinzas
    m = pd.read_csv(raiz / "reports" / "meio_dia_mmgd.csv")
    assert {"mape_modelo", "mape_ons", "mape_modelo_irr", "mmgd_frac"} <= set(m.columns)


def test_aplicacao_mantem_chaves_antigas_e_acrescenta_as_novas(raiz):
    a = json.loads((raiz / "reports" / "aplicacao.json").read_text(encoding="utf-8"))
    for area in ["SIN", "SECO", "S", "NE", "N"]:
        assert {"ons", "modelo", "combinado", "modelo_irr", "combinado_irr"} <= set(a[area])
        assert a[area]["modelo_irr"]["mae_mw"] <= a[area]["modelo"]["mae_mw"]
        assert "reducao_mae_combinado_irr_vs_ons_mw" in a[area]


def test_comparacao_e_figuras(raiz):
    r = raiz / "reports"
    g = pd.read_csv(r / "irradiancia_geral.csv")
    assert set(g.janela) == {"principal", "fev2025_em_diante"}
    assert set(g.faixa) == {"todas as horas", "9h-16h"}
    h = pd.read_csv(r / "irradiancia_por_hora.csv")
    assert h[h.janela == "principal"].hora.nunique() == 24
    dm = pd.read_csv(r / "irradiancia_diebold_mariano.csv")
    assert (dm.comparacao == "modelo_irr vs modelo").any()
    figuras = {p.name for p in (r / "figures").glob("*.png")}
    assert {"01_mape_subsistema.png", "02_mape_por_hora.png", "03_tipo_de_dia.png", "04_mape_mensal.png",
            "05_carnaval_2025.png", "06_meio_dia_mmgd.png", "07_irradiancia_por_hora.png"} <= figuras
