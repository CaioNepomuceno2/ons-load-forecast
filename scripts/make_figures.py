"""Figuras do README a partir de data/processed/avaliacao.parquet e reports/*.csv."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.dates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from loadfc.config import DATA, FIGURES, REPORTS, SUBSISTEMAS  # noqa: E402

FIGURES.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"figure.dpi": 130, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.3, "font.size": 10})
COR = {"modelo": "#2a78d6", "ons": "#e8692f", "combinado": "#7b4fd6", "semana_anterior": "#1aa37a",
       "media_4sem": "#9aa0a6", "modelo_d2": "#8fb8ea", "oraculo": "#444444"}
ROT = {"modelo": "Modelo aberto (LightGBM)", "ons": "ONS: carga programada",
       "combinado": "Média modelo + ONS",
       "semana_anterior": "Mesma hora, semana anterior", "media_4sem": "Média das últimas 4 semanas",
       "modelo_d2": "Modelo só com dados até D-2", "oraculo": "Modelo com temperatura observada (oráculo)"}
NOMES = {"SIN": "SIN", **SUBSISTEMAS}

geral = pd.read_csv(REPORTS / "mape_geral.csv")
areas = ["SIN", "SECO", "S", "NE", "N"]
metodos = ["modelo", "ons", "combinado", "semana_anterior"]

# 1. MAPE por subsistema
fig, ax = plt.subplots(figsize=(9, 4.2))
w = 0.2
for i, m in enumerate(metodos):
    vals = [geral.set_index("area").loc[a, f"mape_{m}"] for a in areas]
    bars = ax.bar([x + (i - 1.5) * w for x in range(len(areas))], vals, w, color=COR[m], label=ROT[m])
    ax.bar_label(bars, fmt="%.1f", fontsize=7, padding=1)
ax.set_xticks(range(len(areas)), [NOMES[a] for a in areas])
ax.set_ylabel("MAPE horário (%)  · menor é melhor")
ini, fim = pd.read_parquet(DATA / "processed" / "avaliacao.parquet", columns=["ts"]).ts.agg(["min", "max"])
ax.set_title(f"Erro da previsão do dia seguinte, {ini:%m/%Y} a {fim:%m/%Y}", loc="left", fontweight="bold")
ax.legend(frameon=False, fontsize=8, ncol=2)
fig.tight_layout()
fig.savefig(FIGURES / "01_mape_subsistema.png")

# 2. MAPE por hora do dia (SIN)
hora = pd.read_csv(REPORTS / "mape_por_hora.csv")
fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=False)
for ax, a in zip(axes, ["SIN", "NE"], strict=True):
    h = hora[hora.area == a]
    for m in ["modelo", "ons", "semana_anterior"]:
        ax.plot(h.hora, h[f"mape_{m}"], color=COR[m], label=ROT[m], lw=2)
    ax.set_title(NOMES[a], loc="left", fontweight="bold")
    ax.set_xlabel("Hora do dia")
    ax.set_xticks(range(0, 24, 3))
axes[0].set_ylabel("MAPE (%)")
axes[0].legend(frameon=False, fontsize=8)
fig.tight_layout()
fig.savefig(FIGURES / "02_mape_por_hora.png")

# 3. tipo de dia e calor
tipo = pd.read_csv(REPORTS / "mape_por_tipo_dia.csv")
calor = pd.read_csv(REPORTS / "mape_por_calor.csv").rename(columns={"calor": "tipo_dia"})
t = pd.concat([tipo, calor])
t = t[t.area == "SIN"].set_index("tipo_dia").loc[
    ["dia útil", "sábado", "domingo", "feriado ou ponte", "calor (máx. prevista > p90)"]]
fig, ax = plt.subplots(figsize=(9, 3.8))
for i, m in enumerate(["modelo", "ons", "semana_anterior"]):
    xs = [x + (i - 1) * 0.27 for x in range(len(t))]
    bars = ax.bar(xs, t[f"mape_{m}"], 0.27, color=COR[m], label=ROT[m])
    ax.bar_label(bars, fmt="%.1f", fontsize=7, padding=1)
ax.set_xticks(range(len(t)), [s.replace(" (", "\n(") for s in t.index], fontsize=8)
ax.set_ylabel("MAPE horário do SIN (%)")
ax.set_title("Onde cada um erra", loc="left", fontweight="bold")
ax.legend(frameon=False, fontsize=8)
fig.tight_layout()
fig.savefig(FIGURES / "03_tipo_de_dia.png")

# 4. MAPE mensal do SIN
mens = pd.read_csv(REPORTS / "mape_mensal.csv", parse_dates=["mes"])
mens = mens[mens.area == "SIN"]
fig, ax = plt.subplots(figsize=(9, 3.5))
for m in ["modelo", "ons", "combinado"]:
    ax.plot(mens.mes, mens[f"mape_{m}"], color=COR[m], label=ROT[m], lw=2, marker="o", ms=3)
ax.set_ylabel("MAPE mensal do SIN (%)")
ax.set_title("Evolução mês a mês", loc="left", fontweight="bold")
ax.legend(frameon=False, fontsize=8)
fig.tight_layout()
fig.savefig(FIGURES / "04_mape_mensal.png")

# 5. semana com feriado (Carnaval 2025) no SE/CO
av = pd.read_parquet(DATA / "processed" / "avaliacao.parquet")
s = av[(av.area == "SECO") & (av.ts >= "2025-02-27") & (av.ts < "2025-03-08")]
fig, ax = plt.subplots(figsize=(9, 3.5))
ax.plot(s.ts, s.y / 1e3, color="black", lw=2, label="Carga verificada")
for m in ["modelo", "ons", "semana_anterior"]:
    ax.plot(s.ts, s[f"pred_{m}"] / 1e3, color=COR[m], lw=1.4, label=ROT[m])
ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%d/%m"))
ax.set_ylabel("GWmed")
ax.set_title("Carnaval de 2025 no Sudeste/Centro-Oeste", loc="left", fontweight="bold")
ax.legend(frameon=False, fontsize=8, ncol=2)
fig.tight_layout()
fig.savefig(FIGURES / "05_carnaval_2025.png")
# 6. meio do dia x MMGD (SIN)
meio = pd.read_csv(REPORTS / "meio_dia_mmgd.csv")
meio = meio[meio.area == "SIN"]
fig, ax = plt.subplots(figsize=(7, 3.6))
for m in ["modelo", "ons"]:
    ax.plot(meio.ano, meio[f"mape_{m}"], color=COR[m], marker="o", lw=2, label=ROT[m])
for _, r in meio.iterrows():
    ax.annotate(f"MMGD = {r.mmgd_frac:.0%}\nda carga", (r.ano, r.mape_ons), textcoords="offset points",
                xytext=(0, 8), ha="center", fontsize=8, color="#555")
ax.set_xlim(meio.ano.min() - 0.35, meio.ano.max() + 0.35)
ax.set_xticks(meio.ano, [f"{a}" if a < 2026 else "2026 (jan-out)" for a in meio.ano])
ax.set_ylim(0, meio[["mape_modelo", "mape_ons"]].max().max() * 1.35)
ax.set_ylabel("MAPE do SIN, 10h-14h (%)")
ax.set_title("No meio do dia, o erro do ONS cresce com a geração distribuída", loc="left", fontweight="bold")
ax.legend(frameon=False, fontsize=8, loc="lower right")
fig.tight_layout()
fig.savefig(FIGURES / "06_meio_dia_mmgd.png")

print(sorted(p.name for p in FIGURES.glob("*.png")))
