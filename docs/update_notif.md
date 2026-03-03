# directives_agent.md — Directives Notifications Telegram (Paper Trading BTC)

## 1) Contexte
Tu es un agent chargé de **refondre les notifications Telegram** d’un bot de paper trading BTC pour les rendre :
- plus **lisibles** (1–2 secondes pour comprendre l’info)
- plus **ergonomiques** (structure cohérente, infos clés en premier)
- moins **spammy** (anti-duplication + rate limiting)
- **standardisées** (mêmes champs, même ordre, même style)

Le bot fait du **paper trading** (wallet simulé), et récupère uniquement le prix (sans trading API). Les messages actuels ressemblent à des logs techniques. Il faut en faire des **notifications produit**.

---

## 2) Objectifs (ce que tu dois livrer)
Tu dois produire :
1) Une **spécification** de messages Telegram ergonomiques (formats + champs + règles d’envoi)
2) Une **table de mapping** : événement → template → champs
3) Une **stratégie anti-spam** (rate limiting + idempotence)
4) Un **plan d’implémentation** simple côté code (structure de fonctions + état minimal à stocker)
5) Des **exemples** concrets (BUY, SELL, kill switch, feed down/up, daily report, wallet low cash)

---

## 3) Contraintes & style
### Langue
- Français.

### Lisibilité
- Chaque message doit avoir :
  - un **titre court** (avec emoji + catégorie)
  - une **ligne de contexte** (symbol/timeframe/date)
  - 3–6 lignes max, sauf daily report (max ~10 lignes)
- Toujours mettre **les infos essentielles en premier** :
  - direction BUY/SELL, prix, taille, PnL, wallet

### Format Telegram
- Utiliser un Markdown “simple” compatible Telegram :
  - `**gras**` pour le titre
  - `` `monospace` `` pour les chiffres/variables
- Éviter les pavés et répétitions.

### Unicité / Anti-duplication
- Le bot ne doit pas envoyer 2 fois le même message (ex: double “Bot démarré”).
- Chaque événement doit être **idempotent** :
  - un trade est identifié par `trade_id`
  - une candle traitée par `(symbol, timeframe, open_time)`
  - un incident feed par une fenêtre (down_since → recovered)

---

## 4) Taxonomie d’événements (à couvrir)
### Événements principaux
- STARTUP : bot démarré
- TRADE_BUY : achat exécuté (paper)
- TRADE_SELL : vente exécutée (paper)
- RISK_KILL_SWITCH : kill switch drawdown
- DATA_FEED_DOWN : feed prix down
- DATA_FEED_OK : feed prix rétabli
- DAILY_REPORT : reporting du jour (trades + portefeuille)
- WALLET_CASH_LOW : cash faible
- ERROR_CRITICAL : erreur critique (optionnel)

---

## 5) Templates — formats attendus (spécification)
### 5.1 STARTUP (1 fois, pas spam)
**🟢 PAPER BOT — DÉMARRÉ**  
`BTCUSDT • 1m • Europe/Paris`  
⏱️ `HH:MM:SS` — `YYYY-MM-DD`  
Mode: `LIVE` | Source: `Binance REST`  
DB: `paper.db` | Version: `vX.Y.Z`

Champs requis :
- symbol, timeframe, timezone
- date/time
- source prix (REST/WS + provider)
- version (si dispo)
- db_name (si dispo)

Règles :
- envoyer max 1 fois / 6h (ou uniquement si process nouveau / version changée)

---

### 5.2 TRADE BUY
**✅ BUY — BTCUSDT (PAPER)**  
⏱️ `HH:MM:SS` — `YYYY-MM-DD`  
Prix: `market` → `exec` (slip `x%`)  
Taille: `qty BTC` | Fee: `fee USDT`  
Wallet: `cash USDT` + `btc BTC` | Eq: `equity`  
Signal: `reason`

Champs requis :
- market_price, exec_price, slippage_rate
- qty_btc, fee_quote
- wallet cash/btc, equity
- reason

---

### 5.3 TRADE SELL (avec PnL)
**✅ SELL — BTCUSDT (PAPER)**  
⏱️ `HH:MM:SS` — `YYYY-MM-DD`  
Prix: `market` → `exec` (slip `x%`)  
Taille: `qty BTC` | Fee: `fee USDT`  
PnL trade: `+/-X USDT` (`+/-Y%`) | PnL jour: `+/-Z`  
Wallet: `cash USDT` + `btc BTC` | Eq: `equity`  
Signal: `reason`

Champs requis :
- pnl_trade_abs + pnl_trade_pct (si possible)
- pnl_day_abs (si possible)

---

### 5.4 KILL SWITCH
**🔴 KILL SWITCH — TRADING STOP**  
⏱️ `HH:MM:SS` — `YYYY-MM-DD`  
Drawdown: `dd%` (seuil `threshold%`)  
Equity: `equity`  
Position: `Flat` ou `X BTC`  
Action: `Aucun nouvel ordre`

Champs requis :
- drawdown, threshold, equity
- position status

---

### 5.5 FEED DOWN (déclenché après N erreurs)
**⚠️ DATA FEED DOWN — Binance**  
⏱️ `HH:MM:SS` — `YYYY-MM-DD`  
Erreur: `timeout / 5xx / ...`  
Retry: `#n` | Backoff: `xs`  
Mode: `Pause trading` (si applicable)

Champs requis :
- provider name
- error type (résumé)
- retry_count, backoff
- trading_paused yes/no

