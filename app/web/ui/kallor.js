/* ══════════ STEG 3 · KÄLLORNA ══════════
   Tre dörrar: förra lektionen, boken, foton av sidorna. En, två eller alla tre
   — samma klickgest som lektionen i steg 1. Dörren styr bara om källan följer
   med; verktygen bakom (utgångskorten, bokuppslaget, sidorna) är oförändrade.

   Förra lektionen föreslås av sig själv: appen vet vilken klass som valdes i
   steg 1 och vilken lektion den hade senast, och slår på den dörren när steget
   öppnas. Transkriptet säger vad klassen faktiskt hann — det är underlaget. */
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const steg = $('.plansteg[data-steg="3"]');
  if (!steg) return;

  const dorrar = $$('#dorrar .kalla');
  const panel = d => $(`.kpanel[data-panel="${d}"]`, steg);
  const pa = d => $(`.kalla[data-dorr="${d}"]`, steg).getAttribute('aria-pressed') === 'true';
  let rortLektion = false;   /* har läraren själv rört lektionsdörren? */
  let autoValt = null;       /* lektionen appen valde åt en — byts när klassen byts */
  let uppslagen = null;      /* EN panel står öppen i taget — se ritaPaneler() */

  /* Fyra utfällda paneler gjorde steget 2 000 px högt och sköt kvittot utanför
     skärmen. Nu står EN uppslagen: de andra dörrarna är fortfarande valda —
     deras rad finns kvar i kvittot — men hopfällda. Ett klick på en vald dörr
     slår upp den igen. */
  function ritaPaneler() {
    dorrar.forEach(b => {
      const d = b.dataset.dorr, p = panel(d);
      const val = b.getAttribute('aria-pressed') === 'true';
      const upp = val && uppslagen === d;
      if (p) p.hidden = !upp;
      b.toggleAttribute('data-hopfalld', val && !upp);
      if (val && !upp) b.dataset.tip = 'Vald — klicka för att öppna den igen';
      else b.removeAttribute('data-tip');
    });
  }

  /* ── Vad appen vet om klassen ──────────────────────── */
  const klassen = () => ($('#p-klass') || {}).value || '';
  const lektioner = () => $$('#inspelningar .kort').map(k => ({
    namn: ($('.namn', k) || {}).textContent ? $('.namn', k).textContent.trim() : '',
    klass: k.dataset.klass || '', datum: k.dataset.datum || '',
    langd: ($('.tumtid', k) || {}).textContent || ''
  })).filter(l => l.namn).sort((a, b) => (a.datum || '').localeCompare(b.datum || ''));
  const senaste = () => {
    const k = klassen();
    const l = lektioner().filter(x => !k || x.klass === k);
    return l[l.length - 1] || null;
  };
  const dagdatum = d => {
    const x = new Date(String(d) + 'T12:00:00');
    if (isNaN(x)) return String(d || '');
    const dag = x.toLocaleDateString('sv-SE', { weekday: 'short' }).replace('.', '');
    const kort = x.toLocaleDateString('sv-SE', { day: 'numeric', month: 'short' }).replace(/\./g, '');
    return dag.charAt(0).toUpperCase() + dag.slice(1) + ' ' + kort;
  };
  const langden = t => {
    const m = String(t || '').match(/(\d{1,2})[:.](\d{2})/);
    return m ? `${+m[1]} min ${+m[2]} s` : String(t || '');
  };

  /* ── Dörrarnas undertexter ─────────────────────────── */
  function ritaDorrar() {
    const l = senaste(), k = klassen();
    const dl = $('.kalla[data-dorr="lektion"]', steg);
    const under = $('i', dl), mark = $('.kmark', dl);
    /* Rubriken följer valet: den föreslagna är «förra lektionen», men väljer man
       själv i listan är det en annan lektion — eller flera. */
    const namn = $$('#valdalektioner .lchip span').map(s => s.textContent);
    const foreslagen = namn.length === 1 && autoValt === namn[0];
    const titel = !namn.length ? 'Lektionen'
      : foreslagen ? 'Förra lektionen'
      : namn.length === 1 ? 'Lektionen'
      : `${namn.length} lektioner`;
    /* Dörren står still: den ÄR «förra lektionen» för klassen man valt i steg 1.
       Vad man sedan lagt till i listan syns i panelen och i kvittot. */
    const b = $('b', dl);
    if (b) b.textContent = 'Förra lektionen';
    const huv = $('.kpanel[data-panel="lektion"] .kpn', steg);
    if (huv) huv.textContent = titel;
    if (l) {
      /* Undertexten håller samma längd som de andra fyra dörrarnas: namnet och
       dagen. Klassen står redan i steg 1 och längden i panelen — med dem blev
       raden dubbelt så lång som grannarnas och dörren en annan höjd. */
      under.textContent = `${l.namn} · ${dagdatum(l.datum)}`;
      dl.removeAttribute('data-tom');
      mark.hidden = rortLektion;
    } else {
      under.textContent = `Ingen transkriberad lektion${k ? ' för ' + k : ''} än`;
      dl.setAttribute('data-tom', '');
      mark.hidden = true;
    }
    /* Boken är indexerad eller inte, och det är BOKENS eget register som avgör.
       Dörren namnger den bok som faktiskt ligger i hyllan — står hyllan på
       Matematik 4 får dörren inte säga 3c. Kursens bok är bara förvalet. */
    const bd = $('.kalla[data-dorr="bok"]', steg);
    const kurs = (($('#p-kurs') || {}).value || '').trim();
    const ihyllan = window.Uppslag && window.Uppslag.spann ? (window.Uppslag.spann() || {}).bok : '';
    const boknamn = ihyllan || (window.Bok && window.Bok.namnFor ? window.Bok.namnFor(kurs) : (window.Bok || {}).namn) || 'Läroboken';
    const reg = window.Bok && window.Bok.registerForBok ? window.Bok.registerForBok(boknamn) : null;
    const indexerad = !!(reg && reg.length);
    $('i', bd).textContent = `${boknamn} · ${indexerad ? 'indexerad per avsnitt' : 'inget register än'}`;
    bd.toggleAttribute('data-tom', !indexerad);
    const antal = $('#sidminis').children.length;
    const fot = $('.kalla[data-dorr="foton"]', steg);
    /* De fyra andra tomma d\u00f6rrarna s\u00e4ger att de \u00e4r tomma \u2014 \u00abinget register \u00e4n\u00bb,
       \u00abInget sparat \u00e4n\u00bb. Den h\u00e4r sa bara vad man kunde l\u00e4gga in, och d\u00e5 blev
       konturen det enda som skilde tom fr\u00e5n ifylld. */
    $('i', fot).textContent = antal ? `${antal} ${antal === 1 ? 'fil' : 'filer'} inlagda` : 'Ingen fil inlagd \u00e4n \u00b7 PDF eller foto';
    /* Ingen fil inlagd är ett tomt förråd, precis som en oöppnad lektion eller ett
       orattat prov — dörren öppnas ändå, det är där man lägger in dem. */
    fot.toggleAttribute('data-tom', !antal);
    /* Ur Sparat: samma sak som resten — dörren säger vad den bär just nu. Dörren
       bär två användningar av samma hög, och undertexten namnger högen. */
    const sp = $('.kalla[data-dorr="sparat"]', steg);
    if (sp) {
      const f = forlagan();
      const n = dokument().length;
      $('i', sp).textContent = f ? window.Dokument.namn(f)
        : n ? `${n} papper att bygga vidare på eller lägga om`
        : 'Inget sparat än';
      sp.toggleAttribute('data-tom', !n);
    }
    /* Det rättade provet: dörren säger vilket prov och hur det gick. */
    const pv = $('.kalla[data-dorr="prov"]', steg);
    if (pv) {
      const r = resultatet();
      const n = rattade().length;
      $('i', pv).textContent = r ? `${window.Dokument.namn(r)} · ${provkort(r)}`
        : n ? `${n} rättat${n === 1 ? '' : 'a'} prov att utgå från`
        : 'Inget prov är rättat än';
      pv.toggleAttribute('data-tom', !n);
    }
  }

  /* ── Ett rättat prov ─────────────────────────────────
     Femte dörren skiljer sig från «ett tidigare papper» i AVSIKT: förlagan är
     något man bygger EN NY version av, provresultatet är något man bygger något
     ANNAT av. Därför är det en egen dörr och inte en rad i samma lista — och
     därför rör den aldrig förlagan. */
  const rattade = () => dokument().filter(v => v.typ === 'Prov' && v.rattat)
    .sort((a, b) => String(b.datum || '').localeCompare(String(a.datum || '')));
  const resultatet = () => (window.Dokument && window.Dokument.resultatet ? window.Dokument.resultatet() : null);
  const provkort = v => {
    const r = v.rattat || {};
    const del = r.andel != null ? `${Math.round(r.andel * 100)} % av poängen` : '';
    const sv = (r.svaga || []).map(s => s.kod).filter(Boolean);
    return [r.elever ? `${r.elever} elever` : '', del, sv.length ? `svagast ${sv.join(', ')}` : ''].filter(Boolean).join(' · ');
  };
  function ritaProvlista() {
    const lista = $('#provlista');
    if (!lista) return;
    const alla = rattade();
    const vald = resultatet();
    lista.innerHTML = '';
    if (!alla.length) {
      const p = document.createElement('p');
      p.className = 'doktom';
      p.textContent = 'Inget prov är rättat än — skriv in klassens poäng på ett prov i veckan, så går det att utgå från här.';
      lista.appendChild(p);
      return;
    }
    alla.forEach(v => {
      const ar = !!vald && window.Dokument.namn(vald) === window.Dokument.namn(v);
      const r = document.createElement('button');
      r.type = 'button';
      r.className = 'dokrad';
      r.setAttribute('role', 'option');
      r.setAttribute('aria-selected', String(ar));
      r.innerHTML = '<span class="dring"></span><span class="dtum">PR</span><span class="dtext"><b></b><span></span></span>';
      $('.dtext b', r).textContent = window.Dokument.namn(v);
      $('.dtext>span', r).textContent = [v.klass || 'ingen klass', provkort(v)].filter(Boolean).join(' · ');
      r.addEventListener('click', () => {
        if (ar) { window.Dokument.slappResultat(); ritaProvlista(); ritaDorrar(); ritaKvitto(); return; }
        window.Dokument.sattResultat(v);
        if (!pa('prov')) satt('prov', true, true);
        ritaProvlista();
        ritaDorrar();
        ritaKvitto();
        const sv = ((v.rattat || {}).svaga || []).map(s => s.kod).filter(Boolean);
        window.toast && window.toast(sv.length
          ? `Utgår från resultatet — uppgift ${sv.join(', ')} föll och väger tyngst`
          : 'Utgår från provets resultat');
      });
      lista.appendChild(r);
    });
  }

  /* ── Ur Sparat ───────────────────────────────────────
     Fjärde dörren: det man redan gjort är också ett underlag. Valet sätter bara
     förlagan — vad som ska SKAPAS är fortfarande steg 2:s fråga. */
  const dokument = () => (window.Dokument && window.Dokument.sparade ? window.Dokument.sparade() : []).filter(v => !v.losningsblad);
  const forlagan = () => (window.Dokument && window.Dokument.forlagan ? window.Dokument.forlagan() : null);
  const dokmeta = v => [v.kurs || 'ingen kurs', v.klass || 'ingen klass',
    v.datum ? (window.Kalender && window.Kalender.ord ? window.Kalender.ord(v.datum) : v.datum) : 'utan datum'].filter(Boolean).join(' · ');
  const dokminis = v => v.typ === 'Tavla' ? 'TA' : v.typ === 'Prov' ? 'PR' : v.typ === 'Gruppuppgift' ? 'GU' : 'AB';
  function ritaSparatVald() {
    ritaSparatlista();
  }

  /* ── De två användningarna av ett tidigare papper ──
     «Bygg vidare på» och «Använd oförändrat» visar SAMMA dokumenthög. Två dörrar
     för samma hög vore ett fel och inte en nyans — skillnaden är därför ett val
     inne i dörren. Att bygga vidare sätter förlagan (ett nytt papper skrivs); att
     använda oförändrat kopierar pappret till lektionen man planerar, precis som
     samlingen i terminsvyn gjorde förr. Samlingen bodde där; den hör här, i det
     ögonblick man har en lektion och ska säga vad materialet ska utgå från. */
  let sparatlage = 'vidare';
  function ritaSparatlista() {
    const lista = $('#sparatlista');
    if (!lista) return;
    const seg = $('#sparatlage');
    if (seg) $$('button', seg).forEach(b => b.setAttribute('aria-pressed', String(b.dataset.lage === sparatlage)));
    const cap = $('#sparatcap');
    if (cap) cap.textContent = sparatlage === 'oforandrat'
      ? 'Pappret läggs som det är på lektionen du planerar — ingenting skrivs om'
      : 'Det valda blir förlaga — i sista steget säger du vad som ska följa med och vad som ska bli nytt';
    if (sparatlage === 'oforandrat') {
      const zon = $('#doksok');
      if (zon) zon.hidden = true;
      lista.setAttribute('role', 'list');
      ritaAterbruk(lista);
      return;
    }
    lista.setAttribute('role', 'listbox');
    /* Samma upplysning i b\u00e5da l\u00e4gena: hur stor h\u00f6gen \u00e4r. I \u00e5terbrukets l\u00e4ge \u00e4r den
       kursens h\u00f6g och r\u00e4knas d\u00e4r; h\u00e4r \u00e4r den hela h\u00f6gen. */
    const not = $('#sparatnot');
    if (not) { const n = dokument().length; not.textContent = n ? `${n} papper sparade` : 'inget sparat \u00e4n'; }
    ritaVidare();
  }
  function ritaVidare() {
    const lista = $('#sparatlista');
    if (!lista) return;
    const alla = dokument();
    const sok = $('#sparatsok');
    const q = ((sok || {}).value || '').trim().toLowerCase();
    const zon = $('#doksok');
    if (zon) zon.hidden = alla.length < 7;
    const val = q ? alla.filter(v => (window.Dokument.namn(v) + ' ' + dokmeta(v)).toLowerCase().includes(q)) : alla;
    const vald = forlagan();
    lista.innerHTML = '';
    if (!val.length) {
      const p = document.createElement('p');
      p.className = 'doktom';
      p.textContent = alla.length ? 'Inget papper matchar sökningen.' : 'Inget sparat än — godkänn ett utkast så landar det här.';
      lista.appendChild(p);
      return;
    }
    [...new Set(val.map(v => v.typ))].forEach(t => {
      const g = document.createElement('p');
      g.className = 'dokgrupp';
      g.textContent = t;
      lista.appendChild(g);
      val.filter(v => v.typ === t).forEach(v => {
        const ar = !!vald && window.Dokument.namn(vald) === window.Dokument.namn(v);
        const r = document.createElement('button');
        r.type = 'button';
        r.className = 'dokrad';
        r.setAttribute('role', 'option');
        r.setAttribute('aria-selected', String(ar));
        r.innerHTML = '<span class="dring"></span><span class="dtum"></span><span class="dtext"><b></b><span></span></span>';
        $('.dtum', r).textContent = dokminis(v);
        $('.dtext b', r).textContent = window.Dokument.namn(v);
        $('.dtext>span', r).textContent = dokmeta(v);
        r.addEventListener('click', () => {
          if (ar) {
            window.Dokument.slappForlaga();
            ritaSparatlista();
            ritaDorrar();
            ritaKvitto();
            return;
          }
          window.Dokument.sattForlaga(v);
          if (!pa('sparat')) satt('sparat', true, true);
          ritaSparatlista();
          ritaDorrar();
          ritaKvitto();
          window.toast && window.toast(`Utgår från ${window.Dokument.namn(v)} — säg i sista steget vad som ska följa med`);
        });
        lista.appendChild(r);
      });
    });
  }
  $('#sparatsok') && $('#sparatsok').addEventListener('input', ritaSparatlista);

  /* ── Att använda ett papper oförändrat ──────────────
     Samlingen är kursens: tavlor, arbetsblad och gruppuppgifter, grupperade per
     bokavsnitt. Kursen läses ur den lektion som planeras — därför KAN ett
     Matematik 4-papper inte stå på en Matematik 3c-lektion här, listan innehåller
     bara kursens egna papper. Prov står inte i listan: de skrivs från grunden
     varje gång.

     Två handlingar, som i samlingen förr: lägg pappret på lektionen, eller kasta
     det för gott. */
  const ATERBRUK = ['Tavla', 'Arbetsblad', 'Gruppuppgift'];
  const aktivLektion = () => (window.PlanKo && window.PlanKo.aktiv ? window.PlanKo.aktiv() : null);
  const kursNu = () => { const a = aktivLektion(); return (a && a.kurs) || ((($('#p-kurs') || {}).value || '').trim()); };
  const klassNu = () => { const a = aktivLektion(); return (a && a.klass) || klassen(); };
  const passar = (moment, a) => {
    const l = String(moment || '').toLowerCase();
    return !!l && (l.includes(a.titel.toLowerCase()) || a.titel.toLowerCase().includes(l));
  };
  const aterbrukbara = () => {
    const k = kursNu();
    return dokument().filter(v => ATERBRUK.includes(v.typ) && (!v.kurs || !k || v.kurs === k));
  };
  const versal = s => String(s || '').charAt(0).toUpperCase() + String(s || '').slice(1);
  function ritaAterbruk(lista) {
    const k = kursNu();
    const a = aktivLektion();
    const kanLagga = !!(a && a.datum);
    const alla = aterbrukbara();
    /* «7 papper · 7 från en annan klass» var det som gjorde återbruket möjligt att
       lita på — därför står upplysningen kvar, nu i dörren. */
    const kl = klassNu();
    const andra = alla.filter(v => v.klass && kl && v.klass !== kl).length;
    const not = $('#sparatnot');
    if (not) not.textContent = !alla.length ? (k ? `inget att återanvända i ${k} än` : 'inget sparat än')
      : [`${alla.length} ${alla.length === 1 ? 'papper' : 'papper'}${k ? ' i ' + k : ''}`,
        andra ? `${andra} från en annan klass` : '',
        kanLagga ? '' : 'välj en lektion i veckan för att lägga ett dit'].filter(Boolean).join(' · ');
    lista.innerHTML = '';
    if (!alla.length) {
      const p = document.createElement('p');
      p.className = 'doktom';
      p.textContent = `Tavlor, arbetsblad och gruppuppgifter du godkänner i ${k || 'kursen'} samlas här — och kan läggas på en ny lektion utan att skrivas om. Prov återanvänds inte: de skrivs från grunden varje gång.`;
      lista.appendChild(p);
      return;
    }
    const A = (window.Bok && window.Bok.forKurs ? window.Bok.forKurs(k) : null) || [];
    const grupper = [];
    alla.forEach(v => {
      const av = A.find(x => passar(v.moment, x));
      const namn = av ? `${av.nr} ${av.titel}` : versal(v.moment || 'Utan moment');
      let g = grupper.find(x => x.namn === namn);
      if (!g) grupper.push(g = { namn, nr: av ? av.nr : 'zz', rader: [] });
      g.rader.push(v);
    });
    grupper.sort((x, y) => x.nr.localeCompare(y.nr, 'sv', { numeric: true }) || x.namn.localeCompare(y.namn, 'sv'));
    grupper.forEach(g => {
      const h = document.createElement('p');
      h.className = 'atergrupp';
      h.textContent = g.namn;
      lista.appendChild(h);
      g.rader.sort((x, y) => String(y.datum || '').localeCompare(String(x.datum || ''))).forEach(v => {
        const rad = document.createElement('div');
        rad.className = 'aterrad';
        const anv = v.anvand && v.anvand > 1 ? `använd ${v.anvand} gånger` : '';
        const meta = [v.klass || 'ingen klass',
          v.datum ? (window.Kalender && window.Kalender.ord ? window.Kalender.ord(v.datum) : v.datum) : 'utan datum',
          anv, v.aterbruk ? `återanvänd från ${v.aterbruk.klass || 'tidigare'}` : ''].filter(Boolean).join(' · ');
        rad.innerHTML = `<span class="atertum" data-typ="${v.typ}">${dokminis(v)}</span>
          <span class="atertext"><b></b><span></span></span>
          <button class="chip aterlagg" type="button"${kanLagga ? '' : ' disabled data-tip="Välj en lektion i veckan först"'}>${kanLagga ? `Lägg på ${a.klass || 'lektionen'}` : 'Lägg på lektionen'}</button>
          <button class="aterbort" type="button" data-tip="Ta bort för gott" aria-label="Ta bort ${window.Dokument.namn(v)} för gott">✕</button>`;
        $('.atertext b', rad).textContent = window.Dokument.namn(v);
        $('.atertext>span', rad).textContent = meta;
        $('.aterlagg', rad).addEventListener('click', () => {
          window.Dokument.aterAnvand(v);
          ritaSparatlista();
          ritaDorrar();
          ritaKvitto();
        });
        $('.aterbort', rad).addEventListener('click', () => {
          window.Dokument.radera(v);
          ritaSparatlista();
          ritaDorrar();
          ritaKvitto();
        });
        lista.appendChild(rad);
      });
    });
  }
  const lseg = $('#sparatlage');
  if (lseg) lseg.addEventListener('click', e => {
    const b = e.target.closest('button');
    if (!b || !b.dataset.lage || b.dataset.lage === sparatlage) return;
    sparatlage = b.dataset.lage;
    /* Byter man till «använd oförändrat» är förlagan inte längre vad man menar —
       den skulle annars stå kvar i kvittot och säga att pappret ska skrivas om. */
    if (sparatlage === 'oforandrat' && forlagan() && window.Dokument.slappForlaga) window.Dokument.slappForlaga();
    ritaSparatlista();
    ritaDorrar();
    ritaKvitto();
  });

  /* ── Att slå på och av en dörr ─────────────────────── */
  function satt(d, till, tyst) {
    const knapp = $(`.kalla[data-dorr="${d}"]`, steg);
    knapp.setAttribute('aria-pressed', String(till));
    /* Lektionen får alltid ta uppslaget: det är dörren med förslaget i sig. */
    if (till) { if (!tyst || !uppslagen || d === 'lektion') uppslagen = d; }
    else if (uppslagen === d) uppslagen = null;
    const p = panel(d);
    ritaPaneler();
    if (d === 'lektion') {
      if (till) {
        /* Ingen lektion vald än → ta den appen föreslår. */
        if (!$('#valdalektioner').children.length) {
          const l = senaste();
          if (l && window.Dokument) {
            window.Dokument.valjLektion(l.namn);
            autoValt = l.namn;
            window.Utgang && window.Utgang.rita();
            if (!tyst) window.toast && window.toast(`Utgår från ${l.namn}`);
          }
        }
      } else if (window.Dokument) {
        $$('#valdalektioner .lchip span').map(s => s.textContent).forEach(n => window.Dokument.slappLektion(n));
        autoValt = null;
        window.Utgang && window.Utgang.rita();
      }
    } else if (d === 'sparat') {
      if (!till && window.Dokument && window.Dokument.slappForlaga) {
        window.Dokument.slappForlaga();
      }
      ritaSparatVald();
    } else if (d === 'prov') {
      if (!till && window.Dokument && window.Dokument.slappResultat) window.Dokument.slappResultat();
      ritaProvlista();
    }
    ritaDorrar();
    ritaKvitto();
    if (till && !tyst && p && !p.hidden) {
      const r = p.getBoundingClientRect();
      if (r.bottom > window.innerHeight) (window.rullaTill || (y => window.scrollTo(0, y)))(window.scrollY + r.top - 140, 520);
    }
  }

  dorrar.forEach(b => b.addEventListener('click', () => {
    const d = b.dataset.dorr;
    if (d === 'lektion') rortLektion = true;
    /* Vald men hopfälld → slå upp den. Vald OCH uppslagen → ta bort källan. */
    if (pa(d) && uppslagen !== d) {
      uppslagen = d;
      ritaPaneler();
      const p = panel(d);
      if (p) {
        const r = p.getBoundingClientRect();
        if (r.bottom > window.innerHeight) (window.rullaTill || (y => window.scrollTo(0, y)))(window.scrollY + r.top - 140, 520);
      }
      return;
    }
    satt(d, !pa(d));
  }));
  $$('.kpstang', steg).forEach(b => b.addEventListener('click', () => {
    if (b.dataset.stang === 'lektion') rortLektion = true;
    satt(b.dataset.stang, false);
  }));

  /* ── Kvittot: vad man faktiskt utgår från ───────────
     Inte etiketter, utan innehåll: vilken lektion med vilken klass och när,
     vilken bok och vilka sidor om vad, vilka foton av vad. En rad per källa. */
  function bokinfoRad() {
    const s = window.Uppslag && window.Uppslag.spann ? window.Uppslag.spann() : null;
    if (!s) return null;
    /* Registret måste vara BOKENS eget: läste kvittot alltid 3c:s avsnitt fick
       Matematik 4 s. 178–183 rubriken «4.4 Gränsvärden» — 3c:s avsnitt på samma
       sidnummer. Kvittot är det läraren läser för att kontrollera valet. */
    const A = (window.Bok && window.Bok.registerForBok ? window.Bok.registerForBok(s.bok) : (window.Bok || {}).avsnitt) || [];
    const grans = a => a.sid.split('–').map(Number);
    const inom = A.filter(a => { const [f, t] = grans(a); return t >= s.fran && f <= s.till; });
    const antal = s.till - s.fran + 1;
    const helt = inom.length === 1 && grans(inom[0])[0] === s.fran && grans(inom[0])[1] === s.till;
    const om = inom.length
      ? inom.map(a => `${a.nr} ${a.titel}`).join(' + ')
      : 'utanför registret';
    const bit = [om, `${antal} ${antal === 1 ? 'sida' : 'sidor'}`];
    if (helt && inom[0].uppg) bit.push(`${inom[0].uppg} uppgifter`);
    return { titel: `${s.bok} · s. ${s.fran}–${s.till}`, detalj: bit.join(' · ') };
  }
  function fotoinfoRad() {
    const minis = [...$('#sidminis').children];
    if (!minis.length) return null;    const teman = [...new Set(minis.map(m => {
      const t = $('.sidnamn', m);
      return t ? t.textContent.replace(/\s+—.*$/, '').trim() : '';
    }).filter(Boolean))];
    const typer = [...new Set(minis.map(m => {
      const t = $('.sidnamn', m);
      const d = t && t.textContent.match(/—\s*(.+)$/);
      return d ? d[1].trim() : '';
    }).filter(Boolean))];
    return {
      titel: `${minis.length} ${minis.length === 1 ? 'fil' : 'filer'} ur boken`,
      detalj: [teman.slice(0, 2).join(' + ') || 'tolkas ur rubrikerna', typer.slice(0, 2).join(', ')].filter(Boolean).join(' · ')
    };
  }
  function lektionsinfo(namn) {
    const l = lektioner().find(x => x.namn === namn);
    if (!l) return { titel: namn, detalj: 'transkriberad lektion' };
    return {
      titel: l.namn,
      detalj: ['Transkript', l.klass || 'ingen klass', dagdatum(l.datum), veckonr(l.datum), langden(l.langd)].filter(Boolean).join(' · ')
    };
  }
  const veckonr = d => (d && window.Kalender && window.Kalender.veckonr) ? 'v' + window.Kalender.veckonr(d) : '';

  function ritaKvitto() {
    /* Fotozonen hör till dörren, inte till om något annat råkar vara valt. */
    $('#dropzon').hidden = false;
    const lv = $('#lektionsknapp .valjtext');
    if (lv) lv.textContent = $('#valdalektioner').children.length ? 'Välj en annan lektion' : 'Välj lektion ur listan';
    const ut = $('#kvittoextra');
    ut.innerHTML = '';
    const namn = $$('#valdalektioner .lchip span').map(s => s.textContent);
    namn.forEach(n => {
      const i = lektionsinfo(n);
      ut.appendChild(rad('Lektion', i.titel, i.detalj, () => {
        if (window.Dokument) window.Dokument.slappLektion(n);
        window.Utgang && window.Utgang.rita();
        if (autoValt === n) autoValt = null;
        rortLektion = true;
        if (!$('#valdalektioner').children.length) satt('lektion', false, true);
      }, 'lektion'));
    });
    if (pa('bok')) {
      const b = bokinfoRad();
      if (b) ut.appendChild(rad('Boken', b.titel, b.detalj, () => satt('bok', false), 'bok'));
    }
    if (pa('foton')) {
      const f = fotoinfoRad();
      if (f) ut.appendChild(rad('Egna filer', f.titel, f.detalj, () => satt('foton', false), 'foton'));
    }
    const fl = forlagan();
    if (fl) ut.appendChild(rad('Förlaga', window.Dokument.namn(fl), dokmeta(fl), () => satt('sparat', false), 'sparat'));
    const rs = resultatet();
    if (rs) {
      const sv = ((rs.rattat || {}).svaga || []);
      const detalj = [provkort(rs), sv.length ? sv.map(s => s.formaga || s.text).filter(Boolean).slice(0, 2).join(', ') : '']
        .filter(Boolean).join(' · ');
      ut.appendChild(rad('Resultat', window.Dokument.namn(rs), detalj, () => satt('prov', false), 'prov'));
    }
    /* Har man markerat bort den sista lektionen står panelen tom sånär som på
       listan — inga kort som inte längre gäller. */
    const nat = $('#utgangnat');
    if (nat) nat.hidden = pa('lektion') && !namn.length;
    const nagot = ut.children.length;
    $('#kvittotom').hidden = !!nagot;
    /* Den uppslagna panelen säger redan vad den bär — kvittot är därför bara för
       de källor som ligger hopfällda. Raderna stannar i DOM (canvasen läser dem),
       men den som hör till den öppna panelen döljs, och står inget kvar att läsa
       försvinner hela kvittot i stället för att stå tomt. */
    const kv = $('#kvitto');
    kv.dataset.oppen = uppslagen || '';
    const kvar = [...ut.children].filter(r => (r.dataset.kalla || (r.hasAttribute('data-lmrad') ? 'lektion' : '')) !== (uppslagen || '\u0000')).length;
    kv.toggleAttribute('data-dolt', !kvar);
    kv.toggleAttribute('data-tom', !nagot);
    ritaSparatVald();
  }
  function rad(art, titel, detalj, av, kalla) {
    const r = document.createElement('div');
    r.className = 'krad';
    if (kalla) r.dataset.kalla = kalla;
    r.innerHTML = '<span class="kart"></span><span class="ktext"><b></b><span></span></span><button class="kbort" type="button" data-tip="Ta bort ur underlaget" aria-label="Ta bort ur underlaget">✕</button>';
    $('.kart', r).textContent = art;
    $('.ktext b', r).textContent = titel;
    $('.ktext span', r).textContent = detalj;
    $('.kbort', r).addEventListener('click', av);
    return r;
  }

  /* ── En bok som PDF, på plats i bokpanelen ─────────── */
  (() => {
    const zon = $('#bokladd'), fil = $('#bokfil'), las = $('#boklas');
    if (!zon) return;
    const namnUr = f => String(f || 'Ny bok.pdf').replace(/\.pdf$/i, '').replace(/[_-]+/g, ' ').trim() || 'Ny bok';
    function lasIn(filnamn) {
      const namn = namnUr(filnamn);
      zon.hidden = true;
      las.hidden = false;
      const fyll = $('#boklasfyll'), text = $('.boklastext', las);
      const steg2 = [[18, `Läser ${namn} …`], [56, 'Hittar kapitel och avsnitt …'], [88, 'Indexerar sidorna …'], [100, 'Klar — boken ligger i hyllan']];
      let i = 0;
      const gaVidare = () => {
        const [p, t] = steg2[i];
        fyll.style.width = p + '%';
        text.textContent = t;
        i++;
        if (i < steg2.length) setTimeout(gaVidare, 620);
        else setTimeout(() => {
          las.hidden = true;
          zon.hidden = false;
          fyll.style.width = '0';
          window.Uppslag && window.Uppslag.laggBok && window.Uppslag.laggBok(namn);
          if (!pa('bok')) satt('bok', true, true);
          ritaDorrar();
          ritaKvitto();
          window.toast && window.toast(`${namn} ligger i bokhyllan`);
        }, 700);
      };
      gaVidare();
    }
    zon.addEventListener('click', () => fil.click());
    zon.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fil.click(); } });
    fil.addEventListener('change', () => { if (fil.files && fil.files[0]) lasIn(fil.files[0].name); fil.value = ''; });
    ['dragenter', 'dragover'].forEach(n => zon.addEventListener(n, e => { e.preventDefault(); zon.setAttribute('data-over', ''); }));
    ['dragleave', 'dragend'].forEach(n => zon.addEventListener(n, () => zon.removeAttribute('data-over')));
    zon.addEventListener('drop', e => {
      e.preventDefault();
      zon.removeAttribute('data-over');
      const f = e.dataTransfer && e.dataTransfer.files[0];
      lasIn(f ? f.name : 'Ny bok.pdf');
    });
  })();

  /* ── Håll dörrarna i takt med det som händer i panelerna ── */
  /* Väljer man en lektion i listan ska den också få sitt kort i panelen. */
  new MutationObserver(() => {
    window.Utgang && window.Utgang.rita();
    if ($('#valdalektioner').children.length && !pa('lektion')) satt('lektion', true, true);
    ritaDorrar();
    ritaKvitto();
  }).observe($('#valdalektioner'), { childList: true });
  new MutationObserver(() => {
    if ($('#sidminis').children.length && !pa('foton')) satt('foton', true, true);
    ritaDorrar();
    ritaKvitto();
  }).observe($('#sidminis'), { childList: true });
  $('#bkremsa') && $('#bkremsa').addEventListener('click', () => setTimeout(ritaKvitto, 0));
  $('#bkkapitel') && $('#bkkapitel').addEventListener('click', () => setTimeout(ritaKvitto, 0));
  $('#p-klass') && $('#p-klass').addEventListener('change', () => { syncKlass(); ritaDorrar(); });
  /* Klassen sätts programmatiskt när lektionen klickas i veckan — inget
     change-event kommer. Vi läser om strax efter klicket i stället. */
  $('#schemagrid') && $('#schemagrid').addEventListener('click', () => setTimeout(() => { syncKlass(); ritaDorrar(); }, 80), true);

  /* Byter klassen i veckan byter också den föreslagna lektionen — så länge
     läraren inte själv rört dörren. */
  function syncKlass() {
    if (rortLektion || !pa('lektion')) return;
    const l = senaste();
    if (!l) { satt('lektion', false, true); return; }
    if (autoValt === l.namn) return;
    if (window.Dokument) {
      if (autoValt) window.Dokument.slappLektion(autoValt);
      window.Dokument.valjLektion(l.namn);
      autoValt = l.namn;
      window.Utgang && window.Utgang.rita();
    }
    ritaDorrar();
    ritaKvitto();
  }

  /* ── Förslaget slår till när steget öppnas ─────────── */
  function kanskeForesla() {
    if (steg.hasAttribute('data-last') || rortLektion) return;
    syncKlass();
    if (pa('lektion') || !senaste()) return;
    satt('lektion', true, true);
  }
  new MutationObserver(kanskeForesla).observe(steg, { attributes: true, attributeFilter: ['data-last'] });

  /* Håll fotozonen synlig: äldre kod (och den kompilerade bundlen) speglar
     fortfarande zonen mot «har något valts» och skulle annars gömma den. */
  ['#dropzon'].forEach(sel => {
    const el = $(sel);
    if (!el) return;
    new MutationObserver(() => { if (el.hidden) el.hidden = false; }).observe(el, { attributes: true, attributeFilter: ['hidden'] });
  });

  /* Går man vidare utan att ha markerat något sägs det rakt ut — en gång, i
     förbifarten, utan att stoppa. */
  const fot = steg.querySelector('.stegfot .primar');
  if (fot) fot.addEventListener('click', () => {
    const nagot = $('#valdalektioner').children.length || $('#kvittoextra').children.length;
    if (!nagot) window.toast && window.toast('Skriver utan underlag — bara moment och kursplan');
  });

  /* Förlagan kan sättas också utanför dörren (förhandsvisningen) — då ska dörren
     följa med i stället för att säga emot. */
  function speglaForlaga() {
    const f = forlagan();
    if (f && !pa('sparat')) { satt('sparat', true, true); return; }
    if (!f && pa('sparat')) {
      $('.kalla[data-dorr="sparat"]', steg).setAttribute('aria-pressed', 'false');
      if (uppslagen === 'sparat') uppslagen = null;
      ritaPaneler();
    }
    ritaSparatVald();
    ritaDorrar();
    ritaKvitto();
  }

  /* Resultatet kan också släppas utifrån (när pappret godkänns) — då ska dörren
     följa med i stället för att stå kvar tänd utan innehåll. */
  function speglaResultat() {
    const r = resultatet();
    if (r && !pa('prov')) { satt('prov', true, true); return; }
    if (!r && pa('prov')) {
      $('.kalla[data-dorr="prov"]', steg).setAttribute('aria-pressed', 'false');
      if (uppslagen === 'prov') uppslagen = null;
      ritaPaneler();
    }
    ritaProvlista();
    ritaDorrar();
    ritaKvitto();
  }

  ritaDorrar();
  ritaKvitto();
  ritaPaneler();
  ritaProvlista();
  kanskeForesla();
  /* Fokusfältet står bara där något är valt: utan källor finns inget att väga.
     Raderna i `#kvittoextra` ÄR alla källor — också lektionerna, som ritaKvitto()
     lägger dit en rad var för. Att räkna lektionsbrickorna ovanpå dem räknade
     samma transkript två gånger, och då frågade appen «Vad ska väga tyngst?» med
     en enda källa vald — väga mot vad? */
  function ritaFokus() {
    const ruta = $('#fokusruta');
    if (!ruta) return;
    const n = $('#kvittoextra').children.length;
    ruta.hidden = n < 1;
    const f = $('#fokus');
    /* Med en enda källa finns inget att väga mot något annat — frågan är då vad
       som ska hållas, inte vad som ska väga tyngst. */
    const et = $('#fokusruta .minietikett');
    if (et) et.textContent = n > 1 ? 'Vad ska väga tyngst?' : 'Något att hålla fast vid?';
    if (f) f.placeholder = n > 1
      ? 'T.ex. mest ur provet, lite ur boken — eller ett tema att hålla'
      : 'T.ex. håll det vid det som föll, ta talen ur boken';
  }
  new MutationObserver(ritaFokus).observe($('#kvittoextra'), { childList: true });
  new MutationObserver(ritaFokus).observe($('#valdalektioner'), { childList: true });
  ritaFokus();
  window.Kallor = { satt, ritaKvitto, ritaDorrar, speglaForlaga, ritaProvlista, speglaResultat };
})();
