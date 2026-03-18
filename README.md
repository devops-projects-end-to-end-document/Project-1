# 🚀 Project Deployment & Flow Architecture

Welcome to the overarching documentation for our full-stack project deployment. This guide outlines the end-to-end flow of how the application is built, managed, and deployed gracefully without delving into the command-line specifics.

## 🏗️ Tech Stack Overview

*   **Backend:** Python FastAPI
*   **Frontend:** Angular
*   **Web Server / Reverse Proxy:** Nginx
*   **CI/CD Automation:** GitHub Actions
*   **DNS Management:** GoDaddy

---

## ⚙️ Backend Deployment Workflow

The backend infrastructure is designed for robust performance, continuous integration, and seamless API delivery.

*   **Environment Isolation:** The FastAPI application operates within a dedicated virtual environment, ensuring dependencies remain contained and secure.
*   **Continuous Service:** The application runs as a managed automated background service (via `systemd`) to guarantee high availability and automatic restarts.
*   **Automated Pipeline:** Upon pushing updates to the repository, GitHub Actions securely connects to the Linux server, pulls the latest source code, and refreshes the application logic.
*   **Dependency Synchronization:** The automated pipeline evaluates and installs any new Python package requirements instantly after code updates.
*   **Traffic Routing:** Nginx acts as a reverse proxy, filtering and securely forwarding HTTP requests from the registered GoDaddy domain to the internal FastAPI port.

---

## 🎨 Frontend Deployment Workflow

The frontend pipeline is optimized for speed, delivering a static, highly cached user interface directly to the end users.

*   **Cloud Build Process:** GitHub Actions provisions a temporary Node.js environment to fetch dependencies, compile, and aggressively minify the Angular application.
*   **Secure File Transfer:** Once compiled, the static artifact (`dist` folder) is securely synchronized to the Linux server's web directory via encrypted file transfer (`rsync`).
*   **Static Serving:** Nginx intercepts domain traffic and efficiently serves the static Angular assets.
*   **Client-Side Routing:** To support Angular's Single Page Application (SPA) architecture, the web server is configured to gracefully fallback any unresolved routes to the core `index.html`.
*   **DNS Resolution:** A dedicated GoDaddy `A Record` precisely points the application's domain to the Linux server's IP address.

---

## 🔒 Security & Secrets Management

Security remains a top priority throughout the continuous deployment lifecycle.

*   **Encrypted Secrets:** All sensitive credentials—including the Server IP, SSH Keys, and Usernames—are stored securely within **GitHub Secrets** and are never exposed in the source code.
*   **Isolated Directories:** Both backend and frontend assets reside in strictly separated directories with appropriate ownership boundaries to minimize security risks.
*   **Environment Variables:** The Angular application dynamically pulls the correct backend API domain configurations through structured environment files before the build stage.

***

*This automated flow allows developers to solely focus on writing code, while the CI/CD pipeline seamlessly handles testing, building, and live server deployment!*