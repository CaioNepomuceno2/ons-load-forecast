"""Irradiância e nuvens: de onde vêm os valores, alinhamento horário e ausência de vazamento do dia D."""
import importlib.util
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from loadfc import features, weather
from loadfc.config import CIDADES

ROOT = Path(__file__).resolve().parents[1]
DIA = pd.Timestamp("2024-02-10")  # dia alvo dos testes de vazamento
COLS_SOLAR = list(weather.VARS_SOLAR.values())


def _carga(dias=60, area="S"):
    ts = pd.date_range("2024-01-01", periods=24 * dias, freq="h")
    y = 1000 + 100 * np.sin(np.arange(len(ts)) / 24 * 2 * np.pi) + np.arange(len(ts)) * 0.1
    return pd.DataFrame({"area": area, "ts": ts, "y": y})


def _bruto(dias=60, sub="S", semente=0):
    """Quadro por cidade e hora, como sai de ``quadro_solar``, com valores aleatórios."""
    rng = np.random.default_rng(semente)
    ts = pd.date_range("2024-01-01", periods=24 * dias, freq="h")
    linhas = []
    for nome, _, _, peso in CIDADES[sub]:
        d = pd.DataFrame({"ts": ts, **{c: rng.uniform(0, 1000, len(ts)) for c in COLS_SOLAR}})
        linhas.append(d.assign(area=sub, cidade=nome, peso=peso))
    return pd.concat(linhas, ignore_index=True)


def _cols_dia(X, dia=DIA):
    cols = [c for c in features.colunas_modelo(X) if c in X.columns]
    return X[X.dia == dia][cols].reset_index(drop=True)


def _montar(bruto, fonte="prev_d1"):
    return features.montar(_carga(), None, solar=weather.solar_area(bruto), solar_fonte=fonte)


# --------------------------------------------------------------------------- de onde vêm os valores

def test_previsoes_so_vem_de_rodadas_com_antecedencia():
    for api, col in weather.VARS_SOLAR.items():
        if col.endswith(("_prev_d1", "_prev_d2")):
            # previsão: sempre previous_dayN com N >= 1, nunca previous_day0 nem a variável sem sufixo
            assert re.search(r"_previous_day[1-7]$", api), api
            assert not api.endswith("previous_day0")
        else:
            assert col.endswith("_obs") and "previous" not in api  # só oráculo e D-2 usam a rodada recente
    # os dois tipos de variável nas duas famílias (radiação e nuvens), e nada mais
    assert sorted(c.split("_")[0] for c in COLS_SOLAR) == ["ghi"] * 3 + ["nuv"] * 3


def _payload_falso(cidades):
    ts = [f"2024-02-10T{h:02d}:00" for h in range(24)]
    return [{"hourly": {"time": ts, **{api: [float(i)] * 24 for api in weather.VARS_SOLAR}}}
            for i, _ in enumerate(cidades)]


def test_download_pede_so_as_variaveis_certas_e_usa_cache(tmp_path, monkeypatch):
    pedidos = []

    def falso(params, retries=5):
        pedidos.append(params)
        sub = next(s for s, c in CIDADES.items() if params["latitude"] == ",".join(str(x[1]) for x in c))
        return _payload_falso(CIDADES[sub])

    monkeypatch.setattr(weather, "_get", falso)
    monkeypatch.setattr(weather.time, "sleep", lambda s: None)
    arquivos = weather.baixar_solar_ano(2024, tmp_path, pausa=0)
    assert len(pedidos) == len(CIDADES) == len(arquivos)
    for p in pedidos:
        pedido = p["hourly"].split(",")
        assert pedido == list(weather.VARS_SOLAR)
        assert not any(v.endswith("previous_day0") for v in pedido)
        assert p["timezone"] == "America/Sao_Paulo"
    # segunda chamada: tudo em cache, nenhuma requisição
    weather.baixar_solar_ano(2024, tmp_path, pausa=0)
    assert len(pedidos) == len(CIDADES)
    # retomada: apagar um arquivo baixa só aquele subsistema
    arquivos[1].unlink()
    weather.baixar_solar_ano(2024, tmp_path, pausa=0)
    assert len(pedidos) == len(CIDADES) + 1
    assert all(p.exists() for p in arquivos)
    assert not list(tmp_path.glob("*.tmp"))
    df = pd.read_parquet(arquivos[0])
    assert set(COLS_SOLAR) <= set(df.columns) and {"area", "cidade", "peso", "ts"} <= set(df.columns)


