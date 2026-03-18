
# Part 1: Header + ToC + Architecture + Section 1
part1 = r"""# 🚀 MySQL 8.4 LTS + Django Deployment Guide
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
"""

# Part 2: MySQL Installation section
part2 = r"""
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
"""

with open('mysql8-4-installation-guide.md', 'w', encoding='utf-8') as f:
    f.write(part1)
    f.write(part2)

print("Part 1+2 written:", len(part1)+len(part2), "chars")
