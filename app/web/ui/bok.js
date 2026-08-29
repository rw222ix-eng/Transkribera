/* ══════════ BOKEN ══════════
   Två nivåer på samma sak. Sidan man drar in tolkas mot bokens register, och
   hela boken importeras en gång så att momentet kan väljas med tre bokstäver —
   eller inte alls, eftersom appen vet vilket avsnitt som står på tur.
   Registret är listan man ALDRIG ska behöva scrolla i. */
(() => {
  const $ = s => document.querySelector(s);

  /* Registret är bokens innehållsförteckning, och det måste vara HELT: en
     förteckning med luckor mellan avsnitten gör att terminsvyn räknar bort sidor
     som finns i boken, och kursen tar slut för tidigt. Sidorna är därför
     sammanhängande från första till sista avsnittet. */
  const AVSNITT = [
    { nr: '1.1', titel: 'Algebraiska uttryck', kap: 'Kapitel 1 · Algebra', vag: 'Förenkling och faktorisering', sid: '8–19', uppg: 26 },
    { nr: '1.2', titel: 'Andragradsekvationer', kap: 'Kapitel 1 · Algebra', vag: 'Kvadratkomplettering', sid: '20–33', uppg: 24 },
    { nr: '1.3', titel: 'Polynomekvationer och faktorsatsen', kap: 'Kapitel 1 · Algebra', vag: 'Nollställen och faktorer', sid: '34–47', uppg: 22 },
    { nr: '2.1', titel: 'Funktionsbegreppet', kap: 'Kapitel 2 · Funktioner', vag: 'Definitions- och värdemängd', sid: '48–61', uppg: 20 },
    { nr: '2.2', titel: 'Andragradsfunktioner och grafer', kap: 'Kapitel 2 · Funktioner', vag: 'Symmetrilinje och extrempunkt', sid: '62–77', uppg: 25 },
    { nr: '2.3', titel: 'Absolutbelopp och styckvisa funktioner', kap: 'Kapitel 2 · Funktioner', vag: 'Grafer i delar', sid: '78–91', uppg: 18 },
    { nr: '2.4', titel: 'Modeller och tolkning av grafer', kap: 'Kapitel 2 · Funktioner', vag: 'Från verklighet till formel', sid: '92–103', uppg: 19 },
    { nr: '3.1', titel: 'Exponentialfunktioner', kap: 'Kapitel 3 · Exponentialfunktioner', vag: 'Tillväxt och avtagande', sid: '104–111', uppg: 24 },
    { nr: '3.2', titel: 'Potenslagar och rationella exponenter', kap: 'Kapitel 3 · Exponentialfunktioner', vag: 'Räknelagar', sid: '112–117', uppg: 19 },
    { nr: '3.4', titel: 'Exponentialekvationer', kap: 'Kapitel 3 · Exponentialfunktioner', vag: 'Ekvationer med okänd exponent', sid: '118–123', uppg: 18 },
    { nr: '3.5', titel: 'Logaritmer med basen 10', kap: 'Kapitel 3 · Exponentialfunktioner', vag: 'Tiologaritmen', sid: '124–129', uppg: 16 },
    { nr: '3.6', titel: 'Tillämpningar med exponentiell modell', kap: 'Kapitel 3 · Exponentialfunktioner', vag: 'Halveringstid och fördubbling', sid: '130–137', uppg: 21 },
    { nr: '4.1', titel: 'Naturliga logaritmen', kap: 'Kapitel 4 · Logaritmer', vag: 'Talet e och ln', sid: '138–151', uppg: 20 },
    { nr: '4.2', titel: 'Logaritmlagar och exponentform', kap: 'Kapitel 4 · Logaritmer', vag: 'Räknelagar', sid: '152–158', uppg: 17 },
    { nr: '4.3', titel: 'Ekvationer med logaritmer', kap: 'Kapitel 4 · Logaritmer', vag: 'Lösning och rimlighet', sid: '159–171', uppg: 22 },
    { nr: '4.4', titel: 'Gränsvärden', kap: 'Kapitel 4 · Logaritmer', vag: 'Närmevärden och asymptoter', sid: '172–183', uppg: 18 },
    { nr: '5.1', titel: 'Derivatans definition', kap: 'Kapitel 5 · Derivata', vag: 'Från sekant till tangent', sid: '184–191', uppg: 20 },
    { nr: '5.2', titel: 'Derivator av potens- och exponentialfunktioner', kap: 'Kapitel 5 · Derivata', vag: 'Grundderivatorna', sid: '192–197', uppg: 23 },
    { nr: '5.3', titel: 'Deriveringsregler', kap: 'Kapitel 5 · Derivata', vag: 'Produkt, kvot och kedja', sid: '198–206', uppg: 26 },
    { nr: '5.4', titel: 'Extrempunkter och andraderivatan', kap: 'Kapitel 5 · Derivata', vag: 'Teckenschema', sid: '207–215', uppg: 24 },
    { nr: '5.5', titel: 'Kurvor, asymptoter och optimering', kap: 'Kapitel 5 · Derivata', vag: 'Största och minsta värde', sid: '216–223', uppg: 21 },
    { nr: '6.1', titel: 'Primitiva funktioner', kap: 'Kapitel 6 · Integraler', vag: 'Motsatsen till derivering', sid: '224–231', uppg: 18 },
    { nr: '6.2', titel: 'Integraler och areor', kap: 'Kapitel 6 · Integraler', vag: 'Riemannsumma till integral', sid: '232–245', uppg: 22 },
    { nr: '6.3', titel: 'Tillämpningar av integraler', kap: 'Kapitel 6 · Integraler', vag: 'Areor mellan kurvor', sid: '246–259', uppg: 19 }
  ];
  /* Det avsnitt som gicks igenom sist — i appen ur de godkända tavlorna. */
  let senast = '5.1';
  /* Vilket register som gäller avgörs av kursen man planerar, inte av vilken bok
     appen startade med: en sökning i momentfältet på en Ma 4-lektion ska hitta
     «2.3 Polär form», inte 3c:s kapitel. */
  const kursNu = () => (($('#p-kurs') || {}).value || '').trim();
  /* Utan server är prototypens 3c-register default. MED server finns bara det
     läraren själv läst in: en kurs utan bok har inget register, och då är tomt
     det sanna svaret — inte en annan boks kapitel.

     Fallbacken var `REG_BOK[window.Bok.namn]`, alltså FÖRSTA boken i hyllan.
     Med en bok i hyllan såg det rätt ut. Med tre fick Matematik, nivå 2c —
     en kurs helt utan bok — Liber 1c:s tjugotvå avsnitt, och «nästa i boken»
     pekade på en sida i fel kurs. Den enda bok som får svara för en kurs den
     inte är märkt med är en bok utan kurs alls: den gör inget anspråk, och
     var enda boken innan uppladdningen började skicka kursen. Är de flera
     vet ingen vilken som menas, och då är tomt sanningen. */
  const otaggade = () => (servern || []).filter(b => !b.kurs);
  const registerFor = kurs => REGISTER[kurs || kursNu()]
    || (franServern()
      ? (otaggade().length === 1 ? (REG_BOK[otaggade()[0].namn] || []) : [])
      : AVSNITT);
  const nasta = (kurs, klass) => {
    const A = registerFor(kurs);
    if (!A.length) return null;
    const i = A.findIndex(a => a.nr === senast);
    if (i >= 0) return A[Math.min(A.length - 1, i + 1)];
    /* Registret känner inte avsnittet som gicks igenom sist — då är det en annan
       kurs, och det som säger var man är är klassens läge i just den kursen. */
    const kl = klass || (($('#p-klass') || {}).value || '').trim();
    const l = window.Profil && window.Profil.lageFor ? window.Profil.lageFor(kl, kurs || kursNu()) : null;
    const sid = l && l.senasteSida;
    const e = sid ? A.find(a => Number(String(a.sid).split('–')[1]) > sid) : null;
    return e || A[0];
  };
  const sok = q => {
    const l = q.trim().toLowerCase();
    if (!l) return [];
    return registerFor().filter(a => (a.nr + ' ' + a.titel + ' ' + a.vag).toLowerCase().includes(l)).slice(0, 6);
  };
  const namnet = a => `${a.nr} ${a.titel}`;

  /* Registret för Matematik 4. Böckerna delar inte avsnitt: en termin med 9B i
     Ma 4 ska inte läsa 3c:s kapitel. `forKurs` är vägen in — `avsnitt` står kvar
     som 3c så att allt som redan läser den fortsätter göra det. */
  const AVSNITT_4 = [
    { nr: '1.1', titel: 'Trigonometriska ettan', kap: 'Kapitel 1 · Trigonometri', vag: 'Enhetscirkeln', sid: '8–17', uppg: 22 },
    { nr: '1.2', titel: 'Trigonometriska ekvationer', kap: 'Kapitel 1 · Trigonometri', vag: 'Alla lösningar', sid: '18–29', uppg: 20 },
    { nr: '1.3', titel: 'Additions- och subtraktionsformler', kap: 'Kapitel 1 · Trigonometri', vag: 'Formlerna och deras bevis', sid: '30–43', uppg: 19 },
    { nr: '2.1', titel: 'Komplexa tal i rektangulär form', kap: 'Kapitel 2 · Komplexa tal', vag: 'Räknelagar i C', sid: '44–55', uppg: 24 },
    { nr: '2.2', titel: 'Komplexa talplanet', kap: 'Kapitel 2 · Komplexa tal', vag: 'Absolutbelopp och argument', sid: '56–69', uppg: 18 },
    { nr: '2.3', titel: 'Polär form och de Moivre', kap: 'Kapitel 2 · Komplexa tal', vag: 'Multiplikation som vridning', sid: '70–85', uppg: 21 },
    { nr: '3.1', titel: 'Deriveringsregler för trigonometriska funktioner', kap: 'Kapitel 3 · Derivator', vag: 'Sinus, cosinus och kedjan', sid: '86–99', uppg: 26 },
    { nr: '3.2', titel: 'Derivator av sammansatta funktioner', kap: 'Kapitel 3 · Derivator', vag: 'Kedjeregeln i flera steg', sid: '100–115', uppg: 23 },
    { nr: '3.3', titel: 'Tillämpningar och optimering', kap: 'Kapitel 3 · Derivator', vag: 'Modeller som deriveras', sid: '116–131', uppg: 20 },
    { nr: '3.4', titel: 'Differentialekvationer av första ordningen', kap: 'Kapitel 3 · Derivator', vag: 'Separabla ekvationer', sid: '132–147', uppg: 18 },
    { nr: '4.1', titel: 'Integraler och areor', kap: 'Kapitel 4 · Integraler', vag: 'Riemannsumma till integral', sid: '148–161', uppg: 23 },
    { nr: '4.2', titel: 'Partiell integration och substitution', kap: 'Kapitel 4 · Integraler', vag: 'Två metoder', sid: '162–177', uppg: 21 },
    { nr: '4.3', titel: 'Rotationsvolymer', kap: 'Kapitel 4 · Integraler', vag: 'Skivor och skal', sid: '178–195', uppg: 17 }
  ];
  const REGISTER = { 'Matematik 3c': AVSNITT, 'Matematik 4': AVSNITT_4 };
  const forKurs = kurs => REGISTER[kurs] || null;
  const BOKNAMN = { 'Matematik 3c': 'Matematik 5000+ 3c', 'Matematik 4': 'Matematik 5000+ 4' };
  /* Vilken kurs en bok i hyllan hör till. Utan den kan uppslaget inte veta vilket
     register en sida ska tolkas mot, och en Ma 4-sida får ett 3c-avsnittsnamn. */
  const KURS_FOR_BOK = { 'Matematik 5000+ 3c': 'Matematik 3c', 'Matematik 5000+ 4': 'Matematik 4', 'Exponent 3c': 'Matematik 3c' };
  /* ══════════ BÖCKERNA UR SERVERN ══════════
     Hyllan är lärarens egna böcker, och registret är läst ur deras
     innehållsförteckning (app/bok.py: innehållsförteckningen OCR:as vid
     import, sidorna när de behövs). Prototypens tre böcker står kvar tills
     servern svarar — Claude Design har ingen server, och där ska bokdörren
     fortsätta fungera precis som den gör.

     Svarar servern äger den hyllan HELT, också när den är tom: en bok läraren
     inte har lagt in ska inte stå i hennes hylla, och ett register hon inte
     läst in ska inte låtsas finnas. */
  let servern = null;                 // [{id, namn, kurs, sidor, avsnitt …}]
  const REG_BOK = {};                 // boknamn → register
  const ID_BOK = {};                  // boknamn → id på servern
  const franServern = () => Array.isArray(servern);
  const registerForBok = namn => REG_BOK[namn]
    || (franServern() ? [] : (REGISTER[KURS_FOR_BOK[namn]] || AVSNITT));
  /* Samma sak för NAMNET: dörren fick heta «Liber Ma 1c» på en Ma 2c-lektion,
     eftersom förvalet var första boken i hyllan. Utan bok för kursen är tomt
     rätt — kallor.js skriver då «Läroboken», som varken lovar eller ljuger. */
  const namnFor = kurs => BOKNAMN[kurs]
    || (franServern()
      ? (otaggade().length === 1 ? otaggade()[0].namn : '')
      : window.Bok.namn);

  function taEmot(bocker) {
    servern = bocker || [];
    Object.keys(REG_BOK).forEach(k => delete REG_BOK[k]);
    Object.keys(ID_BOK).forEach(k => delete ID_BOK[k]);
    servern.forEach(b => {
      REG_BOK[b.namn] = b.avsnitt || [];
      ID_BOK[b.namn] = b.id;
      if (b.kurs) { REGISTER[b.kurs] = b.avsnitt || []; BOKNAMN[b.kurs] = b.namn; }
      KURS_FOR_BOK[b.namn] = b.kurs || '';
    });
    if (servern.length) window.Bok.namn = servern[0].namn;
    window.Bok.bocker = servern;
    /* Remsan, hyllan, dörren och uppgiftslistan ritas ur det här — de får veta
       i samma andetag, annars står tre olika svar på samma sida. */
    document.dispatchEvent(new CustomEvent('bok-redo', { detail: servern }));
  }

  window.Bok = {
    namn: 'Matematik 5000+ 3c', avsnitt: AVSNITT, register: REGISTER, bocker: null,
    forKurs, registerFor, registerForBok, namnFor, sok, nasta, namnet, tolka,
    franServern, taEmot,
    /* Bokens id på servern — uppslaget och skrivningen behöver det för att
       kunna be om sidorna. null för prototypens böcker: de finns ingenstans. */
    bokId: namn => ID_BOK[namn] || null,
    /* ── Alla avsnitt ett sidspann rör vid ──
       Ett spann stannar sällan i ETT avsnitt. TE26A:s s. 5–9 är slutet på
       «1.1 Kvadratrötter och kubikrötter» (s. 5–6) och början på «1.2 Tal i
       potensform» (s. 7–9) — men allt som läste registret slog upp avsnittet på
       FÖRSTA sidan och stannade där. Veckans kort, uppslagets faktarad och
       momentfältet sa alla «1.1», och momentet går vidare in i prompten: tavlan
       byggdes för kubikrötter på en lektion som till hälften handlar om
       potenser. Varje avsnitt får med sin DEL av spannet, så att sidorna kan
       sägas per avsnitt och inte bara som en klump. */
    avsnitten: (A, fran, till) => (A || []).map(a => {
      const [f, t] = String(a.sid).split('–').map(Number);
      const F = Math.max(f, fran), T = Math.min(t, till);
      return T >= F ? { a, fran: F, till: T, hela: F === f && T === t } : null;
    }).filter(Boolean),
    /* Vilken kurs en bok i hyllan är märkt med. Tom sträng betyder «gör inget
       anspråk» — en sådan bok får svara för vilken kurs som helst (namnFor),
       en märkt bok bara för sin egen. */
    kursForBok: namn => KURS_FOR_BOK[namn] || '',
    /* Kursens bok, och bara när den är KÄND: hyllans bok märkt med kursen, eller
       prototypens par. Tomt betyder «vet inte» — till skillnad från `namnFor`,
       som svarar med appens förstabok när ingen server finns. Klassprofilens
       läkning (profil.js) måste kunna skilja de två: en bok den inte vet något
       om ska den inte skriva om minnet med. */
    bokFor: kurs => BOKNAMN[kurs] || '',
    /* Sidantalet i den tryckta boken (PDF:ens sidor minus omslag och förord).
       Remsan går genom hela boken och måste veta var den slutar. */
    sidorFor: namn => {
      const b = (servern || []).find(x => x.namn === namn);
      if (!b || !b.sidor) return 0;
      return Math.max(1, b.sidor - (b.sidoffset || 0));
    },
    /* Var boken börjar. Ett NEGATIVT sidoffset betyder att PDF:en saknar bokens
       första blad — i Matematik 5000+ 1a är tryckt s. 6 PDF-sida 1, och s. 1–5
       finns ingenstans. Remsan får inte erbjuda dem: sidbilden svarar 404
       «sidan ligger före bokens början» och bladet blir tomt. */
    forstaFor: namn => {
      const b = (servern || []).find(x => x.namn === namn);
      const off = b ? Number(b.sidoffset || 0) : 0;
      return off < 0 ? 1 - off : 1;
    },
    /* SWR: hyllan ändras nästan aldrig (en bok läses in någon gång per termin)
       men avsnittsregistret är stort och fyra vyer väntar på det. Cachen ritar
       hyllan direkt; servern får rätta den om en bok tillkommit. taEmot är
       idempotent och avslutas med `bok-redo`, så en omritning är ofarlig. */
    hamta: () => {
      if (!(window.API && window.API.pa)) return Promise.resolve(null);
      return window.API.jsonSWR('/api/bocker', {
        vidCache: d => taEmot(d.bocker || []),
        vidFarskt: d => taEmot(d.bocker || []),
      }).then(d => d.bocker).catch(() => null);
    },
  };
  if (window.API && window.API.redo) window.API.redo.then(() => window.Bok.hamta());

  /* ── Tolkningen av en indragen sida: rubriken som fältet fylls med ── */
  const SIDTYP = ['teori och två exempel', 'uppgifter, blandad svårighet', 'facit till uppgifterna', 'sammanfattning av avsnittet'];
  function tolka(filnamn, i) {
    const A = registerFor();
    /* Tomt register — ingen bok inläst för kursen. Samma tomkoll som nasta():
       utan den dog anroparens hela lyssnare på a.nr, och Egna filer-dörren
       blev tyst obrukbar. */
    if (!A.length) return null;
    const m = String(filnamn).match(/(\d+)[.,](\d+)/);
    const träff = m && A.find(a => a.nr === `${m[1]}.${m[2]}`);
    const a = träff || A.find(x => x.nr === senast) || A[0];
    return { avsnitt: a, rubrik: namnet(a), text: `${namnet(a)} — ${SIDTYP[i % SIDTYP.length]}` };
  }

  /* ── Sökpanelen: öppnas när man skriver, högst sex rader, grupperad ── */
  const falt = $('#moment'), panel = $('#bokpanel');
  if (!falt || !panel) return;

  function fakta(a) {
    const f = $('#momentfakta');
    if (!f) return;
    f.hidden = !a;
    if (a) f.querySelector('span:last-child').textContent = `${window.Bok.namn} · s. ${a.sid} · ${a.uppg} uppgifter`;
  }
  function valj(a) {
    falt.value = namnet(a);
    falt.removeAttribute('data-gissad');
    const g = $('#momentgissat');
    if (g) g.hidden = true;
    fakta(a);
    falt.dispatchEvent(new Event('input', { bubbles: true }));
    falt.dispatchEvent(new Event('change', { bubbles: true }));
    panel.hidden = true;
  }
  function rita(traffar) {
    if (!traffar.length) { panel.hidden = true; return; }
    let kap = '';
    panel.innerHTML = '';
    traffar.forEach(a => {
      if (a.kap !== kap) {
        kap = a.kap;
        panel.insertAdjacentHTML('beforeend', `<p class="bokgrupp">${kap}</p>`);
      }
      const b = document.createElement('button');
      b.className = 'bokrad';
      b.type = 'button';
      b.innerHTML = '<span><span class="boknamn"></span><span class="bokvag"></span></span><span class="boksid"></span>';
      b.querySelector('.boknamn').textContent = namnet(a);
      b.querySelector('.bokvag').textContent = a.vag;
      b.querySelector('.boksid').textContent = 's. ' + a.sid;
      b.addEventListener('mousedown', e => { e.preventDefault(); valj(a); });
      panel.appendChild(b);
    });
    panel.hidden = false;
  }
  falt.addEventListener('input', e => { if (!e.isTrusted) return; fakta(null); rita(sok(falt.value)); });
  falt.addEventListener('blur', () => setTimeout(() => { panel.hidden = true; }, 80));
  falt.addEventListener('keydown', e => { if (e.key === 'Escape') panel.hidden = true; });

  /* ── Nästa i boken: den vanligaste veckan kräver noll inmatning ── */
  const chip = $('#boknast');
  if (chip) {
    /* Chipet läste registret EN gång vid start. Bytte man till en lektion i en
       annan kurs stod ett 3c-avsnitt kvar som «nästa i boken» i Matematik 4. */
    /* Utan register finns inget «nästa» att peka på — då står chipet inte där
       och påstår något. Det händer med server men utan inläst bok. */
    const skriv = () => {
      const a = nasta();
      chip.hidden = !a;
      if (a) $('#boknastnamn').textContent = namnet(a);
    };
    skriv();
    $('#boknastanv').addEventListener('click', () => { const a = nasta(); if (!a) return; valj(a); senast = a.nr; skriv(); });
    const kf = $('#p-kurs');
    if (kf) kf.addEventListener('change', skriv);
    document.addEventListener('bok-redo', skriv);
  }
})();
