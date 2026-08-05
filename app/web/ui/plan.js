/* ══════════ PLANERING — kärnan ══════════
   Stegen, dokumenttypernas upplägg, skrivningen, dokumentkortet, iterationen och
   Sparat. Tre bitar bodde förut i samma fil men i egna slutningar och lyftes ut
   den 3 augusti 2026: plan-sidor.js (foton av sidorna), plansteg.js (stapeln som
   viker ihop klara steg) och planlage.js (lägeskorten). De hänger på DOM:en och
   på window-API:erna, inte på den här filens slutning. */
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const valt = seg => { const b = $(`[data-seg="${seg}"] [aria-pressed="true"]`); return b ? b.textContent : ''; };

  const GY = {
    'Matematik 3c': ['Derivatans definition', 'Deriveringsregler', 'Extremvärdesproblem', 'Primitiva funktioner', 'Integraler och areor'],
    'Matematik 4': ['Trigonometriska funktioner', 'Trigonometriska formler', 'Komplexa tal', 'Differentialekvationer', 'Bevis och algebraiska metoder'],
    '': ['Begreppsförståelse', 'Procedurer och metoder', 'Problemlösning', 'Resonemang och bevis', 'Kommunikation']
  };
  const KONTEXT = { start: 'vardagsnära', fysik: 'fysikaliska', ekonomi: 'ekonomiska', natur: 'naturvetenskapliga' };

  let vald = new Set(), versioner = [], nu = -1, sparat = [];

  /* Varje dokumenttyp har sina egna val — en tavla läraren skriver av, ett prov med
     provtid och poängnivåer, ett arbetsblad med nivå och facit. */
  /* Bestämd form per dokumenttyp. Fyra typer betyder att '+ et' inte längre
     räcker: en gruppuppgift blir gruppuppgiften, inte gruppuppgiftet. */
  const BEST = { Tavla: 'tavlan', Prov: 'provet', Arbetsblad: 'arbetsbladet', Gruppuppgift: 'gruppuppgiften' };
  const best = t => BEST[t] || String(t || '').toLowerCase();
  const Best = t => { const o = best(t); return o.charAt(0).toUpperCase() + o.slice(1); };

  const TYPVAL = {
    Tavla: [
      /* Ligger genomgången på en lektion ur schemat är längden redan bestämd — men
         planerar man fritt måste både starten och längden gå att sätta. Samma
         vred som provets: rulla på klockslaget eller på minuterna. */
      { id: 'langd', namn: 'Klockslag och längd', typ: 'lektionstid' },
      { id: 'exempel', namn: 'Exempel att skriva upp', typ: 'antal', min: 1, max: 4 }
    ],
    Prov: [
      /* När provet skrivs och hur långt det är var tre rader, sedan två: ett
         segment («På lektionen» / «Annan dag») och en väljare. Men segmentet var
         en fråga om samma sak som väljaren redan svarade på — klickar man en dag i
         kalendern ÄR det en annan dag. Nu är det EN rad: appens kalender med dag,
         klockslag och längd i samma panel. `s.nar` finns kvar i upplägget, men som
         avläsning (se ritaTypval) — sammanfattningen och provNar() läser den. */
      { id: 'nartid', namn: 'När skrivs provet?', typ: 'nartid' },
      { id: 'antal', namn: 'Antal uppgifter', typ: 'antal', min: 4, max: 12 },
      { id: 'nivamix', namn: 'Poängnivåer', typ: 'seg', val: ['Bara E', 'E-tyngd', 'Balanserat', 'C/A-tyngd'] },
      /* Del A är utan digitala hjälpmedel, del B med räknare och GeoGebra.
         Skillnaden är hjälpmedlen — båda delarna bär korta svar och uppgifter
         som redovisas på lösblad. */
      { id: 'delprov', namn: 'Upplägg', typ: 'seg', val: ['En del', 'Del A + Del B'] },
      /* Lösningsförslaget och formelbladet är samma beslut — vad som skrivs ut
         UTÖVER provet — och stod som två switchar på var sin rad. En rad med två
         kryss säger det på halva höjden. Fälten under är oförändrade: tryck.js
         läser `formelblad` och bladet `losningar`. */
      { id: 'bilagor', namn: 'Bilagor', typ: 'kryss', delar: [{ id: 'losningar', namn: 'Lösningsförslag' }, { id: 'formelblad', namn: 'Formelblad' }] }
    ],
    Gruppuppgift: [
      { id: 'grupp', namn: 'Elever per grupp', typ: 'antal', min: 2, max: 5 },
      { id: 'langd', namn: 'Tid på lektionen', typ: 'minuter', snabb: [10, 20, 30, 45], min: 10, max: 180 },
      { id: 'redovisning', namn: 'Redovisning', typ: 'seg', val: ['Muntligt', 'Skriftligt', 'Poster'] }
    ],
    Arbetsblad: [
      { id: 'antal', namn: 'Antal uppgifter', typ: 'antal', min: 1, max: 6 },
      { id: 'niva', namn: 'Nivå', typ: 'seg', val: ['E-nivå', 'C-nivå', 'A-nivå', 'Blandat'] },
      { id: 'facit', namn: 'Facit', typ: 'seg', val: ['Inget facit', 'Facit i bladet', 'Separat facit'] },
      { id: 'illustration', namn: 'Plats för illustration', typ: 'switch' }
    ]
  };
  const inst = {
    Tavla: { langd: 45, starttid: '', exempel: 2 },
    Prov: { nar: 'På lektionen', narDatum: '', narTid: '08:15', provminuter: 90, provtid: '90 min', antal: 6, nivamix: 'Balanserat', delprov: 'Del A + Del B', losningar: true, formelblad: true },
    Arbetsblad: { antal: 3, niva: 'Blandat', facit: 'Facit i bladet', illustration: true },
    Gruppuppgift: { grupp: 3, langd: 60, redovisning: 'Muntligt' }
  };
  /* Utgår pappret från boken är lösningsförslaget till BOKENS uppgifter något
     annat än facit till de uppgifter appen själv skrivit: eleverna räknar i
     boken, läraren räknar dem också, och det är nivå 2 och 3 som behöver en
     skriven lösning — de lätta löser sig i huvudet. Raden hör därför till alla
     fyra typerna, och den finns bara när ett spann i boken är valt. */
  const harBokuppg = () => !!(window.Uppgifter && window.Uppgifter.finns());
  /* Att slå PÅ lösningsförslagen och att säga vilka uppgifter som får ett var en
     switch och en segmentväljare på var sin rad — men det är en fråga med ett
     svar: till vilka. «Inga» ÄR av-läget. Fälten under lever kvar oförändrade
     (`boklosning` bool, `boklosniva` sträng) eftersom uppgifter.js läser båda —
     de hålls i takt av normalisera() i ritaTypval(). */
  Object.keys(TYPVAL).forEach(t => TYPVAL[t].push(
    { id: 'boklosniva', namn: 'Lösningar till bokens uppgifter', typ: 'seg', val: ['Inga', 'Alla', 'Nivå 2 och 3', 'Bara nivå 3'], bara: harBokuppg }
  ));
  Object.keys(inst).forEach(t => Object.assign(inst[t], { boklosning: true, boklosniva: 'Nivå 2 och 3' }));
  const STANDARD = JSON.parse(JSON.stringify(inst));
  /* Lektionens längd står i schemat: «08:15–09:00» är 45 minuter. */
  function schemaminuter() {
    const t = ($('#p-tid') || {}).value || '';
    const m = t.match(/(\d{1,2})[:.](\d{2})\s*[–-]\s*(\d{1,2})[:.](\d{2})/);
    if (!m) return null;
    const min = (+m[3] * 60 + +m[4]) - (+m[1] * 60 + +m[2]);
    return min > 0 ? min : null;
  }
  function schemastart() {
    const t = ($('#p-tid') || {}).value || '';
    const m = t.match(/(\d{1,2})[:.](\d{2})/);
    return m ? `${String(+m[1]).padStart(2, '0')}:${m[2]}` : '';
  }
  /* Ligger det redan en godkänd tavla på lektionen tar den av samma minuter —
     paret ska dela på lektionen, inte var för sig fylla den. */
  function tavlaMinuter() {
    const d = ($('#p-datum') || {}).value || '', kl = ($('#p-klass') || {}).value || '';
    if (!d) return 0;
    const t = sparat.filter(v => !v.losningsblad && v.typ === 'Tavla' && v.datum === d && (!kl || v.klass === kl)).pop();
    return t ? Number((t.inst || {}).langd) || 0 : 0;
  }
  /* Par-uppgiften är 26 % av genomgången (samma delning som tavlan själv trycker
     i sina block) — avrundat till hela fem minuter. */
  const parBlock = min => Math.max(10, Math.round(min * 0.26 / 5) * 5);
  /* En rad under kontrollen som säger om valet håller — längden mot lektionen,
     dagen mot kalendern. Tom rad tar ingen plats. En varning som bara konstaterar
     lämnar läraren att själv leta rätt kontroll — därför bär raden sina åtgärder. */
  function typnot(rad) {
    const p = document.createElement('p');
    p.className = 'typnot';
    p.hidden = true;
    rad.appendChild(p);
    return p;
  }
  function satNot(p, ton, text, atgarder) {
    if (!p) return;
    p.hidden = !text;
    p.dataset.ton = ton || '';
    p.textContent = text || '';
    (atgarder || []).forEach(a => {
      if (!a || !a.namn) return;
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'typnotgor';
      b.textContent = a.namn;
      b.addEventListener('click', a.gor);
      p.appendChild(b);
    });
  }
  /* Bokens lösningar är EN rad med «Inga» som av-läge, men två fält under: en
     bool som uppgifter.js kollar och en nivå den läser. Ärvda upplägg bär den
     gamla kombinationen (boklosning:false + en nivå som står kvar) — de vägs
     ihop här så att raden och pappret aldrig säger olika saker. */
  function normalisera(s) {
    if (!s) return;
    if (s.boklosning === false) s.boklosniva = 'Inga';
    else if (s.boklosniva === 'Inga') s.boklosning = false;
    else s.boklosning = true;
  }
  function ritaTypval() {
    const typ = valt('skrivtyp'), s = inst[typ];
    normalisera(s);
    const lista = (TYPVAL[typ] || []).filter(k => !k.bara || k.bara(s));
    if (typ === 'Tavla') {
      /* Schemat vinner så länge det säger något nytt — sätter läraren tiden för
         hand står den kvar tills en annan lektion väljs. */
      const m = schemaminuter(), st = schemastart();
      if (m && m !== s.langdSchema) { s.langd = m; s.langdSchema = m; s.egen = false; }
      if (!m) s.langdSchema = null;
      if (st && st !== s.tidSchema) { s.starttid = st; s.tidSchema = st; }
      if (!st) s.tidSchema = null;
      if (!s.starttid) s.starttid = '08:15';
    }
    if (typ === 'Prov') {
      /* Provets dag ärvs ur lektionen tills läraren klickar en annan i kalendern.
         Byter man lektion ska den ärvda dagen följa med — annars står förra
         lektionens datum kvar och läses som «annan dag» på en ny planering. En dag
         läraren själv satt rörs inte. */
      const ld = ($('#p-datum') || {}).value || '';
      if (ld !== s.dagSchema) {
        if (!s.narDatum || s.narDatum === s.dagSchema) s.narDatum = ld;
        s.dagSchema = ld;
      }
      /* «På lektionen» är inte längre ett eget val utan en avläsning av dagen —
         fältet står kvar för sammanfattningen och provNar(), som båda läser det. */
      s.nar = !s.narDatum || s.narDatum === ld ? 'På lektionen' : 'Annan dag';
      /* «På lektionen» betyder lektionens klockslag — inte 08:15 för att det råkade
         stå i standarden. Sätter läraren tiden själv står den kvar tills en annan
         lektion väljs. */
      const st = schemastart();
      if (s.nar !== 'Annan dag' && st && st !== s.tidSchema) { s.narTid = st; s.tidSchema = st; }
      if (!st) s.tidSchema = null;
      if (!s.narTid) s.narTid = st || '08:15';
      /* Och LÄNGDEN på samma villkor som klockslaget: ett prov «på lektionen» är
         lektionen långt. Förr stod standardens 90 min kvar på en 45-minuters­lektion
         — och då varnade appen för sitt eget förval («Provet är 90 min men lektionen
         bara 45 min») innan läraren gjort något. Sätter läraren minuterna själv står
         de kvar tills en annan lektion väljs, precis som tavlans längd. */
      const pm = schemaminuter();
      const pnyckel = s.nar === 'Annan dag' ? '' : String(pm || 0);
      if (pnyckel && pnyckel !== '0' && pnyckel !== s.minSchema) {
        s.provminuter = pm; s.provtid = pm + ' min'; s.minSchema = pnyckel;
      }
      if (!pnyckel || pnyckel === '0') s.minSchema = null;
    }
    if (typ === 'Gruppuppgift') {
      /* Lektionen bestämmer längden här också — och står tavlan på samma lektion är
         det inte två tider utan en: gruppuppgiften ÄR tavlans par-uppgift, och
         föreslås därför med den blockets minuter. */
      /* Ligger ingen godkänd tavla ännu men är den vald i steg 1 hör de ändå ihop —
         då räknas par-blocket ur lektionen. Och en gruppuppgift som ÄR hela
         lektionen är ett undantag, inte förvalet: utan tavla föreslås två
         tredjedelar, så det finns tid kvar till start och återsamling. */
      const m = schemaminuter();
      const lagen = (window.Lagen && window.Lagen()) || [];
      const tav = tavlaMinuter() || (lagen.includes('Tavla') ? m : 0);
      const forslag = tav ? parBlock(tav) : (m ? Math.max(15, Math.round(m * 0.66 / 5) * 5) : 0);
      const kalla = `${m || 0}|${tav}`;
      if (forslag && kalla !== s.langdSchema) { s.langd = forslag; s.langdSchema = kalla; }
      if (!m && !tav) s.langdSchema = null;
    }
    const vard = $('#typval');
    vard.innerHTML = `<p class="minietikett">Så ska ${best(typ)} sättas</p><div class="typrader"></div>`;
    const rader = $('.typrader', vard);
    lista.forEach(k => {
      const rad = document.createElement('div');
      rad.className = 'typrad';
      rad.dataset.id = k.id;
      const kontroll = k.typ === 'fakta'
        ? `<span class="typfakta"><b>${s[k.id]} min</b><span>${schemaminuter() ? 'ur schemat' : 'standard — ingen lektion ur schemat'}</span></span>`
        : k.typ === 'lektionstid'
        ? `<span class="narfalt"><span class="typkalla"></span><span class="valj nartidvalj"><button class="valjknapp" type="button" aria-haspopup="dialog" aria-expanded="false"><span class="valjtext"></span><span class="valjpil"></span></button></span><input type="hidden" class="nardatum" value="" /><input type="hidden" class="nartidstart" value="${s.starttid || '08:15'}" /></span>`
        : k.typ === 'nartid'
        /* «Uppskatta tiden» satt vid antalet uppgifter men SÄTTER provtiden —
           knappen stod alltså två rader från det den ändrar. Den hör vid tiden. */
        ? `<span class="narfalt"><button class="ghost minitid" type="button" data-uppskatta data-tip="Räknar arbetstiden ur uppgifterna och sätter provtiden">Uppskatta tiden</button><span class="valj nartidvalj"><button class="valjknapp" type="button" aria-haspopup="dialog" aria-expanded="false"><span class="valjtext"></span><span class="valjpil"></span></button></span><input type="hidden" class="nardatum" value="${s.narDatum || (($('#p-datum') || {}).value || '')}" /><input type="hidden" class="nartidstart" value="${s.narTid || (($('#p-tid') || {}).value || '').split('–')[0].trim() || '08:15'}" /></span>`
        : k.typ === 'minuter'
        ? `<span class="minutval"><span class="minutchips">${k.snabb.map(m => `<button class="minutchip" type="button" aria-pressed="${Number(s[k.id]) === m}">${m}</button>`).join('')}</span><span class="minutfalt"><input type="text" inputmode="numeric" maxlength="3" value="${s[k.id]}" aria-label="${k.namn} i minuter" /><span class="minutenhet">min</span></span></span>`
        : k.typ === 'seg'
        ? `<div class="seg" role="group" data-seg="tv-${k.id}">${k.val.map(v => `<button type="button" aria-pressed="${s[k.id] === v}">${v}</button>`).join('')}</div>`
        : k.typ === 'antal'
          ? `<span class="antalgrupp"><span class="stepper"><button class="gzknapp" type="button" data-steg="-1" aria-label="Färre">−</button><span class="steppervarde">${s[k.id]}</span><button class="gzknapp" type="button" data-steg="1" aria-label="Fler">+</button></span></span>`
          : k.typ === 'kryss'
          ? `<span class="kryssval">${k.delar.map(d => `<button class="kryssknapp" type="button" data-del="${d.id}" aria-pressed="${!!s[d.id]}">${d.namn}</button>`).join('')}</span>`
          : `<button class="switch" type="button" aria-pressed="${s[k.id]}" aria-label="${k.namn}" style="background:${s[k.id] ? 'var(--accent)' : 'var(--track)'};border-color:${s[k.id] ? 'var(--accent)' : 'var(--line)'}"><span class="knopp" style="transform:translateX(${s[k.id] ? 16 : 0}px)"></span></button>`;
      rad.innerHTML = `<span class="typnamn">${typeof k.namn === 'function' ? k.namn(s) : k.namn}</span>${kontroll}`;
      if (k.typ === 'minuter') {
        const falt = $('input', rad);
        let efterSync = null;
        const sync = () => {
          $$('.minutchip', rad).forEach(c => c.setAttribute('aria-pressed', String(Number(c.textContent) === Number(s[k.id]))));
          falt.value = String(s[k.id]);
          if (efterSync) efterSync();
        };
        $$('.minutchip', rad).forEach(c => c.addEventListener('click', () => { s[k.id] = Number(c.textContent); sync(); planKoll(); }));
        falt.addEventListener('input', () => { falt.value = falt.value.replace(/\D/g, '').slice(0, 3); });
        falt.addEventListener('change', () => {
          const v = Math.max(k.min, Math.min(k.max, Number(falt.value) || k.min));
          s[k.id] = v; sync(); planKoll();
        });
        falt.addEventListener('blur', () => falt.dispatchEvent(new Event('change')));
        falt.addEventListener('keydown', e => {
          if (e.key === 'Enter') { e.preventDefault(); falt.blur(); return; }
          if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
            e.preventDefault();
            justera(e.key === 'ArrowUp' ? 1 : -1, e.shiftKey ? 5 : 1);
          }
        });
        /* Minuter är ett tal man justerar, inte skriver om: hovra och rulla.
           Shift rullar fem minuter i taget. */
        function justera(riktning, steg) {
          const v = Math.max(k.min, Math.min(k.max, (Number(s[k.id]) || k.min) + riktning * steg));
          if (v === Number(s[k.id])) return;
          s[k.id] = v; sync(); planKoll();
          ruta.setAttribute('data-rullar', '');
          clearTimeout(ruta._t);
          ruta._t = setTimeout(() => ruta.removeAttribute('data-rullar'), 300);
        }
        const ruta = $('.minutfalt', rad);
        ruta.dataset.tip = 'Rulla för att ändra — shift för fem i taget';
        ruta.addEventListener('wheel', e => {
          const d = e.deltaY || e.deltaX;
          if (!d) return;
          e.preventDefault();
          justera(d < 0 ? 1 : -1, e.shiftKey ? 5 : 1);
        }, { passive: false });
        /* Samma löfte som tavlans och provets: raden under säger om tiden håller
           mot lektionen — och mot tavlan, om de två delar lektion. */
        if (typ === 'Gruppuppgift' && k.id === 'langd') {
          const not = typnot(rad);
          efterSync = () => {
            const lekt = schemaminuter(), min = Number(s.langd) || 0, tav = tavlaMinuter();
            if (!lekt && !tav) return satNot(not, '', '');
            if (tav) {
              const par = parBlock(tav);
              return satNot(not, lekt && min > lekt ? 'krock' : 'ok',
                lekt && min > lekt
                  ? `Gruppuppgiften är ${min} min men lektionen bara ${lekt} min.`
                  : min <= par
                    ? `Ryms i tavlans par-uppgift — ${par} min av genomgången är avsatta till den.`
                    : `Längre än tavlans par-uppgift (${par} min) — genomgången får kortas därefter.`,
                lekt && min > lekt ? [{ namn: `Korta till ${par} min`, gor: () => { s.langd = par; sync(); planKoll(); } }] : null);
            }
            satNot(not, min > lekt ? 'krock' : 'ok', min > lekt
              ? `Gruppuppgiften är ${min} min men lektionen bara ${lekt} min.`
              : min < lekt ? `${lekt - min} min över av lektionen.` : 'Fyller hela lektionen.',
              min > lekt ? [{ namn: `Korta till ${lekt} min`, gor: () => { s.langd = lekt; sync(); planKoll(); } }] : null);
          };
          efterSync();
        }
      }
      if (k.typ === 'seg') $$('button', rad).forEach(b => b.addEventListener('click', () => {
        s[k.id] = b.textContent;
        /* Av-läget är ett val i samma rad, inte en switch bredvid — boolen som
           uppgifter.js läser sätts därför här, i samma klick som nivån. */
        if (k.id === 'boklosniva') s.boklosning = b.textContent !== 'Inga';
        planKoll();
        /* «Annan dag» fäller ut dag och tid direkt under raden. */
        if (k.id === 'nar') ritaTypval();
        /* Byter man nivå byter också antalet uppgifter som får en lösning — och
           det talet står i noten under raden. */
        if (k.id === 'boklosniva') ritaTypval();
      }));
      /* Två kryss på en rad — varje kryss äger sitt eget fält i `s`, så att den
         som läser upplägget längre fram (tryck.js, bladet) inte behöver veta att
         de delar rad. */
      if (k.typ === 'kryss') $$('.kryssknapp', rad).forEach(b => b.addEventListener('click', () => {
        const id = b.dataset.del;
        s[id] = !s[id];
        b.setAttribute('aria-pressed', String(!!s[id]));
        planKoll();
      }));
      /* Raden säger hur många uppgifter som faktiskt får ett lösningsförslag, och
         att lösningarna håller sig inom det boken hunnit ta upp. Utan det sista
         kan ett lösningsförslag i Matematik 3c luta sig mot en sats klassen möter
         först i Matematik 4 — och då är förslaget oanvändbart i klassrummet.
         Noten måste rymmas på EN rad: `.typnot` är en flexrad som wrappar, och en
         längre text sköt pricken upp på en rad för sig själv. */
      if (k.id === 'boklosniva') {
        const not = typnot(rad);
        const U = window.Uppgifter;
        if (s.boklosniva === 'Inga') satNot(not, '', 'Bokens uppgifter står kvar i pappret — men utan skrivna lösningar.');
        else {
          const n = U && U.losningsantal ? U.losningsantal(s.boklosniva) : 0;
          satNot(not, n ? 'ok' : 'krock', n
            ? `${n} ${n === 1 ? 'uppgift' : 'uppgifter'} — lösningar inom bokens metoder t.o.m. ${U.avsnittsnr()}`
            : 'Ingen uppgift på den nivån är kvar i urvalet.');
        }
      }
      /* Dagen, klockslagen och längden i EN panel — appens kalender, samma som
         datumfiltret på Inspelningar. Ligger provet på lektionen är dagen redan
         känd, så då visas bara klockslagen. */
      /* Genomgångens klockslag och längd — samma panel som provets, men utan
         kalender: dagen är lektionens, det som sätts är när och hur länge. */
      if (k.typ === 'lektionstid') {
        const wrap = $('.nartidvalj', rad), knapp = $('.valjknapp', rad);
        const dagFalt = $('.nardatum', rad), tidFalt = $('.nartidstart', rad);
        const kalla = $('.typkalla', rad);
        const visaKalla = () => { kalla.textContent = s.egen ? 'satt för hand' : (schemaminuter() ? 'ur schemat' : 'standard'); };
        const not = typnot(rad);
        const visaNot = () => {
          const lekt = schemaminuter(), min = Number(s.langd) || 45;
          if (!lekt) return satNot(not, '', '');
          satNot(not, min > lekt ? 'krock' : 'ok', min > lekt
            ? `Genomgången är ${min} min men lektionen bara ${lekt} min — den hinner inte klart.`
            : min < lekt ? `${lekt - min} min över av lektionen.` : 'Fyller hela lektionen.',
            min > lekt ? [{ namn: `Korta till ${lekt} min`, gor: () => { s.langd = lekt; s.egen = true; ritaTypval(); planKoll(); } }] : null);
        };
        s.starttid = tidFalt.value;
        if (window.Dagvaljare) window.Dagvaljare(wrap, knapp, dagFalt, tidFalt, {
          tom: 'Välj klockslag och längd',
          dag: false,
          span: true,
          snabb: [40, 45, 60, 80],
          langd: () => Number(s.langd) || 45,
          standardTid: schemastart() || '08:15',
          /* Återställningen ska ge tillbaka schemat, inte frysa det handsatta. */
          aterstall: () => { const m = schemaminuter(); if (m) { s.langd = m; s.langdSchema = m; } s.egen = false; visaKalla(); visaNot(); planKoll(); },
          sattLangd: m => { s.langd = m; s.egen = true; visaKalla(); visaNot(); planKoll(); }
        });
        tidFalt.addEventListener('change', () => { s.starttid = tidFalt.value; s.egen = true; visaKalla(); planKoll(); });
        visaKalla();
        visaNot();
      }
      if (k.typ === 'nartid') {
        const wrap = $('.nartidvalj', rad), knapp = $('.valjknapp', rad);
        const dagFalt = $('.nardatum', rad), tidFalt = $('.nartidstart', rad);
        const lektionsdag = () => ($('#p-datum') || {}).value || '';
        /* Ärvda upplägg bär bara provtiden som text — längden läses ur den. */
        if (!s.provminuter) s.provminuter = parseInt(s.provtid, 10) || 90;
        s.narDatum = dagFalt.value;
        s.narTid = tidFalt.value;
        /* Dagen och längden är ett löfte till kalendern: raden under säger om det
           går att hålla — lov, krock, eller en lektion som är för kort. */
        const not = typnot(rad);
        const visaNot = () => {
          const min = Number(s.provminuter) || 90;
          const ld = lektionsdag();
          /* Vilken dag som är vald avgör VAD raden ska kontrollera: en dag utanför
             lektionen mäts mot kalendern (lov, bokningar), lektionens egen dag mot
             lektionens längd. Segmentet som avgjorde det förr är borta — dagen i
             väljaren säger det själv. */
          if (s.narDatum && ld && s.narDatum !== ld) {
            const kr = window.Kalender ? window.Kalender.krockrad(s.narDatum) : null;
            return satNot(not, kr && kr.krock ? 'krock' : 'ok', kr ? versal(kr.text) : '');
          }
          if (!s.narDatum && !ld) return satNot(not, '', 'Välj dagen — lov och bokningar läses ur kalendern.');
          const lekt = schemaminuter();
          if (!lekt) return satNot(not, '', 'Ingen lektionslängd ur schemat — provtiden är fri.');
          satNot(not, min > lekt ? 'krock' : 'ok', min > lekt
            ? `Provet är ${min} min men lektionen bara ${lekt} min.`
            : `Får plats på lektionen — ${lekt} min att skriva på.`,
            min > lekt ? [
              /* «Flytta till annan dag» satte förr segmentet. Nu är dagen ett klick i
                 väljaren på samma rad — knappen slår upp den i stället för att
                 försätta raden i ett läge där ingen dag ännu är vald. */
              { namn: 'Välj en annan dag', gor: () => knapp.click() },
              { namn: `Korta till ${lekt} min`, gor: () => { s.provminuter = lekt; s.provtid = lekt + ' min'; ritaTypval(); planKoll(); } }
            ] : null);
        };
        if (window.Dagvaljare) window.Dagvaljare(wrap, knapp, dagFalt, tidFalt, {
          tom: 'Välj dag och klockslag',
          dag: true,
          span: true,
          snabb: [60, 90, 120],
          langd: () => Number(s.provminuter) || 90,
          standardTid: schemastart() || '08:15',
          sattLangd: m => { s.provminuter = m; s.provtid = m + ' min'; visaNot(); planKoll(); },
          /* Återställningen tömmer dagen, och en tom dag LÄSES som lektionens — så
             «tillbaka till lektionen» och «rensa» är samma gest här. */
          aterstall: () => { s.narDatum = ''; s.dagSchema = null; ritaTypval(); planKoll(); }
        });
        dagFalt.addEventListener('change', () => { s.narDatum = dagFalt.value; s.nar = !dagFalt.value || dagFalt.value === lektionsdag() ? 'På lektionen' : 'Annan dag'; visaNot(); planKoll(); });
        tidFalt.addEventListener('change', () => { s.narTid = tidFalt.value; visaNot(); planKoll(); });
        visaNot();
      }
      const upp = $('[data-uppskatta]', rad);
      if (upp) upp.addEventListener('click', () => uppskattaNu());
      if (k.typ === 'antal') {
        /* Ärvda uppägg kan bära ett antal som den här typen inte rymmer. */
        s[k.id] = Math.min(k.max, Math.max(k.min, Number(s[k.id]) || k.min));
        $$('[data-steg]', rad).forEach(b => b.addEventListener('click', () => {
          s[k.id] = Math.min(k.max, Math.max(k.min, s[k.id] + Number(b.dataset.steg)));
          $('.steppervarde', rad).textContent = String(s[k.id]);
          planKoll();
        }));
        const varde = $('.steppervarde', rad);
        if (varde) varde.textContent = String(s[k.id]);
      }
      if (k.typ === 'switch') {
        const b = $('.switch', rad);
        b.addEventListener('click', () => {
          s[k.id] = !s[k.id];
          b.setAttribute('aria-pressed', String(s[k.id]));
          b.style.background = s[k.id] ? 'var(--accent)' : 'var(--track)';
          b.style.borderColor = s[k.id] ? 'var(--accent)' : 'var(--line)';
          $('.knopp', b).style.transform = `translateX(${s[k.id] ? 16 : 0}px)`;
          planKoll();
        });
      }
      rader.appendChild(rad);
    });
  }

  /* ── Formuläret ───────────────────────────────────── */
  const moment = $('#moment');
  /* Gy25: innehållet hör till en NIVÅ, inte till en kurs. Nivån föreslås ur kursen
     i steg 1 men kan bytas — och brickorna här visar bara det man valt, inte hela
     nivån; hela nivån står i listan där man väljer. */
  let nivaId = window.Gy ? window.Gy.foreslagen('Matematik 3c') : '';
  const gyPunkter = () => (window.Gy ? window.Gy.punkter(nivaId) : []);
  function ritaGy() {
    const n = window.Gy ? window.Gy.niva(nivaId) : null;
    const namn = gyPunkter().map(p => p.kort);
    if (namn.length) [...vald].forEach(v => { if (!namn.includes(v)) vald.delete(v); });
    /* Brickorna ritas om utan att blinka: nya växer fram, borttagna kollapsar. */
    const chips = $('#gychips');
    const onskade = gyPunkter().filter(p => vald.has(p.kort)).map(p => p.kort);
    const gor = kort => {
      const b = document.createElement('button');
      b.className = 'gychip';
      b.type = 'button';
      b.setAttribute('aria-pressed', 'true');
      b.textContent = kort;
      b.setAttribute('aria-label', `Ta bort ${kort} ur planeringen`);
      b.addEventListener('click', () => { vald.delete(kort); ritaGy(); planKoll(); });
      return b;
    };
    if (window.ritaBrickor) window.ritaBrickor(chips, onskade, gor);
    else { chips.innerHTML = ''; onskade.forEach(k => chips.appendChild(gor(k))); }
    if (onskade.length) chips.hidden = false;
    else setTimeout(() => { if (!chips.querySelector('[data-nyckel]:not([data-ut])')) chips.hidden = true; }, 260);
    /* En knapp bär både nivån och hur mycket av den som är taget. */
    const t = $('#gyknapp .valjtext'), not = $('#nivanot');
    if (n && t) t.textContent = vald.size ? `${n.etikett} · ${vald.size} av ${gyPunkter().length}` : n.etikett;
    if (n && not) not.textContent = n.gammal ? `motsvarar ${n.gammal}` : '';
    ritaTackning();
  }
  function ritaTackning() {
    const n = window.Gy ? window.Gy.niva(nivaId) : null;
    const punkter = gyPunkter();
    const antal = vald.size;
    /* Ett spår utan fyllning är ingen mätare, bara ett streck: när inget är valt
       står meningen för sig själv. */
    $('.tackning').toggleAttribute('data-tomt', !antal);
    $('#tackfyll').style.width = (antal / Math.max(1, punkter.length) * 100) + '%';
    $('#tacktext').textContent = antal
      ? `${antal} av ${punkter.length} punkter i ${n ? n.niva : 'nivån'}`
      : 'Inget centralt innehåll valt — utkastet blir fritt formulerat';
  }
  /* Väljarna i gy.js äger listorna, planeringen äger valet. */
  window.GyVal = {
    niva: () => nivaId,
    har: t => vald.has(t),
    valda: () => [...vald],
    vaxla(t) { vald.has(t) ? vald.delete(t) : vald.add(t); ritaGy(); planKoll(); },
    rensa() { vald.clear(); ritaGy(); planKoll(); },
    sattNiva(id) {
      if (id === nivaId) return;
      const foreDetta = vald.size;
      nivaId = id;
      ritaGy();
      planKoll();
      const n = window.Gy.niva(id), kvar = vald.size;
      window.toast && window.toast(foreDetta && kvar < foreDetta
        ? `${n.etikett} — ${foreDetta - kvar} punkter hörde till förra nivån och togs bort`
        : `Innehåll ur ${n.etikett}`);
    }
  };
  function planKoll() {
    ritaArv();
    const v = moment.value.trim(), typ = valt('skrivtyp');
    $('#skriv').disabled = false;
    $('#skriv').toggleAttribute('data-vantar', !v);
    /* Ligger utkastet redan på skärmen är godkännandet sidans huvudväg. Då säger
       knappen «Skriv om» och kliver ner till ghost — förr stod två mörkblå
       knappar samtidigt och båda såg ut som nästa steg. */
    const utkast = !$('#dokument').hidden && ((versioner[nu] || {}).typ === typ);
    $('#skriv').textContent = (utkast ? 'Skriv om ' : 'Skriv ') + best(typ);
    $('#skriv').classList.toggle('nedtonad', utkast);
    /* Raden sa «Tavla om ”5.2 …” för 9A · 1 lektion som underlag» — ord för ord
       det som redan står i de två hopfällda stegraderna ovanför och i köremsan.
       Kvar står bara det ingen annan rad säger: att momentet fattas. Momentfältet
       ligger i steg 2 och är oftast fällt ihop, så «beskriv momentet ovan» pekar
       på något man inte ser — raden pekar på steget i stället. */
    const not = $('#plannot');
    not.textContent = v ? '' : `Välj avsnittet i boken i steg 2 — det blir momentet ${best(typ)} skrivs om.`;
    not.hidden = !!v;
  }
  window.planKoll = () => { ritaTypval(); planKoll(); };
  moment.addEventListener('input', planKoll);
  $('#p-klass').addEventListener('change', planKoll);
  $('#p-kurs').addEventListener('change', () => {
    /* Kursen i steg 1 pekar ut nivån — men bara så länge man inte valt innehåll själv. */
    const foreslagen = window.Gy ? window.Gy.foreslagen($('#p-kurs').value) : nivaId;
    if (foreslagen && foreslagen !== nivaId && !vald.size) nivaId = foreslagen;
    ritaGy();
    planKoll();
  });
  /* Byter man lektion byter också lektionslängden — tavlan läser om schemat. */
  $('#p-klass').addEventListener('change', () => { ritaTypval(); });
  $('#p-tid') && $('#p-tid').addEventListener('change', () => { ritaTypval(); });
  /* ── Vilka lektioner utkastet bygger på ───────────── */
  const valdaLektioner = new Set();
  const lektioner = () => $$('#inspelningar .kort').map(k => {
    const tumme = $('.tumme', k), slot = tumme && tumme.querySelector('image-slot');
    return {
      el: k,
      namn: $('.namn', k).textContent.trim(),
      klass: k.dataset.klass, kurs: k.dataset.kurs, datum: k.dataset.datum,
      vecka: k.closest('.veckogrupp') ? $('.vecka', k.closest('.veckogrupp')).textContent : '',
      spann: k.closest('.veckogrupp') ? $('.spann', k.closest('.veckogrupp')).textContent : '',
      langd: $('.tumtid', k) ? $('.tumtid', k).textContent : '',
      typ: tumme && tumme.dataset.typ === 'ljud' ? 'ljud' : 'video',
      bild: slot && slot.shadowRoot ? ((slot.shadowRoot.querySelector('img[src]') || {}).src || '') : ''
    };
  });
  const minuter = t => { const d = String(t).split(':').map(Number); return d.length === 2 ? d[0] + d[1] / 60 : 0; };
  const tidstext = m => m >= 60 ? `${Math.floor(m / 60)} h ${Math.round(m % 60)} min` : `${Math.round(m)} min`;
  const valdaNamn = () => lektioner().filter(l => valdaLektioner.has(l.namn));
  function ritaKallval() {
    const v = valdaNamn();
    const wrap = $('#lektionsvalj');
    /* Knappens egen text ägs av kallor.js — den skrevs förr av båda filerna, och
       då stod «1 lektion» eller «Välj en annan lektion» beroende på vilken som
       råkade rita sist. Här sätts bara det wrap-tillstånd som styr formen.
       Raden som stod ovanför kalendern är också borta: kortet under kalendern
       namnger redan lektionen, dagen, veckan och längden, och dörren och kvittot
       säger det en gång var till. Fyra röster om samma val är tre för många. */
    v.length ? wrap.setAttribute('data-satt', '') : wrap.removeAttribute('data-satt');
    const chips = $('#valdalektioner');
    const gor = namn => {
      const b = document.createElement('button');
      b.className = 'lchip';
      b.type = 'button';
      b.innerHTML = '<span></span><i>✕</i>';
      $('span', b).textContent = namn;
      b.dataset.tip = 'Ta bort ur underlaget';
      b.addEventListener('click', () => { valdaLektioner.delete(namn); ritaKallval(); planKoll(); });
      return b;
    };
    if (window.ritaBrickor) window.ritaBrickor(chips, v.map(l => l.namn), gor);
    else { chips.innerHTML = ''; v.forEach(l => chips.appendChild(gor(l.namn))); }
    planKoll();
  }
  (() => {
    const wrap = $('#lektionsvalj'), knapp = $('#lektionsknapp');
    let panel = null;
    const stang = () => {
      if (!panel) return;
      const p = panel; panel = null;
      p.setAttribute('data-ut', '');
      setTimeout(() => p.remove(), 180);
      wrap.removeAttribute('data-oppen');
      knapp.setAttribute('aria-expanded', 'false');
      document.removeEventListener('pointerdown', ut, true);
      document.removeEventListener('keydown', tangent, true);
    };
    const ut = e => { if (!wrap.contains(e.target)) stang(); };
    const tangent = e => { if (e.key === 'Escape') { stang(); knapp.focus(); } };
    let sokord = '';
    function ritaPanel() {
      const alla = lektioner();
      const q = sokord.trim().toLowerCase();
      const lista = q
        ? alla.filter(l => (l.namn + ' ' + l.klass + ' ' + l.kurs + ' ' + l.vecka).toLowerCase().includes(q))
        : alla;
      const grupper = [...new Set(lista.map(l => l.vecka))];
      const total = valdaNamn().reduce((a, l) => a + minuter(l.langd), 0);
      panel.innerHTML = `<div class="lsokrad"><input type="text" placeholder="Sök lektion, klass eller kurs …" value="${sokord.replace(/"/g, '&quot;')}" aria-label="Sök lektion" /></div>`
        + (lista.length
          ? grupper.map(g => {
            const iGrupp = lista.filter(l => l.vecka === g);
            const allaValda = iGrupp.every(l => valdaLektioner.has(l.namn));
            return `<div class="lgrupprad"><span class="lg">${g}${iGrupp[0].spann ? ' · ' + iGrupp[0].spann : ''}</span><button class="lgalla" type="button" data-grupp="${g}">${allaValda ? 'Avmarkera' : 'Välj alla'}</button></div>`
              + iGrupp.map(l => `<button class="lrad-val" type="button" role="option" data-namn="${l.namn.replace(/"/g, '&quot;')}" aria-selected="${valdaLektioner.has(l.namn)}">
                  <span class="lkryss">✓</span>
                  <span class="ltum" data-typ="${l.typ}">${l.typ === 'ljud' ? 'LJUD' : l.bild ? `<img src="${l.bild}" alt="" />` : ''}</span>
                  <span><span class="lvnamn"></span><span class="lvmeta"${l.klass || l.kurs ? '' : ' data-tom'}>${[l.klass, l.kurs].filter(Boolean).join(' · ') || 'Ingen klass eller kurs'}</span></span>
                  <span class="lvlangd">${l.langd}</span>
                </button>`).join('');
          }).join('')
          : '<p class="ltomsok">Ingen lektion matchar sökningen.</p>')
        + `<div class="valjfot"><button class="lank" type="button" data-inga>Rensa</button><span class="summa">${valdaLektioner.size ? `${valdaLektioner.size} valda · ${tidstext(total)}` : 'Inget valt'}</span></div>`;
      /* Ett kryss ska se ut som ett kryss som sätts — inte som en lista som
         byts ut. Raden uppdateras därför på plats, och bara texterna som
         faktiskt ändrats skrivs om. */
      const synka = () => {
        $$('.lrad-val', panel).forEach(r => r.setAttribute('aria-selected', String(valdaLektioner.has(r.dataset.namn))));
        $$('[data-grupp]', panel).forEach(b => {
          const iGrupp = lista.filter(l => l.vecka === b.dataset.grupp);
          b.textContent = iGrupp.length && iGrupp.every(l => valdaLektioner.has(l.namn)) ? 'Avmarkera' : 'Välj alla';
        });
        const s = $('.valjfot .summa', panel);
        if (s) s.textContent = valdaLektioner.size
          ? `${valdaLektioner.size} valda · ${tidstext(valdaNamn().reduce((a, l) => a + minuter(l.langd), 0))}`
          : 'Inget valt';
        ritaKallval();
      };
      $$('.lrad-val', panel).forEach(r => {
        $('.lvnamn', r).textContent = r.dataset.namn;
        r.addEventListener('click', () => {
          const n = r.dataset.namn;
          valdaLektioner.has(n) ? valdaLektioner.delete(n) : valdaLektioner.add(n);
          synka();
        });
      });
      /* «Välj alla» kryssar raderna i tur och ordning — femton kryss på en gång
         läses inte, femton kryss efter varandra gör det. */
      const ivag = (rader, gor) => rader.forEach((l, i) => setTimeout(() => { gor(l); synka(); }, Math.min(i * 45, 400)));
      $$('[data-grupp]', panel).forEach(b => b.addEventListener('click', () => {
        const iGrupp = lista.filter(l => l.vecka === b.dataset.grupp);
        const allaValda = iGrupp.every(l => valdaLektioner.has(l.namn));
        ivag(iGrupp, l => allaValda ? valdaLektioner.delete(l.namn) : valdaLektioner.add(l.namn));
      }));
      const inga = $('[data-inga]', panel);
      if (inga) inga.addEventListener('click', () => ivag(valdaNamn(), l => valdaLektioner.delete(l.namn)));
      const sok = $('.lsokrad input', panel);
      sok.addEventListener('input', () => {
        sokord = sok.value;
        const pos = sok.selectionStart;
        ritaPanel();
        const nytt = $('.lsokrad input', panel);
        nytt.focus();
        nytt.setSelectionRange(pos, pos);
      });
    }

    const oppnaPanel = () => {
      if (panel) return;
      panel = document.createElement('div');
      panel.className = 'valjpanel brett';
      panel.setAttribute('role', 'listbox');
      panel.setAttribute('aria-multiselectable', 'true');
      wrap.appendChild(panel);
      wrap.setAttribute('data-oppen', '');
      knapp.setAttribute('aria-expanded', 'true');
      ritaPanel();
      if (window.centreraPanel) window.centreraPanel(panel);
      document.addEventListener('pointerdown', ut, true);
      document.addEventListener('keydown', tangent, true);
    };
    knapp.addEventListener('click', () => (panel ? stang() : oppnaPanel()));
    if (matchMedia('(hover:hover) and (pointer:fine)').matches) {
      let fordrojd;
      wrap.addEventListener('pointerenter', () => clearTimeout(fordrojd));
      wrap.addEventListener('pointerleave', e => { if (e.pointerType === 'touch') return; fordrojd = setTimeout(() => { if (panel) stang(); }, 70); });
    }
  })();

  /* ── Innehåll ─────────────────────────────────────── */
  const versal = s => s.charAt(0).toUpperCase() + s.slice(1);
  const tillMin = t => { const m = String(t || '').match(/(\d{1,2})[:.](\d{2})/); return m ? +m[1] * 60 + +m[2] : null; };
  const franMin = m => `${String(Math.floor((((m % 1440) + 1440) % 1440) / 60)).padStart(2, '0')}:${String(((m % 60) + 60) % 60).padStart(2, '0')}`;
  /* Provet har en egen dag och ett eget klockslag — valen i steg 3, inte
     lektionens. Utan det här sa «Annan dag» en sak och dokumentet en annan. */
  function provNar() {
    const s = inst.Prov;
    const min = Math.max(5, Number(s.provminuter) || 90);
    const start = s.narTid || schemastart() || '08:15';
    const b = tillMin(start);
    return {
      /* Dagen står i upplägget, inte i lektionsfältet: `narDatum` ärvs ur
         lektionen och skrivs över när läraren klickar en annan dag i väljaren,
         så den ENA raden är sanningen om båda fallen. */
      datum: s.narDatum || ($('#p-datum').value || ''),
      tid: b == null ? '' : `${franMin(b)}–${franMin(b + min)}`,
      minuter: min
    };
  }
  function nyVersion(bas, andring) {
    const vtyp = valt('skrivtyp');
    const nar = vtyp === 'Prov' ? provNar() : null;
    /* Ingen lektion vald i veckan? Då ärvs klass och kurs ur lektionen utkastet
       UTGÅR FRÅN. «Ingen klass · ingen kurs» hjälper ingen — och appen vet. */
    const ur = valdaNamn()[0] || null;
    const v = bas
      ? JSON.parse(JSON.stringify(bas))
      : {
        typ: vtyp, moment: moment.value.trim(),
        klass: $('#p-klass').value || (ur && ur.klass) || '',
        kurs: $('#p-kurs').value || (ur && ur.kurs) || '',
        datum: nar ? nar.datum : $('#p-datum').value, tid: nar ? nar.tid : $('#p-tid').value,
        lektionsdatum: $('#p-datum').value, lektionstid: $('#p-tid').value,
        gy: [...vald], kalla: valdaLektioner.size > 0, kallor: valdaNamn().map(l => l.namn),
        /* Boksidorna följer med dokumentet: tavlan skriver upp dem åt eleverna,
           och utan dem skulle den peka på förlagans sidor i stället för klassens. */
        sidor: (() => { const s = window.Uppslag && window.Uppslag.spann ? window.Uppslag.spann() : null; return s && s.fran ? `${s.fran}–${s.till}` : (moment.dataset.sidor || '').replace(/^s\.\s*/, ''); })(),
        /* Uppgiftsurvalet ur boken följer med pappret: tavlan skriver upp det i
           vänsterspalten, lösningsförslagen skrivs till just de uppgifterna och
           paketet i Att skriva ut lägger dem som ett eget ark. Snapshot, inte
           uppslag — en tavla i Sparat ska peka på de uppgifter den skrevs för. */
        bokuppg: window.Uppgifter && window.Uppgifter.urval ? window.Uppgifter.urval(inst[vtyp]) : null,
        inst: JSON.parse(JSON.stringify(inst[vtyp])), bilder: {}, referenser: window.Sidor ? window.Sidor.lista() : [],
        forlaga: refDok ? { namn: dokNamn(refDok), typ: refDok.typ, moment: refDok.moment, datum: refDok.datum, hur: ($('#refhur') || {}).value ? $('#refhur').value.trim() : '' } : null,
        /* Utfallet och viktningen följer med pappret: canvasen visar dem som
           källor, och nästa ändring vet vad som vägde tyngst när det skrevs. */
        resultat: resDok ? { namn: dokNamn(resDok), datum: resDok.datum, klass: resDok.klass || '', rattat: JSON.parse(JSON.stringify(resDok.rattat || {})) } : null,
        fokus: ($('#fokus') || {}).value ? $('#fokus').value.trim() : '',
        kontext: 'start', niva: false, svarighet: 0, andrat: [], anteckning: 'Första utkastet'
      };
    v.andrat = [];
    if (andring) andring(v);
    v.uppgifter = uppgifter(v);
    return v;
  }
  function uppgifter(v) {
    /* Uppgifterna står på pappret. Rättningen, «8 uppgifter» och poängsummorna
       läser samma lista, annars säger appen en sak och bladet en annan. */
    if (window.Blad) return window.Blad.uppgifter(v);
    const m = v.moment.toLowerCase(), k = KONTEXT[v.kontext], i = v.inst || {};
    const nivaText = i.niva || (i.nivamix === 'Bara E' || i.nivamix === 'E-tyngd' ? 'E-nivå' : i.nivamix === 'C/A-tyngd' ? 'A-nivå' : 'Blandat');
    const lyft = nivaText === 'A-nivå' ? 1 : nivaText === 'E-nivå' ? -1 : 0;
    const svar = (v.svarighet || 0) + lyft;
    const mallar = [
      { t: `Förklara med egna ord vad ${m} innebär. Ge ett exempel.`, p: 2, f: 'Begreppet beskrivet + ett korrekt exempel.' },
      { t: `Beräkna med hjälp av ${m}.`, del: ['enkelt fall', 'fall som kräver ett mellansteg'], p: 4, f: 'a) 6  b) 2x + h → 2x' },
      { t: `Ett ${k} sammanhang: en storhet ändras över tid. Bestäm förändringen i den angivna punkten och tolka svaret.`, p: 4, f: 'Derivata i punkten, tolkning i storhetens enhet.' },
      { t: 'Avgör om påståendet är sant och motivera.', p: 3, f: 'Motargument eller bevisidé räcker.' },
      { t: 'Lös problemet och redovisa hela lösningen.', p: 5, f: 'Fullständig lösning med tolkning.' },
      { t: `Skissa en graf som visar hur ${m} förändras och förklara vad lutningen betyder.`, p: 4, f: 'Graf med korrekt lutningsresonemang.' },
      { t: `Två elever räknar olika och får olika svar. Avgör vem som har rätt och var felet ligger.`, p: 4, f: 'Felet identifierat och rättat.' },
      { t: `Härled sambandet och visa att det gäller generellt.`, p: 6, f: 'Korrekt härledning i alla steg.' }
    ];
    const antal = Math.max(3, Math.min(12, i.antal || 5));
    const bas = Array.from({ length: antal }, (_, n) => ({ ...mallar[n % mallar.length] }));
    if (svar > 0) {
      bas.forEach((u, n) => { if (n % 2 === 1) { u.p = Math.min(8, u.p + 2); } });
      if (bas[2]) bas[2].t = `Ett ${k} sammanhang där sambandet inte är givet: ställ upp det själv, bestäm förändringen och tolka svaret.`;
    }
    if (svar < 0) {
      bas.forEach(u => { u.p = Math.max(1, u.p - 1); });
      if (bas[2]) bas[2].t = `Ett ${k} sammanhang: sambandet är givet. Bestäm förändringen och tolka svaret.`;
    }
    if (v.niva || i.delprov === 'Del A + Del B') {
      bas.push({ t: 'Fördjupning: visa varför metoden fungerar även när villkoret inte är uppfyllt.', p: 4, f: 'Resonemang som håller generellt.', niva: true });
      if (v.typ === 'Prov') bas.push({ t: `Modellera situationen, lös den med ${m} och värdera rimligheten i svaret.`, p: 6, f: 'Modell, lösning och värdering.', niva: true });
    }
    return bas.map((u, n) => ({ ...u, nr: n + 1 }));
  }

  /* ── Rendering per format ─────────────────────────── */
  const datumText = v => v.datum
    ? new Date(v.datum + 'T12:00:00').toLocaleDateString('sv-SE', { weekday: 'long', day: 'numeric', month: 'long' }) + (v.tid ? ' · ' + v.tid : '')
    : 'utan datum';
  const mark = (v, nyckel) => v.andrat.includes(nyckel) ? ' andrad' : '';

  /* ── Gruppuppgiften (fjärde dokumenttypen) ───────────────────
     Ifyllnadsställningen väljs aldrig ur ett mallbibliotek — den följer av vad
     uppgiften är. Beskriver momentet en undersökning blir ställningen hypotes,
     metod, mätning, slutsats; en diskussion ger påstående och motargument. */
  function stallning(m) {
    const t = String(m || '').toLowerCase();
    if (/undersök|labor|mät|experiment|data|statistik/.test(t)) return {
      slag: 'Undersökning',
      steg: [
        ['Vad tror ni händer?', 'Skriv en hypotes ni kan pröva — inte en gissning utan skäl.'],
        ['Hur mäter ni?', 'Bestäm metod, vad som varieras och vad som hålls konstant.'],
        ['Mätningarna', 'För in värdena i tabellen. Räkna om till samma enhet.'],
        ['Vad visar de?', 'Beskriv sambandet i ord, och sedan med ett uttryck.'],
        ['Håller hypotesen?', 'Svara på er egen fråga och säg vad som skulle kunna vara fel.']
      ]
    };
    if (/diskut|resonemang|argument|etik|jämför|värdera/.test(t)) return {
      slag: 'Diskussion',
      steg: [
        ['Påståendet', 'Skriv om påståendet med egna ord så att alla i gruppen menar samma sak.'],
        ['Argument för', 'Minst två — matematiska, inte tyckanden.'],
        ['Argument mot', 'Minst två. Den som håller med måste ändå hitta ett.'],
        ['Vad avgör?', 'Vilket argument väger tyngst, och varför?'],
        ['Gruppens svar', 'En mening ni alla kan stå för — och den invändning som blev kvar.']
      ]
    };
    if (/model|tillämp|verklig|problem/.test(t)) return {
      slag: 'Modellering',
      steg: [
        ['Situationen', 'Vad ska ni ta reda på? Skriv frågan som en mening.'],
        ['Antaganden', 'Vad förenklar ni bort? Var ärliga — det är antagandena som avgör svaret.'],
        ['Modellen', 'Ställ upp uttrycket och namnge varje variabel.'],
        ['Räkningen', 'Genomför den så att en annan grupp kan följa er.'],
        ['Rimligheten', 'Kan svaret stämma i verkligheten? Vad skulle göra det bättre?']
      ]
    };
    return {
      slag: 'Samarbete',
      steg: [
        ['Problemet', 'Skriv uppgiften med egna ord. Vad är känt, vad söks?'],
        ['Gruppens plan', 'Vilken väg väljer ni, och varför just den?'],
        ['Vem gör vad', 'Fördela stegen. Alla ska kunna redovisa hela lösningen.'],
        ['Lösningen', 'Redovisa så att den går att följa utan er röst till.'],
        ['Vad lärde ni er?', 'En sak ni skulle göra annorlunda nästa gång.']
      ]
    };
  }
  /* ── Gruppuppgiften som tryckt arbetsblad ────────────────────
     Den generiska formen (numrerade rader i en lista) var appens, inte lärarens.
     Ett papper som ligger på ett bord under en lektion har en annan grammatik:
     rubrik, ett grått instruktionsband, bokstavsbrickor och ifyllnadsrader man
     skriver på. Ställningen är densamma som förut — det är sättningen som byts.

     Varje steg blir en ruta med bokstav. Steget som handlar om något ritbart får
     en figur i höger spalt, kompilerad ur CeTZ; de andra är bara text. Vilka
     rader man skriver på följer av vad steget frågar: ett mätsteg vill ha en
     tabellrad, ett resonemangssteg vill ha flera linjer. */
  const BOKSTAV = 'ABCDEFGH';
  /* ── Figuren, en gång för alla dokumenttyper ──
     Prov, arbetsblad, tavlor och gruppuppgifter ritar samma figur i samma
     storlek. Byggs den per dokumenttyp driver de isär, och det som är läsbart på
     ett arbetsblad blir en miniatyr på ett prov. */
  const figurFor = v => window.Figurer && window.Figurer.forslagFor
    ? window.Figurer.forslagFor(v.moment, v.kurs) : null;
  function figurbit(forslag, klass) {
    if (!forslag) return '';
    const kalla = window.Figurer.kalla(forslag.fig);
    if (!kalla) return '';
    return `<div><div class="${klass}" data-vantar data-cetz="${String(kalla).replace(/"/g, '&quot;')}"></div><p class="${klass}kap">${forslag.kapning}</p></div>`;
  }
  /* Raderna under en fråga följer av frågan. Ett steg som ber om en storhet får
     en namngiven rad; ett som ber om ett resonemang får rena skrivlinjer. */
  function stegrader(rubrik, n) {
    const r = String(rubrik).toLowerCase();
    if (/hypotes|påstående|pastaende|problemet|situationen|frågan|fragan/.test(r)) return { rader: ['Med egna ord'], linjer: 1 };
    if (/mät|mat|mätning|matning|räkning|rakning|lösning|losning|modellen|beräkn/.test(r)) return { rader: ['Uttryck', 'Svar'], linjer: 1 };
    if (/antagand|argument|vad avgör|vad avgor|rimlig|håller|haller|lärde|larde/.test(r)) return { rader: [], linjer: 3 };
    if (/vem gör|vem gor|plan/.test(r)) return { rader: ['Vem gör vad'], linjer: 2 };
    return { rader: ['Svar'], linjer: 1 };
  }
  function ritaGrupp(v) {
    const i = v.inst || {};
    const s = stallning(v.moment);
    const per = Math.round((i.langd || 60) / (s.steg.length + 1));
    /* Figuren hör till ETT steg, och till RÄTT steg: det som handlar om själva
       sambandet. På «vem gör vad» är en graf dekor, inte hjälp. */
    const forslag = figurFor(v);
    const barFigur = /modell|lösning|losning|räkning|rakning|mätning|matning|situationen|problemet|påståendet|pastaendet/i;
    const figurSteg = forslag ? (s.steg.findIndex(([r]) => barFigur.test(r)) + 1 || 1) - 1 : -1;
    const kalla = forslag && window.Figurer.kalla ? window.Figurer.kalla(forslag.fig) : null;

    const huvud = `<div class="guhuv" data-el="rubrik" data-namn="Sidhuvudet"><h4 class="gutitel">${versal(v.moment)}</h4></div>`;
    const band = `<div class="guband" data-el="instr" data-namn="Instruktionen">Arbeta i grupp om ${i.grupp || 3}. Fyll i rutorna <b>i ordning</b> — en i taget, och alla ska kunna redovisa hela lösningen. Redovisning: ${(i.redovisning || 'Muntligt').toLowerCase()}.${(v.gy || []).length ? ` Centralt innehåll: ${v.gy.join(' · ')}.` : ''}</div>`;

    const kort = s.steg.map(([rubrik, stod], n) => {
      const f = stegrader(rubrik, n);
      /* En rad som heter samma sak som frågan säger inget nytt — då står bara
         linjen där, utan etikett. */
      const rader = f.rader.filter(namn => namn.toLowerCase() !== String(rubrik).toLowerCase())
        .map(namn => `<div class="gurad"><span class="gunamn">${namn}:</span><span class="gulinje"></span></div>`).join('')
        + '<p class="gulos">Lösningen skrivs på lösblad.</p>';
      const fraga = `<p class="gufraga">${rubrik} — <i>${stod}</i></p>`;
      const kropp = n === figurSteg && kalla
        ? `<div class="gutva">${'<div>' + fraga + rader + '</div>'}${figurbit(forslag, 'gufigur')}</div>`
        : fraga + rader;
      return `<div class="gukort${mark(v, 'steg' + n)}" data-el="steg${n}" data-namn="${rubrik}"><div class="gukorttopp"><span class="gubricka">${BOKSTAV[n]}</span><span class="gutid">${per} min</span></div>${kropp}</div>`;
    }).join('');

    const namnrader = Array.from({ length: Math.min(4, Math.max(2, i.grupp || 3)) },
      () => '<div class="gurad"><span class="gunamn">Namn:</span><span class="gulinje"></span></div>').join('');
    return `<div class="ark gruppark" data-sida="1">${huvud}<div class="gutopp" data-el="namn" data-namn="Namnraderna">${namnrader}</div>${band}${kort}</div>`;
  }

  function ritaTavla(v) {
    const m = v.moment, i = v.inst || {};
    const forslag = figurFor(v);
    const minuter = Number(i.langd) || 45;
    const exempel = Math.max(1, Math.min(4, i.exempel || 2));
    const del = [0.12, 0.34, 0.26, 0.2, 0.08].map(x => Math.round(x * minuter));
    let t = 0;
    const spann = () => { const fran = t; t += del.shift(); return `${fran}–${t}`; };
    const block = [
      { min: spann(), h: 'Ingång', p: `Varför ${m.toLowerCase()}? Koppling till förra lektionen.` },
      { min: spann(), h: 'Genomgång', p: `${exempel} exempel på tavlan, det sista med mellansteg.`, ex: v.kontext === 'start' ? Array.from({ length: exempel }, (_, n) => n === 0 ? 'f(x) = x²  →  f′(x) = 2x' : 'f(x) = 3x² − 2x  →  f′(x) = 6x − 2').join('     ') : `${versal(KONTEXT[v.kontext])} exempel — ${exempel} st` },
      { min: spann(), h: 'Elevuppgift', p: 'Räkna i par. Gå runt och lyssna.' },
      { min: spann(), h: 'Återsamling', p: 'Vanliga fel på tavlan — särskilt tecken vid negativa värden.' },
      { min: spann(), h: 'Avslut', p: 'Sammanfatta i tre punkter och peka framåt.' }
    ];
    return `<div class="tavla"><h4 class="ttitel" data-el="rubrik" data-namn="Rubriken">${versal(m)}</h4>${(v.referenser || []).length ? `<p class="tref" data-el="referens" data-namn="Bokreferensen">Utgår från ${v.referenser.length} ${v.referenser.length === 1 ? 'uppladdad sida' : 'uppladdade sidor'} ur läroboken · ${v.referenser.map(r => r.namn).join(', ')}</p>` : ''}<p class="tunder">${[v.kurs || 'Ingen kurs', v.klass || 'ingen klass', datumText(v)].join(' · ')} · ${minuter} min</p>
      ${block.map((b, n) => `<div class="tblock${mark(v, 'block' + n)}"${n === 1 && forslag ? ' data-figur-plats' : ''} data-el="block${n}" data-namn="${b.h} · ${b.min} min"><span class="tmin">${b.min}</span><div class="tinnehall"><div><h4>${b.h}</h4><p>${b.p}</p>${b.ex ? `<p class="texempel">${b.ex}</p>` : ''}${(v.bilder || {})['block' + n] ? `<img class="tbild" src="${v.bilder['block' + n]}" alt="" />` : ''}</div>${n === 1 ? figurbit(forslag, 'dokfigur') : ''}</div></div>`).join('')}
      </div>`;
  }

  function ritaArk(v) {
    const prov = v.typ === 'Prov';
    const summa = v.uppgifter.reduce((a, u) => a + u.p, 0);
    const huvud = `<div class="ahuvud" data-el="rubrik" data-namn="Sidhuvudet"><div class="av"><h4 class="atitel">${prov ? 'Prov' : 'Arbetsblad'} — ${versal(v.moment)}</h4><p class="aunder">${[v.kurs || 'Ingen kurs', v.klass || 'ingen klass', datumText(v)].join(' · ')}</p></div><div class="apoang">${prov ? `${summa} p<br />90 min` : `${v.uppgifter.length} uppgifter`}</div></div>`;
    const instr = `<p class="ainstr${mark(v, 'instr')}" data-el="instr" data-namn="Instruktionen">${prov
      ? 'Skriv dina lösningar så att de går att följa. Endast penna, sudd och linjal. Räknare är inte tillåten på del 1.'
      : 'Arbeta i den ordning du vill. Redovisa hur du tänker — svaret räcker inte.'}${v.gy.length ? ` <b>Centralt innehåll:</b> ${v.gy.join(' · ')}.` : ''}</p>`;
    const forslag = figurFor(v);
    /* Figuren hör till den tillämpade uppgiften, inte till begreppsfrågan och
       inte till varje rad — då blir den dekor. */
    const figurNr = forslag ? (v.uppgifter[2] ? 3 : 1) : -1;
    const rad = u => {
      const figur = u.nr === figurNr ? figurbit(forslag, 'dokfigur') : '';
      return `<div class="uppg${mark(v, 'uppg' + u.nr)}"${figur ? ' data-figur-plats' : ''} data-el="uppg${u.nr}" data-namn="Uppgift ${u.nr}"><span class="unr">${u.nr}</span><span class="utext">${u.t}${(u.del || []).map(d => `<span class="del">${d}</span>`).join('')}${prov ? '' : `<span class="usvar${u.p > 4 ? ' uhog' : ''}"></span>`}${u.f ? `<span class="afacit">Facit: ${u.f}</span>` : ''}</span>${figur}<span class="upoang">${prov ? u.p + ' p' : ''}</span></div>`;
    };
    const vanliga = v.uppgifter.filter(u => !u.niva), extra = v.uppgifter.filter(u => u.niva);
    return `<div class="ark" data-sida="1">${huvud}${instr}<div class="auppg">${vanliga.map(rad).join('')}</div>
      ${extra.length ? `<div class="aniva andrad" data-el="niva" data-namn="${prov ? 'Del B' : 'Nivå B'}"><p class="anivarubrik">${prov ? 'Del B · högre nivå' : 'Nivå B — för den som vill mer'}</p><div class="auppg">${extra.map(rad).join('')}</div></div>` : ''}
      <span class="asidnr">1 / 1 · ${prov ? summa + ' p' : 'arbetsblad'}</span></div>`;
  }

  /* Provet är elevens dokument. Lösningsförslaget är lärarens — ett eget ark,
     inte facit intryckt i provet. Växlaren visas bara när det finns ett. */
  let visarLosning = false;
  /* Facit finns till allt som har uppgifter: provet, arbetsbladet och
     gruppuppgiften. Gruppuppgiften saknade det förut — det var en lucka, inte
     ett val: det är just gruppuppgifterna läraren går igenom på tavlan efteråt. */
  const harLosning = v => v.typ === 'Prov'
    ? !!(v.inst || {}).losningar
    : v.typ === 'Arbetsblad' ? (v.inst || {}).facit === 'Separat facit'
      : v.typ === 'Gruppuppgift';
  function visa(i, ark) {
    nu = i;
    const v = versioner[i];
    $('#dokument').hidden = false;
    /* Metaraden ska säga hela underlaget, inte bara lektionerna: papperen från
       lektionen är också något dokumentet är byggt på. */
    const pap = window.Lektionsmaterial ? window.Lektionsmaterial.antal() : 0;
    const antalK = (v.kallor || []).length;
    const byggt = antalK
      ? `byggt på ${antalK} ${antalK === 1 ? 'lektion' : 'lektioner'}${pap ? ` och ${pap} papper` : ''}`
      : 'fritt skrivet';
    $('#doktyp').textContent = v.typ;
    $('#dokmeta').textContent = [v.kurs || 'ingen kurs', v.klass || 'ingen klass', datumText(v),
      v.kalla ? byggt : 'fritt skrivet'].join(' · ');
    const vaxel = $('#arkval'), tva = harLosning(v);
    vaxel.hidden = !tva;
    if (!tva) visarLosning = false;
    $$('button', vaxel).forEach((b, j) => {
      b.textContent = j === 0
        ? (v.typ === 'Prov' ? 'Provet' : 'Arbetsbladet')
        : (v.typ === 'Prov' ? 'Lösningsförslag' : 'Facit');
      b.setAttribute('aria-pressed', String(j === (visarLosning ? 1 : 0)));
    });
    const d = visarLosning ? Object.assign(JSON.parse(JSON.stringify(v)), { losningsblad: true }) : v;
    /* Formen är bestämd i «Arbetsblad prov och tavlor — femton former»: bladen
       ritas därifrån, inte ur appens egna mallar. */
    const skal = $('#arkskal');
    ritaIn(skal, d);
    ritaHistorik();
    satKrymp($('#dokument').hasAttribute('data-litet'));
    omGranska(ark);
  }

  /* Historiken är ångra/gör om — inte namngivna versioner. Tio ändringar ger tio steg
     bakåt, inte tio brickor att välja mellan. Att ändra från ett ångrat läge kapar
     det som låg framåt (samma regel som i en textredigerare). */
  const kortNot = t => { t = String(t || '').trim(); return t.length > 46 ? t.slice(0, 45) + '…' : t; };
  function ritaHistorik() {
    const kanAngra = nu > 0, kanGorOm = nu >= 0 && nu < versioner.length - 1;
    const v = versioner[nu];
    const steg = !v ? '' : nu === 0 ? 'Första utkastet' : `Ändring ${nu} av ${versioner.length - 1}`;
    const helt = !v || nu === 0 ? steg : `${steg}${v.anteckning ? ' · ' + kortNot(v.anteckning) : ''}`;
    [['#angra', '#gorom', '#histnot', helt], ['#g-angra', '#g-gorom', '#g-histnot', steg]].forEach(([a, g, n, txt]) => {
      const ea = $(a), eg = $(g), en = $(n);
      if (ea) ea.disabled = !kanAngra;
      if (eg) eg.disabled = !kanGorOm;
      if (en) { en.textContent = txt; en.dataset.tip = helt; }
    });
  }
  function angra() {
    if (nu <= 0) return;
    visa(nu - 1);
    window.toast && window.toast('Ändringen ångrad', 'Gör om', gorOm);
  }
  function gorOm() {
    if (nu < 0 || nu >= versioner.length - 1) return;
    visa(nu + 1);
  }

  $('#skriv').addEventListener('click', () => {
    if (window.Lagen && !window.Lagen().length) {
      if (window.PlanSteg) window.PlanSteg.gaTill(2);
      window.toast && window.toast('Välj först vad som ska skapas');
      return;
    }
    if (!moment.value.trim()) {
      /* Fältet ligger i steg 2 och är fällt ihop när man står här. En puls på ett
         dolt fält är ingen puls — öppna steget där valet görs i stället, och peka
         där först när fältet faktiskt syns. */
      if (!moment.offsetParent) {
        /* data-steg 3 är steget som heter «2 · Utgår från» — det är där boken bor. */
        if (window.PlanSteg) window.PlanSteg.gaTill(3);
        window.toast && window.toast('Välj avsnittet i boken — det blir momentet');
        return;
      }
      const r = moment.getBoundingClientRect();
      if (r.top < 80 || r.bottom > innerHeight - 80) {
        const mal = Math.max(0, r.top + scrollY - innerHeight / 2 + r.height);
        window.rullaTill ? window.rullaTill(mal, 520) : window.scrollTo(0, mal);
      }
      moment.focus({ preventScroll: true });
      moment.classList.remove('pekar');
      void moment.offsetWidth;
      moment.classList.add('pekar');
      window.toast && window.toast('Säg vad lektionen handlar om — eller välj ett avsnitt i boken');
      setTimeout(() => moment.classList.remove('pekar'), 2400);
      return;
    }
    const typ = valt('skrivtyp');
    $('#skriv').disabled = true;
    const not = $('#plannot');
    const gammal = not.textContent;
    const underlag = valdaNamn();
    /* Utkastet får sina värden NÄR man trycker Skriv, inte när texten kommer
       tillbaka: hinner man byta lektion under tiden ska pappret ändå bära den
       lektion man skrev det för. */
    const utkast = nyVersion(null);
    window.Fraga.kor($('#skrivstatus'), {
      /* Smalt läge: en rad, ett tunt spår, en klocka — samma diskreta förlopp som i
         lektionschatten. Sidan följer med ner till raden i stället för att låta den
         poppa upp utanför synfältet. */
      smal: true,
      omfang: underlag.length ? `${underlag.length} lektion${underlag.length === 1 ? '' : 'er'} ur arkivet` : 'Gy25 och kursplanen',
      antal: underlag.length || vald.size || 5,
      svar: `Utkastet är skrivet. ${Best(typ)} täcker ${vald.size || 'inga'} valda moment — läs igenom och skriv vad som ska bli annorlunda.`,
      plan: [
        { namn: 'Läser centralt innehåll (Gy25)', detalj: (vald.size || 0) + ' moment' },
        ...(refDok ? [{ namn: 'Läser förlagan', detalj: dokNamn(refDok) + (($('#refhur') || {}).value ? ' · ' + $('#refhur').value.trim().slice(0, 40) : '') }] : []),
        ...(resDok ? [{ namn: 'Läser provets utfall', detalj: (((resDok.rattat || {}).svaga || []).map(s => s.kod).filter(Boolean).join(', ') || dokNamn(resDok)) + ' föll' }] : []),
        ...(($('#fokus') || {}).value && $('#fokus').value.trim() ? [{ namn: 'Väger källorna', detalj: $('#fokus').value.trim().slice(0, 46) }] : []),
        { namn: underlag.length ? 'Läser vad klassen hann med' : 'Hoppar över transkripten', detalj: underlag.length ? underlag.map(l => l.namn).join(' · ') : 'inga lektioner valda' },
        { namn: 'Skriver och poängsätter', detalj: typ }
      ],
      efterKlar: () => {
        versioner = [utkast];
        /* Ett nytt dokument öppnas alltid på ELEVERNAS ark. Stod växlaren kvar på
           facit sedan förra dokumentet fick läraren lösningsgången i stället för
           uppgifterna — och kunde bara ändra i facit. */
        visarLosning = false;
        if (omprovAv && versioner[0].typ === omprovAv.typ) markeraOmprov(versioner[0]);
        $('#dokument').setAttribute('data-litet', '');
        visa(0);
        $('#skriv').disabled = false;
        planKoll();
        not.textContent = gammal;
        /* statusrutan bort FÖRE rullningen — annars flyttar sidan sig en andra gång */
        $('#skrivstatus').hidden = true;
        $('#skrivstatus').innerHTML = '';
        /* React ritar dokumentet asynkront — mät när höjden verkligen är satt */
        visaFolje();
        setTimeout(() => {
          const d = $('#dokument');
          const r = d.getBoundingClientRect();
          const luft = Math.max(24, (window.innerHeight - r.height) / 2);
          const mal = Math.max(0, r.top + window.scrollY - luft);
          window.rullaTill ? window.rullaTill(mal) : window.scrollTo(0, mal);
        }, 220);
      }
    });
  });

  /* ── Följeslagaren ────────────────────────────────────
     Valde man två saker skrivs de i tur och ordning, aldrig parallellt. Medan
     utkastet ligger uppe är raden bara en upplysning: det andra dokumentet
     föreslås FÖRST när det första är godkänt och ligger i Sparat — då vet man vad
     det bygger på. Sa man «inte nu» ligger det kvar som en väntande rad högst upp
     i planeringen; ingenting försvinner för alltid. */
  const OBEST = { Tavla: 'en tavla', Prov: 'ett prov', Arbetsblad: 'ett arbetsblad', Gruppuppgift: 'en gruppuppgift' };
  let foljdKvar = null, foljdVantar = null;
  function visaFolje() {
    const rad = $('#foljerad');
    if (!rad) return;
    const lagen = window.Lagen ? window.Lagen() : [];
    const v = versioner[nu] || versioner[0];
    foljdKvar = lagen.length > 1 && v && v.typ === lagen[0] ? lagen[1] : null;
    rad.hidden = !foljdKvar;
    if (foljdKvar) $('#foljetext').textContent = `${Best(foljdKvar)} till ${best(v.typ)} väntar — skrivs när ${best(v.typ)} är godkänd och ligger i Sparat`;
  }

  /* Notisen: ett stopp med två vägar, ingen kryssruta i hörnet. */
  const foljeskal = $('#foljeskal');
  const foljeTangent = e => { if (e.key === 'Escape') $('#foljesen').click(); };
  function foljeNotis(o) {
    if (!foljeskal) return;
    foljdVantar = o;
    const f = o.forlaga;
    $('#foljetitel').textContent = `${Best(o.typ)} till ${best(f.typ)}`;
    $('#foljebrod').textContent = `${Best(f.typ)} är godkänd och ligger i Sparat. Du valde att skapa ${OBEST[o.typ] || o.typ.toLowerCase()} också — ${best(o.typ)} skrivs på det du just godkände, med samma exempel och begrepp.`;
    const nar = f.datum ? (window.Kalender ? window.Kalender.ord(f.datum) : f.datum) : 'utan datum';
    const lekt = [f.klass || 'ingen klass', f.kurs || 'ingen kurs', nar].filter(Boolean).join(' · ');
    const antalLekt = valdaNamn().length;
    const underlag = [f.moment ? versal(f.moment) : null, antalLekt ? `${antalLekt} ${antalLekt === 1 ? 'lektion' : 'lektioner'}` : null]
      .filter(Boolean).join(' · ') || 'inget underlag';
    $('#foljeredan').innerHTML = '';
    [['Redan valt', lekt], ['Utgår från', underlag], ['Förlaga', dokNamn(f)], ['Kvar att välja', `Upplägget för ${best(o.typ)}${o.typ === 'Prov' ? ' — provet kan ligga en annan dag' : ''}`]]
      .forEach(([n, v2]) => {
        const rad = document.createElement('div');
        rad.className = 'nrad';
        rad.innerHTML = '<span class="nnamn"></span><span class="nvarde"></span>';
        $('.nnamn', rad).textContent = n;
        $('.nvarde', rad).textContent = v2;
        $('#foljeredan').appendChild(rad);
      });
    $('#foljeja').textContent = `Ja, skriv ${best(o.typ)}`;
    foljeskal.hidden = false;
    /* setTimeout, inte rAF: notisen ska tona in \u00e4ven n\u00e4r fliken \u00e4r i bakgrunden. */
    setTimeout(() => foljeskal.setAttribute('data-pa', ''), 16);
    setTimeout(() => $('#foljeja').focus({ preventScroll: true }), 240);
    document.addEventListener('keydown', foljeTangent);
  }
  function stangNotis() {
    if (!foljeskal || foljeskal.hidden) return;
    foljeskal.removeAttribute('data-pa');
    setTimeout(() => { foljeskal.hidden = true; }, 220);
    document.removeEventListener('keydown', foljeTangent);
  }
  function ritaFoljeVanta() {
    const rad = $('#foljevanta');
    if (!rad) return;
    rad.hidden = !foljdVantar;
    if (!foljdVantar) return;
    $('#foljevantatext').textContent = `${Best(foljdVantar.typ)} till ${best(foljdVantar.forlaga.typ)} väntar — ${best(foljdVantar.forlaga.typ)} ligger i Sparat`;
    $('#foljevantaja').textContent = `Skriv ${best(foljdVantar.typ)}`;
  }
  /* Ja — samma stapel igen, men bara det som verkligen är ett nytt beslut står
     kvar att välja: lektionen, typen och underlaget är redan bestämda. */
  function startaFoljd(o) {
    if (!o) return;
    foljdVantar = null;
    ritaFoljeVanta();
    refDok = JSON.parse(JSON.stringify(o.forlaga));
    $('#refhur').value = `Följer ${best(o.forlaga.typ)}: samma exempel och begrepp, men som ${o.typ.toLowerCase()}.`;
    sattSkrivtyp(o.typ);
    if (window.SattAndraHand) window.SattAndraHand(o.typ, o.forlaga.typ);
    else if (window.SattLage) window.SattLage(o.typ);
    if (o.forlaga.moment) {
      /* Paret handlar om SAMMA sak. Står det något annat i momentfältet — boken
         har hunnit bläddra fram till nästa uppslag när det första godkändes — är
         det förlagans moment som gäller, inte nästa lektions sidor. */
      moment.value = o.forlaga.moment;
      moment.dispatchEvent(new Event('input', { bubbles: true }));
    }
    ritaRef();
    planKoll();
    if (window.PlanSteg) { window.PlanSteg.las(4, false); window.PlanSteg.gaTill(4); }
    window.toast && window.toast(`${Best(o.typ)} bygger på ${best(o.forlaga.typ)} — bara upplägget kvar`);
  }
  $('#foljeja') && $('#foljeja').addEventListener('click', () => { const o = foljdVantar; stangNotis(); startaFoljd(o); });
  $('#foljesen') && $('#foljesen').addEventListener('click', () => {
    stangNotis();
    ritaFoljeVanta();
    window.toast && window.toast(`${Best(foljdVantar ? foljdVantar.typ : 'Dokumentet')} ligger kvar högst upp i planeringen`);
  });
  $('#foljevantaja') && $('#foljevantaja').addEventListener('click', () => startaFoljd(foljdVantar));
  $('#foljevantabort') && $('#foljevantabort').addEventListener('click', () => {
    foljdVantar = null;
    ritaFoljeVanta();
    window.toast && window.toast('Släppt — du kan alltid bygga vidare ur Sparat');
  });

  /* ── Iteration ────────────────────────────────────── */
  /* Provet ärver. Poängfördelning, antal uppgifter och E/C/A-profil är stabila per
     lärare och kurs — att börja från tomt varje gång var det största kvarvarande
     tidsläckaget i Planering. */
  let arvtFran = null;
  function senasteFor(typ, kurs) {
    for (let j = sparat.length - 1; j >= 0; j--) {
      const v = sparat[j];
      if (v.typ === typ && !v.losningsblad && v.kurs === kurs) return v;
    }
    return null;
  }
  function beskrivInst(typ) {
    const s = inst[typ];
    if (typ === 'Prov') {
      const nar = s.nar === 'Annan dag' && s.narDatum
        ? `${window.Kalender ? window.Kalender.ord(s.narDatum) : s.narDatum}${s.narTid ? ' ' + s.narTid : ''}`
        : 'på lektionen';
      return `${s.antal} uppgifter · ${s.nivamix} · ${s.delprov} · ${s.provtid} · ${nar}${s.formelblad ? ' · formelblad' : ''}`;
    }
    if (typ === 'Arbetsblad') return `${s.antal} uppgifter · ${s.niva} · ${s.facit}`;
    if (typ === 'Gruppuppgift') return `${s.grupp} per grupp · ${s.langd} min · ${s.redovisning.toLowerCase()}`;
    return `${s.starttid ? s.starttid + ' · ' : ''}${s.langd} min · ${s.exempel} exempel`;
  }
  /* ── Provtiden uppskattas på pappret (13) ────────────────────
     Förr räknade steg 3 fram en «dimensionerad tid» ur antal uppgifter och
     poängnivå — innan en enda uppgift fanns. Det gick inte att veta: två
     uppgifter på samma poäng kan skilja fem minuter i arbete. Uppskattningen bor
     därför i canvasen, där uppgifterna ligger framme, och görs på begäran.

     Modellen: minuter per poäng efter nivå — praxis och lärarerfarenhet ligger
     på 1,5–3 min per poäng, tyngre ju högre nivå — plus en dryg minut per
     uppgift för läsning och byte, plus åtta minuter för start och avslut. */
  const PER_NIVA = { E: 1.6, C: 2.2, A: 3.1 };
  /* Samma poängfördelning som provet trycker i marginalen. */
  function ecaDel(poang, mix) {
    const p = Math.max(1, poang);
    /* «Bara E» är ett prov där varje poäng ligger på E — inget C, inget A. */
    if (mix === 'Bara E') return [p, 0, 0];
    if (mix === 'E-tyngd') return p <= 2 ? [p, 0, 0] : p <= 4 ? [p - 1, 1, 0] : [p - 2, 2, 0];
    if (mix === 'C/A-tyngd') return p <= 2 ? [0, p, 0] : p <= 4 ? [0, p - 1, 1] : [0, Math.ceil((p - 1) / 2), Math.floor((p - 1) / 2) + 1];
    if (p <= 2) return [p, 0, 0];
    if (p === 3) return [2, 1, 0];
    if (p === 4) return [2, 2, 0];
    if (p === 5) return [1, 2, 2];
    if (p === 6) return [1, 3, 2];
    return [1, 3, 3];
  }
  function uppskatta(v) {
    const mix = (v.inst || {}).nivamix || 'Balanserat';
    let e = 0, c = 0, a = 0;
    (v.uppgifter || []).forEach(u => {
      const [x, y, z] = ecaDel(u.p, mix);
      e += x; c += y; a += z;
    });
    const antal = (v.uppgifter || []).length;
    const rena = e * PER_NIVA.E + c * PER_NIVA.C + a * PER_NIVA.A;
    return { min: Math.max(20, Math.round((rena + antal * 1.1 + 8) / 5) * 5), e, c, a, antal, poang: e + c + a };
  }
  function sattProvtid(m) {
    inst.Prov.provminuter = m;
    inst.Prov.provtid = m + ' min';
    ritaTypval();
    planKoll();
  }
  /* Uppskattningen sitter vid antalet uppgifter i steg 3, inte i canvasen: det är
     där provets storlek bestäms, och innan något är skrivet. Knappen räknar på
     upplägget som står i formuläret och SÄTTER provtiden — klockslagen väljer man
     sedan själv, men längden är bestämd av det man klickade på. */
  function uppskattaNu() {
    if (valt('skrivtyp') !== 'Prov') return;
    const v = nyVersion(null);
    const u = uppskatta(v);
    const forr = Number(inst.Prov.provminuter) || parseInt(inst.Prov.provtid, 10) || 90;
    sattProvtid(u.min);
    const skal = $('#tidsskal');
    if (skal) { skal.hidden = true; skal.textContent = ''; }
    const text = `Provtiden satt till ${u.min} min — ${u.antal} uppgifter · ${u.poang} p · ${u.e}/${u.c}/${u.a} E/C/A.`;
    if (!window.toast) return;
    if (forr !== u.min) window.toast(text, `Ångra (${forr} min)`, () => sattProvtid(forr));
    else window.toast(text);
  }

  function ritaArv() {
    const rad = $('#arvrad');
    if (!rad) return;
    /* bygger man vidare på en förlaga ska ingenting ärvas i smyg — valen är nya */
    if (refDok) { rad.hidden = true; arvtFran = null; return; }
    const typ = valt('skrivtyp'), kurs = $('#p-kurs').value;
    const v = typ === 'Tavla' || !kurs ? null : senasteFor(typ, kurs);
    if (!v) { rad.hidden = true; arvtFran = null; return; }
    if (arvtFran !== v) {
      arvtFran = v;
      Object.assign(inst[typ], JSON.parse(JSON.stringify(v.inst || {})));
      /* Ärvda upplägg bär förra lektionens minuter. Schemat ska ändå få säga sitt
         om längden — annars ärver en 45-minuterslektion ett 60-minutersblock.
         Nycklarna för alla tre måtten måste bort, inte två: står `minSchema`
         kvar på 45 tror ritaTypval() att provtiden redan är läst ur schemat och
         låter det ärvda «120 min» stå — och det är `provtid`, inte
         `provminuter`, som följer med ut på pappret. */
      delete inst[typ].langdSchema;
      delete inst[typ].tidSchema;
      delete inst[typ].minSchema;
      ritaTypval();
    }
    rad.hidden = false;
    const nar = v.datum ? (window.Kalender ? window.Kalender.ord(v.datum) : v.datum) : 'utan datum';
    $('#arvtext').textContent = `Ärvt från ${typ} ${kurs.replace(/^Matematik\s*/, '')} — ${nar} · ${beskrivInst(typ)}`;
  }
  $('#arvaterstall') && $('#arvaterstall').addEventListener('click', () => {
    const typ = valt('skrivtyp');
    Object.assign(inst[typ], JSON.parse(JSON.stringify(STANDARD[typ])));
    arvtFran = null;
    ritaTypval();
    $('#arvrad').hidden = true;
    window.toast && window.toast('Tillbaka till standarduppägget');
  });

  /* ── Bygg vidare på ett sparat dokument ────────────────────────
     Formuläret ärver det som hör till ämnet — typ, moment, klass, kurs och centralt
     innehåll. Datum och tid står tomma, och inställningarna börjar på standard: hur
     provet ska sättas är ett nytt beslut varje gång. Dokumentet följer med som förlaga
     i stället för lektioner, med en rad där läraren säger vad som ska ärvas. */
  const REFCHIPS = [
    'Samma typ av uppgifter, nytt område',
    'Repetera det klassen gjorde sämst på',
    'Undvik att upprepa uppgifter',
    'Bygg på kunskaperna från förlagan',
    'Samma svårighetsprofil'
  ];
  let refDok = null;
  /* Det rättade provet är inte en förlaga: det är ett utfall. Förlagan styr hur
     nästa papper SER UT, resultatet styr vad det HANDLAR OM — därför två platser
     och aldrig samma variabel. */
  let resDok = null;
  function byggVidare(i) {
    const v = sparat[i];
    if (!v) return;
    refDok = JSON.parse(JSON.stringify(v));
    window.SlappAndraHand && window.SlappAndraHand();
    moment.value = v.moment || '';
    if (v.kurs) { $('#p-kurs').value = v.kurs; $('#p-kurs').dispatchEvent(new Event('change', { bubbles: true })); }
    if (v.klass) { $('#p-klass').value = v.klass; $('#p-klass').dispatchEvent(new Event('change', { bubbles: true })); }
    $('#p-datum').value = '';
    $('#p-tid').value = '';
    const dk = $('#pdatumknapp');
    if (dk) { $('.valjtext', dk).textContent = 'Välj datum'; $('#pdatumvalj').removeAttribute('data-satt'); }
    vald.clear();
    (v.gy || []).forEach(g => vald.add(g));
    /* Niv\u00e5n s\u00e4tts efter valet, inte via kurs-h\u00e4ndelsen: dokumentets punkter h\u00f6r till
       DESS niv\u00e5, och de skulle annars filtreras bort mot en niv\u00e5 fr\u00e5n f\u00f6rra planeringen. */
    if (window.Gy) {
      const gy = v.gy || [];
      const bar = id => gy.length && gy.every(g => window.Gy.punkter(id).some(p => p.kort === g));
      const ur = window.Gy.foreslagen(v.kurs);
      /* Kursens egen niv\u00e5 g\u00e4ller n\u00e4r den b\u00e4r punkterna \u2014 annars den niv\u00e5 som g\u00f6r det. */
      nivaId = bar(ur) ? ur : ((window.Gy.lista().find(n => bar(n.id)) || {}).id || ur || nivaId);
    }
    /* inställningarna ärvs INTE — provtid, poängnivåer, upplägg och lösningsblad väljs om */
    const typ = v.typ;
    Object.assign(inst[typ], JSON.parse(JSON.stringify(STANDARD[typ])));
    arvtFran = null;
    valdaLektioner.clear();
    ritaGy();
    ritaTypval();
    ritaKallval();
    ritaRef();
    planKoll();
    (window.rullaTill || (y => window.scrollTo(0, y)))(0);
    /* Typen väljs OM: att bygga vidare säger vad man utgår från, inte vad man gör.
       Därför landar man på steg 2 med förlagan redan på plats. */
    if (window.PlanSteg) { window.PlanSteg.las(2, false); window.PlanSteg.gaTill(2); }
    window.toast && window.toast(`Utgår från ${dokNamn(v)} — välj vad du vill skapa`);
    setTimeout(() => { const f = $('#refhur'); if (f) f.focus({ preventScroll: true }); }, 380);
  }

  /* ── Omprovet ────────────────────────────────────────────────
     Ett omprov är inte ett nytt prov och inte en historikpost — det är samma
     prov en gång till, för dem som missade eller ska göra om. Knappen lämnar
     därför inget färdigt kort bakom sig: den fyller planeringen med allt vi
     redan vet — klassen, kursen, det centrala innehållet, underlaget, provtiden
     och nivåfördelningen — och skickar tillbaka upp i veckan. Bara DAGEN är
     öppen, för det är det enda provet inte kan svara på. */
  let omprovAv = null;
  function omprov(v) {
    if (!v) return;
    omprovAv = { namn: dokNamn(v), typ: v.typ, moment: v.moment, klass: v.klass || '' };
    refDok = JSON.parse(JSON.stringify(v));
    window.SlappAndraHand && window.SlappAndraHand();
    moment.value = v.moment || '';
    if (v.kurs) { $('#p-kurs').value = v.kurs; $('#p-kurs').dispatchEvent(new Event('change', { bubbles: true })); }
    if (v.klass) { $('#p-klass').value = v.klass; $('#p-klass').dispatchEvent(new Event('change', { bubbles: true })); }
    $('#p-datum').value = '';
    $('#p-tid').value = '';
    const dk = $('#pdatumknapp');
    if (dk) { $('.valjtext', dk).textContent = 'Välj datum'; $('#pdatumvalj').removeAttribute('data-satt'); }
    vald.clear();
    (v.gy || []).forEach(g => vald.add(g));
    if (window.Gy) {
      const gy = v.gy || [];
      const bar = id => gy.length && gy.every(g => window.Gy.punkter(id).some(p => p.kort === g));
      const ur = window.Gy.foreslagen(v.kurs);
      nivaId = bar(ur) ? ur : ((window.Gy.lista().find(n => bar(n.id)) || {}).id || ur || nivaId);
    }
    /* Upplägget ÄRVS här, till skillnad från «bygg vidare»: provtiden, antalet
       uppgifter, nivåfördelningen och lösningsbladet var redan avgjorda en gång. */
    Object.assign(inst[v.typ], JSON.parse(JSON.stringify(v.inst || STANDARD[v.typ])));
    /* Samma sak som vid arvet: det ärvda upplägget får inte bära med sig nyckeln
       som säger att längden redan är läst ur schemat. */
    delete inst[v.typ].langdSchema;
    delete inst[v.typ].tidSchema;
    delete inst[v.typ].minSchema;
    arvtFran = null;
    valdaLektioner.clear();
    /* Bara källor som fortfarande finns bland inspelningarna — annars räknar
       kvittot lektioner som inte går att visa. */
    const namn = new Set(lektioner().map(l => l.namn));
    (v.kallor || []).filter(n => namn.has(n)).forEach(n => valdaLektioner.add(n));
    const hur = $('#refhur');
    if (hur) hur.value = 'Omprov: samma centrala innehåll, samma provtid och samma nivåfördelning — nya tal och ny ordning på uppgifterna.';
    if (window.SattLage) window.SattLage(v.typ);
    sattSkrivtyp(v.typ);
    ritaGy();
    ritaTypval();
    ritaKallval();
    ritaRef();
    planKoll();
    window.Utgang && window.Utgang.rita();
    /* Veckan frågar efter dagen. Resten står redan ifyllt när man kommer ner. */
    if (window.Klass && window.Klass.valjOmprov) window.Klass.valjOmprov(v);
    else if (window.PlanSteg) window.PlanSteg.las(4);
  }
  /* Omprovet måste faktiskt skilja sig från originalet — annars ljuger pappret.
     Ordningen kastas om och de fristående talen byts (poäng rörs inte). */
  function markeraOmprov(v) {
    if (!omprovAv) return;
    v.syskonAv = omprovAv.namn;
    v.variant = 'Omprov';
    v.syskontext = `omprov av ${omprovAv.namn}`;
    v.anteckning = 'Omprov — samma skelett, nya tal och ny ordning';
    v.uppgifter = blanda(v.uppgifter || []).map((u, n) => Object.assign({}, u, { t: nyaTal(u.t), nr: n + 1 }));
  }
  function sattSkrivtyp(typ) {
    const knappar = $$('[data-seg="skrivtyp"] button');
    const traff = knappar.find(b => b.textContent === typ);
    if (traff && traff.getAttribute('aria-pressed') !== 'true') traff.click();
  }
  function ritaRef() {
    const ruta = $('#refruta');
    if (!ruta) return;
    ruta.hidden = !refDok;
    if (window.Kallor && window.Kallor.speglaForlaga) window.Kallor.speglaForlaga();
    if (!refDok) return;
    $('#refnamn').textContent = dokNamn(refDok);
    const nar = refDok.datum ? (window.Kalender ? window.Kalender.ord(refDok.datum) : refDok.datum) : 'utan datum';
    const i = refDok.inst || {};
    $('#refmeta').textContent = [refDok.kurs || 'ingen kurs', refDok.klass || 'ingen klass', nar,
      i.antal ? `${i.antal} uppgifter` : null, i.nivamix || i.niva || null].filter(Boolean).join(' · ');
    $('#refminis').textContent = refDok.typ === 'Tavla' ? 'TA' : refDok.typ === 'Prov' ? 'PR' : 'AB';
    $('#refminis').dataset.typ = refDok.typ;
    const chips = $('#refchips');
    chips.innerHTML = '';
    REFCHIPS.forEach(t => {
      const b = document.createElement('button');
      b.className = 'chip';
      b.type = 'button';
      b.textContent = t;
      b.addEventListener('click', () => {
        const f = $('#refhur');
        f.value = f.value.trim() ? f.value.trim().replace(/\.$/, '') + '. ' + t + '.' : t + '.';
        f.focus();
        planKoll();
      });
      chips.appendChild(b);
    });
  }
  $('#reftabort') && $('#reftabort').addEventListener('click', () => {
    refDok = null;
    $('#refhur').value = '';
    ritaRef();
    planKoll();
    window.toast && window.toast('Förlagan borttagen');
  });
  $('#refhur') && $('#refhur').addEventListener('input', planKoll);

  /* Dokumentet ritas asynkront (React) — vänta på att pappret finns innan canvas byter ut det.
     Utan väntan klonades den tomma värden och canvas blev blank. */
  /* Dokumentet är TRAVEN, inte ett av dess blad. Med «facit i bladet» ligger tre
     blad i samma dokument, och det första är ett .gu — plockade granskningen
     första .ark fick läraren facit i canvas och kom aldrig åt uppgifterna. */
  const arkNod = () => $('#arkskal .bladtrav') || $('#arkskal .provark') || $('#arkskal .tavla') || $('#arkskal .ark') || null;
  function omGranska(ark, forsok) {
    if (!window.Granska || !window.Granska.oppen) return;
    const nod = arkNod();
    if (nod) { window.Granska.sattOm(nod, ark); return; }
    if ((forsok || 0) > 30) return;
    requestAnimationFrame(() => omGranska(ark, (forsok || 0) + 1));
  }
  function iterera(text, etikett, elId) {
    if (nu < 0) return;
    const l = (etikett ? etikett + ' ' : '') + text.toLowerCase();
    const v = nyVersion(versioner[nu], x => {
      x.anteckning = etikett ? `${etikett}: ${text}` : text;
      /* Elementet canvas pekade på är det som ska märkas — en uppgift som heter
         «B» har inget nummer att läsa ut ur etiketten. */
      if (elId) x.andrat.push(elId);
      const traff = (etikett || '').match(/uppgift\s*(\d+)/i);
      if (traff) x.andrat.push('uppg' + traff[1]);
      if (/sidhuvud/i.test(etikett || '')) x.andrat.push('rubrik');
      if (/instruktion/i.test(etikett || '')) x.andrat.push('instr');
      const block = (etikett || '').match(/(Ing\u00e5ng|Genomg\u00e5ng|Par-uppgift|\u00c5tersamling|Avslut)/i);
      if (block) x.andrat.push('block' + ['Ingång', 'Genomgång', 'Par-uppgift', 'Återsamling', 'Avslut'].findIndex(b => new RegExp(b, 'i').test(block[1])));
      if (/svårare|hårdare|tuffare/.test(l)) { x.svarighet = 1; x.andrat.push('uppg3', 'uppg5'); }
      if (/lättare|enklare/.test(l)) { x.svarighet = -1; x.andrat.push('uppg3'); }
      if (/nivå|fördjup|extra utmaning/.test(l)) { x.niva = true; }
      if (/fysik/.test(l)) { x.kontext = 'fysik'; x.andrat.push('uppg3', 'block1'); }
      if (/ekonomi|pengar/.test(l)) { x.kontext = 'ekonomi'; x.andrat.push('uppg3', 'block1'); }
      if (/natur|biologi/.test(l)) { x.kontext = 'natur'; x.andrat.push('uppg3', 'block1'); }
      if (/instruktion|regler|räknare/.test(l)) x.andrat.push('instr');
      if (!x.andrat.length) x.andrat.push('uppg1', 'block0');
    });
    versioner = versioner.slice(0, nu + 1).concat([v]);
    visa(versioner.length - 1);
  }
  $('#angra').addEventListener('click', angra);
  $('#gorom').addEventListener('click', gorOm);
  $('#g-angra') && $('#g-angra').addEventListener('click', angra);
  $('#g-gorom') && $('#g-gorom').addEventListener('click', gorOm);
  $('#g-godkann') && $('#g-godkann').addEventListener('click', () => {
    window.Granska && window.Granska.stang();
    $('#godkann').click();
  });
  function satKrymp(litet) {
    const d = $('#dokument'), typ = (versioner[nu] || {}).typ || valt('skrivtyp');
    const namn = best(typ);
    d.toggleAttribute('data-litet', litet);
    $('#dokhint').textContent = litet
      ? `Förminskad vy av ${namn} — fäll ut här, eller öppna canvas för att zooma och kommentera.`
      : `Hela ${namn} visas i rutan. Canvas ger zoom, panorering och kommentarer på element.`;
    const knapp = $('#dokstorlek');
    if (knapp) {
      knapp.textContent = litet ? 'Visa hela' : 'Förminska';
      knapp.setAttribute('aria-expanded', String(!litet));
    }
  }
  /* Förhandsvisningen var en återvändsgränd: 190 px papper och canvas som enda
     väg vidare. Nu fälls den ut där den står. */
  $('#dokstorlek') && $('#dokstorlek').addEventListener('click', () => {
    satKrymp(!$('#dokument').hasAttribute('data-litet'));
  });
  let bildmal = null;
  function valjBild(mal) {
    if (nu < 0) return;
    bildmal = mal || 'rubrik';
    const inp = $('#bildfil');
    inp.value = '';
    inp.click();
  }
  $('#bildfil').addEventListener('change', () => {
    const fil = $('#bildfil').files && $('#bildfil').files[0];
    if (!fil || nu < 0) return;
    const las = new FileReader();
    las.onload = () => {
      const v = versioner[nu];
      v.bilder = v.bilder || {};
      v.bilder[bildmal] = las.result;
      v.andrat = [bildmal];
      visa(nu);
      window.toast && window.toast(`Bilden lades in — ${fil.name}`);
    };
    las.readAsDataURL(fil);
  });
  window.valjBild = valjBild;
  const arkNamn = v => v.typ === 'Prov' ? ['Provet', 'Lösningsförslag'] : v.typ === 'Gruppuppgift' ? ['Gruppuppgiften', 'Facit'] : ['Arbetsbladet', 'Facit'];
  const arkLage = v => ({ tva: harLosning(v), namn: arkNamn(v), vald: visarLosning ? 1 : 0, byt: j => byt(j) });
  function byt(j) {
    visarLosning = j === 1;
    if (nu < 0) return;
    visa(nu, arkLage(versioner[nu]));
  }
  $('#granska').addEventListener('click', () => {
    if (nu < 0) return;
    const nod = arkNod() || $('#arkskal').firstElementChild;
    if (!nod || !window.Granska) return;
    const v = versioner[nu];
    window.Granska.oppna({
      nod,
      titel: `${v.typ} — ${versal(v.moment)}`,
      meta: $('#dokmeta').textContent,
      ark: arkLage(v),
      onAndra: (text, etikett, elId) => iterera(text, etikett, elId),
      onBild: elId => valjBild(elId)
    });
  });
  $$('#arkval button').forEach((b, j) => b.addEventListener('click', () => byt(j)));

  /* ── Sparat ───────────────────────────────────────── */
  function minisida(v) {
    const rader = v.typ === 'Tavla' ? 4 : 6;
    return `<span class="minisida" data-typ="${v.typ}"><span class="msrub"></span><span class="mslinje" style="width:88%"></span><span class="mslinje" style="width:74%"></span>
      ${Array.from({ length: rader }, () => '<span class="msrad"><span class="msnr"></span><span class="mslinje" style="flex:1;margin:0"></span></span><span class="mslinje" style="width:64%"></span>').join('')}</span>`;
  }
  window.Dokument = {
    sparade: () => sparat,
    /* Utgångspunkterna i steg 3 väljer källor åt planeringen — samma tillstånd
       som lektionsväljaren och förlagerutan, bara ett klick i stället för tre. */
    valjLektion(namn) { valdaLektioner.add(namn); ritaKallval(); planKoll(); },
    slappLektion(namn) { valdaLektioner.delete(namn); ritaKallval(); planKoll(); },
    harLektion(namn) { return valdaLektioner.has(namn); },
    sattForlaga(v, hur) {
      refDok = JSON.parse(JSON.stringify(v));
      const f = $('#refhur');
      if (f && hur) f.value = hur;
      ritaRef();
      planKoll();
    },
    slappForlaga() { refDok = null; const f = $('#refhur'); if (f) f.value = ''; ritaRef(); planKoll(); },
    sattResultat(v) { resDok = JSON.parse(JSON.stringify(v)); planKoll(); },
    slappResultat() { resDok = null; planKoll(); },
    resultatet: () => resDok,
    /* ── Biblioteket ────────────────────────────────────
       En tavla, ett arbetsblad eller en gruppuppgift som fungerade ska inte
       skrivas på nytt för nästa klass — den ska läggas på en ny lektion som den
       är. Prov är undantaget: de skrivs från grunden varje gång, annars sprids de
       mellan klasserna.

       Kopian bär `aterbruk` så att båda papperen vet att de hör ihop — och så att
       biblioteket kan räkna hur ofta något faktiskt använts. */
    aterAnvand(v, post) {
      if (!v || v.typ === 'Prov') return null;
      const p = post || (window.PlanKo && window.PlanKo.aktiv && window.PlanKo.aktiv()) || null;
      /* Utan lektion finns ingen plats att lägga pappret på — och ett papper utan
         datum ligger ingenstans i veckan. Då görs ingen kopia alls. */
      if (!p || !p.datum) {
        window.toast && window.toast('Välj en lektion i veckan först — då lägger sig pappret där');
        return null;
      }
      const kopia = JSON.parse(JSON.stringify(v));
      delete kopia.rattat;
      delete kopia.syskonAv;
      delete kopia.syskontext;
      delete kopia.variant;
      kopia.andrat = [];
      kopia.aterbruk = { namn: dokNamn(v), datum: v.datum || '', klass: v.klass || '' };
      kopia.anteckning = `Återanvänd från ${v.klass || 'tidigare'}${v.datum ? ' · ' + v.datum : ''}`;
      kopia.klass = p.klass || kopia.klass;
      kopia.kurs = p.kurs || kopia.kurs;
      kopia.datum = p.datum;
      kopia.tid = p.tid || '';
      v.anvand = (v.anvand || 1) + 1;
      sparat.push(kopia);
      ritaSparat();
      window.Klass && window.Klass.rita();
      window.toast && window.toast(
        `${dokNamn(v)} ligger på ${p.klass || 'lektionen'}s lektion — oförändrad`,
        'Ångra', () => {
          const j = sparat.indexOf(kopia);
          if (j > -1) sparat.splice(j, 1);
          v.anvand = Math.max(1, (v.anvand || 2) - 1);
          ritaSparat();
          window.Klass && window.Klass.rita();
        });
      return kopia;
    },
    /* Med tiden vet man vad som inte fungerade. Det ska gå att kasta — pappret
       OCH dess facit, för ett facit utan sitt blad är skräp. */
    radera(v) {
      const i = sparat.indexOf(v);
      if (i < 0) return;
      const syskon = sparat.filter(x => x !== v && x.losningsblad && x.typ === v.typ && x.moment === v.moment && x.datum === v.datum);
      const bort = [{ i, v }].concat(syskon.map(s => ({ i: sparat.indexOf(s), v: s })));
      bort.sort((a, b) => b.i - a.i).forEach(b => sparat.splice(b.i, 1));
      ritaSparat();
      window.Klass && window.Klass.rita();
      window.toast && window.toast(`${dokNamn(v)} raderad${syskon.length ? ' med sitt facit' : ''}`, 'Ångra', () => {
        bort.slice().sort((a, b) => a.i - b.i).forEach(b => sparat.splice(b.i, 0, b.v));
        ritaSparat();
        window.Klass && window.Klass.rita();
      });
    },
    /* «Börja om» släpper också den väntande följeslagaren — allt rensat betyder allt. */
    slappFoljd() { foljdVantar = null; foljdKvar = null; ritaFoljeVanta(); const r = $('#foljerad'); if (r) r.hidden = true; },
    forlagan: () => refDok,
    /* Omprovet startas härifrån: från kortet, från lektionen i veckan eller från
       förhandsvisningen — samma väg, ett förifyllt formulär och en dag att välja. */
    omprov: v => omprov(v),
    slappOmprov() { omprovAv = null; },
    arOmprov: () => !!omprovAv,
    namn: v => dokNamn(v),
    rita: () => ritaSparat(),
    /* Klassvyn öppnar pappret direkt från lektionen det hör till. */
    visa: i => forhandsvisa(i),
    /* Uppgiftsbanken lägger plockade uppgifter i ett nytt arbetsblad — samma
       dokumentform som allt annat, inget separat förråd. */
    arbetsbladAv(uppgifter, moment, forlaga) {
      const v = fardigt({
        typ: 'Arbetsblad', moment, klass: (forlaga && forlaga.klass) || '', kurs: (forlaga && forlaga.kurs) || '',
        datum: '', inst: { antal: uppgifter.length, niva: 'Blandat', facit: 'Facit i bladet', svar: 'Skrivlinjer', illustration: false },
        anteckning: 'Plockat ur uppgiftsbanken'
      });
      v.uppgifter = uppgifter.map((u, n) => Object.assign({}, u, { nr: n + 1 }));
      sparat.push(v);
      ritaSparat();
      return v;
    }
  };
  function ritaSparat() {
    const nat = $('#sparatnat');
    /* Högen har ingen egen vy längre — materialet ligger på sin lektion i veckan.
       Ritas det ändå någonstans (en äldre sida) fungerar korten som förr. */
    if (!nat) { window.Klass && window.Klass.rita(); return; }
    nat.innerHTML = '';
    sparat.forEach((v, i) => {
      const d = document.createElement('article');
      d.className = 'dokkort';
      const syskon = v.syskonAv ? 0 : sparat.filter(s => s.syskonAv === dokNamn(v)).length;
      d.innerHTML = `${minisida(v)}<div class="dokmeta"><p class="dnamn"></p><p class="dmeta2">${[v.kurs || 'ingen kurs', v.klass || '—', v.datum || 'utan datum'].join(' · ')}</p>${v.syskonAv ? '<p class="doksyskon"></p>' : ''}${syskon ? `<span class="dokvarianter">${syskon} ${syskon === 1 ? 'syskon' : 'syskon'}</span>` : ''}</div><span class="dokbricka"${v.losningsblad ? ' data-losning' : ''}${v.variant ? ' data-variant' : ''}>${v.variant || (v.losningsblad ? (v.typ === 'Prov' ? 'Lösningar' : 'Facit') : v.typ)}</span>`;
      if (v.syskonAv) $('.doksyskon', d).textContent = v.syskontext || ('av ' + v.syskonAv);
      /* Åtgärderna ligger på pappret: en rad som glider in över miniatyrens nederkant
         vid hover. Kortet behåller sin höjd, och rutnätet blir tätare. */
      const syskonknapp = !v.losningsblad ? `<button class="dsl" type="button" data-a="syskon">${v.typ === 'Tavla' ? 'Klass' : 'Omprov'}</button>` : '';
      $('.minisida', d).insertAdjacentHTML('beforeend',
        `<span class="dokslojan"><button class="dsl" type="button" data-a="visa">Visa</button>${syskonknapp}<button class="dsl" type="button" data-a="pdf">PDF</button><button class="dsl" type="button" data-a="radera" data-farlig>Radera</button></span>`);
      $('.dnamn', d).textContent = dokNamn(v);
      /* Provet rättas där provet ligger — inte i en ruta som dyker upp på sidan. */
      if (v.typ === 'Prov' && !v.losningsblad) {
        const r = document.createElement('button');
        r.type = 'button';
        r.className = 'dokratta';
        r.dataset.a = 'ratta';
        r.textContent = v.rattat ? `Rättat · ${Math.round((v.rattat.andel || 0) * 100)} % av poängen` : 'Rätta provet';
        if (v.rattat) r.setAttribute('data-klar', '');
        $('.dokmeta', d).appendChild(r);
      }
      d.addEventListener('click', e => {
        const b = e.target.closest('[data-a]');
        const namn = dokNamn(v);
        if (b && b.dataset.a === 'pdf') { skrivUt(b, namn); return; }
        if (b && b.dataset.a === 'radera') { fragaRadera(d, i, namn); return; }
        if (b && b.dataset.a === 'syskon') { fragaSyskon(d, i); return; }
        if (b && b.dataset.a === 'ratta') { e.stopPropagation(); window.Rattning && window.Rattning.oppna(v); return; }
        if (b && (b.dataset.a === 'ja' || b.dataset.a === 'nej')) return;
        forhandsvisa(i);
      });
      nat.appendChild(d);
    });
    window.Klass && window.Klass.rita();
    const tom = $('#arkiv-tom'), rader = $('#arkivrader');
    if (tom) tom.hidden = sparat.length > 0;
    if (rader) rader.textContent = sparat.length ? `${sparat.length} ${sparat.length === 1 ? 'dokument' : 'dokument'}` : '';
  }

  /* ── Sparat: alla vägar ut ur ett kort ────────────────────────
     Kortet är en förhandsvisning — klick någonstans på det öppnar pappret i full storlek.
     PDF skriver ut på plats (knappen byter läge, inget nytt fönster). Radera frågar i
     kortet, inte i en modal, och går att ångra från toasten. */
  const dokNamn = v => !v || !v.typ ? 'Dokumentet' : v.losningsblad
    ? `${v.typ === 'Prov' ? 'Lösningsförslag' : 'Facit'} — ${versal(v.moment)}`
    : `${v.variant === 'Omprov' ? 'Omprov' : v.typ} — ${versal(v.moment)}`;

  /* Figurerna kompileras efter att pappret ligger i DOM:en. Varm kompilering tar
     4–7 ms, så rutan står streckad i ett ögonblick och fylls sedan — sättningen
     hoppar inte, för rutan har sin höjd redan. */
  function kompileraFigurer(mal, forsok) {
    if (!window.Figur || !mal) return;
    if (mal.querySelector('[data-cetz]:not([data-klar])')) { window.Figur.ritaAlla(mal); return; }
    /* Provet och arbetsbladet ritas av React och finns inte i samma andetag som
       anropet. Vi väntar på rutorna i stället för att gissa en fördröjning. */
    if ((forsok || 0) > 40) return;
    requestAnimationFrame(() => kompileraFigurer(mal, (forsok || 0) + 1));
  }
  function ritaIn(mal, v) {
    if (!mal) return;
    if (window.Blad) { window.Blad.rita(mal, v); return; }
    /* Utan bladen finns ingen form att visa — hellre tomt än en generisk mall. */
    mal.innerHTML = '';
  }

  function skrivUt(b, namn) {
    if (b.dataset.lage) return;
    const text = b.textContent;
    b.dataset.lage = 'skriver';
    b.textContent = 'Skriver …';
    setTimeout(() => {
      b.dataset.lage = 'klar';
      b.textContent = 'Sparad';
      window.toast && window.toast(`${namn} · PDF:en ligger i Hämtat`, 'Öppna', () => window.toast && window.toast('Öppnar PDF:en i din läsare'));
      setTimeout(() => { b.removeAttribute('data-lage'); b.textContent = text; }, 1700);
    }, 850);
  }

  /* ── Syskondokument (10 + 17) ────────────────────────────────
     En variant är varken en historikpost eller ett nytt prov: den ligger direkt
     efter sitt original, bunden med en hårlinje, med svart bricka och namnet på
     originalet under. Samma form bär omprovet och parallellklassens tavla —
     tre användningar av ett mönster. */
  const KLASSER = ['9A', '9B', '9C'];
  /* Varianten måste faktiskt skilja sig — annars ljuger kortet. Ordningen kastas
     om och de fristående talen i uppgiftstexten byts (poängangivelser rörs inte). */
  const nyaTal = t => String(t).replace(/(?:^|[^\d(/])(\d{1,3})(?![\d)/])/g, (hel, n) => hel.replace(n, String(((+n * 3 + 5) % 90) + 2)));
  function blanda(lista) {
    const a = lista.slice();
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }
  function skapaSyskon(i, sort) {
    const orig = sparat[i];
    const v = JSON.parse(JSON.stringify(orig));
    v.syskonAv = dokNamn(orig);
    v.variant = sort.bricka;
    v.syskontext = sort.text;
    if (sort.klass) v.klass = sort.klass;
    if (sort.datum) v.datum = sort.datum;
    v.anteckning = sort.text;
    v.uppgifter = blanda(v.uppgifter || []).map((u, n) => Object.assign({}, u, { t: nyaTal(u.t), nr: n + 1 }));
    v.andrat = [];
    sparat.splice(i + 1, 0, v);
    ritaSparat();
    window.toast && window.toast(`${sort.bricka} skapad — ${sort.text}`, 'Ångra', () => {
      sparat.splice(i + 1, 1);
      ritaSparat();
    });
  }
  function nastaBokstav(i) {
    const orig = sparat[i];
    const tagna = sparat.filter(s => s.syskonAv === dokNamn(orig) && /^Variant/.test(s.variant || '')).length;
    return 'Variant ' + 'BCDE'[Math.min(3, tagna)];
  }
  function fragaSyskon(kort, i) {
    if ($('.dokfraga', kort)) return;
    const v = sparat[i];
    const tavla = v.typ === 'Tavla';
    const annanKlass = KLASSER.find(k => k !== v.klass) || '9B';
    const f = document.createElement('div');
    f.className = 'dokfraga';
    f.innerHTML = tavla
      ? `<p class="dfrubrik">Skriv om för en annan klass?</p><p class="dfnamn">Skelettet är samma. Minneskontexten byts till ${annanKlass}:s egna lektioner.</p><div class="dfknappar"><button class="primar" type="button" data-a="klass">För ${annanKlass}</button><button class="lank" type="button" data-a="nej">Avbryt</button></div>`
      : `<p class="dfrubrik">Omprov på samma sak?</p><p class="dfnamn">Klassen, det centrala innehållet, underlaget och provtiden följer med — nya tal och ny ordning. Du väljer bara dagen.</p><div class="dfknappar"><button class="primar" type="button" data-a="omprov">Välj dag för omprovet</button><button class="lank" type="button" data-a="nej">Avbryt</button></div>`;
    kort.appendChild(f);
    requestAnimationFrame(() => f.setAttribute('data-pa', ''));
    const stang = () => { f.removeAttribute('data-pa'); setTimeout(() => f.remove(), 180); };
    f.addEventListener('click', ev => {
      const b = ev.target.closest('[data-a]');
      if (!b) return;
      ev.stopPropagation();
      if (b.dataset.a === 'nej') return stang();
      stang();
      if (b.dataset.a === 'omprov') omprov(v);
      if (b.dataset.a === 'klass') skapaSyskon(i, { bricka: annanKlass, text: `samma tavla för ${annanKlass} · minneskontexten bytt`, klass: annanKlass });
    });
  }

  function fragaRadera(kort, i, namn) {
    if ($('.dokfraga', kort)) return;
    const f = document.createElement('div');
    f.className = 'dokfraga';
    f.innerHTML = '<p class="dfrubrik">Radera dokumentet?</p><p class="dfnamn"></p><div class="dfknappar"><button class="primar farlig" type="button" data-a="ja">Radera</button><button class="lank" type="button" data-a="nej">Behåll</button></div>';
    $('.dfnamn', f).textContent = namn;
    kort.appendChild(f);
    requestAnimationFrame(() => f.setAttribute('data-pa', ''));
    $('[data-a="ja"]', f).addEventListener('click', ev => { ev.stopPropagation(); taBort(i, namn); });
    $('[data-a="nej"]', f).addEventListener('click', ev => {
      ev.stopPropagation();
      f.removeAttribute('data-pa');
      setTimeout(() => f.remove(), 180);
    });
  }
  function taBort(i, namn) {
    const bort = sparat.splice(i, 1)[0];
    ritaSparat();
    window.toast && window.toast(`${namn} raderades`, 'Ångra', () => {
      sparat.splice(i, 0, bort);
      ritaSparat();
      const kort = $$('#sparatnat .dokkort')[i];
      if (kort) { kort.setAttribute('data-traff', ''); setTimeout(() => kort.removeAttribute('data-traff'), 2400); }
      window.toast && window.toast(`${namn} är tillbaka`);
    });
  }

  const fhskal = $('#forhandsskal');
  let fhIndex = -1;
  const fhTangent = e => { if (e.key === 'Escape') fhStang(); };
  function forhandsvisa(i) {
    const v = sparat[i];
    if (!v || !fhskal) return;
    fhIndex = i;
    $('#fh-etikett').textContent = v.losningsblad ? 'Förhandsvisning · lösningsblad' : 'Förhandsvisning';
    $('#fh-titel').textContent = dokNamn(v);
    $('#fh-meta').textContent = [v.kurs || 'ingen kurs', v.klass || 'ingen klass', (v.datum ? (window.Kalender && window.Kalender.ord ? window.Kalender.ord(v.datum) : v.datum) : 'utan datum'),
      typeof beskriv === 'function' ? beskriv(v) : ''].filter(Boolean).join(' · ');
    ritaIn($('#fh-ark'), v);
    fhskal.hidden = false;
    requestAnimationFrame(() => fhskal.setAttribute('data-pa', ''));
    document.addEventListener('keydown', fhTangent);
  }
  function fhStang() {
    if (!fhskal || fhskal.hidden) return;
    fhskal.removeAttribute('data-pa');
    setTimeout(() => { fhskal.hidden = true; $('#fh-ark').innerHTML = ''; }, 220);
    document.removeEventListener('keydown', fhTangent);
  }
  if (fhskal) {
    $('#fh-stang').addEventListener('click', fhStang);
    fhskal.addEventListener('pointerdown', e => { if (e.target === fhskal) fhStang(); });
    $('#fh-pdf').addEventListener('click', e => skrivUt(e.currentTarget, dokNamn(sparat[fhIndex])));
    $('#fh-oppna').addEventListener('click', () => {
      if (fhIndex < 0 || !sparat[fhIndex]) return;
      const i = fhIndex;
      fhStang();
      byggVidare(i);
    });
  }
  $('#godkann').addEventListener('click', () => {
    if (nu < 0) return;
    const v = versioner[nu];
    sparat.push(JSON.parse(JSON.stringify(v)));
    /* Ett godkänt dokument hör hemma i tiden. Provet blir en post med bläck-
       kontur och en tryckskyldighet några dagar innan; tavlan bara en post som
       släcker «Tavla saknas» i veckan. Ingenting läggs in innan godkännandet. */
    if (window.Kalender && v.datum) {
      const namn = `${v.variant === 'Omprov' ? 'Omprov' : v.typ} — ${versal(v.moment)}`;
      const finns = window.Kalender.poster.some(p => p.datum === v.datum && p.titel === namn);
      if (!finns) window.Kalender.lagg({
        datum: v.datum,
        tid: v.tid || (v.typ === 'Prov' ? (v.inst && v.inst.provtid ? v.inst.provtid : '') : ''),
        titel: namn, klass: v.klass || '', slag: v.typ.toLowerCase(),
        antal: v.typ === 'Prov' ? 24 : 1
      });
      window.Klass && window.Klass.rita && window.Klass.rita();
    }
    const i = v.inst || {};
    if ((v.typ === 'Prov' && i.losningar) || (v.typ === 'Arbetsblad' && i.facit === 'Separat facit')) {
      const l = JSON.parse(JSON.stringify(v));
      l.losningsblad = true;
      sparat.push(l);
    }
    ritaSparat();
    omprovAv = null;
    /* Förlagan hör till dokumentet som just skrevs. Står den kvar bygger nästa
       dokument — ofta i en annan klass — vidare på ett papper läraren aldrig
       pekade ut, och «Därför ärvt»-raden tystnar på köpet. */
    if (refDok) { refDok = null; const rh = $('#refhur'); if (rh) rh.value = ''; ritaRef(); }
    /* Utfallet och viktningen hör till det papper som just skrevs, inte till
       nästa — de släpps i samma gest som förlagan. */
    if (resDok) { resDok = null; window.Kallor && window.Kallor.speglaResultat && window.Kallor.speglaResultat(); }
    const fk = $('#fokus');
    if (fk) fk.value = '';
    /* Klassprofilen lär sig av valet: typen, boken, sidorna och takten. */
    window.Profil && window.Profil.lar(v);
    $('#dokument').hidden = true;
    versioner = []; nu = -1;
    visarLosning = false;
    moment.value = '';
    planKoll();
    /* Stapelns rader läser momentet — töms det måste de skrivas om, annars står
       «Utgår från 5.1 …» kvar bredvid «Beskriv momentet ovan». */
    window.PlanSteg && window.PlanSteg.rita && window.PlanSteg.rita();
    const extra = (v.typ === 'Prov' && i.losningar) || (v.typ === 'Arbetsblad' && i.facit === 'Separat facit');
    /* Godkännandet är grinden: först här föreslås nästa i paret, och då med det
       sparade dokumentet som förlaga. */
    const par = foljdKvar ? { typ: foljdKvar, forlaga: JSON.parse(JSON.stringify(v)) } : null;
    foljdKvar = null;
    $('#foljerad').hidden = true;
    if (par) {
      window.PlanKo && window.PlanKo.vantar && window.PlanKo.vantar(par.typ);
      setTimeout(() => foljeNotis(par), 420);
      return;
    }
    /* Kön går vidare av GODKÄNNANDET, inte av utkastet. Först när pappret ligger
       i Sparat är lektionen färdigplanerad — då är nu nästa klass förvald och
       sidan går själv upp till steg 1. Är det den sista säger remsan att allt är
       planerat. */
    const ko = window.PlanKo;
    if (ko && ko.aktiv()) {
      if (ko.harFler && ko.harFler()) { setTimeout(() => ko.nasta(), 240); return; }
      ko.klar();
    }
    window.toast && window.toast(extra ? 'Sparad som två PDF:er — dokument och lösningsförslag' : 'Sparad som PDF i Sparat', 'Visa', () => (window.rullaTill || ((y) => window.scrollTo(0, y)))(document.body.scrollHeight));
  });

  /* ── Fråga det sparade OCH det inspelade ─────────────
     En fråga till hela arbetet: pappren i Sparat, veckan i schemat, och det som
     faktiskt sades på lektionerna. Citat ur ett transkript blir blåmarkerade
     precis som dokumentnamnen — men de spelar upp stället i stället för att
     öppna ett papper. */
  const inspLista = () => (window.Inspelningar && window.Inspelningar.lista) ? window.Inspelningar.lista() : [];
  let inspKallor = [];
  const transkriptrad = i => (window.transkript || [])[Math.min(i, Math.max(0, (window.transkript || []).length - 1))] || ['00:00', ''];
  function inspMark(p, i, text) {
    const r = transkriptrad(i);
    const n = inspKallor.push({ kort: p.el, tid: r[0], rad: r[1], namn: p.namn, klass: p.klass, kurs: p.kurs }) - 1;
    return `[[insp:${n}|${(text || r[1]).slice(0, 46).trim()}]]`;
  }
  const inspCit = (p, i) => inspMark(p, i);
  const inspLank = (p, i) => inspMark(p, i, p.namn);

  $('#arkivknapp').addEventListener('click', () => {
    /* Inspelningsläget filtrerar medan man skriver — det har inget svar att ge. */
    if (valt('arkivläge') === 'Inspelningar') return;
    const q = $('#arkivfalt').value.trim();
    if (!q) return $('#arkivfalt').focus();
    /* Sökningen ser bara det som ligger i Sparat — prov, arbetsblad, tavlor
       och deras lösningsblad. Inget utkast uppe i planeringen. */
    const namnetPa = v => (v.losningsblad ? (v.typ === 'Prov' ? 'Lösningsförslag' : 'Facit') : v.typ) + ' — ' + versal(v.moment);
    if (valt('arkivläge') === 'Sök ord') {
      const l = q.toLowerCase();
      const traff = sparat.filter(v => (namnetPa(v) + ' ' + v.kurs + ' ' + v.klass + ' ' + (v.gy || []).join(' ')).toLowerCase().includes(l));
      /* Sökningen går över BÅDE pappren och inspelningarna — det är ett arkiv. */
      const insp = inspLista();
      const itraff = insp.filter(p => `${p.namn} ${p.klass} ${p.kurs}`.toLowerCase().includes(l));
      $('#arkivsvar').hidden = false;
      $('#arkivsvar').innerHTML = `<div class="fsvar" data-lage="klar"><p class="ftext">${traff.length} av ${sparat.length} dokument${insp.length ? ` och ${itraff.length} av ${insp.length} inspelningar` : ''} innehåller ”${q.replace(/</g, '&lt;')}”.</p></div>`;
      return;
    }
    const ord = q.toLowerCase().split(/[^a-zåäöé0-9]+/).filter(w => w.length > 3);
    const namnFor = namnetPa;
    const poang = v => {
      const text = (namnFor(v) + ' ' + v.kurs + ' ' + v.klass + ' ' + (v.gy || []).join(' ')).toLowerCase();
      return ord.reduce((a, w) => a + (text.includes(w) ? 1 : 0), 0);
    };
    /* dokumentnamn skrivs som citat — de blir blåmarkerade i svaret */
    const lank = v => `[[dok:${sparat.indexOf(v)}|${namnFor(v)}]]`;
    const rankad = sparat.map(v => ({ v, p: poang(v) })).sort((a, b) => b.p - a.p);
    const bast = rankad[0] && rankad[0].p > 0 ? rankad[0].v : null;
    const traffar = rankad.filter(r => r.p > 0).slice(0, 3).map(r => r.v);
    const datumOrd = v => v.datum ? new Date(v.datum + 'T12:00:00').toLocaleDateString('sv-SE', { day: 'numeric', month: 'long' }) : 'utan datum';
    const beskriv = v => {
      const i = v.inst || {};
      if (v.typ === 'Prov') return `${v.uppgifter.length} uppgifter, ${i.provtid || '90 min'}, ${i.delprov || 'Del A + Del B'}`;
      if (v.typ === 'Arbetsblad') return `${v.uppgifter.length} uppgifter, ${i.niva || 'Blandat'}, ${(i.facit || 'Facit i bladet').toLowerCase()}`;
      return `${i.langd || 45} minuter, ${i.exempel || 2} exempel på tavlan`;
    };
    /* Handlar frågan om tid — prov, nästa vecka, kapitlet — svarar klassvyn med
       schemat och boken invägda. Annars är det högen som söks igenom. */
    const schemasvar = window.Klass && window.Klass.fragan ? window.Klass.fragan(q) : null;
    /* Handlar den om vad som SADES går den till transkripten i stället. */
    const insp = inspLista();
    inspKallor = [];
    const ipoang = p => {
      const text = `${p.namn} ${p.klass} ${p.kurs}`.toLowerCase();
      return ord.reduce((a, w) => a + (text.includes(w) ? 1 : 0), 0);
    };
    const irank = insp.map(p => ({ p, n: ipoang(p) })).sort((a, b) => b.n - a.n);
    const ibast = irank[0] && irank[0].n > 0 ? irank[0].p : null;
    const omTalet = /\bsa\b|sade|sades|säger|gick igenom|hann|hanns|lektion|inspelning|transkript|nämnde|frågade|elev|förklara/i.test(q);
    const inspSvar = (ibast && (omTalet || !bast)) ? {
      omfang: `${insp.length} ${insp.length === 1 ? 'inspelning' : 'inspelningar'} · ${sparat.length} dokument`,
      antal: Math.max(1, insp.length),
      svar: `Det togs upp i ${inspLank(ibast, 0)} — ${inspCit(ibast, 1)} — och återkom senare: ${inspCit(irank[1] && irank[1].n ? irank[1].p : ibast, 2)}. Svaret bygger på det som faktiskt sades, inte på rubrikerna.${bast ? ` Bland pappren ligger ${lank(bast)} närmast.` : ''}`,
      plan: [
        { namn: 'Söker i transkripten', detalj: insp.length + (insp.length === 1 ? ' inspelning' : ' inspelningar') },
        { namn: 'Väljer ut relevanta avsnitt', detalj: '2 avsnitt' },
        { namn: 'Läser avsnitten i sin helhet', detalj: '00:42–28:05' },
        { namn: 'Skriver svar med citat', detalj: '' }
      ],
      kallor: []
    } : null;
    window.Fraga.kor($('#arkivsvar'), Object.assign({
      fraga: q,
      omfang: `${sparat.length} sparade dokument`,
      antal: Math.max(1, sparat.length),
      svar: bast
        ? `Närmast ligger ${lank(bast)} för ${bast.kurs || 'ingen kurs'} ${bast.klass ? '· ' + bast.klass + ' ' : ''}— sparat ${datumOrd(bast)}, ${beskriv(bast)}.${bast.gy && bast.gy.length ? ` Det täcker ${bast.gy.join(' och ')} ur Gy25.` : ''}${(() => { const los = sparat.find(x => x.losningsblad && x.moment === bast.moment); return los ? ` ${lank(los)} ligger som eget dokument.` : ''; })()}${traffar.length > 1 ? ` Även ${traffar.filter(v => v !== bast).map(lank).join(' och ')} nämner det.` : ''}`
        : sparat.length
          ? `Inget sparat dokument nämner det. Du har ${sparat.length} dokument: ${sparat.slice(0, 3).map(lank).join(', ')}${sparat.length > 3 ? ' med flera' : ''}.`
          : 'Det finns inget sparat än. Skriv en tavla, ett prov eller ett arbetsblad ovan — det du godkänner samlas här och blir sökbart.',
      plan: [
        { namn: 'Läser rubriker och centralt innehåll', detalj: sparat.length + ' dokument' },
        { namn: 'Rangordnar träffar', detalj: traffar.length + ' relevanta' },
        { namn: 'Skriver svar med källor', detalj: '' }
      ],
      kallor: []
    }, inspSvar || {}, schemasvar || {}));
  });
  $('#arkivfalt').addEventListener('keydown', e => { if (e.key === 'Enter') $('#arkivknapp').click(); });

  /* ── Blåmarkerade dokument i svaret ────────────────
     Samma beteende som citaten i lektionschatten: hovra för en snabbtitt,
     klicka för att landa på kortet i Sparat. */
  const arkivsvar = $('#arkivsvar'), arkivpop = $('#arkivpop');
  const dokFor = m => sparat[Number(String(m.dataset.t || '').split(':')[1])];
  const inspFor = m => /^insp:/.test(String(m.dataset.t || '')) ? inspKallor[Number(String(m.dataset.t).split(':')[1])] : null;
  function stangArkivpop() { arkivpop.hidden = true; arkivpop.innerHTML = ''; }
  function visaArkivpop(m, peka) {
    const ins = inspFor(m);
    if (ins) return visaInsppop(m, peka, ins);
    const v = dokFor(m);
    if (!v) return;
    const i = v.inst || {};
    const rad = v.typ === 'Prov'
      ? `${v.uppgifter.length} uppgifter · ${i.provtid || '90 min'} · ${i.delprov || 'Del A + Del B'}${i.formelblad && !v.losningsblad ? ' · formelblad som bilaga' : ''}${v.losningsblad ? ' · lösningsförslag' : ''}`
      : v.typ === 'Arbetsblad'
        ? `${v.uppgifter.length} uppgifter · ${i.niva || 'Blandat'}${v.losningsblad ? ' · facit' : ''}`
        : `${i.langd || 45} minuter · ${i.exempel || 2} exempel på tavlan`;
    arkivpop.dataset.sak = '';
    arkivpop.innerHTML = '<p class="kallrad"></p><div class="kallmeta"><span class="kalltid"></span><span class="kallnamn"></span><span class="kallgor">Visa i Sparat</span></div>';
    $('.kallrad', arkivpop).textContent = rad;
    $('.kalltid', arkivpop).textContent = datumText(v);
    $('.kallnamn', arkivpop).textContent = [v.kurs || 'ingen kurs', v.klass || 'ingen klass'].join(' · ');
    arkivpop.hidden = false;
    const rutor = [...m.getClientRects()];
    const r = (peka && rutor.find(x => peka.y >= x.top - 2 && peka.y <= x.bottom + 2)) || rutor[0] || m.getBoundingClientRect();
    const k = (arkivpop.offsetParent || arkivsvar).getBoundingClientRect();
    const bredd = Math.min(340, k.width - 24);
    arkivpop.style.width = bredd + 'px';
    arkivpop.style.left = Math.round(Math.min(Math.max(12, r.left - k.left + r.width / 2 - bredd / 2), Math.max(12, k.width - bredd - 12))) + 'px';
    const over = r.top - k.top - arkivpop.offsetHeight - 10;
    arkivpop.style.top = Math.round(over > 8 ? over : r.bottom - k.top + 10) + 'px';
  }
  /* Citat ur ett transkript: raden som sades, tiden, lektionen — och «spela upp»,
     för det är vad klicket gör. */
  function visaInsppop(m, peka, ins) {
    arkivpop.dataset.sak = '';
    arkivpop.innerHTML = '<p class="kallrad"></p><div class="kallmeta"><span class="kalltid"></span><span class="kallnamn"></span><span class="kallgor">▶ Spela upp</span></div>';
    $('.kallrad', arkivpop).textContent = '”' + ins.rad + '”';
    $('.kalltid', arkivpop).textContent = ins.tid;
    $('.kallnamn', arkivpop).textContent = [ins.namn, ins.klass].filter(Boolean).join(' · ');
    arkivpop.hidden = false;
    const rutor = [...m.getClientRects()];
    const r = (peka && rutor.find(x => peka.y >= x.top - 2 && peka.y <= x.bottom + 2)) || rutor[0] || m.getBoundingClientRect();
    const k = (arkivpop.offsetParent || arkivsvar).getBoundingClientRect();
    const bredd = Math.min(340, k.width - 24);
    arkivpop.style.width = bredd + 'px';
    arkivpop.style.left = Math.round(Math.min(Math.max(12, r.left - k.left + r.width / 2 - bredd / 2), Math.max(12, k.width - bredd - 12))) + 'px';
    const over = r.top - k.top - arkivpop.offsetHeight - 10;
    arkivpop.style.top = Math.round(over > 8 ? over : r.bottom - k.top + 10) + 'px';
  }
  let arkivpopTimer = null;
  arkivsvar.addEventListener('pointerover', e => {
    const m = e.target.closest('.kallmark');
    if (!m) return;
    clearTimeout(arkivpopTimer);
    visaArkivpop(m, { x: e.clientX, y: e.clientY });
  });
  arkivsvar.addEventListener('pointerout', e => {
    if (!e.target.closest('.kallmark')) return;
    clearTimeout(arkivpopTimer);
    arkivpopTimer = setTimeout(stangArkivpop, 90);
  });
  arkivsvar.addEventListener('focusin', e => { const m = e.target.closest('.kallmark'); if (m) visaArkivpop(m); });
  arkivsvar.addEventListener('focusout', e => { if (e.target.closest('.kallmark')) stangArkivpop(); });
  arkivsvar.addEventListener('keydown', e => {
    const m = e.target.closest('.kallmark');
    if (m && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); m.click(); }
  });
  arkivsvar.addEventListener('click', e => {
    const m = e.target.closest('.kallmark');
    if (!m) return;
    stangArkivpop();
    /* Ett citat ur en lektion spelar upp stället; ett dokument öppnas. */
    const ins = inspFor(m);
    if (ins) return window.Lektion && window.Lektion.spelaUpp && window.Lektion.spelaUpp(ins.kort, ins.tid);
    const i = sparat.indexOf(dokFor(m));
    if (i > -1) forhandsvisa(i);
  });

  /* ── Från en lektion in i planeringen ───────────────
     Lektionen man kom ifrån är UNDERLAGET (steg 3), inte svaret på steg 1.
     Därför börjar stapeln om på «Vilken lektion?» — det som ska planeras väljs
     ur veckan, precis som annars — medan källan redan ligger vald längre ner. */
  window.planeraFran = (l, typ) => {
    const flik = $$('.flik').find(f => f.textContent === 'Planering');
    if (flik) flik.click();
    const seg = $('[data-seg="skrivtyp"]');
    const mal = [...seg.querySelectorAll('button')].find(b => b.textContent === (typ || 'Tavla'));
    if (mal) mal.click();
    moment.value = l.namn;
    if (l.tagg) {
      const kurs = (GY['Matematik 3c'] && l.tagg.includes('3c')) ? 'Matematik 3c' : l.tagg.includes('Matematik 4') ? 'Matematik 4' : '';
      const klass = (l.tagg.match(/\b9[AB]\b/) || [''])[0];
      if (kurs) { $('#p-kurs').value = kurs; $('#p-kurs').dispatchEvent(new Event('change', { bubbles: true })); }
      if (klass) { $('#p-klass').value = klass; $('#p-klass').dispatchEvent(new Event('change', { bubbles: true })); }
    }
    valdaLektioner.add(l.namn);
    ritaKallval();
    window.Utgang && window.Utgang.rita();
    planKoll();
    window.PlanSteg && window.PlanSteg.omstart();
    const not = $('#plankallnot');
    if (not) {
      not.hidden = false;
      not.innerHTML = 'Utgår från <b></b> — välj lektionen i veckan högst upp.';
      $('b', not).textContent = `”${l.namn}”`;
    }
    const grid = $('#schemagrid');
    if (grid) {
      grid.setAttribute('data-peka', '');
      setTimeout(() => grid.removeAttribute('data-peka'), 2600);
    }
    window.toast && window.toast(`”${l.namn}” ligger som underlag — välj lektionen du planerar`);
  };

  /* några tidigare dokument så att sökningen och frågan har något att arbeta med */
  function fardigt(spec) {
    const typ = spec.typ || 'Prov';
    const v = Object.assign({
      typ, moment: '', klass: '', kurs: '', datum: '', tid: '', gy: [], kalla: false, kallor: [],
      inst: JSON.parse(JSON.stringify(inst[typ])), bilder: {}, kontext: 'start', niva: false,
      svarighet: 0, andrat: [], anteckning: 'Sparat tidigare'
    }, spec);
    v.uppgifter = uppgifter(v);
    return v;
  }
  const provMaj = fardigt({
    typ: 'Prov', moment: 'deriveringsregler', klass: '9A', kurs: 'Matematik 3c', datum: '2026-05-14',
    gy: ['Deriveringsregler', 'Extremvärdesproblem'], kalla: true, kallor: ['Deriveringsregler', 'Produktregeln'],
    inst: { provtid: '120 min', antal: 8, nivamix: 'Balanserat', delprov: 'Del A + Del B', losningar: true, formelblad: true }
  });
  /* Majprovet är rättat: klassens poäng per uppgift ligger på pappret, och därmed
     går det att utgå från utfallet när nästa tavla eller gruppuppgift skrivs. */
  provMaj.rattat = {
    elever: 22, andel: .68, varden: {},
    svaga: [
      { kod: '5b', formaga: 'Kedjeregeln i flera steg', text: 'Derivera f(x) = (3x² − 1)⁴', andel: .34 },
      { kod: '7', formaga: 'Extremvärdesproblem', text: 'Bestäm största värdet för arean', andel: .41 },
      { kod: '4a', formaga: 'Grafisk tolkning', text: 'Skissa derivatans graf ur f', andel: .52 }
    ]
  };
  sparat = [
    provMaj,
    Object.assign(JSON.parse(JSON.stringify(provMaj)), { losningsblad: true }),
    fardigt({
      typ: 'Arbetsblad', moment: 'primitiva funktioner', klass: '9A', kurs: 'Matematik 3c', datum: '2026-06-02',
      gy: ['Primitiva funktioner'], inst: { antal: 6, niva: 'C-nivå', facit: 'Facit i bladet', svar: 'Skrivlinjer', illustration: true }
    }),
    /* Papperen som hör till den transkriberade lektionen 3 juni. De följer med av
       sig själv när man utgår från «förra lektionen» — se lektionsmaterial.js. */
    fardigt({
      typ: 'Gruppuppgift', moment: 'derivatans definition', klass: '9A', kurs: 'Matematik 3c', datum: '2026-06-03', tid: '08:15–09:00',
      gy: ['Derivatans definition'], inst: { grupp: 3, langd: 45, redovisning: 'Muntligt' }
    }),
    fardigt({
      typ: 'Arbetsblad', moment: 'sekant och tangent', klass: '9A', kurs: 'Matematik 3c', datum: '2026-06-03', tid: '08:15–09:00',
      gy: ['Derivatans definition'], inst: { antal: 6, niva: 'Blandat', facit: 'Facit i bladet', svar: 'Skrivlinjer', illustration: true }
    }),
    fardigt({
      typ: 'Arbetsblad', moment: 'komplexa tal', klass: '9B', kurs: 'Matematik 4', datum: '2026-06-18',
      gy: ['Komplexa tal'], inst: { antal: 8, niva: 'Blandat', facit: 'Separat facit', svar: 'Rutnät', illustration: false }
    }),
    fardigt({
      typ: 'Tavla', moment: 'integraler och areor', klass: '9A', kurs: 'Matematik 3c', datum: '2026-06-20',
      gy: ['Integraler och areor'], kalla: true, kallor: ['Integraler — introduktion'],
      inst: { langd: 60, exempel: 3 }
    }),
    /* Terminens första vecka har redan material på några lektioner — klassvyn
       ska visa både det som är gjort och luckorna. */
    fardigt({
      typ: 'Tavla', moment: 'derivatans definition', klass: '9A', kurs: 'Matematik 3c', datum: '2026-08-17', tid: '08:15–09:00',
      gy: ['Derivatans definition'], kalla: true, kallor: ['Från sekant till tangent'], inst: { langd: 45, exempel: 2 }
    }),
    fardigt({
      typ: 'Gruppuppgift', moment: 'derivatans definition', klass: '9A', kurs: 'Matematik 3c', datum: '2026-08-17', tid: '08:15–09:00',
      gy: ['Derivatans definition'], inst: { grupp: 3, langd: 60, redovisning: 'Muntligt' }
    }),
    fardigt({
      typ: 'Tavla', moment: 'komplexa tal i polär form', klass: '9B', kurs: 'Matematik 4', datum: '2026-08-18', tid: '09:15–10:00',
      gy: ['Komplexa tal'], inst: { langd: 45, exempel: 3 }
    }),
    fardigt({
      typ: 'Arbetsblad', moment: 'deriveringsregler', klass: '9A', kurs: 'Matematik 3c', datum: '2026-08-19', tid: '08:15–09:00',
      gy: ['Deriveringsregler'], inst: { antal: 6, niva: 'Blandat', facit: 'Facit i bladet', svar: 'Skrivlinjer', illustration: false }
    })
  ];

  ritaGy();
  ritaTypval();
  ritaKallval();
  planKoll();
  ritaSparat();
})();
