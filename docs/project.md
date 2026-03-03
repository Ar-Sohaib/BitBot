# projet.md — Paper Trading BTC “Maison” sur VPS (prix public + wallet simulé) + Notifications Telegram

## 0) Objectif (ce que tu construis)
Un système autonome sur ton VPS qui :
1. Récupère le prix du Bitcoin (BTC) via **données publiques** (sans compte, sans clés, sans API trading).
2. Construit / stocke des **candles** (ex: 1m).
3. Exécute une **stratégie** sur candle close (BUY/SELL/HOLD).
4. Simule l’exécution dans un **wallet fictif** (paper broker) avec **fees + slippage**.
5. Logge tout (candles, signaux, trades, equity).
6. Envoie des **notifications Telegram** (mouvements + rapport journalier portefeuille/trades).

Le projet est volontairement modulaire : tu peux changer la source de prix, la stratégie, la base (PostgreSQL), ou ajouter du WebSocket plus tard.

---

## 1) Périmètre & principes (pour éviter les faux résultats)
### Périmètre
- ✅ Paper trading uniquement (aucun trade réel).
- ✅ Source de prix publique (REST / WebSocket).
- ✅ Simulation d’ordres “market” (simple) avec slippage + fees.
- ✅ Reporting journalier + notifications Telegram.
- ❌ Pas de gestion de carnet d’ordres complet au début.
- ❌ Pas de trading API (pas de clés exchange).

### Principes anti-biais
- **Décision sur candle close** uniquement (pas de candle en cours).
- Toujours inclure **fees + slippage** (sinon performance “magique”).
- Logging exhaustif (sinon debug impossible).

---

## 2) Architecture (MVP solide)
### Modules
1. **price_feed**
   - Récupère les candles (REST recommandé au début).
   - Stocke en base (candles).
2. **strategy**
   - Lit la dernière candle close + historique.
   - Calcule features/indicateurs.
   - Produit un signal BUY/SELL/HOLD + “reason”.
3. **paper_broker**
   - Exécute virtuellement le signal.
   - Met à jour le wallet (cash, btc_qty, avg_entry).
   - Calcule PnL réalisé/latent, equity, drawdown.
4. **storage**
  - PostgreSQL : schéma + fonctions insert/select.
5. **analytics/reporting**
   - Calcule métriques journalières (PnL, nb trades, winrate, max DD, fees).
   - Construit un rapport texte (Telegram).
6. **notifier_telegram**
   - Envoie messages sur trades / événements / rapport quotidien.

### Modes d’exécution
- **Live paper** (sur VPS) : tourne 24/7, traite chaque nouvelle candle close.
- **Backtest** (optionnel) : rejoue l’historique stocké, mêmes règles.

---

## 3) Choix techniques (recommandation)
- Python 3.11+
- PostgreSQL
- `requests` (REST)
- `pandas` (optionnel, pratique pour indicateurs)
- `python-dotenv` (optionnel) pour `.env`
- `systemd` (pour tourner H24)

---

## 4) Source de prix (sans “plateforme de paper trading”)
Tu n’utilises aucune plateforme de paper trading. Tu utilises **une source de prix publique**.

### Reco MVP : REST candles
- Récupère des candles 1m via endpoint public (OHLCV déjà agrégé).
- Poll toutes les 10–30 secondes pour détecter une nouvelle candle close.

### Évolution : WebSocket (plus tard)
- Stream trades/ticker.
- Reconstruit candles localement.
- Utile pour scalping / microstructure.

---

## 5) Base de données (PostgreSQL) — schéma minimal
### Table `candles`
- symbol (TEXT) ex: BTCUSDT
- timeframe (TEXT) ex: 1m
- open_time (INTEGER, epoch ms)
- open, high, low, close (REAL)
- volume (REAL)
- close_time (INTEGER, epoch ms)
- UNIQUE(symbol, timeframe, open_time)

### Table `signals`
- ts (INTEGER)
- symbol, timeframe
- signal (TEXT) BUY/SELL/HOLD
- reason (TEXT)
- features_json (TEXT) (optionnel)
- UNIQUE(symbol, timeframe, ts)

### Table `trades`
- trade_id (TEXT/UUID)
- ts (INTEGER)
- side (TEXT) BUY/SELL
- symbol (TEXT)
- qty_btc (REAL)
- price_market (REAL)
- price_exec (REAL)
- fee (REAL)
- cash_after (REAL)
- btc_after (REAL)
- pnl_realized (REAL) (SELL)
- meta_json (TEXT) (optionnel)

