#!/usr/bin/env python3
import os, re, subprocess, json, urllib.request, tempfile, time, logging
from flask import Flask, render_template_string, request, Response, abort, redirect, get_flashed_messages, flash, url_for, session
from werkzeug.middleware.proxy_fix import ProxyFix
from sqlalchemy.exc import SQLAlchemyError

from db import get_session, engine
from models import Base, Service, ServiceLimits, ServiceFeatures, ServiceIcecast, ServiceAutoDJ, ServiceRelay
from werkzeug.utils import secure_filename

APP_TITLE = "Ingest Admin (Lite)"

# Optioneel: laad /etc/default/ingest-admin en .env overlays om env-variabelen te vullen
def _load_env_file(path: str):
  try:
    if not os.path.exists(path):
      return
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
      for line in fh:
        line = line.strip()
        if not line or line.startswith("#"):  # comment/empty
          continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line)
        if not m:
          continue
        key, val = m.group(1), m.group(2)
        # strip optional export and quotes
        if key == "export":
          continue
        val = val.strip()
        if (val.startswith("\"") and val.endswith("\"")) or (val.startswith("'") and val.endswith("'")):
          val = val[1:-1]
        # Respecteer reeds ingestelde env
        if key not in os.environ:
          os.environ[key] = val
  except Exception:
    pass

def _maybe_load_secret_file(var_file_key: str, target_key: str):
  try:
    p = os.environ.get(var_file_key, '').strip()
    if p and target_key not in os.environ and os.path.exists(p):
      # Veiligheidscheck: liever 600
      try:
        st = os.stat(p)
        mode = st.st_mode & 0o777
        # We lezen ook zonder 600, maar we veranderen niets aan permissies hier
      except Exception:
        mode = None
      with open(p, 'r', encoding='utf-8', errors='ignore') as fh:
        secret = fh.read().strip()
      if secret:
        os.environ[target_key] = secret
  except Exception:
    pass

def _load_env_defaults():
  # 1) hoofd EnvironmentFile (systemd)
  _load_env_file("/etc/default/ingest-admin")
  # 2) optionele .env overlay
  overlay = os.environ.get("INGEST_ADMIN_ENV") or os.environ.get("ENV_FILE") or "/etc/ingest-admin.env"
  if overlay:
    _load_env_file(overlay)
  # 3) secret files
  _maybe_load_secret_file("ICE_ADMIN_PASS_FILE", "ICE_ADMIN_PASS")
  _maybe_load_secret_file("ADMIN_LOGIN_PASS_FILE", "ADMIN_LOGIN_PASS")

_load_env_defaults()

ICECAST_STATUS_URL = os.environ.get("ICECAST_STATUS_URL", "http://127.0.0.1:8001/status-json.xsl")
ICECAST_NAME       = os.environ.get("ICECAST_NAME", "Icecast-KH")
ADMIN_TOKEN        = os.environ.get("ADMIN_TOKEN", "")
ICE_URL_PUBLIC     = os.environ.get("ICE_URL_PUBLIC", "http://127.0.0.1:8000")
MOUNT_DIR          = os.environ.get("MOUNT_DIR", "/srv/fallback-music")
ICE_ADMIN_BASE     = os.environ.get("ICE_ADMIN_BASE", os.environ.get("ICE_ADMIN_URL", ""))
ADMIN_DRY_RUN      = os.environ.get("ADMIN_DRY_RUN", "")
MOVEALL_MIN_INTERVAL_SEC = int(os.environ.get("MOVEALL_MIN_INTERVAL_SEC", "10") or "10")

# Media secties (submappen van MOUNT_DIR)
PLAYLISTS_DIR = os.environ.get("PLAYLISTS_DIR", "PLAYLISTS")
JINGLES_DIR   = os.environ.get("JINGLES_DIR", "Jingles")
MUSIC_DIR     = os.environ.get("MUSIC_DIR", "Music")

# Gebruik een stabiele secret voor flash-meldingen
SECRET_KEY         = os.environ.get("SECRET_KEY", ADMIN_TOKEN or "please-change-this")
ADMIN_LOGIN_USER   = (os.environ.get("ADMIN_LOGIN_USER", "") or "").strip()
ADMIN_LOGIN_PASS   = (os.environ.get("ADMIN_LOGIN_PASS", "") or "").strip()

