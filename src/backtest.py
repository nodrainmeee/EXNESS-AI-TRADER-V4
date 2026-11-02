"""Backtest de la stratégie (mêmes règles que le robot).

Utilisation (MT5 ouvert, compte démo) :
    python src/backtest.py --symbol EURUSD --tf M15 --bars 30000 --optimize
Ou avec un CSV (colonnes : time,open,high,low,close[,spread_price]) :
    python src/backtest.py --csv data.csv --spread 0.00012

Hypothèses prudentes : entrée à l'ouverture de la bougie suivante, spread payé,
si SL et TP sont touchés dans la même bougie -> on compte le SL (pire cas).
Résultats en multiples de R (1R = risque d'un trade, ex. 1 % du capital).
"""
import argparse
import itertools
import sys

import numpy as np
import pandas as pd

from strategy import DEFAULT_PARAMS, compute_base, make_signal, min_bars

MAX_BARS_IN_TRADE = 96


def run_backtest(df, p=None, ind=None):
    """ind : indicateurs déjà calculés (compute_base) pour accélérer la recherche."""
    p = dict(DEFAULT_PARAMS, **(p or {}))
    if ind is None:
        ind = compute_base(df, p)
    sig = make_signal(ind, p)
    o, h, l, c = (ind[k].values for k in ("open", "high", "low", "close"))
    sp = ind["spread_price"].values if "spread_price" in ind else np.zeros(len(ind))
    atr = ind["atr"].values
    hours = ((ind["time"].values // 3600) % 24) if "time" in ind else None
    n = len(ind)
    rr, mult = p["rr"], p["atr_sl_mult"]
    results = []
    i = min_bars(p)
    while i < n - 2:
        d = sig[i]
        if d == 0 or not np.isfinite(atr[i]) or atr[i] <= 0:
            i += 1
            continue
        e = i + 1
        if hours is not None and not (p["hour_start"] <= hours[e] < p["hour_end"]):
            i += 1
            continue
        sl_dist = mult * atr[i]
        entry = o[e] + (sp[e] if d == 1 else 0.0)          # BUY paie l'ask
        sl = entry - d * sl_dist
        tp = entry + d * rr * sl_dist
        r_val, exit_bar = None, None
        last = min(n - 1, e + MAX_BARS_IN_TRADE)
        for j in range(e, last + 1):
            if d == 1:
                hit_sl, hit_tp = l[j] <= sl, h[j] >= tp
            else:
                hit_sl, hit_tp = h[j] + sp[j] >= sl, l[j] + sp[j] <= tp
            if hit_sl:                                       # pire cas en priorité
                r_val, exit_bar = -1.0, j
                break
            if hit_tp:
                r_val, exit_bar = rr, j
                break
        if r_val is None:                                    # sortie au temps
            exit_bar = last
            px = c[last] if d == 1 else c[last] + sp[last]
            r_val = d * (px - entry) / sl_dist
        results.append((e, d, r_val))
        i = exit_bar + 1
    return pd.DataFrame(results, columns=["idx", "dir", "R"])


def metrics(trades):
    if trades.empty:
        return {"trades": 0, "win_rate": 0, "expectancy_R": 0, "profit_factor": 0, "total_R": 0, "max_dd_R": 0}
    r = trades["R"].values
    wins, losses = r[r > 0].sum(), -r[r < 0].sum()
    curve = np.cumsum(r)
    dd = (np.maximum.accumulate(curve) - curve).max()
    return {
        "trades": len(r),
        "win_rate": round(float((r > 0).mean()) * 100, 1),
        "expectancy_R": round(float(r.mean()), 3),
        "profit_factor": round(float(wins / losses), 2) if losses > 0 else float("inf"),
        "total_R": round(float(r.sum()), 1),
        "max_dd_R": round(float(dd), 1),
    }


def optimize(df, split=0.7):
    """Cherche les meilleurs réglages sur 70 % des données, puis les vérifie sur les 30 % restants
    jamais vus. Si le résultat s'effondre sur la partie test : sur-optimisation, ne pas s'y fier."""
    cut = int(len(df) * split)
    train, test = df.iloc[:cut].reset_index(drop=True), df.iloc[cut:].reset_index(drop=True)
    grid = itertools.product([1.0, 1.5, 2.0], [1.0, 1.5, 2.0, 2.5], [15, 20, 25], [40, 45, 50])
    best, best_m = None, None
    for mult, rr, adx, rb in grid:
        p = {"atr_sl_mult": mult, "rr": rr, "adx_min": adx, "rsi_buy": rb, "rsi_sell": 100 - rb}
        m = metrics(run_backtest(train, p))
        if m["trades"] < 30:
            continue
        if best_m is None or m["expectancy_R"] > best_m["expectancy_R"]:
            best, best_m = p, m
    if best is None:
        return None, None, None
    return best, best_m, metrics(run_backtest(test, best))


def load_csv(path, spread):
    df = pd.read_csv(path)
    if "spread_price" not in df:
        df["spread_price"] = spread
    return df


def load_mt5(symbol, tf_name, bars):
    import MetaTrader5 as mt5
    from trader import resolve_symbol, TF
    if not mt5.initialize():
        sys.exit(f"MT5 non connecté : {mt5.last_error()}")
    real = resolve_symbol(symbol)
    if not real:
        sys.exit(f"Symbole {symbol} introuvable dans MT5.")
    mt5.symbol_select(real, True)
    rates = mt5.copy_rates_from_pos(real, TF[tf_name], 1, bars)
    info = mt5.symbol_info(real)
    mt5.shutdown()
    if rates is None or len(rates) < 1000:
        sys.exit("Historique insuffisant. Dans MT5 : Outils > Options > Graphiques > "
                 "'Max de barres dans le graphique' = Illimité, puis ouvrez le graphique et défilez vers la gauche.")
    df = pd.DataFrame(rates)
    df["spread_price"] = df["spread"] * info.point
    return df


def show(title, m):
    print(f"  {title:<28} trades={m['trades']:<5} gagnants={m['win_rate']}%  "
          f"espérance={m['expectancy_R']}R  PF={m['profit_factor']}  total={m['total_R']}R  "
          f"drawdown max={m['max_dd_R']}R")


def verdict(m):
    if m["trades"] < 100:
        return "Pas assez de trades pour conclure."
    if m["expectancy_R"] > 0.10 and m["profit_factor"] > 1.2:
        return "Résultat prometteur sur la partie test — à confirmer en démo avant toute décision."
    if m["expectancy_R"] > 0:
        return "Gain marginal : probablement mangé par les coûts réels (slippage, commissions)."
    return "Stratégie PERDANTE sur la partie test : ne pas l'activer telle quelle."


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--tf", default="M15")
    ap.add_argument("--bars", type=int, default=30000)
    ap.add_argument("--csv")
    ap.add_argument("--spread", type=float, default=0.0)
    ap.add_argument("--optimize", action="store_true")
    a = ap.parse_args(argv)

    data = load_csv(a.csv, a.spread) if a.csv else load_mt5(a.symbol, a.tf, a.bars)
    print(f"\n=== {a.symbol if not a.csv else a.csv} | {a.tf} | {len(data)} bougies ===")
    show("Réglages par défaut", metrics(run_backtest(data)))
    if a.optimize:
        best, m_tr, m_te = optimize(data)
        if best is None:
            print("  Optimisation impossible (trop peu de trades).")
        else:
            print(f"  Meilleurs réglages (entraînement) : {best}")
            show("Entraînement (70 %)", m_tr)
            show("TEST jamais vu (30 %)", m_te)
            print("  ->", verdict(m_te))


if __name__ == "__main__":
    main()
