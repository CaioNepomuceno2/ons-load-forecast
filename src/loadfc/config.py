"""Configuração do recorte: subsistemas, cidades para o clima e caminhos."""
from __future__ import annotations

import os
from pathlib import Path

# ``LOADFC_ROOT`` aponta os scripts para outra pasta de dados e relatórios (usado nos testes)
ROOT = Path(os.environ.get("LOADFC_ROOT") or Path(__file__).resolve().parents[2])
DATA = ROOT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"

# Áreas de carga da API do ONS que coincidem com os subsistemas do SIN.
SUBSISTEMAS = {"SECO": "Sudeste/Centro-Oeste", "S": "Sul", "NE": "Nordeste", "N": "Norte"}

# Centros de carga usados para a temperatura de cada subsistema, com peso
# aproximado pela população da região metropolitana (milhões, IBGE 2022, arredondado).
CIDADES = {
    "SECO": [("Sao Paulo", -23.55, -46.63, 20.7), ("Rio de Janeiro", -22.91, -43.17, 12.3),
             ("Belo Horizonte", -19.92, -43.94, 5.3), ("Brasilia", -15.79, -47.88, 3.9),
             ("Goiania", -16.69, -49.26, 2.6), ("Campo Grande", -20.47, -54.62, 0.9)],
    "S": [("Porto Alegre", -30.03, -51.23, 4.4), ("Curitiba", -25.43, -49.27, 3.7),
          ("Florianopolis", -27.59, -48.55, 1.2)],
    "NE": [("Salvador", -12.97, -38.50, 3.9), ("Recife", -8.05, -34.88, 3.9),
           ("Fortaleza", -3.73, -38.52, 4.1), ("Sao Luis", -2.53, -44.30, 1.6)],
    "N": [("Belem", -1.46, -48.49, 2.5), ("Manaus", -3.12, -60.02, 2.2), ("Palmas", -10.18, -48.33, 0.3)],
}

TZ = "America/Sao_Paulo"