HTML = """
<!doctype html>
<html lang="nl">
<meta charset="utf-8">
<title>{{title}}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Arial,sans-serif;margin:24px;color:#1f2937}
  header{display:flex;justify-content:space-between;align-items:center;margin:0 0 12px}
  h1{margin:0;font-size:22px}
  h2{margin:0 0 8px;font-size:16px;color:#374151}
  .muted{color:#6b7280;font-size:12px}
  .grid{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(280px,1fr))}
  .layout{display:grid;gap:16px}
  @media (min-width: 920px){ .layout{grid-template-columns:320px 1fr} }
  .sidebar{display:grid;gap:16px;align-content:start;position:sticky;top:12px;height:fit-content}
  .main{display:grid;gap:16px}
  .card{border:1px solid #e5e7eb;border-radius:12px;padding:16px;box-shadow:0 3px 10px rgba(0,0,0,.06)}
  .ok{color:#047857}.warn{color:#d97706}.err{color:#b91c1c}
  code{background:#f3f4f6;padding:2px 6px;border-radius:6px}
  ul{margin:8px 0 0;padding-left:18px}
  button{padding:10px 12px;border-radius:10px;border:1px solid #e5e7eb;background:#fff;cursor:pointer}
  form{display:grid;gap:8px;max-width:360px}
  .alert{padding:10px 12px;border-radius:10px;border:1px solid #e5e7eb;margin:0 0 12px}
  .alert.ok{background:#ecfdf5;border-color:#a7f3d0;color:#065f46}
  .alert.err{background:#fef2f2;border-color:#fecaca;color:#991b1b}
  .alert.warn{background:#fff7ed;border-color:#fed7aa;color:#9a3412}
  .badge-dry{display:inline-block;margin-left:8px;padding:2px 8px;border-radius:999px;background:#fff7ed;border:1px solid #fed7aa;color:#9a3412;font-size:12px;vertical-align:middle}
  .navmenu ul{list-style:none;margin:0;padding:0}
  .navmenu li{margin:2px 0}
  .navmenu a{display:block;padding:6px 8px;border-radius:8px;color:#1f2937;text-decoration:none}
  .navmenu a:hover{background:#f3f4f6}
  .acct{font-size:13px;color:#374151}
  .acct a{color:#1f2937;text-decoration:none}
  .acct a:hover{text-decoration:underline}
  .badge-db{display:inline-block;margin-left:8px;padding:2px 8px;border-radius:999px;font-size:12px;vertical-align:middle}
  .badge-db.ok{background:#ecfdf5;border:1px solid #a7f3d0;color:#065f46}
  .badge-db.err{background:#fef2f2;border:1px solid #fecaca;color:#991b1b}
  .badge-db{display:inline-block;margin-left:8px;padding:2px 8px;border-radius:999px;font-size:12px;vertical-align:middle}
  .badge-db.ok{background:#ecfdf5;border:1px solid #a7f3d0;color:#065f46}
  .badge-db.err{background:#fef2f2;border:1px solid #fecaca;color:#991b1b}
  /* Settings tabs */
  .tabs{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 12px}
  .tab{display:inline-block;padding:8px 10px;border:1px solid #e5e7eb;border-radius:999px;text-decoration:none;color:#1f2937;background:#fff}
  .tab.active{background:#eef2ff;border-color:#c7d2fe}
</style>
<script>
  function _copyText(t){
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(t).then(()=>alert('Curl gekopieerd'),()=>alert('Kopiëren mislukt'));
    } else {
      // Fallback
      const ta=document.createElement('textarea'); ta.value=t; document.body.appendChild(ta); ta.select(); try{document.execCommand('copy'); alert('Curl gekopieerd');}catch(e){alert('Kopiëren mislukt');} finally{document.body.removeChild(ta);}    }
  }
  function copyMoveCurl(base, userPlaceholder, src, selectId){
    var sel=document.getElementById(selectId); if(!sel){alert('Selectie niet gevonden');return}
    var dst=sel.value; var b=(base||'').replace(/\/$/,'');
    var url=b+"/admin/moveclients?mount="+encodeURIComponent(src)+"&destination="+encodeURIComponent(dst);
    var cmd='curl -i -u '+userPlaceholder+' "'+url+'"';
    _copyText(cmd);
  }
  function copyMoveAllCurls(base, userPlaceholder, selectId, mounts){
    var sel=document.getElementById(selectId); if(!sel){alert('Selectie niet gevonden');return}
    var dst=sel.value; var b=(base||'').replace(/\/$/,'');
    var lines=[]; (mounts||[]).forEach(function(src){ if(src && src!==dst){ var url=b+"/admin/moveclients?mount="+encodeURIComponent(src)+"&destination="+encodeURIComponent(dst); lines.push('curl -i -u '+userPlaceholder+' "'+url+'"'); } });
    if(!lines.length){ alert('Geen bronnen om te verplaatsen'); return; }
    _copyText(lines.join('\n'));
  }
</script>
<body>
  <header>
    <h1 id="menu">{{title}} {% if is_dry_run %}<span class="badge-dry">DRY-RUN</span>{% endif %}{% if db_ok is not none %} <span class="badge-db {{ 'ok' if db_ok else 'err' }}">DB {{ 'OK' if db_ok else 'ERR' }}</span>{% endif %}</h1>
    <div class="acct">
      {% if login_enabled %}
        {% if logged_in %}
          Ingelogd als <strong>{{login_user}}</strong>
          &middot; <a href="{{pref}}/logout">Log uit</a>
        {% else %}
          <a href="{{pref}}/login">Inloggen</a>
        {% endif %}
      {% endif %}
    </div>
  </header>

  {% if is_dry_run %}
    <div class="alert warn">DRY-RUN actief — admin/file-acties worden gesimuleerd</div>
  {% endif %}

  {% for m in messages %}
    <div class="alert {{ 'ok' if m.ok else 'err' }}">{{ m.text }}</div>
  {% endfor %}

  <p class="muted">OK – app.py draait.</p>

  <div class="layout">
    <div class="sidebar">
      <div class="card navmenu">
        <h2>Menu</h2>
        <ul>
          <li><a href="#overzicht">Overzicht</a></li>
          <li><a href="{{pref}}/services">Services</a></li>
          <li><a href="#mounts">Mountpunten</a></li>
          <li><a href="#media">Media</a></li>
          <li><a href="#afspeellijsten">Afspeellijsten</a></li>
          <li><a href="#jingels">Jingels</a></li>
          <li><a href="{{pref}}/settings">Instellen</a></li>
          <li><a href="#widgets-links">Widgets & Links</a></li>
          <li><a href="#openbaar">Openbare pagina</a></li>
          <li><a href="#dj">DJ beheer</a></li>
          <li><a href="#logs">Logbeheer</a></li>
        </ul>
      </div>
      <div class="card" id="status">
        <h2>Service status</h2>
        <ul>
          <li><strong>Icecast:</strong>
            {% if svc_ice == 'active' %}<span class="ok">active</span>
            {% elif svc_ice == 'inactive' %}<span class="warn">inactive</span>
            {% else %}<span class="err">{{svc_ice}}</span>{% endif %}
            <div class="muted">unit: <code>{{ice_unit}}</code></div>
          </li>
          <li><strong>Liquidsoap:</strong>
            {% if svc_lsq == 'active' %}<span class="ok">active</span>
            {% elif svc_lsq == 'inactive' %}<span class="warn">inactive</span>
            {% else %}<span class="err">{{svc_lsq}}</span>{% endif %}
            <div class="muted">unit: <code>{{lsq_unit}}</code></div>
          </li>
        </ul>
      </div>

      <div class="card" id="instellen">
        <h2>Admin Config</h2>
        <ul>
          <li><strong>Gebruiker:</strong> {{admin_conf.user or '(niet gezet)'}}
            {% if admin_conf.pass_set %}
              <span class="muted">(wachtwoord via {{admin_conf.pass_source}})</span>
            {% else %}
              <span class="err">[wachtwoord ontbreekt]</span>
            {% endif %}
          </li>
          <li>
            <strong>Bases volgorde:</strong>
            {% if admin_conf.bases %}
              {% for b in admin_conf.bases %}
                <div><code>{{b}}</code></div>
              {% endfor %}
            {% else %}
              <div class="muted">(geen bases geconfigureerd)</div>
            {% endif %}
            <div class="muted">voorkeur/copy: <code>{{admin_base}}</code></div>
          </li>
          <li><strong>Dry-run:</strong> {{ 'aan' if is_dry_run else 'uit' }}</li>
        </ul>
      </div>

      <div class="card">
        <h2>Systeemacties</h2>
        <form method="post" action="action">
          <input type="hidden" name="csrf" value="{{csrf}}">
          <button name="do" value="icecast:reload">Reload Icecast</button>
          <button name="do" value="icecast:restart">Restart Icecast</button>
          <button name="do" value="liquidsoap:reload">Reload Liquidsoap</button>
          <button name="do" value="liquidsoap:restart">Restart Liquidsoap</button>
          <button name="do" value="env:reload">Reload Env (.env)</button>
          <button name="do" value="admin:test">Test Admin</button>
          <button name="do" value="admin:probe-kill">Test Killsource Auth</button>
          <button name="do" value="admin:probe-move">Test Moveclients Auth</button>
        </form>
        <p class="muted">CSRF vereist; acties gelogd in systemd-journal.</p>
      </div>
    </div>

    <div class="main">

      <a id="mounts"></a>
      <div class="card" id="overzicht">
        <h2>{{icecast_name}} listeners</h2>
        {% if ice.listeners is not none %}
          {% if mounts %}
          <form method="post" action="{{pref}}/mount/moveclients-all" style="margin:6px 0">
            <input type="hidden" name="csrf" value="{{csrf}}">
            <label>Move all listeners to:
              <select name="dst" id="dst-global">
                {% for m in mounts %}
                  <option value="{{m.mount}}">{{m.mount}}</option>
                {% endfor %}
              </select>
            </label>
            <button>move all →</button>
            <button type="button" onclick="copyMoveAllCurls('{{admin_base}}','{{ (admin_user if admin_user else "USER") }}:*****','dst-global', {{ mounts_names|tojson }})">copy curls</button>
          </form>
          {% endif %}
          <div><strong>Totaal:</strong> {{ice.listeners}}</div>
          <div><strong>Mounts:</strong> {{ice.mounts_count}}</div>
          {% if mounts %}
            <ul>
              {% for m in mounts %}
                <li>
                  <code>{{m.mount}}</code> — {{m.listeners}} luisteraars
                  &nbsp;·&nbsp;
                  <a href="{{public_base}}{{m.mount}}" target="_blank">luister</a>
                  <form method="post" action="mount/soft-reload" style="display:inline">
                    <input type="hidden" name="csrf" value="{{csrf}}">
                    <input type="hidden" name="mount" value="{{m.mount}}">
                    <button>soft reload</button>
                  </form>
                  <form method="post" action="mount/disconnect" style="display:inline" onsubmit="return confirm('Disconnect {{m.mount}}?')">
                    <input type="hidden" name="csrf" value="{{csrf}}">
                    <input type="hidden" name="mount" value="{{m.mount}}">
                    <button>restart (disconnect)</button>
                  </form>
                  <form method="post" action="mount/moveclients" style="display:inline" onsubmit="return confirm('Move listeners van {{m.mount}} naar gekozen mount?')">
                    <input type="hidden" name="csrf" value="{{csrf}}">
                    <input type="hidden" name="src" value="{{m.mount}}">
                    {% set sel_id = 'dst-' + m.mount|replace('/','_')|replace('.','_')|replace(' ','_') %}
                    <select name="dst" id="{{sel_id}}">
                      {% for m2 in mounts %}
                        {% if m2.mount != m.mount %}
                          <option value="{{m2.mount}}">→ {{m2.mount}}</option>
                        {% endif %}
                      {% endfor %}
                    </select>
                    <button>moveclients</button>
                    <button type="button" onclick="copyMoveCurl('{{admin_base}}','{{ (admin_user if admin_user else "USER") }}:*****','{{m.mount}}','{{sel_id}}')">copy curl</button>
                  </form>
                  {% if m.dir %}
                    <div class="muted">map: <code>{{m.dir}}</code></div>
                    {% if m.files %}
                      <div style="margin-top:6px"><strong>Bestanden</strong> (max 20):</div>
                      <ul>
                        {% for f in m.files %}
                          <li>
                            <code>{{f}}</code>
                            <form method="post" action="{{pref}}/files/delete" style="display:inline" onsubmit="return confirm('Verwijder {{f}} uit {{m.dir}}?')">
                              <input type="hidden" name="csrf" value="{{csrf}}">
                              <input type="hidden" name="mount" value="{{m.mount}}">
                              <input type="hidden" name="name" value="{{f}}">
                              <button>verwijderen</button>
                            </form>
                          </li>
                        {% endfor %}
                      </ul>
                      {% if m.files_total and m.files_total > 20 %}
                        <div class="muted" style="margin-top:4px">
                          <a href="?dir={{m.dir}}&per=100">Bekijk alle ({{m.files_total}})</a>
                        </div>
                      {% endif %}
                    {% else %}
                      <div class="muted">Geen mp3's gevonden in {{m.dir}}</div>
                    {% endif %}
                  {% endif %}
                </li>
              {% endfor %}
            </ul>
          {% endif %}
        {% else %}
          <div class="err">Kon Icecast status niet ophalen</div>
          <div class="muted">URL: <code>{{ice_url}}</code></div>
        {% endif %}
      </div>

      <div class="card" id="media">
        <h2>Muziekbeheer</h2>
        <div class="muted">Standaard muziekmap: <code>{{mount_dir}}/{{music_dir}}</code></div>
        <form method="post" action="files/upload" enctype="multipart/form-data">
          <input type="hidden" name="csrf" value="{{csrf}}">
          <label>Mount:
            <select name="mount">
              {% for m in mounts %}
                <option value="{{m.mount}}">{{m.mount}}</option>
              {% endfor %}
            </select>
          </label>
          <label>Map (optioneel override):
            <select name="dir">
              <option value="">(automatisch op basis van mapping)</option>
              {% for d in dirs %}
                <option value="{{d}}">{{d}}</option>
              {% endfor %}
            </select>
          </label>
          <label>Bestand (.mp3): <input type="file" name="file" accept="audio/mpeg"></label>
          <button>Upload</button>
        </form>
        <p class="muted">Upload plaatst het bestand in de gekozen of gemapte directory en triggert soft reload.</p>
      </div>

      <div class="card" id="bestanden">
        <h2>Bestanden in map</h2>
        <form method="get" action="">
          <label>Map:
            <select name="dir" onchange="this.form.submit()">
              <option value="">(kies een map)</option>
              {% for d in dirs %}
                <option value="{{d}}" {% if selected_dir==d %}selected{% endif %}>{{d}}</option>
              {% endfor %}
            </select>
          </label>
          <noscript><button>Kies</button></noscript>
        </form>
        {% if selected_dir %}
          {% if selected_files %}
            <ul>
              {% for f in selected_files %}
                <li>
                  <code>{{f}}</code>
                  <form method="post" action="files/delete" style="display:inline" onsubmit="return confirm('Verwijder {{f}} uit {{selected_dir}}?')">
                    <input type="hidden" name="csrf" value="{{csrf}}">
                    <input type="hidden" name="dir" value="{{selected_dir}}">
                    <input type="hidden" name="name" value="{{f}}">
                    <button>verwijderen</button>
                  </form>
                </li>
              {% endfor %}
            </ul>
            {% if pages and pages > 1 %}
              <div class="muted" style="margin-top:6px">
                Pagina {{page}} / {{pages}} — totaal {{total_files}} bestanden
                <div style="margin-top:4px">
                  {% if page > 1 %}
                    <a href="?dir={{selected_dir}}&page={{page-1}}&per={{per}}">← Vorige</a>
                  {% else %}
                    <span class="muted">← Vorige</span>
                  {% endif %}
                  &nbsp;|
                  {% if page < pages %}
                    <a href="?dir={{selected_dir}}&page={{page+1}}&per={{per}}">Volgende →</a>
                  {% else %}
                    <span class="muted">Volgende →</span>
                  {% endif %}
                </div>
              </div>
            {% endif %}
          {% else %}
            <div class="muted">Geen mp3's in {{selected_dir}}</div>
          {% endif %}
          <form method="post" action="files/upload" enctype="multipart/form-data" style="margin-top:8px">
            <input type="hidden" name="csrf" value="{{csrf}}">
            <input type="hidden" name="mount" value="">
            <input type="hidden" name="dir" value="{{selected_dir}}">
            <label>Upload naar <code>{{selected_dir}}</code>: <input type="file" name="file" accept="audio/mpeg"></label>
            <button>Upload</button>
          </form>
        {% endif %}
        <p class="muted">Beheer bestanden direct per map (los van mounts).</p>
      </div>

      <div class="card" id="widgets-links">
        <h2>Widgets & Links</h2>
        <ul>
          <li>Luisterbasis (public): <code>{{public_base}}</code></li>
          <li>Admin basis (voorkeur): <code>{{admin_base}}</code></li>
          <li>Gebruik “copy curl” naast mounts voor admin‑acties.</li>
          <li>DB status: <a href="{{pref}}/db-status">{{pref}}/db-status</a></li>
        </ul>
        <h3 style="margin-top:10px">Liquidsoap snippet (ratio)</h3>
        <form method="get" action="#widgets-links" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <label>Ratio muziek:jingles
            <select name="lsq_ratio" onchange="this.form.submit()">
              {% for r in [3,5,10,20] %}
                <option value="{{r}}" {% if lsq_ratio==r %}selected{% endif %}>{{r}}:1</option>
              {% endfor %}
            </select>
          </label>
          <label>Aangepast: <input type="number" name="lsq_ratio" min="1" max="100" value="{{lsq_ratio}}" onchange="this.form.submit()" style="width:80px"></label>
          <noscript><button>Toepassen</button></noscript>
        </form>
        <div class="muted" style="margin:4px 0 6px">Kopieer en voeg toe aan je Liquidsoap‑config. Herlaad daarna Liquidsoap.</div>
        <pre style="white-space:pre-wrap;background:#f3f4f6;padding:8px;border-radius:8px"><code>{{lsq_snippet}}</code></pre>
        <button type="button" onclick="_copyText({{ lsq_snippet|tojson }})">Copy snippet</button>
        <form method="post" action="{{pref}}/liquidsoap/apply" style="display:inline">
          <input type="hidden" name="csrf" value="{{csrf}}">
          <input type="hidden" name="mode" value="ratio">
          <input type="hidden" name="val" value="{{lsq_ratio}}">
          <button>Apply ratio snippet</button>
        </form>
        <form method="post" action="action" style="margin-top:8px">
          <input type="hidden" name="csrf" value="{{csrf}}">
          <button name="do" value="liquidsoap:reload">Reload Liquidsoap</button>
        </form>

        <h3 style="margin-top:16px">Liquidsoap snippet (elke N minuten jingle)</h3>
        <form method="get" action="#widgets-links" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <label>Interval (minuten)
            <input type="number" name="lsq_minutes" min="1" max="180" value="{{lsq_minutes}}" onchange="this.form.submit()" style="width:90px">
          </label>
          <noscript><button>Toepassen</button></noscript>
        </form>
        <div class="muted" style="margin:4px 0 6px">Vereist Liquidsoap 2.x. Deze variant duwt elke N minuten een jingle in een request queue vóór de muziek.</div>
        <pre style="white-space:pre-wrap;background:#f3f4f6;padding:8px;border-radius:8px"><code>{{lsq_time_snippet}}</code></pre>
        <button type="button" onclick="_copyText({{ lsq_time_snippet|tojson }})">Copy snippet</button>
        <form method="post" action="{{pref}}/liquidsoap/apply" style="display:inline">
          <input type="hidden" name="csrf" value="{{csrf}}">
          <input type="hidden" name="mode" value="time">
          <input type="hidden" name="val" value="{{lsq_minutes}}">
          <button>Apply time snippet</button>
        </form>
      </div>

      <div class="card" id="openbaar">
        <h2>Openbare pagina</h2>
        <p class="muted">Open <a href="{{public_base}}" target="_blank">{{public_base}}</a> voor publieke streams/mounts.</p>
      </div>

      <div class="card" id="afspeellijsten">
        <h2>Afspeellijsten</h2>
        <div class="muted">Map: <code>{{mount_dir}}/{{playlists_dir}}</code></div>
        {% if playlists %}
          <ul>
            {% for f in playlists %}
              <li>
                <code>{{f}}</code>
                <form method="post" action="files/delete" style="display:inline" onsubmit="return confirm('Verwijder {{f}} uit {{playlists_dir}}?')">
                  <input type="hidden" name="csrf" value="{{csrf}}">
                  <input type="hidden" name="dir" value="{{playlists_dir}}">
                  <input type="hidden" name="name" value="{{f}}">
                  <button>verwijderen</button>
                </form>
              </li>
            {% endfor %}
          </ul>
        {% else %}
          <div class="muted">Geen bestanden gevonden.</div>
        {% endif %}
        <form method="post" action="files/upload" enctype="multipart/form-data" style="margin-top:8px">
          <input type="hidden" name="csrf" value="{{csrf}}">
          <input type="hidden" name="mount" value="">
          <input type="hidden" name="dir" value="{{playlists_dir}}">
          <label>Upload naar <code>{{playlists_dir}}</code>: <input type="file" name="file" accept="audio/mpeg"></label>
          <button>Upload</button>
        </form>
      </div>

      <div class="card" id="jingels">
        <h2>Jingels</h2>
        <div class="muted">Map: <code>{{mount_dir}}/{{jingles_dir}}</code></div>
        {% if jingles %}
          <ul>
            {% for f in jingles %}
              <li>
                <code>{{f}}</code>
                <form method="post" action="files/delete" style="display:inline" onsubmit="return confirm('Verwijder {{f}} uit {{jingles_dir}}?')">
                  <input type="hidden" name="csrf" value="{{csrf}}">
                  <input type="hidden" name="dir" value="{{jingles_dir}}">
                  <input type="hidden" name="name" value="{{f}}">
                  <button>verwijderen</button>
                </form>
              </li>
            {% endfor %}
          </ul>
        {% else %}
          <div class="muted">Geen bestanden gevonden.</div>
        {% endif %}
        <form method="post" action="files/upload" enctype="multipart/form-data" style="margin-top:8px">
          <input type="hidden" name="csrf" value="{{csrf}}">
          <input type="hidden" name="mount" value="">
          <input type="hidden" name="dir" value="{{jingles_dir}}">
          <label>Upload naar <code>{{jingles_dir}}</code>: <input type="file" name="file" accept="audio/mpeg"></label>
          <button>Upload</button>
        </form>
      </div>

      <div class="card" id="dj">
        <h2>DJ beheer</h2>
        <p class="muted">Nog niet beschikbaar in deze UI.</p>
      </div>

      <div class="card" id="logs">
        <h2>Logbeheer</h2>
        <p class="muted">Snelle weergave (laatste 200 regels): <a href="{{pref}}/logs" target="_blank">/logs</a></p>
        <form method="get" action="{{pref}}/logs" target="_blank" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:6px">
          <label>Unit
            <select name="unit">
              <option value="">Alle</option>
              <option value="liquidsoap">Liquidsoap</option>
              <option value="icecast">Icecast</option>
              <option value="ingest-admin">Ingest Admin</option>
            </select>
          </label>
          <label>Regels <input type="number" name="n" min="10" max="1000" value="200" style="width:90px"></label>
          <button>Open</button>
        </form>
        <p class="muted">Server: <code>journalctl -u {{ice_unit}} -u {{lsq_unit}} -u ingest-admin --since "-1h"</code></p>
      </div>

      <div class="card">
        <h2>Help & Info</h2>
        <ul>
          <li><strong>Reload Icecast</strong>: probeert admin reload; valt terug op <code>systemctl reload</code> (unit: <code>{{ice_unit}}</code>).</li>
          <li><strong>Restart Icecast</strong>: <code>systemctl restart</code> van de service.</li>
          <li><strong>Reload/Restart Liquidsoap</strong>: gebruikt respectievelijk <code>systemctl reload</code> of <code>restart</code> (unit: <code>{{lsq_unit}}</code>).</li>
          <li><strong>Status JSON</strong>: <code>{{ice_url}}</code></li>
        </ul>
        <p class="muted" style="margin-top:8px">
          Beheer en deployment: zie <code>/opt/ingest-admin/DEPLOY.md</code>. 
          Stel <code>ADMIN_TOKEN</code> en <code>SECRET_KEY</code> in via <code>/etc/default/ingest-admin</code>.
        </p>
      </div>
    </div>
  </div>

  <p class="muted" style="margin-top:12px">TIP: stel <code>ICECAST_STATUS_URL</code>, <code>ICECAST_NAME</code> (en evt. admin vars) in via <code>/etc/default/ingest-admin</code>.</p>
</body>
</html>
"""