### Table `equity`
- ts (INTEGER)
- cash (REAL)
- btc_qty (REAL)
- btc_price (REAL)
- equity (REAL) = cash + btc_qty * btc_price
- drawdown (REAL)

### Table `bot_state`
- key (TEXT PRIMARY KEY)
- value (TEXT)
(sert à stocker `last_processed_open_time`, etc.)

---

## 6) Paper Broker (wallet simulé)
### État du wallet
- cash_quote : ex 10_000 (USDT fictif)
- btc_qty : ex 0.0
- avg_entry_price : prix moyen d’entrée (pour PnL)
- fees_paid_total

### Paramètres réalistes
- fee_rate : ex 0.001 (0.1%)
- slippage_rate : ex 0.0002 (0.02%) (à ajuster)
- max_position_pct : ex 0.20 (20% max du capital par trade)
- min_order_notional : ex 10 (pour éviter micro-ordres)
- kill_switch_drawdown_pct : ex 0.15 (arrêt si drawdown > 15%)

### Règles BUY (market)
- price_exec = price_market * (1 + slippage_rate)
- notional = cash_to_spend
- fee = notional * fee_rate
- btc_bought = (notional - fee) / price_exec
- cash -= notional
- btc_qty += btc_bought
- avg_entry_price = moyenne pondérée

### Règles SELL (market)
- price_exec = price_market * (1 - slippage_rate)
- notional = btc_to_sell * price_exec
- fee = notional * fee_rate
- cash += (notional - fee)
- btc_qty -= btc_to_sell
- pnl_realized = (price_exec - avg_entry_price) * btc_to_sell - fee

### 6.1) Architecture détaillée du module `paper_broker`

But
- Simuler l'exécution d'ordres market de façon réaliste (fees + slippage), maintenir l'état wallet, produire des enregistrements transactionnels et exposer une API idempotente et sûre pour les autres modules.

Responsabilités
- Calculs d'exécution : slippage, fees, qty/notional, pnl_realized.
- Gestion d'état : `cash`, `btc_qty`, `avg_entry_price`, `fees_paid_total`, `is_blocked`.
- Persistance atomique : écrire `trades` + snapshot `equity` + mise à jour `bot_state` en transaction.
- Règles de risque : `max_position_pct`, `min_order_notional`, `kill_switch_drawdown`.
- Idempotence & locking : éviter double-exécution pour une même candle.
- Observabilité : logs structurés, métriques, hooks de notification.

API proposée (surface publique)
- `class PaperBroker(config, db):`
  - `load_state() -> WalletState` : charger l'état depuis la DB.
  - `get_state() -> WalletState` : état courant thread-safe.
  - `execute_signal(signal: Signal, candle: Candle) -> TradeResult` : point d'entrée principal ; vérifie règles, exécute, persiste et renvoie résultat.
  - `simulate_order(side, price_market, notional=None, qty=None) -> SimResult` : calcul local pour tests/preview.
  - `snapshot_equity(ts, btc_price)` : calcule et persiste une ligne `equity`.
  - `check_kill_switch() -> bool` : évalue drawdown et bloque le trading si nécessaire.
  - `admin_reset()` / `force_unblock()` : utilitaires pour admin/tests.

Types internes
- `WalletState` : {cash, btc_qty, avg_entry_price, fees_paid_total, is_blocked}
- `TradeRecord` : correspond au schéma `trades` + `trade_id` UUID + `source_candle_open_time`
- `SimResult` : {price_exec, qty, fee, cash_after, btc_after, pnl_realized}

Séquence d'exécution (BUY)
1. Vérifications initiales : `is_blocked` ? `min_order_notional` ? `max_position_pct` ? existence d'un trade pour `source_candle_open_time` ?
2. Calculs : `price_exec = price_market * (1 + slippage_rate)` ; `notional = requested_notional` ou limité par `cash * max_position_pct` ; `fee = notional * fee_rate` ; `btc_bought = (notional - fee) / price_exec`.
3. Mise à jour mémoire du `WalletState` (avant persistance seulement pour validation).
4. Persistance atomique : dans une transaction DB -> INSERT `trades`, INSERT `equity` snapshot, UPDATE `bot_state` (ex: `last_processed_open_time`).
5. Commit ; logs structurés ; émettre événement pour `notifier_telegram.notify_trade()`.

Persistance & transactions
- Grouper insert/update liés à un trade dans une transaction ACID (BEGIN/COMMIT) côté PostgreSQL.
- Utiliser contraintes uniques (`trade_id`, ou `UNIQUE(symbol, timeframe, source_candle_open_time)`) pour empêcher doublons.
- Marquer `bot_state['last_processed_open_time']` uniquement après commit réussi.

