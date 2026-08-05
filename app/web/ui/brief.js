/* ══════════ VECKOBRIEFEN ══════════
   Agendan var passiv. Briefen är appens startläge de dagar det finns något att
   säga — rader med verb, högst fem, i den ordning som betalar tillbaka mest tid.
   Finns ingenting kollapsar ytan helt: ingen «allt klart»-ruta.

   Raderna var förr en hårdkodad lista. Den räknade upp 9A:s lektioner också när
   klassremsan stod på 9B, och skrev kalenderns datum medan schemat sextio pixlar
   längre ner visade en annan vecka — två «nu» i samma ruta. Nu läser briefen
   exakt samma tre källor som veckan och terminen: veckan som schemat står i
   (Klass.veckan), klassfiltret (Klass.klass) och de godkända dokumenten
   (Dokument.sparade). Klass.rita() ropar hit varje gång någon av dem ändras. */
window.Brief = (() => {
  const $ = s => document.querySelector(s);
  const ruta = $('#veckobrief');
  const wrap = $('#briefwrap');
  if (!ruta || !wrap) return { rita() {} };
  const K = window.Kalender;

  const ORD = ['inga', 'ett', 'två', 'tre', 'fyra', 'fem', 'sex', 'sju', 'åtta', 'nio', 'tio', 'elva', 'tolv'];
  const rakna = n => ORD[n] || String(n);
  const versal = s => String(s || '').charAt(0).toUpperCase() + String(s || '').slice(1);
  const start = t => String(t || '').split('–')[0].trim();
  const dok = () => (window.Dokument && window.Dokument.sparade ? window.Dokument.sparade() : []);
  const filtret = () => (window.Klass && window.Klass.klass ? window.Klass.klass() : 'alla');
  const veckan = () => (window.Klass && window.Klass.veckan ? window.Klass.veckan() : K.mandagen(K.idag()));

  /* Samma tillhörighetsregel som veckan och terminen: samma dag, samma klass,
     samma kurs — och samma klockslag när dokumentet vet sitt klockslag. */
  const dokFor = (datum, s) => dok().filter(v => v.datum === datum && (v.klass || '') === (s.klass || '')
    && (!v.tid || !s.tid || start(v.tid) === start(s.tid))
    && (!v.kurs || !s.kurs || v.kurs === s.kurs));

  function bytFlik(namn) {
    const f = [...document.querySelectorAll('.flik')].find(b => b.textContent.trim() === namn);
    if (f) f.click();
  }
  /* Raderna är genvägar, inte lägen: briefen fäller ihop sig när man tagit en. */
  function tillVeckan(kl, datum) {
    fall();
    bytFlik('Planering');
    if (kl && kl !== 'alla' && window.Klass && window.Klass.filtrera) window.Klass.filtrera(kl);
    if (datum && window.Klass && window.Klass.till) window.Klass.till(datum);
    const el = $('#klassvyn');
    if (!el) return;
    const y = Math.max(0, el.getBoundingClientRect().top + window.scrollY - 84);
    (window.rullaTill || (v => window.scrollTo(0, v)))(y, 620);
  }

  /* ── Vad veckan faktiskt saknar ─────────────────────
     Tre slag av rader, i den ordning de kostar tid att upptäcka sent: ett bokat
     prov som ingen skrivit, lektioner utan material, och papper som ska tryckas. */
  function poster() {
    const bild = K.veckoBild(veckan());
    const kl = filtret();
    const iVeckan = d => d >= bild.mandag && d <= bild.fredag;
    const minKlass = k => kl === 'alla' || (k || '') === kl;
    const p = [];

    /* 1 · Prov som står i kalendern utan att vara skrivet. Ett nationellt prov är
       inte lärarens att skriva — det är en tid att hålla, inte en uppgift. */
    const oskrivna = K.poster.filter(x => iVeckan(x.datum) && minKlass(x.klass)
      && /prov/i.test(x.titel || '') && !/nationell/i.test(x.titel || '')
      && !dok().some(v => v.datum === x.datum && (v.klass || '') === (x.klass || '') && /prov/i.test(v.typ)));
    if (oskrivna.length) {
      const f = oskrivna[0];
      p.push({
        rubrik: oskrivna.length === 1 ? 'Provet är oskrivet' : `${versal(rakna(oskrivna.length))} prov är oskrivna`,
        under: oskrivna.slice(0, 2).map(x => [(x.titel || '').replace(/^prov\s+/i, ''), K.ord(x.datum)]
          .filter(Boolean).join(' · ')).join('  ·  '),
        antal: oskrivna.length > 1 ? oskrivna.length : 0,
        gor: () => tillVeckan(f.klass, f.datum)
      });
    }

    /* 2 · Lektioner i veckan utan ett enda godkänt papper. */
    const tomma = [];
    bild.dagar.forEach(d => {
      if (d.lov) return;
      d.schema.filter(s => minKlass(s.klass))
        .slice().sort((a, b) => start(a.tid).localeCompare(start(b.tid)))
        .forEach(s => { if (!dokFor(d.datum, s).length) tomma.push({ d, s }); });
    });
    if (tomma.length) {
      const rad = t => `${t.d.namn.split(' ')[0]} ${start(t.s.tid)}${t.s.klass && kl === 'alla' ? ' ' + t.s.klass : ''}`;
      const visade = tomma.slice(0, 2).map(rad).join(' · ');
      p.push({
        rubrik: tomma.length === 1 ? 'En lektion saknar material' : `${versal(rakna(tomma.length))} lektioner saknar material`,
        under: visade + (tomma.length > 2 ? ` · och ${tomma.length - 2 === 1 ? 'en' : rakna(tomma.length - 2)} till` : ''),
        antal: tomma.length,
        gor: () => tillVeckan(kl, tomma[0].d.datum)
      });
    }

    /* 3 · Prov som ÄR skrivet och ligger i veckan ska tryckas innan det hålls —
       det är den enda av de tre raderna som bär en hög papper. Bara framåt: ett
       prov som redan är hållet ska inte «skrivas ut till» sitt eget datum. */
    const tryck = dok().filter(v => !v.losningsblad && /prov/i.test(v.typ) && iVeckan(v.datum)
      && minKlass(v.klass) && v.datum >= K.idag());
    if (tryck.length && window.Tryck) {
      const v = tryck[0];
      p.push({
        rubrik: `Provet ska skrivas ut till ${K.ord(v.datum)}`,
        under: [versal(v.moment || v.typ), v.klass, v.kurs].filter(Boolean).join(' · '),
        gor: () => { fall(); bytFlik('Planering'); window.Tryck.lektion({ datum: v.datum, klass: v.klass }); }
      });
    }
    return p;
  }

  /* Rubriken är radernas summa i en mening — inte en egen påstående som kan
     hamna i otakt med listan under sig. Klassen står i raden över och behöver
     inte hängas på slutet: «… saknar material i 9B» läste sig som om bara den
     sista satsen gällde 9B. */
  function rubriken(p) {
    const bit = r => r.rubrik.replace(/^(\S+) /, (m, f) => ORD.includes(f.toLowerCase()) ? f.toLowerCase() + ' ' : m).toLowerCase();
    const delar = p.map(bit);
    const text = delar.length === 1 ? delar[0]
      : delar.slice(0, -1).join(', ') + ' och ' + delar[delar.length - 1];
    return versal(text);
  }

  function narraden(bild, kl) {
    const m1 = new Date(bild.mandag + 'T12:00:00');
    const m2 = new Date(bild.fredag + 'T12:00:00');
    const spann = m1.getMonth() === m2.getMonth()
      ? `${m1.getDate()}–${K.ord(bild.fredag)}`
      : `${K.ord(bild.mandag)} – ${K.ord(bild.fredag)}`;
    /* Veckonumret är schemats, inte kalenderns: briefen sammanfattar den vecka
       man står i. Är det den vi lever i heter den så. */
    const nu = K.mandagen(K.idag()) === bild.mandag;
    return [nu ? 'Den här veckan' : `Vecka ${bild.vecka}`, spann, kl !== 'alla' ? kl : '']
      .filter(Boolean).join(' · ');
  }

  function rita() {
    if (!K) return;
    const p = poster(), kl = filtret();
    if (!p.length) {
      wrap.hidden = true;
      fall();
      return;
    }
    $('#briefnar').textContent = narraden(K.veckoBild(veckan()), kl);
    $('#briefrubrik').textContent = rubriken(p.slice(0, 5));
    const lista = $('#brieflista');
    lista.innerHTML = '';
    p.slice(0, 5).forEach(post => {
      const b = document.createElement('button');
      b.className = 'nstegrad';
      b.type = 'button';
      b.innerHTML = '<span class="nsn"><span class="nsr"></span><span class="nst"></span></span>' +
        (post.antal ? `<span class="nsantal">${post.antal}</span>` : '') + '<span class="nspil">→</span>';
      b.querySelector('.nsr').textContent = post.rubrik;
      b.querySelector('.nst').textContent = post.under;
      b.addEventListener('click', post.gor);
      lista.appendChild(b);
    });
    /* Knappen i sökraden bär ett ord och ett antal — rubriken står i panelen. */
    $('#brktext').textContent = 'Veckan';
    $('#brkantal').textContent = String(p.length);
    wrap.hidden = false;
  }

  /* Startläget är remsan, inte rutan — briefen tar plats först när man ber om den. */
  const knapp = $('#briefoppna');
  function fall() { wrap.classList.remove('oppen'); knapp.setAttribute('aria-expanded', 'false'); }
  /* Knappen står kvar när rullgardinen är öppen — då måste den också stänga. */
  knapp.addEventListener('click', () => {
    if (wrap.classList.contains('oppen')) return fall();
    wrap.classList.add('oppen');
    knapp.setAttribute('aria-expanded', 'true');
  });
  /* Ett klick utanför raderna fäller ihop briefen igen — samma gest som stänger
     en väljare. Escape gör samma sak. */
  document.addEventListener('pointerdown', e => {
    if (!wrap.classList.contains('oppen')) return;
    if (wrap.contains(e.target)) return;
    fall();
  }, true);
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && wrap.classList.contains('oppen')) fall();
  });
  /* Och som appens övriga fällda ytor: går musen ut faller den ihop av sig själv
     — men aldrig medan man skriver i den. */
  if (matchMedia('(hover:hover) and (pointer:fine)').matches) {
    let ut;
    const skriver = () => {
      const a = document.activeElement;
      return !!a && wrap.contains(a) && (a.matches('input,textarea') || a.isContentEditable);
    };
    wrap.addEventListener('pointerenter', () => clearTimeout(ut));
    wrap.addEventListener('pointerleave', e => {
      if (e.pointerType === 'touch' || !wrap.classList.contains('oppen')) return;
      clearTimeout(ut);
      ut = setTimeout(() => { if (wrap.classList.contains('oppen') && !skriver()) fall(); }, 240);
    });
  }

  /* Första ritningen kommer ur Klass.rita() — briefen laddas före klassvyn och
     vet därför inte vilken vecka schemat öppnar i förrän den ropar. */
  return { rita };
})();
