/* ── Sidor ur läroboken: PDF/foto som referens för genomgången ── */
(() => {
  const q = s => document.querySelector(s);
  const knapp = q('#sidknapp'), fil = q('#sidfil'), ut = q('#sidminis'), not = q('#sidnot'), ruta = q('#sidrad');
  if (!knapp) return;
  const lista = [], grund = not.textContent;
  /* ── Uppladdningen ────────────────────────────────────
     Dörren SÅG kopplad ut men var det inte: filerna levde bara i den här
     listan, ingen JOBB-kropp bar dem, och noten lovade ändå att «tolkningen
     skickas». Hela servervägen fanns (POST /api/planning/underlag →
     bildtolkning → underlag-fältet i generate → boksidan på arket) — det som
     saknades var anropet. Uppladdningen görs LATT vid Skriv (sakra nedan):
     tolkningen kostar ett visionsanrop per sida, och den ska inte betalas
     för filer läraren hinner ångra. Samma filer i samma ordning laddas inte
     upp två gånger. */
  let uppladdat = null;             /* { nyckel, pid } när sidorna ligger uppe */
  let laddar = null;                /* pågående uppladdning (löfte) */
  const nyckel = () => lista.map(r => `${r.namn}:${(r.data || '').length}`).join('|');
  async function sakra(val) {
    if (!lista.length || !(window.API && window.API.pa)) return null;
    /* Filerna läses av en FileReader, och Skriv kan tryckas innan en tjock PDF
       är genomläst: då gick tomma data-URL:er i väg och servern svarade
       «formatet stöds inte» om en fil som var alldeles riktig. */
    await Promise.all(lista.map(r => r.klar));
    const nu = nyckel();
    if (uppladdat && uppladdat.nyckel === nu) return uppladdat.pid;
    if (laddar) return laddar;
    laddar = window.API.strom('/api/planning/underlag', {
      filer: lista.map(r => ({ namn: r.namn, data: r.data })),
    }, { log: (val || {}).log }).then(r => {
      laddar = null;
      if (!r || !r.id) throw new Error('Sidorna gick inte att ladda upp den här gången. Försök igen.');
      uppladdat = { nyckel: nu, pid: r.id };
      /* Tolkningsraden under varje mini är från och med nu APPENS lästa
         beskrivning, inte filnamnsgissningen. */
      tolkningarna(r.filer || []);
      rita();
      return r.id;
    }).catch(e => {
      /* Felet ska VIDARE, inte bli null. Förr svalde den här catchen allt:
         planen rullade på med raden «Tolkar dina sidor · N filer», tavlan
         skrevs utan sidorna och läraren fick aldrig veta varför. En HEIC ur
         telefonens kamerarulle fäller hela begäran med 400 (_UNDERLAG_MIME),
         och det är serverns svenska mening som ska stå i rutan — jobbkedjan
         (plan.js → Fraga.kor) visar den när löftet avvisar. */
      laddar = null;
      throw e;
    });
    return laddar;
  }
  /* Svarets poster är SIDOR, inte filer: servern expanderar varje PDF till en
     post per sida («kapitel3.pdf — sida 2», routes_planning.py). Lästes de
     index för index hamnade PDF-sidornas beskrivningar under fel papper —
     fotot sist i raden fick sida 2 ur kapitlet under sig. Posterna kommer i
     filernas ordning, så varje fil sväljer sina egna sidor. Namnet jämförs mot
     serverns SANERADE form (samma regel som _safe_component), annars tappar en
     fil med kolon eller frågetecken i namnet sin tolkning. */
  const SIDSUFFIX = / — sida \d+$/;
  const sanerat = n => String(n || '').replace(/[<>:"/\\|?*\x00-\x1f]/g, '')
    .trim().replace(/^\.+|\.+$/g, '').slice(0, 80) || 'fil';
  function tolkningarna(filer) {
    let i = 0;
    lista.forEach(rad => {
      const vantat = sanerat(rad.namn);
      const passar = () => i < filer.length
        && String((filer[i] || {}).namn || '').replace(SIDSUFFIX, '') === vantat;
      const mina = [];
      if (rad.typ === 'pdf') { while (passar()) mina.push(filer[i++]); }
      else if (passar()) mina.push(filer[i++]);
      /* Går namnet inte att para ihop (sidbudgeten kapade PDF:en, servern
         sanerade annorlunda) tar raden nästa post ändå — annars fastnar
         gången här och ALLA filer efter blir utan tolkning. */
      if (!mina.length && i < filer.length) mina.push(filer[i++]);
      const b = mina.map(f => (f || {}).beskrivning).find(Boolean);
      if (b) rad.tolkning = b.split('\n')[0].slice(0, 90);
    });
  }
  window.Sidor = {
    lista: () => lista.map(r => ({ namn: r.namn, typ: r.typ })),
    antal: () => lista.length,
    sakra,
  };
  /* Sidorna ligger som små papper i en rad — dragbara, med appens tolkning under.
     Utan tolkningsraden vet läraren aldrig varför utkastet blev som det blev. */
  function rita() {
    ut.innerHTML = lista.map((r, i) => `<div class="sidmini" draggable="true" data-i="${i}">${r.url ? `<img class="sidbild" src="${r.url}" alt="" />` : '<span class="sidpdf">PDF</span>'}<span class="sidtext"><span class="sidnamn">${r.tolkning || r.namn}</span><span class="sidmeta">${i + 1} · ${r.typ} · ${r.namn}</span></span><button class="sidbort" type="button" data-i="${i}" aria-label="Ta bort ${r.namn}">×</button></div>`).join('');
    const lasta = lista.length ? `${lista.length} ${lista.length === 1 ? 'fil' : 'filer'} lästa — bilderna stannar på datorn, bara tolkningen skickas.` : grund;
    /* Den avvisade filen står i noten, inte i tystnaden: läraren ska se på en
       gång att telefonbilden inte ligger i dörren, och vad hen gör åt det. */
    not.textContent = avvisade.length
      ? `${avvisade.join(', ')} kan inte läsas — spara om som JPG, PNG eller PDF `
        + `(iPhone: Inställningar → Kamera → Format → Mest kompatibelt). ${lasta}`
      : lasta;
    knapp.querySelector('.valjtext').textContent = lista.length ? 'Lägg till fler' : 'Lägg till filer';
  }
  /* Fältet ersätts inte av bilden — det fylls i av sidans rubrik och bär
     gissningens streckade ram, precis som klass och kurs i kön. */
  function gissaMoment(tolkat) {
    const f = document.querySelector('#moment'), not2 = document.querySelector('#momentgissat');
    if (!f || !tolkat || f.value.trim()) return;
    f.value = tolkat.rubrik;
    f.setAttribute('data-gissad', '');
    if (not2) not2.hidden = false;
    f.dispatchEvent(new Event('input', { bubbles: true }));
    f.dispatchEvent(new Event('change', { bubbles: true }));
  }
  const momentfalt = document.querySelector('#moment');
  if (momentfalt) momentfalt.addEventListener('input', e => {
    if (!e.isTrusted) return;
    momentfalt.removeAttribute('data-gissad');
    const n = document.querySelector('#momentgissat');
    if (n) n.hidden = true;
  });
  /* Formaten servern tar (_UNDERLAG_MIME i routes_planning.py), och huvudet
     den letar efter. EN okänd fil fäller HELA begäran med 400 — en HEIC rakt
     ur telefonens kamerarulle är precis det. Därför stoppas den i dörren i
     stället för i skrivningen, och resten av sidorna får gå vidare. */
  const FORMAT = {
    'image/png': 'data:image/png;base64,',
    'image/jpeg': 'data:image/jpeg;base64,',
    /* «image/jpg» finns inte, men Windows lämnar ut den — och en FileReader
       skriver då ett huvud servern inte känner igen. Filen är riktig; det är
       bara namnet på typen som är fel, så huvudet skrivs om. */
    'image/jpg': 'data:image/jpeg;base64,',
    'image/webp': 'data:image/webp;base64,',
    'application/pdf': 'data:application/pdf;base64,',
  };
  const ANDELSER = { png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg',
                     webp: 'image/webp', pdf: 'application/pdf' };
  /* Lämnar systemet ut filen utan typ får ändelsen avgöra — det är ändå den
     webbläsarens egen typgissning bygger på i Windows. */
  const mimen = f => (f.type || '').toLowerCase()
    || ANDELSER[String(f.name || '').split('.').pop().toLowerCase()] || '';
  let avvisade = [];
  /* Rubrikgissningen är en BEKVÄMLIGHET, aldrig ett villkor för att filen ska
     komma in. Bok.tolka slår upp kursens register och kastar på en kurs UTAN
     bok (bok.js: namnet(A[0]) på en tom lista) — och eftersom kastet skedde
     mitt i lägget dog hela dörren med den: ingen mini, ingen not, inget fel
     läraren kunde se. Med en riktig server och ingen inläst bok var det varje
     gång. */
  function gissaSidan(namn, i) {
    if (!(window.Bok && window.Bok.tolka)) return null;
    try { return window.Bok.tolka(namn, i); } catch (e) { return null; }
  }
  function lagg(filer) {
    let forsta = null;
    avvisade = [];
    [...filer].forEach(f => {
      const mime = mimen(f);
      if (!FORMAT[mime]) { avvisade.push(f.name); return; }
      const bild = mime !== 'application/pdf';
      const tolkat = gissaSidan(f.name, lista.length);
      const rad = { namn: f.name, typ: bild ? 'foto' : 'pdf', url: bild ? URL.createObjectURL(f) : '', tolkning: tolkat ? tolkat.text : '', data: '' };
      lista.push(rad);
      /* Fildatat läses direkt (uppladdningen vid Skriv är synkron i sin
         kropp) — som data-URL, samma form servern validerar. Huvudet sätts
         efter den typ som godkändes: en fil utan MIME-typ läses annars ut som
         application/octet-stream, och servern läser bara huvudet. */
      const las = new FileReader();
      rad.klar = new Promise(los => {
        las.onload = () => { rad.data = String(las.result || '').replace(/^data:[^,]*,/, FORMAT[mime]); los(); };
        las.onerror = () => los();
      });
      las.readAsDataURL(f);
      if (!forsta) forsta = tolkat;
    });
    rita();
    gissaMoment(forsta);
  }
  /* Ordningen dras om — sidorna läses i den ordning de ligger */
  let drag = null;
  ut.addEventListener('dragstart', e => { const m = e.target.closest('.sidmini'); if (!m) return; drag = +m.dataset.i; e.dataTransfer.effectAllowed = 'move'; });
  ut.addEventListener('dragover', e => { e.preventDefault(); });
  ut.addEventListener('drop', e => {
    const m = e.target.closest('.sidmini');
    if (!m || drag === null) return;
    e.preventDefault();
    e.stopPropagation();
    const till = +m.dataset.i;
    lista.splice(till, 0, lista.splice(drag, 1)[0]);
    drag = null;
    rita();
  });
  knapp.addEventListener('click', () => fil.click());
  fil.addEventListener('change', () => { lagg(fil.files); fil.value = ''; });
  ut.addEventListener('click', e => {
    const b = e.target.closest('.sidbort');
    if (!b) return;
    const r = lista.splice(+b.dataset.i, 1)[0];
    if (r && r.url) URL.revokeObjectURL(r.url);
    /* Städar läraren i raden är beskedet om den avvisade filen läst — det ska
       inte stå kvar över nästa urval. */
    avvisade = [];
    rita();
  });
  ['dragover', 'dragenter'].forEach(t => ruta.addEventListener(t, e => { e.preventDefault(); ruta.setAttribute('data-over', ''); }));
  ['dragleave', 'drop'].forEach(t => ruta.addEventListener(t, e => { e.preventDefault(); ruta.removeAttribute('data-over'); }));
  ruta.addEventListener('drop', e => { if (e.dataTransfer && e.dataTransfer.files.length) lagg(e.dataTransfer.files); });
})();
