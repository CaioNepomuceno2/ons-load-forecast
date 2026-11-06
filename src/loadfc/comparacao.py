"""Comparação antes/depois de uma variante contra o modelo anterior e o ONS, por janela e faixa de horas."""
from __future__ import annotations

import pandas as pd

from loadfc import metricas

# janelas de avaliação fixadas em docs/preregistro_irradiancia.md: a principal é a do README
JANELAS = {"principal": "2024-01-01", "fev2025_em_diante": "2025-02-01"}
FAIXAS = {"todas as horas": (0, 23), "9h-16h": (9, 16)}
# (variante nova, referência): estatística negativa do DM = a variante nova erra menos
PARES = [("modelo_irr", "modelo"), ("modelo_irr", "ons"), ("modelo", "ons"),
         ("combinado_irr", "combinado"), ("combinado_irr", "ons"),
         ("modelo_irr_estrito", "modelo"), ("modelo_irr_embaralhado", "modelo"),
         ("modelo_d2_irr", "modelo_d2"), ("oraculo_irr", "oraculo")]


def recortar(df: pd.DataFrame, inicio: str, faixa: tuple[int, int]) -> pd.DataFrame:
    return df[(df.ts >= inicio) & df.hora.between(*faixa)]


def geral(df: pd.DataFrame, metodos: dict[str, str]) -> pd.DataFrame:
    """MAPE e MAE de cada método por janela, faixa de horas e área (formato longo)."""
    linhas = []
    for janela, inicio in JANELAS.items():
        for faixa, horas in FAIXAS.items():
            r = recortar(df, inicio, horas)
            for area, g in r.groupby("area"):
                for nome, col in metodos.items():
                    linhas.append({"janela": janela, "faixa": faixa, "area": area, "metodo": nome,
                                   "mape": metricas.mape(g.y, g[col]), "mae_mw": metricas.mae(g.y, g[col]),
                                   "n_horas": len(g)})
    return pd.DataFrame(linhas)


def por_hora(df: pd.DataFrame, metodos: dict[str, str]) -> pd.DataFrame:
    """MAPE por hora do dia, por janela e área (uma coluna por método)."""
    linhas = []
    for janela, inicio in JANELAS.items():
        r = df[df.ts >= inicio]
        t = metricas.tabela(r, metodos, ["area", "hora"])
        linhas.append(t[["area", "hora", *[f"mape_{m}" for m in metodos]]].assign(janela=janela))
    return pd.concat(linhas, ignore_index=True)


def diebold_mariano(df: pd.DataFrame, metodos: dict[str, str], h: int = 7) -> pd.DataFrame:
    """DM sobre o erro percentual médio diário, por janela, faixa de horas e área."""
    linhas = []
    for janela, inicio in JANELAS.items():
        for faixa, horas in FAIXAS.items():
            r = recortar(df, inicio, horas)
            for area, g in r.groupby("area"):
                ape = g.assign(**{f"ape_{k}": (g[c] - g.y).abs() / g.y for k, c in metodos.items()}) \
                    .groupby("dia")[[f"ape_{k}" for k in metodos]].mean()
                for a, b in [(a, b) for a, b in PARES if a in metodos and b in metodos]:
                    stat, p = metricas.diebold_mariano(ape[f"ape_{a}"], ape[f"ape_{b}"], h=h)
                    linhas.append({
                        "janela": janela, "faixa": faixa, "area": area, "comparacao": f"{a} vs {b}",
                        "mape_a": 100 * ape[f"ape_{a}"].mean(), "mape_b": 100 * ape[f"ape_{b}"].mean(),
                        "dm": stat, "p_valor": p, "n_dias": len(ape)})
    return pd.DataFrame(linhas)
