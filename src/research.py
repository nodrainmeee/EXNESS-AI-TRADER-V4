"""RECHERCHE DE STRATÉGIE (V3) : teste 3 stratégies x 4 timeframes x vos marchés avec validation
glissante (walk-forward) et classe les résultats HONNÊTEMENT.

Principe : à chaque étape, on choisit les meilleurs réglages sur le PASSÉ uniquement, puis on les
applique sur la période SUIVANTE jamais vue. On ne juge que ces résultats "hors échantillon".
Coûts : spread x1.5 (pour couvrir le slippage). Aucun ordre n'est envoyé.
"""
import itertools
import json
import os
import sys

import numpy as np
import pandas as pd

from backtest import run_backtest
from strategy import DEFAULT_PARAMS, STRATEGIES, compute_base

GRIDS = {
    "pullback": dict(atr_sl_mult=[1.5, 2.0], rr=[1.5, 2.0, 3.0], adx_min=[20, 25], rsi_buy=[40, 45]),
    "breakout": dict(donchian_n=[20, 40, 60], atr_sl_mult=[1.5, 2.0], rr=[1.5, 2.0, 3.0], adx_min=[15, 20, 25]),
    "meanrev": dict(bb_k=[2.0, 2.5], rsi_low=[25, 30], adx_max=[20, 25, 30], atr_sl_mult=[1.5, 2.0], rr=[1.0, 1.5]),
}
HOURS = [(0, 24), (7, 20)]
BARS = {"M15": 50000, "M30": 30000, "H1": 20000, "H4": 8000}
FOLDS, MIN_TRAIN, MIN_OOS = 5, 30, 100
COST_MULT = 1.5


def make_combos(strategy):
    g = GRIDS[strategy]
    keys = list(g)
    out = []
    for vals in itertools.product(*[g[k] for k in keys]):
        c = dict(zip(keys, vals))
        if strategy == "pullback":
            c["rsi_sell"] = 100 - c["rsi_buy"]
        if strategy == "meanrev":
            c["rsi_high"] = 100 - c["rsi_low"]
        for hs, he in HOURS:
            out.append(dict(c, hour_start=hs, hour_end=he))
    return out


def _pf(r):
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else (99.0 if w > 0 else 0.0)


def evaluate(df, strategy, seed=0):
    """Walk-forward d'une stratégie sur un jeu de données. Retourne un dict de résultats."""
    p0 = dict(DEFAULT_PARAMS, strategy=strategy)
    ind = compute_base(df, p0)
    runs = []
    for c in make_combos(strategy):
        tr = run_backtest(df, dict(p0, **c), ind=ind)
        runs.append((c, tr["idx"].values, tr["R"].values))
    n = len(df)
    start, step = int(n * 0.5), int(n * 0.1)
    oos, fold_sums, last = [], [], None
    for k in range(FOLDS):
        a = start + k * step
        b = a + step if k < FOLDS - 1 else n
        best = None
        for ci, (c, idx, r) in enumerate(runs):
            rt = r[idx < a]
            if len(rt) < MIN_TRAIN or _pf(rt) <= 1.0:
                continue
            m = rt.mean()
            if best is None or m > best[0]:
                best = (m, ci)
        if best is None:
            fold_sums.append(0.0)
            continue
        c, idx, r = runs[best[1]]
        te = r[(idx >= a) & (idx < b)]
        oos.append(te)
        fold_sums.append(float(te.sum()))
        last = c
    R = np.concatenate(oos) if oos else np.array([])
    res = {"strategy": strategy, "oos_trades": int(len(R)), "expectancy": 0.0, "pf": 0.0,
           "total_R": 0.0, "pos_folds": int(sum(1 for x in fold_sums if x > 0)), "p_value": 1.0,
           "params": last}
    if len(R):
        res.update(expectancy=float(R.mean()), pf=_pf(R), total_R=float(R.sum()))
        rng = np.random.default_rng(seed)
        means = rng.choice(R, size=(2000, len(R))).mean(axis=1)
        res["p_value"] = float((means <= 0).mean())     # proba que l'espérance réelle soit <= 0
    res["verdict"] = verdict(res)
    return res


