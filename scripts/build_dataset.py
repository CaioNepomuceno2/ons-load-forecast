"""Monta a base horária (carga verificada, programada e temperatura) e a matriz de features."""
import logging

import pandas as pd

from loadfc import features, ons, weather
from loadfc.config import INTERIM, RAW

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
INTERIM.mkdir(parents=True, exist_ok=True)

prog = ons.ler("programada", RAW / "ons")
verif = ons.ler("verificada", RAW / "ons")
# A carga programada corresponde à carga global verificada (com MMGD); ver docs/dados.md.
h_v = ons.para_horario(verif, "val_cargaglobal").rename(columns={"val_cargaglobal": "y"})
h_p = ons.para_horario(prog, "val_cargaglobalprogramada").rename(
    columns={"val_cargaglobalprogramada": "pred_ons"})
h_mmgd = ons.para_horario(verif.dropna(subset=["val_cargammgd"]), "val_cargammgd").rename(
    columns={"val_cargammgd": "mmgd"})
carga = h_v.merge(h_p, on=["area", "ts"], how="left").merge(h_mmgd, on=["area", "ts"], how="left")
carga.to_parquet(INTERIM / "carga_horaria.parquet", index=False)
logging.info("carga horária: %d linhas, %s a %s", len(carga), carga.ts.min(), carga.ts.max())

temp_raw = pd.concat([pd.read_parquet(p) for p in sorted((RAW / "openmeteo").glob("*.parquet"))])
temp = weather.temperatura_area(temp_raw)
temp.to_parquet(INTERIM / "temperatura_area.parquet", index=False)

for nome, col in [("features", "temp_prev_d1"), ("features_oraculo", "temp_obs")]:
    X = features.montar(carga[["area", "ts", "y"]], temp, temp_col=col)
    X.to_parquet(INTERIM / f"{nome}.parquet", index=False)
    logging.info("%s: %d linhas", nome, len(X))
