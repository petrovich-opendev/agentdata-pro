# BioCoach — Nginx & Firewall Plan: Host Reverse Proxy

> Created: 2026-04-01
> Goal: Single host-level nginx as entry point for all services. Two domains, one IP, only 443+22 open.
> Priority: Execute AFTER Round 1 (chat works) to avoid breaking current build.
> Constraint: DO NOT kill SSH (port 22).

---

## Architecture: Before → After

### Before (current)
```
Internet → :22 (SSH direct to VM)
         → :80/:443 (Docker biocoach-nginx container)
                      ├─ / → web:80 (React)
                      └─ /api/ → api:8000 (FastAPI)

GitLab: localhost:8929 (no external access)
x.oesv.ae: DNS points here, nothing listens
```

### After (target)
```
Internet → :22   (SSH — untouched, VM-level)
         → :443  (Host nginx — single entry point)
                  ├─ agentdata.pro / → localhost:3080 (React, Docker)
                  ├─ agentdata.pro /api/ → localhost:3000 (FastAPI, Docker)
                  └─ x.oesv.ae /gitlab/ → localhost:8929 (GitLab, Docker)

:80 → redirect to HTTPS only (certbot ACME + 301)
All other ports → CLOSED from outside (ufw)
```

---

## Task N.1 — Install and Configure Host Nginx

### Install (minimal footprint)
```bash
sudo apt install -y nginx-light   # ~2MB RAM idle, no extras
```

`nginx-light` — stripped build without mail/perl/image-filter modules. Enough for reverse proxy. Typical RSS: **2–5 MB** (master + 2 workers).

### Tune for low memory
File: `/etc/nginx/nginx.conf`
```nginx
worker_processes 1;               # 1 CPU worker is enough for 10 users
worker_rlimit_nofile 2048;

events {
    worker_connections 512;       # low, sufficient for MVP
}

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    # Logging
    log_format main '$remote_addr - $remote_user [$time_local] '
                    '"$request" $status $body_bytes_sent '
                    '"$http_referer" "$http_user_agent"';
    access_log /var/log/nginx/access.log main buffer=16k flush=5s;
    error_log  /var/log/nginx/error.log warn;

    # Performance
    sendfile        on;
    tcp_nopush      on;
    tcp_nodelay     on;
    keepalive_timeout 65;
    types_hash_max_size 2048;

    # Compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css application/json application/javascript
               text/xml application/xml text/javascript image/svg+xml;

    # Security — hide version
    server_tokens off;

    # Rate limiting zone (auth endpoints)
    limit_req_zone $binary_remote_addr zone=auth:1m rate=5r/m;

    # Block common scanners
    map $request_uri $block_uri {
        default 0;
        ~*\.(git|env|DS_Store|htaccess|htpasswd) 1;
        ~*(xmlrpc|wp-login|wp-admin|phpmyadmin) 1;
    }

    include /etc/nginx/conf.d/*.conf;
    include /etc/nginx/sites-enabled/*;
}
```

---

## Task N.2 — SSL Certificates

### agentdata.pro — already has Let's Encrypt cert
```bash
# Verify existing cert
sudo certbot certificates

# Cert paths (already exist):
# /etc/letsencrypt/live/agentdata.pro/fullchain.pem
# /etc/letsencrypt/live/agentdata.pro/privkey.pem
```

### x.oesv.ae — needs a certificate

**Option A: Let's Encrypt (preferred if DNS allows)**
```bash
sudo certbot certonly --nginx -d x.oesv.ae
```

**Option B: Self-signed (if LE fails — e.g. corporate DNS/firewall)**
```bash
sudo mkdir -p /etc/nginx/ssl
sudo openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
  -keyout /etc/nginx/ssl/x.oesv.ae.key \
  -out /etc/nginx/ssl/x.oesv.ae.crt \
  -subj "/CN=x.oesv.ae"
```

**Recommendation:** Try Let's Encrypt first. x.oesv.ae already resolves to this IP. If it fails (e.g. Cloudflare proxy is on), fall back to self-signed.

### Auto-renewal
```bash
# Certbot timer should already be active
sudo systemctl status certbot.timer

# If not:
sudo systemctl enable --now certbot.timer

# Renewal hook — reload host nginx
sudo tee /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh << 'EOF'
#!/bin/bash
systemctl reload nginx
EOF
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
```

---

## Task N.3 — Site Config: agentdata.pro (BioCoach PaaS)

