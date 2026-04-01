# BioCoach — PostgreSQL: Docker → Host Migration

> Created: 2026-04-01
> Goal: Move PostgreSQL from Docker container to host for easier administration, extensions, and backups.
> Priority: Execute AFTER nginx migration (ROUND_NGINX) — reduces Docker dependency step by step.
> Estimated downtime: 2–3 minutes.

---

## Current State

| Param | Value |
|-------|-------|
| Container | `biocoach-postgres-1` (postgres:16-alpine) |
| Version | PostgreSQL 16.13 (Alpine musl) |
| Database | `biocoach` (~8 MB) |
| Tables | 8 (users, domains, domain_types, auth_codes, refresh_tokens, chat_sessions, chat_messages, bot_contacts) |
| RLS policies | 3 (domain_isolation, session_isolation, message_isolation) |
| Roles | `biocoach` (superuser), `biocoach_app` (no login) |
| Extensions | plpgsql only |
| Data volume | Docker volume `pgdata` |
| Connection string | `postgresql://biocoach:biocoach_secret@postgres:5432/biocoach` |
| Host PG installed | No — available in apt: `postgresql-16` 16.13 |

---

## Architecture: Before → After

### Before
```
api container ──(Docker network)──→ postgres container:5432
                                     └─ volume: pgdata
```

### After
```
api container ──(127.0.0.1:5432)──→ host PostgreSQL:5432
                                     └─ /var/lib/postgresql/16/main/
```

---

## Task PG.1 — Install PostgreSQL 16 on Host

```bash
sudo apt update
sudo apt install -y postgresql-16 postgresql-client-16

# Verify
sudo systemctl status postgresql
psql --version   # expect 16.x
```

Expected: ~50 MB disk, ~25 MB RSS idle.

---

## Task PG.2 — Configure Host PostgreSQL

### Memory tuning for 8 GB RAM / 10 users

File: `/etc/postgresql/16/main/postgresql.conf`
```ini
# Connection
listen_addresses = '127.0.0.1,172.17.0.1'   # localhost + docker bridge
port = 5432
max_connections = 50                          # MVP: 10 users + pool

# Memory (conservative for 8 GB total, many services)
shared_buffers = 256MB          # ~3% of RAM
effective_cache_size = 1GB
work_mem = 4MB
maintenance_work_mem = 64MB
wal_buffers = 8MB

# WAL
wal_level = replica             # enables pg_basebackup later
max_wal_size = 256MB
min_wal_size = 64MB

# Logging
log_destination = 'stderr'
logging_collector = on
log_directory = '/var/log/postgresql'
log_filename = 'postgresql-%Y-%m-%d.log'
log_rotation_age = 1d
log_rotation_size = 50MB
log_min_duration_statement = 500   # log slow queries > 500ms
log_line_prefix = '%t [%p] %u@%d '

# Locale
lc_messages = 'en_US.UTF-8'
```

### Authentication

File: `/etc/postgresql/16/main/pg_hba.conf`
```
# TYPE  DATABASE  USER       ADDRESS         METHOD
local   all       postgres                   peer
local   all       biocoach                   scram-sha-256

# Docker containers connect via docker bridge
host    biocoach  biocoach   172.16.0.0/12   scram-sha-256

# Localhost
host    biocoach  biocoach   127.0.0.1/32    scram-sha-256
```

### Apply and restart
```bash
sudo systemctl restart postgresql
sudo systemctl enable postgresql
```

---

## Task PG.3 — Create Roles and Database

```bash
sudo -u postgres psql << 'SQL'
-- Create role with strong password (change from default!)
CREATE ROLE biocoach WITH LOGIN PASSWORD 'biocoach_secret' 
    NOSUPERUSER NOCREATEDB NOCREATEROLE;

-- Create database
CREATE DATABASE biocoach OWNER biocoach 
    ENCODING 'UTF8' LC_COLLATE 'en_US.UTF-8' LC_CTYPE 'en_US.UTF-8'
    TEMPLATE template0;

-- IMPORTANT: biocoach should NOT be superuser in production.
-- The Docker setup had it as superuser — we fix that now.
-- RLS requires the connecting role to NOT bypass RLS.
SQL
```

### Security note
In Docker, `biocoach` was **superuser with Bypass RLS** — this means RLS policies were not actually enforced! On host, we create it as a regular user, so RLS actually works. This is a **security improvement**.

However, verify that the application code does not rely on superuser privileges:
- `SET LOCAL app.current_domain = ...` — works for any role
- Schema DDL (migrations) — needs separate migration role or run as postgres

### Migration role (for Alembic/schema changes)
```sql
-- Separate role for migrations only
CREATE ROLE biocoach_admin WITH LOGIN PASSWORD '<strong_password>'
    NOSUPERUSER CREATEDB;
GRANT ALL ON DATABASE biocoach TO biocoach_admin;
```

---

## Task PG.4 — Migrate Data

### Dump from Docker container
```bash
# Full dump with roles-compatible format
docker exec biocoach-postgres-1 pg_dump -U biocoach -d biocoach \
    --no-owner --no-privileges --format=plain \
    > /tmp/biocoach_dump.sql

# Verify dump
head -20 /tmp/biocoach_dump.sql
wc -l /tmp/biocoach_dump.sql
grep -c "CREATE TABLE" /tmp/biocoach_dump.sql   # expect 8
```

### Restore to host
```bash
sudo -u postgres psql -d biocoach < /tmp/biocoach_dump.sql

# Verify
sudo -u postgres psql -d biocoach -c '\dt'              # 8 tables
sudo -u postgres psql -d biocoach -c 'SELECT count(*) FROM users;'
sudo -u postgres psql -d biocoach -c "SELECT tablename, policyname FROM pg_policies;"  # 3 policies
```

