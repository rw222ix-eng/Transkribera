/* Transkribera — interaktion för app.html. Ingen ramverk, ren DOM. */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

/* ── Flikar ─────────────────────────────────────────── */
const flikar = $$('.flik');
function visaFlik(f) {
  flikar.forEach(o => {
    const pa = o === f;
    o.setAttribute('aria-selected', String(pa));
    $('#' + o.getAttribute('aria-controls')).hidden = !pa;
  });
  window.scrollTo(0, 0);
}
flikar.forEach(f => f.addEventListener('click', () => visaFlik(f)));
/* Flikarna adresseras med NAMN, inte index — en flik kan försvinna (Inspelningar
   gjorde det: lektionerna bor på sin plats i veckan nu) utan att allt förskjuts. */
const flikNamn = n => flikar.find(f => f.textContent.trim() === n) || flikar[0];

/* ── Segmentkontroller (delas av hela appen) ────────── */
document.addEventListener('click', e => {
  const b = e.target.closest('.seg button');
  if (!b) return;
  const seg = b.parentElement;
  if (seg.dataset.flerval) {
    const pa = b.getAttribute('aria-pressed') === 'true';
    if (pa && $$('[aria-pressed="true"]', seg).length === 1) return; // minst ett format
    b.setAttribute('aria-pressed', String(!pa));
  } else {
    $$('button', seg).forEach(o => o.setAttribute('aria-pressed', String(o === b)));
  }
  segBytt(seg, b);
});
function segBytt(seg, b) {
  const namn = seg.dataset.seg;
  if (namn === 'talat' || namn === 'resultat') sprakNot();
  if (namn === 'talat' || namn === 'resultat' || namn === 'format') ritaInst();
  if (namn === 'arkivläge') {
    /* Tre lägen i EN sökruta: fråga appen, sök i orden, eller bläddra bland
       inspelningarna. Lådan under schemat är borta — den var samma sökning en
       gång till, längre ner på sidan. */
    const insp = b.textContent === 'Inspelningar';
    $('#arkivfalt').placeholder = insp
      ? 'Sök bland inspelningarna — namn, klass eller kurs …'
      : 'Fråga om veckan eller lektionerna …';
    $('#arkivknapp').textContent = 'Fråga';
    /* I inspelningsläget filtrerar fältet medan man skriver — då finns inget
       att trycka på. */
    $('#arkivknapp').hidden = insp;
    if (insp) $('#arkivfalt').value = '';
    window.Inspelningar && window.Inspelningar.lage && window.Inspelningar.lage(insp);
    if (insp) setTimeout(() => $('#arkivfalt').focus(), 0);
  }
  /* Rubriken \u00e4gs av l\u00e4geskorten i steg 2 \u2014 inte av den d\u00f6lda skrivtyp-speglingen. */
  if (namn === 'skrivtyp') { window.planKoll && window.planKoll(); }
}
const valt = seg => $(`[data-seg="${seg}"] [aria-pressed="true"]`).textContent;
/* Inspelningsläget söker medan man skriver — ingen knapp att trycka på. */
$('#arkivfalt') && $('#arkivfalt').addEventListener('input', () => {
  if (valt('arkivläge') !== 'Inspelningar') return;
  window.Inspelningar && window.Inspelningar.sokord && window.Inspelningar.sokord($('#arkivfalt').value);
});
/* Whisper känner igen språket själv och rättningspasset bekräftar det — läraren
   väljer bara vad som ska komma ut. */
const talatSprak = () => {
  const e = $('#talat-upptackt');
  const t = (e ? e.textContent : 'svenska').trim().toLowerCase();
  return t.startsWith('eng') ? 'Engelska' : 'Svenska';
};
const valda = seg => $$(`[data-seg="${seg}"] [aria-pressed="true"]`).map(b => b.textContent);

/* ══════════════════ STEG 1–2 ══════════════════ */
let ko = [];
let steg = 1;

/* Prototypens klasser och kurser. Med server byts de mot lärarens egna, ur
   schemat och ur inspelningarna — se hydreraFilter(). */
let KLASSVAL = ['9A', '9B'], KURSVAL = ['Matematik 3c', 'Matematik 4'];
const MANAD = { jan: 0, feb: 1, mar: 2, apr: 3, maj: 4, jun: 5, jul: 6, aug: 7, sep: 8, okt: 9, nov: 10, dec: 11 };
const idag = () => new Date().toISOString().slice(0, 10);
function gissaDatum(namn) {
  let m = namn.match(/(20\d\d)[-_. ]?(0[1-9]|1[0-2])[-_. ]?(0[1-9]|[12]\d|3[01])/);
  if (m) return `${m[1]}-${m[2]}-${m[3]}`;
  m = namn.match(/(\d{1,2})\s*(jan|feb|mar|apr|maj|jun|jul|aug|sep|okt|nov|dec)/i);
  if (m) return `${new Date().getFullYear()}-${String(MANAD[m[2].toLowerCase()] + 1).padStart(2, '0')}-${String(+m[1]).padStart(2, '0')}`;
  return idag();
}
function gissaKurs(namn) {
  const n = namn.toLowerCase();
  if (/3c|derivat|integral|primitiv/.test(n)) return 'Matematik 3c';
  if (/ma4|matematik 4|trigonometr|komplexa|logaritm/.test(n)) return 'Matematik 4';
  return '';
}
const senasteKlass = { 'Matematik 3c': '9A', 'Matematik 4': '9B' };
const datumOrd = iso => {
  const d = new Date((iso || idag()) + 'T12:00:00');
  return isNaN(d) ? 'okänt datum' : d.toLocaleDateString('sv-SE', { day: 'numeric', month: 'long' });
};

function visaSteg(n) {
  steg = n;
  /* Bara transkriberingsvyns steg — planeringens .plansteg bär också data-steg
     och ägs av sin egen stapel. */
  $$('#vy-transkribera [data-steg]').forEach(s => { s.hidden = Number(s.dataset.steg) !== n; });
  $$('#stegrad .stegpost').forEach(p => {
    const i = Number(p.dataset.s), br = $('.bricka', p);
    p.classList.toggle('pa', i === n);
    br.className = 'bricka' + (i === n ? ' pa' : i < n ? ' klar' : '');
    br.textContent = i < n ? '✓' : String(i);
  });
  /* Stegbytet rullar upp — mjukt, aldrig ett hopp. Samma tween som allt annat
     automatiskt i appen (se rullaTill nedan). */
  if (window.scrollY > 2) rullaTill(0); else window.scrollTo(0, 0);
}

let ritade = 0;
function ritaKo() {
  const el = $('#ko-steg1');
  el.innerHTML = '';
  ko.forEach((f, i) => {
    const rad = document.createElement('div');
    rad.className = 'korad';
    if (i >= ritade) rad.dataset.ny = '1';
    rad.innerHTML = `<span class="minietikett kotyp">${f.typ}</span><span class="konamn"></span><span class="kolangd">${f.langd}</span><button class="ta-bort" aria-label="Ta bort">✕</button><span class="komark"><select class="komini" data-f="klass" aria-label="Klass"></select><select class="komini" data-f="kurs" aria-label="Kurs"></select><span class="kodatum" data-tip="Läst ur filens metadata — inspelningsdatum"></span><span class="gissatnot" hidden>Gissat — kontrollera</span><span class="faktarad" hidden><span class="kk">Ur schemat</span><span class="faktatext"></span></span></span>`;
    $('.konamn', rad).textContent = f.namn;
    $('.kodatum', rad).textContent = 'Inspelat ' + datumOrd(f.datum);
    const val = (falt, lista, tomtext) => {
      const s = $(`[data-f="${falt}"]`, rad);
      s.innerHTML = `<option value="">${tomtext}</option>` + lista.map(v => `<option>${v}</option>`).join('');
      s.value = f[falt] || '';
      s.addEventListener('change', () => {
        f[falt] = s.value; f.gissad[falt] = false;
        if (falt === 'kurs' && s.value && !f.klass) { f.klass = senasteKlass[s.value] || ''; f.gissad.klass = !!f.klass; }
        if (falt === 'klass' && s.value && f.kurs) senasteKlass[f.kurs] = s.value;
        ritaKo();
      });
      /* samma väljare som i filtren och planeringen — en app, en dropdown */
      finSelect(s);
      const wrap = s.closest('.valj');
      if (wrap) wrap.toggleAttribute('data-gissad', !!f.gissad[falt]);
    };
    val('klass', KLASSVAL, 'Klass');
    val('kurs', KURSVAL, 'Kurs');
    /* Tre nivåer, inte två: fakta ur schemat (solid ram), gissning (streckad
       ram + källan i notraden) och tomt. Formen betyder «granska mig» oavsett
       varifrån gissningen kom — det är notraden som bär nyansen. */
    const gissar = f.gissad.klass || f.gissad.kurs;
    $('.gissatnot', rad).hidden = !gissar || !!f.schema;
    if (gissar && !f.schema) $('.gissatnot', rad).textContent = 'Gissat ur filnamnet — kontrollera';
    $('.faktarad', rad).hidden = !f.schema;
    if (f.schema) $('.faktatext', rad).textContent = `${f.schema.dagnamn} ${f.schema.tid} · ${f.schema.klass} · ${f.schema.kurs}`;
    $('.ta-bort', rad).addEventListener('click', () => mjukBort(rad, () => { ko.splice(i, 1); ritaKo(); }));
    el.appendChild(rad);
  });
  ritade = ko.length;
  $('#starta').disabled = ko.length === 0;
  const saknar = ko.filter(f => !f.klass || !f.kurs).length;
  $('#skal').textContent = ko.length === 0
    ? 'Lägg till minst en fil, en länk eller en inspelning först.'
    : saknar
      ? `${saknar} av ${ko.length} saknar klass eller kurs — sätt det i raden ovan, eller kör ändå.`
      : `${ko.length} ${ko.length === 1 ? 'källa' : 'källor'} i kö · färdigtaggade för arkivet.`;
}
function gissaTid(namn) {
  /* Datumet plockas bort först — annars läses 2026-08-20 som klockan 20:26. */
  const utan = String(namn).replace(/(20\d\d)[-_. ]?(0[1-9]|1[0-2])[-_. ]?(0[1-9]|[12]\d|3[01])/, ' ');
  let m = utan.match(/(?:^|[^\d])([01]\d|2[0-3])[:.]([0-5]\d)(?:[^\d]|$)/);
  if (!m) m = utan.match(/(?:^|[^\d])([01]\d|2[0-3])([0-5]\d)(?:[^\d]|$)/);
  return m ? `${m[1]}:${m[2]}` : '';
}
function laggTill(namn, langd, kalla) {
  const typ = (namn.split('.').pop() || 'fil').toUpperCase().slice(0, 4);
  let kurs = gissaKurs(namn);
  const datum = gissaDatum(namn);
  let klass = kurs ? (senasteKlass[kurs] || '') : '';
  let gissad = { klass: !!klass, kurs: !!kurs };
  /* Schemat vet vem som hade lektion när filen spelades in. Faller tiden inuti
     en lektion är klass och kurs fakta — inte något läraren ska kontrollera. */
  let schema = null;
  const tid = gissaTid(namn);
  const t = window.Kalender && window.Kalender.traff ? window.Kalender.traff(datum, tid) : null;
  if (t) {
    kurs = t.kurs; klass = t.klass;
    gissad = { klass: false, kurs: false };
    const dn = new Date(datum + 'T12:00:00').toLocaleDateString('sv-SE', { weekday: 'short' }).replace('.', '');
    schema = { tid: t.tid, klass: t.klass, kurs: t.kurs, dagnamn: dn };
    senasteKlass[kurs] = klass;
  }
  /* `kalla` är det servern transkriberar: en sökväg på disk eller en URL. Utan
     server (Claude Design) finns den inte, och kön är då en ren uppvisning. */
  ko.push({ namn, langd: langd || '—', typ, klass, kurs, datum, gissad, schema, kalla });
  ritaKo();
}

/* Filerna läggs på disk innan de hamnar i kön: en lektion får inte bo i en
   webbläsarbuffert som försvinner med fliken. */
async function valjFiler() {
  const val = document.createElement('input');
  val.type = 'file';
  val.multiple = true;
  val.accept = 'audio/*,video/*,.mp3,.wav,.m4a,.mp4,.mkv,.mov,.webm,.flac,.ogg';
  val.addEventListener('change', () => laggUppFiler([...val.files]));
  val.click();
}

async function laggUppFiler(filer) {
  for (const fil of filer) {
    const sek = await window.API.langd(fil);
    const rad = laddarrad(fil.name);
    try {
      const sparad = await window.API.laddaUpp(fil);
      laggTill(fil.name, sek ? window.API.klocka(sek) : '—', sparad.path);
    } catch (e) {
      toast(`${fil.name} kunde inte läggas till: ${e.message}`);
    } finally {
      rad.remove();
    }
  }
}

/* Uppladdningen tar tid på en 70-minuterslektion — kön visar raden medan den
   pågår i stället för att stå tom och se trasig ut. */
function laddarrad(namn) {
  const d = document.createElement('div');
  d.className = 'korad';
  d.innerHTML = '<span class="minietikett kotyp">…</span><span class="konamn"></span><span class="kolangd">lägger till</span>';
  $('.konamn', d).textContent = namn;
  $('#ko-steg1').appendChild(d);
  return d;
}

