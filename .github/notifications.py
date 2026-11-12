"""Notifications des applis (FC St Léon, Amicale des Bagarreurs), lancé par .github/workflows/notifications.yml.

Modes (variable MODE) :
  changements : compare le calendrier avec l'état précédent (fichier ETAT) et prévient tout le monde
                si une séance à venir est modifiée ou annulée. Au premier passage, enregistre seulement l'état.
                Prévient aussi d'une nouvelle séance au calendrier et d'un résultat de match enregistré.
  rappel      : le samedi à 16 h (heure de Paris), rappelle à chacun d'indiquer sa présence pour les
                séances des 7 prochains jours auxquelles il n'a pas encore répondu (sauf profils désactivés).
  message     : message rédigé à la main (TITRE, TEXTE, CATEGORIE, LIEN ; APERCU=true pour ne rien envoyer).
  test        : envoie une notification de test à tous les téléphones inscrits.

Abonnements : collection privée fc_push (une fiche par téléphone : jeton, membre, catégories choisies),
illisible depuis le site ; lue ici avec le compte de service. Les anciens abonnements (champ « push » de la
fiche du membre) restent servis pour les catégories d'origine (calendrier modifié, rappel) jusqu'à leur migration.
L'envoi passe par Firebase Cloud Messaging (API HTTP v1) avec le compte de service du secret FCM_COMPTE.
Chaque envoi est consigné dans la collection privée fc_push_log.
"""
import datetime, json, os, re, sys, urllib.error, urllib.request
from zoneinfo import ZoneInfo

APP = os.environ["APP"]              # foot | boxe
PROJET = os.environ["PROJET"]
SITE = os.environ["SITE"]
MODE = os.environ.get("MODE", "changements")
ETAT = os.environ.get("ETAT", "/tmp/etat-notifs/etat.json")
PARIS = ZoneInfo("Europe/Paris")
NOW = datetime.datetime.now(PARIS)
TODAY = NOW.date().isoformat()
KEY = re.search(r'apiKey:\s*"([^"]+)"', open("index.html", encoding="utf-8").read()).group(1)
HDR = {"Referer": SITE}
FAUX = os.environ.get("FAUX_SERVEUR", "")   # tests : faux Firestore + faux FCM en local
BASE = (FAUX or "https://firestore.googleapis.com") + f"/v1/projects/{PROJET}/databases/(default)/documents"
FCM = (FAUX or "https://fcm.googleapis.com") + f"/v1/projects/{PROJET}/messages:send"
CATS = {"cal": "Séance modifiée ou annulée", "nouv": "Nouvelle séance au calendrier", "res": "Résultat de match", "rappel": "Rappel du samedi", "info": "Message de l'équipe"}
ONGLETS = ("", "effectif", "calendrier", "resultats", "stats")
NOM = {"foot": "FC St Léon", "boxe": "Amicale des Bagarreurs"}[APP]
ICONE = {"foot": "icon-round-192-v5.png", "boxe": "icon-192.png"}[APP]
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
KINDS = {"ent": "Entraînement", "match": "Match", "autre": "Séance"}
TYPES = {"BA": "Cours de boxe anglaise", "BF": "Cours de boxe française", "BT": "Cours de boxe thaï", "SP": "Sparring", "PP": "Préparation physique"}


def val(v):
    if "stringValue" in v: return v["stringValue"]
    if "integerValue" in v: return int(v["integerValue"])
    if "doubleValue" in v: return v["doubleValue"]
    if "booleanValue" in v: return v["booleanValue"]
    if "nullValue" in v: return None
    if "arrayValue" in v: return [val(x) for x in v["arrayValue"].get("values", [])]
    if "mapValue" in v: return {k: val(x) for k, x in v["mapValue"].get("fields", {}).items()}
    return None


def lire(col, prive=False):
    out, token = {}, ""
    while True:
        url = f"{BASE}/{col}?pageSize=300" + ("" if prive else f"&key={KEY}") + (f"&pageToken={token}" if token else "")
        try:
            data = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"Authorization": "Bearer " + acces()} if prive else HDR)))
        except urllib.error.HTTPError as e:
            if prive:
                print(f"::warning::Lecture privée de {col} impossible ({e.code}) : le compte de service a-t-il accès à Firestore ?"); return out
            print(f"::error::Lecture de {col} impossible ({e.code}) : {' '.join(e.read().decode('utf-8', 'replace').split())[:300]}")
            sys.exit(1)
        for d in data.get("documents", []):
            out[d["name"].split("/")[-1]] = {k: val(x) for k, x in d.get("fields", {}).items()}
        token = data.get("nextPageToken")
        if not token: return out


