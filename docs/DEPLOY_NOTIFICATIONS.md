# 🚀 Guide de Déploiement — Notifications Refactorisées

## 📌 Contexte

La refonte des notifications Telegram a été complétée. Le système est maintenant :
- ✅ Lisible (messages compacts, < 2s)
- ✅ Ergonomique (emojis, Markdown, structure cohérente)
- ✅ Anti-spam (rate limiting + idempotence)
- ✅ Standardisé (8 templates avec champs unifiés)

## 📦 Fichiers à Déployer

3 fichiers modifiés + 2 fichiers de test/exemple :

```
src/notify/telegram.py          (refactorisé)
src/notify/dispatcher.py        (NOUVEAU)
src/main_live.py               (intégré dispatcher)
test_new_notifications.py       (test des 8 formats)
example_notifications.py        (exemple d'utilisation)
NOTIFICATION_REFACTOR.md        (doc complète)
```

## 🔄 Déploiement en Production

### Option 1 : Manuel (recommandé pour vérification)

```bash
# 1. Backups des fichiers actuels
sudo cp /opt/paper-btc-bot/src/notify/telegram.py \
        /opt/paper-btc-bot/src/notify/telegram.py.backup

# 2. Copier les fichiers modifiés
sudo cp src/notify/telegram.py /opt/paper-btc-bot/src/notify/
sudo cp src/notify/dispatcher.py /opt/paper-btc-bot/src/notify/
sudo cp src/main_live.py /opt/paper-btc-bot/src/

# 3. Vérifier la syntaxe (en tant que paperbot)
sudo -u paperbot /opt/paper-btc-bot/.venv/bin/python3 -m py_compile \
    /opt/paper-btc-bot/src/notify/telegram.py \
    /opt/paper-btc-bot/src/notify/dispatcher.py \
    /opt/paper-btc-bot/src/main_live.py

# 4. Redémarrer le service
sudo systemctl restart paper-btc-bot

# 5. Vérifier les logs
sudo journalctl -u paper-btc-bot -f
```

### Option 2 : Via script déploiement (si présent)

```bash
bash deploy/deploy.sh
```

## ✅ Vérifications Post-Déploiement

### 1. Le service démarre correctement

```bash
sudo systemctl status paper-btc-bot
# Doit être "active (running)"
```

### 2. Les logs ne montrent pas d'erreurs

```bash
sudo journalctl -u paper-btc-bot -n 50 | grep -i error
# Doit être vide (ou erreurs existantes)
```

### 3. Notification de démarrage envoyée (une fois en 6h)

```bash
sudo journalctl -u paper-btc-bot | grep "🟢 PAPER BOT — DÉMARRÉ"
# Ou vérifier dans Telegram qu'un message est arrivé
```

### 4. Premier trade généré correctement

Attendez un trade, puis vérifier :
```bash
sudo journalctl -u paper-btc-bot | grep "✅ BUY\|✅ SELL"
# Ou vérifier dans Telegram un message de trade
```

## 🔧 Configuration

Aucun fichier de config à modifier. Les taux de rate limiting sont codés en dur dans [src/notify/dispatcher.py](src/notify/dispatcher.py) :

```python
RATE_LIMITS = {
    "startup": 6 * 3600,      # 1 per 6h
    "feed_down": 60,          # Only 1 per incident
    "feed_ok": 60,            # Only 1 per incident
    "wallet_low": 3600,       # 1 per hour
    "trade": 0,               # No limit (idempotent)
    "daily_report": 86400,    # 1 per day
}
```

Pour ajuster : éditer `/opt/paper-btc-bot/src/notify/dispatcher.py` et redémarrer.

## 📊 État Persisté (Bot State)

Les clés suivantes sont stockées dans la base de données `bot_state` :

| Clé | Type | Durée | Rôle |
|-----|------|-------|------|
| `last_startup_notif_ts` | float (epoch) | 6h | Rate limit startup |
| `feed_status` | "ok" / "down" | Jusqu'à changement | État feed |
| `feed_down_since_ts` | float (epoch ms) | Jusqu'à OK | Calcul downtime |
| `last_wallet_low_notif_ts` | float (epoch) | 1h | Rate limit wallet |
| `last_daily_report_date` | YYYY-MM-DD | Jusqu'à minuit | 1 rapport/jour |
| `trade_notif_{id}` | "1" | Permanent | Idempotence trade |

**Nettoyer l'état** (reset tous les rate limits) :

```bash
# Via PostgreSQL (adapter DSN)
export POSTGRES_DSN='postgresql://user:pass@host:5432/bitbot'
psql "$POSTGRES_DSN" \
    -c "DELETE FROM bot_state WHERE key LIKE 'last_%' OR key LIKE 'feed_%' OR key LIKE 'trade_notif_%';"
```

## 🧪 Tests Locaux (avant déploiement)

Testez les formats localement :

```bash
# Affiche tous les 8 templates Markdown
python3 test_new_notifications.py

# Démontre le flux dispatcher (sans envoyer)
python3 example_notifications.py
```

## 📝 Rollback (si nécessaire)

En cas de problème :

```bash
# Restaurer backup
sudo cp /opt/paper-btc-bot/src/notify/telegram.py.backup \
        /opt/paper-btc-bot/src/notify/telegram.py

# Supprimer dispatcher (reverrà aux méthodes legacy)
sudo rm /opt/paper-btc-bot/src/notify/dispatcher.py

# Revenir à main_live.py simple (sans dispatcher)
# Ou chercher une version antérieure dans git
git checkout HEAD~1 -- src/main_live.py

# Redémarrer
sudo systemctl restart paper-btc-bot
```

## 📋 Checklist Déploiement

- [ ] Fichiers copiés à `/opt/paper-btc-bot/`
- [ ] Syntaxe Python vérifiée (py_compile)
- [ ] Service redémarré sans erreur
- [ ] Logs vérifiés (pas d'erreur)
- [ ] Notification startup arrivée dans Telegram
- [ ] Premier trade notifié correctement
- [ ] Daily report de la veille arrivé (si applicable)
- [ ] Pas de doublons dans les notifications

## ❓ FAQ

### Q: Est-ce que ça va spammer Telegram ?

**A:** Non, le dispatcher rate-limit tous les événements répétitifs. Voir RATE_LIMITS plus haut.

### Q: Dois-je modifier `.env` ?

**A:** Non, les settings restent les mêmes. Assurez-vous juste que `TELEGRAM_ENABLE=true` et tokens/chat_id sont valides.

### Q: Peut-on revenir aux anciens messages ?

**A:** Oui, mais il faudrait revenir la version antérieure de telegram.py et main_live.py.

### Q: Comment déboguer les notifs ?

**A:** Vérifiez les logs :
```bash
sudo journalctl -u paper-btc-bot | grep -i telegram
```

Et dans Telegram, activez le bot avec `/start` pour vérifier la connectivité.

---

**Questions ?** Consultez [NOTIFICATION_REFACTOR.md](NOTIFICATION_REFACTOR.md) pour détails techniques.
