# Refactorisation Notifications Telegram — Documentation Index

## 🎯 Point d'Entrée

Vous êtes ici pour **comprendre, tester, ou déployer** les nouvelles notifications.

Choisissez votre chemin :

### 👤 Je veux déployer rapidement
→ [NOTIFICATIONS_QUICKSTART.md](NOTIFICATIONS_QUICKSTART.md) (5 min)

**Contient :** 5 étapes de déploiement, checklist vérification, FAQ rapide

### 📚 Je veux comprendre la refonte
→ [NOTIFICATION_REFACTOR.md](NOTIFICATION_REFACTOR.md) (détails techniques)

**Contient :** Avant/après, 8 templates, dispatcher, état persisté, validation

### 🚀 Je veux un guide complet de déploiement
→ [DEPLOY_NOTIFICATIONS.md](DEPLOY_NOTIFICATIONS.md) (guide prod)

**Contient :** Déploiement manuel/script, vérifications, config, rollback, tests

### ✅ Je veux un résumé exécutif
→ [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) (rapport complet)

**Contient :** Résumé, avant/après, 8 templates, validation, examples visuels

### 📋 Je veux voir le changelog
→ [CHANGES.txt](CHANGES.txt) (changelog court)

**Contient :** Fichiers créés/modifiés, résumé changements, dispatcher api

---

## 📂 Structure des Fichiers

### Code (Production)
```
src/notify/telegram.py          Refactorisé — 8 format_*() functions
src/notify/dispatcher.py        NOUVEAU — Rate limiting + state tracking
src/main_live.py                Intégré — Appels dispatcher
```

### Tests (Locaux)
```
test_new_notifications.py       Affiche les 8 templates Markdown
example_notifications.py        Démo du dispatcher (rate limiting)
```

### Documentation
```
README_NOTIFICATIONS.md         Ce fichier (index)
NOTIFICATIONS_QUICKSTART.md    Guide rapide (5 min)
NOTIFICATION_REFACTOR.md       Détails techniques (deep dive)
DEPLOY_NOTIFICATIONS.md        Guide déploiement prod
IMPLEMENTATION_SUMMARY.md      Résumé complet avec examples
CHANGES.txt                    Changelog court
```

---

## 🎯 8 Templates Implémentés

| # | Type | Emoji | Rate Limit | Status |
|---|------|-------|-----------|--------|
| 1 | Startup | 🟢 | 1/6h | ✅ |
| 2 | Trade Buy | ✅ | Idempotent | ✅ |
| 3 | Trade Sell (PnL) | ✅ | Idempotent | ✅ |
| 4 | Kill Switch | 🔴 | Aucun | ✅ |
| 5 | Feed Down | ⚠️ | Transition | ✅ |
| 6 | Feed OK (durée) | 🟢 | Transition | ✅ |
| 7 | Daily Report | 📊 | 1/jour | ✅ |
| 8 | Wallet Low | 🟠 | 1/h | ✅ |

---

## 🚀 Déploiement — 3 Variantes

### A. Je veux juste déployer (5 min)
1. Lis [NOTIFICATIONS_QUICKSTART.md](NOTIFICATIONS_QUICKSTART.md)
2. Follow les 5 étapes
3. ✅ Done

### B. Je veux tester d'abord (15 min)
1. Lis [NOTIFICATIONS_QUICKSTART.md](NOTIFICATIONS_QUICKSTART.md)
2. Lance `python3 test_new_notifications.py` (voir les 8 formats)
3. Lance `python3 example_notifications.py` (voir dispatcher en action)
4. Follow les 5 étapes de déploiement
5. ✅ Done

### C. Je veux tout comprendre (30 min)
1. Lis [NOTIFICATION_REFACTOR.md](NOTIFICATION_REFACTOR.md) (technique)
2. Lis [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) (exemples)
3. Lis [DEPLOY_NOTIFICATIONS.md](DEPLOY_NOTIFICATIONS.md) (prod checklist)
4. Lis le code : [src/notify/telegram.py](src/notify/telegram.py) + [src/notify/dispatcher.py](src/notify/dispatcher.py)
5. Lance les tests
6. Follow les 5 étapes
7. ✅ Done