def jour(d, court=False):
    x = datetime.date.fromisoformat(d)
    return f"{JOURS[x.weekday()][:3]}. {x.day:02d}/{x.month:02d}" if court else f"{JOURS[x.weekday()]} {x.day} {MOIS[x.month - 1]}"


# ---------- Calendrier et membres, selon l'appli ----------
if APP == "foot":
    COL_MEMBRES, COL_SEANCES = "fc_players", "fc_events"
    def seances():
        return {i: {"date": e.get("date", ""), "heure": e.get("time") or "", "fin": e.get("end") or "", "lieu": e.get("place") or "",
                    "nom": KINDS.get(e.get("kind"), "Séance")}
                for i, e in lire(COL_SEANCES).items() if e.get("kind") != "note" and e.get("date")}
    def reponses():
        return {pid: set((r.get("a") or {}).keys()) for pid, r in lire("fc_rsvp").items()}
else:
    COL_MEMBRES, COL_SEANCES = "members", "courses"
    def seances():
        return {i: {"date": c.get("date", ""), "heure": c.get("time") or "", "fin": str(c.get("dur") or ""), "lieu": c.get("place") or "",
                    "nom": TYPES.get(c.get("type"), "Cours")}
                for i, c in lire(COL_SEANCES).items() if c.get("kind") != "note" and c.get("date")}
    def reponses():
        out = {}
        for a in lire("attendance").values():
            if a.get("memberId") and a.get("courseId"): out.setdefault(a["memberId"], set()).add(a["courseId"])
        return out


def membres():
    return {i: m for i, m in lire(COL_MEMBRES).items() if isinstance(m.get("push"), list) and m["push"]}


# ---------- Envoi par Firebase Cloud Messaging ----------
_jeton = None
def acces():
    global _jeton
    if _jeton: return _jeton
    if FAUX: _jeton = "test"; return _jeton
    from google.oauth2 import service_account
    import google.auth.transport.requests
    info = json.loads(os.environ["FCM_COMPTE"])
    cred = service_account.Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/firebase.messaging", "https://www.googleapis.com/auth/datastore"])
    cred.refresh(google.auth.transport.requests.Request())
    _jeton = cred.token
    return _jeton


_abos = None
def abonnes(cat):
    """Téléphones à prévenir pour une catégorie : [(membre, jeton, fiche fc_push ou None)], un jeton une seule fois."""
    global _abos
    if _abos is None:
        _abos = []
        if APP == "foot":
            for i, a in lire("fc_push", prive=True).items():
                if a.get("on") and a.get("token"): _abos.append((a.get("who") or "", a["token"], i, set(a.get("cats") or [])))
        for mid, m in membres().items():   # anciens abonnements : catégories d'origine seulement
            for tok in m["push"]: _abos.append((mid, tok, None, {"cal", "rappel"}))
    vus, out = set(), []
    for who, tok, fiche, cats in _abos:
        if tok in vus or not (cat == "test" or cat in cats): continue
        vus.add(tok); out.append((who, tok, fiche))
    return out


morts = []  # (membre, jeton, fiche) à retirer : téléphone désinstallé ou notifications coupées
def envoyer(cible, titre, texte, tag, url=None):
    who, tok, fiche = cible
    url = url or SITE
    msg = {"message": {"token": tok, "data": {"title": titre, "body": texte, "tag": tag, "url": url},
                       "webpush": {"headers": {"Urgency": "high", "TTL": "86400"}, "fcm_options": {"link": url}}}}
    req = urllib.request.Request(FCM, data=json.dumps(msg).encode(), headers={"Authorization": "Bearer " + acces(), "Content-Type": "application/json"})
    for essai in (1, 2):
        try:
            urllib.request.urlopen(req).read(); return True
        except urllib.error.HTTPError as e:
            corps = e.read().decode("utf-8", "replace")
            if e.code in (404, 400) and ("UNREGISTERED" in corps or "INVALID_ARGUMENT" in corps and "registration" in corps.lower()):
                morts.append(cible); return False
            if e.code in (429, 500, 503) and essai == 1:   # quota ou panne passagère : un seul nouvel essai
                import time; time.sleep(2); continue
            print(f"::warning::Envoi refusé ({e.code}) : {' '.join(corps.split())[:200]}"); return False
        except urllib.error.URLError as e:
            print(f"::warning::Envoi impossible : {e.reason}"); return False