File: `/etc/nginx/sites-available/agentdata.pro`
```nginx
# HTTP → HTTPS redirect + ACME challenge
server {
    listen 80;
    listen [::]:80;
    server_name agentdata.pro;

    # Let's Encrypt challenge
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name agentdata.pro;

    ssl_certificate     /etc/letsencrypt/live/agentdata.pro/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/agentdata.pro/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    ssl_session_cache   shared:SSL:1m;
    ssl_session_timeout 10m;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Block scanner probes
    if ($block_uri) {
        return 444;
    }

    # React SPA
    location / {
        proxy_pass http://127.0.0.1:3080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # FastAPI
    location /api/ {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection '';

        # SSE streaming support
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
        chunked_transfer_encoding on;
        add_header X-Accel-Buffering no always;
    }

    # Rate limit auth endpoints
    location /api/auth/ {
        limit_req zone=auth burst=3 nodelay;

        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## Task N.4 — Site Config: x.oesv.ae (GitLab)

File: `/etc/nginx/sites-available/x.oesv.ae`
```nginx
server {
    listen 80;
    listen [::]:80;
    server_name x.oesv.ae;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name x.oesv.ae;

    # Use LE or self-signed depending on what worked
    ssl_certificate     /etc/letsencrypt/live/x.oesv.ae/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/x.oesv.ae/privkey.pem;
    # OR if self-signed:
    # ssl_certificate     /etc/nginx/ssl/x.oesv.ae.crt;
    # ssl_certificate_key /etc/nginx/ssl/x.oesv.ae.key;

    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # GitLab proxy
    location /gitlab/ {
        proxy_pass http://127.0.0.1:8929/;   # trailing / strips /gitlab/ prefix
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Ssl on;

        # GitLab needs larger buffers
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
        proxy_busy_buffers_size 256k;
        proxy_read_timeout 300s;

        # WebSocket for live features
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Large repo uploads
        client_max_body_size 250m;
    }

    # Root redirect
    location = / {
        return 302 /gitlab/;
    }

    # Block everything else
    location / {
        return 444;
    }
}
```

### GitLab relative_url configuration
GitLab must know it runs under `/gitlab/`. Update the container:
```bash
# In the GitLab docker run/compose, set:
GITLAB_OMNIBUS_CONFIG="external_url 'https://x.oesv.ae/gitlab'"
```

Then reconfigure GitLab:
```bash
docker exec gitlab gitlab-ctl reconfigure
```

**Important:** GitLab relative URL support requires reconfigure and takes a few minutes. Assets paths change from `/assets/...` to `/gitlab/assets/...`.

---

## Task N.5 — Modify docker-compose.yml (BioCoach)

Remove Docker nginx container; expose web and api on localhost only.

### Changes to `~/biocoach/docker-compose.yml`
```yaml
services:
  # REMOVE the entire nginx service block

  web:
    build: ./web
    ports:
      - "127.0.0.1:3080:80"     # was: expose: ["80"]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:80/"]
      interval: 30s
      timeout: 5s
      retries: 3
    networks:
      - biocoach

  api:
    build:
      context: .
      dockerfile: api/Dockerfile
    ports:
      - "127.0.0.1:3000:8000"   # was: expose: ["8000"]
    env_file:
      - .env
    depends_on:
      postgres:
        condition: service_healthy
      nats:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 30s
    networks:
      - biocoach

  # nats, postgres — unchanged, no external ports (already internal)
```

Key changes:
- **Delete** `nginx` service entirely
- **web**: `expose: ["80"]` → `ports: ["127.0.0.1:3080:80"]`
- **api**: `expose: ["8000"]` → `ports: ["127.0.0.1:3000:8000"]`
- `127.0.0.1` binding = accessible only from host, not from internet

---

## Task N.6 — Firewall (ufw)

### CRITICAL: Order matters. Add SSH FIRST, then enable.

```bash
# 1. Reset to clean state
sudo ufw --force reset

# 2. Default: deny incoming, allow outgoing
sudo ufw default deny incoming
sudo ufw default allow outgoing

# 3. SSH FIRST — before enabling!
sudo ufw allow 22/tcp comment "SSH"

# 4. HTTPS
sudo ufw allow 443/tcp comment "HTTPS"

# 5. HTTP (for certbot ACME + redirects)
sudo ufw allow 80/tcp comment "HTTP-redirect-and-ACME"

# 6. Enable
sudo ufw --force enable

# 7. Verify
sudo ufw status verbose
```

### Expected output:
```
Status: active

