# Project Flow and Deployment Guide

## Architecture Overview
- **Backend:** Python FastAPI
- **Frontend:** Angular deployed in Nginx
- **CI/CD:** GitHub Actions

---

## Part 1: Backend Deployment (Python FastAPI)

### Objective
Deploy the Python FastAPI backend to a Linux server via a GitHub Actions pipeline. The setup ensures isolation from other applications and exposes the backend using GoDaddy DNS.

### Prerequisites (Checklist before starting)
- [ ] **Linux Server (European Cloud):** Accessible via SSH.
  - *Example Public IP:* `198.51.100.10` (Change this to your actual server IP)
- [ ] **GitHub Repository:** FastAPI code is pushed to the `dev` branch.
- [ ] **GoDaddy DNS:** Access to manage DNS records for your domain.
  - *Example Domain:* `yourdomain.com` (Change this to your actual domain)
- [ ] **SSH Keys:** You have an SSH private key that can connect to the server.

### Step-by-Step Backend Implementation

#### Step 1: Server Preparation
Isolate the new FastAPI deployment to prevent conflicts.

1.  **Create an Isolated Directory:**
    ```bash
    sudo mkdir -p /var/www/fastapi-backend-dev
    sudo chown -R ubuntu:www-data /var/www/fastapi-backend-dev # Adjust 'ubuntu' if your user is different
    ```
2.  **Clone the Repository (Initial Setup):**
    ```bash
    cd /var/www/fastapi-backend-dev
    git clone -b dev https://github.com/yourusername/yourrepo.git . # Change URL to your repository URL
    ```
3.  **Setup Virtual Environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```
4.  **Create Independent Service Manager (`systemd`):**
    Create a file named `fastapi-backend.service`:
    ```bash
    sudo nano /etc/systemd/system/fastapi-backend.service
    ```
    *Add the following content (Change paths and user if necessary):*
    ```ini
    [Unit]
    Description=FastAPI Backend Dev Environment
    After=network.target

    [Service]
    User=ubuntu # Change to your server username
    Group=www-data
    WorkingDirectory=/var/www/fastapi-backend-dev
    Environment="PATH=/var/www/fastapi-backend-dev/venv/bin"
    # Port 8001 is used here. Ensure it's not used by other apps.
    ExecStart=/var/www/fastapi-backend-dev/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8001

    [Install]
    WantedBy=multi-user.target
    ```
    Enable and start the service:
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable fastapi-backend.service
    sudo systemctl start fastapi-backend.service
    ```