### Fix ownership
```bash
sudo -u postgres psql -d biocoach << 'SQL'
-- Grant schema access
GRANT USAGE ON SCHEMA public TO biocoach;
GRANT ALL ON ALL TABLES IN SCHEMA public TO biocoach;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO biocoach;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO biocoach;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO biocoach;
SQL
```

### Verify RLS works
```bash
# As biocoach role (not postgres), RLS should filter
PGPASSWORD=biocoach_secret psql -h 127.0.0.1 -U biocoach -d biocoach -c \
    "SET app.current_domain = '00000000-0000-0000-0000-000000000000'; SELECT count(*) FROM chat_sessions;"
# Expect: 0 (fake domain_id, RLS blocks)
```

---

## Task PG.5 — Update docker-compose.yml

### Remove postgres service
```yaml
services:
  # DELETE the postgres service block entirely
  # DELETE the pgdata volume

  api:
    # ...existing config...
    # REMOVE depends_on postgres
    depends_on:
      nats:
        condition: service_healthy
    # Add docker bridge access
    extra_hosts:
      - "host.docker.internal:host-gateway"
    networks:
      - biocoach
```

### Update `.env`
```env
# BEFORE:
DATABASE_URL=postgresql://biocoach:biocoach_secret@postgres:5432/biocoach

# AFTER:
DATABASE_URL=postgresql://biocoach:biocoach_secret@host.docker.internal:5432/biocoach
```

Alternative to `host.docker.internal`: use the Docker bridge IP directly:
```env
DATABASE_URL=postgresql://biocoach:biocoach_secret@172.17.0.1:5432/biocoach
```
`host.docker.internal` is cleaner but requires `extra_hosts` mapping in compose.

---

## Task PG.6 — Backups (cron)

### Daily pg_dump
```bash
sudo mkdir -p /var/backups/postgresql
sudo chown postgres:postgres /var/backups/postgresql
```

File: `/etc/cron.d/biocoach-backup`
```cron
# Daily backup at 03:00 UTC, keep 7 days
0 3 * * * postgres pg_dump -U postgres -d biocoach --format=custom -f /var/backups/postgresql/biocoach_$(date +\%Y\%m\%d).dump 2>/dev/null
# Cleanup old backups
10 3 * * * postgres find /var/backups/postgresql -name "biocoach_*.dump" -mtime +7 -delete 2>/dev/null
```

### Test restore procedure
```bash
# Create test DB, restore into it, verify
sudo -u postgres createdb biocoach_test
sudo -u postgres pg_restore -d biocoach_test /var/backups/postgresql/biocoach_YYYYMMDD.dump
sudo -u postgres psql -d biocoach_test -c '\dt'
sudo -u postgres dropdb biocoach_test
```

---

## Task PG.7 — Future Extensions (Phase 2 prep)

With host PostgreSQL, installing extensions is trivial:
```bash
# Apache AGE (graph queries) — when needed
sudo apt install postgresql-16-age
sudo -u postgres psql -d biocoach -c "CREATE EXTENSION age;"

# pgvector (embeddings) — when needed  
sudo apt install postgresql-16-pgvector
sudo -u postgres psql -d biocoach -c "CREATE EXTENSION vector;"
```

No custom Docker images, no rebuild cycles.

---

## Activation Sequence

```
Step 1: Install host PostgreSQL
           sudo apt install -y postgresql-16

Step 2: Configure (postgresql.conf, pg_hba.conf)
           sudo systemctl restart postgresql

Step 3: Create role + database on host
           sudo -u postgres psql ...

Step 4: Dump from Docker
           docker exec biocoach-postgres-1 pg_dump ... > /tmp/biocoach_dump.sql

Step 5: Restore to host
           sudo -u postgres psql -d biocoach < /tmp/biocoach_dump.sql
           Grant permissions to biocoach role

Step 6: Verify data on host
           psql: table count, row counts, RLS policies

--- DOWNTIME STARTS HERE (~2 min) ---

Step 7: Stop API container
           docker compose stop api

Step 8: Update .env (DATABASE_URL → host)
           Update docker-compose.yml (remove postgres service, add extra_hosts)

Step 9: Restart
           docker compose up -d

Step 10: Verify
           curl https://agentdata.pro/api/health
           Send a chat message — verify it persists

--- DOWNTIME ENDS ---

Step 11: Cleanup (after 24h of stable operation)
           docker compose down   # if old postgres container lingers
           docker volume rm biocoach_pgdata   # free disk
```

### Rollback plan
If host PG fails:
```bash
# Revert .env
DATABASE_URL=postgresql://biocoach:biocoach_secret@postgres:5432/biocoach
# Revert docker-compose.yml (add postgres service back)
docker compose up -d
# Data is still in Docker volume (not deleted until Step 11)
```

---

## Success Criteria

- [ ] Host PostgreSQL running, `systemctl status postgresql` = active
- [ ] `psql -h 127.0.0.1 -U biocoach -d biocoach` — connects
- [ ] 8 tables, 3 RLS policies, data matches Docker dump
- [ ] API container connects to host PG, `/api/health` = 200
- [ ] Chat works: send message, check it's in host DB
- [ ] RLS enforced (biocoach role is NOT superuser, NOT bypass RLS)
- [ ] Daily backup cron active
- [ ] Docker postgres container and volume removed (after stabilization)
- [ ] `apt install postgresql-16-age` works (extension readiness)
