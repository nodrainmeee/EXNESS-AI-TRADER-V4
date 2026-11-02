"""EXNESS AI TRADER V4 — interface desktop, MT5 démo uniquement."""
import json
import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

import MetaTrader5 as mt5
import trader

BG = "#e9e5df"
PANEL = "#f7f5f1"
CARD = "#ffffff"
INK = "#252525"
MUTED = "#77736e"
GREEN = "#2e9b69"
RED = "#c85b54"
ACCENT = "#6c8fbd"


class TradingApp:
    def __init__(self, root):
        self.root = root
        root.title("EXNESS AI TRADER V4")
        root.geometry("1320x900")
        root.minsize(1100, 760)
        root.configure(bg=BG)
        self.cfg = trader.load_config()
        self.connected = False
        self.auto = False
        self.busy = False
        self.closing = False
        self.lock = threading.RLock()
        self.symbol_map = {}
        self.state = {"signal_state": {}, "executed_signals": {}}
        self._style()
        self._build()
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._schedule()

    def _style(self):
        st = ttk.Style()
        st.theme_use("clam")
        st.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=INK,
                     rowheight=29, borderwidth=0, font=("Segoe UI", 9))
        st.configure("Treeview.Heading", background="#e7e3dd", foreground=INK,
                     font=("Segoe UI", 9, "bold"), relief="flat")
        st.map("Treeview", background=[("selected", "#dce8f3")])
        st.configure("TCombobox", padding=5)

    def _card(self, parent, title, value="—", sub=""):
        frame = tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground="#dedad4")
        tk.Label(frame, text=title.upper(), bg=CARD, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=14, pady=(12, 2))
        val = tk.Label(frame, text=value, bg=CARD, fg=INK, font=("Segoe UI", 19, "bold"))
        val.pack(anchor="w", padx=14)
        note = tk.Label(frame, text=sub, bg=CARD, fg=MUTED, font=("Segoe UI", 8))
        note.pack(anchor="w", padx=14, pady=(1, 12))
        return frame, val, note

    def _build(self):
        header = tk.Frame(self.root, bg="#d9d4cd", height=76)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="◉", bg="#d9d4cd", fg=ACCENT,
                 font=("Segoe UI", 24, "bold")).pack(side="left", padx=(22, 10))
        tk.Label(header, text="EXNESS AI TRADER", bg="#d9d4cd", fg=INK,
                 font=("Segoe UI", 19, "bold")).pack(side="left")
        tk.Label(header, text="V4  •  TICK ENGINE", bg="#d9d4cd", fg=MUTED,
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=14)
        self.conn_var = tk.StringVar(value="MT5 DÉCONNECTÉ")
        self.conn_label = tk.Label(header, textvariable=self.conn_var, bg="#d9d4cd",
                                   fg=RED, font=("Segoe UI", 9, "bold"))
        self.conn_label.pack(side="right", padx=22)

        toolbar = tk.Frame(self.root, bg=BG)
        toolbar.pack(fill="x", padx=20, pady=12)
        self._button(toolbar, "Connecter MT5", self.connect, ACCENT).pack(side="left", padx=(0, 8))
        self.auto_btn = self._button(toolbar, "▶ Démarrer AUTO démo", self.toggle_auto, GREEN)
        self.auto_btn.pack(side="left", padx=4)
        self._button(toolbar, "Analyser", self.run_cycle, "#77736e").pack(side="left", padx=8)
        self._button(toolbar, "Arrêt d'urgence", self.emergency, RED).pack(side="right")
        self.mode_var = tk.StringVar(value="SIGNAUX UNIQUEMENT — aucun ordre envoyé")
        tk.Label(toolbar, textvariable=self.mode_var, bg=BG, fg=MUTED,
                 font=("Segoe UI", 9, "bold")).pack(side="right", padx=18)

        cards = tk.Frame(self.root, bg=BG)
        cards.pack(fill="x", padx=20)
        self.metrics = {}
        for title, key in [("Balance","balance"),("Équité","equity"),("P/L réalisé","pnl"),
                           ("Trades du jour","trades"),("Win rate","winrate"),("Positions","positions"),
                           ("Risque / trade","risk")]:
            f, v, n = self._card(cards, title)
            f.pack(side="left", fill="both", expand=True, padx=(0, 8))
            self.metrics[key] = (v, n)

        markets = tk.Frame(self.root, bg=BG)
        markets.pack(fill="x", padx=20, pady=12)
        self.market_cards = {}
        for symbol in ("EURUSD", "XAUUSD"):
            f = tk.Frame(markets, bg=PANEL, highlightthickness=1, highlightbackground="#d8d3cc")
            f.pack(side="left", fill="both", expand=True, padx=(0, 8))
            tk.Label(f, text=symbol, bg=PANEL, fg=INK,
                     font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=14, pady=(10, 0))
            price = tk.Label(f, text="Bid —  |  Ask —", bg=PANEL, fg=INK,
                             font=("Segoe UI", 15, "bold"))
            price.pack(anchor="w", padx=14, pady=4)
            detail = tk.Label(f, text="Spread —  •  ADX —  •  RSI —  •  Signal —",
                              bg=PANEL, fg=MUTED, font=("Segoe UI", 9))
            detail.pack(anchor="w", padx=14, pady=(0, 10))
            self.market_cards[symbol] = (price, detail)

        main = tk.Frame(self.root, bg=BG)
        main.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        left = tk.Frame(main, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right = tk.Frame(main, bg=BG, width=330)
        right.pack(side="right", fill="y")
        self._section(left, "POSITIONS OUVERTES")
        cols = ("symbol","side","volume","entry","sl","tp","profit")
        self.positions = ttk.Treeview(left, columns=cols, show="headings", height=7)
        for c, label, width in zip(cols, ("Marché","Type","Volume","Entrée","Stop Loss","Take Profit","P/L"),
                                   (100,70,75,100,100,100,90)):
            self.positions.heading(c, text=label)
            self.positions.column(c, width=width, anchor="center")
        self.positions.pack(fill="x", pady=(5, 3))
        self._button(left, "Fermer la position sélectionnée", self.close_selected, RED).pack(anchor="e", pady=(0, 10))

        self._section(left, "JOURNAL EN TEMPS RÉEL")
        self.log = tk.Text(left, bg="#292d31", fg="#e8e8e8", insertbackground="white",
                           relief="flat", font=("Consolas", 9), height=15, wrap="word")
        self.log.pack(fill="both", expand=True, pady=5)
        self.log.configure(state="disabled")

        self._section(right, "PARAMÈTRES")
        settings = tk.Frame(right, bg=CARD, padx=12, pady=10)
        settings.pack(fill="x", pady=5)
        self.setting_vars = {}
        for key, label in [("risk_percent","Risque (%)"),("max_trades_per_day","Trades max / jour"),
                           ("max_total_open","Positions max"),("max_spread_sl_ratio","Spread / SL max")]:
            row = tk.Frame(settings, bg=CARD)
            row.pack(fill="x", pady=4)
            tk.Label(row, text=label, bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
            var = tk.StringVar(value=str(self.cfg.get(key, "")))
            self.setting_vars[key] = var
            tk.Entry(row, textvariable=var, width=9, relief="flat", bg="#f0eeea",
                     justify="right").pack(side="right")
        self._button(settings, "Enregistrer les paramètres", self.save_settings, ACCENT).pack(fill="x", pady=(10, 2))
        self._section(right, "ÉTAT DU MOTEUR")
        self.engine_var = tk.StringVar(value="En attente de connexion MT5")
        tk.Label(right, textvariable=self.engine_var, bg=PANEL, fg=MUTED, justify="left",
                 wraplength=300, font=("Segoe UI", 9), padx=12, pady=12).pack(fill="x", pady=5)
        tk.Label(self.root, text="Compte démo uniquement • risque calculé sur l'equity et le SL réel • "
                 "les signaux sont évalués sur les ticks, sans attendre la clôture M5",
                 bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=22, pady=(0, 8))
        self.write_log("V4 initialisé. Aucun ordre ne sera envoyé avant activation explicite du mode AUTO démo.")

    def _button(self, parent, label, command, color):
        return tk.Button(parent, text=label, command=command, bg=color, fg="white",
                         activebackground=color, activeforeground="white", relief="flat",
                         padx=13, pady=8, font=("Segoe UI", 9, "bold"), cursor="hand2")

    def _section(self, parent, label):
        tk.Label(parent, text=label, bg=BG, fg=MUTED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(4, 0))

    def write_log(self, message):
        if not hasattr(self, "log"): return
        self.log.configure(state="normal")
        self.log.insert("end", f"[{datetime.now():%H:%M:%S}] {message}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def connect(self):
        self.write_log("Connexion MT5 demandée…")
        threading.Thread(target=self._connect_worker, daemon=True).start()

    def _connect_worker(self):
        with self.lock:
            if not mt5.initialize():
                err = mt5.last_error()
                self.root.after(0, lambda: self._connection_failed(err))
                return
            if not trader.is_demo():
                mt5.shutdown()
                self.root.after(0, lambda: self._connection_failed("Compte non démo : connexion trading refusée."))
                return
            found = {}
            for symbol in self.cfg["symbols"]:
                real = trader.resolve_symbol(symbol)
                if real:
                    found[symbol] = real
                    mt5.symbol_select(real, True)
        self.root.after(0, lambda: self._connected(found))

    def _connection_failed(self, error):
        self.conn_var.set("MT5 REFUSÉ / DÉCONNECTÉ")
        self.conn_label.configure(fg=RED)
        self.write_log(f"Connexion impossible : {error}")

    def _connected(self, found):
        self.connected, self.symbol_map = True, found
        self.conn_var.set("MT5 CONNECTÉ • COMPTE DÉMO")
        self.conn_label.configure(fg=GREEN)
        self.engine_var.set("Connexion confirmée. Réception des ticks active ; moteur AUTO désactivé.")
        for name in self.cfg["symbols"]:
            self.write_log(f"{name} : {found.get(name, 'symbole introuvable')}")
        self.run_cycle()

    def toggle_auto(self):
        if self.auto:
            self.auto = False
            self.mode_var.set("SIGNAUX UNIQUEMENT")
            self.auto_btn.configure(text="▶ Démarrer AUTO démo", bg=GREEN)
            self.write_log("Trading automatique mis en pause.")
            return
        if not self.connected:
            messagebox.showwarning("MT5", "Connectez d'abord MetaTrader 5 sur un compte démo.")
            return
        if not messagebox.askyesno("Activation AUTO démo",
                "Autoriser les ordres automatiques sur le compte DÉMO connecté ?"):
            return
        self.auto = True
        self.mode_var.set("AUTO ACTIF • COMPTE DÉMO")
        self.auto_btn.configure(text="⏸ Mettre en pause", bg="#b47b36")
        self.write_log("Trading automatique activé sur compte démo.")

    def close_selected(self):
        selection = self.positions.selection()
        if not selection:
            messagebox.showinfo("Positions", "Sélectionnez une position à fermer.")
            return
        ticket = self.positions.item(selection[0], "tags")
        # Le ticket est conservé dans iid de la ligne.
        try:
            ticket = int(selection[0])
        except ValueError:
            messagebox.showerror("Position", "Ticket de position invalide.")
            return
        if not messagebox.askyesno("Fermer la position", f"Confirmer la fermeture de la position #{ticket} ?"):
            return
        def worker():
            with self.lock:
                ok, msg = trader.close_position(self.cfg, ticket)
            self.root.after(0, lambda: self.write_log(msg))
            self.root.after(0, self.run_cycle)
        threading.Thread(target=worker, daemon=True).start()

    def emergency(self):
        self.auto = False
        self.mode_var.set("ARRÊT D'URGENCE — AUTO DÉSACTIVÉ")
        self.auto_btn.configure(text="▶ Démarrer AUTO démo", bg=GREEN)
        self.write_log("Arrêt d'urgence : nouvelles entrées désactivées.")
        if self.connected and messagebox.askyesno("Arrêt d'urgence", "Fermer aussi les positions du robot ?"):
            def worker():
                with self.lock:
                    out = trader.close_all(self.cfg)
                self.root.after(0, lambda: [self.write_log(x) for x in out])
            threading.Thread(target=worker, daemon=True).start()

    def save_settings(self):
        try:
            updated = dict(self.cfg)
            updated["risk_percent"] = float(self.setting_vars["risk_percent"].get())
            updated["max_trades_per_day"] = int(self.setting_vars["max_trades_per_day"].get())
            updated["max_total_open"] = int(self.setting_vars["max_total_open"].get())
            updated["max_spread_sl_ratio"] = float(self.setting_vars["max_spread_sl_ratio"].get())
            if not 0 < updated["risk_percent"] <= 1:
                raise ValueError("Le risque doit être > 0 et ≤ 1 %.")
            if updated["max_trades_per_day"] < 1 or updated["max_total_open"] < 1:
                raise ValueError("Les limites doivent être positives.")
            with open(trader.CFG_PATH, "w", encoding="utf-8") as f:
                json.dump(updated, f, indent=2, ensure_ascii=False)
            self.cfg = updated
            self.write_log("Configuration enregistrée.")
        except Exception as exc:
            messagebox.showerror("Paramètres invalides", str(exc))

    def run_cycle(self):
        if self.busy or not self.connected or self.closing:
            return
        self.busy = True
        threading.Thread(target=self._cycle_worker, args=(self.auto,), daemon=True).start()

    def _cycle_worker(self, auto):
        try:
            with self.lock:
                data = trader.cycle(self.cfg, self.symbol_map, self.state, auto)
            self.root.after(0, lambda: self._render(data))
        except Exception as exc:
            self.root.after(0, lambda: self._cycle_error(str(exc)))

    def _cycle_error(self, error):
        self.busy = False
        self.auto = False
        self.mode_var.set("ERREUR — AUTO COUPÉ")
        self.auto_btn.configure(text="▶ Démarrer AUTO démo", bg=GREEN)
        self.engine_var.set(error)
        self.write_log(f"ERREUR : {error} — trading auto désactivé par sécurité.")

    def _render(self, data):
        self.busy = False
        for event in data["events"]:
            self.write_log(event)
        acc = data["acc"]
        if acc:
            realized, opened, win_rate = data["stats"]
            self.metrics["balance"][0].configure(text=f"{acc.balance:,.2f} {acc.currency}")
            self.metrics["equity"][0].configure(text=f"{acc.equity:,.2f} {acc.currency}")
            self.metrics["pnl"][0].configure(text=f"{realized:+,.2f} {acc.currency}",
                fg=GREEN if realized >= 0 else RED)
            self.metrics["trades"][0].configure(text=str(opened))
            self.metrics["positions"][0].configure(text=str(len(data["positions"])))
            self.metrics["winrate"][0].configure(text=f"{win_rate:.1f} %")
            self.metrics["winrate"][1].configure(text="sur les sorties du jour")
            self.metrics["risk"][0].configure(text=f"{self.cfg['risk_percent']:.2f} %")
            self.metrics["trades"][1].configure(text=f"Limite {self.cfg['max_trades_per_day']}")
        for item in self.positions.get_children():
            self.positions.delete(item)
        for p in data["positions"]:
            side = "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL"
            self.positions.insert("", "end", iid=str(p.ticket), values=(p.symbol, side, p.volume, p.price_open,
                p.sl, p.tp, f"{p.profit:+.2f}"))
        for symbol, price, detail in []:
            pass
        for row in data["rows"]:
            name, bid, ask, spread, adx, rsi, signal = row[:7]
            if name in self.market_cards:
                self.market_cards[name][0].configure(text=f"Bid {bid}   /   Ask {ask}")
                self.market_cards[name][1].configure(
                    text=f"Spread {spread} pts  •  ADX {adx}  •  RSI {rsi}  •  {signal}")
        self.engine_var.set(f"Tick live • {datetime.now():%H:%M:%S} • "
                            f"{len(self.symbol_map)} instrument(s) • AUTO {'ACTIF' if self.auto else 'INACTIF'}")

    def _schedule(self):
        if self.closing: return
        if self.connected:
            self.run_cycle()
        self.root.after(max(100, int(self.cfg.get("check_interval_ms", 250))), self._schedule)

    def close(self):
        self.closing = True
        self.auto = False
        try:
            with self.lock:
                mt5.shutdown()
        except Exception:
            pass
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    TradingApp(root)
    root.mainloop()
