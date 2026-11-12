"""Tests du programme d'envoi des notifications (.github/notifications.py).
Lancer : python3 tests/notifications.test.py   (aucune dépendance, aucun envoi réel)
Un faux serveur local remplace Firestore et Firebase Cloud Messaging : on vérifie ce que le programme
enverrait, à qui, et qu'il ne l'envoie pas deux fois."""
import http.server, json, os, subprocess, sys, tempfile, threading, datetime, re

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = lambda v: {"stringValue": v}
def doc(col, i, f):
    def V(v):
        if isinstance(v, bool): return {"booleanValue": v}
        if isinstance(v, int): return {"integerValue": str(v)}
        if isinstance(v, list): return {"arrayValue": {"values": [V(x) for x in v]}}
        if isinstance(v, dict): return {"mapValue": {"fields": {k: V(x) for k, x in v.items()}}}
        return S(v)
    return {"name": f"projects/p/databases/(default)/documents/{col}/{i}", "fields": {k: V(v) for k, v in f.items()}}

class Faux(http.server.BaseHTTPRequestHandler):
    base, envois, journal, supprimes, prive_sans_cle, morts = {}, [], [], [], [], set()
    def log_message(self, *a): pass
    def _ok(self, o=None):
        b = json.dumps(o or {}).encode(); self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        col = self.path.split("/documents/")[1].split("?")[0]
        if col in ("fc_push", "fc_push_log"):
            if "key=" in self.path or not self.headers.get("Authorization"):   # lecture publique interdite
                self.send_response(403); self.end_headers(); self.wfile.write(b"{}"); return
        self._ok({"documents": [doc(col, i, f) for i, f in Faux.base.get(col, {}).items()]})
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path.endswith("messages:send"):
            m = body["message"]
            if m["token"] in Faux.morts:
                self.send_response(404); self.end_headers(); self.wfile.write(b'{"error":{"status":"NOT_FOUND","details":[{"errorCode":"UNREGISTERED"}]}}'); return
            Faux.envois.append(m); return self._ok({"name": "ok"})
        Faux.journal.append(body["fields"]); self._ok()
    def do_DELETE(self):
        Faux.supprimes.append(self.path.split("/documents/")[1]); self._ok()
    def do_PATCH(self):
        self.rfile.read(int(self.headers["Content-Length"])); Faux.supprimes.append("PATCH " + self.path.split("/documents/")[1].split("?")[0]); self._ok()

srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Faux)
threading.Thread(target=srv.serve_forever, daemon=True).start()
etat = os.path.join(tempfile.mkdtemp(), "etat.json")