# Settings (Instellen) template
SETTINGS_HTML = """
<!doctype html>
<meta charset=\"utf-8\">
<title>Instellen – {{title}}</title>
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
<style>
  body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Arial,sans-serif;margin:24px;color:#1f2937}
  h1{margin:0 0 12px;font-size:22px}
  h2{margin:0 0 8px;font-size:16px;color:#374151}
  .muted{color:#6b7280;font-size:12px}
  .card{border:1px solid #e5e7eb;border-radius:12px;padding:16px;box-shadow:0 3px 10px rgba(0,0,0,.06);max-width:900px}
  form{display:grid;gap:10px}
  label{display:grid;gap:6px}
  input,select{padding:10px;border:1px solid #e5e7eb;border-radius:10px}
  .tabs{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 12px}
  .tab{display:inline-block;padding:8px 10px;border:1px solid #e5e7eb;border-radius:999px;text-decoration:none;color:#1f2937;background:#fff}
  .tab.active{background:#eef2ff;border-color:#c7d2fe}
  button{padding:10px 12px;border-radius:10px;border:1px solid #e5e7eb;background:#fff;cursor:pointer;width:max-content}
  .alerts{margin:0 0 12px}
  .alert{padding:10px 12px;border-radius:10px;border:1px solid #e5e7eb;margin:0 0 8px}
  .alert.ok{background:#ecfdf5;border-color:#a7f3d0;color:#065f46}
  .alert.err{background:#fef2f2;border-color:#fecaca;color:#991b1b}
  .row{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(260px,1fr))}
  .hint{font-size:12px;color:#6b7280}
  .topbar{display:flex;justify-content:space-between;align-items:center;margin:0 0 12px}
  .back{color:#1f2937;text-decoration:none}
  .back:hover{text-decoration:underline}
  .badge{display:inline-block;margin-left:8px;padding:2px 8px;border-radius:999px;background:#f3f4f6;border:1px solid #e5e7eb;color:#374151;font-size:12px;vertical-align:middle}
</style>
<body>
  <div class=\"topbar\">
    <h1>Instellen <span class=\"badge\">{{service_name}}</span></h1>
    <a class=\"back\" href=\"{{pref}}/\">← Terug</a>
  </div>

  <div class=\"alerts\">
    {% for m in messages %}
      <div class=\"alert {{ 'ok' if m.ok else 'err' }}\">{{ m.text }}</div>
    {% endfor %}
  </div>

  <nav class=\"tabs\">
    {% for key,label in tabs %}
      <a class=\"tab {% if active==key %}active{% endif %}\" href=\"{{pref}}/settings?tab={{key}}\">{{label}}</a>
    {% endfor %}
  </nav>

  <div class=\"card\">
    <form method=\"post\" action=\"{{pref}}/settings?tab={{active}}\">
      <input type=\"hidden\" name=\"csrf\" value=\"{{csrf}}\">
      {% if active=='algemeen' %}
        <div class=\"row\">
          <label>Service naam*<input name=\"service_name\" value=\"{{settings.name or ''}}\" placeholder=\"Naam\" required></label>
          <label>Service Type*<select name=\"svc_type\"><option {% if settings.svc_type=='Icecast 2 KH' %}selected{% endif %}>Icecast 2 KH</option></select></label>
          <label>Eigenaar*<input name=\"owner\" value=\"{{settings.owner or ''}}\" placeholder=\"naam of e-mail\"></label>
          <label>Unieke ID*<input name=\"uid\" value=\"{{settings.uid or ''}}\" placeholder=\"8174\"></label>
          <label>Poortnummer*<input name=\"port\" value=\"{{settings.port or ''}}\" placeholder=\"8000\"></label>
          <label>Wachtwoord*<input name=\"admin_pass\" value=\"{{settings.admin_pass or ''}}\" placeholder=\"Sterk wachtwoord\"></label>
          <label>Stream Bron wachtwoord<input name=\"source_pass\" value=\"{{settings.source_pass or ''}}\"></label>
          <label>Relay Bron wachtwoord<input name=\"relay_pass\" value=\"{{settings.relay_pass or ''}}\"></label>
          <label class=\"muted\"><input type=\"checkbox\" name=\"apply_icecast\" value=\"1\"> Toepassen: Icecast reload na opslaan</label>
        </div>
      {% elif active=='limieten' %}
        <div class=\"row\">
          <label>Mount punten*<input name=\"mounts\" value=\"{{settings.limits.mounts}}\" placeholder=\"1\"></label>
          <label># van AutoDJ*<input name=\"autodj\" value=\"{{settings.limits.autodj}}\" placeholder=\"1\"></label>
          <label>Bitrate* (kbps)<input name=\"bitrate\" value=\"{{settings.limits.bitrate}}\" placeholder=\"320\"></label>
          <label>Max gebruikers*<input name=\"listeners\" value=\"{{settings.limits.listeners}}\" placeholder=\"100\"></label>
          <label>Bandbreedte (MB)*<input name=\"bandwidth\" value=\"{{settings.limits.bandwidth}}\" placeholder=\"0\"></label>
          <label>Opslaglimiet (MB)*<input name=\"storage\" value=\"{{settings.limits.storage}}\" placeholder=\"11000\"></label>
        </div>
      {% elif active=='functies' %}
        <div class=\"row\">
          <label><input type=\"checkbox\" name=\"hist\" {% if settings.features.hist %}checked{% endif %}> Historische rapportage</label>
          <label><input type=\"checkbox\" name=\"proxy\" {% if settings.features.proxy %}checked{% endif %}> HTTP/HTTPS Proxy-ondersteuning*</label>
          <label><input type=\"checkbox\" name=\"geoip\" {% if settings.features.geoip %}checked{% endif %}> GeoIP-landvergrendeling</label>
          <label><input type=\"checkbox\" name=\"auth\" {% if settings.features.auth %}checked{% endif %}> Streamauthenticatie</label>
          <label><input type=\"checkbox\" name=\"multi\" {% if settings.features.multi %}checked{% endif %}> Laat meerdere gebruikers toe</label>
          <label><input type=\"checkbox\" name=\"public\" {% if settings.features.public %}checked{% endif %}> Openbare pagina*</label>
          <label><input type=\"checkbox\" name=\"social\" {% if settings.features.social %}checked{% endif %}> Posten op sociale media</label>
          <label><input type=\"checkbox\" name=\"record\" {% if settings.features.record %}checked{% endif %}> Live-opname toestaan</label>
        </div>
      {% elif active=='icecast' %}
        <div class=\"row\">
          <label>Publieke server*<select name=\"public_server\"><option {% if settings.icecast.public_server.startswith('Default') %}selected{% endif %}>Default (bron bepaalt)</option></select></label>
          <label>Introbestand<input name=\"intro\" value=\"{{settings.icecast.intro}}\" placeholder=\"/pad/naar/intro.mp3\"><span class=\"hint\">Zelfde bitrate/channels als stream</span></label>
          <label>Publiceer naar YP<input name=\"yp\" value=\"{{settings.icecast.yp}}\" placeholder=\"http://dir.xiph.org/cgi-bin/yp-cgi\"></label>
          <label>Redirect Icecast-pagina<input name=\"redirect\" value=\"{{settings.icecast.redirect}}\" placeholder=\"/default.mp3\"></label>
        </div>
      {% elif active=='autodj' %}
        <div class=\"row\">
          <label>AutoDJ-type*<select name=\"autodj_type\"><option {% if settings.autodj.autodj_type=='liquidsoap' %}selected{% endif %}>liquidsoap</option></select></label>
          <label>Fade-in (s)*<input name=\"fade_in\" value=\"{{settings.autodj.fade_in}}\" placeholder=\"0\"></label>
          <label>Fade-out (s)*<input name=\"fade_out\" value=\"{{settings.autodj.fade_out}}\" placeholder=\"0\"></label>
          <label>Min drempel voor crossfade<input name=\"fade_min\" value=\"{{settings.autodj.fade_min}}\" placeholder=\"0\"></label>
          <label><input type=\"checkbox\" name=\"smart_fade\" {% if settings.autodj.smart_fade %}checked{% endif %}> Slimme crossfade</label>
          <label><input type=\"checkbox\" name=\"replay_gain\" {% if settings.autodj.replay_gain %}checked{% endif %}> Replay Gain aanpassen</label>
        </div>
      {% elif active=='relays' %}
        <div class=\"row\">
          <label>Type relais<select name=\"relay_type\">
            <option {% if settings.relays.relay_type=='Uitgeschakeld' %}selected{% endif %}>Uitgeschakeld</option>
            <option {% if settings.relays.relay_type=='Master-Slave-relay' %}selected{% endif %}>Master-Slave-relay</option>
            <option {% if settings.relays.relay_type=='Single Broadcast-relay' %}selected{% endif %}>Single Broadcast-relay</option>
          </select></label>
        </div>
      {% endif %}
      <div>
        <button>Opslaan</button>
        <span class=\"muted\" style=\"margin-left:8px\">Demo: instellingen worden nog niet persistent opgeslagen</span>
      </div>
    </form>
  </div>
</body>
"""

