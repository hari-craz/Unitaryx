# Production Deployment Guide: CI/CD & Portainer GitOps

This document outlines the deployment architecture for the project using GitHub Actions, GHCR, and Portainer GitOps on TrueNAS SCALE.

## 1. Architecture Overview
- **CI/CD Pipeline**: GitHub Actions automatically lints, tests, builds, and pushes Docker images to GHCR (GitHub Container Registry) whenever a commit is pushed to `main` or a semantic version tag (e.g., `v1.0.0`) is created.
- **Image Registry**: GHCR securely stores the built images.
- **Deployment**: A webhook triggers Portainer to pull the latest `docker-compose.yml` from GitHub and the latest image from GHCR, preserving all database volumes and environment variables.

---

## 2. GitHub Secrets Setup
To allow the CI pipeline to function and deploy the code, navigate to **Settings > Secrets and variables > Actions** in your GitHub repository and add the following secrets:

- `PORTAINER_WEBHOOK_URL`: The full URL provided by Portainer when you enable Webhook deployment for your stack (e.g., `https://portainer.yourdomain.com/api/webhooks/xxxx-xxxx`).
- `PROD_URL`: The URL of your application to verify health after deployment (e.g., `https://unitaryx.org`).

*(Note: `GITHUB_TOKEN` is automatically provided by Actions for pushing to GHCR.)*

---

## 3. Portainer Configuration (GitOps Mode)

### Step 3.1: Authenticate Portainer with GHCR
Since the image is private, Portainer must be allowed to pull it.
1. In GitHub, create a Personal Access Token (Classic) with the `read:packages` scope.
2. In Portainer, go to **Registries > Add registry**.
3. Select **GitHub Container Registry**.
4. Enable Authentication.
5. Use your GitHub Username and paste the Personal Access Token as the password. Save it.

### Step 3.2: Create the GitOps Stack
1. Go to **Stacks > Add stack**.
2. Name the stack (e.g., `unitaryx-prod`).
3. Select **Repository** build method.
4. Set Repository URL to your GitHub repo (e.g., `https://github.com/username/unitaryx`).
5. Set Repository reference to `refs/heads/main`.
6. Enable **Automatic updates** and choose **Webhook**. 
7. **Important**: Copy the generated Webhook URL and save it to your GitHub Secrets (`PORTAINER_WEBHOOK_URL`).
8. Under **Environment variables**, set the required production values:
   - `REGISTRY`: `ghcr.io/YOUR_GITHUB_USERNAME/YOUR_REPO_NAME`
   - `SECRET_KEY`, `ADMIN_EMAIL`, `ADMIN_PASS`, `SUPERADMIN_EMAIL`, `SUPERADMIN_PASSWORD`
   - `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`
9. Click **Deploy the stack**.

---

## 4. Rollback Procedure
Portainer Standalone does not natively "rollback" to a previous state automatically. If a deployment fails (e.g., the health check fails):
1. Navigate to your GitHub Repository -> **Actions**.
2. Find the last successful build.
3. If you used a semantic version tag (e.g., `v1.2.0`), you can manually re-trigger a deployment by pointing Portainer's environment variable `APP_VERSION=v1.2.0` and updating the stack manually, OR you can `git revert` the bad commit on `main`, which will automatically trigger a new clean build and deployment.

## 5. Local Development
For local testing without GitOps:
```bash
docker-compose -f docker-compose.yml up --build -d
```
*(Since `build:` was removed from the GitOps `docker-compose.yml`, local development should use an override file like `docker-compose.override.yml` containing the `build: context: .` directives).*

## 6. Database backups and restore test

The database lives in the `db_data_v2` Docker volume. Volumes are not backups, so dump it regularly to a folder **outside** Docker.

**Nightly backup** (on the node that runs the `db` service). Install once:

```bash
sudo mkdir -p /var/backups/unitaryx && sudo chown "$USER" /var/backups/unitaryx
( crontab -l 2>/dev/null; echo '15 2 * * * /path/to/repo/scripts/backup_db.sh >> /var/log/unitaryx_backup.log 2>&1' ) | crontab -
```

`scripts/backup_db.sh` writes `unitaryx_YYYYmmdd_HHMMSS.sql.gz`, verifies it is a valid, non-empty dump, and keeps 14 days (`KEEP_DAYS`). It exits non-zero on failure. Also copy the folder off the machine (NAS, rclone to cloud storage): a backup on the same disk does not survive a disk failure.

**Restore test** (run monthly and after any infrastructure change). Restores the newest dump into a throwaway container and prints row counts, without touching production:

```bash
scripts/restore_test.sh
```

**Real restore** into the live database (after taking a fresh backup of what is there):

```bash
zcat /var/backups/unitaryx/<file>.sql.gz | docker exec -i $(docker ps -q -f name=unitaryx_db) psql -U unitaryx -d unitaryx -v ON_ERROR_STOP=1 -1
```

The dump contains a full schema, so restore into an empty database (drop and recreate the `public` schema first) to avoid duplicate-object errors. Dumps contain user emails and password hashes: keep them private and out of git.

**Startup check:** the app refuses to boot if any table is missing after initialization, so an empty database shows up as a crash-looping service instead of a site that returns 500s.
