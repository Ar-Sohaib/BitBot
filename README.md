# Paper BTC Bot (MVP)

Implémentation du projet décrit dans `project.md` : paper trading BTC autonome, feed public, stratégie MA cross, broker simulé (fees + slippage), PostgreSQL, notifications Telegram, reporting journalier.

## Structure

```
src/
  main_live.py           # Boucle live paper (24/7)
  main_backtest.py       # Replay sur candles en base
  config.py              # Configuration via .env
  models.py              # Types partagés
  price_feed/
    rest_provider.py     # Provider REST Binance public
  strategy/
    base.py              # Interface Strategy
    ma_cross.py          # Stratégie MA cross
  broker/
    paper_broker.py      # Exécution paper + risque/idempotence
    risk.py              # Calculs equity/drawdown
  storage/
    db.py                # Persistence PostgreSQL
    schema.sql           # Schéma DB
  analytics/
    metrics.py           # Winrate, max DD
    daily_report.py      # Rapport quotidien
  notify/
    telegram.py          # Notifications Telegram
  scripts/
    init_db.py           # Initialisation de la base
    import_candles.py    # Import historique CSV/API
deploy/
  paper-btc-bot.service  # Service systemd
  deploy.sh              # Script de déploiement VPS
tests/
  broker/                # Tests paper broker (basiques + avancés)
  notify/                # Tests Telegram (mock HTTP)
  analytics/             # Tests metrics + daily report
  price_feed/            # Tests REST provider (mock HTTP)
```

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Éditer .env avec vos paramètres
# Obligatoire : POSTGRES_DSN=postgresql://user:pass@host:5432/dbname
python -m src.scripts.init_db
```

## Import candles historiques (pour backtest)

```bash
# Via l'API Binance (30 derniers jours) :
python -m src.scripts.import_candles --fetch --days 30

# Via CSV :
python -m src.scripts.import_candles --csv data/btcusdt_1m.csv
```

## Exécution live

```bash
python -m src.main_live
```

## Backtest (sur candles en base)

```bash
python -m src.main_backtest
```

## Tests

```bash
python -m unittest discover -s tests -p "test_*.py"
```

## Déploiement VPS (systemd)

```bash
# Sur le VPS :
sudo bash deploy/deploy.sh

# Vérifier :
sudo systemctl status paper-btc-bot
sudo journalctl -u paper-btc-bot -f
```

Le script crée un user dédié `paperbot`, installe le venv, initialise le schéma PostgreSQL, et active le service systemd avec redémarrage automatique.

## Notes

- Sans `TELEGRAM_ENABLE=true` + token/chat_id, les notifications sont silencieusement désactivées.
- Le feed REST est public (Binance), sans API key.
- Le système est paper trading uniquement (aucun ordre réel).
- Les secrets (.env) ne doivent jamais être commités (inclus dans .gitignore).
