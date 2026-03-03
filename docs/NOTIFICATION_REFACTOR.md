# Refactoring Notifications Telegram — Rapport d'Implémentation

## 📋 Résumé

La refonte des notifications Telegram a été complétée selon les directives fournies dans `update_notif.md`. Le système est maintenant :

- ✅ **Lisible** : Messages compacts (< 2s de lecture), emojis + titres clairs
- ✅ **Ergonomique** : Structure cohérente, infos essentielles en premier, Markdown simple
- ✅ **Anti-spam** : Rate limiting + idempotence via dispatcher + state tracking
- ✅ **Standardisé** : 8 templates avec champs dans le même ordre pour chaque type d'événement

---

## 🔧 Changements Implémentés

### 1. **src/notify/telegram.py** — Refactorisation complète

**Avant** :
- Messages sans structure (tags `[PAPER][BTC]`, logs-like)
- Formatage inline dans les méthodes notify_*()
- Pas de rate limiting

**Après** :
- 8 fonctions `format_*()` dédiées, une par type d'événement
- Templates en Markdown Telegram (**gras**, `` `monospace` ``)
- Format unifié : emoji + titre + timestamp + infos clés
- Méthodes legacy conservées pour compatibilité ascendante
- Parser Markdown automatique via `parse_mode="Markdown"`

**8 formats implémentés** :
1. `format_startup()` — Bot démarrage (🟢)
2. `format_trade_buy()` — Achat paper (✅)
3. `format_trade_sell()` — Vente paper avec PnL (✅)
4. `format_kill_switch()` — Drawdown stop (🔴)
5. `format_feed_down()` — Feed prix déconnecté (⚠️)
6. `format_feed_ok()` — Feed rétabli (🟢)
7. `format_daily_report()` — Rapport du jour (📊)
8. `format_wallet_low()` — Cash faible (🟠)

---

### 2. **src/notify/dispatcher.py** — NOUVEAU module

**Responsabilité** : Rate limiting + idempotence + state tracking

**Méthodes publiques** :

| Méthode | Rôle | Rate Limit |
|---------|------|------------|
| `should_send_startup()` | Vérifier si startup peut s'envoyer | 1 / 6h |
| `mark_startup_sent()` | Enregistrer timestamp startup | — |
| `should_send_feed_down()` | Feed n'est pas déjà DOWN | Transition only |
| `mark_feed_down()` | Marquer feed DOWN + downtime start | — |
| `should_send_feed_ok()` | Feed était DOWN, redevient OK | Transition only |
| `mark_feed_ok()` | Marquer feed OK + reset downtime | — |
| `get_feed_downtime_seconds()` | Durée du downtime | — |
| `should_send_wallet_low()` | Cash bas, peut envoyer alerte | 1 / 60min |
| `mark_wallet_low_sent()` | Enregistrer timestamp wallet alert | — |
| `should_send_daily_report(date)` | Pas encore envoyé aujourd'hui | 1 / jour |
| `mark_daily_report_sent(date)` | Enregistrer date rapport | — |
| `should_send_trade(trade_id)` | Trade ID unique (idempotent) | Aucun |
| `mark_trade_sent(trade_id)` | Enregistrer trade notifié | — |

**État persisté dans `bot_state`** :

```
last_startup_notif_ts        (float epoch)
feed_status                  ("ok" / "down")
feed_down_since_ts           (float epoch ms)
last_wallet_low_notif_ts     (float epoch)
last_daily_report_date       (YYYY-MM-DD)
trade_notif_{trade_id}       ("1") — per trade
```

---

### 3. **src/main_live.py** — Intégration dispatcher

**Imports ajoutés** :
```python
from src.notify.dispatcher import TelegramDispatcher
```

**Changements** :

#### a) `main()` 
- Initialise dispatcher : `dispatcher = TelegramDispatcher(db=db, tz_name=settings.report_tz)`
- Check startup rate limit avant `notifier.notify_bot_start()` → remplacé par:
  ```python
  if dispatcher.should_send_startup():
      text = notifier.format_startup(...)
      notifier.send_message(text)
      dispatcher.mark_startup_sent()
  ```

#### b) `process_once(db, broker, strategy, notifier, dispatcher, settings)`
- Param ajouté : `dispatcher`
- **Feed down/ok** : Utilise `dispatcher.should_send_feed_down/ok()` avant d'envoyer
  ```python
  if dispatcher.should_send_feed_down():
      text = notifier.format_feed_down(...)
      notifier.send_message(text)
      dispatcher.mark_feed_down()
  ```
- **Trade** : Utilise `dispatcher.should_send_trade(trade_id)` 
  ```python
  if result.executed and dispatcher.should_send_trade(result.trade_id):
      notifier.notify_trade(...)
      dispatcher.mark_trade_sent(result.trade_id)
  ```
- **Kill switch** : Envoie directement (pas de rate limit par directive)
  ```python
  text = notifier.format_kill_switch(...)
  notifier.send_message(text)
  ```

#### c) `_maybe_send_daily_report(..., dispatcher, ...)`
- Check : `if dispatcher.should_send_daily_report(current_local_day):`
- Mark : `dispatcher.mark_daily_report_sent(current_local_day)`

