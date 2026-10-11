// Tests du moteur d'actions et de possession (scénarios A à J du cahier des charges).
// Lancer : node tests/moteur.test.js   (aucune dépendance)
// Le moteur est lu directement dans index.html, entre /*ENGINE-START*/ et /*ENGINE-END*/ :
// on teste donc exactement le code qui tourne dans l'appli.
const fs = require("fs"), path = require("path"), vm = require("vm"), assert = require("assert");
const html = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");
const code = html.slice(html.indexOf("/*ENGINE-START*/"), html.indexOf("/*ENGINE-END*/"));
const E = {};
vm.runInNewContext(code + ";Object.assign(E,{ACTS,applyRule,replayEvents,statsFromList,possTotals,possPct});", { E });
// results are copied into plain objects (the engine runs in its own context)
const plain = fn => (...a) => JSON.parse(JSON.stringify(fn(...a)));
const replayEvents = plain(E.replayEvents), statsFromList = plain(E.statsFromList), possTotals = plain(E.possTotals), possPct = plain(E.possPct);

let n = 0, failed = 0;
function test(name, fn) { n++; try { fn(); console.log("ok   " + name) } catch (e) { failed++; console.log("FAIL " + name + "\n     " + e.message) } }
const ev = (code, pid, gt, extra) => Object.assign({ id: "e" + Math.random(), code, pid, gt: gt * 1000, h: 1 }, extra || {});
const poss = (to, gt) => ({ id: "p" + Math.random(), code: "poss", to, origin: "manual", gt: gt * 1000, h: 1 });
const statsOf = (evs, poss0, pid = "j") => statsFromList(replayEvents(evs, poss0).list).by[pid] || {};
const sum = o => Object.values(o).reduce((a, b) => a + b, 0);

