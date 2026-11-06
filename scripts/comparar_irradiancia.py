"""Antes/depois da irradiância: MAPE geral e por hora, e Diebold-Mariano contra o modelo anterior e o ONS.

Lê data/processed/avaliacao.parquet (gerado por scripts/avaliar.py) e grava em reports/:
``irradiancia_geral.csv``, ``irradiancia_por_hora.csv`` e ``irradiancia_diebold_mariano.csv``.
Janelas e faixas de horas: ver ``loadfc.comparacao`` e ``docs/preregistro_irradiancia.md``.
"""
import pandas as pd

from loadfc import comparacao
from loadfc.config import DATA, REPORTS

df = pd.read_parquet(DATA / "processed" / "avaliacao.parquet")
nomes = ["ons", "modelo", "modelo_irr", "combinado", "combinado_irr", "modelo_d2", "modelo_d2_irr",
         "oraculo", "oraculo_irr", "modelo_irr_estrito", "modelo_irr_embaralhado"]
metodos = {n: f"pred_{n}" for n in nomes if f"pred_{n}" in df.columns}
if "modelo_irr" not in metodos:
    raise SystemExit("sem pred_modelo_irr em avaliacao.parquet: rode backtest.py e avaliar.py")

REPORTS.mkdir(exist_ok=True)
g = comparacao.geral(df, metodos)
g.to_csv(REPORTS / "irradiancia_geral.csv", index=False)
comparacao.por_hora(df, metodos).to_csv(REPORTS / "irradiancia_por_hora.csv", index=False)
dm = comparacao.diebold_mariano(df, metodos)
dm.to_csv(REPORTS / "irradiancia_diebold_mariano.csv", index=False)

for janela in comparacao.JANELAS:
    for faixa in comparacao.FAIXAS:
        t = g[(g.janela == janela) & (g.faixa == faixa)].pivot(index="area", columns="metodo", values="mape")
        print(f"\nMAPE (%), janela {janela}, {faixa}")
        print(t.reindex(["SIN", "SECO", "S", "NE", "N"])[list(metodos)].round(3).to_string())
print()
print(dm[dm.area == "SIN"].round(4).to_string(index=False))