def nettoyer():
    """Retire les abonnements des téléphones qui ne reçoivent plus rien."""
    if not morts: return
    par = {}
    for who, tok, fiche in morts:
        if fiche:
            try:
                urllib.request.urlopen(urllib.request.Request(f"{BASE}/fc_push/{fiche}", method="DELETE", headers={"Authorization": "Bearer " + acces()})).read()
            except urllib.error.HTTPError as e:
                print(f"::warning::Nettoyage de l'abonnement {fiche[:8]}… impossible ({e.code})")
        else: par.setdefault(who, set()).add(tok)
    tous = lire(COL_MEMBRES) if par else {}
    for mid, toks in par.items():
        m = tous.get(mid)
        if not m: continue
        reste = [t for t in (m.get("push") or []) if t not in toks]
        body = {"fields": {"push": {"arrayValue": {"values": [{"stringValue": t} for t in reste]}}}}
        url = f"{BASE}/{COL_MEMBRES}/{mid}?key={KEY}&updateMask.fieldPaths=push&currentDocument.exists=true"
        try:
            urllib.request.urlopen(urllib.request.Request(url, data=json.dumps(body).encode(), method="PATCH", headers={**HDR, "Content-Type": "application/json"})).read()
        except urllib.error.HTTPError as e:
            print(f"::warning::Nettoyage du jeton de {mid} impossible ({e.code})")
    print(f"{len(morts)} téléphone(s) retiré(s) (notifications coupées ou appli supprimée)")


def consigner(cat, titre, texte, n, total):
    """Historique des envois, dans la collection privée fc_push_log."""
    if APP != "foot": return
    f = {"at": NOW.isoformat(timespec="seconds"), "mode": MODE, "cat": cat, "titre": titre, "texte": texte}
    body = {"fields": {**{k: {"stringValue": v} for k, v in f.items()}, "envoyes": {"integerValue": str(n)}, "abonnes": {"integerValue": str(total)}}}
    try:
        urllib.request.urlopen(urllib.request.Request(f"{BASE}/fc_push_log", data=json.dumps(body).encode(), headers={"Authorization": "Bearer " + acces(), "Content-Type": "application/json"})).read()
    except Exception as e:
        print(f"::warning::Envoi non consigné dans l'historique ({e})")


def diffuser(cat, titre, texte, tag, url=None):
    cibles = abonnes(cat)
    n = sum(envoyer(c, titre, texte, tag, url) for c in cibles)
    print(f"::notice::[{CATS.get(cat, cat)}] « {titre} » envoyée à {n} téléphone(s) sur {len(cibles)} : {texte}")
    consigner(cat, titre, texte, n, len(cibles))
    return n


def libelle(s):
    return f"{s['nom']} du {jour(s['date'])}" + (f" à {s['heure']}" if s["heure"] else "")


def changements(avant, actuel, matchs_avant, matchs):
    """Notifications à envoyer, à partir de l'état précédent et de l'état actuel : [(catégorie, titre, texte, tag, onglet)].
    Fonction pure (testée) : une séance ou un match déjà connu n'est jamais annoncé deux fois."""
    out, msgs = [], []
    for i, a in avant.items():
        if a["date"] < TODAY: continue
        n = actuel.get(i)
        if n is None:
            msgs.append(("annul", f"{libelle(a)} : annulé" + ("e" if a["nom"] in ("Séance", "Préparation physique") else "") + "."))
        elif any(n[k] != a[k] for k in ("date", "heure", "fin", "lieu")):
            detail = []
            if n["date"] != a["date"]: detail.append(f"déplacé{'e' if a['nom'] in ('Séance', 'Préparation physique') else ''} au {jour(n['date'])}")
            if n["heure"] != a["heure"] or n["fin"] != a["fin"]: detail.append(f"désormais à {n['heure']}" + (f"–{n['fin']}" if APP == "foot" and n["fin"] else ""))
            if n["lieu"] != a["lieu"]: detail.append(f"lieu : {n['lieu'] or 'à préciser'}")
            msgs.append(("modif", f"{libelle(a)} : " + ", ".join(detail) + "."))
    if msgs:
        if len(msgs) == 1:
            titre = "Séance annulée" if msgs[0][0] == "annul" else "Séance modifiée"
            if APP == "boxe": titre = titre.replace("Séance", "Cours").replace("annulée", "annulé").replace("modifiée", "modifié")
            texte = msgs[0][1]
        else:
            titre = "Calendrier modifié"
            texte = " ".join(m[1] for m in msgs[:4]) + (f" (+{len(msgs) - 4} autres)" if len(msgs) > 4 else "")
        out.append(("cal", titre, texte, "calendrier", "calendrier"))
    neuves = sorted((s for i, s in actuel.items() if i not in avant), key=lambda s: (s["date"], s["heure"]))
    if len(neuves) == 1:
        s = neuves[0]; out.append(("nouv", "Nouveau au calendrier", libelle(s) + (f", {s['lieu']}" if s["lieu"] else "") + ". Indique si tu viens.", "nouveau", "calendrier"))
    elif neuves:
        out.append(("nouv", "Nouveau au calendrier", f"{len(neuves)} nouvelles séances, du {jour(neuves[0]['date'])} au {jour(neuves[-1]['date'])}. Indique tes présences.", "nouveau", "calendrier"))
    if matchs_avant is not None:
        limite = (NOW.date() - datetime.timedelta(days=7)).isoformat()
        for i, m in sorted(matchs.items()):
            if i in matchs_avant or (m.get("date") or "") < limite: continue   # ancien match restauré : pas d'annonce
            out.append(("res", "Résultat du match", f"{NOM} {m.get('us', 0)}–{m.get('them', 0)} {m.get('adv') or 'adversaire'}. Si tu as joué, vote pour l'homme du match.", "resultat-" + i, "resultats"))
    return out