$('#dropzone').addEventListener('click', () => {
  if (window.API && window.API.pa) valjFiler();
  else laggTill('Mamma waw isolerad.wav', '12:04');
});
$('#dropzone').addEventListener('dragover', e => { e.preventDefault(); $('#dropzone').setAttribute('data-over', ''); });
$('#dropzone').addEventListener('dragleave', () => $('#dropzone').removeAttribute('data-over'));
$('#dropzone').addEventListener('drop', e => {
  e.preventDefault();
  $('#dropzone').removeAttribute('data-over');
  const filer = [...(e.dataTransfer.files || [])];
  if (window.API && window.API.pa && filer.length) laggUppFiler(filer);
  else if (filer.length) filer.forEach(f => laggTill(f.name, '—'));
});
$('#dropzone').addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('#dropzone').click(); } });
$('#lagg-till-lank').addEventListener('click', () => {
  const v = $('#lankfalt').value.trim();
  if (!v) { $('#lankfalt').focus(); return; }
  laggTill(v.replace(/^https?:\/\//, '').slice(0, 48), 'länk', v);
  $('#lankfalt').value = '';
});
$('#lankfalt').addEventListener('keydown', e => { if (e.key === 'Enter') $('#lagg-till-lank').click(); });
$$('[data-exempel]').forEach(b => b.addEventListener('click', async () => {
  const [namn, langd] = b.dataset.exempel.split('|');
  /* Med server pekar «prova ett exempel» på en RIKTIG fil på disken — annars
     hade knappen köat ett filnamn som alltid faller på start. */
  if (window.API && window.API.pa) {
    try {
      const ex = await window.API.json('/api/sample');
      laggTill(ex.name, langd, ex.path);
      return;
    } catch (e) { /* inget exempel på disken — falla igenom till namnet */ }
  }
  laggTill(namn, langd);
}));

/* Inspelning */
let inspelning = null;
$('#spela-in') && $('#spela-in').addEventListener('click', () => {
  const knapp = $('#spela-in'), klocka = $('#inspelningsklocka'), text = $('#inspelningstext');
  $('#inspelningsrad').classList.toggle('spelar', !inspelning);
  if (inspelning) {
    clearInterval(inspelning.timer);
    const s = inspelning.sek;
    laggTill(`Inspelning ${new Date().toLocaleDateString('sv-SE')}.m4a`, klockstr(s));
    inspelning = null;
    knapp.textContent = 'Starta inspelning';
    klocka.hidden = true;
    text.textContent = 'Spela in lektionen direkt — ljudet sparas lokalt';
  } else {
    inspelning = { sek: 0, timer: null };
    knapp.textContent = 'Stoppa inspelning';
    klocka.hidden = false;
    klocka.textContent = '00:00';
    text.textContent = 'Spelar in — ljudet sparas lokalt';
    inspelning.timer = setInterval(() => { inspelning.sek++; klocka.textContent = klockstr(inspelning.sek); }, 1000);
  }
});
const klockstr = s => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;

/* Inställningar */
function ritaInst() { /* Valen syns i sina egna reglage — inget chip att skriva om. */ }
function sprakNot() {
  const talat = talatSprak(), res = valt('resultat');
  const m = $('#modell');
  /* Ingen modell «väljs automatiskt» längre — det finns ett val och det är
     gjort. scribe_v2 kör hos ElevenLabs, och priset står där så att det inte
     är en överraskning på fakturan. */
  if (m) m.textContent = `scribe_v2 hos ElevenLabs (${talat === 'Svenska' ? 'sv' : 'en'}) · $0,22/timme`;
  const not = $('#spraknot');
  if (not) not.textContent = talat === res
    ? `Resultatet blir på ${res.toLowerCase()} — samma som det talade språket.`
    : `Resultatet översätts från ${talat.toLowerCase()} till ${res.toLowerCase()}.`;
}
/* Inga chipspaneler kvar i raden — maskineriet står kvar för framtida paneler. */
const instPar = [];
let instOppen = null;
/* Panelen ligger fast i vyn (position:fixed) och räknas därför inte in i sidans
   höjd. Det tar bort hela klipp-problemet: ingenting krymper när den stängs, så
   ingen korrigeringsrullning behövs. */
/* Panelerna hänger i chipsraden och har alla samma plats och bredd — en enda
   yta som byter innehåll, i stället för tre som letar sin egen kant. */
instPar.forEach(([, pi]) => { const p = $('#' + pi); if (p && p.parentElement !== $('#instrad')) $('#instrad').appendChild(p); });
function stangInst() {
  if (!instOppen) return;
  const { chip, panel } = instOppen;
  instOppen = null;
  chip.setAttribute('aria-expanded', 'false');
  panel.setAttribute('data-ut', '');
  const slut = () => { panel.hidden = true; panel.removeAttribute('data-ut'); };
  panel.addEventListener('animationend', slut, { once: true });
  setTimeout(slut, 140);
  document.removeEventListener('pointerdown', instUtanfor, true);
  document.removeEventListener('keydown', instTangent, true);
}
function instUtanfor(e) {
  if (!instOppen) return;
  const inne = instOppen.chip.closest('.instval').contains(e.target) || instOppen.panel.contains(e.target);
  if (!inne) stangInst();
}
function instTangent(e) { if (e.key === 'Escape' && instOppen) { const c = instOppen.chip; stangInst(); c.focus(); } }
instPar.forEach(([ci, pi]) => {
  const chip = $('#' + ci), panel = $('#' + pi);
  if (!chip || !panel) return;
  chip.addEventListener('click', () => {
    const redanOppen = instOppen && instOppen.chip === chip;
    stangInst();
    if (redanOppen) return;
    panel.hidden = false;
    panel.removeAttribute('data-ut');
    panel.classList.remove('upp');
    /* Får panelen inte plats under raden vänder den uppåt — den ska aldrig hänga
       under vyns kant och tvinga fram en manuell rullning. */
    const rad = $('#instrad').getBoundingClientRect();
    if (rad.bottom + 14 + panel.offsetHeight > window.innerHeight - 16) panel.classList.add('upp');
    chip.setAttribute('aria-expanded', 'true');
    instOppen = { chip, panel };
    setTimeout(() => {
      document.addEventListener('pointerdown', instUtanfor, true);
      document.addEventListener('keydown', instTangent, true);
    }, 0);
  });
  /* Lämnar musen chipet och dess panel stängs menyn av sig själv — en kort
     respit så att vägen ner till panelen inte räknas som ett avhopp. */
  let lamna = null;
  const avbrytLamna = () => { if (lamna) { clearTimeout(lamna); lamna = null; } };
  const kanskeStang = e => {
    if (e.pointerType !== 'mouse' || !instOppen || instOppen.chip !== chip) return;
    avbrytLamna();
    lamna = setTimeout(() => { if (instOppen && instOppen.chip === chip) stangInst(); }, 70);
  };
  [chip.closest('.instval'), panel].forEach(yta => {
    yta.addEventListener('pointerleave', kanskeStang);
    yta.addEventListener('pointerenter', avbrytLamna);
  });
});

/* Steg 2 · körningen */
let klaraFiler = [];
function kvarText(sek) {
  if (sek < 45) return 'under en minut kvar';
  const min = Math.round(sek / 60);
  return `≈ ${min} min kvar`;
}
$('#starta').addEventListener('click', () => {
  visaSteg(2);
  $('#korvarningar').innerHTML = '';
  korAntal = ko.length;
  visaPill(0);
  klaraFiler = ko.slice();
  const lista = $('#progresslista');
  lista.innerHTML = '';
  $('#klarruta').hidden = true;
  $('#steg3-rubrik').textContent = 'Lyssnar igenom …';
  const rader = klaraFiler.map(f => {
    const d = document.createElement('div');
    d.className = 'prograd';
    d.innerHTML = `<div class="progtopp"><span class="pnamn"></span><span class="pkvar"></span><span class="pklocka">0:00</span><span class="ppct">0 %</span></div><div class="spar"><span class="fyll"></span></div><ol class="fassteg"></ol>`;
    $('.pnamn', d).textContent = f.namn;
    const fs = faser(f);
    $('.fassteg', d).innerHTML = fs.map(s => `<li class="fas" data-lage="vantar"${s.moln ? ' data-moln' : ''}><span class="fasikon"></span><span class="fasnamn">${s.namn}</span><span class="fasdetalj"></span></li>`).join('');
    lista.appendChild(d);
    return { el: d, fil: f, fs, noder: [...d.querySelectorAll('.fas')],
             tot: Math.max(35, sekunder(f.langd) * 0.32) };
  });
  const totalSek = rader.reduce((a, r) => a + r.tot, 0);
  /* Foten bär hela sanningen i en mening, i tidsordning: ljudet går ut först
     (och tiderna kommer med svaret), texten går till Claude sist. */
  const FOTTEXT = 'ljudet skickas till ElevenLabs, som transkriberar och sätter tidsstämplarna · sista steget skickar texten till Claude.';
  $('#korkvar').textContent = `${kvarText(totalSek)} · ${FOTTEXT}`;
  if (window.API && window.API.pa) korRiktigt(rader, FOTTEXT);
  else korFejk(rader, totalSek, FOTTEXT);
});

/* ── Riktig körning ───────────────────────────────────────────────────────
   En fil i taget: servern serialiserar jobben mot samma arbiter som övriga
   Claude-jobb, så två parallella hade ändå bara fått vänta — men här syns kön. */
async function korRiktigt(rader, fottext) {
  const t0 = Date.now();
  const klockan = setInterval(() => {
    const gick = mmss(Math.round((Date.now() - t0) / 1000));
    rader.forEach(r => { if (!r.klar && !r.fel) $('.pklocka', r.el).textContent = gick; });
  }, 500);
  let kostnad = 0;
  for (const r of rader) {
    const f = r.fil;
    if (!f.kalla) {
      r.fel = true;
      $('.ppct', r.el).textContent = 'ingen fil';
      varnruta('fel', `${f.namn} finns inte på disken`,
        'Filen lades till utan att laddas upp. Lägg till den igen via rutan högst upp.', [
          { namn: 'Tillbaka till kön', stark: true, gor: d => { d.remove(); visaSteg(1); } }]);
      continue;
    }
    try {
      const svar = await window.API.strom('/api/transcribe', {
        source: f.kalla,
        language: talatSprak() === 'Svenska' ? 'sv' : 'en',
        target_language: valt('resultat') === 'Svenska' ? 'sv' : 'en',
        formats: valda('format').map(x => x.toLowerCase()),
      }, {
        progress: p => {
          $('.fyll', r.el).style.width = p + '%';
          $('.ppct', r.el).textContent = Math.round(p) + ' %';
          ritaFaser(r, p);
          visaPill(p, '');
          $('#korkvar').textContent = `${Math.round(p)} % · ${fottext}`;
        },
        log: m => { r.senasteLogg = m; },
        /* Batch-API:et svarar i ett svep: hela texten kommer som ETT delta när
           molnet är klart. Ordräkningen kvitterar att svaret faktiskt kom. */
        delta: t => {
          r.moln = (r.moln || '') + t;
          const fas = $$('.fas', r.el)[2];
          if (fas) $('.fasdetalj', fas).textContent =
            `${r.moln.trim().split(/\s+/).length} ord mottagna`;
        },
        kostnad: h => { kostnad += h.usd; },
      });
      /* Strömmen kan ta slut utan sitt done — servern kan dö, anslutningen kan
         brytas. Utan den här kontrollen blev det ett JS-fel i konsolen och en
         obegriplig rad i varningsrutan i stället för ett besked. */
      if (!svar) throw new Error('Servern slutade svara mitt i körningen. Filen är orörd — försök igen.');
      r.klar = true;
      r.resultat = svar;
      /* Lektionens id på servern följer med filen: granskningen efteråt ber om
         den riktiga extraktionen på den, i stället för att läsa transkriptet
         med regex här. */
      f.lektionId = svar.lesson_id || null;
      window.transkript = (svar.transcript || []).map(s => [klockstr(Math.round(s.start)), s.text]);
      ritaFaser(r, 100);
      $('.fyll', r.el).style.width = '100%';
      $('.ppct', r.el).textContent = '100 %';
      $('.pkvar', r.el).textContent = '';
    } catch (e) {
      r.fel = true;
      $('.ppct', r.el).textContent = 'avbruten';
      $('.fyll', r.el).style.background = 'var(--berry)';
      const kor = $('.fas[data-lage="kor"]', r.el);
      if (kor) kor.dataset.lage = 'fel';
      varnruta('fel', `${f.namn} gick inte att transkribera`, e.message, [
        { namn: 'Försök igen', stark: true, gor: d => { d.remove(); $('#starta').click(); } },
        { namn: 'Hoppa över filen', gor: d => d.remove() }]);
      klaraFiler = klaraFiler.filter(x => x !== f);
    }
  }
  clearInterval(klockan);
  taBortPill();
  $('#korkvar').textContent = klaraFiler.length
    ? `Klart · ${kostnad ? '$' + kostnad.toFixed(2) + ' hos ElevenLabs · ' : ''}ljudet ligger kvar på datorn, transkriptet är sparat här`
    : 'Ingen fil blev klar.';
  if (klaraFiler.length) klar();
}

/* ── Prototypens klocka ───────────────────────────────────────────────────
   Utan server finns ingen körning att följa. Förloppet spelas upp i samma
   band som servern skulle ha emitterat, så designen visar en sann form. */
function korFejk(rader, totalSek, fottext) {
  let p = 0;
  const t0 = Date.now();
  const timer = setInterval(() => {
    p = Math.min(100, p + 1.6);
    const gick = mmss(Math.round((Date.now() - t0) / 1000));
    rader.forEach(r => {
      if (r.fel) return;
      $('.fyll', r.el).style.width = p + '%';
      $('.ppct', r.el).textContent = Math.round(p) + ' %';
      $('.pklocka', r.el).textContent = gick;
      $('.pkvar', r.el).textContent = p >= 100 ? '' : kvarText(r.tot * (1 - p / 100));
      ritaFaser(r, p);
    });
    const kvarSek = totalSek * (1 - p / 100);
    $('#korkvar').textContent = p >= 100
      ? 'Klart · ljudet transkriberades hos ElevenLabs, tiderna kom med svaret'
      : `${kvarText(kvarSek)} · ${fottext}`;
    visaPill(p, p >= 100 ? '' : kvarText(kvarSek));
    if (p > 21 && p < 23) varningar(ko, rader);
    if (p >= 100) { clearInterval(timer); taBortPill(); klar(); }
  }, 110);
}
function sekunder(langd) {
  const d = String(langd || '').split(':').map(Number);
  return d.length === 2 && d.every(n => !isNaN(n)) ? d[0] * 60 + d[1] : 600;
}
function mmss(s) { const h = Math.max(0, Math.round(s)); return Math.floor(h / 60) + ':' + String(h % 60).padStart(2, '0'); }
/* Faserna speglar serverns egna band (app/web/server.py): molnet 0–60 (texten
   OCH ordtiderna kommer i samma svar), efterarbetet resten. Samma lista används
   av den riktiga körningen och av prototypens klocka — då finns bara ett
   förlopp att hålla sant.

   Två steg lämnar datorn, och de är märkta: ljudet till ElevenLabs, texten till
   Claude. Molnfasen är en väntan utan mellanrapporter — batch-API:et svarar i
   ett svep, och det ska fastexten vara ärlig med. */
function faser(f) {
  const sek = sekunder(f.langd);
  const mb = Math.round(sek / 60 * 1.4 * 10) / 10;
  const fmt = (valda('format').join(' · ') || 'TXT');
  const lista = [
    { namn: 'Läser in filen', fran: 0, till: 4, d: () => `${mb} MB · ${f.langd || '—'}` },
    { namn: 'Komprimerar ljudet', fran: 4, till: 8,
      d: () => '16 kHz Opus · här' },
    { namn: 'Skickar ljudet till ElevenLabs', fran: 8, till: 60, moln: true,
      d: () => 'scribe_v2 · text och ordtider · svaret kommer i ett svep' },
  ];
  lista.push({ namn: 'Skriver ut resultat', fran: 60, till: 96, d: () => fmt });
  lista.push({ namn: 'Sammanfattar och letar förslag', fran: 96, till: 100,
               d: () => 'skickas till Claude · ≈ 1 min', moln: true });
  return lista;
}
function ritaFaser(r, p) {
  r.fs.forEach((s, i) => {
    const li = r.noder[i], det = $('.fasdetalj', li);
    if (p >= s.till) {
      if (li.dataset.lage !== 'klar') { li.dataset.lage = 'klar'; det.textContent = s.d(1); }
    } else if (p >= s.fran) {
      li.dataset.lage = 'kor';
      det.textContent = s.d(Math.min(1, (p - s.fran) / (s.till - s.fran)));
    } else { li.dataset.lage = 'vantar'; det.textContent = ''; }
  });
}
function klar() {
  $('#steg3-rubrik').textContent = klaraFiler.length === 1 ? 'Transkriptet är klart' : 'Transkripten är klara';
  const f0 = klaraFiler[0] || {};
  $('#klarfil').textContent = klaraFiler.length === 1
    ? f0.namn
    : `${klaraFiler.length} filer · ${klaraFiler.map(f => f.langd).join(' + ')}`;
  $('#klartext').textContent = [
    klaraFiler.length === 1 ? f0.langd : null,
    valt('resultat').toLowerCase(),
    'scribe_v2 · text och ordtider från ElevenLabs'
  ].filter(Boolean).join(' · ');
  const kurs = klaraFiler.map(f => f.kurs).filter(Boolean)[0];
  $('#klarsparat').textContent = `Ligger på sin lektion i veckan${kurs ? ' · ' + kurs : ''}.`;
  const chips = $('#klarchips');
  chips.innerHTML = '';
  valda('format').forEach(fmt => {
    const b = document.createElement('button');
    b.className = 'chip';
    b.textContent = fmt;
    b.addEventListener('click', () => toast(`${fmt} laddades ner`));
    chips.appendChild(b);
  });
  $('#klarruta').hidden = false;
  sparaAutomatiskt();
  granskaAutomatiskt();
}

/* Extraktionen körs av sig själv när transkriptet är klart. Att behöva komma ihåg att
   fråga är precis det appen finns för — klarrutan visar redan vad som hittades. */
function extrahera(filer) {
  const t = window.transkript || [];
  const rad = re => t.find(r => re.test(r[1]));
  const kortText = s => {
    /* Ett citat ska kapas mellan orden, aldrig mitt i ett: «låter h gå mot nol…»
       läses som ett stavfel, inte som en förkortning. Citattecknen hör också till —
       raden är något läraren SA, inte appens egna ord. */
    const t = String(s || '').trim();
    if (t.length <= 54) return `”${t}”`;
    const kap = t.slice(0, 54);
    const brytet = kap.lastIndexOf(' ');
    return `”${(brytet > 26 ? kap.slice(0, brytet) : kap).replace(/[\s,;:.–—-]+$/, '')} …”`;
  };
  const f0 = filer[0] || {};
  const ut = [];
  const laxa = rad(/till nästa gång|uppgift/i);
  if (laxa) ut.push({
    titel: 'Arbetsblad på hemuppgiften',
    text: 'Lektionen slutade med en hemuppgift. Jag kan bygga ett arbetsblad på samma innehåll.',
    rader: [['Källa', `${laxa[0]} · ${kortText(laxa[1])}`], ['Kurs', f0.kurs || 'ingen kurs'], ['Format', 'Arbetsblad · 6 uppgifter']],
    knapp: 'Bygg arbetsbladet',
    kort: 'arbetsblad',
    gor: () => { visaFlik(flikNamn('Planering')); toast('Planeringen öppnad — momentet är ifyllt'); }
  });
  const svart = rad(/differenskvot|h går mot noll/i);
  if (svart) ut.push({
    titel: 'Repetera differenskvoten',
    text: 'Två elever tvekade på samma ställe. Det är värt fem minuter nästa lektion.',
    rader: [['Ställe', `${svart[0]} · ${kortText(svart[1])}`], ['Tid', '5 minuter'], ['När', 'Nästa lektion']],
    knapp: 'Lägg på nästa tavla',
    kort: 'repetition',
    gor: () => { visaFlik(flikNamn('Planering')); toast('Lagt som ingång på nästa tavla'); }
  });
  const start = t[0];
  /* Transkriptet vet vad klassen FAKTISKT hann — läget i klassprofilen vet bara
     vilka sidor som stod i planeringen. Därför frågan, en gång, med kvitto på var
     lektionen slutade. Finns inget transkript ställer terminsvyn samma fråga. */
  const slutrad = t[t.length - 1];
  const lage = window.Profil && window.Profil.lageFor && f0.klass ? window.Profil.lageFor(f0.klass, f0.kurs || '') : null;
  if (slutrad && f0.klass) ut.push({
    titel: 'Flytta klassens läge',
    text: 'Så här slutade lektionen. Kom klassen längre än planerat — eller kortare?',
    rader: [['Slutade', `${slutrad[0]} · ${kortText(slutrad[1])}`], ['Klass', f0.klass],
      ['Läge nu', lage && lage.senasteSida ? `s. ${lage.senasteSida}` : 'inte satt']],
    knapp: 'Sätt läget',
    kort: 'läge',
    gor: () => {
      visaFlik(flikNamn('Planering'));
      window.Termin && window.Termin.visa('termin');
      toast('Terminen öppnad — sätt läget på kursen');
    }
  });
  if (start) ut.push({
    titel: 'Prov på momentet',
    text: 'Momentet är genomgånget. Ett prov om två veckor ligger lättast nära i tid.',
    rader: [['Moment', kortText(start[1])], ['Kurs', f0.kurs || 'ingen kurs'], ['Förslag', 'Prov · 12 uppgifter · om två veckor']],
    knapp: 'Skriv provet',
    kort: 'prov',
    kalender: true,
    gor: () => { visaFlik(flikNamn('Planering')); toast('Planeringen öppnad — typ Prov valt'); }
  });
  return ut;
}
/* ══════════ FÖRSLAGEN UR DEN RIKTIGA EXTRAKTIONEN ══════════
   `extrahera()` ovan letar efter fyra fraser med regex — det är vad prototypen
   kan, och det syns: den hittar «till nästa gång» men inte att klassen fastnade
   på något som aldrig sas rakt ut. Servern läser hela lektionen
   (POST /api/lessons/{id}/extract, app/postprocess.extract_full) och svarar med
   insikter i fem slag. Korten är desamma — det är innehållet som blir sant.

   Insikterna sparas samtidigt på lektionen (källa 'llm'), så de finns kvar i
   minnet och i nästa lektions kontext även om läraren stänger rutan. */
const INSIKTSKORT = {
  'svårighet': { titel: 'Repetera det som fastnade', kort: 'repetition', nyckel: 'Ur lektionen',
                 text: 'Det här stannade upp under lektionen. Det är värt fem minuter nästa gång.',
                 knapp: 'Lägg på nästa tavla' },
  'åtgärd': { titel: 'Att följa upp', kort: 'åtgärd', nyckel: 'Sades',
              text: 'Något lämnades öppet på lektionen.', knapp: 'Lägg på nästa tavla' },
  'material': { titel: 'Arbetsblad på hemuppgiften', kort: 'arbetsblad', nyckel: 'Källa',
                text: 'Lektionen slutade med något att öva på. Jag kan bygga ett arbetsblad på samma innehåll.',
                knapp: 'Bygg arbetsbladet' },
  'grupprum': { titel: 'Att ordna före nästa lektion', kort: 'grupprum', nyckel: 'Sades',
                text: 'Något praktiskt sades under lektionen.', knapp: 'Lägg på nästa tavla' },
  'kalender': { titel: 'Lägg in i kalendern', kort: 'kalender', nyckel: 'Sades', kalender: true,
                text: 'En tid nämndes på lektionen. Den ligger inte i kalendern än.',
                knapp: 'Lägg in i kalendern' },
};

function insiktsforslag(insikter, f0) {
  const ut = [];
  (insikter || []).forEach(i => {
    const mall = INSIKTSKORT[i.typ];
    if (!mall || ut.length >= 4) return;
    const rader = [[mall.nyckel, i.text]];
    if (i.due_date) rader.push(['När', window.Kalender && window.Kalender.ord ? window.Kalender.ord(i.due_date) : i.due_date]);
    rader.push(['Klass', f0.klass || 'ingen klass']);
    ut.push({
      titel: mall.titel, text: mall.text, rader, knapp: mall.knapp,
      kort: mall.kort, kalender: !!(mall.kalender && i.due_date),
      /* Kalenderinsikten är den enda som kan göras färdig här: den skriver in
         posten i veckan. De andra öppnar planeringen, som förut. */
      gor: mall.kalender && i.due_date && window.Kalender
        ? () => {
          window.Kalender.lagg({ datum: i.due_date, titel: String(i.text).slice(0, 60),
                                 klass: f0.klass || '', kurs: f0.kurs || '',
                                 slag: 'post', ursprung: 'insikt' });
          window.Klass && window.Klass.rita && window.Klass.rita();
          toast('Inlagt i veckan');
        }
        : () => { visaFlik(flikNamn('Planering')); toast('Planeringen öppnad'); },
    });
  });
  return ut;
}

/* Regexförslagen står framme direkt — den som är klar ska inte vänta på en
   analys — och byts ut mot serverns när den svarat. Svarar den inte alls står
   prototypens kvar, precis som i Claude Design. */
function hamtaInsikter() {
  const f0 = klaraFiler.find(f => f.lektionId);
  if (!f0 || !(window.API && window.API.pa)) return;
  const not = $('#forslagnot');
  const forra = not.textContent;
  not.textContent = 'Läser igenom lektionen …';
  window.API.strom(`/api/lessons/${f0.lektionId}/extract`, {})
    .then(res => {
      const forslag = insiktsforslag(res && res.insights, f0);
      if (!forslag.length) { not.textContent = forra; return; }
      const vard = $('#klarforslag'), rad = $('#granska-forslag');
      vard.innerHTML = '';
      vard.hidden = true;
      rad.setAttribute('aria-expanded', 'false');
      const nsr = $('.nsr', rad);
      if (nsr) nsr.textContent = 'Granska förslagen';
      visaForslag(forslag);
    })
    .catch(() => { not.textContent = forra; });
}

function granskaAutomatiskt() {
  const vard = $('#klarforslag'), rad = $('#granska-forslag');
  if (!vard || !rad) return;
  vard.innerHTML = '';
  vard.hidden = true;
  visaForslag(extrahera(klaraFiler));
  hamtaInsikter();
}

function visaForslag(forslag) {
  const vard = $('#klarforslag'), rad = $('#granska-forslag');
  const antal = $('#forslagantal'), not = $('#forslagnot');
  antal.hidden = !forslag.length;
  antal.textContent = String(forslag.length);
  rad.disabled = !forslag.length;
  if (!forslag.length) {
    not.textContent = 'Inget att föreslå den här gången';
    return;
  }
  not.textContent = forslag.map(f => f.kort).join(' · ');
  rad.onclick = () => {
    if (!vard.childElementCount) forslag.forEach(f => vard.appendChild(forslagKort(f)));
    vard.hidden = !vard.hidden;
    rad.setAttribute('aria-expanded', String(!vard.hidden));
    $('.nsr', rad).textContent = vard.hidden ? 'Granska förslagen' : 'Dölj förslagen';
  };
}
function forslagKort(f) {
  const d = document.createElement('div');
  d.className = 'forslag';
  d.innerHTML = `<p class="forslagtitel"></p><p class="forslagtext"></p>${f.rader.map(([k, v]) => `<div class="forslagrad"><span class="fnyckel">${k}</span><span class="fvarde"></span></div>`).join('')}<div class="forslagknappar"><button class="primar" type="button" data-gor></button><button class="lank" type="button" data-bort>Inte nu</button></div>`;
  $('.forslagtitel', d).textContent = f.titel;
  $('.forslagtext', d).textContent = f.text;
  $$('.forslagrad .fvarde', d).forEach((el, i) => { el.textContent = f.rader[i][1]; });
  if (f.kalender && window.Kalender) {
    const k = window.Kalender.krockrad(window.Kalender.omVeckor(2));
    const r = document.createElement('div');
    r.className = 'forslagrad';
    r.innerHTML = `<span class="fnyckel">Krock</span><span class="fvarde"${k.krock ? ' data-krock' : ''}></span>`;
    $('.fvarde', r).textContent = k.text;
    $('.forslagknappar', d).before(r);
  }
  $('[data-gor]', d).textContent = f.knapp;
  $('[data-gor]', d).addEventListener('click', () => { d.setAttribute('data-inlagt', ''); $('.forslagknappar', d).innerHTML = '<span class="fklar">✓ Inlagt</span>'; f.gor && f.gor(); });
  $('[data-bort]', d).addEventListener('click', () => mjukBort(d, () => d.remove()));
  return d;
}
/* En inspelning hör hemma i den vecka den spelades in — inte i den vecka som
   råkade stå först i markupen. Saknas veckan skapas den på sin plats i tiden. */
function veckogruppFor(iso) {
  const K = window.Kalender;
  const mandag = K && K.mandagen ? K.mandagen(iso) : iso;
  const nr = K && K.veckonr ? K.veckonr(mandag) : Number(isoVecka(new Date(iso + 'T12:00:00')).split('-W')[1]);
  const finns = $(`.veckogrupp[data-mandag="${mandag}"]`) || $(`.veckogrupp[data-vecka="${nr}"][data-mandag]`);
  if (finns) return finns;
  const start = new Date(mandag + 'T12:00:00');
  const slut = new Date(start); slut.setDate(start.getDate() + 4);
  const kort = d => d.toLocaleDateString('sv-SE', { day: 'numeric', month: 'short' }).replace('.', '');
  const g = document.createElement('div');
  g.className = 'veckogrupp skiva';
  g.dataset.vecka = String(nr);
  g.dataset.mandag = mandag;
  g.setAttribute('data-stig', '');
  g.innerHTML = `<div class="grupprubrik"><h2 class="vecka">Vecka ${nr}</h2><span class="spann">${kort(start)} – ${kort(slut)}</span><span class="antal">0 inspelningar</span></div><div class="lista"></div>`;
  const vard = $('#inspelningar');
  const efter = $$('.veckogrupp', vard).find(o => (o.dataset.mandag || '') < mandag);
  efter ? vard.insertBefore(g, efter) : vard.appendChild(g);
  return g;
}
function sparaAutomatiskt() {
  nyssKort = null;
  const rorda = new Set();
  klaraFiler.forEach(f => {
    const grupp = veckogruppFor(f.datum || idag());
    grupp.hidden = false;
    rorda.add(grupp);
    const kort = nyttKort(f);
    grupp.querySelector('.lista').prepend(kort);
    if (!nyssKort) nyssKort = kort;
  });
  void rorda;
  raknaOm();
  /* Veckan i planeringen ritas om — annars står lektionen kvar utan sin
     inspelning trots att notisen säger att den ligger där. */
  window.Klass && window.Klass.rita && window.Klass.rita();
  window.Lektionskal && window.Lektionskal.rita && window.Lektionskal.rita();
  const flera = klaraFiler.length > 1;
  $('#fraga-nyss') && ($('.nsr', $('#fraga-nyss')).textContent = flera ? 'Fråga den första lektionen' : 'Fråga lektionen');
  /* Lektionen har ingen egen hög längre — den ligger på sin plats i veckan. */
  toast('Sparad — ligger på sin lektion i veckan', 'Visa', () => visaFlik(flikNamn('Planering')));
}
let nyssKort = null;
/* Från klarrutan rakt in i samtalet med lektionen — utan att leta upp kortet först.
   Stänger man modalen kommer man tillbaka hit, inte till arkivet man passerade. */
$('#fraga-nyss').addEventListener('click', () => {
  if (!nyssKort || !window.Lektion) return;
  const franSteg = steg;
  /* Lektionsfönstret är ett rum ovanpå sidan — det behöver ingen flik under sig. */
  requestAnimationFrame(() => window.Lektion.oppna(nyssKort, {
    fokus: true,
    tillbaka: () => { visaFlik(flikNamn('Transkribera')); visaSteg(franSteg); }
  }));
});
$('#gor-om').addEventListener('click', () => { ko = []; ritaKo(); visaSteg(1); });
/* "42:11" är en tidsstämpel — "42 min 11 s" är en längd. Korten visar längden. */
const klartext = t => {
  const m = String(t).match(/(\d{1,2}):(\d{2})/);
  if (!m) return t || '';
  const s = Number(m[2]);
  return `${Number(m[1])} min${s ? ' ' + s + ' s' : ''}`;
};
function nyttKort(f) {
  const a = document.createElement('article');
  a.className = 'kort';
  const klass = f.klass || '', kurs = f.kurs || '';
  const iso = f.datum || idag();
  const d = new Date(iso + 'T12:00:00');
  a.dataset.klass = klass; a.dataset.kurs = kurs;
  a.dataset.manad = d.toLocaleDateString('sv-SE', { month: 'short' }).replace('.', '');
  a.dataset.datum = iso;
  /* En hydrerad post VET om den har bild (servern sparade en videofil) och vilka
     språk den kördes med. En nyss klar körning vet det inte om sig själv och
     läser reglagen — som förut. */
  const video = f.video != null ? !!f.video
    : (/\.(mp4|mkv|mov|webm|avi)$/i.test(f.namn) || /^https?:|youtu/i.test(f.namn));
  const talat = f.talat || talatSprak(), mal = f.mal || valt('resultat');
  const langdtext = klartext(f.langd);
  const tum = video
    ? `<div class="tumme" data-typ="video"><image-slot id="tum-${Date.now()}-${Math.round(Math.random() * 1e4)}" shape="rect" placeholder="Bildruta"></image-slot><span class="tumspela"><span>▶</span></span><span class="tumtid">${f.langd}</span></div><span class="tumlangd">${langdtext}</span>`
    : `<div class="tumme" data-typ="ljud"><span class="tumljud">Ljud</span><span class="tumtid">${f.langd}</span></div><span class="tumlangd">${langdtext}</span>`;
  const cc = klass && kurs ? (KURSFARG[kurs] || 'sky') : 'none';
  a.innerHTML = `<div class="tumkol">${tum}</div><div class="text"><p class="datum"><span class="dagnamn">${d.toLocaleDateString('sv-SE', { weekday: 'short' }).replace('.', '')}</span> ${d.toLocaleDateString('sv-SE', { day: 'numeric', month: 'short' })}</p><p class="namn" data-akt="redigera" data-tip="Klicka för att byta namn"></p><span class="tagg" data-cc="${cc}"><button class="taggdel" type="button" data-del="klass"${klass ? '' : ' data-tom'}>${klass || 'Klass'}</button><span class="taggpunkt">·</span><button class="taggdel" type="button" data-del="kurs"${kurs ? '' : ' data-tom'}>${kurs || 'Kurs'}</button></span><p class="meta"><span class="sprakmark"${talat === mal ? '' : ' data-oversatt'} data-tip="${talat === mal ? 'Talad ' + mal.toLowerCase() + ', transkriberad på samma språk' : 'Talad ' + talat.toLowerCase() + ', översatt till ' + mal.toLowerCase()}">${talat === mal ? mal : talat + ' → ' + mal.toLowerCase()}</span></p></div><div class="knappar"><button class="tyst" data-akt="fraga">Fråga</button><button class="mer" data-akt="mer" aria-haspopup="menu" aria-expanded="false" aria-label="Mer">⋯</button></div>`;
  $('.namn', a).textContent = f.namn.replace(/\.[a-z0-9]+$/i, '');
  return a;
}

/* ══════════ HYDRERING · arkivet ur servern ══════════
   Korten i #inspelningar står i app.html för att designprojektet ska visa en
   fylld app utan server. Svarar servern är det DEN som äger listan: de statiska
   korten byts ut mot lärarens riktiga lektioner, EN gång vid start, innan
   filtren, lovbanden och veckan räknas.

   Två källor slås ihop på history_id, för ingen av dem har allt:
   /api/lessons bär organisationen (datum, klass, kurs — det arkivet sorterar
   och filtrerar på) och /api/history bär körningen (talat och målspråk, om det
   finns bild). Att spegla in det saknade fältet i den andra tabellen hade gjort
   samma sanning till två som kan glida isär. */
async function hydreraArkivet() {
  const A = window.API;
  if (!A || !A.pa) return;
  let lektioner, historik;
  try {
    [lektioner, historik] = await Promise.all([A.json('/api/lessons'), A.json('/api/history')]);
  } catch (e) {
    return;                       // servern svarar inte längre: prototypen står kvar
  }
  const kor = new Map((historik || []).map(h => [h.id, h]));
  const vard = $('#inspelningar');
  $$('.veckogrupp', vard).forEach(g => g.remove());
  /* Servern sorterar nyast först — korten läggs i den ordningen, i sin egen
     ISO-vecka (veckogruppFor skapar veckan om den saknas). */
  (lektioner || []).forEach(les => {
    const h = kor.get(les.history_id) || {};
    const datum = les.datum || (les.ts || '').slice(0, 10) || idag();
    const grupp = veckogruppFor(datum);
    grupp.hidden = false;
    grupp.querySelector('.lista').appendChild(nyttKort({
      namn: les.name || 'Namnlös inspelning',
      langd: les.dur || '—',
      klass: les.group || '',
      kurs: les.course || '',
      datum,
      video: !!h.video,
      talat: les.lang || h.lang || 'Svenska',
      mal: h.target_lang || les.lang || 'Svenska',
    }));
  });
  hydreraFilter();
  raknaOm();                      // räknar om rubrikerna och ritar lovbanden (lov.js)
  window.Klass && window.Klass.rita && window.Klass.rita();
  window.Lektionskal && window.Lektionskal.rita && window.Lektionskal.rita();
}

/* Filtren ska erbjuda de klasser och kurser läraren FAKTISKT har: schemat
   först (det är facit), inspelningarna som komplement för det som ligger i
   arkivet men inte i veckan. Samma listor styr kökns två väljare. */
function hydreraFilter() {
  const K = window.Kalender;
  const ur = falt => [...new Set([
    ...((K && K.schema) || []).map(s => s[falt]),
    ...$$('.kort').map(k => k.dataset[falt]),
  ].filter(Boolean))].sort((a, b) => a.localeCompare(b, 'sv'));
  const klasser = ur('klass'), kurser = ur('kurs');
  if (!klasser.length && !kurser.length) return;   // tom server: behåll prototypen
  KLASSVAL = klasser; KURSVAL = kurser;
  const fyll = (sel, tom, lista) => {
    if (!sel) return;
    const forra = sel.value;
    sel.innerHTML = `<option value="">${tom}</option>` + lista.map(v => `<option></option>`).join('');
    [...sel.options].slice(1).forEach((o, i) => { o.textContent = lista[i]; });
    sel.value = lista.includes(forra) ? forra : '';
    sel.dispatchEvent(new Event('change', { bubbles: true }));
  };
  fyll($('#f-klass'), 'Alla klasser', klasser);
  fyll($('#f-kurs'), 'Alla kurser', kurser);
  /* Planeringens egna väljare läser SAMMA listor. De stod hårdkodade i
     app.html, och med ett riktigt schema erbjöd de klasser läraren inte har —
     och saknade dem hon faktiskt undervisar. */
  fyll($('#p-klass'), 'Ingen klass', klasser);
  fyll($('#p-kurs'), 'Ingen kurs', kurser);
  ritaKo();                        // köns klass-/kursväljare läser samma listor
}

/* Schemat först, arkivet sedan: filtren och veckan läser båda, och en halv
   vecka ritad två gånger är sämre än en hel ritad en gång. */
(window.Kalender && window.Kalender.redo ? window.Kalender.redo : Promise.resolve())
  .then(hydreraArkivet);

/* ══════════════════ INSPELNINGAR ══════════════════ */
function raknaOm() {
  $$('.veckogrupp').forEach(g => {
    const synliga = $$('.kort', g).filter(k => !k.hidden);
    $('.antal', g).textContent = `${synliga.length} ${synliga.length === 1 ? 'inspelning' : 'inspelningar'}`;
    if (!$$('.kort', g).length) g.hidden = true;
    else g.hidden = synliga.length === 0;
  });
  const kvar = $$('.kort').filter(k => !k.hidden).length;
  $('#tomrad-filter').hidden = kvar > 0;
}
['#f-klass', '#f-kurs'].forEach(id => $(id).addEventListener('change', filtrera));
function isoVecka(d) {
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  t.setUTCDate(t.getUTCDate() + 4 - (t.getUTCDay() || 7));
  const nyar = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
  return t.getUTCFullYear() + '-W' + String(Math.ceil(((t - nyar) / 864e5 + 1) / 7)).padStart(2, '0');
}
function utanforPeriod(kort) {
  if (!period.typ) return false;
  const iso = kort.dataset.datum;
  if (!iso) return true;
  if (period.typ === 'manad') return iso.slice(0, 7) !== period.v;
  if (period.typ === 'datum') return iso !== period.v;
  return isoVecka(new Date(iso + 'T12:00:00')) !== period.v;
}

/* ── KALENDERFILTER ─────────────────────────────── */
const period = { typ: '', v: '' };
const kalWrap = $('#kalvalj'), kalKnapp = $('#kalknapp');
/* Filtret öppnar på DAGENS månad — aldrig på en månad appen råkade byggas i. */
const kalIdagDatum = () => new Date(((window.Kalender && window.Kalender.idag && window.Kalender.idag()) || isoDag(new Date())) + 'T12:00:00');
const kalDennaManad = () => { const d = kalIdagDatum(); return new Date(d.getFullYear(), d.getMonth(), 1); };
let kalVisad = null, kalPanel = null;
const isoDag = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const manadTitel = d => d.toLocaleDateString('sv-SE', { month: 'long', year: 'numeric' });
function ritaKalKnapp() {
  const t = $('.valjtext', kalKnapp);
  if (!period.typ) { t.textContent = 'Alla datum'; kalWrap.removeAttribute('data-satt'); return; }
  kalWrap.setAttribute('data-satt', '');
  if (period.typ === 'datum') t.textContent = new Date(period.v + 'T12:00:00').toLocaleDateString('sv-SE', { day: 'numeric', month: 'short', year: 'numeric' });
  else if (period.typ === 'vecka') { const [ar, v] = period.v.split('-W'); t.textContent = `Vecka ${Number(v)} · ${ar}`; }
  else { const [ar, m] = period.v.split('-'); t.textContent = manadTitel(new Date(+ar, +m - 1, 1)); }
}
function valj(typ, v) {
  if (period.typ === typ && period.v === v) { period.typ = ''; period.v = ''; }
  else { period.typ = typ; period.v = v; }
  ritaKalKnapp(); filtrera(); stangKal(); kalKnapp.focus();
}
function ritaKalender() {
  const dagar = new Set($$('.kort').map(k => k.dataset.datum).filter(Boolean));
  const idag = (window.Kalender && window.Kalender.idag && window.Kalender.idag()) || isoDag(new Date());
  const idagV = isoVecka(new Date(idag + 'T12:00:00'));
  const ar = kalVisad.getFullYear(), man = kalVisad.getMonth();
  const manV = `${ar}-${String(man + 1).padStart(2, '0')}`;
  const start = new Date(ar, man, 1);
  start.setDate(1 - ((start.getDay() + 6) % 7));
  let rutor = '<span class="kaltopp">v</span>' + ['mån', 'tis', 'ons', 'tor', 'fre', 'lör', 'sön'].map(d => `<span class="kaltopp">${d}</span>`).join('');
  for (let r = 0; r < 6; r++) {
    const mandag = new Date(start); mandag.setDate(start.getDate() + r * 7);
    const vNr = isoVecka(mandag);
    rutor += `<button class="kalvecka" type="button" data-vecka="${vNr}"${vNr === idagV ? ' data-idag' : ''} aria-pressed="${period.typ === 'vecka' && period.v === vNr}" data-tip="Vecka ${Number(vNr.split('-W')[1])}">${Number(vNr.split('-W')[1])}</button>`;
    for (let k = 0; k < 7; k++) {
      const d = new Date(mandag); d.setDate(mandag.getDate() + k);
      const iso = isoDag(d);
      rutor += `<button class="kaldag" type="button" data-dag="${iso}"${d.getMonth() !== man ? ' data-utanfor' : ''}${dagar.has(iso) ? ' data-finns' : ''}${iso === idag ? ' data-idag aria-current="date"' : ''} aria-pressed="${period.typ === 'datum' && period.v === iso}">${d.getDate()}</button>`;
    }
  }
  kalPanel.innerHTML = `<div class="kalhuvud"><button class="kalpil" type="button" data-gar="-1" aria-label="Föregående månad">‹</button><button class="kalman" type="button" aria-pressed="${period.typ === 'manad' && period.v === manV}" data-tip="Filtrera hela månaden">${manadTitel(kalVisad)}</button><button class="kalpil" type="button" data-gar="1" aria-label="Nästa månad">›</button></div>
    <div class="kalrutnat">${rutor}</div>
    <div class="kalfot"><button class="lank" type="button" data-idagknapp>Idag</button><button class="lank" type="button" data-alla>Alla datum</button><span class="kaltips">Klicka dag, veckonummer eller månad</span></div>`;
  $$('.kalpil', kalPanel).forEach(b => b.addEventListener('click', () => {
    kalVisad = new Date(kalVisad.getFullYear(), kalVisad.getMonth() + Number(b.dataset.gar), 1);
    ritaKalender();
  }));
  $('.kalman', kalPanel).addEventListener('click', () => valj('manad', manV));
  $$('.kalvecka', kalPanel).forEach(b => b.addEventListener('click', () => valj('vecka', b.dataset.vecka)));
  $$('.kaldag', kalPanel).forEach(b => b.addEventListener('click', () => valj('datum', b.dataset.dag)));
  $('[data-idagknapp]', kalPanel).addEventListener('click', () => {
    const d = new Date(idag + 'T12:00:00');
    if (d.getFullYear() !== kalVisad.getFullYear() || d.getMonth() !== kalVisad.getMonth()) {
      kalVisad = new Date(d.getFullYear(), d.getMonth(), 1);
      ritaKalender();
    } else valj('datum', idag);
  });
  $('[data-alla]', kalPanel).addEventListener('click', () => { period.typ = ''; period.v = ''; ritaKalKnapp(); filtrera(); stangKal(); });
}
function stangKal() {
  if (!kalPanel) return;
  const p = kalPanel; kalPanel = null;
  p.setAttribute('data-ut', '');
  p.addEventListener('animationend', () => p.remove(), { once: true });
  setTimeout(() => p.remove(), 140);
  kalWrap.removeAttribute('data-oppen');
  kalKnapp.setAttribute('aria-expanded', 'false');
  document.removeEventListener('pointerdown', kalUtanfor, true);
  document.removeEventListener('keydown', kalTangent, true);
}
const kalUtanfor = e => { if (!kalWrap.contains(e.target)) stangKal(); };
const kalTangent = e => { if (e.key === 'Escape') { stangKal(); kalKnapp.focus(); } };
function oppnaKal() {
  if (kalPanel) return stangKal();
  kalVisad = kalDennaManad();
  if (period.typ === 'datum') kalVisad = new Date(period.v + 'T12:00:00');
  if (period.typ === 'manad') kalVisad = new Date(period.v + '-01T12:00:00');
  kalPanel = document.createElement('div');
  kalPanel.className = 'kalpanel';
  kalPanel.setAttribute('role', 'dialog');
  kalPanel.setAttribute('aria-label', 'Välj period');
  kalWrap.appendChild(kalPanel);
  kalWrap.setAttribute('data-oppen', '');
  kalKnapp.setAttribute('aria-expanded', 'true');
  ritaKalender();
  centreraPanel(kalPanel);
  document.addEventListener('pointerdown', kalUtanfor, true);
  document.addEventListener('keydown', kalTangent, true);
}
kalKnapp.addEventListener('click', oppnaKal);
if (matchMedia('(hover:hover) and (pointer:fine)').matches) {
  let kalFordrojd;
  kalWrap.addEventListener('pointerenter', () => clearTimeout(kalFordrojd));
  kalWrap.addEventListener('pointerleave', e => {
    if (e.pointerType === 'touch') return;
    kalFordrojd = setTimeout(() => { if (kalPanel) stangKal(); }, 70);
  });
}
ritaKalKnapp();
function filtrera() {
  const k = $('#f-klass').value, ku = $('#f-kurs').value;
  $$('.kort').forEach(kort => {
    kort.hidden = (k && kort.dataset.klass !== k) || (ku && kort.dataset.kurs !== ku) || utanforPeriod(kort);
    const d = kort.nextElementSibling;
    if (d && d.classList.contains('detalj')) d.hidden = kort.hidden;
  });
  raknaOm();
}

/* Ett fält, två verb. Inget läge att ställa in i förväg — man väljer i samma
   ögonblick man vet vad man vill: fråga eller söka ord. */
$('#soknapp').addEventListener('click', () => sok('fraga'));
$('#sokordknapp').addEventListener('click', () => sok('ord'));
$('#sokfalt').addEventListener('keydown', e => { if (e.key === 'Enter') sok('fraga'); });
function rensaTraffar() { $$('.traffar,.traffrad').forEach(t => t.remove()); }
function tidFor(rad) { return rad[0]; }
function visaTraffar(kort, rader, q) {
  const l = q.toLowerCase();
  const rubrik = document.createElement('p');
  rubrik.className = 'traffrad';
  rubrik.textContent = `${rader.length} ${rader.length === 1 ? 'träff' : 'träffar'} i transkriptet`;
  const lista = document.createElement('div');
  lista.className = 'traffar';
  rader.forEach(([t, txt]) => {
    const b = document.createElement('button');
    b.className = 'traff';
    b.type = 'button';
    const i = txt.toLowerCase().indexOf(l);
    const fore = txt.slice(Math.max(0, i - 34), i), efter = txt.slice(i + q.length, i + q.length + 46);
    b.innerHTML = `<span class="ttid">${t}</span><span></span>`;
    b.lastChild.append(document.createTextNode((i > 34 ? '… ' : '') + fore));
    const m = document.createElement('mark');
    m.textContent = txt.slice(i, i + q.length);
    b.lastChild.append(m, document.createTextNode(efter + '…'));
    b.addEventListener('click', ev => { ev.stopPropagation(); window.Lektion.oppna(kort, { hoppa: t }); });
    lista.appendChild(b);
  });
  $('.text', kort).append(rubrik, lista);
}
function sok(lage) {
  const q = $('#sokfalt').value.trim();
  if (!q) { $('#sokfalt').focus(); return; }
  rensaTraffar();
  $('#fragavard').hidden = true;
  const kort = $$('.kort');
  if (lage === 'ord') {
    const l = q.toLowerCase();
    let antal = 0, traffar = 0;
    kort.forEach(k => {
      const rubrikTraff = ($('.namn', k).textContent + ' ' + $('.tagg', k).textContent).toLowerCase().includes(l);
      const rader = (window.transkript || []).filter(([, t]) => t.toLowerCase().includes(l));
      k.hidden = !rubrikTraff && !rader.length;
      if (!k.hidden) { antal++; traffar += rader.length; if (rader.length) visaTraffar(k, rader, q); }
    });
    raknaOm();
    const v = $('#fragavard');
    v.hidden = false;
    v.innerHTML = '<div class="fsvar" data-lage="klar"><p class="ftext"></p></div>';
    $('.ftext', v).textContent = antal
      ? `${traffar} träffar i ${antal} ${antal === 1 ? 'lektion' : 'lektioner'} — klicka på en tidsmarkör för att höra stället.`
      : `Inget i transkripten matchar ”${q}”.`;
    return;
  }
  kort.forEach(k => { k.hidden = false; });
  raknaOm();
  const synliga = kort.filter(k => !k.hidden);
  const kallor = synliga.slice(0, 3).map((k, i) => {
    const r = window.transkript[Math.min(i + 1, window.transkript.length - 1)] || ['', ''];
    return { titel: $('.namn', k).textContent.trim(), tid: r[0], text: r[1], kort: k };
  });
  /* Citaten ligger i själva svaret — hovra för en snabbtitt, klicka för att spela
     upp lektionen framspolad till stället. Ingen separat källrad behövs. */
  const t = window.transkript;
  fragaKallor = {};
  const cit = (i, kort) => {
    const r = t[Math.min(i, t.length - 1)];
    fragaKallor[r[0]] = { kort, rad: r[1] };
    return `[[${r[0]}|${r[1].slice(0, 46).trim()}]]`;
  };
  const namn = k => $('.namn', k).textContent.trim();
  /* Lektionsnamnet är också en källa: markerad text som inte går att klicka på
     ser ut som en trasig länk. Namnet pekar på lektionens första rad. */
  const namnLank = (kort, i) => {
    const r = t[Math.min(i, t.length - 1)];
    fragaKallor[r[0]] = { kort, rad: r[1] };
    return `[[${r[0]}|${namn(kort)}]]`;
  };
  const k0 = synliga[0], k1 = synliga[1] || synliga[0];
  window.Fraga.kor($('#fragavard'), {
    fraga: q,
    omfang: `${synliga.length} lektioner · ${synliga.length * 41} minuter tal`,
    antal: synliga.length,
    svar: `Det gicks igenom i ${namnLank(k0, 0)} — ${cit(1, k0)} — och följdes upp veckan efter med ${cit(2, k1)}. Svaret bygger på det som faktiskt sades, inte på lektionsrubrikerna.`,
    plan: [
      { namn: 'Söker i transkripten', detalj: synliga.length + ' lektioner' },
      { namn: 'Väljer ut relevanta avsnitt', detalj: '2 avsnitt' },
      { namn: 'Läser avsnitten i sin helhet', detalj: '00:42–28:05' },
      { namn: 'Skriver svar med citat', detalj: '' }
    ]
  });
}

/* ── CITAT I SÖKSVARET ──────────────────────────── */
let fragaKallor = {};
(() => {
  const vard = $('#fragavard'), pop = $('#fragapop');
  if (!vard || !pop) return;
  let popTimer = null;
  const stangPop = () => { pop.hidden = true; pop.innerHTML = ''; };
  function visaPop(m, peka) {
    const k = fragaKallor[m.dataset.t];
    if (!k) return;
    pop.innerHTML = '<p class="kallrad"></p><div class="kallmeta"><span class="kalltid"></span><span class="kallnamn"></span><span class="kallgor">▶ Spela upp</span></div>';
    $('.kallrad', pop).textContent = '”' + k.rad + '”';
    $('.kalltid', pop).textContent = m.dataset.t;
    $('.kallnamn', pop).textContent = $('.namn', k.kort).textContent.trim();
    pop.hidden = false;
    const rutor = [...m.getClientRects()];
    const r = (peka && rutor.find(x => peka.y >= x.top - 2 && peka.y <= x.bottom + 2)) || rutor[0] || m.getBoundingClientRect();
    const kv = (pop.offsetParent || vard).getBoundingClientRect();
    const bredd = Math.min(360, kv.width - 24);
    pop.style.width = bredd + 'px';
    pop.style.left = Math.round(Math.min(Math.max(12, r.left - kv.left + r.width / 2 - bredd / 2), Math.max(12, kv.width - bredd - 12))) + 'px';
    const over = r.top - kv.top - pop.offsetHeight - 10;
    pop.style.top = Math.round(over > 8 ? over : r.bottom - kv.top + 10) + 'px';
  }
  vard.addEventListener('pointerover', e => {
    const m = e.target.closest('.kallmark');
    if (!m) return;
    clearTimeout(popTimer);
    visaPop(m, { x: e.clientX, y: e.clientY });
  });
  vard.addEventListener('pointerout', e => {
    if (!e.target.closest('.kallmark')) return;
    clearTimeout(popTimer);
    popTimer = setTimeout(stangPop, 90);
  });
  vard.addEventListener('focusin', e => { const m = e.target.closest('.kallmark'); if (m) visaPop(m); });
  vard.addEventListener('focusout', e => { if (e.target.closest('.kallmark')) stangPop(); });
  vard.addEventListener('keydown', e => {
    const m = e.target.closest('.kallmark');
    if (m && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); m.click(); }
  });
  vard.addEventListener('click', e => {
    const m = e.target.closest('.kallmark');
    if (!m) return;
    const k = fragaKallor[m.dataset.t];
    if (!k || !window.Lektion) return;
    stangPop();
    window.Lektion.spelaUpp(k.kort, m.dataset.t);
  });
  window.addEventListener('resize', stangPop);
})();

const transkript = window.transkript = [
  ['00:42', 'Vi börjar med att titta på vad en derivata egentligen mäter.'],
  ['04:11', 'Någon som kan ge ett exempel på förändringshastighet?'],
  ['12:36', 'Här skriver vi differenskvoten och låter h gå mot noll.'],
  ['28:05', 'Till nästa gång: uppgift 3.14 till 3.22.']
];
function bytNamn(kort) {
  const n = $('.namn', kort);
  if ($('.namnfalt', kort)) return $('.namnfalt', kort).focus();
  const gammalt = n.textContent;
  const inp = document.createElement('input');
  inp.className = 'field namnfalt';
  inp.value = gammalt;
  inp.setAttribute('aria-label', 'Namn på inspelningen');
  n.replaceWith(inp);
  inp.focus(); inp.select();
  const stang = spara => {
    if (!inp.isConnected) return;
    const v = inp.value.trim();
    n.textContent = spara && v ? v : gammalt;
    inp.replaceWith(n);
    if (spara && v && v !== gammalt) toast('Namnet ändrades');
  };
  inp.addEventListener('click', e => e.stopPropagation());
  inp.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); stang(true); }
    if (e.key === 'Escape') { e.preventDefault(); stang(false); }
  });
  inp.addEventListener('blur', () => stang(true));
}
function raderaKort(kort) {
  const foralder = kort.parentElement, index = [...foralder.children].indexOf(kort);
  mjukBort(kort, raknaOm);
  raknaOm();
  toast('Inspelningen raderades', 'Ångra', () => {
    kort.removeAttribute('style');
    const barn = foralder.children[index];
    barn ? foralder.insertBefore(kort, barn) : foralder.appendChild(kort);
    raknaOm();
  });
}
/* Menyn ligger vid sidan av prickarna, och prickarna stänger den de öppnade */
function placeraMeny(knapp, p) {
  p.style.left = 'calc(100% + 8px)';
  p.style.right = 'auto';
  const r = p.getBoundingClientRect();
  if (r.right > window.innerWidth - 12) { p.style.left = 'auto'; p.style.right = 'calc(100% + 8px)'; p.style.transformOrigin = 'right center'; }
  const r2 = p.getBoundingClientRect();
  if (r2.bottom > window.innerHeight - 12) p.style.transform = `translateY(calc(-50% + ${Math.round(window.innerHeight - 12 - r2.bottom)}px))`;
  else if (r2.top < 12) p.style.transform = `translateY(calc(-50% + ${Math.round(12 - r2.top)}px))`;
}
function radmeny(knapp, kort) {
  if (Date.now() - Number(knapp.dataset.stangd || 0) < 320) return;
  const gammal = knapp.parentElement.querySelector('.radmeny');
  if (gammal) { gammal.remove(); knapp.setAttribute('aria-expanded', 'false'); return; }
  const p = document.createElement('div');
  p.className = 'radmeny';
  p.innerHTML = '<button data-m="ner">Ladda ner transkript</button><button data-m="plan">Planera nästa lektion</button><hr /><button class="farlig" data-m="del">Radera lektion och transkript</button>';
  knapp.parentElement.appendChild(p);
  knapp.setAttribute('aria-expanded', 'true');
  placeraMeny(knapp, p);
  const stang = () => { p.remove(); knapp.setAttribute('aria-expanded', 'false'); document.removeEventListener('pointerdown', ut, true); };
  const ut = ev => {
    if (p.contains(ev.target)) return;
    if (knapp.contains(ev.target)) knapp.dataset.stangd = String(Date.now());
    stang();
  };
  setTimeout(() => document.addEventListener('pointerdown', ut, true), 0);
  p.addEventListener('click', e => {
    const b = e.target.closest('[data-m]');
    if (!b) return;
    e.stopPropagation();
    const m = b.dataset.m;
    stang();
    if (m === 'plan') window.planeraFran && window.planeraFran({ namn: $('.namn', kort).textContent.trim(), tagg: $('.tagg', kort).textContent });
    if (m === 'ner') toast('SRT laddades ner');
    if (m === 'del') raderaKort(kort);
  });
}
document.addEventListener('click', e => {
  const kort = e.target.closest('.kort');
  if (!kort) return;
  const b = e.target.closest('[data-akt]');
  if (b) {
    e.stopPropagation();
    if (b.dataset.akt === 'fraga') window.Lektion.oppna(kort, { lage: 'fraga' });
    if (b.dataset.akt === 'redigera') bytNamn(kort);
    if (b.dataset.akt === 'mer') radmeny(b, kort);
    return;
  }
  if (e.target.closest('.tagg,.namnfalt,.traffar,.radmeny')) return;
  window.Lektion.oppna(kort);
});

