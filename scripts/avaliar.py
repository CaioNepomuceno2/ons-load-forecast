"""Compara o modelo, a carga programada do ONS e os baselines no período de teste."""
import json
import logging

import numpy as np
import pandas as pd

from loadfc import metricas
from loadfc.config import DATA, INTERIM, REPORTS, SUBSISTEMAS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
P = DATA / "processed"
carga = pd.read_parquet(INTERIM / "carga_horaria.parquet")
df = carga[["area", "ts", "y", "pred_ons", "mmgd"]]
variantes = [p.stem.removeprefix("bt_") for p in sorted(P.glob("bt_*.parquet"))]
for v in variantes:
    df = df.merge(pd.read_parquet(P / f"bt_{v}.parquet")[["area", "ts", f"pred_{v}"]], on=["area", "ts"])
df = df.merge(pd.read_parquet(P / "baselines.parquet"), on=["area", "ts"])
pred_cols = [c for c in df.columns if c.startswith("pred_")]
df = df.dropna(subset=["y", *pred_cols])
df["pred_combinado"] = (df.pred_modelo + df.pred_ons) / 2
pred_cols.append("pred_combinado")
if "pred_modelo_irr" in df.columns:  # variante com irradiância e nuvens (docs/preregistro_irradiancia.md)
    df["pred_combinado_irr"] = (df.pred_modelo_irr + df.pred_ons) / 2
    pred_cols.append("pred_combinado_irr")

# SIN = soma dos quatro subsistemas, só nas horas em que os quatro estão completos
completos = df.groupby("ts").area.transform("nunique") == len(SUBSISTEMAS)
sin = df[completos].groupby("ts")[["y", "mmgd", *pred_cols]].sum().reset_index().assign(area="SIN")
df = pd.concat([df, sin], ignore_index=True)
df["dia"], df["hora"], df["ano"] = df.ts.dt.normalize(), df.ts.dt.hour, df.ts.dt.year

dias = pd.read_parquet(P / "dias.parquet")
dias = pd.concat([dias, dias[dias.area == "SECO"].assign(area="SIN")])  # SIN herda o clima do SE/CO
df = df.merge(dias, on=["area", "dia"], how="left")
df["tipo_dia"] = np.select(
    [(df.feriado == 1) | (df.ponte == 1), df.dow == 6, df.dow == 5],
    ["feriado ou ponte", "domingo", "sábado"], "dia útil")
p90 = df.groupby("area").temp_max_dia.transform(lambda s: s.quantile(0.9))
df["calor"] = np.where(df.temp_max_dia > p90, "calor (máx. prevista > p90)", "demais dias")

metodos = {"modelo": "pred_modelo", "ons": "pred_ons", "combinado": "pred_combinado",
           "modelo_d2": "pred_modelo_d2", "oraculo": "pred_oraculo",
           "semana_anterior": "pred_semana_anterior", "media_4sem": "pred_media_4sem",
           "modelo_irr": "pred_modelo_irr", "combinado_irr": "pred_combinado_irr",
           "modelo_d2_irr": "pred_modelo_d2_irr", "oraculo_irr": "pred_oraculo_irr",
           "modelo_irr_estrito": "pred_modelo_irr_estrito",
           "modelo_irr_embaralhado": "pred_modelo_irr_embaralhado"}
metodos = {k: v for k, v in metodos.items() if v in df.columns}
REPORTS.mkdir(exist_ok=True)
ordem = {"SIN": 0, "SECO": 1, "S": 2, "NE": 3, "N": 4}
geral = metricas.tabela(df, metodos, ["area"]).sort_values("area", key=lambda s: s.map(ordem))
geral.to_csv(REPORTS / "mape_geral.csv", index=False)
for nome, por in {"ano": ["area", "ano"], "hora": ["area", "hora"], "tipo_dia": ["area", "tipo_dia"],
                  "calor": ["area", "calor"]}.items():
    metricas.tabela(df, metodos, por).to_csv(REPORTS / f"mape_por_{nome}.csv", index=False)
mensal = metricas.tabela(df.assign(mes=df.ts.dt.to_period("M").dt.to_timestamp()), metodos, ["area", "mes"])
mensal.to_csv(REPORTS / "mape_mensal.csv", index=False)

# Diebold-Mariano sobre o erro percentual médio diário (h=7 para a autocorrelação semanal)
dm = []
for area, g in df.groupby("area"):
    d = g.assign(**{f"ape_{k}": (g[c] - g.y).abs() / g.y for k, c in metodos.items()}) \
        .groupby("dia")[[f"ape_{k}" for k in metodos]].mean()
    pares = [("modelo", "ons"), ("combinado", "ons"), ("modelo", "semana_anterior"),
             ("modelo_irr", "modelo"), ("modelo_irr", "ons"), ("combinado_irr", "combinado"),
             ("combinado_irr", "ons"), ("modelo_irr_estrito", "modelo"), ("modelo_irr_embaralhado", "modelo"),
             ("modelo_d2_irr", "modelo_d2"), ("oraculo_irr", "oraculo")]
    for a, b in [(a, b) for a, b in pares if a in metodos and b in metodos]:
        stat, p = metricas.diebold_mariano(d[f"ape_{a}"], d[f"ape_{b}"], h=7)
        dm.append({"area": area, "comparacao": f"{a} vs {b}", "dm": round(stat, 2), "p_valor": p,
                   "n_dias": len(d)})
dm = pd.DataFrame(dm)
dm.to_csv(REPORTS / "diebold_mariano.csv", index=False)

# meio do dia (10h-14h) x MMGD: o erro de cada método acompanha a fatia de MMGD na carga?
md = df[df.hora.between(10, 13)].assign(mmgd_frac=lambda d: d.mmgd / d.y)
meio = metricas.tabela(md, {k: metodos[k] for k in ["modelo", "ons", "modelo_irr"] if k in metodos},
                       ["area", "ano"])
meio = meio.merge(md.groupby(["area", "ano"]).mmgd_frac.mean().reset_index(), on=["area", "ano"])
meio.to_csv(REPORTS / "meio_dia_mmgd.csv", index=False)

df.to_parquet(P / "avaliacao.parquet", index=False)
res = {
    "periodo_teste": [str(df.ts.min()), str(df.ts.max())],
    "mape_geral": geral.round(3).to_dict("records"),
    "diebold_mariano": dm.round(4).to_dict("records"),
    "meio_dia_mmgd": meio.round(4).to_dict("records"),
}
(REPORTS / "resultados.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
cols = ["area"] + [f"mape_{k}" for k in metodos] + ["n_horas"]
print(geral[cols].round(2).to_string(index=False))
print(dm.to_string(index=False))
