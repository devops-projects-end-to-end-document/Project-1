
part3 = r"""
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
"""

part4 = r"""
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
"""

with open('mysql8-4-installation-guide.md', 'a', encoding='utf-8') as f:
    f.write(part3)
    f.write(part4)

print("Parts 3+4 appended. Total size:")
import os
print(os.path.getsize('mysql8-4-installation-guide.md'), "bytes")
