"""Monta a base horária (carga verificada, programada, temperatura, irradiância) e a matriz de features."""
import logging

import pandas as pd

from loadfc import features, ons, weather
from loadfc.config import CIDADES, INTERIM, RAW

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

temp_raw = pd.concat([pd.read_parquet(p) for p in sorted((RAW / "openmeteo").glob("temperatura_*.parquet"))])
temp = weather.temperatura_area(temp_raw)
temp.to_parquet(INTERIM / "temperatura_area.parquet", index=False)

for nome, col in [("features", "temp_prev_d1"), ("features_oraculo", "temp_obs")]:
    X = features.montar(carga[["area", "ts", "y"]], temp, temp_col=col)
    X.to_parquet(INTERIM / f"{nome}.parquet", index=False)
    logging.info("%s: %d linhas", nome, len(X))

# irradiância e nuvens: exige o download completo (todos os subsistemas em todos os anos baixados)
pasta_solar = RAW / "openmeteo_solar"
arquivos = sorted(pasta_solar.glob("sol_*.parquet"))
if arquivos:
    anos = sorted({int(p.stem.split("_")[1]) for p in arquivos})
    faltam = [f"sol_{a}_{s}" for a in anos for s in CIDADES
              if not (pasta_solar / f"sol_{a}_{s}.parquet").exists()]
    if faltam:
        raise SystemExit(f"download de irradiância incompleto, faltam: {faltam}")
    solar = weather.solar_area(pd.concat([pd.read_parquet(p) for p in arquivos]))
    solar.to_parquet(INTERIM / "solar_area.parquet", index=False)
    logging.info("irradiância e nuvens: %d linhas, %s a %s", len(solar), solar.ts.min(), solar.ts.max())
    for nome, col, fonte in [("features_irr", "temp_prev_d1", "prev_d1"),
                             ("features_oraculo_irr", "temp_obs", "obs")]:
        X = features.montar(carga[["area", "ts", "y"]], temp, temp_col=col, solar=solar, solar_fonte=fonte)
        X.to_parquet(INTERIM / f"{nome}.parquet", index=False)
        logging.info("%s: %d linhas", nome, len(X))
else:
    logging.info("sem irradiância baixada (data/raw/openmeteo_solar vazio): rode download_weather.py")
