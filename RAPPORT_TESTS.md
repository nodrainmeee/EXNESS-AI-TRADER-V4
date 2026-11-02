# Rapport de validation — EXNESS AI TRADER V4

Date : 2 novembre 2026

## Vérifications effectuées dans cet environnement
- Archive V3 ouverte et inventaire des 21 entrées effectué.
- Sources Python V3, configuration, scripts Windows, documentation et workflow CI examinés.
- Moteur modifié pour calculer le signal sur la bougie en formation, rafraîchie à partir des données MT5, avec polling `symbol_info_tick` à 250 ms.
- Anti-doublon revu : détection des transitions de signal et identifiant par symbole / bougie / direction.
- Calcul de lot testé avec doubles de test : refus si le lot minimum dépasse le budget de risque ; calcul de volume conforme lorsque le budget le permet.
- Stratégies pullback, breakout et meanrev exécutées sur un jeu de données synthétique pour vérifier le pipeline indicateurs/signaux.
- Backtest exécuté sur données synthétiques pour vérifier le pipeline de simulation historique.
- Tous les fichiers Python compilés avec `py_compile` sans erreur de syntaxe.
- Configuration JSON relue et valeurs M5 / polling 250 ms vérifiées.

## Non vérifié ici
- MetaTrader5 Python n'est pas installé dans l'environnement d'exécution et aucun terminal MT5 / compte Exness démo n'est connecté.
- Aucun tick réel n'a donc été reçu et aucun ordre réel ou démo n'a été envoyé.
- La compilation PyInstaller Windows n'a pas été exécutée : cet environnement est Linux.
- La fluidité UI et les interactions avec le terminal doivent être testées sur Windows 10/11.

## Conclusion
Le code source V4 et le workflow de compilation Windows sont préparés. Le livrable ne doit pas être considéré comme validé en trading réel ni comme un exécutable Windows testé avant exécution du protocole démo sur un poste Windows avec MT5.
