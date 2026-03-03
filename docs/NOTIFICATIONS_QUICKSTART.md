# 🎯 Notifications Telegram Refactorisées — Quick Start

## ✅ Implémentation Complète

La refonte des notifications Telegram a été **complètement implémentée et testée**.

### État
- ✅ 3 fichiers Python modifiés/créés
- ✅ 8 templates Markdown implémentés
- ✅ Dispatcher anti-spam + rate limiting
- ✅ Tous les tests passants
- ✅ Documentation complète

---

## 📦 Fichiers Concernés

### **Code (à déployer)**
```
src/notify/telegram.py       ← Refactorisé (8 formats)
src/notify/dispatcher.py     ← NOUVEAU (rate limiting)
src/main_live.py             ← Intégré dispatcher
```

### **Tests & Exemples (locaux)**
```
test_new_notifications.py    ← Affiche les 8 templates
example_notifications.py     ← Démo dispatcher
```

### **Documentation**
```
NOTIFICATION_REFACTOR.md     ← Détails techniques
DEPLOY_NOTIFICATIONS.md      ← Guide déploiement
IMPLEMENTATION_SUMMARY.md    ← Résumé complet
CHANGES.txt                  ← Changelog court
```

---

## 🚀 Déploiement en 5 Étapes

```bash
# 1. Backup
sudo cp /opt/paper-btc-bot/src/notify/telegram.py \
        /opt/paper-btc-bot/src/notify/telegram.py.backup

# 2. Copier les fichiers
sudo cp src/notify/telegram.py /opt/paper-btc-bot/src/notify/
sudo cp src/notify/dispatcher.py /opt/paper-btc-bot/src/notify/
sudo cp src/main_live.py /opt/paper-btc-bot/src/

# 3. Vérifier syntaxe
sudo -u paperbot /opt/paper-btc-bot/.venv/bin/python3 -m py_compile \
    /opt/paper-btc-bot/src/notify/telegram.py \
    /opt/paper-btc-bot/src/notify/dispatcher.py \
    /opt/paper-btc-bot/src/main_live.py

# 4. Redémarrer
sudo systemctl restart paper-btc-bot

# 5. Vérifier logs
sudo journalctl -u paper-btc-bot -f
```

---

## ✨ 8 Nouveaux Templates

| # | Événement | Emoji | Rate Limit |
|---|-----------|-------|-----------|
| 1 | Startup | 🟢 | 1/6h |
| 2 | Buy | ✅ | idempotent |
| 3 | Sell | ✅ | idempotent |
| 4 | Kill Switch | 🔴 | aucun |
| 5 | Feed Down | ⚠️ | transition |
| 6 | Feed OK | 🟢 | transition |
| 7 | Daily Report | 📊 | 1/jour |
| 8 | Wallet Low | 🟠 | 1/h |

---

## 🔍 Vérifier l'Installation

### En local (avant déploiement)
```bash
# Voir tous les 8 templates
python3 test_new_notifications.py

# Test dispatcher
python3 example_notifications.py
```

### En prod (après déploiement)
```bash
# Vérifier que le bot démarre
sudo systemctl status paper-btc-bot

# Attendre un trade et vérifier Telegram
sudo journalctl -u paper-btc-bot -f | grep "✅\|🟢\|⚠️"

# Vérifier pas de doublons après redémarrage
sudo systemctl restart paper-btc-bot
# → Un seul message 🟢 PAPER BOT — DÉMARRÉ doit arriver (rate limit 1/6h)
```

---

## 📊 Avant/Après

### Avant
```
[PAPER][BTC] BUY exécuté
Time: 14:32:48
Market: 42500.0
Exec: 42510.5
```

### Après
```
**✅ BUY — BTCUSDT (PAPER)**
⏱️ `14:32:48 | 2026-03-03`
Prix: `42500.00` → `42510.75` (slip `0.02%`)
...
```

---

## 🛠 Configuration

Tous les rate limits sont dans [src/notify/dispatcher.py](src/notify/dispatcher.py) :

```python
RATE_LIMITS = {
    "startup": 6 * 3600,      # 1 par 6 heures
    "wallet_low": 3600,       # 1 par heure
    "daily_report": 86400,    # 1 par jour
    # feed_down/ok: transition-based (no time limit)
    # trade: idempotent (no time limit)
}
```

Besoin d'ajuster ? Éditer et redémarrer le service.

---

## 📖 Documentation Complète

- [NOTIFICATION_REFACTOR.md](NOTIFICATION_REFACTOR.md) — Implémentation technique
- [DEPLOY_NOTIFICATIONS.md](DEPLOY_NOTIFICATIONS.md) — Guide déploiement détaillé
- [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) — Résumé complet avec exemples
- [CHANGES.txt](CHANGES.txt) — Changelog court

---

## ❓ Questions?

- **Comment revenir à l'ancienne version ?**
  ```bash
  sudo cp /opt/paper-btc-bot/src/notify/telegram.py.backup \
          /opt/paper-btc-bot/src/notify/telegram.py
  sudo systemctl restart paper-btc-bot
  ```

- **Peut-on déboguer les notifications ?**
  ```bash
  sudo journalctl -u paper-btc-bot | grep -i telegram
  ```

- **Comment ajouter un nouveau type de notification ?**
  1. Ajouter `format_nouveau()` dans telegram.py
  2. Ajouter `should_send_nouveau()` + `mark_nouveau_sent()` dans dispatcher.py
  3. Appeler dans main_live.py

---

**Prêt à déployer ?** → Suivez les 5 étapes ci-dessus. ✅
