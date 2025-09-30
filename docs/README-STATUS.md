# Ingest Admin – Status, Config & Roadmap

Dit document beschrijft wat er is gebouwd, hoe je het draait (met MySQL 8), welke configuratie belangrijk is, en wat de volgende stappen zijn.

## Wat is gerealiseerd
- Twee‑koloms UI met vaste zijbalk (Service status, Admin Config, Systeemacties, Services‑link) en hoofdinhoud (listeners, muziekbeheer, bestanden, widgets, help).
- Per‑mount acties (soft reload, disconnect, moveclients) en “move all”; copy‑curl voor admin endpoints.
- Muziekbeheer met upload; Bestanden in map met browse/delete/upload‑in‑dir.
- Widgets & Links:
  - Liquidsoap snippets (ratio en elke N minuten) + “Apply” acties die snippet schrijven en Liquidsoap veilig herladen (respecteert DRY‑RUN).
  - Link naar DB statuspagina.
- UI‑login met sessies, ProxyFix voor subpad ‘/admin’, secure cookies (Secure/HttpOnly/SameSite=Lax).
- NGINX reverse proxy op /admin met HSTS ingeschakeld.
- SQLAlchemy + Alembic migraties (SQLite→MySQL 8), DB_URL geconfigureerd (nu MySQL), helper script db‑migrate.sh.
- MySQL hardening: user alleen op 127.0.0.1; wildcard/localhost hosts verwijderd.
- DB‑badge in header (DB OK/ERR) en /admin/db-status (engine/driver/DB/tafeltellingen).
- Instellen (/admin/settings) met tabs: Algemeen, Limieten, Functies, Icecast 2 KH, AutoDJ, Relais. Waarden persist in DB.
- Services (/admin/services): overzicht, aanmaken, selecteren (actief), verwijderen (niet‑actief). Instellen gebruikt de geselecteerde service.
- Directory‑validatie voor upload/delete (realpath check binnen MOUNT_DIR).

## Belangrijke ENV‑variabelen
- ADMIN_TOKEN, SECRET_KEY (verplicht), ADMIN_LOGIN_USER/PASS of ADMIN_LOGIN_PASS_FILE
- ICECAST_STATUS_URL, ICECAST_NAME, ICECAST_UNIT, LIQUIDSOAP_UNIT
- ICE_ADMIN_BASE (+ ICE_ADMIN_USER/PASS of ICE_ADMIN_PASS_FILE), ICE_URL_PUBLIC/PRIVATE
- MOUNT_DIR, MUSIC_DIR (Music), JINGLES_DIR (Jingles), PLAYLISTS_DIR
- MOVEALL_MIN_INTERVAL_SEC (10), MAX_UPLOAD_MB (100), ADMIN_DRY_RUN
- DB_URL (MySQL), LIQ_SNIPPET_PATH (/etc/liquidsoap/snippets/admin.liq)

## Deploy & Operatie
- UI: https://<domein>/admin (Proxy: X‑Forwarded‑Prefix /admin)
- Health: curl -s http://127.0.0.1:5011/health → 200
- Logs UI: /admin/logs (read‑only; filters unit/n)
- DB migraties: ./contrib/db-migrate.sh upgrade
- Services beheer: /admin/services → selecteer service → /admin/settings

### NGINX (samenvatting)
- Proxy: `/admin/` → `127.0.0.1:5011/`, headers X‑Forwarded‑Prefix; HSTS actief.
- Reload: `systemctl reload nginx`

### Database (MySQL 8)
- DB en user (lokaal):
  - `CREATE DATABASE ingest_admin CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;`
  - `CREATE USER 'ingest_admin'@'127.0.0.1' IDENTIFIED BY '<STRONGPASS>';`
  - `GRANT ALL ON ingest_admin.* TO 'ingest_admin'@'127.0.0.1'; FLUSH PRIVILEGES;`
- Migrations:
  - `cd /opt/ingest-admin && venv/bin/pip install -r requirements.txt && ./contrib/db-migrate.sh upgrade`
- Health: `curl -s http://127.0.0.1:5011/health`

## Roadmap (volgende stappen)
1) Services bewerken (inline):
   - Edit op /services (naam/type) naast selecteren en verwijderen.
2) Instellen valideren en toepassen:
   - Sterke validatie (port uniek, wachtwoorden policy, paden bestaan), feedback in UI.
   - Icecast‑specifiek: opties (intro/redirect/public/YP) toepassen via admin/config + reload (nu wordt reload ondersteund, settings persist in DB).
3) Security & observability:
   - Login rate‑limit, auditlog voor Instellen acties.
   - Structured logs of optionele Sentry/Prometheus endpoints.
4) UX polish:
   - Icons/badges, sticky listeners kaart, filter/sortering in bestanden en services.

## Known items
- Icecast optie‑toepassing is nu “reload na opslaan”; directe configuratie push vereist extra integratie (afhankelijk van deployment).
- Directory‑validatie actief; mapping uit bestand/env blijft toegestaan maar wordt nu veilig gejoined binnen MOUNT_DIR.

## Snelle checklijst
- Login werkt (admin/pw via env).
- DB‑badge OK, /admin/db-status toont tabellen.
- Services aangemaakt en geselecteerd.
- Instellen slaat op en (optioneel) herlaadt Icecast.
- Liquidsoap snippet applied en reload OK.
- Logs endpoint werkt.

Laat weten welke stap je als volgende wil — dan bouw ik die uit.
