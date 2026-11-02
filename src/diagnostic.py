"""Diagnostic : le robot peut-il trader avec VOTRE solde démo ? (aucun ordre envoyé)"""
import sys
import MetaTrader5 as mt5
import trader
from strategy import compute_indicators, params_from_cfg


def main():
    cfg = trader.load_config()
    if not mt5.initialize():
        sys.exit(f"MT5 non connecté : {mt5.last_error()}")
    if not trader.is_demo():
        mt5.shutdown()
        sys.exit("Le compte connecté n'est PAS démo. Connectez un compte démo dans MT5.")
    acc = mt5.account_info()
    term = mt5.terminal_info()
    risk_money = acc.equity * cfg["risk_percent"] / 100
    print(f"\nCompte démo {acc.login} | serveur {acc.server} | solde {acc.balance:.2f} {acc.currency} | equity {acc.equity:.2f}")
    print(f"Algo Trading autorisé dans MT5 : {'OUI' if term and term.trade_allowed else 'NON  <-- activez le bouton Algo Trading'}")
    print(f"Budget de risque par trade ({cfg['risk_percent']} %) : {risk_money:.2f} {acc.currency}\n")
    for base in cfg["symbols"]:
        sym = trader.resolve_symbol(base)
        if not sym:
            print(f"[{base}] introuvable : ajoutez-le dans Observation du marché.\n")
            continue
        mt5.symbol_select(sym, True)
        scfg = trader.symbol_cfg(cfg, base)
        p = params_from_cfg(scfg)
        try:
            ind = compute_indicators(trader.get_rates(sym, scfg["timeframe"]), p)
        except Exception as exc:
            print(f"[{base}] {sym} : historique impossible ({exc})\n")
            continue
        info, tick = mt5.symbol_info(sym), mt5.symbol_info_tick(sym)
        sl_dist = p["atr_sl_mult"] * float(ind.iloc[-1]["atr"])
        spread = tick.ask - tick.bid
        loss_min = abs(mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, sym, info.volume_min, tick.ask, tick.ask - sl_dist) or 0)
        lot, err = trader.calc_lot(sym, 1, tick.ask, tick.ask - sl_dist, risk_money)
        print(f"[{base}] symbole MT5 : {sym}")
        print(f"   Stop Loss typique : {sl_dist:.{info.digits}f} | spread actuel : {spread / info.point:.0f} pts "
              f"({spread / sl_dist:.0%} du SL, max autorisé {cfg['max_spread_sl_ratio']:.0%})")
        print(f"   Lot minimum {info.volume_min} -> perte si SL touché : {loss_min:.2f} {acc.currency} "
              f"({loss_min / acc.equity:.1%} du compte)")
        if lot:
            print(f"   => OK : le robot peut trader {sym} (lot calculé {lot}).\n")
        else:
            print(f"   => BLOQUÉ : {err}\n")
    mt5.shutdown()


if __name__ == "__main__":
    main()
