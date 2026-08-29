/* ══════════ GRANSKA — dokumentet i en canvas, med elementval och kommentarer ══════════
   Öppnas från planeringen: window.Granska.oppna({ nod, titel, meta, onAndra })
   Panorera med musen, zooma med hjulet, och sätt kommentarer som fäster på element. */
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const skal = $('#granskaskal');
  if (!skal) return;
  const duk = $('#g-duk'), plan = $('#g-plan'), lista = $('#g-lista');
  let vy = { x: 0, y: 0, z: 1 }, valjLage = false, kommentarer = [], nr = 0, host = null, forraOverflow = '';
  /* Går ett varv just nu? Ett dokument skrivs om en gång i taget: servern låser
     per dokument och versionerar optimistiskt, så två varv mot samma papper kan
     aldrig sparas båda. Det läraren skriver medan varvet går hamnar därför i
     `ko` och avfyras när varvet är över — se KÖN nedan. */
  let skickarNu = false;
  /* KÖN — lärarens önskemål som väntar på tur, i den ordning hon skrev dem. */
  let ko = [];

  const satVy = () => {
    plan.style.transform = `translate3d(${vy.x}px,${vy.y}px,0) scale(${vy.z})`;
    $('#g-zoomtext').textContent = Math.round(vy.z * 100) + ' %';
    $$('.gpin', plan).forEach(p => { p.style.transform = `translate(-50%,-50%) scale(${1 / vy.z})`; });
  };
  const zooma = (faktor, cx, cy) => {
    const ny = Math.min(3, Math.max(0.25, vy.z * faktor));
    satLage(null);
    const r = duk.getBoundingClientRect();
    /* Punkten zoomen håller fast vid, i dukens egna koordinater. Raden var förr
       en subtraktion använd som villkor — den råkade fungera så länge duken
       började på x = 0 och hoppade till mitten så fort den inte gjorde det. */
    const px = (cx ?? r.left + r.width / 2) - r.left;
    const py = (cy ?? r.top + r.height / 2) - r.top;
    vy.x = px - (px - vy.x) * (ny / vy.z);
    vy.y = py - (py - vy.y) * (ny / vy.z);
    vy.z = ny;
    satVy();
  };
  function anpassa() {
    satLage('fit');
    passa('bredd');
  }
  /* Tre lägen med namn i stället för ett «Återställ»: sidbredd (det man läser i),
     100 % (papprets egen storlek) och hela dokumentet (överblicken). */
  function passa(lage) {
    const nod = $('.gdok', plan);
    if (!nod) return;
    const r = duk.getBoundingClientRect();
    const b = nod.getBoundingClientRect();
    const naturlig = b.width / vy.z, hojd = b.height / vy.z;
    /* Ett prov är fyra sidor i en trave. Att krämma in hela traven i höjden gav
       25 % — ett papper man inte kan läsa ett ord av. Bredden är det som bestämmer
       läsbarheten: sidan får fylla duken, och är traven högre än duken börjar den
       i överkanten — där man börjar läsa — i stället för att centreras. */
    if (lage === 'ett') vy.z = 1;
    else if (lage === 'hela') vy.z = Math.max(0.15, Math.min((r.width - 96) / naturlig, (r.height - 96) / hojd, 1.6));
    else vy.z = Math.max(0.3, Math.min((r.width - 96) / naturlig, 1.6));
    const h = hojd * vy.z;
    vy.x = (r.width - naturlig * vy.z) / 2;
    vy.y = h <= r.height - 96 ? (r.height - h) / 2 : 40;
    satVy();
  }
  const lagen = $$('.gzlagen button');
  const satLage = n => lagen.forEach(b => b.setAttribute('aria-pressed', String(b.dataset.z === n)));

  /* ── panorera och zooma ── */
  let drar = null;
  duk.addEventListener('pointerdown', e => {
    if (valjLage && e.target.closest('[data-el]')) return;
    /* `.aprick` med i listan: pekarfångsten nedan äter annars klicket på
       prickarna i pappret — panoreringen tog gesten och knappen fick aldrig
       veta att någon tryckte på den. Samma skäl som nålarna står här.

       `.prplatfot` och `.prscen` av EXAKT samma skäl (lärarens arbetsblad
       2026-08-25): setPointerCapture flyttar klickets mål till duken, så
       «Byt plåt», «Ta bort» och «Kopiera scen» fick aldrig veta att någon
       tryckte — och scenrutans släppyta, som öppnar filväljaren när man
       klickar den, inte heller. Bara foten och scenrutan står här, inte hela
       plåtbilden: en plåt är ett par hundra pixlar av arket, och att dra i
       den ska fortfarande panorera.

       Och `.gmini` av samma skäl: mini-chatten ligger över duken, och utan den
       här raden åt panoreringen klicket på dess knapp och dess textfält. */
    if (e.target.closest('.gpin,.gfab,.gpanel,.gmini,.aprick,.prplatfot,.prscen')) return;
    e.preventDefault();
    const val = window.getSelection && window.getSelection();
    if (val && !val.isCollapsed) val.removeAllRanges();
    drar = { x: e.clientX - vy.x, y: e.clientY - vy.y };
    duk.setPointerCapture(e.pointerId);
    duk.dataset.drar = '';
  });
  duk.addEventListener('pointermove', e => {
    if (!drar) return;
    vy.x = e.clientX - drar.x;
    vy.y = e.clientY - drar.y;
    satVy();
  });
  const slut = () => { drar = null; duk.removeAttribute('data-drar'); };
  duk.addEventListener('pointerup', slut);
  duk.addEventListener('pointercancel', slut);
  duk.addEventListener('wheel', e => {
    e.preventDefault();
    if (e.ctrlKey || Math.abs(e.deltaY) > 12) zooma(e.deltaY < 0 ? 1.12 : 1 / 1.12, e.clientX, e.clientY);
    else { vy.x -= e.deltaX; vy.y -= e.deltaY; satVy(); }
  }, { passive: false });
  $('[data-z="in"]').addEventListener('click', () => zooma(1.2));
  $('[data-z="ut"]').addEventListener('click', () => zooma(1 / 1.2));
  lagen.forEach(b => b.addEventListener('click', () => { satLage(b.dataset.z); passa(b.dataset.z); }));

  /* ── elementval och chatt ── */
  const etikett = el => el.dataset.namn || 'Element';
  /* ── URVALET ───────────────────────────────────────
     Flera rutor, i den ordning läraren pekade på dem. Förr var det EN ruta och
     ett klick ersatte den — men önskemålen kommer sällan en ruta i taget. «Gör
     3 och 5 kortare» blev två varv, två väntor, och två chanser för det andra
     varvet att skriva om det förstas grund. Nu VÄXLAR klicket rutan i urvalet:
     ingen modifierartangent, för läraren sitter ofta med pekplatta. */
  let malen = [];
  /* Sex är taket, och det är en promptbudget snarare än en teknisk gräns: varje
     mål bär både sin JSON-text och sin renderade bild, och tio rutor lämnar
     inget utrymme åt själva önskemålet. */
  const MAXMAL = 6;

  function satValj(pa) {
    valjLage = pa;
    skal.toggleAttribute('data-valj', pa);
    $('#g-valj').setAttribute('aria-pressed', String(pa));
    $('#g-valjtext').textContent = pa ? 'Klicka på det du vill ändra' : 'Välj element';
    /* Mini-chatten hör till väljläget: slås det av är rutan inte längre vald
       på ett sätt som går att skriva om. */
    satMini();
  }
  $('#g-valj').addEventListener('click', () => satValj(!valjLage));

  /* Utan valt element gäller ändringen ARKET man tittar på, inte «dokumentet»:
     provet och lösningsförslaget är två ark i samma canvas, och en ändring i det
     ena är sällan en ändring i det andra. */
  /* Arkets namn, uppslaget på INDEX och inte på vilken flik som råkar vara
     nedtryckt: en köad post bär arket den skrevs på, och hann läraren byta flik
     medan den låg i kön ska raden ändå heta det arket den gäller. */
  function arkNamnFor(i) {
    const a = $('#g-arkval');
    if (!a || a.hidden) return 'Hela dokumentet';
    const b = $$('button', a)[i || 0];
    return b ? b.textContent.trim() : 'Hela dokumentet';
  }
  const arkNamn = () => arkNamnFor(arkIndex());
  /* VILKET ark som ligger framme, som index. Ett dokument utan växlare har
     bara ett ark och är alltid 0. Nålarna, diffen och ögonblicksbilderna
     stämplas med det: uppgiftsarket och facitarket bär SAMMA element-id:n
     (uppg3 finns på båda), så utan arknumret hamnade nål 1 — satt på uppgift 3
     — på facits uppgift 3 så fort läraren bytte flik, och diffen jämförde
     provets text med lösningsförslagets. */
  function arkIndex() {
    const a = $('#g-arkval');
    if (!a || a.hidden) return 0;
    const knappar = $$('button', a);
    const i = knappar.findIndex(b => b.getAttribute('aria-pressed') === 'true');
    return i < 0 ? 0 : i;
  }
  /* «Lösningsförslag» blir «lösningsförslaget» i en mening — arkets etikett är
     en flik, frågan i fältet är svenska. */
  const BEST = { 'hela dokumentet': 'dokumentet', 'lösningsförslag': 'lösningsförslaget',
    'bedömningsanvisning': 'bedömningsanvisningen', 'provet': 'provet' };
  const bestamd = namn => { const n = String(namn || '').toLowerCase(); return BEST[n] || n; };
  /* Namnet räcker för läraren men inte för modellen: «Formel 3» och «Uppgift B»
     står ingenstans i dokumentet den skriver om. Innehållet gör det — det är
     det enda som pekar ut elementet i JSON:en. Kapat, för ett block kan vara
     långt och prompten har annat att bära. */
  const innehall = el => (el.dataset.text || el.textContent || '')
    .replace(/\s+/g, ' ').trim().slice(0, 300);
  /* Rutans text SÅ SOM DEN STÅR PÅ SKÄRMEN, oförkortat av `data-text`. Den
     skiljer sig från JSON:en på ett sätt som betyder något: KaTeX lämnar kvar
     sin LaTeX-källa i en MathML-annotation, så en satt formel står här två
     gånger — och det är DEN bilden läraren beskriver när hon skriver «det står
     ett dollartecken mitt i raden». Går med som `mal.renderat`. */
  const renderat = el => (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 600);
  /* Ett mål så som det ser ut i urvalet och i kroppen till servern. */
  const malAv = el => ({ el: el.dataset.el, namn: etikett(el), text: innehall(el),
                         renderat: renderat(el) });
  /* Målrutan: ett chip per vald ruta, med lärarens egen etikett och ett eget
     kryss. Med ETT val ser raden ut precis som förr — det är först vid två den
     blir en lista, och `data-flera` är det enda CSS behöver veta om saken. */
  function ritaMal() {
    satSnabb(!!malen.length);
    const ruta = $('#g-mal'), chips = $('#g-malchips');
    chips.innerHTML = '';
    if (!malen.length) {
      const t = document.createElement('span');
      t.className = 'gmaltext';
      t.textContent = arkNamn();
      chips.appendChild(t);
    } else malen.forEach(m => {
      const c = document.createElement('span');
      c.className = 'gmalchip';
      c.innerHTML = '<span class="gmaltext"></span><button class="gmalkryss" type="button">✕</button>';
      $('.gmaltext', c).textContent = m.namn;
      const x = $('.gmalkryss', c);
      x.setAttribute('aria-label', `Ta bort ${m.namn} ur urvalet`);
      x.addEventListener('click', () => taBortMal(m.el));
      chips.appendChild(c);
    });
    ruta.toggleAttribute('data-satt', !!malen.length);
    ruta.toggleAttribute('data-flera', malen.length > 1);
    $('#g-malx').hidden = !malen.length;
    markeraMalen();
    /* Arkbytet går också här (nollaMal) — svepet hör till sitt ark och ska
       släckas när det andra ligger framme. */
    markeraArbete();
    /* Ny ruta, ny mening: en halvskriven mini-chatt hörde till den förra. */
    stangMini(false);
    satMini();
    /* Placeholdern går genom skrivläget och inte förbi det: går ett varv, eller
       väntar en kö, är det «Skriv nästa — läggs i kö» som gäller — inte frågan
       om urvalet. */
    ritaFalt();
    $('#g-falt').focus({ preventScroll: true });
  }
  /* `[data-mal]` på ALLA valda rutor — CSS:en är densamma som när det bara
     kunde vara en. */
  const markeraMalen = () => $$('.gdok [data-el]', plan).forEach(x =>
    x.toggleAttribute('data-mal', malen.some(m => m.el === x.dataset.el)));

  /* ── VÄNTAN SOM SYNS ───────────────────────────────
     Urvalet nollställs så fort meningen gått i väg (se skicka), och därmed
     slocknade också markeringen: i de minuter en omskrivning tar såg pappret
     orört ut, och den enda upplysningen om att något pågick stod i panelen
     längst bort till höger. `arbetar` håller kvar VILKA rutor varvet gäller
     tills patchen landat, och de får ett svep över sig så länge. */
  let arbetar = null;
  const satArbete = (elen, ark) => { arbetar = { elen: elen.slice(), ark: ark || 0 }; markeraArbete(); };
  const slappArbete = () => { arbetar = null; markeraArbete(); };
  /* Svepet är ett eget BARN till rutan och inte ett `::after`: väljläget har
     redan tagit pseudoelementet till sin etikett (app2.css), och bladen sätter
     egna på sina rutor. Ritas om efter varje omritning — omritningen slänger
     hela klonen med allt som hängde i den. */
  function markeraArbete() {
    $$('.gshimmer', plan).forEach(s => s.remove());
    if (!arbetar || arbetar.ark !== arkIndex()) return;
    arbetar.elen.forEach(id => $$(`.gdok [data-el="${id}"]`, plan).forEach(el => {
      const s = document.createElement('span');
      s.className = 'gshimmer';
      el.appendChild(s);
    }));
  }
  /* ── OMRITNINGAR VI INTE BAD OM ────────────────────
     Tavlan ritar om sig själv när den blivit mätbar (blad.js nar()), en stund
     efter att canvasen öppnats — och den omritningen slänger rutorna med
     markeringarna i. Klickade läraren på ett element strax innan slocknade
     urvalet i pappret utan att någon rört det, och svepet hade gjort samma sak
     mitt under ett varv. Vakten sätter tillbaka det granskningen äger.
     Våra EGNA barn (nålar och svep) räknas inte som en omritning — annars hade
     markeraArbete väckt vakten som väckte markeraArbete, bildruta efter
     bildruta. */
  let atersatt = 0;
  const varEgen = m => [...m.addedNodes, ...m.removedNodes].every(n =>
    n.nodeType === 1 && (n.classList.contains('gpin') || n.classList.contains('gshimmer')));
  if (typeof MutationObserver === 'function') {
    new MutationObserver(muts => {
      if (atersatt || skal.hidden) return;
      if (muts.every(m => m.type !== 'childList' || varEgen(m))) return;
      atersatt = requestAnimationFrame(() => {
        atersatt = 0;
        if (skal.hidden) return;
        markeraMalen();
        markeraArbete();
      });
    }).observe(plan, { childList: true, subtree: true });
  }
  /* ── BLINKEN PÅ DET SOM FAKTISKT ÄNDRADES ──────────
     Serverns `andrade` är den ärliga listan (app/dokumentdiff.py), samma som
     nålarna och kortet går på. Blinken hängs på OMRITNINGEN och inte på svaret:
     arket ritas om HELT (plan.js iterera → visa → Blad.rita tömmer värden), och
     en markering satt före det hade slängts med klonen. Kommer ingen omritning
     — servern ändrade inget, eller pappret är prototypens — blinkar vi ändå,
     på det som ligger framme, när väntan gått ut. */
  let vantarBlink = null, blinkade = [];
  function armeraBlink(idn, ark) {
    if (!idn || !idn.length) return;
    const mitt = vantarBlink = { idn: idn.slice(), ark: ark || 0 };
    setTimeout(() => { if (vantarBlink === mitt) blinkaNu(); }, 700);
  }
  function blinkaNu() {
    const b = vantarBlink;
    vantarBlink = null;
    /* Fel ark framme? Provet och lösningsförslaget bär samma id:n, och en blink
       där hade lyst upp en ruta ingen skrev om. */
    if (!b || b.ark !== arkIndex()) return;
    blinkade = b.idn.slice();
    b.idn.forEach(id => $$(`.gdok [data-el="${id}"]`, plan).forEach(el => {
      el.setAttribute('data-blink', '');
      setTimeout(() => el.removeAttribute('data-blink'), 1600);
    }));
  }
  const taBortMal = id => { malen = malen.filter(m => m.el !== id); ritaMal(); };
  const nollaMal = () => { malen = []; ritaMal(); };
  function vaxlaMal(el) {
    const id = el.dataset.el;
    if (malen.some(m => m.el === id)) return taBortMal(id);
    /* Taket sägs, det tigs inte bort: ett klick som inte gör något är ett fel
       läraren letar efter i sin egen hand. */
    if (malen.length >= MAXMAL) {
      window.toast && window.toast(`${MAXMAL} rutor är taket — ta bort en först.`);
      return;
    }
    malen.push(malAv(el));
    ritaMal();
  }
  /* Frågan i fältet, på ett ställe: målrutan sätter den när valet ändras, och
     skrivläget nedan sätter tillbaka den när kön är tom. Flera val räknas upp
     på svenska («Vad ska ändras i uppgift 3 och uppgift 5?») med samma
     uppräkning och samma bestämda former som svaren i tråden använder. */
  const faltPlaceholder = () =>
    `Vad ska ändras i ${malen.length ? raknaUpp(malen.map(m => bestamd(m.namn)))
                                     : bestamd(arkNamn())}?`;
  /* ── KÖN, I STÄLLET FÖR ETT LÅS ────────────────────
     Här stod ett lås: fältet gick i disabled medan varvet gick, med
     motiveringen att lärarens nästa mening annars skrivs mot ett papper hon
     inte sett. Det var sant om meningen SKICKATS med en gång — men det är inte
     det som händer nu. Posten läggs i kö, och när den avfyras läses målens
     innehåll OM ur färska dokumentet (se korOnskan): meningen möter alltså
     pappret som det ser ut när den skickas, inte som det såg ut när den skrevs.
     Och ångra/gör om är låsta så länge något står i kön, så basen under den kan
     inte dras undan.
     Parallellt vore fel form av samma skäl som förut: servern låser per
     dokument och versionerar optimistiskt, så av två varv mot samma papper kan
     bara det ena sparas. Kön är den ärliga formen. */
  function satSkickar(pa) { skickarNu = !!pa; ritaSkrivlage(); }
  /* Varvet är över — hur det än slutade. Historikens knappar släpps HELT ett
     ögonblick, så att plan.js (ritaHistorik) hinner räkna om deras eget läge
     innan nästa post ur kön låser dem igen med rätt värde sparat. */
  function varvetOver() { skickarNu = false; slappHistorik(); slappArbete(); ritaFalt(); }
  function ritaSkrivlage() { ritaFalt(); satHistoriklas(); }
  function ritaFalt() {
    const koar = skickarNu || ko.length > 0;
    const form = $('#g-form');
    if (form) form.toggleAttribute('data-vantar', skickarNu);
    const f = $('#g-falt');
    if (f) {
      /* ALDRIG disabled. En låst ruta är en tanke som tappas bort. */
      f.disabled = false;
      f.placeholder = koar ? 'Skriv nästa — läggs i kö' : faltPlaceholder();
    }
    const knapp = form && $('button[type="submit"]', form);
    if (knapp) {
      knapp.disabled = false;
      knapp.textContent = koar ? 'Lägg i kö' : 'Ändra';
    }
    $$('.gsnabbknapp').forEach(b => { b.disabled = false; });
  }
  /* Ångra/gör om är låsta så länge det finns något som ska skrivas — ett varv
     som går ELLER en kö som väntar. Backar läraren mitt i byggs nästa post på
     en bas hon just kastat: servern skriver om den version som ligger framme
     när posten avfyras, inte den hon såg när hon skrev meningen.
     Knapparnas EGET läge (plan.js vet om det finns något att ångra) sparas
     undan medan låset sitter och lämnas tillbaka efteråt. */
  function satHistoriklas() {
    if (!(skickarNu || ko.length)) return slappHistorik();
    ['#g-angra', '#g-gorom'].forEach(id => {
      const b = $(id);
      if (!b) return;
      /* Bara FÖRSTA låsningen sparar undan läget — kön låser om och om igen,
         och en andra sparning hade sparat vårt eget lås. */
      if (b.dataset.lastVarv === undefined) b.dataset.lastVarv = b.disabled ? '' : '1';
      b.disabled = true;
    });
  }
  function slappHistorik() {
    ['#g-angra', '#g-gorom'].forEach(id => {
      const b = $(id);
      if (!b || b.dataset.lastVarv === undefined) return;
      b.disabled = b.dataset.lastVarv !== '1';
      delete b.dataset.lastVarv;
    });
  }
  /* ── SNABBKNAPPARNA ───────────────────────────────────────
     Fyra ändringar återkommer i nästan varje granskning, och de skrevs för hand
     varje gång. Knapparna skriver meningen åt läraren — och skickar den GENOM
     SAMMA `skicka()` som formuläret. Ingen egen kodväg och ingen egen prompt:
     en snabbknapp som gick en genväg hade blivit en andra sanning att hålla i
     takt med fritexten.

     Meningarna är skrivna som läraren själv hade sagt dem, och de står i
     fältet ett ögonblick innan de skickas — hon ska se vad som gick i väg och
     kunna känna igen den i tråden efteråt. */
  const SNABBA = [
    ['Kortare', 'Gör den kortare — samma innehåll, färre ord.'],
    ['Enklare', 'Gör den enklare — samma sak, men på en nivå som fler hänger med på.'],
    ['Svårare', 'Gör den svårare — höj kravet ett steg utan att byta ämne.'],
    ['Byt sammanhang', 'Byt sammanhang — samma matematik, men i en annan situation.'],
  ];
  const snabbrad = $('#g-snabb');
  if (snabbrad) {
    SNABBA.forEach(([namn, mening]) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'gsnabbknapp';
      b.textContent = namn;
      b.addEventListener('click', () => {
        const f = $('#g-falt');
        f.value = mening;
        skicka(mening);
        f.value = '';
        f.style.height = 'auto';
      });
      snabbrad.appendChild(b);
    });
  }
  /* Bara när ett element är valt: «Kortare» om hela pappret är inte en
     snabbändring, det är en omskrivning. */
  function satSnabb(pa) {
    if (snabbrad) snabbrad.hidden = !pa;
  }
  $('#g-malx').addEventListener('click', () => nollaMal());
  plan.addEventListener('click', e => {
    if (!valjLage) return;
    const el = e.target.closest('[data-el]');
    if (!el) return;
    e.stopPropagation();
    /* Klicket VÄXLAR: en ny ruta läggs till urvalet, samma ruta igen betyder
       «inte den här heller». Utan växlingen satt markeringen kvar hur mycket
       man än klickade, och enda vägen ur den var krysset i målrutan — som man
       ska behöva hitta först. */
    vaxlaMal(el);
  });

  /* en nål per skickad ändring, numrerad i trådens ordning — och bara på det
     ark den hör till (se arkIndex) */
  function satNal(elId, n, ark) {
    if ((ark || 0) !== arkIndex()) return;
    /* ALLA förekomster: facit-i-bladet delar id med sin uppgift med flit
       (blad.js), och en nål bara på den första lämnade facitets ändring
       omärkt. */
    $$(`[data-el="${elId}"]`, plan).forEach(el => {
      const pin = document.createElement('span');
      pin.className = 'gpin';
      pin.dataset.id = String(n);
      pin.textContent = String(n);
      pin.style.transform = `translate(-50%,-50%) scale(${1 / vy.z})`;
      pin.addEventListener('click', ev => { ev.stopPropagation(); fokusera(n); });
      el.appendChild(pin);
    });
  }
  const markera = (elId, pa) => {
    if (!elId) return;
    $$(`[data-el="${elId}"]`, plan).forEach(el => el.toggleAttribute('data-pekad', pa));
  };
  function fokusera(n) {
    const post = kommentarer.find(k => k.id === n);
    if (!post) return;
    $$('.gvarv', lista).forEach(v => v.toggleAttribute('data-pa', Number(v.dataset.id) === n));
    $$('.gpin', plan).forEach(p => p.toggleAttribute('data-pa', Number(p.dataset.id) === n));
    const v = $(`.gvarv[data-id="${n}"]`, lista);
    if (v) (window.rullaLada || ((b, y) => { b.scrollTop = y; }))(lista, v.offsetTop - 40);
  }

  /* Före och efter. Att godkänna en ändring utan att se exakt vad som blev annorlunda
     tvingar en att läsa om hela uppgiften — diffen står därför i ändringsposten. */
  const platt = n => n.textContent.replace(/\s+/g, ' ').trim();
  /* Senaste varvets före/efter, per element-id. Prickarna i pappret läser den
     här (window.Granska.diffFor) i stället för att hålla en egen kopia som kan
     säga emot panelen. Nollställs när canvasen öppnas på ett nytt papper. */
  let senaste = { varv: 0, ark: 0, par: {} };
  const kapa = s => s.length > 160 ? s.slice(0, 159) + '…' : s;
  function ogonblick() {
    const m = {};
    $$('.gdok [data-el]', plan).forEach(n => { m[n.dataset.el] = platt(n); });
    return m;
  }
  /* En diff som visar samma text två gånger är ingen diff — den får läraren att
     tro att något ändrats som inte gjort det. Bara verkliga skillnader står kvar. */
  function ritaDiff(varv, fore, efter, andrade, ark) {
    andrade = andrade.filter(id => (fore[id] || '').trim() !== (efter[id] || '').trim());
    if (!andrade.length) return;
    if ($('.gdiff', varv)) return;
    /* SAMMA par som rutan nedan ritar — prickarna i pappret visar dem i sin
       popover, och de får inte kunna säga något annat än panelen. Sparas här,
       där paret först finns, i stället för att räknas fram en gång till. */
    senaste = { varv: Number(varv.dataset.id) || 0, ark: ark || 0, par: {} };
    andrade.forEach(id => {
      senaste.par[id] = { fore: kapa(fore[id] || ''), efter: kapa(efter[id] || '') };
    });
    const d = document.createElement('div');
    d.className = 'gdiff';
    andrade.slice(0, 2).forEach(id => {
      const p = document.createElement('p');
      p.style.margin = '0';
      /* Vilken ruta paret gäller — «Ändrade delar»-kortet ovanför pekar hit,
         och utan id:t hade det bara kunnat peka på diffen som helhet. */
      p.dataset.el = id;
      p.innerHTML = '<span class="gfore"></span><span class="gefter"></span>';
      $('.gfore', p).textContent = kapa(fore[id]);
      $('.gefter', p).textContent = kapa(efter[id]);
      d.appendChild(p);
    });
    if (andrade.length > 2) {
      const s = document.createElement('p');
      s.className = 'gdifford';
      s.style.margin = '8px 0 0';
      s.textContent = `· ${andrade.length - 2} till ändrade`;
      d.appendChild(s);
    }
    varv.appendChild(d);
  }
  function vantaDiff(varv, fore, n, ark) {
    /* Ögonblicksbilden togs på ETT ark. Bytte läraren flik medan varvet gick
       hade «före» varit provets rutor och «efter» facitets — en diff som visar
       två olika papper och kallar skillnaden en ändring. Då är det bättre att
       inte visa någon diff alls. */
    if (arkIndex() !== (ark || 0)) return;
    const efter = ogonblick();
    /* Ett element som HADE text och nu är tomt är nästan alltid en halvritad
       tavla, inte en ändring: motorn tömmer sin värd och ritar om, och en
       ögonblicksbild tagen mitt i det gav «före: hela rubriken / efter: (tomt)»
       — en diff som ser ut som en radering av något som står kvar på skärmen.
       Vänta i stället ut ritningen; är elementet borta på riktigt försvinner
       också dess data-el, och då står det inte kvar i `efter` alls. */
    const andrade = Object.keys(efter).filter(id =>
      fore[id] !== undefined
      && (fore[id] || '').trim() !== (efter[id] || '').trim()
      && !((fore[id] || '').trim() && !(efter[id] || '').trim()));
    if (andrade.length) return ritaDiff(varv, fore, efter, andrade, ark);
    if ((n || 0) > 40) return;
    requestAnimationFrame(() => vantaDiff(varv, fore, (n || 0) + 1, ark));
  }

  /* ── Underlaget som kontext ─────────────────────────
     Dokumentet skrevs ur något: transkriptet, boken, foton av sidorna, papper
     från lektionen. Det följer med hit — dels för att man ska SE vad modellen
     redan har i handen, dels för att viktningen hör hit och inte till ett
     reglage i planeringen: ett klick på en källa börjar meningen «Ta mer ur
     boken …», och resten skriver man själv. */
  const BEST_KALLA = {
    lektion: 'lektionen', boken: 'boken', foton: 'fotona av sidorna',
    förlaga: 'förlagan', 'från lektionen': 'materialet från lektionen'
  };
  function ritaUnderlag() {
    const box = $('#g-underlag'), ut = $('#g-kallor');
    if (!box || !ut) return;
    const kallor = [...document.querySelectorAll('#kvittoextra .krad')].map(r => ({
      art: ($('.kart', r) || {}).textContent ? $('.kart', r).textContent.trim() : '',
      titel: ($('.ktext b', r) || {}).textContent ? $('.ktext b', r).textContent.trim() : '',
      detalj: ($('.ktext span', r) || {}).textContent ? $('.ktext span', r).textContent.trim() : ''
    })).filter(k => k.titel);
    ut.innerHTML = '';
    box.hidden = !kallor.length;
    if (!kallor.length) return;
    kallor.forEach(k => {
      const namn = BEST_KALLA[k.art.toLowerCase()] || k.art.toLowerCase();
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'gkalla';
      b.innerHTML = '<b></b><span></span>';
      $('b', b).textContent = k.art;
      $('span', b).textContent = k.titel;
      b.dataset.tip = `${k.titel}${k.detalj ? ' — ' + k.detalj : ''}`;
      b.addEventListener('click', () => {
        const f = $('#g-falt');
        const bit = `mer ur ${namn}`;
        if (!f.value.toLowerCase().includes(bit)) {
          f.value = f.value.trim() ? `${f.value.trim()} och ${bit}` : `Ta ${bit} — `;
        }
        f.focus();
        f.setSelectionRange(f.value.length, f.value.length);
        f.dispatchEvent(new Event('input'));
      });
      ut.appendChild(b);
    });
  }

  /* Elementets namn så som det står i pappret — samma etikett läraren ser i
     målrutan. Läses ur canvasens klon, och den är fortfarande den gamla när
     svaret skrivs: fraga.js kör `svar` FÖRE `efterKlar`, alltså före
     omritningen. Hittas inget namn svarar vi tomt hellre än «uppg3». */
  function namnFor(id) {
    const el = $(`.gdok [data-el="${id}"]`, plan);
    const n = el && el.dataset.namn;
    return n ? n.toLowerCase() : '';
  }
  /* «sidhuvudet, uppgift B och namnraderna» — en uppräkning på svenska, inte en
     lista med id:n. Fler än tre blir «med flera»: meningen ska gå att läsa. */
  function raknaUpp(namn) {
    const n = namn.slice(0, 3);
    const svans = namn.length > 3 ? ' med flera' : '';
    if (n.length === 1) return n[0] + svans;
    return n.slice(0, -1).join(', ') + ' och ' + n[n.length - 1] + svans;
  }
  /* SKÄLET, när servern FÄLLDE begäran. Reparationsloopen validerar varje varv
     (exam_spec.validate_balance), och en del önskemål kan den inte gå med på:
     «ta bort poängen från uppgift 3» faller på regeln att varje uppgift måste
     ge minst en poäng, dokumentet lämnas orört och `andrade` blir tom. «Ingenting
     på pappret ändrades» är då sant men till ingen hjälp — läraren vet inte om
     modellen missförstod henne eller om det var förbjudet, och det avgör om hon
     ska skriva om meningen eller släppa det. Skälet står redan i `errors`, i
     klartext; det ska bara sägas. */
  function skalet(res) {
    const fel = (res && Array.isArray(res.errors) ? res.errors : [])
      .map(f => String((f && f.message) || '').trim()).filter(Boolean);
    if (!fel.length) return '';
    /* Ett skäl räcker. Fem rader felmeddelanden i en chattbubbla läses inte, och
       det första är det som fällde begäran. */
    const ett = fel[0];
    return ett.charAt(0).toLowerCase() + ett.slice(1);
  }
  /* Vad panelen SÄGER att som hände, byggt ur serverns diff. Se kommentaren
     vid `svar:` nedan — det här är hela poängen med den. */
  function svarText(post, res) {
    const gjort = `Skrivet om. ${post.namn} följer nu ”${post.text}” — ändringen är markerad i pappret.`;
    /* `Array.isArray` och inte sanningsvärde: en TOM lista är ett svar
       («ingenting på pappret ändrades»), inte ett saknat fält. Samma regel som
       plan.js iterera följer när den avgör vilka rutor som märks. */
    const sagt = res && Array.isArray(res.andrade) ? res.andrade : null;
    if (!sagt) return gjort;
    if (!sagt.length) {
      const skal = skalet(res);
      return skal
        ? `Ingenting på pappret ändrades: ${skal} ${post.namn} står alltså kvar som förut — formulera om önskemålet, eller låt det stå.`
        : `Ingenting på pappret ändrades. ${post.namn} står kvar som förut — säg gärna vad som ska stå i stället, eller peka på en annan del av pappret.`;
    }
    /* NÅGOT av målen räcker: pekade läraren på tre rutor och servern skrev om
       en av dem är önskemålet uppfyllt i den mån det gick, och «ingenting av
       ditt ändrades» hade varit fel besked. */
    if (!post.elen.length || post.elen.some(id => sagt.includes(id))) return gjort;
    /* Servern ändrade något — men inte det läraren pekade på. Då är det den
       skillnaden som är beskedet, och inget annat. */
    const namn = [...new Set(sagt.map(namnFor).filter(Boolean))];
    return namn.length
      ? `${post.namn} står kvar oförändrad. Det som ändrades var ${raknaUpp(namn)} — markerat i pappret.`
      : `${post.namn} står kvar oförändrad. Något annat på pappret skrevs om i stället, och det är markerat.`;
  }

  /* Etiketten SÅ SOM DEN STÅR, till skillnad från namnFor ovan som svarar i
     gemener åt meningarna i tråden. Kortet nedan sätter namn på knappar, och
     där ska det stå «Uppgift 3» precis som i målchipsen. */
  const namnRakt = id => {
    const el = $(`.gdok [data-el="${id}"]`, plan);
    return (el && el.dataset.namn) || '';
  };
  /* ── ÄNDRADE DELAR ─────────────────────────────────
     Ett varv säger i dag i löpande text vad som hände, och blir det tre rutor
     drunknar de i meningen. Kortet räknar upp dem — ur SAMMA `andrade` som
     nålarna och blinken går på, alltså serverns ärliga diff och inte en
     avläsning av önskemålet. Varje del är en knapp: finns dess före/efter i
     varvets diff lyser paret upp där, annars panoreras pappret till rutan. */
  function ritaAndradeKort(varv, post, sagt) {
    if (!sagt || !sagt.length) return;
    const kort = document.createElement('div');
    kort.className = 'gandrade';
    kort.innerHTML = '<span class="gandradehuv"></span><div class="gandradelista"></div>';
    $('.gandradehuv', kort).textContent = sagt.length === 1
      ? '1 del ändrades' : `${sagt.length} delar ändrades`;
    const ut = $('.gandradelista', kort);
    sagt.forEach(id => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'gandradedel';
      b.dataset.el = id;
      /* Hittas ingen etikett står id:t kvar hellre än ingenting: en tom knapp
         är sämre än en knapp som heter «forsatt». */
      b.textContent = namnRakt(id) || id;
      b.addEventListener('click', ev => { ev.stopPropagation(); visaDel(varv, id, post.ark); });
      ut.appendChild(b);
    });
    varv.appendChild(kort);
  }
  function visaDel(varv, id, ark) {
    const rad = $(`.gdiff p[data-el="${id}"]`, varv);
    if (rad) {
      $$('.gdiff p[data-lyst]', lista).forEach(p => p.removeAttribute('data-lyst'));
      rad.setAttribute('data-lyst', '');
      (window.rullaLada || ((b, y) => { b.scrollTop = y; }))(lista, varv.offsetTop - 40);
      setTimeout(() => rad.removeAttribute('data-lyst'), 1800);
      return;
    }
    visaElement(id, ark);
  }
  /* Panorera fram en ruta. Duken har ingen scroll — pappret flyttas med
     `vy`-transformen — så vägen dit är en förskjutning och inte scrollIntoView. */
  function visaElement(id, ark) {
    if ((ark || 0) !== arkIndex()) {
      window.toast && window.toast('Den rutan ligger på det andra arket.');
      return;
    }
    const el = $(`.gdok [data-el="${id}"]`, plan);
    if (!el) return;
    const r = duk.getBoundingClientRect(), b = el.getBoundingClientRect();
    vy.x += (r.left + r.width / 2) - (b.left + b.width / 2);
    vy.y += (r.top + r.height / 2) - (b.top + b.height / 2);
    satLage(null);
    satVy();
    markera(id, true);
    setTimeout(() => markera(id, false), 1400);
  }
  /* ── «FUNKADE INTE» ────────────────────────────────
     Blev varvet inte som läraren tänkt är omtaget en mening hon inte ska behöva
     skriva en gång till: samma rutor, samma önskan, plus det servern själv sa
     om varför det inte gick. Går genom KÖN som allt annat — ett varv i luften
     åt gången, och står något redan där hamnar omtaget bakom det. */
  function omtagText(post, res) {
    /* Serverns egna meningar slutar med punkt, fallbacken gör det inte —
       och en mening som glider ihop med nästa läser modellen som en enda. */
    const fel = skalet(res) || 'resultatet blev inte som önskat';
    return `${post.text}\n\nDet förra försöket gick fel: ${fel}${/[.!?]$/.test(fel) ? '' : '.'}`
      + ' Gör om ändringen, den här gången så att önskemålet uppfylls.';
  }
  function ritaOmtag(varv, post, res) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'gomtag';
    b.textContent = 'Funkade inte';
    b.addEventListener('click', ev => {
      ev.stopPropagation();
      /* Ett omtag per varv: klickas knappen två gånger står samma mening två
         gånger i kön. Misslyckas omtaget får DET varvet sin egen knapp. */
      b.disabled = true;
      kosatt({ text: omtagText(post, res), ark: post.ark,
               mal: post.malen.map(m => Object.assign({}, m)) });
    });
    varv.appendChild(b);
  }

  /* Vad varvet HETER — i tråden, i jobbtexten och i svaren: rutornas egna
     etiketter, uppräknade på svenska. Utan valda rutor är det arket som gäller,
     och det slås upp på postens eget ark (se arkNamnFor). */
  const malNamn = (mal, ark) => mal.length ? raknaUpp(mal.map(m => m.namn)) : arkNamnFor(ark);

  /* ── EN POST BLIR TILL ──────────────────────────────
     Vad posten bär med sig: meningen, målens id och etiketter, och arket de
     valdes på. Innehållet står med flit inte här — det läses om när posten
     avfyras (korOnskan). Texten som fångades när läraren skrev meningen följer
     ändå med som reserv, för det enda fall där avläsningen inte går att lita
     på: att hon hunnit byta ark. */
  function skicka(text) {
    if (!text.trim()) return;
    const onskan = { text: text.trim(), ark: arkIndex(),
                     mal: malen.map(m => Object.assign({}, m)) };
    /* Urvalet nollställs så fort meningen är avskickad — nästa klick och nästa
       mening börjar rent, precis som förut. */
    nollaMal();
    kosatt(onskan);
  }
  /* Går ett varv, eller står redan något i kön? Då bakom det. FIFO: läraren
     skrev meningarna i en ordning, och den ordningen är hennes. Egen funktion
     för att «Funkade inte» går samma väg — ett omtag är en post som alla
     andra. */
  function kosatt(onskan) {
    if (skickarNu || ko.length) return koa(onskan);
    korOnskan(onskan);
  }

  /* Raden i tråden. Byggs EN gång — en köad post och det varv den blir är samma
     rad, den dubbleras inte när turen kommer. */
  function nyRad(onskan) {
    const rad = document.createElement('div');
    rad.className = 'gvarv';
    rad.innerHTML = '<div class="gvarvhuvud"></div><p class="gfraga"></p><div class="gsvar"></div>';
    $('.gfraga', rad).textContent = onskan.text;
    const tom = $('#g-tom');
    if (tom) tom.hidden = true;
    lista.appendChild(rad);
    onskan.rad = rad;
    (window.rullaLada || ((b, y) => { b.scrollTop = y; }))(lista, lista.scrollHeight);
    return rad;
  }
  /* En köad post syns MED EN GÅNG: en dämpad rad med sitt läge i stället för
     ett nummer. Numret får den när den avfyras, för det är då den blir en
     ändring — och först då räknas den i «3 ändringar». */
  function koa(onskan) {
    const rad = nyRad(onskan);
    rad.setAttribute('data-i-ko', '');
    $('.gvarvhuvud', rad).innerHTML = '<span class="gkonot">I kö</span><span class="gvarvel"></span><button class="gkokryss" type="button" aria-label="Ta bort ur kön">✕</button>';
    $('.gvarvel', rad).textContent = malNamn(onskan.mal, onskan.ark);
    $('.gkokryss', rad).addEventListener('click', ev => { ev.stopPropagation(); taUrKo(onskan); });
    /* Klick på raden lägger tillbaka meningen — OCH urvalet — i skrivrutan och
       tar posten ur kön: redigera och skicka om. Att bara lämna tillbaka texten
       hade tappat rutorna hon pekat ut, och nästa Enter hade gällt hela arket i
       stället utan att någon sagt det. Vakten mot `data-i-ko` behövs för att
       raden lever vidare som varvets egen rad, med sin egen klicklyssnare. */
    rad.addEventListener('click', () => {
      if (!rad.hasAttribute('data-i-ko')) return;
      taUrKo(onskan);
      aterta(onskan);
    });
    ko.push(onskan);
    ritaSkrivlage();
  }
  function taUrKo(onskan) {
    ko = ko.filter(x => x !== onskan);
    if (onskan.rad) onskan.rad.remove();
    ritaSkrivlage();
    /* Tog hon bort det enda som stod i tråden är tråden tom igen — och då ska
       raden som förklarar canvasen stå där, precis som när pappret öppnades. */
    if (!$('.gvarv', lista) && $('#g-tom')) $('#g-tom').hidden = false;
  }
  function aterta(onskan) {
    const f = $('#g-falt');
    f.value = onskan.text;
    /* Rutor som hunnit försvinna ur pappret återtas inte — de finns inte att
       peka på längre. Ligger ett ANNAT ark framme går urvalet tillbaka orört:
       arken bär samma id:n, och en kontroll här hade läst fel papper. */
    malen = (onskan.ark || 0) !== arkIndex() ? onskan.mal.slice(0, MAXMAL)
      : onskan.mal.filter(m => $(`.gdok [data-el="${m.el}"]`, plan)).slice(0, MAXMAL);
    ritaMal();
    f.style.height = 'auto';
    f.style.height = Math.min(120, f.scrollHeight) + 'px';
    f.focus({ preventScroll: true });
    f.setSelectionRange(f.value.length, f.value.length);
  }

  /* ── AVFYRNING ─────────────────────────────────────
     Här läses målen OM ur pappret. Posten kan ha legat i kö medan ett annat
     varv skrev om dokumentet, och då är texten läraren såg när hon skrev
     meningen inte längre den som står där. Id:na är stabila över omritningar
     (blad.js markera() sätter samma id varje varv), så rutan går att hitta
     igen — det är innehållet som ska hämtas på nytt. */
  function korOnskan(onskan) {
    const sammaArk = (onskan.ark || 0) === arkIndex();
    const funna = [], borta = [];
    onskan.mal.forEach(m => {
      /* Fel ark framme? Då går texten som lästes när meningen skrevs. Provet
         och lösningsförslaget bär SAMMA id:n (uppg3 finns på båda), så en
         avläsning här hade skickat facitets text som om den var provets — och
         en ruta som «saknas» hade bara saknats på fel papper. */
      if (!sammaArk) return funna.push(m);
      const el = $(`.gdok [data-el="${m.el}"]`, plan);
      if (!el) return borta.push(m);
      funna.push(malAv(el));
    });
    /* Ett mål som försvunnit droppas, men de andra går: läraren bad om något
       för var och en av rutorna, och att slänga hela önskemålet för att en av
       tre är borta är att kasta två uppfyllbara önskemål. */
    if (onskan.mal.length && !funna.length) return bortaRad(onskan, borta);
    kor(onskan, funna);
  }
  /* Alla rutorna borta — då finns önskemålet inte att uppfylla. Att skicka det
     ändå hade betytt att modellen skriver om något annat och att panelen kallar
     det gjort. Raden säger vad som hände i stället, och räknas inte som en
     ändring: ingen ändring skedde. */
  function bortaRad(onskan, borta) {
    const rad = onskan.rad || nyRad(onskan);
    rad.removeAttribute('data-i-ko');
    rad.setAttribute('data-borta', '');
    const namn = raknaUpp(borta.map(m => m.namn));
    $('.gvarvhuvud', rad).innerHTML = '<span class="gkonot">Togs bort</span><span class="gvarvel"></span>';
    $('.gvarvel', rad).textContent = namn;
    const p = document.createElement('p');
    p.className = 'gbortatext';
    p.textContent = `${namn} finns inte längre på pappret — önskemålet togs bort.`;
    $('.gsvar', rad).appendChild(p);
    (window.rullaLada || ((b, y) => { b.scrollTop = y; }))(lista, lista.scrollHeight);
    naste(null, 0);
  }
  /* Nästa post ur kön — FIFO, och först när pappret ritats om. Målen läses om
     vid avfyrningen, och en avfyrning i samma andetag som svaret hade läst den
     GAMLA texten: omritningen sker ett ögonblick senare. Samma väntan som
     diffen gör, med samma tak — ritas ingenting om (servern ändrade inget)
     skickas posten ändå. Timer och inte bildrutor: i en bakgrundsflik ritas
     inga bildrutor alls, och en kö som stannar för att läraren tittade i en
     annan flik är värre än en som skickar en aning för tidigt. */
  function naste(fore, n) {
    if (skickarNu || !ko.length) return;
    if (fore && (n || 0) < 40 && !nagotAndrat(fore)) {
      return setTimeout(() => naste(fore, (n || 0) + 1), 30);
    }
    const onskan = ko.shift();
    if (onskan.rad) onskan.rad.removeAttribute('data-i-ko');
    ritaFalt();
    korOnskan(onskan);
  }
  const nagotAndrat = fore => {
    const efter = ogonblick();
    return Object.keys(efter).some(id => fore[id] !== undefined && fore[id] !== efter[id]);
  };

  function kor(onskan, funna) {
    const fore = ogonblick(), foreArk = arkIndex();
    nr++;
    const post = { id: nr,
                   /* Vilket ARK önskemålet gällde. Provet och lösningsförslaget
                      bär samma id:n (uppg3 finns på båda), så en nål utan ark
                      hamnade på det ark som råkade ligga framme. */
                   ark: onskan.ark || 0,
                   /* `el` är FÖRSTA målet och står kvar för nålarnas och
                      hovringens skull — `elen` är alla, och det är den listan
                      koden nedan går på. */
                   el: funna.length ? funna[0].el : '',
                   elen: funna.map(m => m.el),
                   namn: malNamn(funna, onskan.ark),
                   /* Vad rutorna FAKTISKT innehåller, läst nyss. Följer med
                      till servern så att omskrivningen gäller det läraren
                      pekade på. */
                   malen: funna, text: onskan.text };
    kommentarer.push(post);
    const varv = onskan.rad || nyRad(onskan);
    varv.removeAttribute('data-i-ko');
    varv.dataset.id = String(nr);
    $('.gvarvhuvud', varv).innerHTML = '<span class="gnotnr"></span><span class="gvarvel"></span>';
    $('.gnotnr', varv).textContent = String(nr);
    $('.gvarvel', varv).textContent = post.namn;
    /* hovra ett meddelande — ALLA dess element lyser upp i pappret, men bara när
       det är deras eget ark som ligger framme */
    const pekbart = () => post.ark === arkIndex();
    varv.addEventListener('pointerenter', () => pekbart() && post.elen.forEach(id => markera(id, true)));
    varv.addEventListener('pointerleave', () => post.elen.forEach(id => markera(id, false)));
    varv.addEventListener('click', () => fokusera(post.id));
    post.elen.forEach(id => satNal(id, post.id, post.ark));
    /* Svepet över rutorna varvet gäller — se VÄNTAN SOM SYNS ovan. Urvalet är
       redan nollställt här, så markeringen kan inte bäras av `data-mal`. */
    satArbete(post.elen, post.ark);
    (window.rullaLada || ((b, y) => { b.scrollTop = y; }))(lista, lista.scrollHeight);

    window.Fraga.kor($('.gsvar', varv), {
      /* Enkelt läge: en rad medan Claude skriver, sedan svaret. Faslistan hörde
         till en modell som kördes lokalt — den finns inte att visa längre. */
      enkel: true,
      omfang: post.namn.toLowerCase(),
      jobbtext: `Skriver om ${post.namn.toLowerCase()} …`,
      /* Skrevs pappret av servern går ändringen dit — hela texten, inklusive
         det ett klick på en källa la till («Ta mer ur boken …»), är prompten.
         Annars är det prototypens omskrivning, som förut. */
      /* Varvhistoriken är trådens EGNA meningar, i ordning, och tas här och inte
         i plan.js: det är granskningen som håller samtalet. Den nya meningen är
         redan påskjuten, så den räknas bort — den står som önskemål längre ner
         i prompten och ska inte också stå som «redan gjort». */
      /* MÅLEN är en LISTA sedan flervalet — plan.js avgör formen på kroppen ur
         den: ett mål ger exakt dagens kropp (kassetterna hänger på det), flera
         ger `malen` därutöver. Tom lista = önskemålet gäller hela arket. */
      jobb: host && host.onJobb ? k => host.onJobb(post.text, post.namn, post.elen, k,
        post.malen.map(m => ({ el: m.el, namn: m.namn, innehall: m.text,
                               renderat: m.renderat })),
        kommentarer.filter(x => x.id !== post.id).map(x => x.text))
        /* Inget riktigt anrop — prototypen, eller ett papper appen skrev själv.
           Då är väntan prototypens egen, precis som förut. */
        || new Promise(r => setTimeout(r, 1400)) : null,
      /* ── ÄRLIGT SVAR ────────────────────────────────
         Raden här var en MALL som alltid skrevs: «Skrivet om. Instruktionen
         följer nu ”…” — ändringen är markerad i pappret.» Den påstod alltså
         att ändringen var gjord oavsett vad servern gjort. Läraren bad att en
         mening skulle bort ur instruktionsrutan, ingenting hände på pappret,
         och panelen svarade ändå att det var klart — det värsta en app kan
         göra, för då slutar man kontrollera.

         Servern diffar dokumentets JSON och skickar `andrade`
         (app/dokumentdiff.py). Finns listan är det den som talar, också när
         den är TOM. Saknas fältet — prototypens papper, gamla utkast,
         kassettsvar — står dagens fras kvar; den är inte sann, men det är det
         enda vi vet där, och att börja gissa åt andra hållet vore lika illa. */
      svar: res => svarText(post, res),
      efterKlar: (_el, res) => {
        /* Ordningen är inte fri. Varvet släpps FÖRST (historikens knappar får
           tillbaka sitt eget läge), sedan tillämpas svaret — då räknar plan.js
           om vad som går att ångra — och SIST går nästa post ur kön, som låser
           igen med det nyss uträknade läget sparat. */
        varvetOver();
        /* Kortet byggs FÖRE omritningen: etiketterna läses ur klonen som ligger
           framme, och den bär samma id:n som den nya (blad.js markera sätter
           dem varje varv). Blinken armeras samtidigt men avfyras först när
           omritningen landat — se armeraBlink. */
        const sagt = res && Array.isArray(res.andrade) ? res.andrade : null;
        ritaAndradeKort(varv, post, sagt);
        ritaOmtag(varv, post, res);
        armeraBlink(sagt, post.ark);
        if (host && host.onAndra) host.onAndra(post.text, post.namn, post.elen, res);
        vantaDiff(varv, fore, 0, foreArk);
        (window.rullaLada || ((b, y) => { b.scrollTop = y; }))(lista, lista.scrollHeight);
        fokusera(post.id);
        naste(fore, 0);
      },
      /* Varvet släpps oavsett hur det slutade: klart, fel eller avbrutet. En
         ruta som står låst för att servern svarade fel är ett andra fel ovanpå
         det första — och kön ska rulla vidare, för nästa önskemål kan mycket
         väl vara det som går igenom. Avbryt-knappen på det AKTIVA varvet rör
         bara det varvet; kön står kvar (kryssen tar posterna en och en). */
      efterFel: () => { varvetOver(); naste(null, 0); },
      efterStopp: () => { varvetOver(); naste(null, 0); }
    });
    satSkickar(true);
    $('#g-antal').textContent = kommentarer.length === 1 ? '1 ändring' : `${kommentarer.length} ändringar`;
  }
  $('#g-form').addEventListener('submit', e => {
    e.preventDefault();
    const f = $('#g-falt');
    skicka(f.value);
    f.value = '';
    f.style.height = 'auto';
  });
  $('#g-falt').addEventListener('input', () => {
    const f = $('#g-falt');
    f.style.height = 'auto';
    f.style.height = Math.min(120, f.scrollHeight) + 'px';
  });
  $('#g-falt').addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('#g-form').requestSubmit(); }
  });
  /* ── MINI-CHATTEN VID RUTAN ────────────────────────
     Med EXAKT en ruta vald ligger knappen vid rutan i stället för i panelen
     520 px bort: ögat står redan där, och meningen ska kunna skrivas där ögat
     är. Den skickar genom `skicka()` — samma kö, samma prompt, samma tråd. En
     egen väg hade blivit en andra sanning att hålla i takt med panelchatten.
     Flera valda rutor får ingen knapp: den hör till EN ruta, och «den här» om
     tre rutor betyder ingenting. */
  const mini = $('#g-mini'), miniform = $('#g-miniform'), minifalt = $('#g-minifalt'),
        miniknapp = $('#g-miniknapp');
  let miniBild = 0;
  const miniMal = () => (valjLage && malen.length === 1)
    ? $(`.gdok [data-el="${malen[0].el}"]`, plan) : null;
  function satMini() {
    const el = miniMal();
    if (!el) return stangMini(true);
    mini.hidden = false;
    flyttaMini(el);
    if (!miniBild) miniBild = requestAnimationFrame(foljMini);
  }
  /* Pappret panoreras och zoomas med en transform — det finns ingen
     scrollposition att lyssna på, så rutans plats mäts om varje bildruta.
     Slingan går bara så länge knappen syns. */
  function foljMini() {
    miniBild = 0;
    if (mini.hidden) return;
    const el = miniMal();
    if (!el) return stangMini(true);
    flyttaMini(el);
    miniBild = requestAnimationFrame(foljMini);
  }
  /* Helst i marginalen TILL HÖGER om rutan: ovanför lägger sig knappen över
     rutan närmast över, och den är någon annans. Ryms den inte bredvid går den
     ovanför ändå — och alltid innanför duken, för pappret kan ligga halvt
     utanför kanten och knappen får inte följa med under panelen. */
  function flyttaMini(el) {
    const r = duk.getBoundingClientRect(), b = el.getBoundingClientRect();
    const br = mini.offsetWidth || 150, h = mini.offsetHeight || 34;
    const bredvid = b.right + 12 + br <= r.right - 10;
    const klam = (v, lag, hog) => Math.round(Math.min(Math.max(v, lag), Math.max(lag, hog)));
    mini.style.left = klam(bredvid ? b.right + 12 : b.left, r.left + 10, r.right - br - 10) + 'px';
    mini.style.top = klam(bredvid ? b.top + b.height / 2 - h / 2 : b.top - h - 8,
                          r.top + 10, r.bottom - h - 10) + 'px';
  }
  /* `helt` gömmer hela knappen; utan den fälls bara fältet ihop och knappen
     står kvar — rutan är fortfarande vald. */
  function stangMini(helt) {
    if (!mini) return;
    miniform.hidden = true;
    minifalt.value = '';
    minifalt.style.height = 'auto';
    miniknapp.hidden = false;
    if (!helt) return;
    mini.hidden = true;
    if (miniBild) cancelAnimationFrame(miniBild);
    miniBild = 0;
  }
  if (mini) {
    miniknapp.addEventListener('click', ev => {
      ev.stopPropagation();
      miniknapp.hidden = true;
      miniform.hidden = false;
      flyttaMini(miniMal() || duk);
      minifalt.focus({ preventScroll: true });
    });
    miniform.addEventListener('submit', e => {
      e.preventDefault();
      const t = minifalt.value;
      if (!t.trim()) return;
      stangMini(false);
      /* `skicka` nollställer urvalet, och då gömmer ritaMal → satMini knappen
         av sig själv. Ingen egen städning här. */
      skicka(t);
    });
    minifalt.addEventListener('input', () => {
      minifalt.style.height = 'auto';
      minifalt.style.height = Math.min(88, minifalt.scrollHeight) + 'px';
    });
    minifalt.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); miniform.requestSubmit(); return; }
      /* Esc fäller ihop fältet och stänger INTE canvasen: `tangent` på
         document hade annars fått gesten och tagit hela överlägget med sig. */
      if (e.key === 'Escape') { e.stopPropagation(); stangMini(false); }
    });
  }

  /* Bilden hör till EN ruta — den läggs på ett ställe i pappret. Med flera valda
     är det den första, alltså den läraren pekade på först. */
  $('#g-bild').addEventListener('click', () => { if (host && host.onBild) host.onBild(malen.length ? malen[0].el : 'rubrik'); });

  /* ── öppna och stäng ── */
  /* Provet och lösningsförslaget är två ark av samma dokument — växlaren
     sitter i canvasens topp så man slipper stänga för att jämföra. */
  const arkval = $('#g-arkval');
  $$('button', arkval).forEach((b, j) => b.addEventListener('click', () => {
    $$('button', arkval).forEach((x, i) => x.setAttribute('aria-pressed', String(i === j)));
    if (host && host.ark && host.ark.byt) host.ark.byt(j);
    /* Byter man ark byter också det man skriver om — elementvalet hörde till
       det förra arket. */
    nollaMal();
    /* Arkbytet ritar om dokumentet, och plan.js räknar då om historikknapparna
       ur versionslistan — utan att veta om kön. Låset sätts tillbaka här. */
    satHistoriklas();
  }));
  function satArkval(ark) {
    arkval.hidden = !(ark && ark.tva);
    if (!ark || !ark.tva) return;
    $$('button', arkval).forEach((b, j) => {
      b.textContent = (ark.namn || ['Provet', 'Bedömningsanvisning'])[j];
      b.setAttribute('aria-pressed', String(j === (ark.vald || 0)));
    });
    if (!malen.length) ritaMal();
  }

  function oppna(o) {
    host = o;
    satArkval(o.ark);
    plan.innerHTML = '';
    const klon = o.nod.cloneNode(true);
    klon.classList.add('gdok');
    plan.appendChild(klon);
    /* Klonens prickar är döda knappar (cloneNode kopierar inga lyssnare) och
       dess timers blev kvar i originalet. pa() utan version läser resttiden ur
       elementens stämpel och byter prickarna mot levande (prickar.js). */
    if (window.Prickar) window.Prickar.pa(klon);
    $('#g-titel').textContent = o.titel || 'Utkast';
    $('#g-meta').textContent = o.meta || '';
    kommentarer = []; nr = 0; malen = []; senaste = { varv: 0, ark: 0, par: {} };
    /* Nytt papper: svepet och den armerade blinken hörde till det förra. */
    arbetar = null; vantarBlink = null;
    satSnabb(false);          // nytt papper, inget element valt än
    /* Nytt papper, tom kö. Ett varv som fortfarande går hör till det förra
       pappret — plan.js slänger dess svar (se sammaPapper där) — och de köade
       önskemålen gällde rutor på ett papper som inte ligger framme längre. */
    ko = [];
    satSkickar(false);
    $$('.gvarv', lista).forEach(v => v.remove());
    $('#g-tom').hidden = false;
    $('#g-antal').textContent = 'Inga ändringar än';
    ritaMal();
    satValj(false);
    ritaUnderlag();
    skal.hidden = false;
    /* Tavlan måste ritas om NÄR canvasen syns — en mätning i ett gömt överlägg
       ger nollor, och då blir tavlan en tom ruta i stället för ett papper.
       Både bildrutan och en kort timer får försöka: i en bakgrundsflik ritas
       inga bildrutor, och då öppnades canvasen förr utan att anpassa sig. */
    const efterOppning = () => {
      skal.setAttribute('data-pa', '');
      if (window.Blad && window.Blad.omritaTavlor) window.Blad.omritaTavlor(plan);
      anpassa();
    };
    requestAnimationFrame(efterOppning);
    setTimeout(efterOppning, 140);
    /* Canvasen ligger över sidan — då ska sidan inte rulla under den. Utan låset
       tog ett hjulsvep utanför duken med sig planeringen bakom överlägget, och
       när man stängde stod man någon annanstans än där man började. */
    forraOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    document.addEventListener('keydown', tangent);
  }
  function stang() {
    stangMini(true);
    skal.removeAttribute('data-pa');
    document.body.style.overflow = forraOverflow;
    setTimeout(() => { skal.hidden = true; }, 220);
    document.removeEventListener('keydown', tangent);
  }
  function tangent(e) {
    if (e.target.matches('textarea,input')) { if (e.key === 'Escape') e.target.blur(); return; }
    if (e.key === 'Escape') return stang();
    /* Ctrl/Cmd+Z och Ctrl/Cmd+Skift+Z går genom KNAPPARNA, inte direkt till
       plan.js — knapparna är låsta medan ett varv går, och genvägen ska
       lyda samma lås. */
    if ((e.ctrlKey || e.metaKey) && (e.key === 'z' || e.key === 'Z')) {
      e.preventDefault();
      const b = $(e.shiftKey ? '#g-gorom' : '#g-angra');
      if (b && !b.disabled) b.click();
      return;
    }
    if (e.key === '+' || e.key === '=') zooma(1.2);
    if (e.key === '-') zooma(1 / 1.2);
    if (e.key === '0') anpassa();
    if (e.key === 'k' || e.key === 'K') satValj(!valjLage);
  }
  $('#g-stang').addEventListener('click', stang);
  /* hovra ett element i pappret — dess ändringar lyser upp i kolumnen */
  plan.addEventListener('pointerover', e => {
    const el = e.target.closest('[data-el]');
    const ark = arkIndex();
    $$('.gvarv', lista).forEach(v => {
      const post = kommentarer.find(k => k.id === Number(v.dataset.id));
      /* Arket måste stämma: uppg3 finns på båda arken, och att hovra facitets
         uppgift 3 lyste annars upp en kommentar som gällde provets. */
      v.toggleAttribute('data-pekad', !!(el && post
        && post.elen.includes(el.dataset.el) && (post.ark || 0) === ark));
    });
  });
  plan.addEventListener('pointerleave', () => $$('.gvarv', lista).forEach(v => v.removeAttribute('data-pekad')));
  window.addEventListener('resize', () => { if (!skal.hidden) anpassa(); });

  /* dokumentet ritas om (t.ex. när en bild lagts in) — nålarna sätts tillbaka på sina element */
  function sattOm(nod, ark) {
    if (!nod || skal.hidden) return;
    /* ett tomt papper (React hann inte rita) får aldrig ersätta det som redan visas */
    if (!nod.children.length && !nod.textContent.trim()) return;
    if (ark) { if (host) host.ark = ark; satArkval(ark); }
    plan.innerHTML = '';
    const klon = nod.cloneNode(true);
    klon.classList.add('gdok');
    plan.appendChild(klon);
    /* Samma väckning som i oppna() — omritningen efter ett varv går här. */
    if (window.Prickar) window.Prickar.pa(klon);
    if (window.Blad && window.Blad.omritaTavlor) window.Blad.omritaTavlor(plan);
    /* Nålarna sätts tillbaka på SITT ark. Raden satte förut alla nålar på det
       ark som råkade ritas, så ett byte till lösningsförslaget flyttade dit
       hela trådens markeringar — och de pekade på uppgifter ingen kommenterat. */
    kommentarer.forEach(k => k.elen.forEach(id => satNal(id, k.id, k.ark)));
    markeraMalen();
    /* Svepet och blinken hängde i den gamla klonen och följde inte med hit.
       Blinken hör HIT och ingen annanstans: det är först nu det nya pappret
       står på skärmen, och en blink satt före omritningen hade slängts med
       klonen utan att någon sett den. */
    markeraArbete();
    blinkaNu();
    satVy();
  }
  /* Vad prickarna i pappret behöver av granskningen: paret att visa, och vägen
     till raden i listan. Ingen egen kopia av någondera — en prick som visade en
     annan text än panelen hade varit värre än ingen prick alls. */
  function diffFor(elId) {
    /* Paret hör till det ark det mättes på. Prickarna på facitets uppgift 3 ska
       inte visa provets före/efter — samma id, annat papper. */
    if (senaste.ark !== arkIndex()) return null;
    const par = senaste.par[elId];
    return par ? { fore: par.fore, efter: par.efter, varv: senaste.varv } : null;
  }
  function visaVarv(n) {
    if (!n) return false;
    if (!kommentarer.some(k => k.id === n)) return false;
    fokusera(n);
    return true;
  }
  window.Granska = { oppna, stang, sattOm, diffFor, visaVarv,
                     get oppen() { return !skal.hidden; },
                     /* Kön utåt, som text: e2e ska kunna fråga vad som väntar
                        utan att gräva i panelens DOM. */
                     get koad() { return ko.map(x => x.text); },
                     /* Blinken varar 1,6 s och går inte att fånga med en
                        väntande expect — den senaste listan står kvar här av
                        samma skäl som `koad` finns: e2e ska slippa jaga en
                        markering i DOM:en. */
                     get blinkade() { return blinkade.slice(); },
                     get senasteVarv() { return senaste.varv; },
                     get kommentarer() { return kommentarer; } };
})();