app = Flask(__name__)
# Respect reverse proxy headers, including X-Forwarded-Prefix for subpaths like /admin
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Debug logging (enable with ADMIN_DEBUG=1)
ADMIN_DEBUG = (os.environ.get('ADMIN_DEBUG','') or '').strip().lower() in ('1','true','yes','on')
logging.basicConfig(level=logging.INFO)
log = logging.getLogger('ingest-admin')

def dbg(msg: str):
  if ADMIN_DEBUG:
    try:
      log.info('[ADMIN] %s', msg)
    except Exception:
      pass
app.secret_key = SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('MAX_UPLOAD_MB', '100')) * 1024 * 1024
# Harden session cookies
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
if SECRET_KEY in ("", "please-change-this"):
  # Niet fatal, maar laat een waarschuwing zien in de UI
  try:
    flash("SECRET_KEY niet gezet — stel een sterke waarde in via /etc/default/ingest-admin", "err")
  except Exception:
    pass

def _is_dry_run() -> bool:
  v = (ADMIN_DRY_RUN or "").strip().lower()
  return v in ("1","true","yes","on")

def _prefix() -> str:
  # Respecteer reverse proxy subpad
  p = request.headers.get("X-Forwarded-Prefix") or request.headers.get("X-Script-Name") or ""
  p = (p or "").rstrip("/")
  dbg(f"prefix={p!r} script_root={request.script_root!r} path={request.path!r} endpoint={request.endpoint}")
  return p

def _db_is_ok() -> bool:
  try:
    db = get_session()
    try:
      db.execute(text("SELECT 1"))
      return True
    finally:
      db.close()
  except Exception:
    return False

def _db_is_ok() -> bool:
  try:
    db = get_session()
    try:
      db.execute(text("SELECT 1"))
      return True
    finally:
      db.close()
  except Exception:
    return False

def systemd_is_active(unit: str) -> str:
  try:
    out = subprocess.check_output(["systemctl","is-active",unit], stderr=subprocess.STDOUT, text=True).strip()
    return out or "unknown"
  except subprocess.CalledProcessError as e:
    return (e.output or "error").strip() or "error"

def fetch_icecast(url: str):
  try:
    with urllib.request.urlopen(url, timeout=2.5) as r:
      data = json.loads(r.read().decode("utf-8","ignore"))
    mounts = []
    src = data.get("icestats",{}).get("source",[])
    if isinstance(src, dict):
      src = [src]
    for s in src:
      mount = s.get("listenurl") or s.get("server_name") or s.get("title") or s.get("mount")
      if mount and mount.startswith("http"):
        from urllib.parse import urlparse
        try:
          p = urlparse(mount); mount = p.path or mount
        except Exception:
          pass
      mounts.append({"mount": mount or "?", "listeners": int(s.get("listeners",0))})
    total = sum(m["listeners"] for m in mounts)
    return {"listeners": total, "mounts": mounts, "mounts_count": len(mounts)}
  except Exception:
    return {"listeners": None, "mounts": None, "mounts_count": 0}