Règles :
- déclencher uniquement après `N=3` erreurs consécutives
- ne pas envoyer chaque erreur, juste l’état DOWN

---

### 5.6 FEED OK (avec durée)
**🟢 DATA FEED OK — Binance**  
⏱️ `HH:MM:SS` — `YYYY-MM-DD`  
Downtime: `Xm Ys`  
Dernier prix: `price`

Règles :
- envoyer uniquement si un DOWN a été envoyé
- inclure durée down

---

### 5.7 DAILY REPORT
**📊 DAILY REPORT — PAPER BTC (YYYY-MM-DD)**  
Timezone: `Europe/Paris`  
Equity: `start` → `end` | PnL: `+/-abs` (`+/-pct`)  
Trades: `n` (B `x` / S `y`) | Win: `w%` | Fees: `f`  
Max DD: `dd%` | Position fin: `btc` | Cash: `cash`  
BTC ref: `price` | Exposure: `exp%`  
Notes: `...`

Règles :
- 1 fois / jour à heure fixe (ex: 23:59) ou au premier tick après minuit
- compacte, pas de roman

---

### 5.8 WALLET CASH LOW
**🟠 WALLET LOW CASH**  
⏱️ `HH:MM:SS` — `YYYY-MM-DD`  
Cash: `cash` (seuil `threshold`)  
Action: `reduce_size / block_buy / info-only`  
Statut: `WARN`

Règles :
- rate limit (ex: max 1 alerte / heure tant que cash reste bas)

---

## 6) Anti-spam & idempotence (obligatoire)
### 6.1 Rate limiting recommandé
- STARTUP : 1 / 6h
- WALLET_CASH_LOW : 1 / 60min (tant que sous seuil)
- FEED_DOWN : 1 par incident (après N erreurs)
- FEED_OK : 1 par incident (uniquement si DOWN envoyé)
- TRADE : toujours (mais idempotent via trade_id)
- DAILY_REPORT : 1 / jour

### 6.2 État minimal à stocker (SQLite `bot_state`)
Clés proposées :
- `last_start_notif_ts`
- `feed_down_active` (0/1)
- `feed_down_since_ts`
- `last_wallet_low_ts`
- `last_daily_report_date` (YYYY-MM-DD)
- `last_processed_open_time` (par symbol/timeframe)
- `last_trade_notif_id` (optionnel)

---

## 7) Plan d’implémentation (niveau code)
Créer un module `notify/telegram.py` avec :
- `send_message(text: str) -> None`
- `format_startup(ctx) -> str`
- `format_trade(trade, wallet, pnl) -> str`
- `format_kill_switch(risk_state) -> str`
- `format_feed_down(feed_state) -> str`
- `format_feed_ok(feed_state) -> str`
- `format_daily_report(report) -> str`
- `format_wallet_low(wallet_state) -> str`

Créer un module `notify/dispatcher.py` avec :
- `should_send(event_type, event_id, state) -> bool`
- `mark_sent(event_type, event_id, state) -> None`

Objectif : séparer **format** (texte) et **règles d’envoi** (anti-spam).

---

## 8) Exemples attendus (à produire par l’agent)
Tu dois fournir au minimum :
- 1 STARTUP
- 1 BUY
- 1 SELL avec PnL
- 1 KILL SWITCH
- 1 FEED DOWN + 1 FEED OK (avec downtime)
- 1 DAILY REPORT
- 1 WALLET LOW CASH

---

## 9) Critères d’acceptation (Definition of Done)
- Messages lisibles en < 2 secondes (titre + résumé)
- Pas de doublons (startup, feed)
- Templates cohérents (même ordre de champs)
- Daily report compact et complet
- Règles anti-spam explicites + état minimal défini
- Facile à implémenter (fonctions + state keys)

---

# PROMPT À FOURNIR À TON AGENT (copie-colle)

Tu es un agent chargé de refondre les notifications Telegram d’un bot de paper trading BTC (wallet simulé) pour les rendre ergonomiques, lisibles et non spammy.

Contexte : le bot récupère uniquement le prix BTC (données publiques), calcule un signal (ex MA10/MA30), exécute des trades en paper (fees + slippage), et envoie des notifications Telegram pour : démarrage, BUY/SELL, kill switch drawdown, feed down/up, daily report, cash faible.

Tâches :
1) Propose une spécification complète des messages Telegram : templates (Markdown simple) + champs requis + ordre des infos.
2) Fais une table : événement → template → champs → règles d’envoi.
3) Définis une stratégie anti-spam : rate limiting + idempotence + état minimal à stocker (ex table bot_state).
4) Donne un plan d’implémentation : modules/fonctions (format vs dispatch), et quelles clés d’état stocker.
5) Fournis des exemples concrets pour chaque événement (STARTUP, BUY, SELL avec PnL, KILL SWITCH, FEED DOWN/OK avec downtime, DAILY REPORT, WALLET LOW CASH).
Contraintes : messages courts, infos clés en premier, pas de doublons, français, Telegram Markdown simple (**gras**, `monospace`).

Voici des exemples actuels peu lisibles (à améliorer) :
- [INFO][PAPER][BTC] Bot démarré (doublons)
- BUY exécuté / SELL exécuté avec market/exec/qty/fee/wallet/reason
- Kill switch déclenché (drawdown)
- Feed prix down / feed rétabli
- Daily report (equity, pnl, trades, winrate, fees, max dd, end wallet)
- Wallet cash low

Livrable final : une mini-doc prête à coller dans le projet + les templates prêts à copier.