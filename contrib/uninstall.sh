#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<EOF
Ingest Admin uninstaller

Gebruik: $0 [--yes] [--purge-env] [--sudoers] [--nginx] [--purge-venv]

Standaard:
  - Stopt en disabled de systemd service 'ingest-admin' en verwijdert de unit

Opties:
  --yes         Voer uit zonder extra bevestiging
  --purge-env   Verwijder /etc/default/ingest-admin
  --sudoers     Verwijder /etc/sudoers.d/ingest-admin
  --nginx       Verwijder NGINX conf (sites-available/enabled) en reload nginx
  --purge-venv  Verwijder /opt/ingest-admin/venv
EOF
}

YES=0
PURGE_ENV=0
PURGE_SUDOERS=0
PURGE_NGINX=0
PURGE_VENV=0

while (($#)); do
  case "$1" in
    --yes) YES=1;;
    --purge-env) PURGE_ENV=1;;
    --sudoers) PURGE_SUDOERS=1;;
    --nginx) PURGE_NGINX=1;;
    --purge-venv) PURGE_VENV=1;;
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

echo "[1/5] Stoppen en disablen van service 'ingest-admin'"
if systemctl list-unit-files | grep -q '^ingest-admin\.service'; then
  systemctl stop ingest-admin 2>/dev/null || true
  systemctl disable ingest-admin 2>/dev/null || true
else
  echo "- Service niet gevonden (ingest-admin.service)"
fi

echo "[2/5] Unit verwijderen"
UNIT=/etc/systemd/system/ingest-admin.service
if [[ -e "$UNIT" ]]; then
  rm -f "$UNIT"
  systemctl daemon-reload
  echo "- Unit verwijderd"
else
  echo "- Unit niet aanwezig: $UNIT"
fi

if (( PURGE_ENV==1 )); then
  echo "[3/5] Env verwijderen"
  if [[ -e /etc/default/ingest-admin ]]; then
    if confirm "Verwijder /etc/default/ingest-admin?"; then
      rm -f /etc/default/ingest-admin
      echo "- Env verwijderd"
    else
      echo "- Env behouden"
    fi
  else
    echo "- Env niet aanwezig"
  fi
else
  echo "[3/5] Env behouden (gebruik --purge-env om te verwijderen)"
fi

if (( PURGE_SUDOERS==1 )); then
  echo "[4/5] Sudoers verwijderen"
  if [[ -e /etc/sudoers.d/ingest-admin ]]; then
    if confirm "Verwijder /etc/sudoers.d/ingest-admin?"; then
      rm -f /etc/sudoers.d/ingest-admin
      visudo -c >/dev/null || echo "WAARSCHUWING: sudoers check gaf een fout" >&2
      echo "- Sudoers verwijderd"
    else
      echo "- Sudoers behouden"
    fi
  else
    echo "- Sudoers niet aanwezig"
  fi
else
  echo "[4/5] Sudoers behouden (gebruik --sudoers om te verwijderen)"
fi

if (( PURGE_NGINX==1 )); then
  echo "[5/5] NGINX conf verwijderen"
  AV=/etc/nginx/sites-available/ingest-admin.conf
  EN=/etc/nginx/sites-enabled/ingest-admin.conf
  [[ -L "$EN" ]] && rm -f "$EN" && echo "- Disabled: $EN" || true
  [[ -e "$AV" ]] && rm -f "$AV" && echo "- Removed: $AV" || true
  if command -v nginx >/dev/null 2>&1; then
    nginx -t && systemctl reload nginx || echo "- NGINX reload overgeslagen (test faalde)"
  fi
else
  echo "[5/5] NGINX conf behouden (gebruik --nginx om te verwijderen)"
fi

if (( PURGE_VENV==1 )); then
  if confirm "Verwijder venv (/opt/ingest-admin/venv)?"; then
    rm -rf /opt/ingest-admin/venv
    echo "- venv verwijderd"
  else
    echo "- venv behouden"
  fi
fi

echo "Klaar."