/* ── Toast ──────────────────────────────────────────── */
let toastEl = null, toastTimer = null;
function toast(text, knapp, cb) {
  if (toastEl) stangToast(toastEl);
  clearTimeout(toastTimer);
  toastEl = document.createElement('div');
  toastEl.className = 'toast';
  const s = document.createElement('span');
  s.textContent = text;
  toastEl.appendChild(s);
  if (knapp) {
    const b = document.createElement('button');
    b.textContent = knapp;
    b.addEventListener('click', () => { cb(); stangToast(toastEl); toastEl = null; });
    toastEl.appendChild(b);
  }
  document.body.appendChild(toastEl);
  /* Pillret ligger fast i nederkanten och kan därför hamna över det den handlar om
     — köns remsa eller stegets knapp. Krockar det, lyfts det över i stället för
     att läggas på. */
  requestAnimationFrame(() => {
    if (!toastEl) return;
    const t = toastEl.getBoundingClientRect();
    if (!t.height) return;
    let hogst = 0;
    document.querySelectorAll('.konrad:not([hidden]),#lektionsrad:not([hidden]),.plansteg:not([hidden]):not([data-last]) .primar,#dokument:not([hidden]) .primar').forEach(e => {
      const r = e.getBoundingClientRect();
      if (!r.height || r.top > window.innerHeight || r.bottom < 0) return;
      if (t.top < r.bottom && t.bottom > r.top && t.left < r.right && t.right > r.left) {
        hogst = Math.max(hogst, window.innerHeight - r.top + 14);
      }
    });
    if (hogst > 28) toastEl.style.bottom = Math.min(hogst, window.innerHeight - t.height - 24) + 'px';
  });
  toastTimer = setTimeout(() => { if (toastEl) { stangToast(toastEl); toastEl = null; } }, 5000);
}

