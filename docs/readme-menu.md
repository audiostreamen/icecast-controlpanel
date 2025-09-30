Instellen pagina (duidelijke structuur)
1. Linkermenu

In het linkermenu staat de knop Instellen.
Wanneer je hierop klikt voor een bepaalde service (bijvoorbeeld een Icecast-server), opent de Instellen-pagina.

2. Nieuwe menubalk bovenaan

Op de Instellen-pagina verschijnt bovenaan een extra menubalk met de volgende tabbladen:

Algemeen

Limieten

Functies

Icecast 2 KH

AutoDJ

Relais

Elk tabblad bevat zijn eigen instellingen. Hieronder de volledige indeling:

🔹 Tabblad: Algemeen

Hier configureer je de basisinstellingen van de service.

Service Type* → bijvoorbeeld Icecast 2 KH

Eigenaar* → naam of e-mailadres van de gebruiker

Unieke ID* → intern ID van de service (bijv. 8174)

Poortnummer* → gekozen poort, samen met poort+1 moet beschikbaar zijn

Wachtwoord* → Sterkwachtwoord

Stream Bron wachtwoord → Sterkwachtwoord

Relay Bron wachtwoord → Sterkwachtwoord

🔹 Tabblad: Limieten

Hier stel je technische limieten en capaciteit in.

Mount punten* → aantal mountpoints (bijv. 1)

# van AutoDJ* → aantal AutoDJ-services dat gekoppeld mag worden (bijv. 1)

Bitrate* → maximale bitrate (bijv. 320 kbps)

Maximaal aantal gebruikers* → max. aantal luisteraars (bijv. 100)

Bandbreedte (MB)* → datalimiet (0 = ongelimiteerd)

Opslaglimiet (MB)* → opslagruimte voor AutoDJ/media (bijv. 11000 MB)

🔹 Tabblad: Functies

Hier kies je welke extra functies de service heeft.

Historische rapportage → geavanceerde luisterstatistieken

HTTP/HTTPS Proxy-ondersteuning* → streamen mogelijk achter firewall

GeoIP-landvergrendeling → toegang beperken op basis van land

Streamauthenticatie → luisteraars moeten inloggen

Laat meerdere gebruikers toe → meerdere luisteraars met dezelfde login

Openbare pagina* → publieke spelerpagina met luisteraars & trackgeschiedenis

Posten op sociale media → automatische posts bij live-uitzending

Live-opname toestaan → uitzendingen automatisch opnemen

🔹 Tabblad: Icecast 2 KH

Hier stel je Icecast-specifieke opties in.

Publieke server* → Default = de bron bepaalt

Introbestand → korte intro-track (zelfde bitrate/channels als de stream)

Publiceer naar YP → publiceren naar directories (bijv. http://dir.xiph.org/cgi-bin/yp-cgi)

Redirect Icecast-pagina → hoofdindexpagina omleiden naar standaard mount

🔹 Tabblad: AutoDJ

Hier beheer je de AutoDJ en de crossfade-instellingen.

AutoDJ-type* → liquidsoap

Crossfade Fade-in duur* → duur in seconden (bijv. 0)

Crossfade Fade-out duur* → duur in seconden (bijv. 0)

Minimale drempelwaarde voor crossfade → minimale tracklengte voor overgang (0 = uitgeschakeld)

Slimme crossfade → kan hier handmatig worden aangezet of uitgezet.
Deze functie berekent automatisch het volume en bepaalt de beste overgang.

Replay Gain aanpassen → gebruikt metadata voor volumeregeling

👉 Let op: de Slimme crossfade is dus een duidelijke optie op dit tabblad en kan door de beheerder eenvoudig in- of uitgeschakeld worden.

🔹 Tabblad: Relais

Hier stel je relay-functionaliteit in.

Type relais

Master-Slave-relay → volledige Icecast-server overnemen

Single Broadcast-relay → enkel één mount relayen naar lokaal mount

Uitgeschakeld → geen relay

✅ Samenvatting:

In het linkermenu klik je op Instellen.

Op de Instellen-pagina verschijnt een nieuwe menubalk bovenaan.

Deze menubalk heeft 6 tabbladen (Algemeen, Limieten, Functies, Icecast 2 KH, AutoDJ, Relais).

Elk tabblad bevat zijn eigen instellingen (zoals hierboven beschreven).

Belangrijk detail: Slimme crossfade kan worden ingesteld via het AutoDJ-tabblad.

-----------------------------

Menu bovenin de instellingen

Algemeen

Limieten

Functies

Icecast 2 KH

AutoDJ

Relais

🔹 Algemeen

Service Type*
Icecast 2 KH

Eigenaar*
piet@hotmail.com

Unieke ID*
8174

Poortnummer*
8174 (poort en poort+1 moeten beschikbaar zijn)

Wachtwoord*
Nodig voor streamen en administratie.
Voorbeeld: S4K

Stream Bron wachtwoord
S4Kkj2

Relay Bron wachtwoord
hgL0

🔹 Limieten

Mount punten* → 1

# van AutoDJ* → 1

Bitrate* → 320 kbps

Maximaal aantal gebruikers* → 100

Bandbreedte (MB)* → 0 (ongelimiteerd)

Opslaglimiet (MB)* → 11000

🔹 Functies

Historische rapportage
Geavanceerde rapportages.

HTTP/HTTPS Proxy-ondersteuning*
Streamen mogelijk achter firewall.

GeoIP-landvergrendeling
Beperkt luisteren op basis van locatie.

Streamauthenticatie
Stream Authentication Control.

Laat meerdere gebruikers toe
Meerdere luisteraars met zelfde login.

Openbare pagina*
Stationpagina met speler, luisteraars, trackgeschiedenis.

Posten op sociale media
Automatische aankondigingen op Facebook/Twitter.

Live-opname toestaan
Mogelijkheid om uitzendingen op te nemen.

🔹 Icecast 2 KH

Publieke server*
Default – Source Client bepaalt

Introbestand
Intro muziektrack (zelfde bitrate/channels als stream).

Publiceer naar YP
Aan/uit + YP-directory URL(s) → http://dir.xiph.org/cgi-bin/yp-cgi

Redirect Icecast-pagina
Hoofdindexpagina doorsturen naar default mount.

🔹 AutoDJ

AutoDJ-type* → liquidsoap

Crossfade Fade-in duur* → 0

Crossfade Fade-out duur* → 0

Minimale drempelwaarde voor crossfade → 0 (geen overgang)

Slimme crossfade
Bepaalt automatisch crossfade op basis van volume.

Replay Gain aanpassen
Gebruik metadata voor volumeregeling.

🔹 Relais

Type relais

Master-Slave-relay: complete Icecast-server overnemen

Single Broadcast-relay: enkel 1 mount relayed naar lokaal mountpunt

Uitgeschakeld