@app.route("/")
def index():
  ice_unit = os.environ.get("ICECAST_UNIT","icecast-kh")
  lsq_unit = os.environ.get("LIQUIDSOAP_UNIT","liquidsoap")
  svc_ice = systemd_is_active(ice_unit)
  svc_lsq = systemd_is_active(lsq_unit)
  ice      = fetch_icecast(ICECAST_STATUS_URL)
  # Flash messages pakken en mappen naar {text, ok}
  raw = get_flashed_messages(with_categories=True)
  msgs = []
  for cat, text in raw:
    ok = (cat == "ok")
    msgs.append({"text": text, "ok": ok})
  # Verrijk mounts met mapping + bestandlijst
  view_mounts = []
  if isinstance(ice.get('mounts'), list):
    for it in ice['mounts']:
      mnt = it.get('mount')
      d = derive_dir_from_mount(mnt or '') if mnt else None
      if d:
        all_files = list_mp3(d)
        files = all_files[:20]
        files_total = len(all_files)
      else:
        files, files_total = [], 0
      view_mounts.append({
        'mount': mnt,
        'listeners': it.get('listeners', 0),
        'dir': d,
        'files': files,
        'files_total': files_total,
      })
  # Directory-overzicht (los van mounts)
  sel_dir = (request.args.get('dir','') or '').strip()
  if sel_dir and not os.path.isdir(os.path.join(MOUNT_DIR, sel_dir)):
    sel_dir = ''
  sel_files = list_mp3(sel_dir) if sel_dir else []
  # Paginering voor directory-weergave
  try:
    page = int(request.args.get('page','1') or '1')
  except ValueError:
    page = 1
  try:
    per = int(request.args.get('per','100') or '100')
  except ValueError:
    per = 100
  if page < 1: page = 1
  if per < 1: per = 1
  if per > 500: per = 500
  sel_total = len(sel_files)
  pages = (sel_total + per - 1) // per if per else 1
  start = (page - 1) * per
  end = start + per
  sel_files = sel_files[start:end]

  # Liquidsoap snippet helpers
  try:
    lsq_ratio = int(request.args.get('lsq_ratio','10') or '10')
  except ValueError:
    lsq_ratio = 10
  if lsq_ratio < 1: lsq_ratio = 1
  if lsq_ratio > 100: lsq_ratio = 100
  try:
    lsq_minutes = int(request.args.get('lsq_minutes','10') or '10')
  except ValueError:
    lsq_minutes = 10
  if lsq_minutes < 1: lsq_minutes = 1
  if lsq_minutes > 180: lsq_minutes = 180
  music_path   = os.path.join(MOUNT_DIR, MUSIC_DIR)
  jingles_path = os.path.join(MOUNT_DIR, JINGLES_DIR)
  lsq_snippet = (
    f'jingles = playlist("{jingles_path}", reload_mode="watch", mode="random")\n'
    f'music   = playlist("{music_path}", reload_mode="watch")\n'
    f'radio   = rotate(weights=[{lsq_ratio},1],[music,jingles])\n'
    '# TODO: vervang met je Icecast credentials en mount:\n'
    '# output.icecast(%mp3, host="127.0.0.1", port=8001, password="<password>", mount="/stream.mp3", radio)\n'
  )
  lsq_time_snippet = (
    f'# Vereist Liquidsoap 2.x\n'
    f'music   = playlist("{music_path}", reload_mode="watch")\n'
    f'jingles = playlist("{jingles_path}", reload_mode="watch", mode="random")\n'
    f'rq = request.queue(id="jingle_q")\n'
    f'clock.every(period={lsq_minutes}m, fun () -> rq.push(pick(jingles)))\n'
    f'radio = fallback(track_sensitive=false, [rq, music])\n'
    '# TODO: vervang met je Icecast credentials en mount:\n'
    '# output.icecast(%mp3, host="127.0.0.1", port=8001, password="<password>", mount="/stream.mp3", radio)\n'
  )

  return render_template_string(
    HTML,
    title=APP_TITLE,
    svc_ice=svc_ice, svc_lsq=svc_lsq,
    ice=ice, ice_url=ICECAST_STATUS_URL, icecast_name=ICECAST_NAME,
    ice_unit=ice_unit, lsq_unit=lsq_unit,
    csrf=ADMIN_TOKEN,
    messages=msgs,
    public_base=ICE_URL_PUBLIC,
    admin_base=(ICE_ADMIN_BASE or os.environ.get('ICE_URL_PUBLIC','') or os.environ.get('ICE_URL_PRIVATE','')),
    admin_user=os.environ.get('ICE_ADMIN_USER',''),
    mount_dir=MOUNT_DIR,
    music_dir=MUSIC_DIR,
    mounts=view_mounts,
    dirs=list_dirs(),
    playlists_dir=PLAYLISTS_DIR,
    jingles_dir=JINGLES_DIR,
    playlists=list_mp3(PLAYLISTS_DIR),
    jingles=list_mp3(JINGLES_DIR),
    lsq_ratio=lsq_ratio,
    lsq_snippet=lsq_snippet,
    lsq_minutes=lsq_minutes,
    lsq_time_snippet=lsq_time_snippet,
    selected_dir=sel_dir,
    selected_files=sel_files,
    page=page,
    pages=pages,
    per=per,
    total_files=sel_total,
    is_dry_run=_is_dry_run(),
    pref=_prefix(),
    login_enabled=_login_enabled(),
    logged_in=bool(session.get('logged_in')),
    login_user=session.get('user',''),
    db_ok=_db_is_ok(),
    mounts_names=[m.get('mount') for m in view_mounts if m.get('mount')],
    admin_conf={
      'bases': [b for b in [(ICE_ADMIN_BASE or ''), os.environ.get('ICE_URL_PUBLIC',''), os.environ.get('ICE_URL_PRIVATE','')] if (b or '')],
      'user': os.environ.get('ICE_ADMIN_USER',''),
      'pass_set': bool(os.environ.get('ICE_ADMIN_PASS') or os.environ.get('ICE_ADMIN_PASS_FILE')),
      'pass_source': ('env' if os.environ.get('ICE_ADMIN_PASS') else ('file' if os.environ.get('ICE_ADMIN_PASS_FILE') else '')),
      'pass_file': (os.path.basename(os.environ.get('ICE_ADMIN_PASS_FILE','').strip()) if os.environ.get('ICE_ADMIN_PASS_FILE') else '')
    },
  )

@app.route('/settings', methods=['GET','POST'])
def settings():
  tabs = [
    ('algemeen','Algemeen'),
    ('limieten','Limieten'),
    ('functies','Functies'),
    ('icecast','Icecast 2 KH'),
    ('autodj','AutoDJ'),
    ('relays','Relais'),
  ]
  active = (request.args.get('tab','') or 'algemeen').lower()
  if active not in dict(tabs):
    active = 'algemeen'
  # Ensure tables exist (idempotent)
  try:
    Base.metadata.create_all(bind=engine)
  except Exception:
    pass

  # Determine selected service id from session or default 1
  try:
    svc_id = int(session.get('service_id', 1))
  except Exception:
    svc_id = 1
  # Load or init the service row
  settings_data = {}
  try:
    db = get_session()
    svc = db.get(Service, svc_id)
    if not svc:
      # If DB empty, create default service
      existing = db.query(Service).count()
      if existing == 0:
        svc = Service(id=1, name='Default')
        svc_id = 1
      else:
        # fallback to first service
        svc = db.query(Service).first()
        svc_id = svc.id
      session['service_id'] = svc_id
      svc.limits = ServiceLimits()
      svc.features = ServiceFeatures()
      svc.icecast = ServiceIcecast()
      svc.autodj = ServiceAutoDJ()
      svc.relay = ServiceRelay()
      db.add(svc)
      db.commit()
      db.refresh(svc)
    if request.method == 'POST':
      _require_csrf()
      # Map form fields to models per tab
      if active == 'algemeen':
        svc.name = request.form.get('service_name', svc.name)
        svc.svc_type = request.form.get('svc_type', svc.svc_type)
        svc.owner = request.form.get('owner', svc.owner)
        svc.uid = request.form.get('uid', svc.uid)
        try:
          svc.port = int(request.form.get('port', svc.port) or svc.port)
        except ValueError:
          pass
        svc.admin_pass = request.form.get('admin_pass', svc.admin_pass)
        svc.source_pass = request.form.get('source_pass', svc.source_pass)
        svc.relay_pass = request.form.get('relay_pass', svc.relay_pass)
        # Optional: apply Icecast settings by reloading admin endpoint
        if request.form.get('apply_icecast') == '1':
          msg, code = run_wrapper('icecast:reload')
          if code == 200:
            flash('✅ Icecast reload uitgevoerd', 'ok')
          else:
            flash(f'❌ Icecast reload mislukt: {msg}', 'err')
      elif active == 'limieten':
        for key in ('mounts','autodj','bitrate','listeners','bandwidth','storage'):
          try:
            setattr(svc.limits, key, int(request.form.get(key, getattr(svc.limits, key))))
          except ValueError:
            pass
      elif active == 'functies':
        for key in ('hist','proxy','geoip','auth','multi','public','social','record'):
          setattr(svc.features, key, bool(request.form.get(key)))
      elif active == 'icecast':
        svc.icecast.public_server = request.form.get('public_server', svc.icecast.public_server)
        svc.icecast.intro_path = request.form.get('intro', svc.icecast.intro_path)
        svc.icecast.yp_url = request.form.get('yp', svc.icecast.yp_url)
        svc.icecast.redirect_path = request.form.get('redirect', svc.icecast.redirect_path)
      elif active == 'autodj':
        svc.autodj.autodj_type = request.form.get('autodj_type', svc.autodj.autodj_type)
        for key in ('fade_in','fade_out','fade_min'):
          try:
            setattr(svc.autodj, key, int(request.form.get(key, getattr(svc.autodj, key))))
          except ValueError:
            pass
        svc.autodj.smart_fade = bool(request.form.get('smart_fade'))
        svc.autodj.replay_gain = bool(request.form.get('replay_gain'))
      elif active == 'relays':
        svc.relay.relay_type = request.form.get('relay_type', svc.relay.relay_type)
      db.commit()
      flash('✅ Instellingen opgeslagen', 'ok')
      pref = _prefix()
      db.close()
      return redirect(f"{pref}/settings?tab={active}")
    # Build settings dict for template values
    settings_data = {
      'name': svc.name,
      'svc_type': svc.svc_type,
      'owner': svc.owner,
      'uid': svc.uid,
      'port': svc.port,
      'admin_pass': svc.admin_pass,
      'source_pass': svc.source_pass,
      'relay_pass': svc.relay_pass,
      'limits': {
        'mounts': svc.limits.mounts,
        'autodj': svc.limits.autodj,
        'bitrate': svc.limits.bitrate,
        'listeners': svc.limits.listeners,
        'bandwidth': svc.limits.bandwidth,
        'storage': svc.limits.storage,
      },
      'features': {
        'hist': svc.features.hist,
        'proxy': svc.features.proxy,
        'geoip': svc.features.geoip,
        'auth': svc.features.auth,
        'multi': svc.features.multi,
        'public': svc.features.public,
        'social': svc.features.social,
        'record': svc.features.record,
      },
      'icecast': {
        'public_server': svc.icecast.public_server,
        'intro': svc.icecast.intro_path,
        'yp': svc.icecast.yp_url,
        'redirect': svc.icecast.redirect_path,
      },
      'autodj': {
        'autodj_type': svc.autodj.autodj_type,
        'fade_in': svc.autodj.fade_in,
        'fade_out': svc.autodj.fade_out,
        'fade_min': svc.autodj.fade_min,
        'smart_fade': svc.autodj.smart_fade,
        'replay_gain': svc.autodj.replay_gain,
      },
      'relays': {
        'relay_type': svc.relay.relay_type,
      }
    }
    db.close()
  except SQLAlchemyError as e:
    flash(f"❌ DB fout: {e}", 'err')
  raw = get_flashed_messages(with_categories=True)
  msgs = []
  for cat, text in raw:
    msgs.append({'text': text, 'ok': (cat=='ok')})
  return render_template_string(
    SETTINGS_HTML,
    title=APP_TITLE,
    service_name=(ICECAST_NAME + (f" – {settings_data.get('name','')}" if settings_data.get('name') else "")),
    tabs=tabs,
    active=active,
    csrf=ADMIN_TOKEN,
    pref=_prefix(),
    messages=msgs,
    settings=settings_data,
  )