ritaKo();


/* ══════════════════ EGNA DROPDOWNS ══════════════════ */
/* När en panel öppnas rullar sidan så att den hamnar mitt i vyn — bara vid öppning,
   och bara när panelen faktiskt inte får plats i bild. */
function centreraPanel(panel) {
  if (!panel) return;
  requestAnimationFrame(() => {
    const r = panel.getBoundingClientRect();
    if (!r.height) return;
    const marginal = 20;
    const synlig = r.top >= marginal && r.bottom <= window.innerHeight - marginal;
    if (synlig) return;
    const delta = (r.top + r.height / 2) - window.innerHeight / 2;
    if (Math.abs(delta) < 24) return;
    rullaTill(Math.max(0, window.scrollY + delta));
  });
}
/* Egen tween — browserns "smooth" hoppar ofta rakt fram mitt i en pekhändelse.
   Samma kurva och tid som resten av systemet (--dur-4 / --ease). */
let rullning = null;
function rullaTill(mal, tid = 620, mjukStart = false) {
  /* Även med reduced motion tweenar vi — men kortare. Ett rakt hopp läses som en bugg. */
  if (matchMedia('(prefers-reduced-motion:reduce)').matches) tid = Math.min(tid, 700);
  if (rullning) cancelAnimationFrame(rullning);
  /* CSS:ens scroll-behavior:smooth skulle annars smeta ut varje enskilt tween-steg
     till en egen browseranimation — då syns bara browserns kurva, aldrig vår. */
  const rotElement = document.documentElement;
  rotElement.style.scrollBehavior = 'auto';
  const fran = window.scrollY, strackan = mal - fran, t0 = performance.now();
  const kurva = mjukStart
    ? t => (t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)
    : t => 1 - Math.pow(1 - t, 3);
  const avbryt = () => { if (rullning) cancelAnimationFrame(rullning); rullning = null; stadaAv(); };
  const stadaAv = () => {
    window.removeEventListener('wheel', avbryt, { passive: true });
    window.removeEventListener('touchstart', avbryt, { passive: true });
    window.removeEventListener('keydown', avbryt);
  };
  window.addEventListener('wheel', avbryt, { passive: true });
  window.addEventListener('touchstart', avbryt, { passive: true });
  window.addEventListener('keydown', avbryt);
  const steg = nu => {
    const t = Math.min(1, (nu - t0) / tid);
    window.scrollTo(0, fran + strackan * kurva(t));
    if (t < 1) rullning = requestAnimationFrame(steg);
    else { rullning = null; rotElement.style.scrollBehavior = ''; stadaAv(); }
  };
  rullning = requestAnimationFrame(steg);
}
/* Samma tween, men för en rullande låda: trådar, listor och paneler ska flytta
   sig lika mjukt som sidan. All automatisk rullning i appen går genom rullaTill
   eller rullaLada — direkta hopp (scrollTop = …, behavior:'smooth') läses som
   en bugg och används inte. */
