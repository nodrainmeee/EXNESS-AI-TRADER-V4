"""Outils en console : diagnostic, backtest, recherche de stratégie (version .exe)."""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trader  # noqa: F401  (crée le dossier logs)
import diagnostic
import backtest
import research


def run(title, fn):
    print(f"\n=== {title} ===\n")
    try:
        fn()
    except SystemExit as e:
        if e.code:
            print(e.code)
    except Exception:
        traceback.print_exc()
    input("\nAppuyez sur Entrée pour revenir au menu...")


def menu():
    while True:
        os.system("cls")
        print("EXNESS AI TRADER V3 - OUTILS (compte DEMO uniquement)")
        print("MT5 doit être ouvert et connecté à un compte démo.\n")
        print("  1) Diagnostic (le robot peut-il trader avec mon solde ?)")
        print("  2) Backtest EURUSD + XAUUSD")
        print("  3) Recherche de stratégie (walk-forward, plusieurs minutes)")
        print("  4) Quitter\n")
        c = input("Votre choix : ").strip()
        if c == "1":
            run("DIAGNOSTIC", diagnostic.main)
        elif c == "2":
            def bt():
                for sym in ("EURUSD", "XAUUSD"):
                    backtest.main(["--symbol", sym, "--tf", "M15", "--bars", "30000", "--optimize"])
            run("BACKTEST", bt)
        elif c == "3":
            run("RECHERCHE", research.main)
        elif c == "4":
            return


if __name__ == "__main__":
    menu()