SERVICES_HTML = """
<!doctype html><meta charset="utf-8"><title>Services – {{title}}</title>
<style>body{font-family:system-ui;margin:24px;color:#1f2937} .card{border:1px solid #e5e7eb;border-radius:12px;padding:16px;max-width:900px}
table{border-collapse:collapse;width:100%;margin-top:8px} th,td{padding:8px;border-bottom:1px solid #e5e7eb;text-align:left}
input,button{padding:10px;border:1px solid #e5e7eb;border-radius:10px}
.muted{color:#6b7280;font-size:12px}
</style>
<div class="card">
  <h2>Services</h2>
  <form method="post" action="{{pref}}/services/create" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
    <input type="hidden" name="csrf" value="{{csrf}}">
    <label>Naam <input name="name" placeholder="Naam" required></label>
    <label>Type <input name="svc_type" value="Icecast 2 KH"></label>
    <button>Aanmaken</button>
  </form>
  <table>
    <thead><tr><th>ID</th><th>Naam</th><th>Type</th><th>Acties</th></tr></thead>
    <tbody>
      {% for s in services %}
        <tr>
          <td>{{s.id}}</td>
          <td>{{s.name}}</td>
          <td>{{s.svc_type}}</td>
          <td>
            <a href="{{pref}}/services/select?id={{s.id}}">selecteer</a>
            {% if s.id != current_id %}
              · <a href="{{pref}}/services/delete?id={{s.id}}" onclick="return confirm('Verwijder service {{s.name}}?')">verwijderen</a>
            {% else %}
              <span class="muted">(actief)</span>
            {% endif %}
          </td>
        </tr>
      {% endfor %}
    </tbody>
  </table>
  <p class="muted" style="margin-top:8px">Actieve service wordt gebruikt in Instellen.</p>
  <p><a href="{{pref}}/settings">→ Naar Instellen</a></p>
</div>
"""

@app.get('/services')
def services_list():
  db = get_session()
  try:
    rows = db.query(Service).order_by(Service.id.asc()).all()
  finally:
    db.close()
  cur = session.get('service_id', 1)
  return render_template_string(
    SERVICES_HTML,
    title=APP_TITLE,
    services=[{'id': r.id, 'name': r.name or f'Service {r.id}', 'svc_type': r.svc_type} for r in rows],
    current_id=cur,
    csrf=ADMIN_TOKEN,
    pref=_prefix(),
  )

@app.post('/services/create')
def services_create():
  _require_csrf()
  name = (request.form.get('name','') or '').strip()
  stype = (request.form.get('svc_type','') or 'Icecast 2 KH').strip()
  if not name:
    flash('❌ Naam is verplicht', 'err'); return redirect(_prefix() + '/services')
  db = get_session()
  try:
    svc = Service(name=name, svc_type=stype)
    svc.limits = ServiceLimits(); svc.features = ServiceFeatures(); svc.icecast = ServiceIcecast(); svc.autodj = ServiceAutoDJ(); svc.relay = ServiceRelay()
    db.add(svc); db.commit(); db.refresh(svc)
    flash(f'✅ Service aangemaakt: {name}', 'ok')
  except Exception as e:
    flash(f'❌ Aanmaken mislukt: {e}', 'err')
  finally:
    db.close()
  return redirect(_prefix() + '/services')

@app.get('/services/select')
def services_select():
  try:
    sid = int(request.args.get('id','') or '0')
  except Exception:
    sid = 0
  if not sid:
    flash('❌ Ongeldige service id', 'err'); return redirect(_prefix() + '/services')
  # Verify exists
  db = get_session()
  ok = False
  try:
    ok = bool(db.get(Service, sid))
  finally:
    db.close()
  if ok:
    session['service_id'] = sid
    flash(f'✅ Service geselecteerd: {sid}', 'ok')
    return redirect(_prefix() + '/settings')
  flash('❌ Service niet gevonden', 'err')
  return redirect(_prefix() + '/services')

@app.get('/services/delete')
def services_delete():
  try:
    sid = int(request.args.get('id','') or '0')
  except Exception:
    sid = 0
  cur = session.get('service_id', 1)
  if sid == cur:
    flash('❌ Kan actieve service niet verwijderen', 'err'); return redirect(_prefix() + '/services')
  db = get_session()
  try:
    svc = db.get(Service, sid)
    if not svc:
      flash('❌ Service niet gevonden', 'err')
    else:
      db.delete(svc); db.commit(); flash('✅ Service verwijderd', 'ok')
  except Exception as e:
    flash(f'❌ Verwijderen mislukt: {e}', 'err')
  finally:
    db.close()
  return redirect(_prefix() + '/services')

@app.get('/db-status')
def db_status():
  info = { 'ok': False, 'error': '', 'engine': '', 'db': '', 'driver': '', 'counts': {} }
  try:
    info['engine'] = engine.url.get_backend_name()
    info['driver'] = engine.url.get_driver_name()
    info['db'] = engine.url.database or ''
    db = get_session()
    try:
      info['counts'] = {
        'services': db.query(Service).count(),
        'service_limits': db.query(ServiceLimits).count(),
        'service_features': db.query(ServiceFeatures).count(),
        'service_icecast': db.query(ServiceIcecast).count(),
        'service_autodj': db.query(ServiceAutoDJ).count(),
        'service_relay': db.query(ServiceRelay).count(),
      }
      info['ok'] = True
    finally:
      db.close()
  except Exception as e:
    info['error'] = str(e)
  pref = _prefix() or ''
  html = f"""<!doctype html><meta charset='utf-8'><title>DB Status</title>
  <style>body{{font-family:system-ui;margin:24px;color:#1f2937}} .card{{border:1px solid #e5e7eb;border-radius:12px;padding:16px;max-width:720px}}
  code{{background:#f3f4f6;padding:2px 6px;border-radius:6px}} .ok{{color:#047857}} .err{{color:#b91c1c}}
  a{{color:#1f2937}}</style>
  <div class='card'>
    <h2>DB Status</h2>
    <div>Engine: <code>{info['engine']}</code> · Driver: <code>{info['driver']}</code> · DB: <code>{info['db']}</code></div>
    <div style='margin-top:8px'>Status: {('<span class=ok>OK</span>' if info['ok'] else '<span class=err>ERROR</span>')}</div>
    {('<ul>'+''.join(f"<li>{k}: <code>{v}</code></li>" for k,v in info['counts'].items())+'</ul>') if info['ok'] else ("<div class='err'>"+info['error']+"</div>")}
    <div style='margin-top:12px'><a href='{pref or '/'}'>← Terug</a></div>
  </div>"""
  return html

@app.post('/liquidsoap/apply')
def liquidsoap_apply():
  _require_csrf()
  mode = (request.form.get('mode','') or '').strip()
  val = (request.form.get('val','') or '').strip()
  # Recompute paths to ensure consistency
  music_path   = os.path.join(MOUNT_DIR, MUSIC_DIR)
  jingles_path = os.path.join(MOUNT_DIR, JINGLES_DIR)
  snippet = ''
  if mode == 'ratio':
    try:
      r = int(val or '10')
    except ValueError:
      r = 10
    if r < 1: r = 1
    if r > 100: r = 100
    snippet = (
      f'jingles = playlist("{jingles_path}", reload_mode="watch", mode="random")\n'
      f'music   = playlist("{music_path}", reload_mode="watch")\n'
      f'radio   = rotate(weights=[{r},1],[music,jingles])\n'
    )
  elif mode == 'time':
    try:
      m = int(val or '10')
    except ValueError:
      m = 10
    if m < 1: m = 1
    if m > 180: m = 180
    snippet = (
      f'# Vereist Liquidsoap 2.x\n'
      f'music   = playlist("{music_path}", reload_mode="watch")\n'
      f'jingles = playlist("{jingles_path}", reload_mode="watch", mode="random")\n'
      f'rq = request.queue(id="jingle_q")\n'
      f'clock.every(period={m}m, fun () -> rq.push(pick(jingles)))\n'
      f'radio = fallback(track_sensitive=false, [rq, music])\n'
    )
  else:
    flash('❌ Onbekende modus', 'err')
    return redirect(_prefix() + '/' if _prefix() else '/')
  target = os.environ.get('LIQ_SNIPPET_PATH','/etc/liquidsoap/snippets/admin.liq')
  try:
    if _is_dry_run():
      flash(f"✅ [DRY-RUN] Zou snippet schrijven naar {target} en Liquidsoap herladen", 'ok')
    else:
      os.makedirs(os.path.dirname(target), exist_ok=True)
      with open(target, 'w', encoding='utf-8') as fh:
        fh.write(snippet)
      # Reload Liquidsoap via wrapper
      msg, code = run_wrapper('liquidsoap:reload')
      if code == 200:
        flash('✅ Snippet toegepast en Liquidsoap herladen', 'ok')
      else:
        flash(f'❌ Reload Liquidsoap mislukt: {msg}', 'err')
  except Exception as e:
    flash(f'❌ Snippet toepassen mislukt: {e}', 'err')
  return redirect(_prefix() + '/' if _prefix() else '/')

@app.get('/logs')
def logs():
  ice_unit = os.environ.get("ICECAST_UNIT","icecast-kh")
  lsq_unit = os.environ.get("LIQUIDSOAP_UNIT","liquidsoap")
  try:
    # Clamp lines for safety
    lines = request.args.get('n','200')
    try:
      n = max(10, min(1000, int(lines)))
    except Exception:
      n = 200
    unit = (request.args.get('unit','') or '').strip().lower()
    if unit in ('icecast','ice','kh'):
      cmd = ["journalctl","-u", ice_unit, "--no-pager","-n", str(n)]
    elif unit in ('liquidsoap','lsq','liq'):
      cmd = ["journalctl","-u", lsq_unit, "--no-pager","-n", str(n)]
    elif unit in ('ingest-admin','admin','ui'):
      cmd = ["journalctl","-u", "ingest-admin", "--no-pager","-n", str(n)]
    else:
      cmd = ["journalctl","-u", "ingest-admin","-u", ice_unit, "-u", lsq_unit, "--no-pager","-n", str(n)]
    out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True, timeout=6)
    txt = out
  except Exception as e:
    txt = f"Unable to read logs: {e}\nTry on server: journalctl -u {ice_unit} -u {lsq_unit} -u ingest-admin --since '-1h'\n"
  return Response(txt, mimetype='text/plain')

@app.route("/health")
def health():
  return "OK", 200

def run_wrapper(arg: str) -> tuple[str,int]:
  if _is_dry_run():
    return (f"[DRY-RUN] would call: sudo /usr/local/bin/ingestctl.sh {arg}", 200)
  try:
    out = subprocess.check_output(["sudo","/usr/local/bin/ingestctl.sh", arg],
                                  stderr=subprocess.STDOUT, text=True, timeout=15)
    return (out.strip() or "OK", 200)
  except subprocess.CalledProcessError as e:
    return (f"ERR({e.returncode}): {e.output}", 500)
  except Exception as e:
    return (f"ERR: {e}", 500)

