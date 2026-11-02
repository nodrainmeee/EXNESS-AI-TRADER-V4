"""Exécution MT5 avec garde-fous. COMPTE DÉMO UNIQUEMENT (vérifié avant chaque ordre)."""
import csv
import json
import math
import os
import sys
from datetime import datetime

import MetaTrader5 as mt5
import pandas as pd

from strategy import compute_indicators, params_from_cfg, min_bars

if getattr(sys, "frozen", False):          # version .exe : dossier de l'exécutable
    BASE_DIR = os.path.dirname(sys.executable)
else:                                       # version Python : dossier du projet
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG_PATH = os.path.join(BASE_DIR, "config.json")
STOP_FILE = os.path.join(BASE_DIR, "STOP.txt")      # créer ce fichier = arrêt immédiat du trading auto
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

TF = {"M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
      "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4}


# ---------- utilitaires ----------
def load_config():
    with open(CFG_PATH, encoding="utf-8") as f:
        return json.load(f)


def symbol_cfg(cfg, name):
    """Réglages d'un marché = config de base + son profil (issu de RECHERCHE.bat) s'il existe."""
    return {**cfg, **cfg.get("profiles", {}).get(name, {})}


def journal(event, symbol="", detail=""):
    os.makedirs(LOG_DIR, exist_ok=True)
    path = os.path.join(LOG_DIR, "journal.csv")
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        if new:
            w.writerow(["heure_pc", "evenement", "symbole", "detail"])
        w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), event, symbol, detail])


def is_demo():
    info = mt5.account_info()
    return info is not None and info.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO


def resolve_symbol(base):
    """Nom exact, sinon variante courte avec suffixe broker (EURUSDm, EURUSDz...)."""
    symbols = mt5.symbols_get()
    if not symbols:
        return None
    names = [s.name for s in symbols]
    if base in names:
        return base
    cand = [n for n in names if n.upper().startswith(base.upper()) and len(n) <= len(base) + 3]
    return sorted(cand, key=lambda n: (len(n), n))[0] if cand else None


TF_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400}


def get_rates(symbol, tf_name, count=700, include_forming=False):
    """Par défaut : bougies clôturées uniquement. include_forming=True ajoute la bougie en cours (dernière ligne)."""
    rates = mt5.copy_rates_from_pos(symbol, TF[tf_name], 0 if include_forming else 1, count)
    if rates is None or len(rates) < 300:
        raise RuntimeError(f"Historique insuffisant ({mt5.last_error()})")
    return pd.DataFrame(rates)


def my_positions(magic, symbol=None):
    pos = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    return [p for p in (pos or []) if p.magic == magic]


def today_stats(magic, server_ts):
    """(résultat réalisé du jour, nombre de trades ouverts aujourd'hui) pour ce robot."""
    day_start = server_ts - server_ts % 86400
    deals = mt5.history_deals_get(datetime.utcfromtimestamp(day_start - 86400),
                                  datetime.utcfromtimestamp(server_ts + 86400)) or []
    mine = [d for d in deals if d.magic == magic and d.time >= day_start]
    realized = sum(d.profit + d.commission + d.swap + getattr(d, "fee", 0.0) for d in mine)
    opened = sum(1 for d in mine if d.entry == mt5.DEAL_ENTRY_IN)
    exits = [d for d in mine if d.entry == mt5.DEAL_ENTRY_OUT]
    wins = sum(1 for d in exits if d.profit + d.commission + d.swap + getattr(d, "fee", 0.0) > 0)
    win_rate = (100.0 * wins / len(exits)) if exits else 0.0
    return realized, opened, win_rate