# ---------- Modes ----------
if MODE == "test":
    diffuser("test", NOM, "Test : les notifications marchent sur ce téléphone \U0001F44D", "test")

elif MODE == "message":
    titre, texte = " ".join(os.environ.get("TITRE", "").split()), " ".join(os.environ.get("TEXTE", "").split())
    cat, lien = os.environ.get("CATEGORIE", "info"), os.environ.get("LIEN", "").strip().lower()
    if not titre or not texte or len(titre) > 60 or len(texte) > 240:
        print("::error::Titre (60 caractères au plus) et message (240 au plus) obligatoires : rien n'est envoyé."); sys.exit(1)
    if cat not in CATS or lien not in ONGLETS:
        print("::error::Catégorie ou lien inconnu : rien n'est envoyé."); sys.exit(1)
    url = SITE + ("#" + lien if lien else "")
    if os.environ.get("APERCU", "").lower() == "true":
        print(f"::notice::APERÇU (rien n'est envoyé) · {CATS[cat]} · {len(abonnes(cat))} téléphone(s) abonné(s) · « {titre} » : {texte} → {url}"); sys.exit(0)
    diffuser(cat, titre, texte, "info-" + NOW.strftime("%Y%m%d%H%M"), url)

elif MODE == "changements":
    actuel = {i: s for i, s in seances().items() if s["date"] >= TODAY}
    matchs = {i: {k: m.get(k) for k in ("date", "adv", "us", "them")} for i, m in lire("fc_matches").items()} if APP == "foot" else {}
    try:
        etat = json.load(open(ETAT))
    except Exception:
        etat = None
    if etat is not None and "seances" not in etat: etat = {"seances": etat, "matchs": None}   # ancien format
    nouvel = {"v": 2, "seances": actuel, "matchs": matchs}
    if etat is None:
        print("::notice::Premier passage : état du calendrier enregistré, aucune notification envoyée.")
        aenvoyer = []
    else:
        aenvoyer = changements(etat["seances"], actuel, etat.get("matchs"), matchs)
    if etat is None or {"v": 2, "seances": etat["seances"], "matchs": etat.get("matchs")} != nouvel:
        # l'état est écrit AVANT l'envoi : en cas de panne, une notification peut manquer mais ne part jamais deux fois
        os.makedirs(os.path.dirname(ETAT), exist_ok=True)
        json.dump(nouvel, open(ETAT, "w"), ensure_ascii=False, sort_keys=True)
        open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a").write("change=1\n")
    for cat, titre, texte, tag, onglet in aenvoyer:
        diffuser(cat, titre, texte, tag, SITE + "#" + onglet)

elif MODE == "rappel":
    if os.environ.get("FORCER") != "1" and not (NOW.weekday() == 5 and NOW.hour == 16):
        print(f"Pas l'heure du rappel ({NOW:%A %H:%M} à Paris) : rien à faire."); sys.exit(0)
    fin = (NOW.date() + datetime.timedelta(days=7)).isoformat()
    semaine = sorted(((i, s) for i, s in seances().items() if TODAY < s["date"] <= fin), key=lambda x: (x[1]["date"], x[1]["heure"]))
    if not semaine:
        print("::notice::Aucune séance dans les 7 prochains jours : pas de rappel."); sys.exit(0)
    rep, n, tous = reponses(), 0, lire(COL_MEMBRES)
    for cible in abonnes("rappel"):
        m = tous.get(cible[0])
        if not m or m.get("off"): continue  # profil supprimé ou désactivé : on n'attend pas sa présence
        manque = [s for i, s in semaine if i not in rep.get(cible[0], set())]
        if not manque: continue
        liste = ", ".join(f"{jour(s['date'], True)} ({s['nom']}{' ' + s['heure'] if s['heure'] else ''})" for s in manque[:5])
        texte = f"{m.get('first', '')}, indique si tu viens : {liste}" + ("…" if len(manque) > 5 else ".")
        n += envoyer(cible, "Tes présences de la semaine", texte, "rappel", SITE + "#calendrier")
    print(f"::notice::Rappel du samedi envoyé à {n} téléphone(s).")
    consigner("rappel", "Tes présences de la semaine", "(texte propre à chaque joueur)", n, len(abonnes("rappel")))

nettoyer()
