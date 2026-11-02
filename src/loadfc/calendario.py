"""Calendário: feriados nacionais e efeitos de ponte, véspera e fim de ano."""
from __future__ import annotations

import holidays
import pandas as pd


def feriados_nacionais(anos: range | list[int]) -> set[pd.Timestamp]:
    """Feriados nacionais do Brasil, incluindo Carnaval (segunda e terça) e Corpus Christi,
    que são pontos facultativos mas derrubam a carga como feriados."""
    br = holidays.Brazil(years=list(anos), categories=(holidays.PUBLIC, holidays.OPTIONAL))
    dias = {pd.Timestamp(d) for d, nome in br.items()
            if "Quarta-feira de Cinzas" not in nome and "Ash Wednesday" not in nome}
    return dias


def features_calendario(dias: pd.Series) -> pd.DataFrame:
    """Uma linha por dia (Timestamp sem hora) com flags de calendário."""
    d = pd.to_datetime(dias).dt.normalize()
    fer = feriados_nacionais(range(d.dt.year.min() - 1, d.dt.year.max() + 2))
    eh = d.isin(fer)
    ontem, amanha = d - pd.Timedelta(days=1), d + pd.Timedelta(days=1)
    dow = d.dt.day_of_week
    return pd.DataFrame({
        "dia": d,
        "dow": dow,
        "mes": d.dt.month,
        "doy": d.dt.day_of_year,
        "feriado": eh.astype(int),
        # ponte: segunda antes de feriado na terça, ou sexta depois de feriado na quinta
        "ponte": (((dow == 0) & amanha.isin(fer)) | ((dow == 4) & ontem.isin(fer))).astype(int),
        "vespera_feriado": amanha.isin(fer).astype(int),
        "pos_feriado": ontem.isin(fer).astype(int),
        "fim_de_ano": (((d.dt.month == 12) & (d.dt.day >= 24))
                       | ((d.dt.month == 1) & (d.dt.day <= 2))).astype(int),
    })
