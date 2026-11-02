"""Logique de signal PURE (sans MetaTrader), partagée par le robot, le backtest et la recherche.
Trois familles de stratégies (paramètre 'strategy') :
  pullback : repli dans le sens de la tendance (EMA20/50/200 + RSI + ADX)
  breakout : cassure d'un canal Donchian dans le sens de la tendance (EMA200) avec ADX
  meanrev  : retour à la moyenne (Bollinger + RSI extrême) quand le marché est sans tendance (ADX bas)
Signaux calculés uniquement sur bougies CLÔTURÉES. SL = atr_sl_mult x ATR ; TP = rr x SL.
"""
import numpy as np
import pandas as pd

DEFAULT_PARAMS = {
    "strategy": "pullback",
    "ema_fast": 20, "ema_slow": 50, "ema_trend": 200,
    "rsi_period": 14, "rsi_buy": 45, "rsi_sell": 55, "rsi_low": 30, "rsi_high": 70,
    "atr_period": 14, "adx_period": 14, "adx_min": 20, "adx_max": 25,
    "donchian_n": 40, "bb_period": 20, "bb_k": 2.0,
    "atr_sl_mult": 1.5, "rr": 1.5,
    "hour_start": 0, "hour_end": 24,      # utilisé par le backtest ; en live : session_start/end_hour
}
STRATEGIES = ("pullback", "breakout", "meanrev")


def params_from_cfg(cfg):
    p = dict(DEFAULT_PARAMS)
    for k in p:
        if k in cfg:
            p[k] = cfg[k]
    return p


def min_bars(p):
    return int(p["ema_trend"]) + 60


def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def _rsi(close, n):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / (dn + 1e-12))


def _atr(df, n):
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def _adx(df, n):
    up = df["high"].diff()
    dn = -df["low"].diff()
    plus = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
    minus = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
    atr = _atr(df, n).replace(0, np.nan)
    pdi = 100 * plus.ewm(alpha=1 / n, adjust=False).mean() / atr
    mdi = 100 * minus.ewm(alpha=1 / n, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean().fillna(0)


def compute_base(df, p=None):
    """Indicateurs qui ne dépendent pas des seuils (calculés une seule fois pour la recherche)."""
    p = p or DEFAULT_PARAMS
    out = df.copy()
    c = out["close"]
    out["ema_fast"] = _ema(c, p["ema_fast"])
    out["ema_slow"] = _ema(c, p["ema_slow"])
    out["ema_trend"] = _ema(c, p["ema_trend"])
    out["rsi"] = _rsi(c, p["rsi_period"])
    out["atr"] = _atr(out, p["atr_period"])
    out["adx"] = _adx(out, p["adx_period"])
    out["bb_mid"] = c.rolling(int(p["bb_period"])).mean()
    out["bb_std"] = c.rolling(int(p["bb_period"])).std(ddof=0)
    return out


def make_signal(ind, p):
    """Retourne un tableau numpy : 1 = BUY, -1 = SELL, 0 = rien (sur la bougie clôturée)."""
    c, s = ind["close"], p["strategy"]
    adx, rsi = ind["adx"], ind["rsi"]
    if s == "pullback":
        up = (ind["ema_fast"] > ind["ema_slow"]) & (ind["ema_slow"] > ind["ema_trend"]) & (c > ind["ema_slow"])
        dn = (ind["ema_fast"] < ind["ema_slow"]) & (ind["ema_slow"] < ind["ema_trend"]) & (c < ind["ema_slow"])
        r1 = rsi.shift(1)
        long_ = up & (r1 < p["rsi_buy"]) & (rsi >= p["rsi_buy"]) & (adx >= p["adx_min"])
        short_ = dn & (r1 > p["rsi_sell"]) & (rsi <= p["rsi_sell"]) & (adx >= p["adx_min"])
    elif s == "breakout":
        n = int(p["donchian_n"])
        hi = ind["high"].rolling(n).max().shift(1)
        lo = ind["low"].rolling(n).min().shift(1)
        long_ = (c > hi) & (c.shift(1) <= hi.shift(1)) & (c > ind["ema_trend"]) & (adx >= p["adx_min"])
        short_ = (c < lo) & (c.shift(1) >= lo.shift(1)) & (c < ind["ema_trend"]) & (adx >= p["adx_min"])
    elif s == "meanrev":
        k = p["bb_k"]
        lower = ind["bb_mid"] - k * ind["bb_std"]
        upper = ind["bb_mid"] + k * ind["bb_std"]
        long_ = (c < lower) & (c.shift(1) >= lower.shift(1)) & (rsi <= p["rsi_low"]) & (adx <= p["adx_max"])
        short_ = (c > upper) & (c.shift(1) <= upper.shift(1)) & (rsi >= p["rsi_high"]) & (adx <= p["adx_max"])
    else:
        raise ValueError(f"Stratégie inconnue : {s}")
    sig = np.zeros(len(ind), dtype=int)
    sig[long_.fillna(False).values] = 1
    sig[short_.fillna(False).values] = -1
    sig[: int(p["ema_trend"])] = 0                     # chauffe des EMA
    return sig


def compute_indicators(df, p=None):
    p = p or DEFAULT_PARAMS
    out = compute_base(df, p)
    out["signal"] = make_signal(out, p)
    return out
