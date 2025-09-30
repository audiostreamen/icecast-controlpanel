#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<EOF
Ingest Admin installer (non-interactive friendly)

Gebruik: $0 [--yes] [--with-nginx]

Stappen:
  - Maakt venv en installeert requirements
  - Plaatst voorbeeld env: /etc/default/ingest-admin (geen overschrijving)
  - Zet sudoers voor wrapper (www-data -> /usr/local/bin/ingestctl.sh)
  - Installeert systemd unit en start service
  - (Optioneel) plaatst NGINX conf (sites-available) en herlaadt NGINX

Opties:
  --yes          Voer zonder extra bevestiging uit
  --with-nginx   Installeer voorbeeld NGINX-config (niet inschakelen zonder confirm)
EOF
}

YES=0
WITH_NGINX=0
while (($#)); do
  case "$1" in
    --yes) YES=1;;
    --with-nginx) WITH_NGINX=1;;
    -h|--help) usage; exit 0;;
    *) echo "Onbekende optie: $1" >&2; usage; exit 2;;
  esac
  shift
done

confirm() {
  local msg="${1:-Doorgaan?} [y/N]: "
  if (( YES==1 )); then return 0; fi
  read -r -p "$msg" ans || return 1
  [[ "$ans" =~ ^([Yy]|[Yy][Ee][Ss])$ ]]
}

ROOT=/opt/ingest-admin
ENVFILE=/etc/default/ingest-admin
UNIT_DST=/etc/systemd/system/ingest-admin.service
NGINX_AVAIL=/etc/nginx/sites-available/ingest-admin.conf
NGINX_EN=/etc/nginx/sites-enabled/ingest-admin.conf

echo "[1/5] Venv + dependencies"
python3 -m venv "$ROOT/venv"
"$ROOT/venv/bin/pip" install -U pip wheel
"$ROOT/venv/bin/pip" install -r "$ROOT/requirements.txt"

echo "[2/5] Environment file"
if [[ -e "$ENVFILE" ]]; then
  echo "- Bestaat al: $ENVFILE (niet overschreven)"
else
  install -o root -g root -m 0644 -D "$ROOT/contrib/ingest-admin.env.example" "$ENVFILE"
  echo "- Voorbeeld geplaatst: $ENVFILE (SECRET_KEY/ADMIN_TOKEN invullen!)"
  chmod 600 "$ENVFILE"
fi

echo "[3/5] sudoers voor wrapper"
SUDOERS=/etc/sudoers.d/ingest-admin
if [[ -e "$SUDOERS" ]]; then
  echo "- Bestaat al: $SUDOERS"
else
  echo 'www-data ALL=(root) NOPASSWD: /usr/local/bin/ingestctl.sh' | sudo tee "$SUDOERS" >/dev/null
  visudo -cf "$SUDOERS" >/dev/null
  echo "- Sudoers toegevoegd: $SUDOERS"
fi

echo "[4/5] systemd unit"
install -o root -g root -m 0644 -D "$ROOT/contrib/ingest-admin.service" "$UNIT_DST"
systemctl daemon-reload
if confirm "Service starten/inschakelen?"; then
  systemctl enable --now ingest-admin
  systemctl status --no-pager ingest-admin || true
else
  echo "- Sla starten over (unit geplaatst)"
fi

if (( WITH_NGINX==1 )); then
  echo "[5/5] NGINX config"
  install -o root -g root -m 0644 -D "$ROOT/contrib/nginx-ingest-admin.conf" "$NGINX_AVAIL"
  if [[ ! -e "$NGINX_EN" ]]; then
    if confirm "NGINX site inschakelen en herladen?"; then
      ln -sf "$NGINX_AVAIL" "$NGINX_EN"
      nginx -t && systemctl reload nginx
    else
      echo "- NGINX site niet ingeschakeld"
    fi
  else
    echo "- NGINX site al enabled: $NGINX_EN"
  fi
else
  echo "[5/5] NGINX config: overgeslagen (gebruik --with-nginx om te plaatsen)"
fi

echo "Klaar. Controleer:"
echo "- Health: curl -s http://127.0.0.1:5050/health"
echo "- Status: curl -s http://127.0.0.1:5050/api/status | jq"
echo "- UI via reverse proxy (zie contrib/nginx-ingest-admin.conf)"