def test_espera_respeita_limites_de_taxa():
    assert weather.espera_s("Minutely API request limit exceeded. Please try again in one minute.", 0) == 65
    assert weather.espera_s("Hourly API request limit exceeded. Please try again in the next hour.", 0) > 3600
    with pytest.raises(RuntimeError, match="diário"):
        weather.espera_s("Daily API request limit exceeded. Please try again tomorrow.", 0)
    with pytest.raises(RuntimeError, match="por hora"):  # não fica esperando horas sem fim
        weather.espera_s("Hourly API request limit exceeded.", 2)
    assert weather.espera_s("Connection reset", 1) == 60


# --------------------------------------------------------------------------- agregação e alinhamento

def test_media_ponderada_por_populacao():
    ts = pd.date_range("2024-02-10", periods=6, freq="h")
    base = {c: 0.0 for c in COLS_SOLAR}
    a = pd.DataFrame({"ts": ts, **base, "nuv_prev_d1": 100.0}).assign(area="S", peso=3.0)
    b = pd.DataFrame({"ts": ts, **base, "nuv_prev_d1": 0.0}).assign(area="S", peso=1.0)
    s = weather.solar_area(pd.concat([a, b]))
    assert s.nuv_prev_d1.tolist() == pytest.approx([75.0] * 6)


def test_hora_de_carga_usa_o_carimbo_seguinte_sem_cruzar_a_meia_noite():
    # a radiação do carimbo T é a média da hora anterior a T; a hora de carga h = [h, h+1) usa o carimbo h+1
    ts = pd.date_range("2024-02-10", periods=72, freq="h")
    bruto = pd.DataFrame({"ts": ts, **{c: np.arange(72.0) for c in COLS_SOLAR}}).assign(
        area="S", peso=1.0)
    s = weather.solar_area(bruto).set_index("ts")
    t = pd.Timestamp
    for c in [c for c in COLS_SOLAR if c.startswith("ghi_")]:
        assert s.at[t("2024-02-10 05:00"), c] == 6.0       # carimbo 06:00
        assert s.at[t("2024-02-10 22:00"), c] == 23.0      # carimbo 23:00
        assert pd.isna(s[c].get(t("2024-02-10 23:00")))    # carimbo 00:00 de D+1 nunca é usado
        assert s.at[t("2024-02-11 00:00"), c] == 25.0      # carimbo 01:00 de D+1 -> hora 0 de D+1
    for c in [c for c in COLS_SOLAR if c.startswith("nuv_")]:  # nuvens são instantâneas: sem deslocamento
        assert s.at[t("2024-02-10 05:00"), c] == 5.0
        assert s.at[t("2024-02-10 23:00"), c] == 23.0


# --------------------------------------------------------------------------- sem vazamento do dia D

def test_irradiancia_observada_de_d_e_d_menos_1_nao_entra_na_previsao():
    bruto = _bruto()
    ref = _cols_dia(_montar(bruto))
    alterado = bruto.copy()
    dias = alterado.ts.dt.normalize()
    m = dias.isin([DIA, DIA - pd.Timedelta(days=1)])
    alterado.loc[m, ["ghi_obs", "nuv_obs"]] *= 7  # a rodada mais recente de D e D-1 não pode aparecer
    pd.testing.assert_frame_equal(ref, _cols_dia(_montar(alterado)))


def test_previsao_de_outros_dias_nao_muda_as_features_de_d():
    bruto = _bruto()
    ref = _cols_dia(_montar(bruto))
    alterado = bruto.copy()
    outros = alterado.ts.dt.normalize() != DIA
    alterado.loc[outros, ["ghi_prev_d1", "nuv_prev_d1", "ghi_prev_d2", "nuv_prev_d2"]] *= 7
    pd.testing.assert_frame_equal(ref, _cols_dia(_montar(alterado)))


def test_carimbo_de_meia_noite_do_dia_seguinte_nunca_entra():
    # previous_day1 do carimbo 00:00 de D+1 vem de uma rodada emitida em D: não pode alimentar o dia D
    bruto = _bruto()
    ref = _cols_dia(_montar(bruto))
    alterado = bruto.copy()
    alterado.loc[alterado.ts == DIA + pd.Timedelta(days=1), COLS_SOLAR] = 1e6
    pd.testing.assert_frame_equal(ref, _cols_dia(_montar(alterado)))