def lancer(mode, **env):
    Faux.envois.clear(); Faux.journal.clear(); Faux.supprimes.clear()
    e = dict(os.environ, APP="foot", PROJET="p", SITE="https://exemple.test/app/", MODE=mode, ETAT=etat, FORCER="1",
             FAUX_SERVEUR=f"http://127.0.0.1:{srv.server_port}", GITHUB_OUTPUT=os.devnull, **env)
    r = subprocess.run([sys.executable, os.path.join(RACINE, ".github", "notifications.py")], cwd=RACINE, env=e, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr

n = echecs = 0
def test(nom, cond, detail=""):
    global n, echecs; n += 1
    if cond: print("ok   " + nom)
    else: echecs += 1; print("FAIL " + nom + ("\n     " + str(detail)[:600] if detail else ""))

demain = (datetime.date.today() + datetime.timedelta(days=2)).isoformat()
plus = (datetime.date.today() + datetime.timedelta(days=4)).isoformat()
auj = datetime.date.today().isoformat()
seance = lambda d, t="20:00", lieu="Stade": {"date": d, "time": t, "end": "21:30", "kind": "ent", "place": lieu, "note": ""}
Faux.base = {
    "fc_players": {"p1": {"first": "Ana", "last": "A", "push": ["ANCIEN-JETON-AAAAAAAAAAAAAAAA"]}, "p2": {"first": "Bob", "last": "B"}, "p3": {"first": "Cy", "last": "C", "off": True}},
    "fc_events": {"e1": seance(demain), "n1": {"kind": "note", "title": "ticket"}},
    "fc_rsvp": {"p2": {"a": {"e1": "p"}}},
    "fc_matches": {"m1": {"date": auj, "adv": "Vieux FC", "us": 1, "them": 0}},
    "fc_push": {
        "i-tout": {"token": "JETON-TOUT-AAAAAAAAAAAAAAAAAAAA", "who": "p2", "cats": ["cal", "nouv", "res", "rappel", "info"], "on": True},
        "i-info": {"token": "JETON-INFO-AAAAAAAAAAAAAAAAAAAA", "who": "", "cats": ["info"], "on": True},
        "i-off": {"token": "JETON-OFF-AAAAAAAAAAAAAAAAAAAAA", "who": "p2", "cats": ["cal", "info"], "on": False},
        "i-p3": {"token": "JETON-P3-AAAAAAAAAAAAAAAAAAAAAA", "who": "p3", "cats": ["rappel"], "on": True},
        "i-double": {"token": "ANCIEN-JETON-AAAAAAAAAAAAAAAA", "who": "p1", "cats": ["cal", "rappel", "res"], "on": True},
    }}
jetons = lambda: sorted(m["token"][:11] for m in Faux.envois)

c, o = lancer("changements")
test("Premier passage : l'état est enregistré, rien n'est envoyé", c == 0 and not Faux.envois and os.path.exists(etat), o)
c, o = lancer("changements")
test("Rien n'a changé : rien n'est envoyé", c == 0 and not Faux.envois, o)

Faux.base["fc_events"]["e2"] = seance(plus, "19:00", "Stade Jean Coteau")
c, o = lancer("changements")
test("Nouvelle séance : une notification « Nouveau au calendrier » aux abonnés de cette catégorie seulement",
     jetons() == ["JETON-TOUT-"] and Faux.envois[0]["data"]["title"] == "Nouveau au calendrier" and Faux.envois[0]["data"]["url"].endswith("#calendrier"), (jetons(), o))
test("L'envoi est consigné dans l'historique privé", len(Faux.journal) == 1 and Faux.journal[0]["cat"]["stringValue"] == "nouv" and Faux.journal[0]["envoyes"]["integerValue"] == "1", Faux.journal)
c, o = lancer("changements")
test("Séance déjà annoncée : jamais de deuxième notification", not Faux.envois, o)

Faux.base["fc_events"]["e1"]["time"] = "20:30"
c, o = lancer("changements")
test("Séance modifiée : « Séance modifiée », l'ancien abonnement et le nouveau reçoivent une seule fois chacun",
     jetons() == ["ANCIEN-JETO", "JETON-TOUT-"] and Faux.envois[0]["data"]["title"] == "Séance modifiée", (jetons(), o))
test("Abonnement coupé (on=false) ou autre catégorie : rien reçu", "JETON-OFF-A" not in jetons() and "JETON-INFO-" not in jetons())
Faux.base["fc_events"]["n1"]["title"] = "ticket modifié"
c, o = lancer("changements")
test("Un ticket de l'onglet Notes n'est pas une séance : rien n'est envoyé", not Faux.envois, o)
del Faux.base["fc_events"]["e2"]
c, o = lancer("changements")
test("Séance supprimée : « Séance annulée »", Faux.envois and Faux.envois[0]["data"]["title"] == "Séance annulée", o)

Faux.base["fc_matches"]["m2"] = {"date": auj, "adv": "Les Gars de la Ville", "us": 4, "them": 3}
Faux.base["fc_matches"]["m0"] = {"date": "2026-01-10", "adv": "Ancien", "us": 0, "them": 0}
c, o = lancer("changements")
test("Résultat enregistré : une notification avec le score, lien vers Résultats ; un vieux match restauré n'est pas annoncé",
     len({m["data"]["tag"] for m in Faux.envois}) == 1 and "4–3 Les Gars de la Ville" in Faux.envois[0]["data"]["body"] and Faux.envois[0]["data"]["url"].endswith("#resultats"), (Faux.envois, o))
Faux.base["fc_matches"]["m2"]["us"] = 5
c, o = lancer("changements")
test("Match corrigé après coup : pas de nouvelle notification", not Faux.envois, o)

c, o = lancer("message", TITRE="Photo d'équipe", TEXTE="Samedi, venez avec le maillot rouge.", CATEGORIE="info", LIEN="calendrier", APERCU="true")
test("Message, aperçu : rien n'est envoyé, le nombre de destinataires est affiché", c == 0 and not Faux.envois and "2 téléphone(s)" in o and "APERÇU" in o, o)
c, o = lancer("message", TITRE="Photo d'équipe", TEXTE="Samedi, venez avec le maillot rouge.", CATEGORIE="info", LIEN="calendrier")
test("Message envoyé aux abonnés « Messages de l'équipe » seulement", jetons() == ["JETON-INFO-", "JETON-TOUT-"] and Faux.envois[0]["data"]["body"].startswith("Samedi"), (jetons(), o))
c, o = lancer("message", TITRE="", TEXTE="x", CATEGORIE="info")
test("Message sans titre : refusé", c != 0 and not Faux.envois, o)
c, o = lancer("message", TITRE="T", TEXTE="x" * 241, CATEGORIE="info")
test("Message trop long : refusé", c != 0 and not Faux.envois, o)
c, o = lancer("message", TITRE="T", TEXTE="x", CATEGORIE="info", LIEN="https://ailleurs.example")
test("Lien hors de l'appli : refusé", c != 0 and not Faux.envois, o)

c, o = lancer("rappel")
test("Rappel du samedi : seulement à qui n'a pas répondu, pas aux profils désactivés ni aux visiteurs sans profil",
     jetons() == ["ANCIEN-JETO"] and "Ana" in Faux.envois[0]["data"]["body"], (jetons(), o))

Faux.morts.add("JETON-TOUT-AAAAAAAAAAAAAAAAAAAA")
c, o = lancer("message", TITRE="T", TEXTE="x", CATEGORIE="info")
test("Téléphone qui ne reçoit plus (appli supprimée) : son abonnement est effacé", "fc_push/i-tout" in Faux.supprimes and jetons() == ["JETON-INFO-"], (Faux.supprimes, o))

src = open(os.path.join(RACINE, ".github", "notifications.py"), encoding="utf-8").read() + open(os.path.join(RACINE, "index.html"), encoding="utf-8").read()
test("Aucune clé privée dans le code public", "BEGIN PRIVATE KEY" not in src and "private_key" not in src)
regles = open(os.path.join(RACINE, "firestore.rules"), encoding="utf-8").read()
test("Règles : les abonnements et l'historique ne sont pas lisibles", re.search(r"match /fc_push/\{id\} \{\s*allow read: if false;", regles) and "match /fc_push_log/{id} { allow read, write: if false; }" in regles)

print(f"\n{n - echecs} / {n} tests réussis"); sys.exit(1 if echecs else 0)