def verdict(r):
    if r["oos_trades"] < MIN_OOS:
        return "insuffisant"
    if r["expectancy"] > 0.10 and r["pf"] > 1.2 and r["p_value"] < 0.05 and r["pos_folds"] >= 4:
        return "PROMETTEUSE"
    if r["expectancy"] > 0 and r["pf"] > 1.05:
        return "marginale"
    return "rejetee"


RANK = {"PROMETTEUSE": 0, "marginale": 1, "insuffisant": 2, "rejetee": 3}


def load_all(symbols):
    import MetaTrader5 as mt5
    from trader import resolve_symbol, TF
    if not mt5.initialize():
        sys.exit(f"MT5 non connecté : {mt5.last_error()}")
    data = {}
    for base in symbols:
        real = resolve_symbol(base)
        if not real:
            print(f"[{base}] introuvable, ignoré.")
            continue
        mt5.symbol_select(real, True)
        info, tick = mt5.symbol_info(real), mt5.symbol_info_tick(real)
        for tf, bars in BARS.items():
            rates = mt5.copy_rates_from_pos(real, TF[tf], 1, bars)
            if rates is None or len(rates) < 2000:
                print(f"[{base} {tf}] historique insuffisant ({0 if rates is None else len(rates)} bougies), ignoré.")
                continue
            df = pd.DataFrame(rates)
            sp = df["spread"] * info.point
            if sp.median() == 0 and tick:
                sp = pd.Series(tick.ask - tick.bid, index=df.index)
            df["spread_price"] = sp * COST_MULT
            data[(base, tf)] = df
    mt5.shutdown()
    return data


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from trader import load_config, CFG_PATH, BASE_DIR
    cfg = load_config()
    data = load_all(cfg["symbols"])
    rows = []
    print(f"\nWalk-forward : {FOLDS} périodes de test jamais vues par réglage. Patience (quelques minutes)...\n")
    for (sym, tf), df in data.items():
        for st in STRATEGIES:
            r = evaluate(df, st)
            r.update(symbol=sym, tf=tf, bars=len(df))
            rows.append(r)
            print(f"{sym:7} {tf:3} {st:9} OOS trades={r['oos_trades']:<4} esp={r['expectancy']:+.3f}R "
                  f"PF={r['pf']:.2f} périodes+={r['pos_folds']}/{FOLDS} p={r['p_value']:.3f}  -> {r['verdict']}")
    if not rows:
        sys.exit("Aucune donnée exploitable.")
    rows.sort(key=lambda r: (RANK[r["verdict"]], -r["expectancy"]))
    pd.DataFrame([{k: v for k, v in r.items() if k != "params"} for r in rows]).to_csv(
        os.path.join(BASE_DIR, "logs", "resultats_recherche.csv"), index=False, sep=";")
    good = [r for r in rows if r["verdict"] in ("PROMETTEUSE", "marginale")]
    print("\n=== CONCLUSION ===")
    if not good:
        print("AUCUNE variante ne tient au test hors échantillon. Ne lancez PAS le trading auto.")
        print("C'est un résultat normal : la plupart des règles simples ne battent pas les coûts.")
        return
    new = dict(cfg)
    new.setdefault("profiles", {})
    chosen = {}
    for r in good:
        if r["symbol"] not in chosen:
            chosen[r["symbol"]] = r
    for sym, r in chosen.items():
        prof = {"timeframe": r["tf"], "strategy": r["strategy"], **r["params"],
                "session_start_hour": r["params"]["hour_start"], "session_end_hour": r["params"]["hour_end"]}
        new["profiles"][sym] = prof
        print(f"{sym}: {r['strategy']} en {r['tf']} -> {r['verdict']} (esp. {r['expectancy']:+.3f}R, "
              f"PF {r['pf']:.2f}, {r['oos_trades']} trades hors échantillon)")
    new["symbols"] = list(chosen)
    out = os.path.join(BASE_DIR, "config_recommandee.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(new, f, indent=2, ensure_ascii=False)
    print(f"\nRéglages écrits dans config_recommandee.json (copiez-les dans config.json si vous êtes d'accord).")
    print("ATTENTION : 'marginale' = probablement mangée par les coûts réels. Validez en démo pendant des semaines.")


if __name__ == "__main__":
    main()
