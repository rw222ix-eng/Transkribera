/* ══════════ INSPELNINGARNA PÅ SIN LEKTION ══════════
   En inspelning är inget arkivobjekt — den är vad som HÄNDE på en lektion. Den
   hör därför hemma på lektionen i schemat, bredvid tavlan och provet, inte i en
   egen hög man går till.

   Två delar:
   1 · Härledningen. Filen bär datum och klockslag i sin metadata; klass och kurs
       följer av schemat den dagen. Saknar en inspelning klass eller kurs fyller
       vi i den ur schemat — och SÄGER att vi gjort det, aldrig tyst.
   2 · Uppslaget. window.Inspelningar.forLektion(datum, schemarad) ger de kort
       som hör till lektionen, så klassvyn kan hänga dem på lektionskortet.
       Kortet som skickas vidare är samma DOM-kort som listan använder, för
       lektionsfönstret läser sin lektion ur det. */
window.Inspelningar = (() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const FARG = { 'Matematik 3c': 'sky', 'Matematik 4': 'sage' };
  const kort = () => $$('#inspelningar .kort');
  const start = t => String(t || '').split('–')[0].trim();

  const post = k => ({
    el: k,
    namn: ($('.namn', k) || {}).textContent ? $('.namn', k).textContent.trim() : '',
    datum: k.dataset.datum || '',
    klass: k.dataset.klass || '',
    kurs: k.dataset.kurs || '',
    langd: ($('.tumlangd', k) || {}).textContent || '',
    harledd: k.hasAttribute('data-harledd')
  });

  /* Vilken av dagens lektioner? Har dagen bara en är svaret givet. Har den flera
     avgör innehållet: kursen i rubriken, annars momentet slås upp i bokens
     register — boken hör till en kurs, och kursen pekar ut lektionen. Är två
     klasser kvar på samma kurs väljer vi den klass som kursens övriga
     inspelningar tillhör. Finns inget av det lämnar vi taggen tom — en gissning
     som ser ut som ett faktum är värre än ett hål. */
  const nyckel = k => ((String(k || '').toLowerCase().match(/(\d+\s*[a-z]?)\s*$/) || [''])[0] || '').replace(/\s+/g, '');
  function ur_schemat(p) {
    const K = window.Kalender;
    if (!K || !p.datum) return null;
    const dagen = (K.schemaFor(p.datum) || []).filter(s => !p.klass || s.klass === p.klass);
    if (!dagen.length) return null;
    if (dagen.length === 1) return { rad: dagen[0], hur: 'schemat' };
    const text = p.namn.toLowerCase();
    let hur = 'schemat';
    let kand = dagen.filter(s => {
      const kurs = String(s.kurs || '').toLowerCase();
      return (kurs && text.includes(kurs)) || (nyckel(kurs) && text.includes(nyckel(kurs)));
    });
    if (kand.length !== 1) {
      /* Vilken lektion inspelningen hör till avgjordes förr av om ett ord i
         filnamnet fanns i 3c:s register OCH om den valda boken råkade heta samma
         som kursen. En Ma 4-inspelning kunde då inte kännas igen alls. Nu prövas
         varje kandidatlektion mot registret för SIN egen kurs. */
      const ord = text.split(/[^a-zåäöé0-9]+/).filter(w => w.length >= 5);
      const iBoken = ord.length ? dagen.filter(s => {
        const A = (window.Bok && window.Bok.registerFor ? window.Bok.registerFor(s.kurs) : null) || [];
        return A.some(a => ord.some(w => `${a.titel} ${a.kap} ${a.vag || ''}`.toLowerCase().includes(w)));
      }) : [];
      if (iBoken.length) { kand = iBoken; hur = 'innehållet'; }
    } else hur = 'innehållet';
    if (kand.length > 1) {
      const rakna = kl => kort().filter(k => k !== p.el && k.dataset.klass === kl && k.dataset.kurs === kand[0].kurs).length;
      kand = kand.slice().sort((a, z) => rakna(z.klass) - rakna(a.klass));
      if (!rakna(kand[0].klass)) return null;
    }
    return kand.length ? { rad: kand[0], hur } : null;
  }

  function harled() {
    let andrat = false;
    kort().forEach(k => {
      const p = post(k);
      if (p.klass && p.kurs) return;
      const traff = ur_schemat(p);
      if (!traff) return;
      const s = traff.rad;
      k.dataset.klass = p.klass || s.klass || '';
      k.dataset.kurs = p.kurs || s.kurs || '';
      k.setAttribute('data-harledd', '');
      const tagg = $('.tagg', k);
      if (tagg) {
        tagg.dataset.cc = FARG[k.dataset.kurs] || 'sky';
        const kl = $('[data-del="klass"]', tagg), ku = $('[data-del="kurs"]', tagg);
        if (kl && k.dataset.klass) { kl.textContent = k.dataset.klass; kl.removeAttribute('data-tom'); }
        if (ku && k.dataset.kurs) { ku.textContent = k.dataset.kurs; ku.removeAttribute('data-tom'); }
        tagg.dataset.tip = `Klass och kurs lästa ur ${traff.hur} (${s.tid || ''} · ${s.klass} · ${s.kurs}) — klicka för att ändra`.replace(/\s+/g, ' ');
      }
      const meta = $('.meta', k);
      if (meta && !$('.harledd', meta)) {
        const m = document.createElement('span');
        m.className = 'sprakmark harledd';
        m.dataset.tip = `Appen läste klass och kurs ur ${traff.hur} — ändra genom att klicka på taggen`;
        m.textContent = 'ur ' + traff.hur;
        meta.appendChild(m);
      }
      andrat = true;
    });
    return andrat;
  }

  /* Inspelningen hör till lektionen: samma dag, samma klass, och samma kurs när
     båda vet sin kurs. Vet inspelningen inte sin klass hängs den INTE på någon
     lektion — hellre ohängd än på fel lektion. */
  function forLektion(datum, s) {
    s = s || {};
    return kort().map(post).filter(p => p.datum === datum && p.klass && p.klass === s.klass
      && (!s.kurs || !p.kurs || p.kurs === s.kurs));
  }

  /* ══════════ 1 · BANDET ÖVER VECKAN ══════════
     En inspelning utan klass hänger ingenstans. Den får inte tyst försvinna —
     bandet frågar där man ändå tittar, och tystnar när man svarat. */
  const dagord = d => (window.Kalender && window.Kalender.ord) ? window.Kalender.ord(d) : d;
  const oplacerade = () => kort().map(post).filter(p => !p.klass);

  function klassval(p) {
    const K = window.Kalender;
    const dagen = (K && K.schemaFor(p.datum)) || [];
    const sedda = [];
    return dagen.filter(s => s.klass && !sedda.includes(s.klass) && sedda.push(s.klass));
  }

  /* Svaret är lärarens, inte appens: ingen «ur schemat»-markering sätts här. */
  function placera(p, s) {
    p.el.dataset.klass = s.klass || '';
    p.el.dataset.kurs = s.kurs || '';
    const tagg = $('.tagg', p.el);
    if (tagg) {
      tagg.dataset.cc = FARG[s.kurs] || 'sky';
      const kl = $('[data-del="klass"]', tagg), ku = $('[data-del="kurs"]', tagg);
      if (kl) { kl.textContent = s.klass; kl.removeAttribute('data-tom'); }
      if (ku && s.kurs) { ku.textContent = s.kurs; ku.removeAttribute('data-tom'); }
    }
    const h = $('.harledd', p.el);
    if (h) h.remove();
    rita();
    window.Klass && window.Klass.rita && window.Klass.rita();
    window.toast && window.toast(`${p.namn} hör till ${s.klass}`);
  }

  function ritaBand() {
    const band = $('#oplacband');
    if (!band) return;
    const kvar = oplacerade();
    band.hidden = !kvar.length;
    band.innerHTML = '';
    if (!kvar.length) return;
    const p = kvar[0];
    band.insertAdjacentHTML('beforeend', '<span class="arvprick"></span><p></p>');
    $('p', band).innerHTML = `<b>${kvar.length === 1 ? '1 inspelning väntar' : kvar.length + ' inspelningar väntar'} på klass</b> · ${dagord(p.datum)} · ${p.langd}`;
    const namn = document.createElement('button');
    namn.type = 'button';
    namn.className = 'oplacchip';
    namn.textContent = p.namn;
    namn.dataset.tip = 'Lyssna innan du avgör vilken klass det är';
    namn.addEventListener('click', () => window.Lektion && window.Lektion.oppna(p.el));
    band.appendChild(namn);
    const fraga = document.createElement('span');
    fraga.className = 'oplacfraga';
    const val = klassval(p);
    fraga.innerHTML = `<span class="oplacvad">${val.length ? 'Vilken klass?' : 'Ingen lektion i schemat den dagen'}</span>`;
    val.forEach(s => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'oplacknapp';
      b.textContent = s.klass;
      b.dataset.tip = `${s.tid || ''} · ${s.kurs || ''}`.trim();
      b.addEventListener('click', () => placera(p, s));
      fraga.appendChild(b);
    });
    band.appendChild(fraga);
  }

  /* ══════════ 3 · INSPELNINGARNA I SÖKRUTAN ══════════
     Lådan under schemat är borta. Att leta rätt på en inspelning är en SÖKNING,
     och appen har redan en sökruta — den högst upp, där man frågar appen eller
     söker i orden. «Inspelningar» är tredje läget i den: samma fält, samma rad.
     Lådan här nere ritar bara träffarna och sysslorna (döpa om, radera,
     säkerhetskopiera); huvudet och det egna sökfältet behövs inte längre. */
  /* Markeringen nycklas på KORTET, inte på namnet — ett namn kan bytas mitt i,
     och två lektioner kan heta samma sak. */
  let oppen = false, sok = '', markt = new Set();
  /* Segmentet i sökrutan äger öppet/stängt — inget eget huvud att klicka på. */
  function lage(pa) {
    oppen = !!pa;
    if (!oppen) { sok = ''; markt.clear(); }
    ritaLada();
  }
  function sokord(v) { sok = v || ''; ritaLada(); }

  const minuter = t => { const m = String(t || '').match(/(\d+)\s*min/); return m ? +m[1] : 0; };
  function ritaLada() {
    const lada = $('#insplada');
    if (!lada) return;
    const alla = kort().map(post);
    /* Lådan göms ALDRIG av läget — då skulle bytet bli ett hopp. Den fälls:
       .ilyta växer och krymper, och tom tar den ingen plats (klass.css). */
    lada.hidden = !alla.length;
    if (!alla.length) return;
    const tim = alla.reduce((a, p) => a + minuter(p.langd), 0);
    const synliga = alla.filter(p => !sok || `${p.namn} ${p.klass} ${p.kurs}`.toLowerCase().includes(sok.toLowerCase()));
    lada.innerHTML = `<div class="ilyta"><div class="ilinner"><div class="ilkropp">
      <div class="iltopp"><span class="ilnamn">Alla inspelningar</span><span class="ilant">${alla.length} · ${Math.floor(tim / 60)} tim ${tim % 60} min${sok ? ` · ${synliga.length} matchar «${sok}»` : ''}</span></div><div class="illista"></div>
      <div class="ilfot"><button class="radera" type="button">${markt.size ? `Radera ${markt.size} markerad${markt.size === 1 ? '' : 'e'}` : 'Radera'}</button><button class="ghost" type="button" data-backup>Säkerhetskopiera alla</button><span class="mjuk ilnot">Ljudet ligger kvar på datorn tills du raderar det</span></div></div></div></div>`;
    /* Öppningen är en rörelse, inte ett hopp: ytan växer och innehållet tonar in
       — samma mjuka fällning som veckobriefen. */
    lada.toggleAttribute('data-oppen', oppen);
    const lista = $('.illista', lada);
    synliga.forEach(p => {
      const r = document.createElement('div');
      r.className = 'ilrad';
      r.innerHTML = '<button class="ilkryss" type="button" role="checkbox" aria-label="Markera inspelningen"></button><button class="iltext" type="button"><b></b><span></span></button><span class="ilknapp"><button class="lank" type="button" data-dop>Döp om</button></span>';
      const kryss = $('.ilkryss', r);
      const pa = markt.has(p.el);
      kryss.setAttribute('aria-checked', String(pa));
      if (pa) kryss.textContent = '✓';
      kryss.addEventListener('click', () => { pa ? markt.delete(p.el) : markt.add(p.el); ritaLada(); });
      $('.iltext b', r).textContent = p.namn;
      $('.iltext span', r).textContent = [p.klass || 'ingen klass', p.kurs, dagord(p.datum), p.langd, p.harledd ? 'ur innehållet' : ''].filter(Boolean).join(' · ');
      $('.iltext', r).addEventListener('click', () => window.Lektion && window.Lektion.oppna(p.el));
      $('[data-dop]', r).addEventListener('click', () => dopOm(p, r));
      lista.appendChild(r);
    });
    if (!synliga.length) lista.insertAdjacentHTML('beforeend', '<p class="mjuk" style="margin:8px 0">Ingen inspelning matchar sökningen.</p>');
    $('.radera', lada).addEventListener('click', () => {
      const bort = kort().filter(k => markt.has(k));
      const antal = bort.length;
      /* Knappen är aldrig död — den säger vad som saknas i stället. */
      if (!antal) return window.toast && window.toast('Markera de inspelningar som ska bort');
      /* Allt destruktivt i appen går att ångra ur toasten. Två markerade kort
         intill varandra: en nodreferens duger inte som plats — index i listan
         plus omvänd ordning återställer rätt. */
      const platser = bort.map(k => ({ k, foralder: k.parentElement, i: [...k.parentElement.children].indexOf(k) }));
      bort.forEach(k => k.remove());
      markt.clear();
      rita();
      window.Klass && window.Klass.rita && window.Klass.rita();
      window.toast && window.toast(
        `${antal} ${antal === 1 ? 'inspelning' : 'inspelningar'} raderades`, 'Ångra', () => {
          platser.slice().sort((a, b) => a.i - b.i).forEach(p => p.foralder.insertBefore(p.k, p.foralder.children[p.i] || null));
          rita();
          window.Klass && window.Klass.rita && window.Klass.rita();
        });
    });
    $('[data-backup]', lada).addEventListener('click', () => window.toast && window.toast('Säkerhetskopian skrivs — ljudet stannar på datorn'));
  }

  function dopOm(p, rad) {
    const t = $('.iltext b', rad);
    const falt = document.createElement('input');
    falt.className = 'field ildop';
    falt.value = p.namn;
    t.replaceWith(falt);
    falt.focus();
    falt.select();
    const klar = spara => {
      if (spara && falt.value.trim()) {
        const n = $('.namn', p.el);
        if (n) n.textContent = falt.value.trim();
      }
      rita();
      window.Klass && window.Klass.rita && window.Klass.rita();
    };
    falt.addEventListener('keydown', e => {
      if (e.key === 'Enter') klar(true);
      if (e.key === 'Escape') klar(false);
    });
    falt.addEventListener('blur', () => klar(true));
  }

  function rita() {
    ritaBand();
    ritaLada();
  }

  function start_() {
    harled();
    rita();
    if (window.Klass && window.Klass.rita) window.Klass.rita();
  }
  if (document.readyState === 'loading') addEventListener('DOMContentLoaded', start_);
  else start_();

  return { forLektion, harled, rita, lage, sokord, lista: () => kort().map(post) };
})();
