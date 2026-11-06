"""Backtest fora da amostra (retreino mensal) do modelo contra a carga programada do ONS e baselines.

Variantes do modelo (todas só com informação da véspera, exceto os oráculos):

* ``modelo_d2``: carga verificada até D-2 + temperatura prevista na véspera + calendário;
* ``modelo``: idem + carga da madrugada/manhã de D-1 (00h-10h), que o ONS também tem ao programar;
* ``oraculo``: como ``modelo``, mas com a temperatura observada de D (limite superior, não é previsão).

Variantes com irradiância e nuvens (``docs/preregistro_irradiancia.md``); mesmas regras, mais as colunas
``ghi``, ``nuv``, ``ghi_lag2``, ``ghi_delta``, ``ghi_media_dia`` e ``nuv_media_dia``:

* ``modelo_d2_irr`` e ``modelo_irr``: irradiância e nuvens previstas na véspera (``previous_day1``);
* ``oraculo_irr``: temperatura, irradiância e nuvens observadas de D (limite superior);
* ``modelo_irr_estrito``: previsões ``previous_day2`` (48 h antes), seguramente anteriores à programação;
* ``modelo_irr_embaralhado``: controle. As mesmas colunas, com a irradiância de outro dia (37 dias antes).

Uso: ``python scripts/backtest.py [variante ...] [--refazer]``. Sem nomes, roda todas as variantes
possíveis; uma variante cujo arquivo em ``data/processed`` já existe é pulada (retoma depois de uma queda),
a menos que se passe ``--refazer``.
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
DESLOCAMENTO_EMBARALHADO = 37
VARIANTES = {
    "modelo_d2": {"temp_col": "temp_prev_d1", "hora_corte_d1": None},
    "modelo": {"temp_col": "temp_prev_d1", "hora_corte_d1": 10},
    "oraculo": {"temp_col": "temp_obs", "hora_corte_d1": 10},
    "modelo_d2_irr": {"temp_col": "temp_prev_d1", "hora_corte_d1": None, "solar_fonte": "prev_d1"},
    "modelo_irr": {"temp_col": "temp_prev_d1", "hora_corte_d1": 10, "solar_fonte": "prev_d1"},
    "oraculo_irr": {"temp_col": "temp_obs", "hora_corte_d1": 10, "solar_fonte": "obs"},
    "modelo_irr_estrito": {"temp_col": "temp_prev_d1", "hora_corte_d1": 10, "solar_fonte": "prev_d2"},
    "modelo_irr_embaralhado": {"temp_col": "temp_prev_d1", "hora_corte_d1": 10, "solar_fonte": "prev_d1",
                               "embaralhar_dias": DESLOCAMENTO_EMBARALHADO},
}
# variantes cuja importância de features vai para reports/ (sufixo do arquivo)
IMPORTANCIA = {"modelo": "", "modelo_irr": "_irr"}


def matriz(carga, temp, solar, cfg):
    """Matriz de features de uma variante. O embaralhamento troca a irradiância de cada dia pela de outro."""
    cfg = dict(cfg)
    deslocar = cfg.pop("embaralhar_dias", 0)
    if "solar_fonte" in cfg:
        if solar is None:
            raise SystemExit("faltam irradiância e nuvens: rode download_weather.py e build_dataset.py")
        cfg["solar"] = solar.assign(ts=solar.ts + pd.Timedelta(days=deslocar)) if deslocar else solar
    return features.montar(carga[["area", "ts", "y"]], temp, **cfg)


def main(argv: list[str]) -> None:
    refazer = "--refazer" in argv
    nomes = [a for a in argv if not a.startswith("--")]
    carga = pd.read_parquet(INTERIM / "carga_horaria.parquet")
    temp = pd.read_parquet(INTERIM / "temperatura_area.parquet")
    arq_solar = INTERIM / "solar_area.parquet"
    solar = pd.read_parquet(arq_solar) if arq_solar.exists() else None
    if not nomes:
        nomes = [n for n, c in VARIANTES.items() if solar is not None or "solar_fonte" not in c]
    out_dir = DATA / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)

    for nome in nomes:
        destino = out_dir / f"bt_{nome}.parquet"
        if destino.exists() and not refazer:
            logging.info("%s: já existe, pulando (use --refazer)", nome)
            continue
        X = matriz(carga, temp, solar, VARIANTES[nome])
        bt = model.backtest(X, INICIO_TESTE, FIM_TESTE, inicio_treino=INICIO_TREINO)
        bt.rename(columns={"pred_modelo": f"pred_{nome}"}).to_parquet(destino, index=False)
        logging.info("%s: %d previsões", nome, len(bt))
        if nome in IMPORTANCIA:
            # importância das features no último modelo (treino até o fim do backtest)
            corte = model.corte_treino(pd.Timestamp(FIM_TESTE))
            imps = {}
            for area, g in X[(X.dia >= INICIO_TREINO) & (X.dia <= corte)].groupby("area"):
                m = model.treinar(g)
                imps[area] = model.importancia(m, features.colunas_modelo(g)).round(4).to_dict()
            REPORTS.mkdir(exist_ok=True)
            (REPORTS / f"importancia_features{IMPORTANCIA[nome]}.json").write_text(
                json.dumps(imps, indent=2, ensure_ascii=False))
        if nome == "modelo":
            model.baselines(X).to_parquet(out_dir / "baselines.parquet", index=False)
            X[["area", "dia", "temp_max_dia", "feriado", "ponte", "dow"]].drop_duplicates(["area", "dia"]) \
                .to_parquet(out_dir / "dias.parquet", index=False)


if __name__ == "__main__":
    main(sys.argv[1:])
