"""Backtest fora da amostra (retreino mensal) do modelo contra a carga programada do ONS e baselines.

Variantes do modelo (todas só com informação da véspera, exceto o oráculo):

* ``modelo_d2``: carga verificada até D-2 + temperatura prevista na véspera + calendário;
* ``modelo``: idem + carga da madrugada/manhã de D-1 (00h-10h), que o ONS também tem ao programar;
* ``oraculo``: como ``modelo``, mas com a temperatura observada de D (limite superior, não é previsão).
"""
import json
import logging
import os
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")

import pandas as pd  # noqa: E402

from loadfc import features, model  # noqa: E402
from loadfc.config import DATA, INTERIM, REPORTS  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
INICIO_TREINO, INICIO_TESTE, FIM_TESTE = "2022-01-15", "2024-01-01", "2026-10-01"
VARIANTES = {
    "modelo_d2": {"temp_col": "temp_prev_d1", "hora_corte_d1": None},
    "modelo": {"temp_col": "temp_prev_d1", "hora_corte_d1": 10},
    "oraculo": {"temp_col": "temp_obs", "hora_corte_d1": 10},
}
escolhidas = sys.argv[1:] or list(VARIANTES)
carga = pd.read_parquet(INTERIM / "carga_horaria.parquet")
temp = pd.read_parquet(INTERIM / "temperatura_area.parquet")
out_dir = DATA / "processed"
out_dir.mkdir(parents=True, exist_ok=True)

for nome in escolhidas:
    cfg = VARIANTES[nome]
    X = features.montar(carga[["area", "ts", "y"]], temp, **cfg)
    bt = model.backtest(X, INICIO_TESTE, FIM_TESTE, inicio_treino=INICIO_TREINO)
    bt.rename(columns={"pred_modelo": f"pred_{nome}"}).to_parquet(out_dir / f"bt_{nome}.parquet", index=False)
    logging.info("%s: %d previsões", nome, len(bt))
    if nome == "modelo":
        # importância das features no último modelo (treino até o fim do backtest)
        corte = model.corte_treino(pd.Timestamp(FIM_TESTE))
        imps = {}
        for area, g in X[(X.dia >= INICIO_TREINO) & (X.dia <= corte)].groupby("area"):
            m = model.treinar(g)
            imps[area] = model.importancia(m, features.colunas_modelo(g)).round(4).to_dict()
        REPORTS.mkdir(exist_ok=True)
        (REPORTS / "importancia_features.json").write_text(json.dumps(imps, indent=2, ensure_ascii=False))
        model.baselines(X).to_parquet(out_dir / "baselines.parquet", index=False)
        X[["area", "dia", "temp_max_dia", "feriado", "ponte", "dow"]].drop_duplicates(["area", "dia"]) \
            .to_parquet(out_dir / "dias.parquet", index=False)