#### Step 2: Configure GoDaddy DNS (Exposure)
1.  Log in to GoDaddy -> DNS Management for `yourdomain.com`.
2.  Add an **A Record**:
    -   **Type:** `A`
    -   **Name:** `api-dev` (This creates `api-dev.yourdomain.com`)
    -   **Value:** `198.51.100.10` (Change to your Server's Public IP)
    -   **TTL:** 1 Hour

#### Step 3: Setup Reverse Proxy on the Server (Nginx)
Create an Nginx configuration to map the DNS name to the internal port 8001.

1.  Create the config file:
    ```bash
    sudo nano /etc/nginx/sites-available/fastapi-backend
    ```
2.  *Add the following content (Change server_name to your domain):*
    ```nginx
    server {
        listen 80;
        server_name api-dev.yourdomain.com; # Change to match GoDaddy DNS

        location / {
            proxy_pass http://127.0.0.1:8001; # Matches the port in the systemd service
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_addrs;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
    ```
3.  Enable and restart Nginx:
    ```bash
    sudo ln -s /etc/nginx/sites-available/fastapi-backend /etc/nginx/sites-enabled/
    sudo nginx -t # check for syntax errors
    sudo systemctl restart nginx
    ```

#### Step 4: Set up GitHub Secrets for Backend
In your GitHub Repo, go to `Settings` > `Secrets and variables` > `Actions` > `New repository secret`. Add:
-   `SERVER_HOST`: `198.51.100.10` (Change to your Server IP)
-   `SERVER_USERNAME`: `ubuntu` (Change to your SSH username)
-   `SERVER_SSH_KEY`: `-----BEGIN OPENSSH PRIVATE KEY-----...` (Paste your private SSH key)

#### Step 5: Create Backend GitHub Actions Workflow
Create `.github/workflows/deploy-backend-dev.yml` in your repository.

```yaml
name: Deploy Python FastAPI Backend (Dev)

on:
  push:
    branches:
      - dev # Triggers on push to dev branch
    paths:
      - 'backend/**' # Optional: Only trigger if backend code changes

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to Linux Server via SSH
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USERNAME }}
          key: ${{ secrets.SERVER_SSH_KEY }}
          script: |
            cd /var/www/fastapi-backend-dev # Path defined in Step 1
            git pull origin dev
            source venv/bin/activate
            # Ensure new dependencies are installed
            pip install -r requirements.txt
            # Restart the service to apply changes
            sudo systemctl restart fastapi-backend.service
```

---

## Part 2: Frontend Deployment (Angular in Nginx)

### Objective
Deploy the Angular application to the same Linux server using GitHub Actions. The Angular app will be built on the GitHub runner and the compiled static files will be deployed to Nginx.

### Prerequisites (Checklist before starting)
- [ ] **Linux Server:** Same server as the backend (`198.51.100.10`).
- [ ] **GitHub Repository:** Angular code pushed to the `dev` branch.
- [ ] **GoDaddy DNS:** Access to manage DNS records.
  - *Example Domain:* `app-dev.yourdomain.com` (Change to your desired frontend domain)
- [ ] **Node.js/npm:** Installed on your local machine to test builds (Not required on the server, as GitHub Actions will build it).

### Step-by-Step Frontend Implementation

#### Step 1: Server Preparation (Directory Setup)
Since Nginx serves static files for Angular, we just need a directory to hold them. No Node.js is needed on the server.

1.  **Create the Web Directory:**
    ```bash
    sudo mkdir -p /var/www/angular-frontend-dev
    sudo chown -R ubuntu:www-data /var/www/angular-frontend-dev # Change 'ubuntu' if needed
    ```

#### Step 2: Configure GoDaddy DNS (Exposure)
1.  Log in to GoDaddy -> DNS Management for `yourdomain.com`.
2.  Add an **A Record**:
    -   **Type:** `A`
    -   **Name:** `app-dev` (This creates `app-dev.yourdomain.com`)
    -   **Value:** `198.51.100.10` (Change to your Server's Public IP)
    -   **TTL:** 1 Hour

#### Step 3: Setup Nginx Server Block for Frontend
Create an Nginx configuration to map the frontend domain to the static files directory.

1.  Create the config file:
    ```bash
    sudo nano /etc/nginx/sites-available/angular-frontend
    ```
2.  *Add the following content (Change server_name to your domain):*
    ```nginx
    server {
        listen 80;
        server_name app-dev.yourdomain.com; # Change to match GoDaddy DNS

        root /var/www/angular-frontend-dev; # Path defined in Step 1
        index index.html index.htm;

        location / {
            # Angular routing requirement: redirect 404s to index.html
            try_files $uri $uri/ /index.html;
        }
    }
    ```
3.  Enable and restart Nginx:
    ```bash
    sudo ln -s /etc/nginx/sites-available/angular-frontend /etc/nginx/sites-enabled/
    sudo nginx -t # check for syntax errors
    sudo systemctl restart nginx
    ```

#### Step 4: Angular Environment Configuration
Ensure your Angular app points to the correct backend API URL.
In your Angular project, edit `src/environments/environment.ts` (or `environment.development.ts` depending on your setup).

*Example `environment.ts`:*
```typescript
export const environment = {
  production: false,
  // Change this to the backend domain you configured in Part 1 -> Step 2
  apiUrl: 'http://api-dev.yourdomain.com' 
};
```

#### Step 5: Create Frontend GitHub Actions Workflow
Create `.github/workflows/deploy-frontend-dev.yml` in your repository. This workflow builds the Angular app on the GitHub runner and securely copies the `dist/` folder to the server using `rsync` over SSH.

**Required Secrets (Same as Backend - no need to recreate if they exist in the repo):**
-   `SERVER_HOST`
-   `SERVER_USERNAME`
-   `SERVER_SSH_KEY`

*Workflow definition:*
```yaml
name: Deploy Angular Frontend (Dev)

on:
  push:
    branches:
      - dev # Triggers on push to dev branch
    paths:
      - 'frontend/**' # Optional: Only trigger if frontend code changes

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v3

      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '18' # Change to match your Angular project's required Node version

      - name: Install Dependencies
        working-directory: ./frontend # Change if your Angular app is in a different folder
        run: npm ci

      - name: Build Angular App
        working-directory: ./frontend # Change if your Angular app is in a different folder
        run: npm run build -- --configuration development

      - name: Deploy to Server via Rsync
        uses: easingthemes/ssh-deploy@main
        env:
          SSH_PRIVATE_KEY: ${{ secrets.SERVER_SSH_KEY }}
          REMOTE_HOST: ${{ secrets.SERVER_HOST }}
          REMOTE_USER: ${{ secrets.SERVER_USERNAME }}
          # SOURCE: Path to the built files relative to repository root. 
          # Example: if your app is named 'my-app', the path is usually 'frontend/dist/my-app/'
          SOURCE: "frontend/dist/your-angular-app-name/" # CHANGE THIS to match the output folder of 'npm run build'
          # TARGET: The directory created in Frontent Step 1
          TARGET: "/var/www/angular-frontend-dev/"
```
