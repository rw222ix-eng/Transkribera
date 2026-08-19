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
       veta att någon tryckte på den. Samma skäl som nålarna står här. */
    if (e.target.closest('.gpin,.gfab,.gpanel,.aprick')) return;
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
  let mal = null;

  function satValj(pa) {
    valjLage = pa;
    skal.toggleAttribute('data-valj', pa);
    $('#g-valj').setAttribute('aria-pressed', String(pa));
    $('#g-valjtext').textContent = pa ? 'Klicka på det du vill ändra' : 'Välj element';
  }
  $('#g-valj').addEventListener('click', () => satValj(!valjLage));

  /* Utan valt element gäller ändringen ARKET man tittar på, inte «dokumentet»:
     provet och lösningsförslaget är två ark i samma canvas, och en ändring i det
     ena är sällan en ändring i det andra. */
  function arkNamn() {
    const a = $('#g-arkval');
    if (!a || a.hidden) return 'Hela dokumentet';
    const pa = $('button[aria-pressed="true"]', a);
    return pa ? pa.textContent.trim() : 'Hela dokumentet';
  }
  /* «Lösningsförslag» blir «lösningsförslaget» i en mening — arkets etikett är
     en flik, frågan i fältet är svenska. */
  const BEST = { 'hela dokumentet': 'dokumentet', 'lösningsförslag': 'lösningsförslaget', 'provet': 'provet' };
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
  function satMal(el) {
    mal = el ? { el: el.dataset.el, namn: etikett(el), text: innehall(el),
                 renderat: renderat(el) } : null;
    satSnabb(!!mal);
    const bred = arkNamn();
    $('.gmaltext', $('#g-mal')).textContent = mal ? mal.namn : bred;
    $('#g-mal').toggleAttribute('data-satt', !!mal);
    $('#g-malx').hidden = !mal;
    $$('.gdok [data-el]', plan).forEach(x => x.toggleAttribute('data-mal', !!mal && x.dataset.el === mal.el));
    const f = $('#g-falt');
    f.placeholder = `Vad ska ändras i ${bestamd(mal ? mal.namn : bred)}?`;
    f.focus({ preventScroll: true });
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
  $('#g-malx').addEventListener('click', () => satMal(null));
  plan.addEventListener('click', e => {
    if (!valjLage) return;
    const el = e.target.closest('[data-el]');
    if (!el) return;
    e.stopPropagation();
    /* Samma element igen betyder «inte det här heller». Utan det satt
       markeringen kvar hur mycket man än klickade, och enda vägen ur den var
       krysset i målrutan — som man ska behöva hitta först. */
    satMal(mal && mal.el === el.dataset.el ? null : el);
  });

  /* en nål per skickad ändring, numrerad i trådens ordning */
  function satNal(elId, n) {
    const el = $(`[data-el="${elId}"]`, plan);
    if (!el) return;
    const pin = document.createElement('span');
    pin.className = 'gpin';
    pin.dataset.id = String(n);
    pin.textContent = String(n);
    pin.style.transform = `translate(-50%,-50%) scale(${1 / vy.z})`;
    pin.addEventListener('click', ev => { ev.stopPropagation(); fokusera(n); });
    el.appendChild(pin);
  }
  const markera = (elId, pa) => {
    if (!elId) return;
    const el = $(`[data-el="${elId}"]`, plan);
    if (el) el.toggleAttribute('data-pekad', pa);
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
  let senaste = { varv: 0, par: {} };
  const kapa = s => s.length > 160 ? s.slice(0, 159) + '…' : s;
  function ogonblick() {
    const m = {};
    $$('.gdok [data-el]', plan).forEach(n => { m[n.dataset.el] = platt(n); });
    return m;
  }
  /* En diff som visar samma text två gånger är ingen diff — den får läraren att
     tro att något ändrats som inte gjort det. Bara verkliga skillnader står kvar. */
  function ritaDiff(varv, fore, efter, andrade) {
    andrade = andrade.filter(id => (fore[id] || '').trim() !== (efter[id] || '').trim());
    if (!andrade.length) return;
    if ($('.gdiff', varv)) return;
    /* SAMMA par som rutan nedan ritar — prickarna i pappret visar dem i sin
       popover, och de får inte kunna säga något annat än panelen. Sparas här,
       där paret först finns, i stället för att räknas fram en gång till. */
    senaste = { varv: Number(varv.dataset.id) || 0, par: {} };
    andrade.forEach(id => {
      senaste.par[id] = { fore: kapa(fore[id] || ''), efter: kapa(efter[id] || '') };
    });
    const d = document.createElement('div');
    d.className = 'gdiff';
    andrade.slice(0, 2).forEach(id => {
      const p = document.createElement('p');
      p.style.margin = '0';
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
  function vantaDiff(varv, fore, n) {
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
    if (andrade.length) return ritaDiff(varv, fore, efter, andrade);
    if ((n || 0) > 40) return;
    requestAnimationFrame(() => vantaDiff(varv, fore, (n || 0) + 1));
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
  function svarText(post, text, res) {
    const gjort = `Skrivet om. ${post.namn} följer nu ”${text.trim()}” — ändringen är markerad i pappret.`;
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
    if (!post.el || sagt.includes(post.el)) return gjort;
    /* Servern ändrade något — men inte det läraren pekade på. Då är det den
       skillnaden som är beskedet, och inget annat. */
    const namn = [...new Set(sagt.map(namnFor).filter(Boolean))];
    return namn.length
      ? `${post.namn} står kvar oförändrad. Det som ändrades var ${raknaUpp(namn)} — markerat i pappret.`
      : `${post.namn} står kvar oförändrad. Något annat på pappret skrevs om i stället, och det är markerat.`;
  }

  function skicka(text) {
    if (!text.trim()) return;
    const fore = ogonblick();
    const tom = $('#g-tom');
    if (tom) tom.hidden = true;
    nr++;
    const post = { id: nr, el: mal ? mal.el : '', namn: mal ? mal.namn : arkNamn(),
                   /* Vad elementet FAKTISKT innehåller. Följer med till servern
                      så att omskrivningen gäller det läraren pekade på. */
                   innehall: mal ? mal.text : '',
                   renderat: mal ? mal.renderat : '', text };
    kommentarer.push(post);
    const varv = document.createElement('div');
    varv.className = 'gvarv';
    varv.dataset.id = String(nr);
    varv.innerHTML = `<div class="gvarvhuvud"><span class="gnotnr">${nr}</span><span class="gvarvel"></span></div><p class="gfraga"></p><div class="gsvar"></div>`;
    $('.gvarvel', varv).textContent = post.namn;
    $('.gfraga', varv).textContent = text;
    /* hovra ett meddelande — elementet lyser upp i pappret */
    varv.addEventListener('pointerenter', () => markera(post.el, true));
    varv.addEventListener('pointerleave', () => markera(post.el, false));
    varv.addEventListener('click', () => fokusera(post.id));
    lista.appendChild(varv);
    if (post.el) satNal(post.el, nr);
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
      jobb: host && host.onJobb ? k => host.onJobb(text, post.namn, post.el, k,
        post.el ? { el: post.el, namn: post.namn, innehall: post.innehall,
                    renderat: post.renderat } : null,
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
      svar: res => svarText(post, text, res),
      efterKlar: (_el, res) => {
        if (host && host.onAndra) host.onAndra(text, post.namn, post.el, res);
        vantaDiff(varv, fore, 0);
        (window.rullaLada || ((b, y) => { b.scrollTop = y; }))(lista, lista.scrollHeight);
        fokusera(nr);
      }
    });
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
  $('#g-bild').addEventListener('click', () => { if (host && host.onBild) host.onBild(mal ? mal.el : 'rubrik'); });

  /* ── öppna och stäng ── */
  /* Provet och lösningsförslaget är två ark av samma dokument — växlaren
     sitter i canvasens topp så man slipper stänga för att jämföra. */
  const arkval = $('#g-arkval');
  $$('button', arkval).forEach((b, j) => b.addEventListener('click', () => {
    $$('button', arkval).forEach((x, i) => x.setAttribute('aria-pressed', String(i === j)));
    if (host && host.ark && host.ark.byt) host.ark.byt(j);
    /* Byter man ark byter också det man skriver om — elementvalet hörde till
       det förra arket. */
    satMal(null);
  }));
  function satArkval(ark) {
    arkval.hidden = !(ark && ark.tva);
    if (!ark || !ark.tva) return;
    $$('button', arkval).forEach((b, j) => {
      b.textContent = (ark.namn || ['Provet', 'Lösningsförslag'])[j];
      b.setAttribute('aria-pressed', String(j === (ark.vald || 0)));
    });
    if (!mal) satMal(null);
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
    kommentarer = []; nr = 0; mal = null; senaste = { varv: 0, par: {} };
    satSnabb(false);          // nytt papper, inget element valt än
    $$('.gvarv', lista).forEach(v => v.remove());
    $('#g-tom').hidden = false;
    $('#g-antal').textContent = 'Inga ändringar än';
    satMal(null);
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
    skal.removeAttribute('data-pa');
    document.body.style.overflow = forraOverflow;
    setTimeout(() => { skal.hidden = true; }, 220);
    document.removeEventListener('keydown', tangent);
  }
  function tangent(e) {
    if (e.target.matches('textarea,input')) { if (e.key === 'Escape') e.target.blur(); return; }
    if (e.key === 'Escape') return stang();
    if (e.key === '+' || e.key === '=') zooma(1.2);
    if (e.key === '-') zooma(1 / 1.2);
    if (e.key === '0') anpassa();
    if (e.key === 'k' || e.key === 'K') satValj(!valjLage);
  }
  $('#g-stang').addEventListener('click', stang);
  /* hovra ett element i pappret — dess ändringar lyser upp i kolumnen */
  plan.addEventListener('pointerover', e => {
    const el = e.target.closest('[data-el]');
    $$('.gvarv', lista).forEach(v => {
      const post = kommentarer.find(k => k.id === Number(v.dataset.id));
      v.toggleAttribute('data-pekad', !!(el && post && post.el === el.dataset.el));
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
    kommentarer.forEach(k => { if (k.el) satNal(k.el, k.id); });
    if (mal) $$('.gdok [data-el]', plan).forEach(x => x.toggleAttribute('data-mal', x.dataset.el === mal.el));
    satVy();
  }
  /* Vad prickarna i pappret behöver av granskningen: paret att visa, och vägen
     till raden i listan. Ingen egen kopia av någondera — en prick som visade en
     annan text än panelen hade varit värre än ingen prick alls. */
  function diffFor(elId) {
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
                     get senasteVarv() { return senaste.varv; },
                     get kommentarer() { return kommentarer; } };
})();
