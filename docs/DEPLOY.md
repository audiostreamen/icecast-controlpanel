# Ingest Admin – Deploy

## Vereisten
- Python 3.11+, pip, venv
- systemd + sudo
- NGINX of een reverse proxy

## Installatie
1. Virtualenv + deps:
   ```bash
   cd /opt/ingest-admin
   python3 -m venv venv
   venv/bin/pip install -U pip wheel
   venv/bin/pip install -r requirements.txt
   ```

2. Config (/etc/default/ingest-admin):
   ```bash
   sudo tee /etc/default/ingest-admin >/dev/null <<'EOF'
   ICECAST_STATUS_URL="http://127.0.0.1:8001/status-json.xsl"
   ICECAST_NAME="Icecast-KH"
   ADMIN_TOKEN="<zet-een-sterke-token>"
   SECRET_KEY="<zet-een-sterke-secret>"
   ICECAST_UNIT="icecast-kh.service"
   LIQUIDSOAP_UNIT="liquidsoap.service"
   ICE_ADMIN_BASE="http://127.0.0.1:8001"
   ICE_ADMIN_USER="admin"
   ICE_ADMIN_PASS="<secret>"
   EOF
   sudo chmod 600 /etc/default/ingest-admin
   ```

3. Sudoers (wachtwoordloos) voor wrapper:
   ```bash
   sudo tee /etc/sudoers.d/ingest-admin >/dev/null <<'EOF'
   www-data ALL=(root) NOPASSWD: /usr/local/bin/ingestctl.sh
   EOF
   sudo visudo -c
   ```

4. systemd unit (Gunicorn):
   ```bash
   sudo tee /etc/systemd/system/ingest-admin.service >/dev/null <<'EOF'
   [Unit]
   Description=Ingest Admin (Flask/Gunicorn)
   After=network.target

   [Service]
   User=www-data
   Group=www-data
   WorkingDirectory=/opt/ingest-admin
   EnvironmentFile=/etc/default/ingest-admin
   ExecStart=/opt/ingest-admin/venv/bin/gunicorn -w 2 -b 127.0.0.1:5050 wsgi:app
   Restart=on-failure

   [Install]
   WantedBy=multi-user.target
   EOF
   sudo systemctl daemon-reload
   sudo systemctl enable --now ingest-admin
   ```

5. NGINX reverse proxy (voorbeeld):
   ```nginx
   server {
     listen 80;
     server_name admin.example.tld;
     location /ingest-admin/ {
       proxy_set_header X-Forwarded-Prefix /ingest-admin;
       proxy_set_header X-Forwarded-Proto $scheme;
       proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       proxy_pass http://127.0.0.1:5050/;
     }
   }
   ```

## Health & Test
- Health: `curl -s http://127.0.0.1:5050/health`
- Status: `curl -s http://127.0.0.1:5050/api/status | jq` 
- UI: ga naar de reverse proxy URL (met subpad als ingesteld).

## Beveiliging
- ADMIN_TOKEN/SECRET_KEY zijn verplicht.
- Paneel achter VPN/IP‑allowlist; sudoers is beperkt tot één wrapper.

## Verwijderen
Gebruik het uninstall-script om de service en bijbehorende configuratie netjes te verwijderen:

```bash
cd /opt/ingest-admin
sudo bash contrib/uninstall.sh --yes --purge-env --sudoers --nginx --purge-venv
```