const ladRull = new WeakMap();
function rullaLada(box, mal, tid = 620) {
  if (!box) return;
  if (matchMedia('(prefers-reduced-motion:reduce)').matches) tid = Math.min(tid, 300);
  const forra = ladRull.get(box);
  if (forra) cancelAnimationFrame(forra);
  const fran = box.scrollTop;
  const till = Math.max(0, Math.min(box.scrollHeight - box.clientHeight, mal));
  if (Math.abs(till - fran) < 1) { box.scrollTop = till; return; }
  const t0 = performance.now(), kurva = t => 1 - Math.pow(1 - t, 3);
  const avbryt = () => { const r = ladRull.get(box); if (r) cancelAnimationFrame(r); ladRull.delete(box); box.removeEventListener('wheel', avbryt); box.removeEventListener('touchstart', avbryt); };
  box.addEventListener('wheel', avbryt, { passive: true });
  box.addEventListener('touchstart', avbryt, { passive: true });
  const steg = nu => {
    const t = Math.min(1, (nu - t0) / tid);
    box.scrollTop = fran + (till - fran) * kurva(t);
    if (t < 1) ladRull.set(box, requestAnimationFrame(steg));
    else { ladRull.delete(box); box.removeEventListener('wheel', avbryt); box.removeEventListener('touchstart', avbryt); }
  };
  ladRull.set(box, requestAnimationFrame(steg));
}
window.rullaTill = rullaTill;
window.rullaLada = rullaLada;
window.centreraPanel = centreraPanel;
const harHover = () => matchMedia('(hover:hover) and (pointer:fine)').matches;
function finSelect(sel) {
  const wrap = document.createElement('div');
  wrap.className = 'valj';
  sel.parentNode.insertBefore(wrap, sel);
  wrap.appendChild(sel);
  const knapp = document.createElement('button');
  knapp.type = 'button';
  knapp.className = 'valjknapp';
  knapp.setAttribute('aria-haspopup', 'listbox');
  knapp.setAttribute('aria-expanded', 'false');
  knapp.innerHTML = '<span class="valjtext"></span><span class="valjpil"></span>';
  wrap.appendChild(knapp);
  const text = $('.valjtext', knapp);
  const rita = () => {
    const o = sel.options[sel.selectedIndex];
    text.textContent = o ? o.textContent : '';
    if (sel.value) wrap.setAttribute('data-satt', ''); else wrap.removeAttribute('data-satt');
  };
  /* värdet kan sättas programmatiskt (t.ex. när man bygger vidare på ett dokument) —
     då måste knapptexten följa med, inte bara den dolda selecten */
  sel.addEventListener('change', rita);
  let panel = null;
  const stang = () => {
    if (!panel) return;
    const p = panel; panel = null;
    p.setAttribute('data-ut', '');
    p.addEventListener('animationend', () => p.remove(), { once: true });
    setTimeout(() => p.remove(), 140);
    wrap.removeAttribute('data-oppen');
    knapp.setAttribute('aria-expanded', 'false');
    document.removeEventListener('pointerdown', utanfor, true);
    document.removeEventListener('keydown', tangent, true);
  };
  const utanfor = e => { if (!wrap.contains(e.target)) stang(); };
  const tangent = e => {
    if (e.key === 'Escape') { stang(); knapp.focus(); return; }
    if (!panel) return;
    const rader = [...panel.querySelectorAll('.valjrad')];
    const i = rader.indexOf(document.activeElement);
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      rader[Math.max(0, Math.min(rader.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)))].focus();
    }
  };
  const oppna = (utanFokus) => {
    if (panel) return stang();
    panel = document.createElement('div');
    panel.className = 'valjpanel';
    panel.setAttribute('role', 'listbox');
    [...sel.options].forEach((o, i) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'valjrad';
      b.setAttribute('role', 'option');
      b.setAttribute('aria-selected', String(i === sel.selectedIndex));
      b.innerHTML = '<span class="valjbock">✓</span><span></span>';
      b.lastChild.textContent = o.textContent;
      b.addEventListener('click', () => {
        sel.selectedIndex = i;
        rita();
        stang();
        knapp.focus();
        sel.dispatchEvent(new Event('change', { bubbles: true }));
      });
      panel.appendChild(b);
    });
    wrap.appendChild(panel);
    wrap.setAttribute('data-oppen', '');
    knapp.setAttribute('aria-expanded', 'true');
    centreraPanel(panel);
    if (!utanFokus) (panel.querySelectorAll('.valjrad')[Math.max(0, sel.selectedIndex)] || panel.firstChild).focus();
    document.addEventListener('pointerdown', utanfor, true);
    document.addEventListener('keydown', tangent, true);
  };
  knapp.addEventListener('click', () => oppna());
  if (harHover()) {
    let fordrojd;
    wrap.addEventListener('pointerenter', () => clearTimeout(fordrojd));
    wrap.addEventListener('pointerleave', e => {
      if (e.pointerType === 'touch') return;
      fordrojd = setTimeout(() => { if (panel) stang(); }, 70);
    });
  }
  sel.addEventListener('change', rita);
  rita();
  return wrap;
}
$$('select.field').forEach(finSelect);


