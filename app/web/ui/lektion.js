/* ══════════ LEKTIONEN — spelaren och tråden ══════════
   Transkriptet visas aldrig som lista: citaten i svaren ÄR transkriptet.
   Hovra en blåmarkerad del för att se raden, klicka för att spola dit. */
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const skal = $('#lektionsskal');
  if (!skal) return;
  const spelrad = $('#l-spelrad'), stor = $('#l-stor'), trad = $('#l-trad'), pop = $('#l-pop');
  const radfot = $('#l-radfot'), fot = $('#l-fot'), kropp = $('#l-kropp');
  const sek = t => { const d = String(t).split(':').map(Number); return d.length === 2 ? d[0] * 60 + d[1] : 0; };
  const mmss = s => Math.floor(s / 60) + ':' + String(Math.round(s % 60)).padStart(2, '0');

  const vskal = $('#videoskal');
  let aktiv = null, nr = 0, tillbaka = null;
  /* Kom man hit från ett citat i ett svar är videon hela ärendet — då ska
     stängningen lämna en tillbaka i svaret, inte i lektionschatten bakom. */
  let baraVideo = false;

  /* ── uppspelningen: ett eget rum, framspolat till citatet ── */
  function oppnaVideo(tid) {
    if (!aktiv) return;
    stangPop();
    $('#v-etikett').textContent = aktiv.typ === 'ljud' ? 'Ljudinspelning' : 'Videoinspelning';
    $('#v-titel').textContent = aktiv.namn;
    const rad = tid ? (aktiv.rader.find(r => r[0] === tid) || [tid, ''])[1] : '';
    const citat = $('#v-citat');
    citat.textContent = rad ? '”' + rad + '”' : '';
    citat.hidden = !rad;
    vskal.hidden = false;
    requestAnimationFrame(() => {
      vskal.setAttribute('data-pa', '');
      if (tid) aktiv.hoppa(tid);
      if (!aktiv.gar) aktiv.spela();
    });
  }
  function stangVideo() {
    if (aktiv && aktiv.gar) aktiv.spela();
    vskal.removeAttribute('data-pa');
    setTimeout(() => { vskal.hidden = true; }, 220);
    if (baraVideo) { baraVideo = false; stang(); }
  }
  $('#v-stang').addEventListener('click', stangVideo);
  vskal.addEventListener('pointerdown', e => { if (e.target === vskal) stangVideo(); });

  /* ── källpopover: var i transkriptet påståendet kommer från ── */
  function stangPop() { pop.hidden = true; pop.innerHTML = ''; }
  function visaPop(mark) {
    if (!aktiv) return;
    const t = mark.dataset.t;
    const rad = (aktiv.rader.find(r => r[0] === t) || [t, ''])[1];
    pop.innerHTML = '<p class="kallrad"></p><div class="kallmeta"><span class="kalltid"></span><span class="kallnamn"></span><span class="kallgor">▶ Spola hit</span></div>';
    $('.kallrad', pop).textContent = rad ? '”' + rad + '”' : 'Raden finns inte längre i transkriptet.';
    $('.kalltid', pop).textContent = t;
    $('.kallnamn', pop).textContent = aktiv ? aktiv.namn : '';
    pop.hidden = false;
    /* Fäst den vid den rad man faktiskt hovrar: en markering som bryts över två
       rader har en bounding box som täcker båda — vi tar radens egen rektangel. */
    const rutor = [...mark.getClientRects()];
    const pekare = visaPop.senastePeka;
    const r = (pekare && rutor.find(x => pekare.y >= x.top - 2 && pekare.y <= x.bottom + 2)) || rutor[0] || mark.getBoundingClientRect();
    const k = kropp.getBoundingClientRect();
    /* Popen är barn till modalen, inte till kroppen — koordinaterna måste räknas
       mot dess egen offsetParent, annars hamnar den en sidhuvudshöjd för högt. */
    const o = pop.offsetParent ? pop.offsetParent.getBoundingClientRect() : { left: 0, top: 0 };
    const bredd = Math.min(340, k.width - 32);
    pop.style.width = bredd + 'px';
    const vanster = Math.min(Math.max(k.left + 12, r.left + r.width / 2 - bredd / 2), k.right - bredd - 12);
    pop.style.left = Math.round(vanster - o.left) + 'px';
    /* Tooltippen står precis ovanför den rad man pekar på — den viker under bara
       om det inte finns plats över den alls. */
    const over = r.top - o.top - pop.offsetHeight - 6;
    pop.style.top = Math.round(over > 2 ? over : r.bottom - o.top + 8) + 'px';
  }
  const puls = () => {
    const nod = $('.lmini', spelrad) || $('.lminivag', spelrad) || spelrad;
    nod.classList.remove('lpuls');
    void nod.offsetWidth;
    nod.classList.add('lpuls');
  };
  let popTimer = null;
  trad.addEventListener('pointerover', e => {
    const m = e.target.closest('.kallmark');
    if (!m) return;
    clearTimeout(popTimer);
    visaPop.senastePeka = { x: e.clientX, y: e.clientY };
    visaPop(m);
  });
  trad.addEventListener('pointerout', e => {
    if (!e.target.closest('.kallmark')) return;
    clearTimeout(popTimer);
    popTimer = setTimeout(stangPop, 90);
  });
  trad.addEventListener('focusin', e => { const m = e.target.closest('.kallmark'); if (m) visaPop(m); });
  trad.addEventListener('focusout', e => { if (e.target.closest('.kallmark')) stangPop(); });
  trad.addEventListener('click', e => {
    const m = e.target.closest('.kallmark');
    if (!m || !aktiv) return;
    e.stopPropagation();
    oppnaVideo(m.dataset.t);
  });
  trad.addEventListener('keydown', e => {
    const m = e.target.closest('.kallmark');
    if (m && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); m.click(); }
  });

  /* ── spelaren ── */
  function byggSpelare(l) {
    const mini = l.typ === 'ljud'
      ? `<span class="lminivag">${Array.from({ length: 26 }, (_, i) => `<i style="height:${18 + Math.round(Math.abs(Math.sin(i * 1.6)) * 70)}%"></i>`).join('')}</span>`
      : `<span class="lmini">${l.bild ? `<img src="${l.bild}" alt="" />` : ''}</span>`;
    spelrad.innerHTML = `<button class="lspelknapp" type="button" aria-label="Spela">▶</button>${mini}
      <span class="lspar"><span></span></span><span class="ltid">0:00 / ${l.langd}</span>
      <button class="lfart" type="button">1,0×</button>`;
    stor.innerHTML = `<div class="lscen" data-typ="${l.typ}">${l.bild ? `<img class="vbild" src="${l.bild}" alt="" />` : '<span class="ltom">Släpp en bildruta på kortets tumme så syns den här</span>'}<div class="lundertext" data-tom><span></span></div><button class="lspel" type="button" aria-label="Spela"><span>▶</span></button></div>`;
    radfot.innerHTML = `<span class="minietikett">Ladda ner</span><button class="chip" data-ner="SRT">SRT</button><button class="chip" data-ner="TXT">TXT</button><button class="chip" data-ner="VTT">VTT</button><span style="margin-left:auto"><button class="ghost" data-planera>Planera nästa lektion utifrån den här</button></span>`;

    const fyll = $('.lspar span', spelrad), spar = $('.lspar', spelrad), tid = $('.ltid', spelrad);
    const knapp = $('.lspelknapp', spelrad), fart = $('.lfart', spelrad);
    const scen = $('.lscen', stor), undertext = $('.lundertext', stor), utspan = $('.lundertext span', stor);
    const stavar = $$('.lminivag i', spelrad);

    l.visa = () => {
      const p = l.pos / l.total;
      fyll.style.width = (p * 100) + '%';
      tid.textContent = `${mmss(l.pos)} / ${l.langd}`;
      stavar.forEach((s, i) => s.toggleAttribute('data-spelad', i / stavar.length <= p));
      const nu = [...l.rader].reverse().find(([t]) => sek(t) <= l.pos && l.pos - sek(t) < 30);
      if (utspan) { utspan.textContent = nu ? nu[1] : ''; undertext.toggleAttribute('data-tom', !nu); }
      const bar = $('.lnuvarande', spelrad);
      if (bar) bar.textContent = nu ? nu[1] : '';
    };
    const stanna = () => {
      clearInterval(l.gar); l.gar = null;
      knapp.textContent = '▶';
      if (scen) scen.removeAttribute('data-spelar');
    };
    l.spela = () => {
      if (l.gar) return stanna();
      knapp.textContent = '❙❙';
      if (scen) scen.setAttribute('data-spelar', '');
      l.gar = setInterval(() => {
        l.pos = Math.min(l.total, l.pos + 2 * l.fart);
        l.visa();
        if (l.pos >= l.total) stanna();
      }, 60);
    };
    l.hoppa = t => { l.pos = Math.max(0, Math.min(l.total, typeof t === 'number' ? t : sek(t))); l.visa(); };
    knapp.addEventListener('click', l.spela);
    if ($('.lspel', stor)) $('.lspel', stor).addEventListener('click', l.spela);
    spar.addEventListener('click', e => { const r = spar.getBoundingClientRect(); l.hoppa((e.clientX - r.left) / r.width * l.total); });
    fart.addEventListener('click', () => {
      l.fart = { 1: 1.25, 1.25: 1.5, 1.5: 2, 2: 1 }[l.fart] || 1;
      fart.textContent = String(l.fart).replace('.', ',') + '×';
    });
    $$('[data-ner]', radfot).forEach(c => c.addEventListener('click', () => window.toast && window.toast(`${c.dataset.ner} laddades ner`)));
    $('[data-planera]', radfot).addEventListener('click', () => { stang(); window.planeraFran && window.planeraFran(l); });
  }

  /* ── frågefältet i foten ── */
  const CHIPS = ['Sammanfatta lektionen', 'Vad bör eleverna repetera?', 'Påminnelse hela veckan 07–14', 'Gör en läxa av det här'];
  const REDIGERA = ['Flytta till 08:15', 'Bara måndagar', 'Avfärda förslaget'];
  function settChips(lista) {
    const chips = $('#l-chips');
    if (!chips) return;
    chips.innerHTML = '';
    lista.forEach(t => {
      const b = document.createElement('button');
      b.className = 'chip';
      b.type = 'button';
      b.textContent = t;
      b.addEventListener('click', () => skicka(t));
      chips.appendChild(b);
    });
  }
  function byggFot() {
    fot.innerHTML = `<div class="chattforslag" id="l-chips"></div>
      <form class="lfragaform" id="l-form"><input id="l-falt" placeholder="Fråga om lektionen — svaret citerar transkriptet …" /><button class="kor" type="submit">Fråga</button></form>`;
    settChips(CHIPS);
    $('#l-form').addEventListener('submit', e => { e.preventDefault(); const f2 = $('#l-falt'); skicka(f2.value); f2.value = ''; });
  }

  const tolkaTid = t => {
    const m = t.match(/(\d{1,2})(?:[.:](\d{2}))?\s*(?:–|-|—|till)\s*(\d{1,2})(?:[.:](\d{2}))?/);
    return m ? `${m[1].padStart(2, '0')}:${m[2] || '00'}–${m[3].padStart(2, '0')}:${m[4] || '00'}` : '';
  };
  const tolkaDagar = t => /hela veckan|varje (?:vardag|dag)|mån\w*\s*(?:–|-|till)\s*fre/i.test(t) ? 'Mån–fre' : '';

  function svarFor(l, q) {
    const low = q.toLowerCase(), r = l.rader;
    const cit = (i, fras) => {
      const rad = r[Math.min(i, r.length - 1)] || ['', ''];
      return `[[${rad[0]}|${fras || rad[1].slice(0, 42).trim()}]]`;
    };
    if (/påminn|kalender|boka|schemalägg/.test(low)) {
      const tid = tolkaTid(q) || '07:00–14:00', dagar = tolkaDagar(q) || 'Enstaka dag';
      return {
        svar: `Åtgärden står i slutet av lektionen: ${cit(r.length - 1)}. Förslaget nedan bygger på den raden — granska innan något läggs in.`,
        plan: [{ namn: 'Letar efter åtgärder och datum', detalj: '2 träffar' }, { namn: 'Tolkar tid och upprepning', detalj: dagar }, { namn: 'Skriver förslag', detalj: '' }],
        forslag: { titel: 'Påminnelse · ' + l.namn, text: 'Granska innan något läggs in.', rader: [['När', dagar], ['Tid', tid], ['Gäller', l.namn]] }
      };
    }
    if (/repet|prov|svårt|missförst/.test(low)) {
      return {
        svar: `Två saker behöver repeteras: ${cit(2, 'differenskvoten och att h går mot noll')} och begreppet förändringshastighet, som kom tillbaka två gånger — ${cit(1, 'frågan om ett exempel')}.`,
        plan: [{ namn: 'Letar efter frågor och tvekan', detalj: '5 ställen' }, { namn: 'Grupperar efter begrepp', detalj: '2 begrepp' }, { namn: 'Skriver svar med citat', detalj: '' }]
      };
    }
    if (/läxa|uppgift|arbetsblad/.test(low)) {
      return {
        svar: `Lektionen slutade med en hemuppgift: ${cit(r.length - 1)}. Jag kan bygga ett arbetsblad på samma innehåll.`,
        atgarder: [{ namn: 'Gör ett arbetsblad av det här', stark: true, gor: () => { stang(); window.planeraFran && window.planeraFran(l, 'Arbetsblad'); } }]
      };
    }
    return {
      svar: `Genomgången började med vad begreppet mäter — ${cit(0)} — gick vidare till ${cit(1, 'ett elevexempel på förändringshastighet')} och landade i ${cit(2, 'differenskvoten på tavlan')}.`
    };
  }

  function skicka(text) {
    if (!text.trim() || !aktiv) return;
    /* Ligger ett förslag öppet är chatten riktad mot det: raden ändrar kortet
       där det står i stället för att lägga en ny bubbla längst ner. */
    if (aktivtForslag && aktivtForslag.d.isConnected) { forslagSvar(text); return; }
    stangPop();
    const tom = $('.ltom-fraga', trad);
    if (tom) tom.remove();
    nr++;
    const s = svarFor(aktiv, text);
    const f2 = document.createElement('div');
    f2.className = 'lfraga';
    f2.textContent = text;
    trad.appendChild(f2);
    const vard = document.createElement('div');
    vard.className = 'lsvarvard';
    trad.appendChild(vard);
    window.Fraga.kor(vard, {
      omfang: 'transkriptet · ' + aktiv.langd,
      antal: aktiv.rader.length,
      svar: s.svar,
      plan: s.plan,
      atgarder: s.atgarder,
      efterKlar: el => {
        if (s.forslag) kalenderKort(el, s.forslag);
      },
      smal: true
    });
  }

  /* ══ CHATTA MED FÖRSLAGET ═══════════════════════════════════════
     Ett förslag som ändras via nya chattbubblor blir fyra versioner av samma sak
     att hålla reda på. Här är kortet samtalet: det man skriver landar i kortet,
     kortet skriver om sig självt på stället, vyn står still. Först när kortet är
     avklarat (inlagt eller avfärdat) är chatten öppen för nästa fråga igen. */
  let aktivtForslag = null;

  function laseTillForslag(d, f) {
    aktivtForslag = { d, f };
    d.setAttribute('data-aktiv', '');
    settChips(REDIGERA);
    const falt = $('#l-falt');
    if (falt) falt.placeholder = 'Ändra förslaget — t.ex. ”flytta till 08:15” eller ”bara måndagar” …';
  }
  function slappForslag() {
    if (aktivtForslag) aktivtForslag.d.removeAttribute('data-aktiv');
    aktivtForslag = null;
    settChips(CHIPS);
    const falt = $('#l-falt');
    if (falt) falt.placeholder = 'Fråga om lektionen — svaret citerar transkriptet …';
  }
  const forslagRad = (d, nyckel) => [...d.querySelectorAll('.forslagrad')].find(r => $('.fnyckel', r) && $('.fnyckel', r).textContent === nyckel);
  function sattRad(d, nyckel, varde) {
    const r = forslagRad(d, nyckel);
    if (!r) return false;
    $('.fvarde', r).textContent = varde;
    r.setAttribute('data-andrad', '');
    setTimeout(() => r.removeAttribute('data-andrad'), 1400);
    return true;
  }
  function loggRad(d, klass, text) {
    const logg = $('.forslagchatt', d);
    const p = document.createElement('p');
    p.className = klass;
    p.textContent = text;
    logg.appendChild(p);
    /* Samma regel som i chatten runtomkring: det senaste man skrivit är det man
       ska se — tråden följer efter mjukt i stället för att lämna raden under kanten. */
    foljMed(d);
    return p;
  }

  /* Rulla bara om kortets nederkant hamnat utanför vyn — annars står allt still. */
  function foljMed(d) {
    requestAnimationFrame(() => {
      const r = d.getBoundingClientRect(), b = trad.getBoundingClientRect();
      const under = r.bottom - (b.bottom - 12);
      if (under > 0) (window.rullaLada || ((x, y) => { x.scrollTop = y; }))(trad, trad.scrollTop + under, 420);
    });
  }

  function forslagSvar(text) {
    const { d, f } = aktivtForslag;
    const falt = $('#l-falt');
    if (falt) falt.value = '';
    loggRad(d, 'fcfraga', text);
    d.setAttribute('data-tanker', '');
    setTimeout(() => {
      d.removeAttribute('data-tanker');
      const low = text.toLowerCase();
      if (/avfärda|glöm|skippa|strunt|ta bort|behövs inte/.test(low)) {
        loggRad(d, 'fcsvar', 'Avfärdat — inget lades in i kalendern.');
        d.setAttribute('data-bort', '');
        slappForslag();
        setTimeout(() => { const t = $('.forslagknappar', d); if (t) t.remove(); }, 240);
        return;
      }
      const tid = tolkaTid(text) || (text.match(/(\d{1,2})[.:](\d{2})/) ? text.match(/(\d{1,2})[.:](\d{2})/)[0].replace('.', ':') : '');
      const dagar = tolkaDagar(text) || (/bara måndag|endast måndag/.test(low) ? 'Måndagar' : /bara fredag/.test(low) ? 'Fredagar' : /varannan vecka/.test(low) ? 'Varannan vecka' : '');
      const gjort = [];
      if (tid) {
        const rad = /^\d{1,2}:\d{2}$/.test(tid) ? tid : tid;
        if (sattRad(d, 'Tid', rad)) { gjort.push('tiden till ' + rad); const i = f.rader.findIndex(x => x[0] === 'Tid'); if (i > -1) f.rader[i][1] = rad; }
      }
      if (dagar) {
        if (sattRad(d, 'När', dagar)) { gjort.push('dagarna till ' + dagar.toLowerCase()); const i = f.rader.findIndex(x => x[0] === 'När'); if (i > -1) f.rader[i][1] = dagar; }
      }
      loggRad(d, 'fcsvar', gjort.length
        ? 'Ändrade ' + gjort.join(' och ') + '. Granska och lägg in.'
        : 'Jag ändrade inget — säg en tid (”08:15”), vilka dagar det gäller, eller ”avfärda”.');
    }, 620);
  }

  function kalenderKort(vard, f) {
    const d = document.createElement('div');
    d.className = 'forslag';
    d.innerHTML = `<p class="forslagtitel"></p><p class="forslagtext">${f.text}</p>
      ${f.rader.map(([k, v]) => `<div class="forslagrad"><span class="fnyckel">${k}</span><span class="fvarde">${v}</span></div>`).join('')}
      <div class="forslagchatt"></div>
      <div class="forslagknappar"><button class="primar" data-lagg>Lägg in i kalendern</button><button class="lank" type="button" data-avfarda>Avfärda</button><span class="mjuk">Eller skriv i chatten vad som ska ändras</span></div>`;
    $('.forslagtitel', d).textContent = f.titel;
    /* Krock-raden: vad som redan står i kalendern den dagen. Ett förslag utan den
       raden tvingar läraren att byta fönster för att kunna svara ja. */
    const datum = f.datum || (aktiv && aktiv.kort && aktiv.kort.dataset.datum) || (window.Kalender && window.Kalender.idag());
    if (window.Kalender && datum) {
      const k = window.Kalender.krockrad(datum);
      const r = document.createElement('div');
      r.className = 'forslagrad';
      r.innerHTML = `<span class="fnyckel">Krock</span><span class="fvarde"${k.krock ? ' data-krock' : ''}></span>`;
      $('.fvarde', r).textContent = k.text;
      $('.forslagknappar', d).before(r);
      f.datum = datum;
    }
    vard.appendChild(d);
    laseTillForslag(d, f);
    foljMed(d);
    $('[data-avfarda]', d).addEventListener('click', () => {
      d.setAttribute('data-bort', '');
      loggRad(d, 'fcsvar', 'Avfärdat — inget lades in i kalendern.');
      $('.forslagknappar', d).remove();
      slappForslag();
    });
    $('[data-lagg]', d).addEventListener('click', () => {
      d.setAttribute('data-inlagt', '');
      $('.forslagknappar', d).innerHTML = '<span class="fklar">✓ Inlagt i kalendern</span>';
      if (window.Kalender && f.datum) window.Kalender.lagg({ datum: f.datum, tid: (f.rader.find(x => x[0] === 'Tid') || ['', '—'])[1], titel: f.titel, klass: (aktiv && aktiv.kort && aktiv.kort.dataset.klass) || '' });
      slappForslag();
      window.toast && window.toast('Inlagt i kalendern · ' + f.titel);
    });
  }

  /* ── öppna och stäng ── */
  function oppna(kort, val = {}) {
    tillbaka = typeof val.tillbaka === 'function' ? val.tillbaka : null;
    const namn = $('.namn', kort) ? $('.namn', kort).textContent.trim() : 'Lektionen';
    const tumme = $('.tumme', kort);
    const typ = tumme && tumme.dataset.typ === 'ljud' ? 'ljud' : 'video';
    const langd = $('.tumtid', kort) ? $('.tumtid', kort).textContent : '—';
    const klass = kort.dataset.klass || '', kurs = kort.dataset.kurs || '';
    const datumrad = $('.datum', kort) ? $('.datum', kort).textContent.trim() : '';
    const tagg = [klass, kurs].filter(Boolean).join(' · ');
    const slot = tumme && tumme.querySelector('image-slot');
    const bild = slot && slot.shadowRoot ? ((slot.shadowRoot.querySelector('img[src]') || {}).src || '') : '';
    aktiv = {
      kort, namn, typ, langd, bild, tagg,
      total: sek(langd) || 600, pos: 0, gar: null, fart: 1,
      rader: (window.transkript || []).map(r => r.slice())
    };
    nr = 0;
    stangPop();
    trad.innerHTML = '<p class="ltom-fraga">Ställ en fråga om lektionen. Svaret citerar transkriptet — klicka på en blåmarkerad del för att se exakt var det sades, och spola dit.</p>';
    $('#l-etikett').textContent = typ === 'ljud' ? 'Ljudinspelning' : 'Videoinspelning';
    $('#l-titel').textContent = namn;
    $('#l-meta').textContent = [datumrad, klass || 'ingen klass', kurs || 'ingen kurs'].filter(Boolean).join(' · ');
    byggSpelare(aktiv);
    byggFot();
    aktiv.visa();
    /* Kommer man från ett citat är videon hela ärendet: spelaren byggs, men
       lektionschatten öppnas aldrig — den ska inte ligga och blinka bakom. */
    const dold = !!val.dold;
    if (!dold) skal.hidden = false;
    requestAnimationFrame(() => {
      if (!dold) skal.setAttribute('data-pa', '');
      if (val.hoppa) aktiv.hoppa(val.hoppa);
      if (val.spelaUpp) oppnaVideo(val.hoppa);
      if (val.fraga) skicka(val.fraga);
      if (val.lage === 'fraga') { const f = $('#l-falt'); if (f) f.focus({ preventScroll: true }); }
    });
    document.addEventListener('keydown', tangent);
  }
  function stang() {
    stangVideo();
    if (aktiv && aktiv.gar) clearInterval(aktiv.gar);
    stangPop();
    skal.removeAttribute('data-pa');
    setTimeout(() => { skal.hidden = true; }, 220);
    document.removeEventListener('keydown', tangent);
    /* Öppnades lektionen från en annan vy — t.ex. klarrutan i Transkribera — ska
       stängningen lämna en tillbaka där, inte i arkivet man passerade igenom. */
    const ater = tillbaka;
    tillbaka = null;
    if (ater) ater();
  }
  function tangent(e) {
    if (e.target.isContentEditable || /input|textarea/i.test(e.target.tagName)) {
      if (e.key === 'Escape') e.target.blur();
      return;
    }
    if (e.key === 'Escape') {
      if (!vskal.hidden) return stangVideo();
      if (skal.hasAttribute('data-max')) return satMax(false);
      return stang();
    }
    if (!aktiv) return;
    if (e.key === 'f' || e.key === 'F') { e.preventDefault(); return satMax(!skal.hasAttribute('data-max')); }
    if (e.key === ' ') { e.preventDefault(); aktiv.spela(); }
    if (e.key === 'ArrowRight') { e.preventDefault(); aktiv.hoppa(aktiv.pos + 5); }
    if (e.key === 'ArrowLeft') { e.preventDefault(); aktiv.hoppa(aktiv.pos - 5); }
    if (e.key === 'j' || e.key === 'k') {
      e.preventDefault();
      const tider = aktiv.rader.map(r => sek(r[0]));
      const i = tider.findIndex(t => t > aktiv.pos + 0.5);
      const nu = (i === -1 ? tider.length : i) - 1;
      aktiv.hoppa(tider[Math.max(0, Math.min(tider.length - 1, e.key === 'j' ? nu + 1 : nu - 1))] || 0);
    }
  }
  $('#l-spelupp').addEventListener('click', () => oppnaVideo());

  function satMax(pa) {
    skal.toggleAttribute('data-max', pa);
    const k = $('#l-max');
    k.setAttribute('aria-pressed', String(pa));
    k.dataset.tips = pa ? 'Tillbaka till fönster' : 'Förstora till helskärm';
    k.setAttribute('aria-label', k.dataset.tips);
    k.innerHTML = pa
      ? `<svg class="ikonsvg" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 9h3.5A2.5 2.5 0 0 0 9 6.5V3" /><path d="M21 9h-3.5A2.5 2.5 0 0 1 15 6.5V3" /><path d="M3 15h3.5A2.5 2.5 0 0 1 9 17.5V21" /><path d="M21 15h-3.5a2.5 2.5 0 0 0-2.5 2.5V21" /></svg>`
      : `<svg class="ikonsvg" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 3H5.5A2.5 2.5 0 0 0 3 5.5V9" /><path d="M15 3h3.5A2.5 2.5 0 0 1 21 5.5V9" /><path d="M9 21H5.5A2.5 2.5 0 0 1 3 18.5V15" /><path d="M15 21h3.5a2.5 2.5 0 0 0 2.5-2.5V15" /></svg>`;
    stangPop();
  }
  $('#l-max').addEventListener('click', () => satMax(!skal.hasAttribute('data-max')));
  $('#l-stang').addEventListener('click', stang);
  skal.addEventListener('pointerdown', e => { if (e.target === skal) stang(); });
  trad.addEventListener('scroll', stangPop);
  window.addEventListener('resize', stangPop);

  window.Lektion = {
    oppna, stang,
    /* från ett citat i ett svar rakt in i uppspelningen, framspolad till stället */
    spelaUpp: (kort, tid) => { baraVideo = true; oppna(kort, { hoppa: tid, spelaUpp: true, dold: true }); },
    get aktiv() { return aktiv; }
  };
})();