# ---------- calcul du lot (risque fixe en % de l'equity) ----------
def calc_lot(symbol, direction, entry, sl, risk_money):
    info = mt5.symbol_info(symbol)
    otype = mt5.ORDER_TYPE_BUY if direction == 1 else mt5.ORDER_TYPE_SELL
    loss = mt5.order_calc_profit(otype, symbol, 1.0, entry, sl)
    loss = abs(loss) if loss else 0.0
    if loss == 0 and info.trade_tick_size:
        loss = abs(entry - sl) / info.trade_tick_size * info.trade_tick_value
    if loss <= 0:
        return None, "perte par lot non calculable"
    lot = risk_money / loss
    step = info.volume_step or 0.01
    lot = math.floor(lot / step + 1e-9) * step
    if lot < info.volume_min:
        if loss * info.volume_min > risk_money:
            return None, (f"lot minimum dépasse le risque autorisé "
                          f"({loss * info.volume_min:.2f} > {risk_money:.2f})")
        lot = info.volume_min
    lot = min(lot, info.volume_max)
    decimals = max(0, -int(math.floor(math.log10(step)))) if step < 1 else 0
    return round(lot, decimals), None


def _filling(info):
    fm = info.filling_mode
    if fm & 1:
        return mt5.ORDER_FILLING_FOK
    if fm & 2:
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


# ---------- garde-fous ----------
def check_guards(cfg, symbol, acc, positions, realized, opened, server_ts, sl_dist, spread_price):
    if not is_demo():
        return False, "compte non DÉMO"
    term = mt5.terminal_info()
    if term is not None and not term.trade_allowed:
        return False, "bouton 'Algo Trading' désactivé dans MT5"
    hour = datetime.utcfromtimestamp(server_ts).hour
    if not (cfg["session_start_hour"] <= hour < cfg["session_end_hour"]):
        return False, f"hors session ({hour}h serveur)"
    if len([p for p in positions if p.symbol == symbol]) >= cfg["max_open_per_symbol"]:
        return False, "position déjà ouverte sur ce marché"
    if len(positions) >= cfg["max_total_open"]:
        return False, "nombre max de positions atteint"
    if opened >= cfg["max_trades_per_day"]:
        return False, "max de trades du jour atteint"
    floating = sum(p.profit for p in positions)
    if realized + floating <= -acc.balance * cfg["daily_loss_limit_percent"] / 100:
        return False, "limite de perte journalière atteinte"
    if spread_price > cfg["max_spread_sl_ratio"] * sl_dist:
        return False, f"spread trop large ({spread_price:.5f} > {cfg['max_spread_sl_ratio']:.0%} du SL)"
    return True, ""


# ---------- ordres ----------
def place_order(cfg, symbol, direction, sl_dist):
    if not is_demo():                                    # double verrou : jamais d'ordre hors démo
        return False, "REFUSÉ : compte non démo"
    info, tick, acc = mt5.symbol_info(symbol), mt5.symbol_info_tick(symbol), mt5.account_info()
    if not info or not tick or not acc:
        return False, "données de marché indisponibles"
    price = tick.ask if direction == 1 else tick.bid
    sl = round(price - direction * sl_dist, info.digits)
    tp = round(price + direction * cfg["rr"] * sl_dist, info.digits)
    min_dist = max(info.trade_stops_level, info.trade_freeze_level) * info.point
    if abs(price - sl) < min_dist * 1.1 or abs(tp - price) < min_dist * 1.1:
        return False, "SL/TP plus proches que la distance minimale du courtier"
    lot, err = calc_lot(symbol, direction, price, sl, acc.equity * cfg["risk_percent"] / 100)
    if err:
        return False, err
    req = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": lot,
        "type": mt5.ORDER_TYPE_BUY if direction == 1 else mt5.ORDER_TYPE_SELL,
        "price": price, "sl": sl, "tp": tp, "deviation": cfg["deviation_points"],
        "magic": cfg["magic"], "comment": "EXNESS_AI_V4",
        "type_time": mt5.ORDER_TIME_GTC, "type_filling": _filling(info),
    }
    margin = mt5.order_calc_margin(req["type"], symbol, lot, price)
    if margin is None or margin > acc.margin_free:
        return False, f"marge insuffisante (requise={margin}, libre={acc.margin_free})"
    chk = mt5.order_check(req)
    if chk is None or chk.retcode != 0:
        return False, f"order_check refusé : {getattr(chk, 'comment', mt5.last_error())}"
    res = mt5.order_send(req)
    if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
        return False, f"order_send refusé : {getattr(res, 'comment', mt5.last_error())}"
    side = "BUY" if direction == 1 else "SELL"
    return True, f"{side} {lot} lot @ {res.price} | SL {sl} | TP {tp} | ticket {res.order}"