Concurrence & idempotence
- Point d'entrée `execute_signal` doit être thread/process-safe. Options : mutex applicatif (`threading.Lock` / file lock) OU contrôle d'idempotence basé sur `source_candle_open_time` vérifié dans la transaction.
- Si exécution distribuée prévue plus tard, remplacer mutex par un verrou DB externalisé ou une file de travail (queue).

Gestion des erreurs & robustesse
- En cas d'échec de persistance : rollback complet et restauration de l'état mémoire depuis DB.
- Retries contrôlés pour erreurs transitoires (DB lock, IO). En cas d'échec répétitif, déclencher alerte Telegram et passer en mode `is_blocked`.
- Refuser exécution si DB inaccessible.

Paramètres configurables
- `fee_rate`, `slippage_rate`, `max_position_pct`, `min_order_notional`, `kill_switch_drawdown_pct`, `precision`.

Observabilité & métriques
- Logs structurés : event=trade_exec, trade_id, side, price_market, price_exec, qty, fee, cash_before, cash_after.
- Compteurs exposés : `trades_total`, `trades_failed`, `fees_total`, `pnl_realized_total`.
- Snapshot `equity` après chaque trade et périodiquement (ex: chaque candle close).

Tests recommandés
- Unitaires : `simulate_order` (fees/slippage/rounding), calculs PnL.
- Intégration : exécution end-to-end avec PostgreSQL ; vérifier INSERT/UPDATE et rollback.
- Scénarios : tentative de double-exécution, DB locked, kill-switch déclenché.

Fichiers recommandés (repo)
- `src/broker/paper_broker.py` : implémentation `PaperBroker`.
- `src/broker/models.py` : `WalletState`, `TradeRecord`, `SimResult`.
- `src/storage/db.py` : helpers transactionnels (`with db.transaction():`).
- `tests/broker/` : tests unitaires & intégration.

Points d'attention pratiques
- Pour le MVP, garder le broker dans le même processus que le polling. Si plus tard on distribue, prévoir mécanisme de verrou/queue.
- Toujours lier `trade_id` à `source_candle_open_time` pour traçabilité.
- Conserver le `reason` (journal de décision) lié au `trade`.
- Prévoir `simulate_only=True` pour backtest / dry-run.

---

## 7) Stratégie (MVP pour valider la pipeline)
### Stratégie “MA Cross” (exemple)
- Calcule MA_fast (ex: 10) et MA_slow (ex: 30) sur closes.
- Signal :
  - BUY si MA_fast croise au-dessus MA_slow et pas déjà en position.
  - SELL si MA_fast croise en dessous MA_slow et en position.
  - HOLD sinon.

### Règles essentielles
- Évalue seulement sur **candles closes**.
- Anti double-trade : traite une candle une seule fois (via `last_processed_open_time`).

---

## 8) Logging & reporting (ce que tu dois absolument tracer)
### À chaque candle close
- timestamp candle, close price
- signal + reason + features
- position avant/après (cash, btc_qty)
- si trade : prix_exec, qty, fee, pnl

### Métriques (journalières)
- Equity début/fin journée, PnL jour
- Nb trades, buy/sell count
- Winrate (trades gagnants / total)
- Max drawdown du jour
- Fees payées
- Exposition moyenne (optionnel)

---

## 9) Notifications Telegram (mouvements + rapport quotidien)
### Objectif
1) Envoyer un message **immédiat** quand le bot exécute un BUY/SELL.
2) Envoyer un **rapport quotidien** récapitulatif : portefeuille + trades du jour.

### Prérequis Telegram (1 fois)
1. Créer un bot via **@BotFather**
   - `/newbot` → récupérer le **BOT_TOKEN**
2. Récupérer le `chat_id`
   - Méthode simple :
     - Envoie un message à ton bot (ex: “hello”)
     - Appelle l’endpoint `getUpdates` et lis `chat.id`
3. Stockage sécurisé :
   - Met `BOT_TOKEN` et `CHAT_ID` dans un fichier `.env` (ou variables d’environnement du service systemd)
   - Ne jamais commit `.env`

#### Variables
- `TELEGRAM_BOT_TOKEN=xxxxx:yyyyy`
- `TELEGRAM_CHAT_ID=123456789`

### Quand notifier (événements)
- ✅ Trade exécuté (BUY/SELL)
- ✅ Kill switch / drawdown dépassé (ALERTE)
- ✅ Feed prix down (ALERTE)
- ✅ Redémarrage bot (INFO)
- ✅ Rapport journalier (DAILY)

