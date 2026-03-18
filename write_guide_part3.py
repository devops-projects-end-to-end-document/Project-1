
part5 = r"""
## 9. Domain & Nginx Configuration

> 💡 **Why Nginx as a reverse proxy?**
> Nginx sits in front of Gunicorn and handles:
> - SSL/TLS termination (decrypts HTTPS)
> - Static file serving (10× faster than Python)
> - Request buffering (protects Gunicorn from slow clients)
> - Load balancing (if you add more Gunicorn workers later)
>
> **Alternatives:** Apache + mod_wsgi (older), Caddy (simpler SSL auto-config), Traefik (container-native)

---

### 9.1 Verify DNS Resolution

```bash
curl -s ifconfig.me
```
```
<YOUR_SERVER_PUBLIC_IP>
```
> 📌 **Why:** Confirms the server's external IP before DNS lookup. If this doesn't match the domain's A record, HTTPS setup will fail.

```bash
sudo apt install -y iputils-ping dnsutils curl net-tools
```
> 📌 **Why install these tools?** `dig` and `ping` were not available on this minimal GCP image — see [Error #4](#error-4-vi--dig--ping-not-found).

```bash
dig +short <YOUR_DOMAIN>
```
```
<YOUR_SERVER_PUBLIC_IP>
```

```bash
ping -c 1 <YOUR_DOMAIN>
```
```
PING <YOUR_DOMAIN> (<YOUR_SERVER_PUBLIC_IP>) 56(84) bytes of data.
64 bytes from ...: icmp_seq=1 ttl=61 time=0.370 ms
1 packets transmitted, 1 received, 0% packet loss
```
> 📌 **Why ping the domain?** Verifies end-to-end DNS resolution and network reachability before configuring Nginx. If DNS isn't pointing to this server, Let's Encrypt certificate issuance will fail.

---

### 9.2 Configure Nginx Site

```bash
sudo nano /etc/nginx/sites-available/insurance
```

Example configuration:
```nginx
server {
    listen 80;
    server_name <YOUR_DOMAIN>;

    location = /favicon.ico { access_log off; log_not_found off; }

    location /static/ {
        root /home/insurance/public_html;
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:/home/insurance/gunicorn.sock;
    }
}
```
> 📌 **Why a separate sites-available file?** Following the Nginx convention:
> - `/etc/nginx/sites-available/` = all configured sites (enabled or not)
> - `/etc/nginx/sites-enabled/` = symlinks to active sites
>
> This allows quick enable/disable: `sudo ln -s /etc/nginx/sites-available/insurance /etc/nginx/sites-enabled/`

**Update `server_name` from IP to domain:**
```bash
# Change: server_name <YOUR_SERVER_PUBLIC_IP>;
# To:     server_name <YOUR_DOMAIN>;
```
> 📌 **Why switch from IP to domain?** Let's Encrypt issues certificates for domain names, not IP addresses. Nginx's `server_name` must match the domain for SSL to work correctly.

```bash
sudo nginx -t
```
```
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```
> 📌 **Always run `nginx -t` before reload!** A syntax error in the config will take down the entire web server if you reload without testing first.

```bash
sudo systemctl reload nginx
```

---

### 9.3 Verify HTTP Response

```bash
curl -I http://<YOUR_DOMAIN>
```
```
HTTP/1.1 404 Not Found
Server: nginx/1.24.0 (Ubuntu)
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
```
> 📌 **Why 404 at root?** Django doesn't serve a route at `/` by default — only `/admin/`, API endpoints, etc. A 404 from Nginx+Django means the stack is working correctly; the route just isn't defined.

```bash
curl -I http://<YOUR_DOMAIN>/admin/
```
```
HTTP/1.1 302 Found
Location: /admin/login/?next=/admin/
```
> ✅ **302 redirect to `/admin/login/`** confirms Django is receiving requests and responding correctly through Nginx → Gunicorn.

---

## 10. SSL Certificate — Let's Encrypt

> 💡 **Why Let's Encrypt?** Free, automated, trusted SSL certificates from a non-profit CA. Certbot automates certificate issuance, renewal, and Nginx configuration.
> **Alternatives:** AWS ACM (free on AWS), paid certificates (DigiCert, Comodo), self-signed (dev only)

```bash
sudo certbot --nginx -d <YOUR_DOMAIN>
```
```
Enter email: <YOUR_EMAIL>
Agree to ToS? Y

Requesting a certificate for <YOUR_DOMAIN>
Successfully received certificate.
Certificate is saved at: /etc/letsencrypt/live/<YOUR_DOMAIN>/fullchain.pem
Key is saved at:         /etc/letsencrypt/live/<YOUR_DOMAIN>/privkey.pem
This certificate expires on 2026-06-14.
Certbot has set up a scheduled task to automatically renew this certificate.

Successfully deployed certificate for <YOUR_DOMAIN> to /etc/nginx/sites-enabled/insurance
Congratulations! You have successfully enabled HTTPS on https://<YOUR_DOMAIN>
```
> 📌 **How Certbot works:**
> 1. Creates an ACME challenge file in the web root
> 2. Let's Encrypt servers fetch the challenge file via HTTP to verify domain ownership
> 3. Issues a 90-day certificate
> 4. Certbot auto-modifies Nginx config to redirect HTTP→HTTPS
> 5. Sets up a systemd timer for automatic renewal before expiry
>
> **Certbot adds to Nginx config automatically:**
> ```nginx
> listen 443 ssl;
> ssl_certificate /etc/letsencrypt/live/<YOUR_DOMAIN>/fullchain.pem;
> ssl_certificate_key /etc/letsencrypt/live/<YOUR_DOMAIN>/privkey.pem;
> # HTTP → HTTPS redirect
> ```

---

## 11. ⚠️ Common Errors & Fixes Encountered

> This section documents all real errors hit during this deployment, their root causes, and how they were resolved.

---

### Error #1: gnupg Pre-dependency Missing

**When:** `sudo dpkg -i mysql-apt-config_0.8.33-1_all.deb` (first attempt)

**Error:**
```
dpkg: regarding mysql-apt-config_0.8.33-1_all.deb containing mysql-apt-config, pre-dependency problem:
 mysql-apt-config pre-depends on gnupg
   gnupg is not installed.

dpkg: error processing archive mysql-apt-config_0.8.33-1_all.deb (--install):
 pre-dependency problem - not installing mysql-apt-config
```

**Root Cause:**
`dpkg` installs packages without resolving dependencies, unlike `apt`. The `mysql-apt-config` package declares `gnupg` as a **pre-dependency** (must be installed before the package itself can be configured). On a minimal GCP Ubuntu image, `gnupg` is not pre-installed.

**Fix:**
```bash
sudo apt update          # Fetches package lists
# apt update implicitly resolves and installs missing pre-deps before dpkg re-run
sudo dpkg -i mysql-apt-config_0.8.33-1_all.deb   # Now succeeds
```

**Alternative fix:**
```bash
sudo apt install gnupg   # Explicitly install gnupg first
sudo dpkg -i mysql-apt-config_0.8.33-1_all.deb
```

**Lesson:** Always run `sudo apt update && sudo apt install -f` before using `dpkg -i` to satisfy pre-dependencies.

---

### Error #2: mysqlclient Wheel Build Failure

**When:** `pip install -r requirements.txt` (both first and second attempts)

**Error (first attempt):**
```
ERROR: Failed to build 'mysqlclient' when getting requirements to build wheel
```

**Error (second attempt — after installing pkg-config, python3-dev, build-essential):**
```
Package openssl was not found in the pkg-config search path.
Perhaps you should add the directory containing 'openssl.pc'
to the PKG_CONFIG_PATH environment variable
Package 'openssl', required by 'mysqlclient', not found
```

**Root Cause:**
`mysqlclient` is a C extension (not a pure Python package). It compiles native code that links against the MySQL C client library (`libmysqlclient`), which itself depends on OpenSSL. The `libssl-dev` package (OpenSSL development headers) was missing, so `pkg-config` could not locate the `openssl.pc` file needed during compilation.

**Fix (step-by-step):**
```bash
# Step 1: Install all build tools
sudo apt install -y pkg-config python3-dev default-libmysqlclient-dev build-essential

# Step 2: Ensure libmysqlclient is latest (was already 8.4.8)
sudo apt install -y libmysqlclient-dev

# Step 3: KEY FIX — install OpenSSL dev headers
sudo apt install -y libssl-dev

# Step 4: Verify pkg-config finds mysqlclient
pkg-config --cflags mysqlclient
# Expected output: -I/usr/include/mysql
```

**Lesson:** When installing `mysqlclient` on Ubuntu 24.04 with MySQL 8.4, always install `libssl-dev` in addition to the standard build tools.

---

### Error #3: ufw / iptables Not Found

**When:** Network security check

**Error:**
```
sudo ufw status verbose
sudo: ufw: command not found

sudo iptables -L -n -v
sudo: iptables: command not found
```

**Root Cause:**
GCP Compute Engine instances manage firewall rules at the **VPC/network level** (via GCP Firewall Rules in the console or `gcloud` CLI), not at the OS level. Therefore, `ufw` (Uncomplicated Firewall) and `iptables` are intentionally not installed on minimal GCP images.

**Fix / Workaround:**
Security is managed via GCP Console → VPC Network → Firewall Rules:
- Allow port 22 (SSH)
- Allow port 80 (HTTP)
- Allow port 443 (HTTPS)
- Block port 3306 from the internet (allow only from app server IP)

```bash
# To install ufw if needed (not recommended on GCP):
sudo apt install ufw
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

**Lesson:** On cloud providers (GCP/AWS/Azure), prefer cloud-native firewall rules over OS-level tools. Use `ss -tlnp` to inspect listening ports instead.

---

### Error #4: vi / dig / ping Not Found

**When:** Various commands during setup

**Errors:**
```
$ vi /home/insurance/public_html/core/external_benefits.py
-bash: vi: command not found

$ dig +short wmsuat.pacificinsurance.com.my
-bash: dig: command not found

$ ping -c 1 wmsuat.pacificinsurance.com.my
-bash: ping: command not found
```

**Root Cause:**
GCP minimal Ubuntu images omit many standard tools to reduce attack surface and image size. `vi`, `dig`, and `ping` are not part of the minimal package selection.

**Fix:**
```bash
# For text editing
sudo apt install -y vim          # full vi/vim
# OR use nano (usually pre-installed):
nano /path/to/file

# For DNS and network tools
sudo apt install -y dnsutils         # provides dig, nslookup
sudo apt install -y iputils-ping     # provides ping
sudo apt install -y net-tools        # provides netstat, ifconfig

# One-liner for all missing tools:
sudo apt install -y iputils-ping dnsutils curl net-tools vim
```

**Lesson:** Always install `dnsutils`, `iputils-ping`, and `net-tools` at the beginning of setup on minimal cloud images.

---

### Error #5: Django migrate Shows Unapplied Model Changes

**When:** `python manage.py migrate` (first run after restoring database backup)

**Warning:**
```
Running migrations:
  No migrations to apply.
  Your models in app(s): 'core' have changes that are not yet reflected in a migration,
  and so won't be applied.
  Run 'manage.py makemigrations' to make new migrations, and then re-run 'manage.py migrate'.
```

**Root Cause:**
The database backup (`kereta_insurance_backup.sql`) was from a production server. The code being deployed (`Kereta-Insurance-main.zip`) had new model fields in the `core` app (e.g., `grossdue`, `netdue`, `payment_prompt_sent`) that were added after the backup was taken. The migration files for these fields existed in the code but weren't in the backup's `django_migrations` table.

**Fix:**
```bash
python manage.py makemigrations    # Creates migration 0045_usersession_grossdue_and_more.py
python manage.py migrate           # Applies it (adds new columns)
```

**New migration created:**
```
+ Add field grossdue to usersession
+ Add field last_payment_order_id to usersession
+ Add field netdue to usersession
+ Add field payment_prompt_sent to usersession
```

**Lesson:** After restoring a database backup, always run `makemigrations` + `migrate` to sync the database schema with the current code. The backup schema and code schema may diverge over time.

---

### Error #6: Nginx Reload Warning After certbot

**When:** `sudo systemctl reload nginx` after DNS change

**Warning:**
```
Warning: The unit file, source configuration file or drop-ins of nginx.service
changed on disk. Run 'systemctl daemon-reload' to reload units.
```

**Root Cause:**
The Nginx systemd service unit file or its configuration changed on disk (likely due to a package update during `apt update`). Systemd detected the change but the daemon hadn't re-read the file yet.

**Fix:**
```bash
sudo systemctl daemon-reload    # Re-reads changed unit files
sudo systemctl reload nginx     # Now reloads cleanly
```

**Lesson:** Always run `systemctl daemon-reload` after any system package update that touches service files.

---

## 12. ✅ Production Best Practices

> 💡 These recommendations go beyond what was done in this guide — apply them to harden and scale the deployment.

---

### 🔐 Security

| Practice | How to Implement |
|----------|-----------------|
| Change MySQL root password regularly | `ALTER USER 'root'@'localhost' IDENTIFIED BY 'NewStr0ng!Pass';` |
| Use environment variables for secrets | Store `SECRET_KEY`, DB password in `.env`; use `python-decouple` in settings.py |
| Never run Django with `DEBUG=True` in production | `DEBUG = False` in settings.py |
| Restrict MySQL access by IP | `GRANT ... TO 'insurance'@'127.0.0.1'` instead of `'%'` |
| Regular SSL renewal monitoring | `sudo certbot renew --dry-run` (Certbot auto-renews, but test it) |
| Firewall: block 3306 from public | GCP Firewall Rule: deny TCP 3306 from `0.0.0.0/0` |
| Use SSH key authentication only | Disable password SSH in `/etc/ssh/sshd_config`: `PasswordAuthentication no` |

---

### 🗄️ Database

| Practice | Command / Config |
|----------|----------------|
| Enable binary logging for point-in-time recovery | `log_bin = /var/log/mysql/mysql-bin.log` in `mysqld.cnf` |
| Set InnoDB buffer pool size | `innodb_buffer_pool_size = 4G` (≈50% of RAM) |
| Schedule automated backups | `mysqldump -u root -p insurance > /backup/$(date +%F).sql` via cron |
| Monitor slow queries | `slow_query_log = 1`, `long_query_time = 2` in `mysqld.cnf` |
| Regular vacuum/optimize | `mysqlcheck -u root -p --optimize --all-databases` weekly |

---

### ⚡ Performance

| Practice | Details |
|----------|---------|
| Scale Gunicorn workers | `--workers = 2 * CPU + 1`. For 2 CPUs: 5 workers |
| Use `--worker-class gevent` for async | Install `gevent`: `pip install gevent`; add `--worker-class gevent` |
| Enable Nginx gzip compression | Add `gzip on;` in `nginx.conf` http block |
| Add Nginx caching for static | `expires 30d;` in the `/static/` location block |
| Use Redis for Django caching | `pip install django-redis`; set `CACHE_BACKEND = 'django_redis...'` |
| Enable MySQL query cache (8.0+ removed) | Use ProxySQL or application-level caching instead |

---

### 📋 Monitoring & Logging

```bash
# Real-time Gunicorn access logs
sudo tail -f /home/insurance/logs/gunicorn-access.log

# Gunicorn error logs
sudo tail -f /home/insurance/logs/gunicorn-error.log

# MySQL error log
sudo tail -f /var/log/mysql/error.log

# Nginx access/error logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log

# System journal for all services
sudo journalctl -u gunicorn -f
sudo journalctl -u mysql -f
sudo journalctl -u nginx -f
```

---

### 🔄 Deployment Checklist

```
Before going live:
[ ] DEBUG = False in settings.py
[ ] ALLOWED_HOSTS includes your domain
[ ] SECRET_KEY not hardcoded (use env var)
[ ] Static files collected (collectstatic)
[ ] Database migrations applied (migrate)
[ ] MySQL root password is strong
[ ] MySQL app user has minimum required permissions
[ ] GCP Firewall: port 3306 blocked from internet
[ ] SSL certificate valid (certbot renew --dry-run)
[ ] Nginx config tested (nginx -t)
[ ] Gunicorn service enabled (systemctl enable gunicorn)
[ ] MySQL service enabled (systemctl enable mysql)
[ ] Automated database backup scheduled (cron)
[ ] Log rotation configured (/etc/logrotate.d/)
```

---

### 🔁 Common Management Commands

```bash
# Restart everything after code changes
sudo systemctl restart gunicorn
sudo systemctl reload nginx

# Check all service statuses at once
sudo systemctl status mysql gunicorn nginx

# Test Django before restarting Gunicorn
source /home/insurance/venv/bin/activate
cd /home/insurance/public_html
python manage.py check --deploy

# View last 50 Gunicorn errors
sudo journalctl -u gunicorn -n 50 --no-pager

# Renew SSL certificate manually
sudo certbot renew

# Create Django superuser
python manage.py createsuperuser
```

---

## 📌 Placeholder Reference

| Placeholder | Description | Original Value |
|---|---|---|
| `<YOUR_SERVER_PUBLIC_IP>` | GCP VM external/public IP | `35.247.162.140` |
| `<SERVER_PRIVATE_IP>` | GCP VM internal IP (ens3) | `10.148.0.2` |
| `<YOUR_DOMAIN>` | Application domain name | `wmsuat.pacificinsurance.com.my` |
| `<YOUR_MYSQL_ROOT_PASSWORD>` | MySQL root user password | *(set during install — use strong password)* |
| `<YOUR_DB_APP_PASSWORD>` | MySQL `insurance` user password | *(replace `Insurance` with a strong password)* |
| `<YOUR_OS_USER_PASSWORD>` | Linux `insurance` OS user password | *(set during `adduser`)* |
| `<YOUR_EMAIL>` | Admin email for Let's Encrypt renewal alerts | `tech2chrome@gmail.com` |

---

*Guide created: 2026-03-18 | Stack: Ubuntu 24.04 LTS · MySQL 8.4.8 · Python 3.12 · Django · Gunicorn 25.1.0 · Nginx 1.24 · Certbot*
"""

with open('mysql8-4-installation-guide.md', 'a', encoding='utf-8') as f:
    f.write(part5)

import os
size = os.path.getsize('mysql8-4-installation-guide.md')
print(f"Final file size: {size} bytes ({size//1024} KB)")