def manage_breakeven(cfg):
    """Passe le SL au prix d'entrée quand le trade gagne breakeven_at_r x le risque initial."""
    out = []
    if not cfg.get("breakeven_at_r"):
        return out
    for p in my_positions(cfg["magic"]):
        tick = mt5.symbol_info_tick(p.symbol)
        info = mt5.symbol_info(p.symbol)
        if not tick or not info or p.sl == 0:
            continue
        buy = p.type == mt5.POSITION_TYPE_BUY
        risk = (p.price_open - p.sl) if buy else (p.sl - p.price_open)
        if risk <= 0:
            continue                                      # déjà à l'équilibre
        move = (tick.bid - p.price_open) if buy else (p.price_open - tick.ask)
        if move >= cfg["breakeven_at_r"] * risk:
            req = {"action": mt5.TRADE_ACTION_SLTP, "symbol": p.symbol, "position": p.ticket,
                   "sl": round(p.price_open, info.digits), "tp": p.tp, "magic": cfg["magic"]}
            res = mt5.order_send(req)
            if res is not None and res.retcode == mt5.TRADE_RETCODE_DONE:
                out.append(f"{p.symbol} #{p.ticket} : SL déplacé à l'équilibre")
    return out


def close_position(cfg, ticket):
    """Ferme uniquement une position du robot identifiée par son ticket."""
    found = [p for p in my_positions(cfg["magic"]) if p.ticket == int(ticket)]
    if not found:
        return False, "position introuvable ou non gérée par ce robot"
    p = found[0]
    tick, info = mt5.symbol_info_tick(p.symbol), mt5.symbol_info(p.symbol)
    if not tick or not info:
        return False, "cotations indisponibles"
    buy = p.type == mt5.POSITION_TYPE_BUY
    req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": p.symbol, "position": p.ticket,
           "volume": p.volume, "type": mt5.ORDER_TYPE_SELL if buy else mt5.ORDER_TYPE_BUY,
           "price": tick.bid if buy else tick.ask, "deviation": cfg["deviation_points"],
           "magic": cfg["magic"], "comment": "EXNESS_AI_V4 close",
           "type_time": mt5.ORDER_TIME_GTC, "type_filling": _filling(info)}
    check = mt5.order_check(req)
    if check is None or check.retcode != 0:
        return False, f"order_check refusé : {getattr(check, 'comment', mt5.last_error())}"
    result = mt5.order_send(req)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        return False, f"fermeture refusée : {getattr(result, 'comment', mt5.last_error())}"
    return True, f"{p.symbol} #{p.ticket} fermeture confirmée par MT5"


def close_all(cfg):
    """Ferme toutes les positions ouvertes PAR LE ROBOT (magic). Ne touche pas aux trades manuels."""
    out = []
    for p in my_positions(cfg["magic"]):
        tick, info = mt5.symbol_info_tick(p.symbol), mt5.symbol_info(p.symbol)
        buy = p.type == mt5.POSITION_TYPE_BUY
        req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": p.symbol, "position": p.ticket,
               "volume": p.volume, "type": mt5.ORDER_TYPE_SELL if buy else mt5.ORDER_TYPE_BUY,
               "price": tick.bid if buy else tick.ask, "deviation": cfg["deviation_points"],
               "magic": cfg["magic"], "comment": "EXNESS_AI_V4 close",
               "type_time": mt5.ORDER_TIME_GTC, "type_filling": _filling(info)}
        res = mt5.order_send(req)
        ok = res is not None and res.retcode == mt5.TRADE_RETCODE_DONE
        out.append(f"{p.symbol} #{p.ticket} : {'fermée' if ok else 'ÉCHEC ' + str(getattr(res, 'comment', ''))}")
    return out