/* ── DAGVÄLJAREN — en kalender, överallt i appen ──
   Samma panel som datumfiltret på Inspelningar: månadshuvud med pilar,
   veckonummer i vänsterkanten, dagrutnätet och tiden som ett eget fält under.
   Den bor i en funktion i stället för i planeringens eget steg, för att provets
   dag i steg 3 ska vara EXAKT samma väljare — inte två fält som ser ut som
   ett formulär.

   val: { tom, dag:false — ingen kalender, bara klockslagen,
          span:true — två klockslag och ett längdval i stället för ett klockslag,
          langd(), sattLangd(min), snabb:[60,90,120] } */
function dagvaljare(wrap, knapp, input, tidInput, val) {
  if (!input || !wrap || !knapp) return null;
  val = typeof val === 'string' ? { tom: val } : (val || {});
  const visaDag = val.dag !== false, spann = !!val.span;
  const langd = () => Math.max(5, Number(val.langd ? val.langd() : 0) || 60);
  const iMin = t => { const d = String(t || '').split(':'); return d.length === 2 ? (+d[0]) * 60 + (+d[1]) : NaN; };
  const klocka = m => `${String(Math.floor((((m % 1440) + 1440) % 1440) / 60)).padStart(2, '0')}:${String(((m % 60) + 60) % 60).padStart(2, '0')}`;
  const slutTid = () => (isNaN(iMin(tidInput.value)) ? '' : klocka(iMin(tidInput.value) + langd()));

  /* Kalendern öppnar alltid på DAGENS månad — aldrig på en månad appen råkade
     vara byggd i. Är ett datum redan satt vinner det (se oppna()). */
  const dennaManad = () => { const n = new Date(); return new Date(n.getFullYear(), n.getMonth(), 1); };
  let visad = dennaManad(), panel = null;
  const rita = () => {
    const d = input.value && visaDag
      ? new Date(input.value + 'T12:00:00').toLocaleDateString('sv-SE', { weekday: 'short', day: 'numeric', month: 'short' }).replace(/\./g, '')
      : '';
    const tid = spann
      ? (tidInput.value ? `${tidInput.value}–${slutTid()}` : '')
      : tidInput.value;
    /* En väljare som lovar en DAG måste också säga när dagen saknas. Förr föll
       den tomma dagen bara ur strängen: raden hette «Dag och klockslag» medan
       knappen visade «09:15–10:45 · 90 min» utan att avslöja vilken dag. */
    const dagdel = visaDag ? (d || (tidInput.value ? 'Välj dag' : '')) : '';
    const bitar = spann ? [dagdel, tid, `${langd()} min`] : [dagdel, tid];
    $('.valjtext', knapp).textContent = bitar.filter(Boolean).join(' · ') || (val.tom || 'Välj datum och tid');
    input.value || tidInput.value ? wrap.setAttribute('data-satt', '') : wrap.removeAttribute('data-satt');
  };
  const dagIso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  /* Värdet kan sättas programmatiskt — planeringskön fyller fälten när en lektion
     väljs. Utan de här två raderna stod knappen kvar på «Välj datum och tid»
     medan dokumentet redan hade både dag och klockslag. */
  input.addEventListener('change', () => rita());
  tidInput.addEventListener('change', () => rita());

  /* Klockslagen rullas fram med hjulet — rutan är ett vred, inte ett
     formulärfält. Ingen tangentbordsinmatning: fem minuter per knäpp (shift ger
     femton) träffar varje rimligt provklockslag, och då finns inget halvskrivet
     värde att normalisera. */
  const blink = f => {
    f.setAttribute('data-rullar', '');
    clearTimeout(f._t);
    f._t = setTimeout(() => f.removeAttribute('data-rullar'), 300);
  };
  function tidfalt(f, satt) {
    f.addEventListener('wheel', ev => {
      ev.preventDefault();
      const steg = ev.shiftKey ? 15 : 5;
      const nu = iMin(f.value), bas = isNaN(nu) ? (iMin(tidInput.value) || 480) : nu;
      f.value = klocka(bas + (ev.deltaY < 0 ? steg : -steg));
      satt(f.value);
      synk();
      blink(f);
    }, { passive: false });
  }
  /* Längden är samma vred som klockslagen — den sitter i raden, inte i en egen
     chipsmeny under. Hjulet ger fem minuter per knäpp (shift femton) och klicket
     hoppar mellan standardlängderna, så snabbvalen finns kvar i samma ruta. */
  function langdfalt(f) {
    const satt = m => {
      if (val.sattLangd) val.sattLangd(Math.min(600, Math.max(5, m)));
      synk();
    };
    f.addEventListener('wheel', ev => {
      ev.preventDefault();
      satt(langd() + (ev.deltaY < 0 ? 1 : -1) * (ev.shiftKey ? 15 : 5));
      blink(f);
    }, { passive: false });
    f.addEventListener('click', () => {
      const p = val.snabb || [60, 90, 120];
      satt(p[(p.indexOf(langd()) + 1) % p.length]);
      blink(f);
    });
  }
  function synk() {
    rita();
    /* Panelen slås upp ur DOM:en, inte ur closuren: raden kan ha ritats om under
       tiden, och då pekar closuren på ett borttaget element. */
    const p = wrap.querySelector('.kalpanel');
    if (!p) return;
    const s = $('.kt-start', p), e = $('.kt-slut', p);
    if (s && document.activeElement !== s) s.value = tidInput.value;
    if (e && document.activeElement !== e) e.value = slutTid();
    const l = $('.kt-langd', p);
    if (l) l.value = String(langd());
  }
  function ritaPanel() {
    /* Panelen kan vara stängd när ritningen kommer: knapparna INNE i den
       (månadspilarna, dagarna, «Idag») ritar om panelen, och ett klick som
       råkar landa medan den fälls ihop — eller ett andra klick på knappen som
       öppnade den — har redan nollat referensen. Förr blev det «Cannot set
       properties of null» och datumväljaren slutade svara. Samma vakt som
       synk() redan har. */
    if (!panel) return;
    const ar = visad.getFullYear(), man = visad.getMonth();
    const start = new Date(ar, man, 1);
    start.setDate(1 - ((start.getDay() + 6) % 7));
    const idag = (window.Kalender && window.Kalender.idag && window.Kalender.idag()) || dagIso(new Date());
    const idagV = isoVecka(new Date(idag + 'T12:00:00'));
    let rutor = '<span class="kaltopp">v</span>' + ['mån', 'tis', 'ons', 'tor', 'fre', 'lör', 'sön'].map(d => `<span class="kaltopp">${d}</span>`).join('');
    for (let r = 0; r < 6; r++) {
      const mandag = new Date(start); mandag.setDate(start.getDate() + r * 7);
      rutor += `<span class="kalvecka"${isoVecka(mandag) === idagV ? ' data-idag' : ''} style="display:grid;place-items:center;cursor:default">${Number(isoVecka(mandag).split('-W')[1])}</span>`;
      for (let k = 0; k < 7; k++) {
        const d = new Date(mandag); d.setDate(mandag.getDate() + k);
        const iso = dagIso(d);
        /* Kalendern kan schemat: lovdagar och redan bokade dagar märks ut, så att
           ingen lägger ett prov mitt i sommarlovet utan att se det. */
        const K = window.Kalender;
        const lov = K && K.lovFor ? K.lovFor(iso) : null;
        const bokat = K && K.forDatum ? K.forDatum(iso) : [];
        const lekt = K && K.schemaFor ? K.schemaFor(iso) : [];
        const tips = lov ? lov.namn
          : bokat.length ? bokat.map(p => `${p.tid} ${p.titel}`).join(' · ')
            : lekt.length ? `${lekt.length} lektioner` : '';
        rutor += `<button class="kaldag" type="button" data-dag="${iso}"${d.getMonth() !== man ? ' data-utanfor' : ''}${lov ? ' data-lov' : ''}${bokat.length ? ' data-bokat' : ''}${!lov && lekt.length ? ' data-finns' : ''}${iso === idag ? ' data-idag aria-current="date"' : ''}${tips ? ` data-tip="${tips.replace(/"/g, '&quot;')}"` : ''} aria-pressed="${input.value === iso}">${d.getDate()}</button>`;
      }
    }
    const kalender = visaDag
      ? `<div class="kalhuvud"><button class="kalpil" type="button" data-gar="-1" aria-label="Föregående månad">‹</button><span class="kalman" style="cursor:default;text-align:center">${visad.toLocaleDateString('sv-SE', { month: 'long', year: 'numeric' })}</span><button class="kalpil" type="button" data-gar="1" aria-label="Nästa månad">›</button></div>
      <div class="kalrutnat">${rutor}</div>`
      : '';
    const tidbit = spann
      ? `<div class="kaltid"${visaDag ? '' : ' data-forst'}><span class="kaltidrubrik">Mellan vilka klockslag — och hur länge</span>
          <div class="kaltidrad"><input class="kaltidfalt kt-start" type="text" readonly tabindex="-1" value="${tidInput.value}" aria-label="Börjar — rulla för att ändra" data-tip="Rulla för att ändra — shift för femton minuter" /><span class="kaltilltext">till</span><input class="kaltidfalt kt-slut" type="text" readonly tabindex="-1" value="${slutTid()}" aria-label="Slutar — rulla för att ändra" data-tip="Rulla för att ändra — shift för femton minuter" /><input class="kaltidfalt kt-langd" type="text" readonly tabindex="-1" value="${langd()}" aria-label="Längd i minuter — rulla för att ändra" data-tip="Rulla för att ändra längden — klicka för 60, 90, 120 minuter" /><span class="kaltilltext">min</span></div></div>`
      : `<div class="kaltid"><span class="kaltidrubrik">Tid</span><input class="kaltidfalt kt-start" type="text" inputmode="numeric" maxlength="5" placeholder="––:––" value="${tidInput.value}" aria-label="Tid, timmar och minuter" /></div>`;
    panel.innerHTML = kalender + tidbit
      + `<div class="kalfot"${visaDag ? '' : ' data-mitten'}>${visaDag ? '<button class="kalater" type="button" data-idagknapp>Idag</button>' : ''}<button class="kalater" type="button" data-rensa>${spann ? 'Återställ' : 'Rensa'}</button></div>`;
    /* «Idag» bläddrar först hem till dagens månad, och väljer dagen först när man
       redan står där — samma ordning som datumfiltret på Inspelningar. */
    const idagKnapp = $('[data-idagknapp]', panel);
    if (idagKnapp) idagKnapp.addEventListener('click', () => {
      const d = new Date(idag + 'T12:00:00');
      if (d.getFullYear() !== visad.getFullYear() || d.getMonth() !== visad.getMonth()) {
        visad = new Date(d.getFullYear(), d.getMonth(), 1);
        return ritaPanel();
      }
      input.value = idag;
      input.dispatchEvent(new Event('change', { bubbles: true }));
      ritaPanel();
    });
    $$('.kalpil', panel).forEach(b => b.addEventListener('click', () => {
      visad = new Date(visad.getFullYear(), visad.getMonth() + Number(b.dataset.gar), 1);
      ritaPanel();
    }));
    /* Dagen stänger inte panelen: nästan alltid vill man sätta klockslaget i
       samma öppning. Panelen stängs av att man går ut ur den. */
    $$('.kaldag', panel).forEach(b => b.addEventListener('click', () => {
      input.value = b.dataset.dag;
      input.dispatchEvent(new Event('change', { bubbles: true }));
      ritaPanel();
      const f = $('.kt-start', panel);
      if (f && !tidInput.value) f.focus();
    }));
    tidfalt($('.kt-start', panel), t => {
      tidInput.value = t;
      synk();
      tidInput.dispatchEvent(new Event('change', { bubbles: true }));
    });
    const slut = $('.kt-slut', panel);
    if (slut) tidfalt(slut, t => {
      const b = iMin(tidInput.value), e = iMin(t);
      if (isNaN(b) || isNaN(e) || !val.sattLangd) return;
      val.sattLangd(Math.min(600, Math.max(5, (e > b ? e : e + 1440) - b)));
      synk();
    });
    const lf = $('.kt-langd', panel);
    if (lf) langdfalt(lf);
    /* Ett prov börjar alltid någonstans: återställningen tar bort DAGEN, aldrig
       klockslaget — det faller tillbaka på lektionens egen starttid. */
    $('[data-rensa]', panel).addEventListener('click', () => {
      if (val.aterstall) {
        /* Återställningen är schemats, inte det handsattas: den som satt tiden för
           hand ska få tillbaka lektionens längd OCH etiketten «ur schemat». */
        tidInput.value = val.standardTid || tidInput.value || '08:15';
        if (visaDag) input.value = '';
        val.aterstall();
        synk();
        stang();
        return;
      }
      if (spann) {
        if (visaDag) input.value = '';
        tidInput.value = val.standardTid || tidInput.value || '08:15';
      } else { input.value = ''; tidInput.value = ''; }
      synk();
      stang();
      input.dispatchEvent(new Event('change', { bubbles: true }));
      tidInput.dispatchEvent(new Event('change', { bubbles: true }));
    });
    synk();
  }
  function stang() {
    if (!panel) return;
    const p = panel; panel = null;
    p.setAttribute('data-ut', '');
    p.addEventListener('animationend', () => p.remove(), { once: true });
    setTimeout(() => p.remove(), 140);
    wrap.removeAttribute('data-oppen');
    knapp.setAttribute('aria-expanded', 'false');
    document.removeEventListener('pointerdown', utanfor, true);
    document.removeEventListener('keydown', tangent, true);
  }
  const utanfor = e => { if (!wrap.contains(e.target)) stang(); };
  const tangent = e => { if (e.key === 'Escape') { stang(); knapp.focus(); } };
  function oppna() {
    if (panel) return stang();
    visad = input.value ? new Date(input.value + 'T12:00:00') : dennaManad();
    panel = document.createElement('div');
    panel.className = 'kalpanel';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', 'Välj datum');
    /* Hjulet inne i panelen tillhör panelen: rullar man på ett klockslag ändras
       tiden, och rullar man någon annanstans i den händer ingenting. data-egenrull
       håller appens mjuka sidscroll borta — den fastnar annars i sidan bakom
       redan i capture-fasen, innan fältet hinner säga nej. */
    panel.setAttribute('data-egenrull', '');
    panel.addEventListener('wheel', ev => ev.preventDefault(), { passive: false });
    wrap.appendChild(panel);
    wrap.setAttribute('data-oppen', '');
    knapp.setAttribute('aria-expanded', 'true');
    ritaPanel();
    centreraPanel(panel);
    document.addEventListener('pointerdown', utanfor, true);
    document.addEventListener('keydown', tangent, true);
  }
  knapp.addEventListener('click', oppna);
  if (matchMedia('(hover:hover) and (pointer:fine)').matches) {
    let f;
    wrap.addEventListener('pointerenter', () => clearTimeout(f));
    wrap.addEventListener('pointerleave', e => { if (e.pointerType === 'touch') return; f = setTimeout(() => { if (panel) stang(); }, 70); });
  }
  rita();
  return { rita, stang };
}
window.Dagvaljare = dagvaljare;
dagvaljare($('#pdatumvalj'), $('#pdatumknapp'), $('#p-datum'), $('#p-tid'));


