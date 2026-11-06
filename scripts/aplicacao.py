"""Números de apoio à seção "Na prática" do README.

Lê data/processed/avaliacao.parquet (gerado por scripts/avaliar.py) e grava reports/aplicacao.json:
erro absoluto em MW do ONS, do modelo e da média modelo + ONS, inclusive na cauda (horas de erro grande),
que é o que pesa no dimensionamento de reserva e no redespacho. As chaves ``modelo`` e ``combinado`` são as
versões sem irradiância; ``modelo_irr`` e ``combinado_irr`` são as com irradiância e nuvens previstas.
"""
import json

import numpy as np
import pandas as pd

from loadfc.config import DATA, REPORTS

PROCESSED = DATA / "processed"

df = pd.read_parquet(PROCESSED / "avaliacao.parquet")
metodos = {"ons": "pred_ons", "modelo": "pred_modelo", "combinado": "pred_combinado"}
if "pred_modelo_irr" in df.columns:  # variante com irradiância e nuvens: chaves novas, as antigas não mudam
    metodos |= {"modelo_irr": "pred_modelo_irr", "combinado_irr": "pred_combinado_irr"}
out = {"periodo": [str(df.ts.min()), str(df.ts.max())]}

for area in ["SIN", "SECO", "S", "NE", "N"]:
    a = df[df.area == area].dropna(subset=["y", *metodos.values()])
    r = {"carga_media_mw": round(float(a.y.mean()), 0), "n_horas": len(a)}
    for nome, col in metodos.items():
        err = (a[col] - a.y).abs()
        r[nome] = {
            "mae_mw": round(float(err.mean()), 0),
            "p95_mw": round(float(np.percentile(err, 95)), 0),
            "p99_mw": round(float(np.percentile(err, 99)), 0),
            "horas_erro_acima_5pct": int((err / a.y > 0.05).sum()),
        }
    r["reducao_mae_combinado_vs_ons_mw"] = r["ons"]["mae_mw"] - r["combinado"]["mae_mw"]
    r["reducao_p95_combinado_vs_ons_mw"] = r["ons"]["p95_mw"] - r["combinado"]["p95_mw"]
    if "combinado_irr" in r:
        r["reducao_mae_combinado_irr_vs_ons_mw"] = r["ons"]["mae_mw"] - r["combinado_irr"]["mae_mw"]
        r["reducao_p95_combinado_irr_vs_ons_mw"] = r["ons"]["p95_mw"] - r["combinado_irr"]["p95_mw"]
    out[area] = r

# meio do dia (10h-14h) no SIN em 2026, onde a MMGD pesa mais
m = df[(df.area == "SIN") & df.hora.between(10, 13) & (df.ano == 2026)].dropna(subset=["y", "pred_ons"])
out["SIN_10h_14h_2026"] = {
    nome: round(float((m[col] - m.y).abs().mean()), 0) for nome, col in metodos.items()
}

(REPORTS / "aplicacao.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(out, indent=2, ensure_ascii=False))