To                         Action      From
--                         ------      ----
22/tcp                     ALLOW       Anywhere       # SSH
443/tcp                    ALLOW       Anywhere       # HTTPS
80/tcp                     ALLOW       Anywhere       # HTTP-redirect-and-ACME
```

### Docker + ufw caveat
Docker manipulates iptables directly and can **bypass ufw**. Since we bind containers to `127.0.0.1` only, this is safe. But verify after deployment:
```bash
# From external machine, check no container ports leak:
nmap -p 1-10000 94.131.92.153
# Expected: only 22, 80, 443 open
```

---

## Task N.7 — Activation Sequence

**Order is critical to avoid downtime:**

```
Step 1: Install host nginx (not started yet)
           sudo apt install -y nginx-light
           sudo systemctl stop nginx       # don't start yet

Step 2: Write configs
           /etc/nginx/nginx.conf           (main config)
           /etc/nginx/sites-available/agentdata.pro
           /etc/nginx/sites-available/x.oesv.ae
           sudo ln -s /etc/nginx/sites-available/agentdata.pro /etc/nginx/sites-enabled/
           sudo ln -s /etc/nginx/sites-available/x.oesv.ae /etc/nginx/sites-enabled/
           sudo rm /etc/nginx/sites-enabled/default

Step 3: Get cert for x.oesv.ae (while Docker nginx still runs)
           # Option: temporarily stop Docker nginx, start host nginx on :80 only
           cd ~/biocoach && docker compose stop nginx
           sudo nginx     # start host nginx (only :80 vhosts for now)
           sudo certbot certonly --nginx -d x.oesv.ae
           sudo nginx -s stop

Step 4: Modify docker-compose.yml
           Remove nginx service
           Bind web → 127.0.0.1:3080, api → 127.0.0.1:3000

Step 5: Restart Docker services
           cd ~/biocoach && docker compose up -d

Step 6: Test nginx config
           sudo nginx -t

Step 7: Start host nginx
           sudo systemctl start nginx
           sudo systemctl enable nginx

Step 8: Configure firewall
           sudo ufw allow 22/tcp
           sudo ufw allow 443/tcp
           sudo ufw allow 80/tcp
           sudo ufw --force enable

Step 9: Update GitLab external_url
           docker exec gitlab bash -c 'echo "external_url \"https://x.oesv.ae/gitlab\"" > /etc/gitlab/gitlab.rb'
           # Actually — append to existing gitlab.rb, not overwrite!
           docker exec gitlab gitlab-ctl reconfigure

Step 10: Verify everything
           curl -s https://agentdata.pro/api/health
           curl -sk https://x.oesv.ae/gitlab/
           ssh devteam "echo SSH works"
           # From external: nmap 94.131.92.153
```

### Rollback plan
If host nginx fails:
```bash
sudo systemctl stop nginx
cd ~/biocoach
# Revert docker-compose.yml (git checkout)
docker compose up -d
# Docker nginx takes over again on :80/:443
```

---

## File Change Map

| File/Service | Action |
|-------------|--------|
| `/etc/nginx/nginx.conf` | New — host nginx main config |
| `/etc/nginx/sites-available/agentdata.pro` | New — PaaS vhost |
| `/etc/nginx/sites-available/x.oesv.ae` | New — GitLab vhost |
| `~/biocoach/docker-compose.yml` | Modify — remove nginx, rebind ports |
| `~/biocoach/deploy/nginx/default.conf` | Keep as archive, no longer used |
| GitLab container | Reconfigure external_url |
| ufw | Enable with 22+80+443 rules |

## Memory Footprint

| Component | RAM |
|-----------|-----|
| nginx-light (1 worker, idle) | ~2–3 MB |
| nginx-light (under load, 10 users) | ~5–8 MB |
| Removed Docker nginx container | **−15–20 MB saved** |
| **Net change** | **−10–15 MB** |

---

## Success Criteria

- [ ] `https://agentdata.pro/` — React app loads
- [ ] `https://agentdata.pro/api/health` — returns `{"status":"ok"}`
- [ ] SSE streaming works (send chat message, tokens stream)
- [ ] `https://x.oesv.ae/gitlab/` — GitLab UI loads
- [ ] `ssh devteam` — works (port 22 open)
- [ ] Port scan from outside: only 22, 80, 443 open
- [ ] `/.git/config` returns 444 (blocked)
- [ ] `Server` header does not leak nginx version
- [ ] Certbot auto-renewal timer active
- [ ] `docker compose ps` — no nginx container