/* ── KLASS OCH KURS DIREKT I TAGGEN ─────────────── */
const KLASSER = ['9A', '9B'], KURSER = ['Matematik 3c', 'Matematik 4'];
const KURSFARG = { 'Matematik 3c': 'sky', 'Matematik 4': 'sage' };
document.addEventListener('click', e => {
  const del = e.target.closest('.taggdel');
  if (!del) return;
  const tagg = del.closest('.tagg'), kort = del.closest('.kort');
  if (tagg.querySelector('.minipanel')) return stangMini(tagg);
  const arKlass = del.dataset.del === 'klass';
  const lista = arKlass ? KLASSER : KURSER;
  const nu = arKlass ? kort.dataset.klass : kort.dataset.kurs;
  const panel = document.createElement('div');
  panel.className = 'minipanel';
  panel.setAttribute('role', 'listbox');
  panel.innerHTML = [...lista, ''].map(v => `<button class="minirad" type="button" role="option" data-v="${v}" aria-selected="${(nu || '') === v}"><span class="minibock">✓</span><span>${v || (arKlass ? 'Ingen klass' : 'Ingen kurs')}</span></button>`).join('');
  panel.style.left = (del.offsetLeft - 4) + 'px';
  tagg.appendChild(panel);
  del.setAttribute('aria-expanded', 'true');
  centreraPanel(panel);
  $$('.minirad', panel).forEach(r => r.addEventListener('click', () => {
    const v = r.dataset.v;
    if (arKlass) kort.dataset.klass = v; else kort.dataset.kurs = v;
    del.textContent = v || (arKlass ? 'Klass' : 'Kurs');
    del.toggleAttribute('data-tom', !v);
    tagg.dataset.cc = kort.dataset.klass && kort.dataset.kurs ? (KURSFARG[kort.dataset.kurs] || 'sky') : 'none';
    stangMini(tagg);
    filtrera();
  }));
  const ut = ev => { if (!tagg.contains(ev.target)) { stangMini(tagg); document.removeEventListener('pointerdown', ut, true); } };
  setTimeout(() => document.addEventListener('pointerdown', ut, true), 0);
  /* Samma hovergest som appens övriga väljare: lämnar pekaren taggen stängs panelen. */
  let taggFordrojd;
  if (!tagg.dataset.hovrar) {
    tagg.dataset.hovrar = '1';
    tagg.addEventListener('pointerenter', () => clearTimeout(taggFordrojd));
    tagg.addEventListener('pointerleave', e => {
      if (e.pointerType === 'touch') return;
      taggFordrojd = setTimeout(() => stangMini(tagg), 70);
    });
  }
});
function stangMini(tagg) {
  const p = tagg.querySelector('.minipanel');
  if (!p) return;
  p.setAttribute('data-ut', '');
  p.addEventListener('animationend', () => p.remove(), { once: true });
  setTimeout(() => p.remove(), 140);
  $$('.taggdel', tagg).forEach(d => d.setAttribute('aria-expanded', 'false'));
}