test("A · but = 1 tir, 1 tir cadré, 1 but, rien d'autre", () => {
  const s = statsOf([ev("goal", "j", 10)], "us");
  assert.deepStrictEqual(s, { tr: 1, b: 1 });                 // tirs = tr + tm = 1
  assert.strictEqual(replayEvents([ev("goal", "j", 10)], "us").poss, "them"); // engagement adverse
});
test("B · duel gagné sans le ballon = 1 duel gagné + 1 récupération, ballon à nous", () => {
  const R = replayEvents([ev("duel_won", "j", 5)], "them");
  assert.deepStrictEqual(statsFromList(R.list).by.j, { dr: 1, rec: 1 });
  assert.strictEqual(R.poss, "us");
});
test("C · duel gagné avec le ballon = 1 duel gagné + 1 dribble réussi, possession gardée", () => {
  const R = replayEvents([ev("duel_won", "j", 5)], "us");
  assert.deepStrictEqual(statsFromList(R.list).by.j, { dr: 1, drb: 1 });
  assert.strictEqual(R.poss, "us"); assert.strictEqual(R.changes.length, 1);
});
test("C bis · duel perdu avec le ballon = duel perdu + dribble raté + perte, ballon à l'adversaire", () => {
  const R = replayEvents([ev("duel_lost", "j", 5)], "us");
  assert.deepStrictEqual(statsFromList(R.list).by.j, { dm: 1, drm: 1, per: 1 }); assert.strictEqual(R.poss, "them");
});
test("C ter · duel perdu sans le ballon = 1 duel perdu seulement, l'adversaire garde le ballon", () => {
  const R = replayEvents([ev("duel_lost", "j", 5)], "them");
  assert.deepStrictEqual(statsFromList(R.list).by.j, { dm: 1 }); assert.strictEqual(R.poss, "them");
});
test("D · passe ratée = 1 passe ratée + 1 perte, ballon à l'adversaire", () => {
  const R = replayEvents([ev("pass_ko", "j", 5)], "us");
  assert.deepStrictEqual(statsFromList(R.list).by.j, { pm: 1, per: 1 }); assert.strictEqual(R.poss, "them");
});
test("E · récupération oubliée : passe réussie alors que l'adversaire a le ballon", () => {
  const R = replayEvents([ev("pass_ko", "j", 5), ev("pass_ok", "k", 20)], "us");
  assert.strictEqual(R.poss, "us");
  const x = R.list[1]; assert.strictEqual(x.implicit, true); assert.strictEqual(x.before, "them");
  const T = statsFromList(R.list).by;
  assert.deepStrictEqual(T.k, { pr: 1 });                     // aucune récupération inventée
  assert.ok(!Object.values(T).some(s => s.rec));
  const imp = R.changes.find(c => c.origin === "implicit");    // horodatée à l'action saisie, pas avant
  assert.strictEqual(imp.gt, 20000);
});
test("F · correction manuelle : la possession bascule, aucune stat individuelle", () => {
  const R = replayEvents([poss("them", 30)], "us");
  assert.strictEqual(R.poss, "them"); assert.deepStrictEqual(statsFromList(R.list).by, {});
  const t = possTotals(R.changes, 50000, Infinity);
  assert.strictEqual(t.us, 30000); assert.strictEqual(t.them, 20000);
});
test("G · 60 s pour nous, 40 s pour l'adversaire = 60 % / 40 %", () => {
  const R = replayEvents([poss("them", 60)], "us");
  const pc = possPct(possTotals(R.changes, 100000, Infinity));
  assert.strictEqual(pc.us, 60); assert.strictEqual(pc.them, 40);
});
test("G bis · exemple du cahier : 85 s / 35 s = 70,8 % / 29,2 %", () => {
  const R = replayEvents([poss("them", 35), poss("us", 70)], "us");
  const t = possTotals(R.changes, 120000, Infinity), pc = possPct(t);
  assert.strictEqual(t.us, 85000); assert.strictEqual(t.them, 35000);
  assert.strictEqual(pc.us, 70.8); assert.strictEqual(pc.them, 29.2); assert.strictEqual(pc.us + pc.them, 100);
});
test("H · pause : le temps est mesuré en temps de jeu, une pause de 5 min ne compte pas", () => {
  // chrono arrêté 5 min à 40 s de jeu : le temps de jeu reste 40 s pendant la pause, puis repart
  const R = replayEvents([], "us");
  assert.strictEqual(possTotals(R.changes, 40000, Infinity).us, 40000);
  assert.strictEqual(possTotals(R.changes, 40000 + 20000, Infinity).us, 60000);
});
test("I · annuler une passe ratée annule la perte et le changement de possession", () => {
  const evs = [ev("pass_ok", "j", 5), ev("pass_ko", "j", 30)];
  const before = replayEvents(evs, "us"); assert.strictEqual(before.poss, "them");
  const after = replayEvents(evs.slice(0, -1), "us");
  assert.strictEqual(after.poss, "us"); assert.deepStrictEqual(statsFromList(after.list).by.j, { pr: 1 });
  assert.strictEqual(possPct(possTotals(after.changes, 60000, Infinity)).us, 100);
});
test("J · rejouer les mêmes événements (rechargement) donne exactement le même résultat", () => {
  const evs = [ev("duel_won", "j", 3), ev("pass_ok", "k", 9), ev("goal", "k", 15, { ast: "j" }), ev("save", "g", 40), poss("them", 50)];
  const saved = JSON.parse(JSON.stringify(evs));               // ce qui est gardé sur l'appareil
  const a = replayEvents(evs, "them"), b = replayEvents(saved, "them");
  assert.deepStrictEqual(statsFromList(a.list), statsFromList(b.list));
  assert.deepStrictEqual(possTotals(a.changes, 70000, 30000), possTotals(b.changes, 70000, 30000));
});
test("Passe décisive : seulement si le passeur est indiqué, jamais inventée", () => {
  const without = statsFromList(replayEvents([ev("pass_ok", "j", 1), ev("goal", "k", 2)], "us").list).by;
  assert.ok(!without.j.pd);
  const withAst = statsFromList(replayEvents([ev("pass_ok", "j", 1), ev("goal", "k", 2, { ast: "j" })], "us").list).by;
  assert.strictEqual(withAst.j.pd, 1); assert.strictEqual(withAst.k.pd, undefined);
});
test("Gardien : arrêt = ballon à nous, but encaissé = engagement pour nous", () => {
  let R = replayEvents([ev("save", "g", 5)], "them"); assert.strictEqual(R.poss, "us");
  assert.deepStrictEqual(statsFromList(R.list).by.g, { arr: 1 });
  R = replayEvents([ev("conc", "g", 5)], "them"); assert.strictEqual(R.poss, "us");
});
test("Tirs : non cadré et cadré rendent le ballon, chaque tir compté une fois", () => {
  const R = replayEvents([ev("shot_off", "j", 1), ev("shot_on", "j", 2), ev("goal", "j", 3)], "us");
  const s = statsFromList(R.list).by.j; assert.strictEqual(s.tr + s.tm, 3); assert.strictEqual(s.tr, 2); assert.strictEqual(s.b, 1);
});
test("Idempotence : recalculer deux fois ne double rien", () => {
  const evs = [ev("pass_ko", "j", 1), ev("duel_won", "j", 2), ev("goal", "j", 3)];
  const a = statsFromList(replayEvents(evs, "us").list), b = statsFromList(replayEvents(evs, "us").list);
  assert.deepStrictEqual(a, b); assert.strictEqual(sum(a.by.j), 2 + 2 + 2);
});
test("Mi-temps : le temps est réparti par période, ballon libre exclu du pourcentage", () => {
  const evs = [poss("them", 20), Object.assign(poss("us", 30), { h: 2, origin: "kickoff" }), Object.assign(poss("unk", 40), { h: 2 })];
  const t = possTotals(replayEvents(evs, "us").changes, 50000, 30000);
  assert.deepStrictEqual([t.h1.us, t.h1.them, t.h2.us, t.h2.unk], [20000, 10000, 10000, 10000]);
  assert.strictEqual(possPct(t).us, 75);                       // 30 s / (30 + 10) — les 10 s libres sont à part
});
test("Ballon libre : le temps compte à part, hors pourcentage, puis reprise", () => {
  const evs = [Object.assign(poss("unk", 20), { origin: "neutral", prev: "us" }), Object.assign(poss("us", 50), { origin: "resume" })];
  const R = replayEvents(evs, "us"), t = possTotals(R.changes, 80000, Infinity);
  assert.deepStrictEqual([t.us, t.them, t.unk], [50000, 0, 30000]);
  assert.strictEqual(possPct(t).us, 100);                       // les 30 s libres ne sont dans aucun pourcentage
  assert.deepStrictEqual(statsFromList(R.list).by, {});         // aucune stat individuelle
});
test("Ballon libre : une action saisie pendant ce temps reprend la logique", () => {
  let R = replayEvents([Object.assign(poss("unk", 10), { prev: "us" }), ev("pass_ok", "j", 25)], "us");
  assert.strictEqual(R.poss, "us"); assert.ok(!statsFromList(R.list).by.j.rec);   // pas de récupération inventée
  R = replayEvents([Object.assign(poss("unk", 10), { prev: "us" }), ev("duel_won", "j", 25)], "us");
  assert.strictEqual(R.poss, "us"); assert.deepStrictEqual(statsFromList(R.list).by.j, { dr: 1, rec: 1 }); // ballon disputé gagné = récupération
  assert.strictEqual(possTotals(R.changes, 40000, Infinity).unk, 15000);
});
console.log("\n" + (n - failed) + " / " + n + " tests réussis");
process.exit(failed ? 1 : 0);