@app.route("/action", methods=["POST"])
@app.route("/ingest-admin/action", methods=["POST"])
def action():
  if not ADMIN_TOKEN:
    abort(503, "ADMIN_TOKEN not configured")
  if request.form.get("csrf") != ADMIN_TOKEN:
    abort(403, "Bad CSRF")
  do = request.form.get("do","")
  if do not in {"icecast:reload","icecast:restart","liquidsoap:reload","liquidsoap:restart","env:reload","admin:test","admin:probe-kill","admin:probe-move"}:
    abort(400, "Unsupported action")
  if do == 'env:reload':
    # herlaad env overlays en secret file
    _load_env_defaults()
    flash("✅ Env herladen (defaults + .env + secretfile)", "ok")
    pref = _prefix()
    return redirect(f"{pref}/" if pref else "/")
  if do == 'admin:test':
    res = admin_test_bases()
    if not res:
      flash('❌ Geen admin bases geconfigureerd (zet ICE_ADMIN_BASE of ICE_URL_PUBLIC/PRIVATE)', 'err')
    else:
      user = os.environ.get('ICE_ADMIN_USER','') or 'USER'
      for it in res:
        base = it['base']
        status = it['status']
        if it['ok']:
          flash(f"✅ Admin OK op {base} (HTTP {status})", 'ok')
        else:
          if status in (401,403):
            flash(f"❌ Admin unauthorized op {base} (HTTP {status}, user: {user})", 'err')
          else:
            flash(f"❌ Admin test faalde op {base} ({it['note'] or status})", 'err')
    pref = _prefix()
    return redirect(f"{pref}/" if pref else "/")
  if do == 'admin:probe-kill':
    # Non-destructive: call /admin/killsource without mount to validate auth (expect 400 on valid auth)
    bases = []
    for b in (ICE_ADMIN_BASE or '', os.environ.get('ICE_URL_PUBLIC',''), os.environ.get('ICE_URL_PRIVATE','')):
      b = (b or '').strip()
      if b and b not in bases:
        bases.append(b)
    if not bases:
      flash('❌ Geen admin bases geconfigureerd', 'err')
    else:
      user = os.environ.get('ICE_ADMIN_USER','') or 'USER'
      for base in bases:
        status, used = _admin_call('/admin/killsource')
        # In dry-run we return 200; mark as simulated
        if _is_dry_run():
          flash(f"✅ [DRY-RUN] Probe OK op {used or base} (simulatie)", 'ok')
        else:
          if status in (400, 405):
            flash(f"✅ Auth OK (verwachte {status}) op {used or base}", 'ok')
          elif status in (401,403):
            flash(f"❌ Unauthorized op {used or base} (HTTP {status}, user: {user})", 'err')
          elif status == 0:
            flash(f"❌ Geen respons op {base}", 'err')
          else:
            flash(f"❌ Onverwachte respons {status} op {used or base}", 'err')
    pref = _prefix()
    return redirect(f"{pref}/" if pref else "/")
  if do == 'admin:probe-move':
    # Non-destructive: call /admin/moveclients without params to validate auth (expect 400/405)
    bases = []
    for b in (ICE_ADMIN_BASE or '', os.environ.get('ICE_URL_PUBLIC',''), os.environ.get('ICE_URL_PRIVATE','')):
      b = (b or '').strip()
      if b and b not in bases:
        bases.append(b)
    if not bases:
      flash('❌ Geen admin bases geconfigureerd', 'err')
    else:
      user = os.environ.get('ICE_ADMIN_USER','') or 'USER'
      for base in bases:
        status, used = _admin_call('/admin/moveclients')
        if _is_dry_run():
          flash(f"✅ [DRY-RUN] Probe OK op {used or base} (simulatie)", 'ok')
        else:
          if status in (400, 405):
            flash(f"✅ Auth OK (verwachte {status}) op {used or base}", 'ok')
          elif status in (401,403):
            flash(f"❌ Unauthorized op {used or base} (HTTP {status}, user: {user})", 'err')
          elif status == 0:
            flash(f"❌ Geen respons op {base}", 'err')
          else:
            flash(f"❌ Onverwachte respons {status} op {used or base}", 'err')
    pref = _prefix()
    return redirect(f"{pref}/" if pref else "/")
  msg, code = run_wrapper(do)
  # Flash melding + redirect naar prefix/
  if code == 200:
    prefix = "[DRY-RUN] " if _is_dry_run() else ""
    flash(f"✅ {prefix}Actie uitgevoerd: {do}", "ok")
  else:
    flash(f"❌ Actie mislukt ({do}): {msg}", "err")
  pref = _prefix()
  return redirect(f"{pref}/" if pref else "/")

@app.route("/api/status")
def api_status():
  ice_unit = os.environ.get("ICECAST_UNIT","icecast-kh")
  lsq_unit = os.environ.get("LIQUIDSOAP_UNIT","liquidsoap")
  return Response(json.dumps({
    "services": {
      "icecast": systemd_is_active(ice_unit),
      "liquidsoap": systemd_is_active(lsq_unit),
    },
    "icecast": fetch_icecast(ICECAST_STATUS_URL),
  }, ensure_ascii=False), mimetype="application/json")

# ---------- Helpers: mapping, admin, files ----------

def admin_test_bases() -> list[dict]:
  """Probe admin endpoints on configured bases. Non-destructive.
  Returns list of {base, url, status, ok, note}.
  """
  results = []
  bases = []
  for b in (ICE_ADMIN_BASE or '', os.environ.get('ICE_URL_PUBLIC',''), os.environ.get('ICE_URL_PRIVATE','')):
    b = (b or '').strip()
    if b and b not in bases:
      bases.append(b)
  user = os.environ.get('ICE_ADMIN_USER','')
  pw   = os.environ.get('ICE_ADMIN_PASS','')
  for base in bases:
    base_clean = base.rstrip('/')
    url = f"{base_clean}/admin/stats"
    status = 0; ok=False; note=''
    try:
      req = urllib.request.Request(url)
      if user or pw:
        import base64
        req.add_header('Authorization','Basic '+base64.b64encode(f"{user}:{pw}".encode('utf-8')).decode('ascii'))
      with urllib.request.urlopen(req, timeout=5) as r:
        status = r.status
        ok = (200 <= status < 300)
    except urllib.error.HTTPError as e:
      status = e.code
      ok = (200 <= status < 300)
      if status in (401,403):
        note = 'unauthorized'
      else:
        note = f'http {status}'
    except Exception as e:
      status = 0
      note = f"error: {e}"
    results.append({'base': base_clean, 'url': url, 'status': status, 'ok': ok, 'note': note})
  return results

def derive_dir_from_mount(mount: str) -> str | None:
  base = (mount or '').lstrip('/')
  base = base.split('/')[-1]
  # 1) env override MOUNT_MAP_<NAME>
  key = 'MOUNT_MAP_' + re.sub(r'[^A-Za-z0-9_]', '_', base.upper())
  if key in os.environ:
    return os.environ[key]
  # 2) mapping file
  try:
    with open('/etc/ingest-mountmap', 'r', encoding='utf-8', errors='ignore') as fh:
      for line in fh:
        line=line.strip()
        if not line or line.startswith('#'): continue
        parts=line.split()
        if len(parts)>=2 and parts[0]==base:
          return parts[1]
  except Exception:
    pass
  # 3) defaults (afstemmen met menu)
  defaults = {
    'teamfmdab.mp3':'ML5DAB2', 'ML5.mp3':'ML5', 'ML5NL.mp3':'ML5NL', 'ML5MIX.mp3':'ML5MIX',
    'ML5DAB2.mp3':'ML5DAB2', 'alltimehits.mp3':'ALLTIMEHITS', 'jumbo.mp3':'JUMBO', 'achterhoeksepiraten.mp3':'ACHTERHOEKSEPIRATEN'
  }
  return defaults.get(base)

def _safe_dir_join(base_dir: str, subdir: str) -> str | None:
  try:
    target = os.path.realpath(os.path.join(base_dir, subdir))
    base = os.path.realpath(base_dir)
    if not target.startswith(base + os.sep):
      return None
    return target
  except Exception:
    return None

def _admin_call(path: str) -> tuple[int, str]:
  """Try admin bases in order; return (status, base_used). 0 if none reachable."""
  if _is_dry_run():
    try:
      print(f"[DRY-RUN] would call {path}")
    except Exception:
      pass
    # When dry-run, pretend success and use preferred base
    b = (ICE_ADMIN_BASE or os.environ.get('ICE_URL_PUBLIC','') or os.environ.get('ICE_URL_PRIVATE','')).rstrip('/')
    return (200, b)
  bases = [ICE_ADMIN_BASE or '', os.environ.get('ICE_URL_PUBLIC',''), os.environ.get('ICE_URL_PRIVATE','')]
  for base in bases:
    base = (base or '').rstrip('/')
    if not base:
      continue
    try:
      req = urllib.request.Request(f"{base}{path}")
      auth = (os.environ.get('ICE_ADMIN_USER','')+":"+os.environ.get('ICE_ADMIN_PASS','')).encode('utf-8')
      import base64
      req.add_header('Authorization', 'Basic ' + base64.b64encode(auth).decode('ascii'))
      with urllib.request.urlopen(req, timeout=5) as r:
        return (r.status, base)
    except urllib.error.HTTPError as e:
      # Auth error: return immediately so we can hint with this base
      if e.code in (401,403):
        return (e.code, base)
      # other HTTP errors: try next base
      continue
    except Exception:
      continue
  return (0, '')

def admin_killsource(mount: str) -> tuple[int, str]:
  """Return (HTTP status code, base_used). 0 on error."""
  return _admin_call(f"/admin/killsource?mount={mount}")

def admin_moveclients(src: str, dst: str) -> tuple[int, str]:
  """Return (HTTP status code, base_used). 0 on error."""
  return _admin_call(f"/admin/moveclients?mount={src}&destination={dst}")

def poke_dir(dir_name: str) -> bool:
  try:
    full = os.path.join(MOUNT_DIR, dir_name)
    os.makedirs(full, exist_ok=True)
    fd, path = tempfile.mkstemp(prefix='.reload-', dir=full)
    os.close(fd)
    os.unlink(path)
    return True
  except Exception:
    return False

def list_mp3(dir_name: str) -> list[str]:
  try:
    full = os.path.join(MOUNT_DIR, dir_name)
    return sorted([f for f in os.listdir(full) if f.lower().endswith('.mp3') and os.path.isfile(os.path.join(full,f))])
  except Exception:
    return []

def list_dirs() -> list[str]:
  try:
    return sorted([d for d in os.listdir(MOUNT_DIR) if os.path.isdir(os.path.join(MOUNT_DIR, d))])
  except Exception:
    return []

# ---------- New actions: per-mount and files ----------

def _get_login_creds() -> tuple[str, str]:
  user = (os.environ.get('ADMIN_LOGIN_USER') or ADMIN_LOGIN_USER or '').strip()
  pw = os.environ.get('ADMIN_LOGIN_PASS') or ADMIN_LOGIN_PASS or ''
  if not pw:
    pfile = (os.environ.get('ADMIN_LOGIN_PASS_FILE') or '').strip()
    try:
      if pfile and os.path.exists(pfile):
        with open(pfile, 'r', encoding='utf-8', errors='ignore') as fh:
          pw = fh.read().strip()
        dbg(f"login creds loaded: user_set={bool(user)} from_file={bool(pw)} file={os.path.basename(pfile) if pfile else ''}")
    except Exception:
      pw = pw or ''
  return user, pw

def _login_enabled() -> bool:
  # Enforce login if a username is configured, even if password is misconfigured,
  # to avoid exposing the UI when secrets fail to load.
  u = (os.environ.get('ADMIN_LOGIN_USER') or ADMIN_LOGIN_USER or '').strip()
  return bool(u)