# ---------- cycle principal ----------
def cycle(cfg, symbol_map, state, auto):
    """Cycle événementiel piloté par les ticks : le signal peut naître pendant la bougie M5."""
    events, rows = [], []
    acc = mt5.account_info()
    if acc is None or acc.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
        raise RuntimeError("Compte démo non confirmé — arrêt.")
    if auto and os.path.exists(STOP_FILE):
        auto = False
        events.append("STOP.txt détecté : trading automatique suspendu.")
    if auto:
        events += manage_breakeven(cfg)

    analyses, server_ts = [], None
    for req_name, sym in symbol_map.items():
        try:
            scfg = symbol_cfg(cfg, req_name)
            params = params_from_cfg(scfg)
            tick, info = mt5.symbol_info_tick(sym), mt5.symbol_info(sym)
            if tick is None or info is None:
                raise RuntimeError(f"tick ou spécifications indisponibles : {mt5.last_error()}")
            server_ts = max(server_ts or 0, int(tick.time))
            # Le tick MT5 est la donnée primaire. La bougie courante est recalculée à partir du flux.
            df = get_rates(sym, scfg["timeframe"], 701, include_forming=True)
            ind = compute_indicators(df, params)
            live = ind.iloc[-1]
            closed = ind.iloc[-2]
            bid, ask = float(tick.bid), float(tick.ask)
            spread_price = ask - bid
            sig = int(live["signal"])
            sl_dist = params["atr_sl_mult"] * float(closed["atr"])
            if not math.isfinite(sl_dist) or sl_dist <= 0:
                raise RuntimeError("ATR de référence invalide")
            analyses.append((req_name, sym, live, closed, tick, info, spread_price,
                             sig, scfg, params, sl_dist))
        except Exception as exc:
            events.append(f"{req_name} : erreur analyse — {exc}")

    if server_ts is None:
        return {"rows": rows, "events": events, "positions": my_positions(cfg["magic"]),
                "acc": acc, "stats": (0, 0, 0.0), "auto": auto}

    if server_ts - state.get("stats_ts", 0) >= 5 or "stats" not in state:
        state["stats"], state["stats_ts"] = today_stats(cfg["magic"], server_ts), server_ts
    realized, opened, win_rate = state["stats"]
    names = {1: "BUY", -1: "SELL", 0: "ATTENTE"}

    for req_name, sym, live, closed, tick, info, spread_price, sig, scfg, params, sl_dist in analyses:
        bar_id = int(live["time"])
        bid, ask = float(tick.bid), float(tick.ask)
        rows.append((req_name, round(bid, info.digits), round(ask, info.digits),
                     round(spread_price / info.point, 1), round(float(live["adx"]), 1),
                     round(float(live["rsi"]), 1), names[sig], "TICK LIVE", "—"))

        # Anti-doublon par transition de signal, pas par bougie : un signal persistant
        # ne renvoie jamais d'ordre, mais une nouvelle transition peut être évaluée intra-bougie.
        previous = state.setdefault("signal_state", {}).get(sym, 0)
        state["signal_state"][sym] = sig
        if sig == 0 or not auto or sig == previous:
            continue
        signal_id = (bar_id, sig)
        if state.setdefault("executed_signals", {}).get(sym) == signal_id:
            continue
        state["executed_signals"][sym] = signal_id

        positions = my_positions(cfg["magic"])
        ok, why = check_guards(scfg, sym, acc, positions, realized, opened,
                               server_ts, sl_dist, spread_price)
        if not ok:
            msg = f"{req_name} : signal {names[sig]} REFUSÉ — {why}"
            events.append(msg)
            journal("REFUS", sym, f"{names[sig]} | {why}")
            continue
        ok, msg = place_order(scfg, sym, sig, sl_dist)
        events.append(f"{req_name} : {'ORDRE CONFIRMÉ ' if ok else 'ORDRE REFUSÉ '}{msg}")
        journal("ORDRE_CONFIRME" if ok else "REFUS", sym, msg)
        if ok:
            opened += 1
            acc = mt5.account_info() or acc

    return {"rows": rows, "events": events, "positions": my_positions(cfg["magic"]),
            "acc": mt5.account_info(), "stats": (realized, opened, win_rate), "auto": auto}
