# 🚀 MySQL 8.4 LTS + Django Deployment Guide
### Ubuntu 24.04 LTS | Google Cloud Platform | Nginx + Gunicorn + SSL

![Architecture Banner](./architecture-banner.png)

> **Stack:** Ubuntu 24.04 LTS · MySQL 8.4 LTS · Python 3.12 · Django · Gunicorn · Nginx · Let's Encrypt
> **Server:** GCP Compute Engine | `<YOUR_SERVER_PUBLIC_IP>` | `<YOUR_DOMAIN>`

---

## 📖 Table of Contents

| # | Section |
|---|---------|
| 1 | [Initial System Check](#1-initial-system-check) |
| 2 | [MySQL 8.4 Installation](#2-mysql-84-lts-installation) |
| 3 | [Database Setup](#3-database-setup) |
| 4 | [System User & Directories](#4-system-user--directory-setup) |
| 5 | [Application Deployment](#5-application-deployment) |
| 6 | [Python venv & Dependencies](#6-python-virtual-environment--dependencies) |
| 7 | [Django App Setup](#7-django-application-setup) |
| 8 | [Gunicorn Systemd Service](#8-gunicorn-systemd-service) |
| 9 | [Nginx Configuration](#9-domain--nginx-configuration) |
| 10 | [SSL Certificate](#10-ssl-certificate-lets-encrypt) |
| 11 | [⚠️ Errors & Fixes](#11--common-errors--fixes-encountered) |
| 12 | [✅ Best Practices](#12--production-best-practices) |

---

## 🏗️ Architecture Overview

```
 Browser (HTTPS)
      │
      ▼
 ┌──────────────┐    Static Files   ┌─────────────────────────┐
 │  NGINX 1.24  │──────────────────▶│ /public_html/staticfiles │
 │  Port 80/443 │                   └─────────────────────────┘
 │   SSL/TLS    │
 └──────┬───────┘
        │ WSGI (Unix Socket)
        ▼
 ┌──────────────┐
 │  GUNICORN    │  3 workers · unix:/home/insurance/gunicorn.sock
 │  WSGI Server │
 └──────┬───────┘
        │ Django ORM
        ▼
 ┌──────────────┐         ┌──────────────────────┐
 │   DJANGO     │────────▶│  MySQL 8.4 LTS       │
 │  Python App  │         │  Port 3306 · 0.0.0.0 │
 └──────────────┘         └──────────────────────┘
```

> 💡 **Why this stack?**
> - **Nginx** handles SSL termination and serves static files 10x faster than Python
> - **Gunicorn** spawns multiple Python worker processes for concurrent requests
> - **Django** provides ORM, admin, and rapid application development
> - **MySQL 8.4 LTS** provides 5-year long-term support, window functions, and enterprise-grade reliability

---

## 1. Initial System Check

> 💡 **Why check before installing?** A pre-flight check prevents conflicts with existing services, validates available resources, and helps you size MySQL and Gunicorn worker settings correctly.

### 1.1 OS & Kernel Info

```bash
lsb_release -a
```
```
No LSB modules are available.
Distributor ID: Ubuntu
Description:    Ubuntu 24.04.4 LTS
Release:        24.04
Codename:       noble
```

> 📌 **Why:** MySQL 8.4 LTS has an official APT repo specifically for Ubuntu 24.04 (`noble`). Using the wrong OS version causes "package not found" errors.
> **Alternatives:** `cat /etc/os-release` · `hostnamectl`

```bash
uname -r
```
```
6.17.0-1008-gcp
```
> 📌 **Why:** The `-gcp` suffix confirms GCP/KVM cloud-optimized kernel with virtio drivers active. This affects I/O scheduling and MySQL disk write performance.

```bash
nproc
```
```
2
```
> 📌 **Why:** Used to size Gunicorn workers: `workers = 2 × CPU_cores + 1 = 5`. In this guide we used 3 (conservative). Scale up in production.
> **Alternatives:** `lscpu | grep "^CPU(s):"` · `grep -c ^processor /proc/cpuinfo`

```bash
free -h
```
```
               total        used        free      shared  buff/cache   available
Mem:           7.7Gi       554Mi       6.1Gi       1.0Mi       1.3Gi       7.2Gi
```
> 📌 **Why:** MySQL InnoDB buffer pool should be 50–70% of RAM. With 7.7 GB RAM, set `innodb_buffer_pool_size=4G` in production.
> **Alternatives:** `vmstat -s | head` · `cat /proc/meminfo`

```bash
df -h
```
```
Filesystem       Size  Used Avail Use% Mounted on
/dev/root         29G  2.5G   26G   9% /
tmpfs            3.9G     0  3.9G   0% /dev/shm
tmpfs            1.6G  1.1M  1.6G   1% /run
```
> 📌 **Why:** The database backup (`kereta_insurance_backup.sql`) was 24 MB compressed but expanded to several GB. Always ensure `/var/lib/mysql` has sufficient space.
> **Alternatives:** `lsblk` · `du -sh /var/lib/mysql`

---

### 1.2 Running Services

```bash
sudo systemctl list-units --type=service
```
> 📌 **Why:** Detects conflicts — e.g., port 80 occupied by Apache before Nginx install, or another MySQL instance already running on 3306.
> **Alternatives:** `service --status-all` · `ps aux | grep mysql`

*(54 services active — key ones: `ssh.service`, `chrony.service`, `rsyslog.service`. No MySQL or Nginx yet.)*

---

### 1.3 Network Ports

```bash
sudo ss -tlnp
```
```
State   Recv-Q  Send-Q   Local Address:Port     Peer Address:Port  Process
LISTEN  0       4096           0.0.0.0:22            0.0.0.0:*      sshd
LISTEN  0       128            0.0.0.0:20202         0.0.0.0:*      fluent-bit
```
> 📌 **Why:** `ss` (socket statistics) is the modern replacement for `netstat`. Only SSH (22) is open — no conflicts with MySQL (3306) or Nginx (80/443).
> **Alternatives:** `sudo netstat -tlnp` · `sudo lsof -i -P -n | grep LISTEN`
> ⚠️ `sudo ufw status` and `sudo iptables -L` returned "command not found" — see [Error #3](#error-3-ufw--iptables-not-found).

---

### 1.4 Network Interface

```bash
ip a
```
```
2: ens3: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1460
    inet <SERVER_PRIVATE_IP>/32 metric 100 scope global dynamic ens3
    inet6 fe80::4001:aff:fe94:2/64 scope link
```
> 📌 **Why:** On GCP, the external/public IP is NAT'd. The NIC (`ens3`) holds only the private IP. MySQL's `bind-address = 0.0.0.0` binds to this interface; the public IP is handled by GCP's VPC.
> **Alternatives:** `ifconfig ens3` · `ip route show`

---

### 1.5 System Info

```bash
hostnamectl
```
```
Transient hostname: insurance
    Virtualization: google
  Operating System: Ubuntu 24.04.4 LTS
          Kernel: Linux 6.17.0-1008-gcp
    Hardware Vendor: Google
     Hardware Model: Google Compute Engine
```
> 📌 **Why:** Validates the machine type and virtualization layer. Google KVM supports live migration — MySQL data is safe during GCP maintenance events.

---

## 2. MySQL 8.4 LTS Installation

> 💡 **Why MySQL 8.4 LTS?**
> MySQL 8.4 is a **Long-Term Support (LTS)** release with full support until **2032**. It includes:
> - Native window functions & CTEs
> - Faster JSON operations
> - Improved InnoDB redo log
> - Better default security settings
>
> **Alternatives:** PostgreSQL (more standards-compliant), MariaDB 11.x (MySQL fork, open-source), SQLite (dev-only, not for production)

---

### 2.1 Download MySQL APT Repository Config

```bash
wget https://dev.mysql.com/get/mysql-apt-config_0.8.33-1_all.deb
```
```
2026-03-14 07:14:44 (270 MB/s) - 'mysql-apt-config_0.8.33-1_all.deb' saved [18072/18072]
```
> 📌 **Why:** Ubuntu's default APT repositories contain MySQL 8.0, not 8.4. This `.deb` package adds the official MySQL APT repository for Ubuntu, enabling `apt install mysql-community-server` to pull 8.4.
> **Alternative:** Download directly from MySQL website or use `snap install mysql` (less control over version).

---

### 2.2 Install Pre-dependency & Configure APT

```bash
sudo apt update
sudo dpkg -i mysql-apt-config_0.8.33-1_all.deb
```
```
# Interactive dialog:
# 1. MySQL Server & Cluster (Currently selected: mysql-8.4-lts)
# 2. MySQL Connectors (Currently selected: Enabled)
# 3. Ok
# → Selected: 3 (save & exit)
```
> 📌 **Why `apt update` first:** The initial `dpkg -i` attempt failed because `gnupg` was missing (see [Error #1](#error-1-gnupg-pre-dependency-missing)).
> Running `apt update` installs `gnupg` as a dependency, resolving the pre-dependency issue.
> **Why `dpkg -i`:** `dpkg` installs `.deb` packages directly (bypassing APT). Unlike `apt install`, it does not auto-resolve dependencies — which caused the gnupg error.

---

### 2.3 Import MySQL GPG Signing Key

```bash
wget -qO- https://repo.mysql.com/RPM-GPG-KEY-mysql-2022 | gpg --dearmor | \
  sudo tee /usr/share/keyrings/mysql-apt-key.gpg > /dev/null
```
```bash
sudo gpg --no-default-keyring \
  --keyring /usr/share/keyrings/mysql-apt-key.gpg \
  --keyserver hkp://keyserver.ubuntu.com:80 \
  --recv-keys B7B3B788A8D3785C
```
```
gpg: key B7B3B788A8D3785C: public key "MySQL Release Engineering" imported
gpg: Total number processed: 1
gpg:               imported: 1
```
> 📌 **Why:** APT verifies package integrity using GPG signatures. Without the correct key, `apt update` would show "NO_PUBKEY" warnings and refuse to use the MySQL repo.
> The original 2021 key had expired (2023-12-14) — importing `B7B3B788A8D3785C` (valid until 2027) fixes this.
> **Alternative:** `sudo apt-key add` (deprecated in Ubuntu 22.04+; use keyring files instead)

---

### 2.4 Update Package Lists

```bash
sudo apt update
```
```
Get:2 http://repo.mysql.com/apt/ubuntu noble InRelease [22.7 kB]
Get:9 http://repo.mysql.com/apt/ubuntu noble/mysql-8.4-lts Sources [983 B]
Get:10 http://repo.mysql.com/apt/ubuntu noble/mysql-8.4-lts amd64 Packages [12.6 kB]
Fetched 3690 kB in 1s (4051 kB/s)
All packages are up to date.
```
> 📌 **Why:** Refreshes the local APT package index so `apt install` knows about the newly added MySQL 8.4 packages.

---

### 2.5 Install MySQL Community Server

```bash
sudo apt install -y mysql-community-server
```
```
Setting up mysql-community-server (8.4.8-1ubuntu24.04) ...
# Prompted: Enter root password during install
Created symlink /etc/systemd/system/multi-user.target.wants/mysql.service
done!
```
> 📌 **Why `mysql-community-server`:** This is the full MySQL 8.4 server package. The `-community` flavour is the free, GPL-licensed edition. Oracle also offers `mysql-enterprise-server` (paid, extra tooling).
> **Alternatives:** `mysql-server` (pulls the default Ubuntu repo version — 8.0, not 8.4)
> ⚠️ Set a **strong root password** when prompted — see security notes in [Error #2](#error-2-mysqlclient-wheel-build-failure).

---

### 2.6 Secure MySQL Installation

```bash
sudo mysql_secure_installation
```
```
VALIDATE PASSWORD COMPONENT?  → y
Password policy level:         → 2 (STRONG)
Change root password?          → No (already strong)
Remove anonymous users?        → y ✓
Disallow root login remotely?  → y ✓
Remove test database?          → y ✓
Reload privilege tables?       → y ✓
All done!
```
> 📌 **Why:** Fresh MySQL installs contain anonymous users, a test database, and allow remote root logins — all security risks.
> `mysql_secure_installation` removes these with guided prompts.
> **What it does:**
> | Action | Risk Removed |
> |--------|-------------|
> | Remove anonymous users | Anyone could log in without credentials |
> | Disallow remote root | Brute-force root attacks from the internet |
> | Remove test DB | World-accessible debug data |
> | Flush privileges | Ensures changes take effect immediately |

---

### 2.7 Verify MySQL Service

```bash
sudo systemctl status mysql
```
```
● mysql.service - MySQL Community Server
     Active: active (running) since Sat 2026-03-14 07:31:59 UTC
     Status: "Server is operational"
   Main PID: 109214 (mysqld)
     Memory: 558.6M
```
> 📌 **Why:** `systemctl status` shows PID, memory usage, and last log entries. "Server is operational" confirms MySQL is fully initialized and ready for connections.
> **Alternatives:** `sudo mysqladmin status` · `sudo mysqladmin ping`

---

## 3. Database Setup

> 💡 **Why a dedicated database?** Instead of using the `root` MySQL account for the app, we create a dedicated `insurance` database and user — following the **principle of least privilege**: the app can only access its own data.

### 3.1 Create Database

```bash
sudo mysql -u root -p
```
```sql
CREATE DATABASE insurance CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```
```
Query OK, 1 row affected (0.00 sec)
```
> 📌 **Why `utf8mb4`?** Django recommends `utf8mb4` over `utf8` because it supports the full Unicode range (including emoji, CJK characters). `utf8` in MySQL is limited to 3 bytes per character.
> **`utf8mb4_unicode_ci`** = case-insensitive collation following Unicode standards.
> **Alternatives:** `latin1` (Western Europe only), `utf8` (3-byte, avoid for Django)

```sql
SHOW DATABASES;
```
```
+--------------------+
| Database           |
+--------------------+
| information_schema |
| insurance          |
| mysql              |
| performance_schema |
| sys                |
+--------------------+
5 rows in set (0.01 sec)
```
> 📌 **Why:** Verifies the database was created. The system databases (`mysql`, `performance_schema`, `sys`, `information_schema`) are internal MySQL databases — do not modify them.

---

### 3.2 Restore Database from Backup

```bash
sudo mysql -u root -p insurance < /root/kereta_insurance_backup.sql
```
```
Enter password: <YOUR_MYSQL_ROOT_PASSWORD>
```
> 📌 **Why:** `<` redirect feeds the SQL dump file directly into MySQL as standard input. This is the fastest way to restore a mysqldump backup.
> **Alternatives:**
> - `mysql --login-path=root insurance < backup.sql` (no password prompt with stored credentials)
> - `mysqlimport` (for CSV files, not SQL dumps)
> - GUI tools: MySQL Workbench, DBeaver

```bash
sudo mysql -u root -p -e "USE insurance; SHOW TABLES;"
```
> 📌 **Why `-e`:** Executes a SQL statement non-interactively — useful for scripting and CI/CD pipelines.
> **Verified:** 41 tables restored, including Django migrations, auth tables, and app-specific tables.

---

### 3.3 Create Application DB User

```sql
CREATE USER 'insurance'@'%' IDENTIFIED BY '<YOUR_DB_APP_PASSWORD>';
GRANT ALL PRIVILEGES ON insurance.* TO 'insurance'@'%';
FLUSH PRIVILEGES;
```
```
Query OK, 0 rows affected (0.02 sec)  -- CREATE USER
Query OK, 0 rows affected (0.00 sec)  -- GRANT
Query OK, 0 rows affected (0.00 sec)  -- FLUSH
```
> 📌 **Why `'%'` host?** Allows connections from any IP — useful when the Django app and MySQL may be on different machines. For single-server setups, use `'localhost'` for tighter security.
> **Why GRANT on `insurance.*`?** Restricts the app user to only its own database. If compromised, it cannot access `mysql` or other databases.
>
> | Permission | Scope | Recommendation |
> |-----------|-------|----------------|
> | `ALL PRIVILEGES ON insurance.*` | Full access to one DB | ✅ App user |
> | `ALL PRIVILEGES ON *.*` | Super access | ❌ Never for apps |
> | `SELECT, INSERT, UPDATE, DELETE` | Read-write only | ✅ More restrictive |

---

### 3.4 Enable Remote Access (bind-address)

```bash
sudo nano /etc/mysql/mysql.conf.d/mysqld.cnf
```
```ini
[mysqld]
pid-file        = /var/run/mysqld/mysqld.pid
socket          = /var/run/mysqld/mysqld.sock
datadir         = /var/lib/mysql
log-error       = /var/log/mysql/error.log
bind-address    = 0.0.0.0
```

```bash
sudo systemctl restart mysql
sudo ss -tlnp | grep 3306
```
```
LISTEN 0      151          0.0.0.0:3306       0.0.0.0:*    users:(("mysqld",pid=111126,fd=28))
LISTEN 0      70                 *:33060            *:*    users:(("mysqld",pid=111126,fd=19))
```
> 📌 **Why `bind-address = 0.0.0.0`?** By default MySQL binds to `127.0.0.1` (localhost only). Changing to `0.0.0.0` allows the Django app (or external tools like DBeaver) to connect over the network.
> ⚠️ **Security:** Always restrict access using **GCP Firewall Rules** or `GRANT ... TO 'user'@'specific_ip'` — never rely solely on `bind-address`.
>
> | Port | Service |
> |------|---------|
> | 3306 | MySQL standard client connections |
> | 33060 | MySQL X Protocol (JSON/document API) |

---

### 3.5 Test Connection with App User

```bash
mysql -u insurance -p -h 127.0.0.1
```
```
Server version: 8.4.8 MySQL Community Server - GPL
```
> 📌 **Why `-h 127.0.0.1` instead of `-h localhost`?** Using `localhost` triggers a Unix socket connection; `127.0.0.1` forces TCP/IP — testing the same path the Django app will use.

---

## 4. System User & Directory Setup

> 💡 **Why a separate OS user?** Running the Django app as a dedicated `insurance` Linux user (not `root`) limits damage if the app is compromised. This follows the **principle of least privilege** at the OS level.

### 4.1 Create OS User

```bash
sudo adduser insurance
```
```
info: Adding user 'insurance' (UID 1003, GID 1003)
info: Creating home directory '/home/insurance'
New password: <YOUR_OS_USER_PASSWORD>
passwd: password updated successfully
Is the information correct? [Y/n] y
```
> 📌 **Why `adduser` not `useradd`?** `adduser` is a higher-level Perl script that creates the home directory, copies `/etc/skel` files, and prompts interactively. `useradd` is the low-level command requiring manual flags.
> **Alternatives:** `sudo useradd -m -s /bin/bash -G users insurance`

---

### 4.2 Create Application Directories

```bash
sudo mkdir -p /home/insurance/public_html   # Application code
sudo mkdir -p /home/insurance/logs          # Gunicorn log files
sudo mkdir -p /home/insurance/venv          # Python virtual environment
sudo chown -R insurance:insurance /home/insurance/
```
> 📌 **Why this directory structure?**
>
> | Directory | Purpose |
> |-----------|---------|
> | `public_html/` | Django project root (manage.py lives here) |
> | `logs/` | Gunicorn access & error logs (separate from system logs) |
> | `venv/` | Isolated Python environment (project-specific packages) |
>
> **`-R` (recursive chown):** Ensures the `insurance` user owns all subdirectories and can write log files, collect static files, and create sock files.

---

## 5. Application Deployment

> 💡 **Why unzip to `public_html`?** Convention from the hosting world — `public_html` is the standard document root. Gunicorn's `WorkingDirectory` points here, giving `manage.py` a clean working path.

### 5.1 Install unzip & Extract Project

```bash
sudo apt install -y unzip
sudo unzip /root/Kereta-Insurance-main.zip -d /home/insurance/public_html/
sudo mv /home/insurance/public_html/Kereta-Insurance-main/* /home/insurance/public_html/
sudo rm -rf /home/insurance/public_html/Kereta-Insurance-main/
sudo chown -R insurance:insurance /home/insurance/public_html/
```
> 📌 **Why move files up one level?** The zip extracts into a subdirectory `Kereta-Insurance-main/`. Moving its contents up makes `manage.py` and the Django project directly under `public_html/` — matching the Gunicorn `WorkingDirectory`.

```bash
ls -la /home/insurance/public_html/
```
```
total 60
drwxr-xr-x 7 insurance insurance 4096 Mar 14 08:52 .
-rw-r--r-- 1 insurance insurance  674 Mar 12 14:48 manage.py
-rw-r--r-- 1 insurance insurance 1627 Mar 12 14:48 requirements.txt
drwxr-xr-x 7 insurance insurance 4096 Mar 12 14:48 core
drwxr-xr-x 2 insurance insurance 4096 Mar 12 14:48 insurance_whatsapp
drwxr-xr-x 3 insurance insurance 4096 Mar 12 14:48 master
drwxr-xr-x 4 insurance insurance 4096 Mar 12 14:48 templates
```

---

## 6. Python Virtual Environment & Dependencies

> 💡 **Why a virtual environment?** A venv isolates project Python packages from the system Python. Without it, `pip install` modifies system-wide packages — causing version conflicts across projects.

### 6.1 Check Python & Install Nginx

```bash
python3 --version
```
```
Python 3.12.3
```
> 📌 **Why Python 3.12?** Django 5.x and modern packages require Python 3.10+. Python 3.12 brings 5–10% performance improvements over 3.11.

```bash
sudo apt install -y nginx
sudo apt install -y python3.12-venv
```
> 📌 **Why `python3.12-venv` separately?** Ubuntu ships Python 3.12 without the `venv` module in some configurations. This ensures `python3 -m venv` works.

---

### 6.2 Create venv & Upgrade pip

```bash
sudo su - insurance
python3 -m venv /home/insurance/venv
source /home/insurance/venv/bin/activate
pip install --upgrade pip
```
```
Successfully installed pip-26.0.1
```
> 📌 **Why upgrade pip?** Newer pip versions include faster dependency resolution and better compatibility with modern `pyproject.toml` packages. Always upgrade before installing project requirements.
> **Alternatives:** `pipenv`, `poetry`, `conda` (heavier alternatives with lock file management)

---

### 6.3 Fix mysqlclient Build Errors

> ⚠️ **This step involved multiple errors — see [Error #2](#error-2-mysqlclient-wheel-build-failure) for full details.**

**First attempt (failed):**
```bash
pip install -r /home/insurance/public_html/requirements.txt
```
```
ERROR: Failed to build 'mysqlclient' when getting requirements to build wheel
```

**Diagnosis & Fix — install C build dependencies:**
```bash
# Exit venv and go back to root
deactivate && exit

# Install build tools
sudo apt install -y pkg-config python3-dev default-libmysqlclient-dev build-essential

# Install libmysqlclient (already newest: 8.4.8)
sudo apt install -y libmysqlclient-dev

# Install OpenSSL dev headers (KEY FIX)
sudo apt install -y libssl-dev
```
```
Setting up libssl-dev:amd64 (3.0.13-0ubuntu3.7) ...
```

**Verify fix:**
```bash
pkg-config --cflags mysqlclient
```
```
-I/usr/include/mysql
```
> 📌 **Why `libssl-dev`?** `mysqlclient` is a C extension that links against MySQL's client library, which depends on OpenSSL. Without `openssl.pc` in `PKG_CONFIG_PATH`, the compiler cannot find SSL headers.
>
> | Package | Purpose |
> |---------|---------|
> | `pkg-config` | Finds C library compile flags |
> | `python3-dev` | Python C headers for building extensions |
> | `default-libmysqlclient-dev` | MySQL C client library headers |
> | `build-essential` | GCC compiler tools (gcc, make, g++) |
> | `libssl-dev` | OpenSSL headers (required by mysqlclient) |

---

### 6.4 Successful Requirements Install

```bash
sudo su - insurance
source /home/insurance/venv/bin/activate
pip install -r /home/insurance/public_html/requirements.txt
```
```
Successfully installed all packages.
```

---

### 6.5 Install Gunicorn

```bash
pip install gunicorn
```
```
Successfully installed gunicorn-25.1.0
```
> 📌 **Why Gunicorn?** Django's built-in dev server (`manage.py runserver`) is single-threaded and not suitable for production. Gunicorn (Green Unicorn) is a Python WSGI server that:
> - Spawns multiple worker processes for concurrency
> - Handles graceful worker restarts
> - Integrates with Unix sockets for Nginx
>
> **Alternatives:** `uWSGI` (more configuration options), `Daphne` (for async/Django Channels), `Hypercorn` (ASGI, HTTP/2)

---

## 7. Django Application Setup

> 💡 **Why Django?** Django is a batteries-included Python web framework with ORM, admin interface, authentication, and migrations built in — ideal for rapid development of data-driven applications.

### 7.1 Update settings.py

```bash
nano /home/insurance/public_html/insurance_whatsapp/settings.py
```
> 📌 **Key settings to update:**
>
> ```python
> ALLOWED_HOSTS = ['<YOUR_DOMAIN>', '<YOUR_SERVER_PUBLIC_IP>']
>
> DATABASES = {
>     'default': {
>         'ENGINE': 'django.db.backends.mysql',
>         'NAME': 'insurance',
>         'USER': 'insurance',
>         'PASSWORD': '<YOUR_DB_APP_PASSWORD>',
>         'HOST': '127.0.0.1',
>         'PORT': '3306',
>     }
> }
>
> STATIC_URL = '/static/'
> STATIC_ROOT = '/home/insurance/public_html/staticfiles'
> ```

---

### 7.2 Edit external_benefits.py

```bash
nano /home/insurance/public_html/core/external_benefits.py
```
> 📌 **Note:** `vi` command was not found — see [Error #4](#error-4-vi--dig--ping-not-found). Used `nano` instead.
> **Alternatives:** `vim`, `micro`, `gedit`, VS Code remote (via SSH extension)

---

### 7.3 Run Migrations

```bash
python manage.py migrate
```
```
Operations to perform:
  Apply all migrations: admin, auth, contenttypes, core, django_celery_results, master, sessions
Running migrations:
  No migrations to apply.
  Your models in app(s): 'core' have changes that are not yet reflected in a migration.
  Run 'manage.py makemigrations' to make new migrations.
```
> ⚠️ **Note:** First migrate shows pending changes — see [Error #5](#error-5-django-migrate-shows-unapplied-model-changes).

```bash
python manage.py makemigrations
```
```
Migrations for 'core':
  core/migrations/0045_usersession_grossdue_and_more.py
    + Add field grossdue to usersession
    + Add field last_payment_order_id to usersession
    + Add field netdue to usersession
    + Add field payment_prompt_sent to usersession
```

```bash
python manage.py migrate
```
```
Running migrations:
  No migrations to apply.
```
> 📌 **Why `makemigrations` before `migrate`?** The database already has the schema (from the SQL backup), but Django's migration history may differ from the model definitions. `makemigrations` creates migration files from model changes; `migrate` applies them to the DB.

---

### 7.4 Collect Static Files

```bash
python manage.py collectstatic --noinput
```
```
169 static files copied to '/home/insurance/public_html/staticfiles'.
```
> 📌 **Why?** In production, Nginx serves static files directly (CSS, JS, images) — bypassing Django/Gunicorn for massive performance gains. `collectstatic` gathers all static files from all apps into `STATIC_ROOT`.
> `--noinput` skips the "Are you sure?" confirmation prompt.

---

### 7.5 Test Gunicorn Binding

```bash
find /home/insurance/public_html -name "wsgi.py"
```
```
/home/insurance/public_html/insurance_whatsapp/wsgi.py
```

```bash
gunicorn --bind 0.0.0.0:8000 insurance_whatsapp.wsgi:application
```
```
[INFO] Starting gunicorn 25.1.0
[INFO] Listening at: http://0.0.0.0:8000 (116604)
[INFO] Using worker: sync
[INFO] Booting worker with pid: 116606
```
> 📌 **Why test with `--bind 0.0.0.0:8000` first?** Before setting up the systemd service and Unix socket, testing on a TCP port lets you verify the app starts correctly in a browser. Press `Ctrl+C` to stop.
> **`insurance_whatsapp.wsgi:application`** = Python module path to the WSGI callable.

---

## 8. Gunicorn Systemd Service

> 💡 **Why systemd?** Running Gunicorn as a systemd service means it:
> - Auto-starts on server reboot
> - Restarts automatically on crashes
> - Logs are integrated with `journalctl`
> - Can be managed like any other Linux service (`start`/`stop`/`enable`)

### 8.1 Create Service File

```bash
sudo nano /etc/systemd/system/gunicorn.service
```

```ini
[Unit]
Description=Gunicorn daemon for Insurance Django App
After=network.target

[Service]
User=insurance
Group=insurance
WorkingDirectory=/home/insurance/public_html
ExecStart=/home/insurance/venv/bin/gunicorn \
          --workers 3 \
          --bind unix:/home/insurance/gunicorn.sock \
          --access-logfile /home/insurance/logs/gunicorn-access.log \
          --error-logfile /home/insurance/logs/gunicorn-error.log \
          insurance_whatsapp.wsgi:application

[Install]
WantedBy=multi-user.target
```

> 📌 **Key settings explained:**
>
> | Setting | Value | Reason |
> |---------|-------|--------|
> | `User=insurance` | App OS user | Least privilege; no root access |
> | `--workers 3` | 3 worker processes | `2 * CPU(2) - 1` conservative formula |
> | `--bind unix:/...sock` | Unix socket | Faster than TCP for local Nginx→Gunicorn |
> | `--access-logfile` | Custom log path | Separate from system logs; easy rotation |
> | `After=network.target` | Start order | Ensures network is up before binding |

---

### 8.2 Enable & Start Service

```bash
sudo systemctl daemon-reload
sudo systemctl start gunicorn
sudo systemctl enable gunicorn
```
```
Created symlink /etc/systemd/system/multi-user.target.wants/gunicorn.service
```

```bash
sudo systemctl status gunicorn
```
```
● gunicorn.service - Gunicorn daemon for Insurance Django App
     Active: active (running) since Sat 2026-03-14 09:49:12 UTC; 21s ago
   Main PID: 116798 (gunicorn)
      Tasks: 8 (limit: 9430)
     Memory: 160.0M
```

```bash
ls -la /home/insurance/gunicorn.sock
```
```
srwxrwxrwx 1 insurance insurance 0 Mar 14 09:49 /home/insurance/gunicorn.sock
```
> 📌 **Why verify the socket file?** The `s` in `srwxrwxrwx` confirms it's a **socket file** (not a regular file). Nginx will connect to this socket to forward requests. If it's missing, Nginx will return a 502 Bad Gateway.
> **`rwxrwxrwx` permissions** allow both the `insurance` user (Gunicorn) and `www-data` (Nginx) to read/write the socket.

---

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