@app.before_request
def _enforce_login():
  if not _login_enabled():
    return
  # Allow public endpoints
  if request.endpoint in {'login','login_post','health','api_status','static'}:
    dbg(f"allow public endpoint: {request.endpoint}")
    return
  if session.get('logged_in'):
    dbg("allow: already logged in")
    return
  # Build a next URL that preserves the proxy prefix and query string
  sr = request.script_root or ''
  p = request.path or '/'
  try:
    qs = ('?' + request.query_string.decode('utf-8','ignore')) if request.query_string else ''
  except Exception:
    qs = ''
  n = f"{sr}{p}{qs}"
  dbg(f"redirect to login; next={n}")
  return redirect(url_for('login', next=n))

@app.get('/login')
def login():
  if not _login_enabled():
    return redirect(url_for('index'))
  next_url = request.args.get('next','')
  pref = _prefix() or ''
  html = '''<!doctype html><meta charset="utf-8"><title>Login</title>
  <style>body{font-family:system-ui;max-width:420px;margin:48px auto;color:#1f2937}
  .card{border:1px solid #e5e7eb;border-radius:12px;padding:16px;box-shadow:0 3px 10px rgba(0,0,0,.06)}
  label{display:block;margin:8px 0}
  input{padding:8px;border:1px solid #e5e7eb;border-radius:8px;width:100%}
  button{padding:10px 12px;border-radius:10px;border:1px solid #e5e7eb;background:#fff;cursor:pointer}
  .muted{color:#6b7280;font-size:12px;margin-top:8px}
  </style>
  <div class="card">
    <h2>Inloggen</h2>
    <form method="post" action="''' + pref + '''/login">
      <input type="hidden" name="next" value="''' + (next_url or '') + '''">
      <label>Gebruiker <input name="u" autocomplete="username"></label>
      <label>Wachtwoord <input type="password" name="p" autocomplete="current-password"></label>
      <button>Login</button>
    </form>
    <div class="muted">UI-login wordt geverifieerd tegen ADMIN_LOGIN_USER/PASS</div>
  </div>'''
  return html

@app.post('/login')
def login_post():
  if not _login_enabled():
    abort(404)
  u = (request.form.get('u','') or '').strip()
  p = request.form.get('p','') or ''
  exp_u, exp_p = _get_login_creds()
  ok = (u == exp_u and p == exp_p)
  try:
    dbg(f"login attempt user={u!r} match_user={u==exp_u} match_pw={bool(p) and bool(exp_p) and (p==exp_p)} pw_len={len(exp_p)} input_len={len(p)}")
  except Exception:
    dbg("login attempt (length logging failed)")
  if ok:
    session['logged_in'] = True
    session['user'] = u
    flash('✅ Ingelogd', 'ok')
    dest = request.form.get('next','') or url_for('index')
    dbg(f"login success; redirect={dest}")
    return redirect(dest)
  flash('❌ Onjuiste login', 'err')
  dbg("login failed")
  return redirect(url_for('login'))

@app.get('/logout')
def logout():
  session.clear()
  return redirect(url_for('login'))

def _require_csrf():
  if not ADMIN_TOKEN: abort(503, 'ADMIN_TOKEN not configured')
  if request.form.get('csrf') != ADMIN_TOKEN: abort(403, 'Bad CSRF')

@app.post('/mount/soft-reload')
def mount_soft_reload():
  _require_csrf()
  m = request.form.get('mount','')
  d = derive_dir_from_mount(m or '')
  if not d:
    flash(f"❌ Geen mapping bekend voor {m}", 'err'); return redirect(url_for('index'))
  if poke_dir(d):
    flash(f"✅ Soft reload uitgevoerd voor {m} (map {d})", 'ok')
  else:
    flash(f"❌ Soft reload mislukt voor {m}", 'err')
  pref = _prefix()
  return redirect(f"{pref}/" if pref else "/")

@app.post('/mount/disconnect')
def mount_disconnect():
  _require_csrf()
  m = request.form.get('mount','')
  code, base_used = admin_killsource(m)
  if code in (200,204):
    prefix = "[DRY-RUN] " if _is_dry_run() else ""
    flash(f"✅ {prefix}Disconnect verstuurd voor {m} (HTTP {code})", 'ok')
  elif code in (401,403):
    user=os.environ.get('ICE_ADMIN_USER','') or 'USER'
    flash(f"❌ Unauthorized/Forbidden (HTTP {code}) voor {m} — controleer admin endpoint/creds (base: {base_used}, user: {user})", 'err')
  else:
    flash(f"❌ Disconnect niet bevestigd voor {m}", 'err')
  pref = _prefix()
  return redirect(f"{pref}/" if pref else "/")

@app.post('/mount/moveclients')
def mount_moveclients():
  _require_csrf()
  src = (request.form.get('src','') or '').strip()
  dst = (request.form.get('dst','') or '').strip()
  if not src or not dst:
    flash("❌ Bron en doel zijn verplicht", 'err'); return redirect(url_for('index'))
  if src == dst:
    flash("❌ Bron en doel mogen niet gelijk zijn", 'err'); return redirect(url_for('index'))
  code, base_used = admin_moveclients(src, dst)
  if code in (200,204):
    prefix = "[DRY-RUN] " if _is_dry_run() else ""
    flash(f"✅ {prefix}Moveclients: {src} → {dst} (HTTP {code})", 'ok')
  elif code in (401,403):
    user=os.environ.get('ICE_ADMIN_USER','') or 'USER'
    hint = f"controleer ICE_ADMIN_BASE/ICE_ADMIN_USER/PASS (base: {base_used}, user: {user}) of probeer via public/private URL"
    flash(f"❌ Unauthorized/Forbidden (HTTP {code}) — {hint}", 'err')
  else:
    flash(f"❌ Moveclients niet bevestigd (bron: {src}, doel: {dst})", 'err')
  pref = _prefix()
  return redirect(f"{pref}/" if pref else "/")

@app.post('/mount/moveclients-all')
def mount_moveclients_all():
  _require_csrf()
  dst = (request.form.get('dst','') or '').strip()
  if not dst:
    flash('❌ Doelmount is verplicht', 'err'); return redirect(url_for('index'))
  # Rate-limit: voorkom snelle herhaling met lockfile in /tmp
  lock = '/tmp/ingest-admin.moveall.lock'
  try:
    now = time.time()
    if os.path.exists(lock):
      age = now - os.path.getmtime(lock)
      if age < MOVEALL_MIN_INTERVAL_SEC:
        wait_s = int(MOVEALL_MIN_INTERVAL_SEC - age)
        flash(f"❌ Te snel achter elkaar. Probeer opnieuw over ~{wait_s}s", 'err')
        return redirect(url_for('index'))
    # Touch/refresh lock
    with open(lock, 'w') as fh:
      fh.write(str(int(now)))
  except Exception:
    pass
  # Haal actuele mounts op
  ice = fetch_icecast(ICECAST_STATUS_URL)
  sources = []
  if isinstance(ice.get('mounts'), list):
    sources = [it.get('mount') for it in ice['mounts'] if it.get('mount') and it.get('mount') != dst]
  if not sources:
    flash('❌ Geen bron-mounts gevonden om te verplaatsen', 'err'); return redirect(url_for('index'))
  ok = 0; unauthorized = False; errors = 0
  for src in sources:
    code, base_used = admin_moveclients(src, dst)
    if code in (200,204):
      ok += 1
    elif code in (401,403):
      unauthorized = True
    else:
      errors += 1
  if ok:
    prefix = "[DRY-RUN] " if _is_dry_run() else ""
    flash(f"✅ {prefix}Move all: {ok}/{len(sources)} bronnen → {dst}", 'ok')
  if errors:
    flash(f"❌ {errors} bronnen gaven geen succesmelding", 'err')
  if unauthorized:
    user=os.environ.get('ICE_ADMIN_USER','') or 'USER'
    flash(f"❌ Unauthorized/Forbidden — controleer ICE_ADMIN_BASE/USER/PASS (user: {user})", 'err')
  pref = _prefix()
  return redirect(f"{pref}/" if pref else "/")

@app.post('/files/upload')
def files_upload():
  _require_csrf()
  m = request.form.get('mount','')
  dir_override = (request.form.get('dir','') or '').strip()
  file = request.files.get('file')
  if not file or not file.filename:
    flash('❌ Geen bestand gekozen', 'err'); return redirect(url_for('index'))
  if dir_override:
    d = dir_override
  else:
    d = derive_dir_from_mount(m or '')
  if not d:
    flash(f"❌ Geen mapping bekend voor {m}", 'err'); return redirect(url_for('index'))
  name = secure_filename(file.filename)
  if not name.lower().endswith('.mp3'):
    flash('❌ Alleen .mp3 toegestaan', 'err'); return redirect(url_for('index'))
  # Validate destination directory strictly
  dest_dir = _safe_dir_join(MOUNT_DIR, d)
  if not dest_dir or not os.path.isdir(dest_dir):
    flash('❌ Ongeldige doelmap', 'err'); return redirect(url_for('index'))
  dest = os.path.join(dest_dir, name)
  try:
    if _is_dry_run():
      flash(f"✅ [DRY-RUN] Zou uploaden naar {d}/{name} en soft reload triggeren", 'ok')
    else:
      os.makedirs(dest_dir, exist_ok=True)
      file.save(dest)
      poke_dir(d)
      flash(f"✅ Geüpload naar {d}/{name} en soft reload getriggerd", 'ok')
  except Exception as e:
    flash(f"❌ Upload mislukt: {e}", 'err')
  pref = _prefix()
  return redirect(f"{pref}/" if pref else "/")

@app.post('/files/delete')
def files_delete():
  _require_csrf()
  m = request.form.get('mount','')
  dir_override = (request.form.get('dir','') or '').strip()
  b = request.form.get('name','')
  d = dir_override or derive_dir_from_mount(m or '')
  if not d:
    flash(f"❌ Geen mapping bekend voor {m}", 'err'); return redirect(url_for('index'))
  name = os.path.basename(b)
  # Validate within mount dir
  target_dir = _safe_dir_join(MOUNT_DIR, d)
  if not target_dir:
    flash('❌ Ongeldige doelmap', 'err'); return redirect(url_for('index'))
  full = os.path.join(target_dir, name)
  try:
    if os.path.isfile(full):
      if _is_dry_run():
        flash(f"✅ [DRY-RUN] Zou verwijderen: {d}/{name}", 'ok')
      else:
        os.remove(full)
        poke_dir(d)
        flash(f"✅ Verwijderd: {d}/{name} en soft reload", 'ok')
    else:
      flash(f"❌ Bestaat niet: {d}/{name}", 'err')
  except Exception as e:
    flash(f"❌ Verwijderen mislukt: {e}", 'err')
  pref = _prefix()
  return redirect(f"{pref}/" if pref else "/")
