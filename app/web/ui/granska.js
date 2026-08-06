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
    if (e.target.closest('.gpin,.gfab,.gpanel')) return;
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
  function satMal(el) {
    mal = el ? { el: el.dataset.el, namn: etikett(el) } : null;
    const bred = arkNamn();
    $('.gmaltext', $('#g-mal')).textContent = mal ? mal.namn : bred;
    $('#g-mal').toggleAttribute('data-satt', !!mal);
    $('#g-malx').hidden = !mal;
    $$('.gdok [data-el]', plan).forEach(x => x.toggleAttribute('data-mal', !!mal && x.dataset.el === mal.el));
    const f = $('#g-falt');
    f.placeholder = `Vad ska ändras i ${bestamd(mal ? mal.namn : bred)}?`;
    f.focus({ preventScroll: true });
  }
  $('#g-malx').addEventListener('click', () => satMal(null));
  plan.addEventListener('click', e => {
    if (!valjLage) return;
    const el = e.target.closest('[data-el]');
    if (!el) return;
    e.stopPropagation();
    satMal(el);
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
    const andrade = Object.keys(efter).filter(id => fore[id] !== undefined && (fore[id] || '').trim() !== (efter[id] || '').trim());
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

  function skicka(text) {
    if (!text.trim()) return;
    const fore = ogonblick();
    const tom = $('#g-tom');
    if (tom) tom.hidden = true;
    nr++;
    const post = { id: nr, el: mal ? mal.el : '', namn: mal ? mal.namn : arkNamn(), text };
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
      jobb: host && host.onJobb ? k => host.onJobb(text, post.namn, post.el, k)
        /* Inget riktigt anrop — prototypen, eller ett papper appen skrev själv.
           Då är väntan prototypens egen, precis som förut. */
        || new Promise(r => setTimeout(r, 1400)) : null,
      svar: `Skrivet om. ${post.namn} följer nu ”${text.trim()}” — ändringen är markerad i pappret.`,
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
    $('#g-titel').textContent = o.titel || 'Utkast';
    $('#g-meta').textContent = o.meta || '';
    kommentarer = []; nr = 0; mal = null;
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
    if (window.Blad && window.Blad.omritaTavlor) window.Blad.omritaTavlor(plan);
    kommentarer.forEach(k => { if (k.el) satNal(k.el, k.id); });
    if (mal) $$('.gdok [data-el]', plan).forEach(x => x.toggleAttribute('data-mal', x.dataset.el === mal.el));
    satVy();
  }
  window.Granska = { oppna, stang, sattOm, get oppen() { return !skal.hidden; }, get kommentarer() { return kommentarer; } };
})();
