# EXNESS AI TRADER V4 — version de développement et validation

## Ce que contient cette V4

- Interface Tkinter redessinée : fond chaud, cartes claires, panneaux arrondis simulés, hiérarchie typographique inspirée de l'image VisionOS fournie.
- Tableau de bord : balance, equity, P/L réalisé journalier, nombre de trades, taux de réussite des sorties, positions ouvertes et risque configuré.
- Marchés EURUSD / XAUUSD : Bid, Ask, spread, ADX, RSI et signal calculé.
- Positions : tickets MT5 réels, SL/TP, volume, P/L flottant et fermeture d'une position sélectionnée.
- Journal horodaté ; les ordres ne sont qualifiés de confirmés qu'après retour positif de `order_send`.
- Analyse du signal sur la bougie M5 en formation, mise à jour par polling du dernier tick MT5 (`symbol_info_tick`) toutes les 250 ms par défaut. Les données de bougies clôturées restent utilisées comme contexte et pour l'ATR du Stop Loss.
- Protection contre les doublons : une transition de signal est traitée une seule fois, et un signal persistant ne renvoie pas une succession d'ordres.
- Validation du compte démo avant connexion et avant chaque ordre ; `order_check`, marge disponible, risque calculé avec `order_calc_profit`, contraintes de volume, spread, session, nombre de positions et limite journalière.
- Configuration externe modifiable et workflow GitHub Actions Windows mis à jour.

## Limites techniques à connaître

1. **MT5 Python ne fournit pas de callback d'événement tick dans cette architecture.** La V4 interroge donc le dernier tick à intervalle court (250 ms par défaut). Elle n'attend pas la clôture M5, mais ce n'est pas une infrastructure HFT à latence déterministe.
2. Les indicateurs stratégiques proviennent des bougies MT5, dont la bougie courante évolue avec le flux. L'entrée est évaluée sur le signal de la bougie en formation ; l'ATR de référence du SL provient de la dernière bougie clôturée pour éviter un stop instable.
3. Le moteur d'origine n'intègre pas de modèle IA entraîné ni de service d'inférence. Il contient des stratégies quantitatives à règles (pullback, breakout, mean reversion). La V4 conserve ces stratégies ; elle ne prétend pas ajouter une IA inexistante.
4. Le mode « signaux uniquement » n'envoie aucun ordre. Le module de backtest existant est une simulation historique, pas un compte paper-trading tick par tick.
5. Le mode d'exécution est verrouillé sur les comptes démo. Ne modifiez pas ce verrou pour passer en réel sans validation séparée.

## Installation Windows

### Depuis les sources
1. Installer MetaTrader 5 et se connecter à un compte **démo Exness**.
2. Installer Python 3.11 ou 3.12 64 bits.
3. Décompresser le ZIP du projet.
4. Exécuter `INSTALLER.bat`.
5. Lancer `DIAGNOSTIC.bat`, puis `BACKTEST.bat`.
6. Lancer `LANCER.bat`. Connecter MT5 et observer les signaux avant d'activer explicitement AUTO démo.

### Exécutable
Le workflow `.github/workflows/build.yml` produit sur un runner Windows :
- `EXNESS_AI_TRADER_V4.exe`
- `EXNESS_AI_TRADER_V4_TOOLS.exe`
- `config.json`
- `README_FR.md`

Le paquet ZIP est publié comme artefact GitHub Actions. La compilation réelle Windows doit être exécutée par GitHub Actions ou sur un poste Windows ; elle ne peut pas être validée par une simple compilation Python sous Linux.

## Paramètres principaux (`config.json`)

- `symbols` : symboles à surveiller (EURUSD, XAUUSD).
- `timeframe` : M5.
- `check_interval_ms` : intervalle de polling des ticks (250 ms par défaut).
- `risk_percent` : risque cible par trade (1 % maximum autorisé dans l'interface).
- `max_trades_per_day` : 6.
- `max_total_open` : 2.
- `max_open_per_symbol` : 1.
- `max_spread_sl_ratio` : filtre de spread par rapport à la distance du SL.
- `daily_loss_limit_percent` : seuil de perte journalière.

Les heures de session sont interprétées selon l'heure serveur MT5/UTC telle que rapportée par le terminal.

## Tests et validation

Les tests hors ligne vérifient la syntaxe, les imports qui ne dépendent pas du terminal, les fonctions de stratégie et le backtest sur données historiques fournies. Ils ne remplacent pas les validations suivantes, qui nécessitent Windows, MT5 ouvert et un compte démo :
- connexion réelle au terminal ;
- réception effective des ticks sur EURUSD et XAUUSD ;
- confirmation des ordres par le serveur Exness démo ;
- comportement face aux requotes, coupures réseau et rejets propres au broker ;
- compilation et lancement de l'exécutable Windows.

Aucune performance de trading n'est garantie. Le backtest et les résultats démo ne préjugent pas des performances futures.
