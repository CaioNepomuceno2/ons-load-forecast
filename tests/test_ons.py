import pandas as pd

from loadfc import ons


def test_parse_json_aceita_campos_vazios():
    txt = '[{"a": 1, "b": , "c": 2.5}, {"a": , "b": 3, "c": }]'
    d = ons.parse_json(txt)
    assert d[0]["b"] is None and d[1]["c"] is None and d[1]["b"] == 3


def test_para_horario_usa_inicio_do_intervalo_em_horario_local():
    # 03:30 UTC = 00:30 local (fim do 1º intervalo do dia); 04:00 UTC = 01:00 local
    ts = pd.to_datetime(["2025-01-01T03:30Z", "2025-01-01T04:00Z", "2025-01-01T04:30Z"], utc=True)
    df = pd.DataFrame({"area": "S", "ts_fim_utc": ts, "v": [10.0, 20.0, 99.0]})
    h = ons.para_horario(df, "v")
    # a hora 00h local tem as duas metades (fim 00:30 e 01:00); a hora 01h só tem uma e é descartada
    assert list(h.ts) == [pd.Timestamp("2025-01-01 00:00")]
    assert h.v.iloc[0] == 15.0