def test_o_teste_de_vazamento_nao_e_vacuo():
    bruto = _bruto()
    ref = _cols_dia(_montar(bruto))
    # a previsão de D tem de mudar as features de D ...
    alterado = bruto.copy()
    alterado.loc[alterado.ts.dt.normalize() == DIA, "ghi_prev_d1"] *= 2
    novo = _cols_dia(_montar(alterado))
    assert not np.allclose(ref.ghi.dropna(), novo.ghi.dropna())
    assert not np.allclose(ref.ghi_media_dia, novo.ghi_media_dia)
    # ... e a irradiância observada de D-2 também (é o passado conhecido na véspera)
    alterado = bruto.copy()
    alterado.loc[alterado.ts.dt.normalize() == DIA - pd.Timedelta(days=2), "ghi_obs"] *= 2
    novo = _cols_dia(_montar(alterado))
    assert not np.allclose(ref.ghi_lag2.dropna(), novo.ghi_lag2.dropna())
    # a fonte estrita usa previous_day2; o oráculo, a rodada recente do próprio D
    alterado = bruto.copy()
    alterado.loc[alterado.ts.dt.normalize() == DIA, "ghi_prev_d2"] *= 2
    assert not np.allclose(_cols_dia(_montar(bruto, "prev_d2")).ghi.dropna(),
                           _cols_dia(_montar(alterado, "prev_d2")).ghi.dropna())
    alterado = bruto.copy()
    alterado.loc[alterado.ts.dt.normalize() == DIA, "ghi_obs"] *= 2
    assert not np.allclose(_cols_dia(_montar(bruto, "obs")).ghi.dropna(),
                           _cols_dia(_montar(alterado, "obs")).ghi.dropna())


def test_fonte_desconhecida_e_recusada():
    with pytest.raises(ValueError):
        features.montar(_carga(), None, solar=weather.solar_area(_bruto()), solar_fonte="prev_d0")


def test_ghi_lag2_e_a_irradiancia_observada_de_dois_dias_antes_na_mesma_hora():
    s = weather.solar_area(_bruto())
    X = features.montar(_carga(), None, solar=s)
    r = X[(X.dia == DIA) & (X.hora == 12)].iloc[0]
    esperado = s[s.ts == DIA - pd.Timedelta(days=2) + pd.Timedelta(hours=12)].ghi_obs.iloc[0]
    assert r.ghi_lag2 == pytest.approx(esperado)
    assert r.ghi_delta == pytest.approx(r.ghi - esperado)


def test_sem_solar_a_matriz_e_a_mesma_de_antes():
    c = _carga()
    antes = features.montar(c, None, hora_corte_d1=10)
    depois = features.montar(c, None, hora_corte_d1=10, solar=None)
    pd.testing.assert_frame_equal(antes, depois)
    assert not {"ghi", "nuv", "ghi_lag2"} & set(antes.columns)


# --------------------------------------------------------------------------- variantes do backtest

def _carregar_backtest():
    spec = importlib.util.spec_from_file_location("backtest_script", ROOT / "scripts" / "backtest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_variantes_do_backtest():
    bt = _carregar_backtest()
    carga, solar = _carga(), weather.solar_area(_bruto())
    base = bt.matriz(carga, None, solar, bt.VARIANTES["modelo"])
    assert not {"ghi", "nuv"} & set(base.columns)
    irr = bt.matriz(carga, None, solar, bt.VARIANTES["modelo_irr"])
    assert {"ghi", "nuv", "ghi_lag2", "ghi_delta", "ghi_media_dia", "nuv_media_dia"} <= set(irr.columns)
    # as colunas antigas são idênticas: a irradiância só acrescenta
    pd.testing.assert_frame_equal(base, irr[base.columns])
    # o controle embaralhado traz as mesmas colunas, com a irradiância de outro dia
    emb = bt.matriz(carga, None, solar, bt.VARIANTES["modelo_irr_embaralhado"])
    assert list(emb.columns) == list(irr.columns)
    assert not np.allclose(emb.ghi.fillna(-1), irr.ghi.fillna(-1))
    # irradiância de 37 dias antes: o dia 2024-02-20 vê a de 2024-01-14
    antes = pd.Timestamp("2024-02-20 12:00") - pd.Timedelta(days=bt.DESLOCAMENTO_EMBARALHADO)
    esperado = solar[solar.ts == antes].ghi_prev_d1.iloc[0]
    assert emb[(emb.ts == "2024-02-20 12:00")].ghi.iloc[0] == pytest.approx(esperado)
    # sem irradiância baixada, as variantes com ela são recusadas com mensagem clara
    with pytest.raises(SystemExit):
        bt.matriz(carga, None, None, bt.VARIANTES["modelo_irr"])
