# Database Migrations

This directory contains SQL migration files for BitBot database schema updates.

## Overview

Migrations are applied automatically when BitBot starts. Each migration file is executed once and any errors (e.g., "column already exists") are safely ignored.

## Migration Files

### 001_add_notification_tracking.sql

**Purpose**: Add notification tracking and recovery mode support

**Changes**:
- Add `notif_sent` (BOOLEAN) and `notif_sent_at` (BIGINT) columns to `trades` table
- Create `sent_notifications` table for deduplication
- Add performance indexes

**Compatibility**: SQLite and PostgreSQL

**Applied**: Automatically on first startup after update

## How Migrations Work

### Automatic Application

1. Bot starts → scans `migrations/` directory
2. Executes each `.sql` file in alphabetical order
3. Catches and logs "already exists" errors (safe to ignore)
4. Continues startup normally

**Code**: `src/storage/db.py` - `run_migration()` method

### Manual Application (if needed)

**SQLite**:
```bash
sqlite3 data/paper.db < migrations/001_add_notification_tracking.sql
```

**PostgreSQL**:
```bash
psql -U user -d bitbot -f migrations/001_add_notification_tracking.sql
```

## Creating New Migrations

### Naming Convention

Format: `NNN_short_description.sql`

Examples:
- `001_add_notification_tracking.sql`
- `002_add_user_preferences.sql`
- `003_optimize_candles_index.sql`

### Template

```sql
-- Migration: Brief description
-- Compatible with both SQLite and PostgreSQL

-- Your schema changes here
ALTER TABLE table_name ADD COLUMN new_column TYPE;

-- Create new tables if needed
CREATE TABLE IF NOT EXISTS new_table (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_name ON table(column);
```

### Testing

1. **SQLite**: Test on fresh database
   ```bash
   rm data/test.db
   python -c "from src.storage.db import Database; from pathlib import Path; db = Database(Path('data/test.db')); db.init_schema(Path('src/storage/schema.sql')); db.run_migration(Path('migrations/YOUR_MIGRATION.sql'))"
   ```

2. **PostgreSQL**: Test on development database
   ```bash
   psql -U user -d bitbot_dev -f migrations/YOUR_MIGRATION.sql
   ```

3. **Idempotence**: Run twice, verify no errors
   ```bash
   psql -U user -d bitbot_dev -f migrations/YOUR_MIGRATION.sql  # Should succeed
   psql -U user -d bitbot_dev -f migrations/YOUR_MIGRATION.sql  # Should be safe
   ```

## Best Practices

### DO ✅

- Use `IF NOT EXISTS` for CREATE statements
- Handle both SQLite and PostgreSQL syntax
- Add indexes for new query patterns
- Keep migrations small and focused
- Test on both database types
- Document what and why

### DON'T ❌

- Drop tables or columns (breaks old versions)
- Use database-specific syntax without fallbacks
- Change existing column types (risky)
- Depend on data being present
- Modify existing migration files after release

## Rollback Strategy

**Important**: Migrations are forward-only. There is no automatic rollback.

### If Migration Fails

1. **Stop bot immediately**
   ```bash
   pkill -f main_live.py
   ```

2. **Restore from backup**
   
   SQLite:
   ```bash
   cp data/paper.db.backup data/paper.db
   ```
   
   PostgreSQL:
   ```bash
   dropdb bitbot
   createdb bitbot
   psql -U user -d bitbot < bitbot_backup.sql
   ```

3. **Fix migration file**
4. **Restart bot**

### Prevention

- Always backup before starting bot after updates
- Test migrations on development database first
- Use staging environment for major updates

## Migration History

| File | Version | Description | Date |
|------|---------|-------------|------|
| `001_add_notification_tracking.sql` | 1.0 | Resume mode support | 2026-03-03 |

## Troubleshooting

### "Column already exists"

**Status**: ✅ Normal (migration already applied)

**Action**: None - safely ignored by bot

### "Table already exists"

**Status**: ✅ Normal (migration already applied)

**Action**: None - safely ignored by bot

### "Syntax error near..."

**Status**: ❌ Error - migration not compatible

**Action**:
1. Check database type (SQLite vs PostgreSQL)
2. Review migration file syntax
3. Open GitHub issue with error details

### Migration Never Runs

**Check**:
1. File in `migrations/` directory? `ls migrations/`
2. File ends with `.sql`? `ls migrations/*.sql`
3. File readable? `cat migrations/001_*.sql`

**Logs**: Check `logs/app.log` for migration messages

## Support

For migration issues:
1. Check this README
2. Review logs in `logs/app.log`
3. Verify database type and connection
4. Open GitHub issue with:
   - Migration file name
   - Database type (SQLite/PostgreSQL)
   - Error message
   - Log excerpt
