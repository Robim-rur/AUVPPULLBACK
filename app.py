import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

from ta.trend import EMAIndicator, ADXIndicator
from ta.momentum import StochasticOscillator

# =========================
# CONFIG
# =========================
st.set_page_config(page_title="Scanner Institucional V3", layout="wide")
st.title("🏦 Scanner Institucional V3 - Pullback Brasil")

# =========================
# UNIVERSO PERSONALIZADO
# =========================
tickers = [
    "ITUB4.SA","SBSP3.SA","BBDC4.SA","B3SA3.SA","ITSA4.SA",
    "WEGE3.SA","BPAC11.SA","ABEV3.SA","BBAS3.SA","PRIO3.SA",
    "PETR4.SA","RDOR3.SA","CMIG4.SA","BBSE3.SA","TIMS3.SA",
    "TOTS3.SA","PSSA3.SA","SAPR11.SA","SAPR4.SA","POMO4.SA"
]

# =========================
# DATA (ROBUSTO)
# =========================
def get_data(ticker, interval="1d", period="2y"):
    df = yf.download(ticker, interval=interval, period=period, progress=False)

    if df.empty:
        return df

    # Corrige MultiIndex
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df[["Open", "High", "Low", "Close", "Volume"]]
    df.dropna(inplace=True)

    return df

# =========================
# INDICADORES (ANTI-ERRO)
# =========================
def add_indicators(df):

    close = pd.Series(df["Close"].values.flatten(), index=df.index)
    high = pd.Series(df["High"].values.flatten(), index=df.index)
    low = pd.Series(df["Low"].values.flatten(), index=df.index)

    df["ema69"] = EMAIndicator(close, 69).ema_indicator()

    stoch = StochasticOscillator(high, low, close, 14, 3)
    df["k"] = stoch.stoch()
    df["d"] = stoch.stoch_signal()

    adx = ADXIndicator(high, low, close, 14)
    df["adx"] = adx.adx()
    df["di_plus"] = adx.adx_pos()
    df["di_minus"] = adx.adx_neg()

    df["vol_ma20"] = df["Volume"].rolling(20).mean()
    df["vol_ma50"] = df["Volume"].rolling(50).mean()

    return df

# =========================
# FILTROS
# =========================
def weekly_trend(ticker):
    dfw = get_data(ticker, interval="1wk")

    if dfw.empty or len(dfw) < 30:
        return False

    dfw["ema20"] = EMAIndicator(dfw["Close"], 20).ema_indicator()

    return dfw["Close"].iloc[-1] > dfw["ema20"].iloc[-1]


def liquidity_filter(df):
    return df["Volume"].iloc[-1] > 500000


def volume_strength(df):
    return df["vol_ma20"].iloc[-1] > df["vol_ma50"].iloc[-1]


def false_breakdown(df):
    if len(df) < 10:
        return False

    last = df.iloc[-1]
    prev_low = df["Low"].rolling(5).min().iloc[-2]

    return last["Close"] > prev_low


# =========================
# SETUP
# =========================
def pullback_signal(df):
    last = df.iloc[-1]

    return (
        last["Close"] > last["ema69"] and
        last["di_plus"] > last["di_minus"] and
        last["k"] > last["d"] and
        last["k"] < 50
    )

# =========================
# PROBABILIDADE
# =========================
def simulate(df):
    gains = 0
    losses = 0

    for i in range(100, len(df)-15):
        row = df.iloc[i]

        cond = (
            row["Close"] > row["ema69"] and
            row["di_plus"] > row["di_minus"] and
            row["k"] > row["d"] and
            row["k"] < 50
        )

        if cond:
            entry = row["Close"]
            future = df.iloc[i+1:i+15]

            for _, f in future.iterrows():
                if f["Close"] >= entry * 1.03:
                    gains += 1
                    break
                elif f["Close"] <= entry * 0.95:
                    losses += 1
                    break

    total = gains + losses
    if total == 0:
        return 0

    return round((gains / total) * 100, 2)

# =========================
# CLASSIFICAÇÃO
# =========================
def classify(df):
    last = df.iloc[-1]

    if last["Close"] < last["ema69"]:
        return "Virou Carteira"
    elif last["k"] < last["d"]:
        return "Aguardar"
    else:
        return "Trade"

# =========================
# SCANNER
# =========================
results = []
progress = st.progress(0)

for i, ticker in enumerate(tickers):
    try:
        df = get_data(ticker)

        if df.empty or len(df) < 150:
            continue

        df = add_indicators(df)

        weekly_ok = weekly_trend(ticker)
        liquidity = liquidity_filter(df)
        volume_ok = volume_strength(df)
        fake_break = false_breakdown(df)
        pullback = pullback_signal(df)
        prob = simulate(df)
        status = classify(df)

        last = df.iloc[-1]

        score = 0
        if pullback: score += 25
        if weekly_ok: score += 15
        if liquidity: score += 15
        if volume_ok: score += 15
        if fake_break: score += 10
        if last["adx"] > 20: score += 20

        results.append({
            "Ticker": ticker.replace(".SA",""),
            "Preço": round(last["Close"], 2),
            "Score": score,
            "Probabilidade +3%": prob,
            "ADX": round(last["adx"],1),
            "Liquidez OK": liquidity,
            "Volume OK": volume_ok,
            "Sem Falso Rompimento": fake_break,
            "Tendência Semanal": weekly_ok,
            "Status": status
        })

    except Exception as e:
        st.warning(f"Erro em {ticker}: {e}")

    progress.progress((i+1)/len(tickers))

df_res = pd.DataFrame(results)

# =========================
# OUTPUT
# =========================
if not df_res.empty:
    df_res = df_res.sort_values(by="Score", ascending=False)

    st.subheader("🏆 Ranking Institucional")
    st.dataframe(df_res, use_container_width=True)

    st.subheader("🔥 ENTRADAS PREMIUM")

    premium = df_res[
        (df_res["Score"] >= 75) &
        (df_res["Probabilidade +3%"] >= 55) &
        (df_res["Status"] == "Trade")
    ]

    st.dataframe(premium, use_container_width=True)

else:
    st.warning("Sem ativos qualificados.")

# =========================
# DETALHE
# =========================
st.subheader("📊 Raio-X do Ativo")

sel = st.selectbox("Escolha o ativo", [t.replace(".SA","") for t in tickers])

if sel:
    ticker_full = sel + ".SA"
    df = get_data(ticker_full)

    if not df.empty:
        df = add_indicators(df)

        st.line_chart(df[["Close","ema69"]])
        st.line_chart(df[["k","d"]])
        st.line_chart(df[["adx"]])
        st.bar_chart(df["Volume"].tail(50))

        st.dataframe(df.tail(10))
    else:
        st.warning("Sem dados para este ativo.")
