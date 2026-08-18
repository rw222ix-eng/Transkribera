/* ══════════ BOKEN SOM UPPSLAG ══════════
   Riktning 02. Sidorna är bilder, inte siffror: man klickar första och sista
   sidan i spannet — samma gest som att slå upp boken på bordet. Remsan går
   genom HELA boken, inte bara avsnittet, så vilket spann som helst går att
   välja; avsnittslistan är bara en genväg till rätt ställe i remsan.
   Momentfältet finns kvar för den som hellre skriver, men det är inte längre
   den första vägen — och «Använd» är borta, det fanns två vägar till steg 3. */
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const vard = $('#bokdel');
  if (!vard || !window.Bok) return;

  /* Hyllan: prototypens tre böcker tills servern svarar med lärarens egna
     (bok.js taEmot). Med server är hyllan hennes — också när den är tom. */
  let BOCKER = ['Matematik 5000+ 3c', 'Matematik 5000+ 4', 'Exponent 3c'];
  const grans = a => String(a.sid).split('–').map(Number);
  /* Registret följer BOKEN i hyllan, inte appens första bok. Låg det fast på 3c
     tolkades en Ma 4-sida mot 3c:s register: s. 178 i Matematik 4 blev «4.4
     Gränsvärden» — det 3c-avsnitt som råkar innehålla sidnumret — och just det
     momentet skrevs sedan på pappret. */
  let bok = window.Bok.namn;
  const reg = () => (window.Bok.registerForBok ? window.Bok.registerForBok(bok) : window.Bok.avsnitt);
  /* Prototypens bok har inget slut, så remsan gissade: sista avsnittet plus
     fyrtio sidor, minst 320. En riktig bok VET hur många sidor den har —
     PDF:ens sidantal minus omslag och förord (app/bok.py sidoffset). */
  const sista = () => {
    const riktig = window.Bok.sidorFor ? window.Bok.sidorFor(bok) : 0;
    if (riktig) return riktig;
    const A = reg();
    return A.length ? Math.max(320, ...A.map(a => grans(a)[1] + 40)) : 320;
  };
  /* …och var den BÖRJAR. Ett negativt sidoffset betyder att PDF:en saknar
     bokens första blad: i Matematik 5000+ 1a är tryckt s. 6 PDF-sida 1, och
     s. 1–5 finns ingenstans att hämta. Remsan ska inte erbjuda sidor som bara
     kan bli tomma blad — routes_bok.sidbild svarar 404 «sidan ligger före
     bokens början», och `onerror` tar då bort bilden utan att säga varför. */
  const forsta = () => (window.Bok.forstaFor ? window.Bok.forstaFor(bok) : 1);
  /* Spannet hålls innanför BOKENS pärmar, och byter man bok byter man pärmar.
     Ett spann som slutade på s. 349 i en bok på 349 sidor pekar utanför en bok
     på 303: servern svarar 404, bilden tas bort och bladet står tomt. Det var
     precis vad läraren såg när hon bytte till rätt bok efter att fel bok
     stått förvald — uppslaget «laddade inte» för den nya boken. */
  function klampa() {
    const F = forsta(), S = Math.max(F, sista());
    fran = Math.max(F, Math.min(S, fran));
    till = Math.max(fran, Math.min(S, till));
  }

  const knapp = $('#bokvalj'), knapptext = $('.valjtext', knapp);
  const avsnittsknapp = $('#bokavsnitt'), lista = $('#bkkapitel');
  const uppslag = $('#bkuppslag'), remsa = $('#bkremsa'), spann = $('#bkspann');
  const moment = $('#moment'), momentrad = $('#momentrad');

  /* Utan register finns inget avsnitt att stå på — remsan öppnar då på sidan
     ett och avsnittsknappen säger «Välj avsnitt». Det händer med server men
     utan inläst bok, och det är sant om läget. */
  let avsnitt = window.Bok.nasta();
  let fran = avsnitt ? grans(avsnitt)[0] : 1, till = avsnitt ? grans(avsnitt)[1] : 1;
  let halv = false;

  const avsnittFor = sida => reg().find(a => { const [f, t] = grans(a); return sida >= f && sida <= t; }) || null;
  const rullaLada = (box, mal) => (window.rullaLada || ((b, y) => { b.scrollTop = y; }))(box, mal, 520);

  /* ── Uppslaget: första och sista sidan som två blad ──
     Bladen var ritade attrapper: fem grå streck på hårdkodade bredder, lika
     för varje sida i varje bok. De såg ut som en förhandsvisning och var det
     inte, vilket är sämre än att inte visa något alls — läraren klickar fram
     ett spann i remsan för att SE om hon träffat rätt uppslag, och strecken
     svarade likadant om hon träffat eller inte.

     Strecken ligger kvar som underlägg. De syns medan bilden hämtas, och de
     blir kvar som enda innehåll när ingen bild går att få: prototypens böcker
     har inget id, och en importerad bok vars PDF flyttats kan bara visa de
     sidor som redan renderats. Bladet ska säga sidnummer och avsnitt även då. */
  function ritaUppslag() {
    const id = window.Bok.bokId ? window.Bok.bokId(bok) : null;
    const blad = (nr, roll) => {
      const a = avsnittFor(nr);
      const rader = [92, 78, 96, 64, 88].map(w => `<i style="width:${w}%"></i>`).join('');
      /* onerror tar bort bilden i stället för att lämna en trasig ikon —
         underlägget under den är redan ett fullgott blad. */
      const bild = id
        ? `<img class="bkbild" alt="Sida ${nr}" src="/api/bocker/${id}/sida/${nr}.png" onerror="this.remove()">`
        : '';
      return `<div class="bkblad"><span class="bkark"><span class="bkbrub"></span>${rader}${bild}</span><span class="bkbnr">${nr} · ${roll}</span><span class="bkbavs">${a ? a.nr + ' ' + a.titel : 'utanför registret'}</span></div>`;
    };
    uppslag.innerHTML = blad(fran, 'första sidan') + blad(till, 'sista sidan');
  }

  /* ── Remsan: hela boken, sida för sida ── */
  function ritaRemsa() {
    let ut = '';
    const A = reg(), SISTA = sista();
    for (let s = forsta(); s <= SISTA; s++) {
      const i = s >= fran && s <= till;
      const kant = s === fran || s === till;
      const start = A.some(a => grans(a)[0] === s);
      ut += `<button class="bksida" type="button" data-s="${s}"${i ? ' data-i' : ''}${kant ? ' data-kant' : ''}${start ? ' data-start' : ''} aria-label="Sida ${s}${avsnittFor(s) ? ' · ' + avsnittFor(s).nr + ' ' + avsnittFor(s).titel : ''}"><span>${s}</span></button>`;
    }
    remsa.innerHTML = ut;
    centrera(false);
  }
  function centrera(mjukt = true) {
    const el = $(`.bksida[data-s="${fran}"]`, remsa);
    if (!el) return;
    const mal = Math.max(0, el.offsetLeft - remsa.clientWidth / 2 + el.offsetWidth / 2);
    if (mjukt && remsa.scrollTo) remsa.scrollTo({ left: mal, behavior: 'smooth' });
    else remsa.scrollLeft = mal;
  }
  function markera() {
    [...remsa.children].forEach(el => {
      const s = +el.dataset.s;
      el.toggleAttribute('data-i', s >= fran && s <= till);
      el.toggleAttribute('data-kant', s === fran || s === till);
    });
  }

  /* Alla avsnitt spannet rör vid, inte bara det på första sidan (bok.js
     avsnitten). s. 5–9 är slutet på 1.1 OCH början på 1.2, och läraren som ser
     «del av 1.1» tror att hon valt en halv lektion. */
  const delarna = () => (window.Bok.avsnitten ? window.Bok.avsnitten(reg(), fran, till) : []);
  const avsnittsnamn = () => delarna().map(d => `${d.a.nr} ${d.a.titel}`).join(' · ');
  function ritaSpann() {
    const antal = till - fran + 1;
    const D = delarna();
    const a = avsnittFor(fran);
    const hela = D.length === 1 && D[0].hela;
    spann.innerHTML = `<b></b><span class="bkfakta"></span><span class="bknyckla">från <input class="bknr" id="bkfran" type="text" inputmode="numeric" maxlength="3" aria-label="Från sida" /> till <input class="bknr" id="bktill" type="text" inputmode="numeric" maxlength="3" aria-label="Till sida" /></span>`;
    $('b', spann).textContent = `s. ${fran}–${till}`;
    $('.bkfakta', spann).textContent = [
      `${antal} ${antal === 1 ? 'sida' : 'sidor'}`,
      D.length ? (hela ? `hela ${a.nr} ${a.titel} · ${a.uppg} uppgifter`
        : `${D.length > 1 ? 'över' : 'del av'} ${D.map(d => `${d.a.nr} ${d.a.titel}`).join(' och ')}`) : 'utanför registret',
      halv ? 'klicka sista sidan' : 'rulla i remsan för att bläddra'
    ].filter(Boolean).join(' · ');
    $('#bkfran', spann).setAttribute('value', fran);
    $('#bktill', spann).setAttribute('value', till);
    ['#bkfran', '#bktill'].forEach(id => {
      const f = $(id, spann);
      f.addEventListener('change', () => {
        const v = Number(f.value) || forsta();
        if (id === '#bkfran') fran = v; else till = v;
        if (till < fran) { const x = fran; fran = till; till = x; }
        klampa();
        halv = false;
        rita(); skrivMoment();
      });
    });
  }

  /* Avsnittslistan har sin egen sökruta: registret är listan man aldrig ska
     behöva scrolla i — tre bokstäver räcker. Därför finns ingen egen knapp för
     att «skriva momentet i stället»; momentet ÄR avsnittet man väljer här. */
  let avsnittssok = '';
  function ritaLista() {
    const pa = window.Bok.nasta();
    const A = reg();
    const q = avsnittssok.trim().toLowerCase();
    const traffar = q ? A.filter(a => (a.nr + ' ' + a.titel + ' ' + (a.vag || '') + ' ' + a.kap).toLowerCase().includes(q)) : A;
    lista.innerHTML = `<div class="bksokrad"><input type="text" id="bksok" placeholder="Sök avsnitt, rubrik eller sidnummer …" aria-label="Sök i boken" value="${avsnittssok.replace(/"/g, '&quot;')}" /></div>`
      + (traffar.length ? traffar.map(a => {
        return `<button class="bkkaprad" type="button" data-nr="${a.nr}"${avsnitt && a.nr === avsnitt.nr ? ' data-pa' : ''}><span class="n">${a.nr} ${a.titel}${pa && a.nr === pa.nr ? '<span class="bktur">står på tur</span>' : ''}</span><span class="s">s. ${a.sid}</span></button>`;
      }).join('') : '<p class="bktomsok">Inget avsnitt matchar sökningen.</p>');
    const falt = $('#bksok', lista);
    if (falt) {
      falt.addEventListener('input', () => {
        const pos = falt.selectionStart;
        avsnittssok = falt.value;
        ritaLista();
        const nytt = $('#bksok', lista);
        if (nytt) { nytt.focus(); nytt.setSelectionRange(pos, pos); }
      });
      falt.addEventListener('keydown', e => {
        if (e.key === 'Escape') { avsnittssok = ''; lista.hidden = true; avsnittsknapp.setAttribute('aria-expanded', 'false'); avsnittsknapp.focus(); }
        if (e.key === 'Enter') { e.preventDefault(); const forst = $('.bkkaprad', lista); forst && forst.click(); }
      });
    }
  }

  function ritaAvsnitt() {
    /* Dörren säger vad spannet ÄR, alla avsnitt det rör vid — inte bara det på
       första sidan. Knappen är ändå vägen till listan; att den namnger två
       avsnitt betyder bara att spannet gör det. */
    avsnittsknapp.textContent = avsnittsnamn() || 'Välj avsnitt';
  }

  function rita() { ritaUppslag(); markera(); ritaSpann(); ritaAvsnitt(); }

  /* Spannet ÄR momentet — fältet fylls i tyst, så steg 3 låses upp av valet. */
  /* ...men bara när momentet är remsans eget. En omritning som INTE kommer ur
     en gest — hyllan som kom från servern, eller uppstarten — får inte skriva
     över ett moment som står där av något annat skäl: ett återställt utkast,
     eller något läraren skrivit själv. Den kapplöpningen (bokhyllan mot
     dokumenthydreringen) var det kända flakyt «utkastet ligger framme igen»:
     vann `bok-redo` stod «s. 192–197 ur Matematik 5000+ 3c» i fältet i stället
     för lärarens moment — i testet, och lika gärna framför läraren. */
  let skrivet = '';
  function skrivMoment(tvinga = true) {
    if (!moment) return;
    if (!tvinga && (moment.value || '').trim() && moment.value !== skrivet) return;
    const a = avsnittFor(fran);
    /* MOMENTET går vidare in i prompten. Stod bara avsnittet på första sidan
       där byggdes tavlan för kubikrötter på en lektion som till hälften handlar
       om potenser — hälften av lektionen fanns inte i begäran. */
    const namn = avsnittsnamn();
    moment.value = namn || `s. ${fran}–${till} ur ${bok}`;
    skrivet = moment.value;
    moment.dataset.sidor = `s. ${fran}–${till}`;
    moment.removeAttribute('data-gissad');
    const g = $('#momentgissat'); if (g) g.hidden = true;
    const f = $('#momentfakta');
    /* Uppgiftsantalet gäller ETT avsnitt. Rör spannet flera är summan inte
       avsnittets, och ett tal som inte betyder något är sämre än inget. */
    const ettAvsnitt = delarna().length === 1;
    if (f) { f.hidden = false; f.querySelector('span:last-child').textContent = `${bok} · s. ${fran}–${till}${a && ettAvsnitt ? ' · ' + a.uppg + ' uppgifter i avsnittet' : ''}`; }
    /* Bara 'input': det markerar steget som ifyllt utan att kasta en framåt.
       Vägen till steg 3 är knappen Nästa — en enda väg, som i riktning 02. */
    moment.dispatchEvent(new Event('input', { bubbles: true }));
  }

  /* ── Klick i remsan: första sidan, sedan sista ── */
  remsa.addEventListener('click', e => {
    const b = e.target.closest('.bksida');
    if (!b) return;
    const s = +b.dataset.s;
    if (!halv) { fran = s; till = s; halv = true; }
    else { if (s < fran) { till = fran; fran = s; } else till = s; halv = false; }
    rita();
    if (!halv) skrivMoment();
  });

  /* ── Avsnittslistan: en genväg till rätt ställe i remsan ── */
  avsnittsknapp.addEventListener('click', () => {
    const oppen = !lista.hidden;
    lista.hidden = oppen;
    avsnittsknapp.setAttribute('aria-expanded', String(!oppen));
    if (!oppen) { ritaLista(); requestAnimationFrame(() => { const f = $('#bksok', lista); f && f.focus(); }); }
  });
  lista.addEventListener('click', e => {
    const r = e.target.closest('.bkkaprad');
    if (!r) return;
    avsnitt = reg().find(a => a.nr === r.dataset.nr);
    [fran, till] = grans(avsnitt);
    halv = false;
    lista.hidden = true;
    avsnittsknapp.setAttribute('aria-expanded', 'false');
    rita(); centrera(); skrivMoment();
  });

  /* ── Bokväljaren gör något nu ── */
  const bokpanel = document.createElement('div');
  bokpanel.className = 'bkbokpanel';
  bokpanel.hidden = true;
  const byggBokpanel = () => {
    bokpanel.innerHTML = BOCKER.map(b => `<button class="bkbokrad" type="button"${b === bok ? ' data-pa' : ''}>${b}</button>`).join('');
  };
  byggBokpanel();
  $('#bokvaljare').appendChild(bokpanel);
  knapp.addEventListener('click', () => {
    bokpanel.hidden = !bokpanel.hidden;
    knapp.setAttribute('aria-expanded', String(!bokpanel.hidden));
  });
  /* Byter man bok byter man register: remsan, uppslaget, avsnittsknappen,
     momentet, dörren och kvittot måste ritas om i samma gest. Gjorde bara
     momentfältet det stod tre olika svar på samma sida samtidigt i panelen —
     och det som trycks på pappret sa något annat än knappen intill. */
  function valjBok(namn, tvinga = true) {
    bok = namn;
    window.Bok.namn = namn;
    knapptext.textContent = namn;
    [...bokpanel.children].forEach(x => x.toggleAttribute('data-pa', x.textContent.trim() === namn));
    /* FÖRE omritningen: bladen ritas ur `fran`/`till`, och pekar de utanför den
       nya boken hämtas två sidbilder som bara kan bli 404. */
    klampa();
    ritaRemsa();
    rita();
    skrivMoment(tvinga);
    if (window.Kallor) {
      window.Kallor.ritaDorrar && window.Kallor.ritaDorrar();
      window.Kallor.ritaKvitto && window.Kallor.ritaKvitto();
    }
  }
  bokpanel.addEventListener('click', e => {
    const b = e.target.closest('.bkbokrad');
    if (!b) return;
    bokpanel.hidden = true;
    knapp.setAttribute('aria-expanded', 'false');
    valjBok(b.textContent.trim());
    window.toast && window.toast(`Boken är nu ${bok}`);
  });
  /* Servern svarade med lärarens hylla: den ersätter prototypens. Boken som
     var vald finns sällan kvar — då öppnas den första i hyllan, och finns
     ingen bok alls står remsan kvar utan register (och säger det). */
  document.addEventListener('bok-redo', e => {
    const bocker = e.detail || [];
    BOCKER = bocker.map(b => b.namn);
    byggBokpanel();
    if (BOCKER.length && !BOCKER.includes(bok)) {
      const a = window.Bok.nasta();
      if (a) { [fran, till] = grans(a); avsnitt = a; halv = false; }
      valjBok(BOCKER[0], false);
    } else {
      ritaRemsa(); rita(); skrivMoment(false);
    }
  });
  document.addEventListener('pointerdown', e => {
    if (!bokpanel.hidden && !$('#bokvaljare').contains(e.target)) { bokpanel.hidden = true; knapp.setAttribute('aria-expanded', 'false'); }
    if (!lista.hidden && !lista.contains(e.target) && e.target !== avsnittsknapp) { lista.hidden = true; avsnittsknapp.setAttribute('aria-expanded', 'false'); }
  }, true);

  /* ── Den som hellre skriver ── */
  /* Menyerna stänger sig själva när musen lämnar dem — mjukt, med en kort
     respit så att en genväg över kanten inte slår igen dörren. */
  function stang(el, efter) {
    if (el.hidden) return;
    el.setAttribute('data-ut', '');
    setTimeout(() => { el.hidden = true; el.removeAttribute('data-ut'); efter && efter(); }, 130);
  }
  function hovervakt(el, lamna) {
    let t = null;
    el.addEventListener('pointerenter', () => { clearTimeout(t); t = null; });
    el.addEventListener('pointerleave', () => { clearTimeout(t); t = setTimeout(lamna, 260); });
  }

  hovervakt($('#bokvaljare'), () => stang(bokpanel, () => knapp.setAttribute('aria-expanded', 'false')));
  hovervakt(lista, () => stang(lista, () => avsnittsknapp.setAttribute('aria-expanded', 'false')));
  hovervakt(avsnittsknapp, () => { if (!lista.hidden && !lista.matches(':hover')) stang(lista, () => avsnittsknapp.setAttribute('aria-expanded', 'false')); });

  /* Ingen scrollbar under remsan — man håller musen över den och rullar.
     Upp bär åt höger (framåt i boken), ner åt vänster. */
  remsa.setAttribute('data-egenrull', '');
  remsa.addEventListener('wheel', e => {
    let d = e.deltaY || e.deltaX;
    if (!d) return;
    if (e.deltaMode === 1) d *= 16;
    else if (e.deltaMode === 2) d *= remsa.clientWidth;
    e.preventDefault();
    remsa.style.scrollBehavior = 'auto';
    remsa.scrollLeft -= Math.sign(d) * Math.min(Math.abs(d), 90) * 1.4;
    clearTimeout(remsa._rullT);
    remsa._rullT = setTimeout(() => { remsa.style.scrollBehavior = ''; }, 90);
  }, { passive: false });

  ritaRemsa();
  rita();
  skrivMoment(false);          /* uppstart: fältet är tomt och fylls — men ett
                                  utkast som redan hunnit fram vinner */
  requestAnimationFrame(() => centrera(false));
  /* Steget är dolt när sidan laddas — remsan kan inte mäta sig själv då.
     Så fort den får bredd (steget öppnas) centrerar den om på spannet. */
  let bredd = 0;
  if (window.ResizeObserver) new ResizeObserver(() => {
    const b = remsa.clientWidth;
    if (b > 0 && bredd === 0) centrera(false);
    bredd = b;
  }).observe(remsa);
  const steg2 = vard.closest('.plansteg');
  if (steg2) new MutationObserver(() => {
    if (!steg2.hidden) requestAnimationFrame(() => centrera(false));
  }).observe(steg2, { attributes: true, attributeFilter: ['hidden'] });
  /* Boken som laddas upp i steg 3 läggs till i hyllan och blir vald direkt. */
  /* `spann` är valfritt, och finns det byts boken OCH sidorna i EN gest. Utan
     det ritades uppslaget först om med förra spannets sidnummer i den nya
     boken innan det rätta spannet hann sättas — två sidbilder ingen bad om,
     och en sidbild kostar en pdfium-öppning av en fil på ett par hundra
     megabyte (app/web/routes_bok.py: sidbild). */
  function laggBok(namn, spann) {
    if (!BOCKER.includes(namn)) {
      BOCKER.push(namn);
      const r = document.createElement('button');
      r.className = 'bkbokrad';
      r.type = 'button';
      r.textContent = namn;
      bokpanel.appendChild(r);
    }
    if (spann && spann.fran) {
      fran = Math.round(spann.fran);
      till = Math.round(spann.till || spann.fran);
      halv = false;
    }
    valjBok(namn);
  }
  /* Klassprofilen sätter spannet åt läraren: boken minns var klassen slutade.
     Samma väg som ett klick i remsan, bara utan klicket. */
  function sattSpann(f, t) {
    fran = Math.round(f || fran);
    till = Math.round(t || fran);
    klampa();
    halv = false;
    ritaRemsa();
    rita();
    centrera(false);
    skrivMoment();
  }
  window.Uppslag = { spann: () => ({ fran, till, bok }), laggBok, satt: sattSpann, sista };
})();