---

## ✨ Highlights

### 🎯 Avant
- Messages logs-like `[PAPER][BTC]`
- Pas de rate limiting → inondation possible
- Pas d'idempotence → doublons
- Formatage inline → code complexe

### ✨ Après
- 8 templates Markdown ergonomiques (emojis, gras, monospace)
- Rate limiting (startup 1/6h, wallet 1/h, report 1/jour)
- Idempotence (trade_id, state keys)
- Code modulaire (format vs dispatch)

---

## 📊 Validation

### Tests Locaux (✅ Tous Passants)
```bash
# Compilation
python3 -m py_compile src/notify/telegram.py src/notify/dispatcher.py src/main_live.py
# → ✅ OK

# Affichage templates
python3 test_new_notifications.py
# → 8 templates générés correctement

# Dispatcher flow
python3 example_notifications.py
# → Rate limiting appliqué, state tracking OK
```

### Vérifications
- ✅ 0 erreurs syntaxe
- ✅ Backward compatible (legacy methods conservées)
- ✅ Timestamps en Europe/Paris
- ✅ Markdown Telegram valide

---

## 🔐 Rate Limiting

Tous les taux sont dans [src/notify/dispatcher.py](src/notify/dispatcher.py) :

```python
RATE_LIMITS = {
    "startup": 6 * 3600,         # 1 startup / 6 heures
    "feed_down": 60,             # Transition-based (no time limit)
    "feed_ok": 60,               # Transition-based (no time limit)
    "wallet_low": 3600,          # 1 alerte / heure
    "trade": 0,                  # Idempotent via trade_id
    "daily_report": 86400,       # 1 rapport / jour
}
```

---

## 💾 État Persisté

Clés stockées dans la table `bot_state` (SQLite) :

| Clé | Type | TTL | Rôle |
|-----|------|-----|------|
| `last_startup_notif_ts` | float (epoch) | 6h | Rate limit startup |
| `feed_status` | "ok" / "down" | Jusqu'à changement | État feed |
| `feed_down_since_ts` | float (epoch ms) | Jusqu'à OK | Calcul downtime |
| `last_wallet_low_notif_ts` | float (epoch) | 1h | Rate limit wallet |
| `last_daily_report_date` | YYYY-MM-DD | Jusqu'à minuit | 1/jour |
| `trade_notif_{id}` | "1" | Permanent | Idempotence |

---

## 🛠 Rollback (Si Nécessaire)

```bash
# Restaurer backup
sudo cp /opt/paper-btc-bot/src/notify/telegram.py.backup \
        /opt/paper-btc-bot/src/notify/telegram.py

# Restart
sudo systemctl restart paper-btc-bot
```

---

## ❓ FAQ Rapide

**Q: Est-ce backward compatible ?**
A: Oui, toutes les méthodes legacy sont conservées.

**Q: Risque de break la prod ?**
A: Faible. Tests locaux passants, backward compat, service en background.

**Q: Comment déboguer ?**
A: `sudo journalctl -u paper-btc-bot | grep telegram`

**Q: Peut-on ajuster les rate limits ?**
A: Oui, éditer [src/notify/dispatcher.py](src/notify/dispatcher.py) ligne ~28

---

## 📞 Support

- **Guide rapide** → [NOTIFICATIONS_QUICKSTART.md](NOTIFICATIONS_QUICKSTART.md)
- **Technique** → [NOTIFICATION_REFACTOR.md](NOTIFICATION_REFACTOR.md)
- **Déploiement** → [DEPLOY_NOTIFICATIONS.md](DEPLOY_NOTIFICATIONS.md)
- **Code** → [src/notify/telegram.py](src/notify/telegram.py) + [src/notify/dispatcher.py](src/notify/dispatcher.py)

---

**Prêt ?** Commencez par [NOTIFICATIONS_QUICKSTART.md](NOTIFICATIONS_QUICKSTART.md) ✅