### Format messages (standardisé)
#### 1) Message “Trade exécuté”
- Exemple :
  - `[PAPER][BTC] BUY exécuté`
  - Time: 2026-03-02 14:05:00
  - Market: 91500.0
  - Exec: 91518.3 (slip 0.02%)
  - Qty: 0.01092 BTC
  - Fee: 1.00 USDT
  - Wallet: cash=8999.0 | btc=0.01092
  - Reason: MA10 crossed above MA30

#### 2) Alerte drawdown / kill switch
- `[ALERT][PAPER][BTC] Kill switch déclenché`
- Drawdown: 15.3% (seuil 15%)
- Action: Trading stoppé (no new orders)
- Equity: 8420.5

#### 3) Rapport quotidien (envoyé 1x/jour)
Contenu minimum :
- Date (timezone Europe/Paris)
- Equity start → equity end
- PnL day (absolu + %)
- Nb trades (BUY/SELL)
- Winrate (si >0 trades)
- Fees totales
- Position finale : cash, btc_qty, price, exposition
- Top 3 trades (optionnel) + pire trade (optionnel)

Exemple :
- `[DAILY REPORT][PAPER][BTC] 2026-03-02`
- Equity: 10000.0 → 10125.4  (PnL +125.4 / +1.25%)
- Trades: 4 (BUY 2 / SELL 2)
- Winrate: 50%
- Fees: 8.2 USDT
- Max DD: 0.9%
- End wallet: cash=6500.0 | btc=0.0398 | BTC=91500.0 | exposure=36%
- Notes: feed ok, no errors

### Fréquence & scheduling
- Trades : instantané
- Rapport : **tous les jours à 23:59** (Europe/Paris) ou après clôture d’une candle particulière (ex: 23:59)
- Alternative : rapport au premier tick après minuit (00:01)

### Implémentation (concept)
- Module `notifier_telegram.py` expose :
  - `send_message(text: str)`
  - `notify_trade(trade_obj)`
  - `notify_daily_report(report_obj)`
- Gestion erreurs :
  - si Telegram échoue → log WARNING + retry léger (ex: 3 tentatives, backoff)
- Anti-spam :
  - regrouper les erreurs feed (pas 100 messages)

---

## 10) Déploiement sur VPS (run H24)
### Installation (MVP)
1. Créer dossier projet : `/opt/paper-btc-bot`
2. Créer venv python
3. Installer deps `requirements.txt`
4. Créer `.env` (ou variables systemd)
5. Lancer une fois pour init DB + tables
6. Activer service systemd

### Bonnes pratiques sécurité
- user dédié (ex: `paperbot`), pas root
- ssh keys only
- ufw + fail2ban (optionnel mais recommandé)
- secrets dans env, jamais dans le repo

---

## 11) systemd (service)
But : redémarrage auto, logs, exécution stable.

- `Restart=always`
- `WorkingDirectory=/opt/paper-btc-bot`
- `EnvironmentFile=/opt/paper-btc-bot/.env` (si tu choisis ce modèle)
- Logs : journalctl + fichier log interne (optionnel)

---

## 12) MVP Checklist (Definition of Done)
✅ Le bot tourne 24h sans crash  
✅ Une candle est traitée une seule fois (pas de double-trade)  
✅ Fees & slippage activés  
✅ Trades + equity loggés  
✅ Notifications Telegram : trade + daily report  
✅ Kill switch drawdown fonctionnel (même simple)

---

## 13) Roadmap (après MVP)
1. Import historique (1 an candles) + backtest
2. Rapport HTML/CSV (export quotidien)
3. WebSocket temps réel + reconnection robuste
4. Slippage dynamique (selon volatilité/spread)
5. Multi-timeframe (1m + 15m)
6. Plusieurs stratégies + allocation
7. Dashboard (Grafana/Metabase)

---

## 14) Structure de repo (recommandée)
paper-btc-bot/
  projet.md
  README.md
  requirements.txt
  .env.example
  src/
    main_live.py
    main_backtest.py
    config.py
    price_feed/
      rest_provider.py
      candles.py
    strategy/
      base.py
      ma_cross.py
    broker/
      paper_broker.py
      risk.py
    storage/
      db.py
      schema.sql
    analytics/
      metrics.py
      daily_report.py
    notify/
      telegram.py
  data/
    README.md
  logs/
    app.log

---

## 15) Notes importantes (pragmatiques)
- Même en paper, ton bot doit être parano : retries réseau, erreurs DB, idempotence sur candle.
- La meilleure “feature” au début : un **journal de décision** clair. Les stratégies viennent après.
- Tout le projet tient sur VPS petit/moyen. Le vrai coût, c’est la discipline de logs + tests.