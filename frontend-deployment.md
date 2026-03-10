# Task 2: Frontend Deployment - Angular CI/CD with GitHub Actions → Nginx

## Architecture Overview
```text
GitHub (push/commit on dev branch)
         ↓
GitHub Actions Workflow
         ↓
Self-Hosted Runner (same EU Linux server)
         ↓
npm install → ng build → dist/ folder
         ↓
/var/www/angular-frontend/    ← isolated directory
         ↓
Nginx serves static files directly
         ↓
app.yourdomain.com  (GoDaddy DNS → EU Server IP)
```

Angular is a static app after build. Nginx serves the `dist/` output directly — no Gunicorn/process manager needed like the FastAPI backend.

---

## Phase 1 — Linux Server Preparation

### 1.1 — Create Isolated Directory
```bash
# Isolated from your other 3 apps and the FastAPI backend
sudo mkdir -p /var/www/angular-frontend
sudo chown $USER:$USER /var/www/angular-frontend
```

### 1.2 — Install Node.js on the Server
The runner needs Node.js to build Angular:

```bash
# Install Node.js 20 LTS (recommended for Angular 17+)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Verify
node -v    # v20.x.x
npm -v     # 10.x.x
```

### 1.3 — Install Angular CLI Globally
```bash
sudo npm install -g @angular/cli

# Verify
ng version
```

---

## Phase 2 — Nginx Configuration for Angular
Angular uses HTML5 routing (RouterModule). Nginx must redirect all routes back to `index.html`, otherwise direct URL access breaks.

### 2.1 — Create Separate Nginx Config File
```bash
sudo nano /etc/nginx/conf.d/app.yourdomain.com.conf
```
Add the configuration:
```text
server {
    listen 80;
    server_name app.yourdomain.com;     # your frontend subdomain

    root /var/www/angular-frontend;
    index index.html;

    # Required for Angular routing (HTML5 pushState)
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Cache static assets (JS, CSS, images)
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    # Gzip for performance
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;
}
```

### 2.2 — Test and Reload Nginx
```bash
sudo nginx -t                   # must show: syntax is ok
sudo systemctl reload nginx     # reload = no downtime for other apps
```

### 2.3 — Enable HTTPS with Let's Encrypt
```bash
sudo certbot --nginx -d app.yourdomain.com
```

---

## Phase 3 — GitHub Actions Workflow
Create this file in your Angular repository at `.github/workflows/deploy-frontend-dev.yml`:

```yaml
name: 🚀 Deploy Angular Frontend — Dev

on:
  push:                          # triggers on every commit/push
    branches:
      - dev                      # change to main if needed

jobs:
  build-and-deploy:
    name: Build & Deploy to EU Nginx
    runs-on: [self-hosted, linux, dev, eu]   # same runner as backend

    steps:
      # ── Step 1: Checkout code ─────────────────────────────────────
      - name: 📥 Checkout Code
        uses: actions/checkout@v4

      # ── Step 2: Setup Node.js ─────────────────────────────────────
      - name: ⚙️ Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'            # caches node_modules for faster builds

      # ── Step 3: Install dependencies ──────────────────────────────
      - name: 📦 Install Dependencies
        run: npm ci               # ci = clean install, faster & deterministic

      # ── Step 4: Build Angular for Dev ─────────────────────────────
      - name: 🏗️ Build Angular App
        run: npm run build -- --configuration=development
        # For production build use: --configuration=production

      # ── Step 5: Deploy dist/ to Nginx directory ───────────────────
      - name: 🔄 Deploy Build to Nginx Root
        run: |
          rsync -av --delete \
            --exclude='.git/' \
            dist/YOUR_APP_NAME/browser/ /var/www/angular-frontend/
          # For Angular 16 and below (no /browser subfolder):
          # dist/YOUR_APP_NAME/ /var/www/angular-frontend/

      # ── Step 6: Fix permissions ────────────────────────────────────
      - name: 🔐 Fix Nginx Permissions
        run: |
          sudo chown -R www-data:www-data /var/www/angular-frontend
          sudo chmod -R 755 /var/www/angular-frontend

      # ── Step 7: Reload Nginx (safe — no downtime) ─────────────────
      - name: ♻️ Reload Nginx
        run: sudo systemctl reload nginx

      # ── Step 8: Health Check ──────────────────────────────────────
      - name: ✅ Health Check
        run: curl -f http://127.0.0.1/  || echo "Check Nginx config"
```
**Finding your app name:** Look in `angular.json → projects → your project key`. That's `YOUR_APP_NAME` in the `dist/` path.

### Grant Runner Permission for Nginx Reload
```bash
sudo visudo
```
Add this line (append to the existing backend line):
```text
ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl reload nginx, /bin/chown -R www-data:www-data /var/www/angular-frontend, /bin/chmod -R 755 /var/www/angular-frontend
```

---

## Phase 4 — Angular Environment File for Dev
In your Angular project, configure `src/environments/environment.development.ts`:

```typescript
export const environment = {
  production: false,
  apiUrl: 'https://api.yourdomain.com',   // your FastAPI backend URL
  envName: 'dev'
};
```
This wires the Angular frontend directly to your FastAPI backend subdomain.

---

## Phase 5 — GoDaddy DNS for Frontend Subdomain
Add another A record in GoDaddy DNS (same EU server IP as the backend):

| Type | Name | Value | TTL |
| :--- | :--- | :--- | :--- |
| A | `app` | `185.x.x.x` (EU Server IP) | 1 Hour |

This creates `app.yourdomain.com` → your Angular frontend.

Your DNS records now look like:
| Subdomain | Points To | Serves |
| :--- | :--- | :--- |
| `api.yourdomain.com` | EU Server IP | FastAPI Backend |
| `app.yourdomain.com` | EU Server IP | Angular Frontend |

*Nginx routes each subdomain to the correct directory using separate config files — they never interfere.*

---

## Phase 6 — Full Verification Checklist
```bash
# 1. Confirm Angular build output exists
ls /var/www/angular-frontend/
# Should show: index.html, main.js, styles.css, assets/ etc.

# 2. Check Nginx is serving it
curl http://127.0.0.1/
# Should return Angular's index.html

# 3. Check subdomain
curl https://app.yourdomain.com/

# 4. Test Angular routing works (not 404)
curl https://app.yourdomain.com/your-angular-route

# 5. Confirm backend API is reachable from frontend
curl https://api.yourdomain.com/health

# 6. Confirm ALL other apps still running
sudo systemctl status existing-app-1
sudo systemctl status existing-app-2
sudo systemctl status existing-app-3
```

### Angular 17+ vs Angular 16 — `dist/` Path Difference
Angular 17+ introduced a `/browser` subfolder in the build output:

| Angular Version | Build Output Path |
| :--- | :--- |
| **Angular 17+** | `dist/YOUR_APP_NAME/browser/` |
| **Angular 16 and below** | `dist/YOUR_APP_NAME/` |

Check your `package.json` for `"@angular/core"` version and adjust the rsync path in the workflow accordingly.

---

## Combined Backend + Frontend Summary

| Component | Directory | Port | Subdomain | status |
| :--- | :--- | :--- | :--- | :--- |
| **FastAPI Backend** | `/var/www/api-backend` | 8001 (internal) | `api.yourdomain.com` | ✅ |
| **Angular Frontend** | `/var/www/angular-frontend` | 80/443 via Nginx | `app.yourdomain.com` | ✅ |
| **Existing App 1–3** | Their own dirs | Their own ports | Unchanged | ✅ |