---

## 📊 Exemple de Réponse — Les 8 Templates

### 1. 🟢 STARTUP

```
**🟢 PAPER BOT — DÉMARRÉ**
`BTCUSDT • 1m • Europe/Paris`
⏱️ `00:32:48 | 2026-03-03`
Mode: `LIVE` | Source: `Binance REST` | Version: `1.0.0` | DB: `postgres`
```

### 2. ✅ BUY

```
**✅ BUY — BTCUSDT (PAPER)**
⏱️ `00:32:48 | 2026-03-03`
Prix: `42500.50` → `42510.75` (slip `0.02%`)
Taille: `0.001234 BTC` | Fee: `1.25 USDT`
Wallet: `9998.75 USDT` + `0.005678 BTC` | Eq: `10239.12`
Signal: MA10/MA30 crossover
```

### 3. ✅ SELL (avec PnL)

```
**✅ SELL — BTCUSDT (PAPER)**
⏱️ `00:32:48 | 2026-03-03`
Prix: `43200.25` → `43190.00` (slip `0.02%`)
Taille: `0.001234 BTC` | Fee: `1.35 USDT`
PnL trade: `+53.12 USDT` (`+3.95%`) | Day: `+53.12`
Wallet: `10053.89 USDT` + `0.004444 BTC` | Eq: `10244.67`
Signal: MA10 < MA30
```

### 4. 🔴 KILL SWITCH

```
**🔴 KILL SWITCH — TRADING STOP**
⏱️ `00:32:48 | 2026-03-03`
Drawdown: `15.75%` (seuil `10.00%`)
Equity: `9754.32 USDT`
Position: `Flat`
Action: Aucun nouvel ordre
```

### 5. ⚠️ FEED DOWN

```
**⚠️ DATA FEED DOWN — Binance REST**
⏱️ `00:32:48 | 2026-03-03`
Erreur: Connection timeout (30s)
Retry: `#1` | Backoff: `1.5s`
Mode: `Monitoring`
```

### 6. 🟢 FEED OK

```
**🟢 DATA FEED OK — Binance REST**
⏱️ `00:32:48 | 2026-03-03`
Downtime: `47s`
```

### 7. 📊 DAILY REPORT

```
**📊 DAILY REPORT — PAPER BTC (2026-03-03)**
Timezone: `Europe/Paris`
Equity: `10000.00` → `10244.67` | PnL: `+244.67` (`+2.45%`)
Trades: `5` (B `2` / S `3`) | Win: `80.0%` | Fees: `6.89`
Max DD: `8.50%` | Position: `0.004444 BTC` | Cash: `10053.89 USDT`
BTC ref: `43200.25` | Exposure: `17.2%`
```

### 8. 🟠 WALLET LOW CASH

```
**🟠 WALLET LOW CASH**
⏱️ `00:32:48 | 2026-03-03`
Cash: `500.50 USDT` (seuil `1000.00`)
Statut: `WARN`
Action: Reduce order size by 50%
```

---

## ✅ Validation

### Code Checks
- ✅ 0 erreurs de syntaxe (telegram.py, dispatcher.py, main_live.py)
- ✅ Imports + types vérifiés
- ✅ Compatibilité ascendante conservée (méthodes legacy)

### Functional Tests
- ✅ Toutes les 8 signatures `format_*()` testées (test_new_notifications.py)
- ✅ Output Markdown valide pour Telegram
- ✅ Timestamps en Europe/Paris correct
- ✅ Champs dans le bon ordre

### Rate Limiting Logic
- ✅ STARTUP : 6h entre envois (timestamp epoch)
- ✅ FEED_DOWN/OK : Transition based (feed_status state)
- ✅ WALLET_LOW : 1/h (timestamp epoch)
- ✅ DAILY_REPORT : 1/jour (date YYYY-MM-DD)
- ✅ TRADE : Idempotent via trade_id

---

## 🚀 Prochaines Étapes

1. **Déploiement en prod** : Les fichiers modifiés sont prêts
   - Copier vers `/opt/paper-btc-bot/`
   - Redémarrer service : `sudo systemctl restart paper-btc-bot`

2. **Observation** : Vérifier logs Telegram pendant 24h
   - Pas de doublons startup
   - Feed down/ok cohérent
   - Daily report 1/jour
   - Trades notifiés une fois

3. **Ajustements** : Si besoin, modifier rate limits dans dispatcher (RATE_LIMITS dict)

---

## 📝 Fichiers Modifiés

1. [src/notify/telegram.py](src/notify/telegram.py) — Refactorisation complète + 8 formats
2. [src/notify/dispatcher.py](src/notify/dispatcher.py) — NOUVEAU : rate limiting + state
3. [src/main_live.py](src/main_live.py) — Intégration dispatcher

## 🧪 Test Script

Exécutable : [test_new_notifications.py](test_new_notifications.py)
```bash
python3 test_new_notifications.py
```
Affiche tous les 8 formats Markdown sans envoyer de messages.

---

**Statut** : ✅ Implémentation complète et validée