/* ══════════════════ KÖRNINGEN LEVER UTANFÖR FLIKEN ══════════════════ */
let pillEl = null, korAntal = 0;
function visaPill(p, eta) {
  if (!pillEl) {
    pillEl = document.createElement('button');
    pillEl.className = 'korpill';
    pillEl.type = 'button';
    pillEl.innerHTML = '<span class="pring"></span><span class="ptext">Transkriberar</span><span class="peta"></span>';
    pillEl.addEventListener('click', () => { visaFlik(flikNamn('Transkribera')); visaSteg(2); });
    $('#korruta').appendChild(pillEl);
  }
  $('.pring', pillEl).style.setProperty('--p', Math.round(p) + '%');
  $('.ptext', pillEl).textContent = `Transkriberar ${korAntal} ${korAntal === 1 ? 'fil' : 'filer'}`;
  $('.peta', pillEl).textContent = eta || '';
}
function taBortPill() {
  if (!pillEl) return;
  const p = pillEl;
  pillEl = null;
  p.classList.add('ut');
  p.style.opacity = '0';
  setTimeout(() => p.remove(), 300);
}

/* ══════════════════ FEL OCH GRÄNSFALL ══════════════════ */
function varnruta(ton, rubrik, under, knappar) {
  const d = document.createElement('div');
  d.className = 'varnruta';
  d.dataset.ton = ton;
  d.innerHTML = `<span class="varnikon">${ton === 'fel' ? '!' : 'i'}</span><div class="varntext"><p></p><p class="under"></p><div class="varnknappar"></div></div>`;
  $('p', d).textContent = rubrik;
  $('.under', d).textContent = under;
  knappar.forEach(k => {
    const b = document.createElement('button');
    b.className = k.stark ? 'primar' : 'ghost';
    b.textContent = k.namn;
    b.addEventListener('click', () => k.gor(d));
    $('.varnknappar', d).appendChild(b);
  });
  $('#korvarningar').appendChild(d);
  return d;
}
let varnatFor = new Set();
function varningar(filer, rader) {
  filer.forEach((f, i) => {
    if (varnatFor.has(f.namn)) return;
    if (/skadad|corrupt/i.test(f.namn)) {
      varnatFor.add(f.namn);
      const r = rader[i];
      if (r) {
        r.fel = true;
        const kor = $('.fas[data-lage="kor"]', r.el) || $$('.fas', r.el)[1];
        if (kor) kor.dataset.lage = 'fel';
        $$('.fas', r.el).forEach(x => { if (x !== kor && x.dataset.lage !== 'klar') x.dataset.lage = 'vantar'; });
        $('.fyll', r.el).style.background = 'var(--berry)';
        $('.ppct', r.el).textContent = 'avbruten';
      }
      klaraFiler = klaraFiler.filter(x => x !== f);
      varnruta('fel', `${f.namn} går inte att läsa`, 'Ljudströmmen bryts efter 00:12. Filen är kvar orörd på disken.', [
        { namn: 'Försök med annan avkodare', stark: true, gor: d => { d.remove(); toast('Kör om med ffmpeg-avkodaren'); } },
        { namn: 'Hoppa över filen', gor: d => { d.remove(); toast('Filen hoppades över'); } }
      ]);
    } else if (/english|lecture|eng\b/i.test(f.namn) && valt('resultat') === 'Svenska') {
      varnatFor.add(f.namn);
      varnruta('info', 'Den här filen låter som engelska', `${f.namn} verkar vara på engelska. Språket känns igen automatiskt — resultatet översätts till svenska eftersom det är valt resultatspråk.`, [
        { namn: 'Behåll engelska i resultatet', stark: true, gor: d => { d.remove(); const b = $$('[data-seg="resultat"] button').find(x => x.textContent === 'Engelska'); if (b) b.click(); toast('Resultatet blir på engelska'); } },
        { namn: 'Översätt till svenska', gor: d => d.remove() }
      ]);
    }
  });
}

/* ══════════════════ ALLT LIGGER LOKALT ══════════════════ */
/* Säkerhetskopian går till en plats man faktiskt pekar ut — disk, USB eller mapp.
   Ingen dold destination, och den valda platsen blir automatisk framåt. */
const PLATSER = [
  { id: 'c', namn: 'Windows (C:)', typ: 'Systemdisk', ledigt: '84 GB ledigt', vag: 'C:\\Users\\larare\\Transkribera' },
  { id: 'd', namn: 'Data (D:)', typ: 'Intern disk', ledigt: '1,2 TB ledigt', vag: 'D:\\Transkribera' },
  { id: 'e', namn: 'KINGSTON (E:)', typ: 'USB-minne · inkopplad nu', ledigt: '46 GB ledigt', vag: 'E:\\Transkribera', senast: true },
  { id: 'n', namn: 'lararhemma (\\\\skolan)', typ: 'Nätverksplats', ledigt: '220 GB ledigt', vag: '\\\\skolan\\lararhemma\\Transkribera' },
  { id: 'annan', namn: 'Välj annan mapp …', typ: 'Bläddra på datorn', ledigt: '', vag: '' }
];
(() => {
  const skal = $('#platsskal');
  if (!skal) return;
  let valdPlats = PLATSER.find(p => p.senast) || PLATSER[0];
  let auto = true;
  const tangent = e => { if (e.key === 'Escape') stang(); };
  function rita() {
    const lista = $('#pl-lista');
    lista.innerHTML = '';
    PLATSER.forEach(p => {
      const b = document.createElement('button');
      b.className = 'platsrad';
      b.type = 'button';
      b.setAttribute('role', 'option');
      b.setAttribute('aria-selected', String(p === valdPlats));
      b.innerHTML = '<span class="platsbock">✓</span><span class="platstext"><span class="platsnamn"></span><span class="platstyp"></span></span><span class="platsledigt"></span>';
      $('.platsnamn', b).textContent = p.namn;
      $('.platstyp', b).textContent = p.typ;
      $('.platsledigt', b).textContent = p.ledigt;
      b.addEventListener('click', () => {
        valdPlats = p;
        if (p.id === 'annan' && !p.vag) p.vag = 'D:\\Skola\\Backup\\Transkribera';
        rita();
        $('#pl-vag').focus({ preventScroll: true });
      });
      lista.appendChild(b);
    });
    $('#pl-vag').value = valdPlats.vag;
  }
  function oppna() {
    rita();
    skal.hidden = false;
    requestAnimationFrame(() => skal.setAttribute('data-pa', ''));
    document.addEventListener('keydown', tangent);
  }
  function stang() {
    skal.removeAttribute('data-pa');
    setTimeout(() => { skal.hidden = true; }, 220);
    document.removeEventListener('keydown', tangent);
  }
  /* ══ SÄKERHETSKOPIAN PÅ RIKTIGT ══
     Rutan räknade upp till hundra procent och sa att kopian skrevs. Servern
     skriver den nu — databasen, historiken och inställningarna som en zip på
     lärarens EGNA plats (POST /api/backup). Går platsen inte att skriva till
     hamnar kopian i appens exports/ och kvittot säger det: en kopia man tror
     finns är värre än ingen.

     «Varje kväll» sparas som en inställning och sköts av servern medan den är
     igång — mer kan en lokal app inte lova, och kvittot lovar inte mer. */
  const klart = (vag, res) => {
    const bt = $('#backuptext');
    if (bt) bt.textContent = new Date().toLocaleDateString('sv-SE', { day: 'numeric', month: 'short' });
    const mb = res && res.bytes ? ` · ${(res.bytes / 1048576).toFixed(1)} MB` : '';
    const plats = (res && res.plats) || vag;
    toast(res && res.fallback
      ? `${plats} gick inte att skriva till — kopian ligger i appens exports-mapp${mb}`
      : `Säkerhetskopian skrevs till ${plats}${mb}${auto ? ' · sker nu varje kväll appen är igång' : ''}`);
  };

  function kopiera() {
    const vag = $('#pl-vag').value.trim() || valdPlats.vag;
    stang();
    const b = $('#backup');
    if (b.disabled) return;
    const gammal = b.textContent;
    b.disabled = true;
    if (window.API && window.API.pa) {
      b.textContent = 'Kopierar …';
      window.API.json('/api/backup', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vag, auto }),
      }).then(res => { b.textContent = gammal; b.disabled = false; klart(vag, res); })
        .catch(e => {
          b.textContent = gammal;
          b.disabled = false;
          toast(e.message || 'Säkerhetskopian gick inte att skriva.');
        });
      return;
    }
    let p = 0;
    const t = setInterval(() => {
      p += 12;
      b.textContent = `Kopierar … ${Math.min(100, p)} %`;
      if (p < 100) return;
      clearInterval(t);
      b.textContent = gammal;
      b.disabled = false;
      klart(vag, null);
    }, 180);
  }
  $('#backup').addEventListener('click', oppna);
  $('#pl-stang').addEventListener('click', stang);
  $('#pl-avbryt').addEventListener('click', stang);
  $('#pl-kor').addEventListener('click', kopiera);
  skal.addEventListener('pointerdown', e => { if (e.target === skal) stang(); });
  $('#pl-auto').addEventListener('click', () => {
    const b = $('#pl-auto');
    auto = b.getAttribute('aria-pressed') !== 'true';
    b.setAttribute('aria-pressed', String(auto));
    b.style.background = auto ? 'var(--accent)' : 'var(--track)';
    b.style.borderColor = auto ? 'var(--accent)' : 'var(--line)';
    $('.knopp', b).style.transform = auto ? 'translateX(16px)' : 'translateX(0)';
  });
})();


ritaInst();
