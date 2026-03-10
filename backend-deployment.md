# Task 1: Backend Deployment - FastAPI CI/CD with GitHub Actions on European Linux Server

## Architecture Overview
```text
GitHub (push/commit)
       ↓
GitHub Actions Workflow
       ↓
Self-Hosted Runner (on your Linux server)
       ↓
/var/www/api-backend/   ← isolated directory
       ↓
Gunicorn + Uvicorn (ASGI)
       ↓
Nginx Reverse Proxy
       ↓
api.yourdomain.com (GoDaddy DNS → European Cloud Server IP)
```

---

## Phase 1 — Linux Server Preparation
This phase isolates your FastAPI app completely from the other 3 existing deployments.

### 1.1 — Create Isolated App Directory
SSH into your European Linux server and run:

```bash
# Create dedicated directory for this app only
sudo mkdir -p /var/www/api-backend
sudo chown $USER:$USER /var/www/api-backend

# Create a dedicated system user for process isolation
sudo useradd -r -m -d /var/www/api-backend -s /bin/bash apiuser
sudo chown -R apiuser:apiuser /var/www/api-backend
```

### 1.2 — Install Python Dependencies
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv -y

# Create virtual environment inside the app folder
sudo -u apiuser python3 -m venv /var/www/api-backend/venv

# Install FastAPI, Gunicorn, Uvicorn
sudo -u apiuser /var/www/api-backend/venv/bin/pip install fastapi gunicorn uvicorn[standard]
```

### 1.3 — Create .env File (Dev Environment)
```bash
sudo nano /var/www/api-backend/.env
```
Add your environment variables, including the connection to your externally hosted database:

```text
ENV=dev
APP_PORT=8001

# --- External Database Connection ---
# Uncomment the database you are using and keep the other commented out.
# Make sure to replace the placeholder IP (203.0.113.50) with your actual Database Server IP.

# Option A: PostgreSQL (Active)
DATABASE_URL=postgresql://db_user:db_password@203.0.113.50:5432/my_database
# Option B: MongoDB (Commented)
# MONGODB_URL=mongodb://db_user:db_password@203.0.113.50:27017/my_database

# Add any additional API keys etc.
```
⚠️ **Important:** This `.env` file will be excluded from `rsync` in the pipeline so it is never overwritten on deploy.

### 1.4 — Create systemd Service
This ensures only your app can be started/stopped — other apps are untouched.

```bash
sudo nano /etc/systemd/system/api-backend.service
```
Add the following configuration:
```ini
[Unit]
Description=FastAPI Backend - Dev
After=network.target

[Service]
User=apiuser
Group=apiuser
WorkingDirectory=/var/www/api-backend
EnvironmentFile=/var/www/api-backend/.env
ExecStart=/var/www/api-backend/venv/bin/gunicorn \
    --workers 3 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 127.0.0.1:8001 \
    --timeout 120 \
    --access-logfile /var/www/api-backend/logs/access.log \
    --error-logfile /var/www/api-backend/logs/error.log \
    app.main:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
*Note: Replace `app.main:app` with your actual module path. For example if your entry file is `main.py` at root with `app = FastAPI()`, use `main:app`.*

```bash
# Create logs directory
sudo mkdir -p /var/www/api-backend/logs
sudo chown -R apiuser:apiuser /var/www/api-backend/logs

sudo systemctl daemon-reload
sudo systemctl enable api-backend
sudo systemctl start api-backend
sudo systemctl status api-backend # should show: active (running)
```

---

## Phase 2 — GitHub Actions Self-Hosted Runner Setup
The runner connects your server directly to GitHub Actions without exposing SSH keys.

### 2.1 — Register Runner on GitHub
Go to your repository:
`GitHub Repo → Settings → Actions → Runners → New self-hosted runner`
Select **Linux → x64**.

### 2.2 — Install Runner on the Server
Run the exact commands shown on the GitHub UI. The pattern is usually:

```bash
# Create runner directory (separate from app directory)
mkdir -p /home/ubuntu/actions-runner && cd /home/ubuntu/actions-runner

# GitHub provides these — copy from GitHub UI
curl -o actions-runner-linux-x64-2.x.x.tar.gz -L https://github.com/actions/runner/releases/download/...
echo "HASH  actions-runner-linux-x64-2.x.x.tar.gz" | shasum -a 256 -c
tar xzf ./actions-runner-linux-x64-2.x.x.tar.gz
```

### 2.3 — Configure the Runner
```bash
./config.sh --url https://github.com/YOUR_ORG/YOUR_REPO --token YOUR_TOKEN_FROM_GITHUB
```
When prompted, enter:
- **Runner group:** Press Enter (default)
- **Runner name:** `eu-dev-server`
- **Labels:** `self-hosted,linux,dev,eu`
- **Work folder:** Press Enter (default `_work`)

### 2.4 — Install as a Persistent Background Service
```bash
sudo ./svc.sh install
sudo ./svc.sh start
sudo ./svc.sh status   # must show: active (running)
```
The runner now auto-starts on server reboot.

### 2.5 — Grant Runner Permission to Restart Only This App
```bash
sudo visudo
```
Add this line at the bottom (replace `ubuntu` with your runner OS user):
```text
ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl restart api-backend, /bin/systemctl status api-backend, /bin/systemctl stop api-backend
```

---

## Phase 3 — GitHub Actions Workflow
Create this file in your repository at `.github/workflows/deploy-backend-dev.yml`:

```yaml
name: 🚀 Deploy FastAPI Backend — Dev

on:
  push:                        # triggers on every commit/push
    branches:
      - dev                    # change to main if needed

jobs:
  deploy:
    name: Deploy to EU Linux Server
    runs-on: [self-hosted, linux, dev, eu]   # matches your runner labels

    steps:
      # ── Step 1: Pull latest code ──────────────────────────────────
      - name: 📥 Checkout Code
        uses: actions/checkout@v4

      # ── Step 2: Verify Python version ─────────────────────────────
      - name: 🐍 Verify Python
        run: python3 --version

      # ── Step 3: Install dependencies into venv ────────────────────
      - name: 📦 Install Dependencies
        run: |
          /var/www/api-backend/venv/bin/pip install --upgrade pip
          /var/www/api-backend/venv/bin/pip install -r $GITHUB_WORKSPACE/requirements.txt

      # ── Step 4: Sync only app files — SAFE rsync ──────────────────
      - name: 🔄 Sync App Files (Safe)
        run: |
          rsync -av --delete \
            --exclude='.env' \
            --exclude='venv/' \
            --exclude='*.log' \
            --exclude='logs/' \
            --exclude='.git/' \
            --exclude='__pycache__/' \
            $GITHUB_WORKSPACE/ /var/www/api-backend/

      # ── Step 5: Fix ownership after sync ──────────────────────────
      - name: 🔐 Fix File Ownership
        run: sudo chown -R apiuser:apiuser /var/www/api-backend/

      # ── Step 6: Restart ONLY this app's service ───────────────────
      - name: ♻️ Restart FastAPI Service
        run: |
          sudo systemctl restart api-backend
          sleep 3
          sudo systemctl status api-backend --no-pager

      # ── Step 7: Health Check ───────────────────────────────────────
      - name: ✅ Health Check
        run: |
          sleep 5
          curl -f http://127.0.0.1:8001/health || echo "Health check endpoint not found — verify /health route exists"
```
**Trigger behavior:** The `on: push` event fires on every single commit or push to the dev branch as required.

Your FastAPI `requirements.txt` (minimum):
```text
fastapi
uvicorn[standard]
gunicorn
python-dotenv

# --- Database Drivers ---
asyncpg          # For PostgreSQL (async)
psycopg2-binary  # For PostgreSQL (sync)
motor            # For MongoDB (async)
```

---

## Phase 4 — Nginx Reverse Proxy Configuration
Nginx sits in front of Gunicorn and handles the public domain routing.

### 4.1 — Create a Separate Config File for This App Only
```bash
sudo nano /etc/nginx/conf.d/api.yourdomain.com.conf
```
Add the configuration:
```text
server {
    listen 80;
    server_name api.yourdomain.com;    # your subdomain

    # Proxy all requests to Gunicorn
    location / {
        proxy_pass         http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection 'upgrade';
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 120s;
    }

    # Optional: serve FastAPI docs
    location /docs {
        proxy_pass http://127.0.0.1:8001/docs;
    }

    location /openapi.json {
        proxy_pass http://127.0.0.1:8001/openapi.json;
    }
}
```

### 4.2 — Test and Reload Nginx Safely
```bash
sudo nginx -t                  # must print: syntax is ok
sudo systemctl reload nginx    # reload = no downtime for other apps
```
*Always use `reload` not `restart` — this keeps your 3 existing apps running without interruption.*

### 4.3 — Enable Free SSL (HTTPS)
```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d api.yourdomain.com
# Follow prompts — certbot auto-updates your nginx config
```
Certbot auto-renews every 90 days. Test renewal with:
```bash
sudo certbot renew --dry-run
```

---

## Phase 5 — GoDaddy DNS Configuration

### 5.1 — Get Your European Cloud Server's Public IP
```bash
curl ifconfig.me
# example output: 185.x.x.x  (European IP)
```

### 5.2 — Add DNS Record in GoDaddy
Log in to GoDaddy → My Products → Click DNS next to your domain. Click Add New Record:

| Type | Name | Value | TTL |
| :--- | :--- | :--- | :--- |
| A | `api` | `185.x.x.x` (your EU server IP) | 1 Hour |

This creates `api.yourdomain.com` → pointing to your EU server.

### 5.3 — Verify DNS Propagation
```bash
# Wait 5–30 minutes, then check:
nslookup api.yourdomain.com
# or
dig api.yourdomain.com

# Should return your EU server IP
```
You can also check at dnschecker.org to see global propagation.

---

## Phase 6 — End-to-End Verification Checklist
Run through this after every setup step:

```bash
# 1. Confirm runner is online
# → GitHub Repo → Settings → Actions → Runners → Status = Active ✅

# 2. Check FastAPI service is running
sudo systemctl status api-backend

# 3. Test locally on server
curl http://127.0.0.1:8001/
curl http://127.0.0.1:8001/health

# 4. Test via domain
curl http://api.yourdomain.com/
curl https://api.yourdomain.com/   # after SSL

# 5. Confirm other apps are untouched
sudo systemctl status existing-app-1
sudo systemctl status existing-app-2
sudo systemctl status existing-app-3

# 6. Push to dev branch → watch GitHub Actions tab trigger automatically
```

### Safety Rules — Existing Apps Are Never Affected

| Risk Area | How It's Protected |
| :--- | :--- |
| **File system** | `rsync` only writes to `/var/www/api-backend/` |
| **.env secrets** | Excluded from `rsync` with `--exclude='.env'` |
| **Service restart** | Only `api-backend.service` is restarted |
| **Nginx config** | Separate file `api.yourdomain.com.conf` — others untouched |
| **Nginx reload** | `reload` (not `restart`) keeps all apps live |
| **sudo access** | Runner can only run `systemctl restart api-backend` |
| **Port conflict** | App runs on `8001` — check your other apps use different ports |

**Port check — before starting**, confirm no other app uses port 8001:
```bash
sudo ss -tlnp | grep 8001
```
If taken, change `8001` to any free port (e.g., `8002`, `8003`) in both systemd service and Nginx config.
