/* ══════════ ELEV FÖR ELEV ══════════
   Klassrättningen (rattning.js) är en summa per uppgift. Den räcker för
   planeringen och inte för eleven: ett betyg går inte att räkna ur en
   klumpsumma — C kräver sin andel av C- och A-poängen — och en feedbacktext
   går inte att skriva till en klass.

   Alltså den här vyn: en elev i taget, poängknappar per NIVÅ, betyget live mot
   provets kravgränser. Klassens siffror räknas fram ur elevernas på servern, så
   lektionsplaneringen läser samma rättning som förut utan att läraren skriver
   in någonting två gånger.

   Elevens tryckta prov är orört. E/C/A-splitten står redan i
   bedömningsanvisningen — det här är rättarens vy, inte elevens.

   Ingen mus krävs: siffertangenten sätter poängen i den grupp som har fokus och
   flyttar vidare, Enter går till nästa elev. */
(() => {
  const $ = (s, r) => (r || document).querySelector(s);
  const skal = $('#elevskal');
  if (!skal) return;

  const NIVA = ['E', 'C', 'A'];
  let doc = null, rader = [], granser = null, elever = [], gruppId = null;
  let resultat = {}, feedback = {}, index = 0, smutsigt = false, harServer = false;
  let oversikt = false;

  /* Kravgränserna räknas också här, inte bara på servern (app/rattning.py
     granser). Samma skäl som FORMAGA_MONSTER i rattning.js: betyget ska stå
     på skärmen medan läraren klickar, och prototypen har ingen server. Serverns
     tal vinner när de finns — den läste provets egen JSON. */
  const KRAV = { e: 0.25, c: 0.45, cCa: 0.30, a: 0.65, aA: 0.40 };
  function granserAv(rad) {
    let e = 0, c = 0, a = 0;
    rad.filter(r => !r.grupp).forEach(r => {
      const p = r.peca || [r.p || 0, 0, 0];
      e += p[0] || 0; c += p[1] || 0; a += p[2] || 0;
    });
    const total = e + c + a;
    return {
      total,
      E: { minst: Math.ceil(total * KRAV.e) },
      C: { minst: Math.ceil(total * KRAV.c), varav_ca: Math.ceil((c + a) * KRAV.cCa) },
      A: { minst: Math.ceil(total * KRAV.a), varav_a: Math.ceil(a * KRAV.aA) }
    };
  }

  /* Elevens poäng per nivå + hur många rader som fortfarande är tomma. `kvar`
     är varför betyget inte visas direkt: ett betyg på halva provet är fejkad
     precision. */
  function summorAv(varden) {
    let e = 0, c = 0, a = 0, tak = 0, kvar = 0;
    rader.filter(r => !r.grupp).forEach(r => {
      const p = r.peca || [r.p || 0, 0, 0];
      const v = (varden || {})[r.nyckel] || [null, null, null];
      let tomt = false;
      for (let i = 0; i < 3; i++) {
        tak += p[i] || 0;
        if (!p[i]) continue;
        if (v[i] == null) { tomt = true; continue; }
        const x = Math.max(0, Math.min(p[i], Math.round(Number(v[i]) || 0)));
        if (i === 0) e += x; else if (i === 1) c += x; else a += x;
      }
      if (tomt) kvar++;
    });
    return { total: e + c + a, e, c, a, tak, kvar };
  }

  /* Det HÖGSTA betyg vars båda villkor är uppfyllda — NP:s ordning. Under
     E-gränsen är F, och F skrivs ut som alla andra betyg. */
  function betygAv(s, g) {
    if (!g) return 'F';
    if (s.total >= g.A.minst && s.a >= (g.A.varav_a || 0)) return 'A';
    if (s.total >= g.C.minst && (s.c + s.a) >= (g.C.varav_ca || 0)) return 'C';
    if (s.total >= g.E.minst) return 'E';
    return 'F';
  }

  const nuvarande = () => elever[index] || null;
  const varden = e => (resultat[String(e && e.id)] ||= {});
  const skrev = e => {
    const v = resultat[String(e && e.id)] || {};
    return Object.keys(v).some(k => (v[k] || []).some(x => x != null));
  };

  /* ── Ritandet ─────────────────────────────────────────────────────────── */

  function ritaBand() {
    const band = $('#elevband');
    band.innerHTML = '';
    elever.forEach((e, i) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'elevprick';
      b.textContent = e.namn;
      b.setAttribute('aria-label', `Gå till ${e.namn}`);
      if (i === index) b.setAttribute('data-nu', '');
      const s = summorAv(varden(e));
      if (skrev(e) && !s.kvar) b.setAttribute('data-klar', '');
      else if (skrev(e)) b.setAttribute('data-halv', '');
      b.addEventListener('click', () => { index = i; rita(); });
      band.appendChild(b);
    });
  }

  function ritaRad(r) {
    const rad = document.createElement('div');
    if (r.grupp) {
      rad.className = 'elevgrupprad';
      rad.innerHTML = '<span class="rattnr"></span><span class="rattupp"></span>';
      $('.rattnr', rad).textContent = r.nr;
      $('.rattupp', rad).textContent = r.text;
      return rad;
    }
    rad.className = 'elevrad';
    rad.dataset.nyckel = r.nyckel;
    rad.innerHTML = '<span class="rattnr"></span><span class="elevupp"></span><span class="elevgrupper"></span>';
    $('.rattnr', rad).textContent = r.nr;
    const upp = $('.elevupp', rad);
    upp.textContent = r.text;
    upp.title = r.text;
    const peca = r.peca || [r.p || 0, 0, 0];
    const v = varden(nuvarande())[r.nyckel] || [null, null, null];
    const bar = $('.elevgrupper', rad);
    /* En grupp per nivå SOM HAR POÄNG. De flesta rader har bara en, och då ser
       raden ut som en enkel knapprad 0 1 2 — etiketten står ändå kvar, för det
       är den som säger om poängen är E eller A. */
    NIVA.forEach((namn, i) => {
      if (!peca[i]) return;
      const g = document.createElement('div');
      g.className = 'elevgrupp';
      g.dataset.niva = String(i);
      g.innerHTML = '<span class="elevniva"></span>';
      $('.elevniva', g).textContent = namn;
      /* Ett tabstopp per grupp, inte per knapp: den valda (annars första)
         siffran bär tabindex 0 — pilarna når resten. */
      const stopp = v[i] != null ? v[i] : 0;
      for (let p = 0; p <= peca[i]; p++) {
        const k = document.createElement('button');
        k.type = 'button';
        k.className = 'elevknapp';
        k.dataset.v = String(p);
        k.textContent = String(p);
        k.tabIndex = p === stopp ? 0 : -1;
        k.setAttribute('aria-label', `${p} av ${peca[i]} ${namn}-poäng på uppgift ${r.kod}`);
        if (v[i] === p) k.setAttribute('data-vald', '');
        k.addEventListener('click', () => satt(r, i, p, k));
        g.appendChild(k);
      }
      bar.appendChild(g);
    });
    return rad;
  }

  function rita() {
    if (!doc) return;
    const harKlass = elever.length > 0;
    const redigerar = !!$('#elevklass').dataset.oppen;
    const bilden = oversikt && harKlass && !redigerar;
    $('#elevklass').hidden = harKlass && !redigerar;
    $('#elevvy').hidden = !harKlass || redigerar || bilden;
    $('#elevoversikt').hidden = !bilden;
    $('#elevvisaoversikt').hidden = !harKlass || redigerar || bilden;
    $('#elevbytklass').hidden = !harKlass || redigerar;
    $('#elevklassavbryt').hidden = !harKlass;
    $('#elevspara').hidden = redigerar;
    if (bilden) ritaOversikt();
    const provet = (window.Dokument ? window.Dokument.namn(doc) : 'Provet')
      .replace(/^Prov — /, 'Prov · ') + (doc.klass ? ' · ' + doc.klass : '');
    if (!harKlass) {
      $('#elevnamn').textContent = doc.klass || 'Klassen';
      $('#elevmeta').textContent = provet;
      $('#elevnot').textContent = 'Klasslistan sparas lokalt — den lämnar aldrig datorn.';
      $('#elevspara').disabled = true;
      $('#elevskriv').hidden = true;
      return;
    }
    index = Math.max(0, Math.min(elever.length - 1, index));
    const e = nuvarande();
    $('#elevnamn').textContent = e.namn;
    $('#elevmeta').textContent = `Elev ${index + 1} av ${elever.length} · ${provet}`;

    const lista = $('#elevrader');
    lista.innerHTML = '';
    rader.forEach(r => lista.appendChild(ritaRad(r)));

    const txt = feedback[String(e.id)] || '';
    $('#elevtext').hidden = !txt;
    $('#elevtextfalt').value = txt;
    ritaCi();
    rakna();
  }

  /* Betyget, summan och bandet — det som ändras vid varje klick. Raderna ritas
     inte om: knappen som just trycktes ska behålla sitt fokus. */
  function rakna() {
    const e = nuvarande();
    if (!e) return;
    const s = summorAv(varden(e));
    const g = granser || granserAv(rader);
    const klar = skrev(e) && !s.kvar;
    $('#elevbetyg').textContent = klar ? betygAv(s, g) : '—';
    $('#elevbetyg').dataset.b = klar ? betygAv(s, g) : '';
    $('#elevsumma').textContent = klar
      ? `${s.total} av ${s.tak} p`
      : (skrev(e)
        ? `${s.total} p · ${s.kvar} ${s.kvar === 1 ? 'rad' : 'rader'} kvar`
        : 'Inget ifyllt än');
    const rattade = elever.filter(skrev).length;
    $('#elevspara').textContent = rattade
      ? `Spara — ${rattade} av ${elever.length} rättade` : 'Spara';
    $('#elevspara').disabled = !rattade;
    /* Feedbacken kan skrivas först när alla är färdiga: modellen ska jämföra
       eleven med klassens utfall, och en halv klass är inte klassen. */
    const allaKlara = elever.every(x => !skrev(x) || !summorAv(varden(x)).kvar)
      && rattade > 0;
    $('#elevskriv').hidden = !allaKlara || !!$('#elevklass').dataset.oppen;
    $('#elevtom').textContent = skrev(e) ? 'Rensa eleven' : 'Skrev inte provet';
    $('#elevtom').disabled = !skrev(e);
    $('#elevskriv').disabled = !harServer;
    $('#elevskriv').title = harServer ? '' : 'Kräver Claude Code';
    $('#elevnot').textContent = smutsigt
      ? 'Osparat — tryck Spara.'
      : 'Siffertangent sätter poäng · Enter går till nästa elev · inga namn skickas till modellen.';
    ritaBand();
  }

  /* ── Klassbilden ──────────────────────────────────────
     Samma summor och samma betygsregler som elevvyn — bara alla på en gång.
     Serverns aggregat frågas inte: siffrorna på skärmen kan vara osparade,
     och bilden ska visa det läraren ser, inte det som senast sparades. */
  function ritaOversikt() {
    const kropp = $('#elevtabellrader');
    if (!kropp) return;
    const g = granser || granserAv(rader);
    kropp.innerHTML = '';
    const fordelning = {};
    elever.forEach((e, i) => {
      const s = summorAv(varden(e));
      const klar = skrev(e) && !s.kvar;
      const betyg = klar ? betygAv(s, g) : '';
      if (klar) fordelning[betyg] = (fordelning[betyg] || 0) + 1;
      const tr = document.createElement('tr');
      tr.innerHTML = '<td class="etnamn"></td><td class="etpoang"></td><td></td><td></td><td></td><td class="etbetyg"></td>';
      $('.etnamn', tr).textContent = e.namn;
      $('.etpoang', tr).textContent = skrev(e) ? `${s.total} av ${s.tak}` : '—';
      const celler = tr.children;
      celler[2].textContent = skrev(e) ? String(s.e) : '';
      celler[3].textContent = skrev(e) ? String(s.c) : '';
      celler[4].textContent = skrev(e) ? String(s.a) : '';
      $('.etbetyg', tr).textContent = klar ? betyg
        : skrev(e) ? `${s.kvar} ${s.kvar === 1 ? 'rad' : 'rader'} kvar` : 'skrev inte';
      if (klar) $('.etbetyg', tr).dataset.b = betyg;
      /* Raden är en väg in: klick öppnar eleven i rättningsvyn. */
      tr.addEventListener('click', () => { oversikt = false; index = i; rita(); fokusera(); });
      kropp.appendChild(tr);
    });
    const ordning = ['A', 'C', 'E', 'F'];
    const delar = ordning.filter(b => fordelning[b])
      .map(b => `${fordelning[b]} ${b}`);
    const rattade = elever.filter(skrev).length;
    $('#elevoversiktnot').textContent = [
      `${rattade} av ${elever.length} har något ifyllt`,
      delar.length ? delar.join(' · ') : '',
      'klick på en rad öppnar eleven',
    ].filter(Boolean).join(' · ');
  }
  function kopieraOversikt() {
    const g = granser || granserAv(rader);
    const text = elever.map(e => {
      const s = summorAv(varden(e));
      const klar = skrev(e) && !s.kvar;
      return [e.namn, skrev(e) ? s.total : '', klar ? betygAv(s, g) : ''].join('\t');
    }).join('\n');
    (navigator.clipboard && navigator.clipboard.writeText
      ? navigator.clipboard.writeText(text) : Promise.reject())
      .then(() => window.toast && window.toast('Kopierat — klistra in i betygskatalogen'))
      .catch(() => { $('#elevnot').textContent = 'Kunde inte kopiera — markera i tabellen i stället.'; });
  }

  function satt(r, niva, poang, knapp) {
    const e = nuvarande();
    if (!e) return;
    const v = varden(e);
    const nu = (v[r.nyckel] || [null, null, null]).slice();
    nu[niva] = nu[niva] === poang ? null : poang;   // klick på vald siffra ångrar
    v[r.nyckel] = nu;
    const grupp = knapp.closest('.elevgrupp');
    [...grupp.querySelectorAll('.elevknapp')].forEach(k => {
      const vald = Number(k.dataset.v) === nu[niva];
      if (vald) k.setAttribute('data-vald', '');
      else k.removeAttribute('data-vald');
      k.tabIndex = (nu[niva] != null ? vald : k.dataset.v === '0') ? 0 : -1;
    });
    smutsigt = true;
    rakna();
    if (nu[niva] != null) nasta(grupp);
  }

  /* Nästa grupp att fylla i — nästa nivå på raden, annars nästa rads första.
     Efter sista gruppen stannar fokus kvar: betyget som just tändes ska hinna
     läsas, och Enter är redan vägen till nästa elev. Ett automatiskt hopp
     prövades och togs bort — det ryckte undan betyget i samma ögonblick som
     sista poängen sattes. */
  function nasta(grupp) {
    const alla = [...skal.querySelectorAll('.elevgrupp')];
    const i = alla.indexOf(grupp);
    const n = alla[i + 1];
    if (n) n.querySelector('.elevknapp').focus();
  }

  /* Första ofyllda gruppen — där rättandet ska fortsätta. */
  function fokusera() {
    if (skal.hidden || $('#elevvy').hidden) return;
    const grupper = [...skal.querySelectorAll('.elevgrupp')];
    const g = grupper.find(x => !x.querySelector('[data-vald]')) || grupper[0];
    if (g) g.querySelector('.elevknapp').focus();
  }

  function byt(steg) {
    if (!elever.length) return;
    sparaTyst();
    index = (index + steg + elever.length) % elever.length;
    rita();
    fokusera();
  }

  /* ── Servern ──────────────────────────────────────────────────────────── */

  const server = () => !!(window.API && window.API.pa && doc && doc.id);
  const vag = v => '/api/dokument/' + v.id + '/elevresultat';

  function las(r) {
    if (!r) return;
    if ((r.rader || []).length) rader = r.rader;
    if (r.granser) granser = r.granser;
    if (r.elever) elever = r.elever.filter(e => e.aktiv);
    if (r.group_id) gruppId = r.group_id;
    resultat = Object.assign({}, r.resultat || {});
    feedback = Object.assign({}, r.feedback || {});
  }

  function hamta() {
    if (!server()) return;
    const v = doc;
    window.API.json(vag(v)).then(r => {
      if (doc !== v) return;
      harServer = true;
      las(r);
      smutsigt = false;
      rita();
      /* Omritningen slog undan fokus — utan det är siffertangenterna döda
         och läraren måste klicka innan hon kan börja. Textfält lämnas ifred. */
      const aktiv = document.activeElement;
      if (!aktiv || aktiv.tagName !== 'TEXTAREA') fokusera();
    }).catch(() => {});
  }

  /* ── CI-profilen ──────────────────────────────────────────────────────
     Rättningen ovanför säger hur det gick på DET HÄR pappret. Profilen säger
     vad som brister i KURSEN — samma poäng summerade i kursplanens dimension i
     stället för i uppgifternas, vägda över alla rättade papper med det senaste
     tyngst. Räkningen bor på servern (app/ci_profil.py) och görs inte om här:
     utan server finns ingen historik att räkna på, och en påhittad profil vore
     ett påstående om en riktig elev.

     Svaren cachas per nyckel för sidans livstid — läraren bläddrar fram och
     tillbaka mellan eleverna, och profilen ändras bara när något sparats. */
  let civem = 'Eleven';
  const cicache = new Map();

  function cinyckel() {
    const e = nuvarande();
    if (civem === 'Klassen') return gruppId ? `g${gruppId}` : null;
    return e && e.id > 0 ? `e${e.id}` : null;
  }

  function cihamta() {
    const nyckel = cinyckel();
    if (!server() || !nyckel) return Promise.resolve(null);
    if (cicache.has(nyckel)) return Promise.resolve(cicache.get(nyckel));
    const kurs = encodeURIComponent(doc.kurs || '');
    const vagen = nyckel[0] === 'g'
      ? `/api/groups/${gruppId}/ci-profil?kurs=${kurs}`
      : `/api/elever/${nuvarande().id}/ci-profil?kurs=${kurs}`
        + (gruppId ? `&group_id=${gruppId}` : '');
    return window.API.json(vagen).then(r => {
      cicache.set(nyckel, r);
      return r;
    }).catch(() => null);
  }

  /* Hur många punkter som ritas. Listan ska gå att överblicka utan att rulla —
     det är hålen som söks, och de ligger först. Resten räknas i noten. */
  const CI_TAK = 6;

  function ritaCi() {
    const ruta = $('#elevci');
    if (!ruta) return;
    const nyckel = cinyckel();
    if (!server() || !nyckel) { ruta.hidden = true; return; }
    ruta.hidden = false;
    const lista = $('#elevcilista'), not = $('#elevcinot');
    const vald = cicache.get(nyckel);
    if (!vald) {
      lista.innerHTML = '';
      not.textContent = 'Läser …';
      cihamta().then(() => { if (cinyckel() === nyckel) ritaCi(); });
      return;
    }
    const punkter = (vald.punkter || []).filter(p => p.andel !== null);
    lista.innerHTML = '';
    punkter.slice(0, CI_TAK).forEach(p => {
      const rad = document.createElement('div');
      rad.className = 'elevcirad';
      rad.dataset.styrka = p.styrka;
      rad.innerHTML = '<span class="elevcinamn"></span><span class="elevcispar"><span class="elevcifyll"></span></span><span class="elevciandel"></span>';
      $('.elevcinamn', rad).textContent = p.kort;
      $('.elevcinamn', rad).title = p.kod;
      $('.elevcifyll', rad).style.width = Math.round(p.andel * 100) + '%';
      $('.elevciandel', rad).textContent = Math.round(p.andel * 100) + ' %';
      lista.appendChild(rad);
    });
    /* Ett papper utan CI-data ska säga det rakt ut. «0 %» på en punkt som
       aldrig prövats är ett påstående om eleven, och det värsta slaget: det
       ser ut som ett mätvärde. */
    if (!punkter.length) {
      not.textContent = vald.utan_ci
        ? 'Ingen CI-data — pappren är rättade men uppgifterna saknar centralt innehåll.'
        : 'Ingen CI-data ännu — profilen fylls när ett prov med centralt innehåll rättats.';
      return;
    }
    const kvar = punkter.length - Math.min(CI_TAK, punkter.length);
    const svaga = punkter.filter(p => p.styrka === 'svag').length;
    not.textContent = [
      svaga ? `${svaga} ${svaga === 1 ? 'punkt' : 'punkter'} under 50 %` : 'Inget under 50 %',
      kvar ? `${kvar} till som sitter bättre` : '',
      `vägt över ${vald.dokument} ${vald.dokument === 1 ? 'rättat papper' : 'rättade papper'}, det senaste tyngst`,
    ].filter(Boolean).join(' · ');
  }

  /* Prototypens efternamnssortering — servern gör den riktiga städningen
     (app/klasslista.py: kolumner, numrering, partiklar), men klassen ska
     hamna i samma ordning även utan server. Kommat säger vilket som är
     efternamnet; annars är det sista ordet. */
  function ordnaNamn(namn) {
    const stada = n => n.replace(/^\s*(?:\d+\s*[.):]?|[-*•·])\s*/, '')
      .split(/\s+/).filter(Boolean)
      .map(o => o.length > 1 && o === o.toUpperCase()
        ? o.split('-').map(d => d[0] + d.slice(1).toLowerCase()).join('-') : o)
      .join(' ');
    const dela = n => {
      if (n.includes(',')) {
        const [e, f] = n.split(',');
        return [stada(`${f.trim()} ${e.trim()}`), stada(e.trim())];
      }
      const ord = stada(n).split(' ');
      return [ord.join(' '), ord[ord.length - 1]];
    };
    return namn.map(dela).filter(x => x[0])
      .sort((a, b) => a[1].localeCompare(b[1], 'sv') || a[0].localeCompare(b[0], 'sv'))
      .map(x => x[0]);
  }

  function sparaKlassen() {
    const namn = $('#elevnamnfalt').value.split('\n')
      .map(s => s.trim()).filter(Boolean);
    if (!namn.length) {
      $('#elevnot').textContent = 'Klistra in klasslistan först — ett namn per rad.';
      return;
    }
    /* Med server men utan grupp: pappret saknar klass, och prototypgrenen
       hade skapat elever med negativa id:n som servern sedan fäller på FK.
       Bättre ett rakt besked än en halvsparad rättning. */
    if (server() && !gruppId) {
      $('#elevnot').textContent =
        'Pappret saknar klass — sätt klassen på pappret och öppna igen.';
      return;
    }
    delete $('#elevklass').dataset.oppen;
    if (!server()) {
      /* Utan server (Claude Design) finns klassen bara i den här sessionen.
         Prototypen ska ändå gå att visa hela vägen. */
      elever = ordnaNamn(namn).map((n, i) => ({ id: -(i + 1), namn: n, aktiv: true }));
      index = 0;
      rita();
      return;
    }
    window.API.json(`/api/groups/${gruppId}/elever`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ namn }),
    }).then(r => {
      elever = (r.elever || []).filter(e => e.aktiv);
      index = 0;
      rita();
      fokusera();
    }).catch(e => {
      $('#elevnot').textContent = (e && e.message) || 'Klassen gick inte att spara.';
    });
  }

  /* Autosparningen vid elevbyte och stängning. Ingen toast, ingen omritning —
     PUT:en är samma idempotenta helstate som Spara-knappens, men svaret får
     inte skrivas tillbaka: hinner läraren klicka medan anropet är ute vore
     ekot äldre än skärmen. Flaggan släcks bara om ingenting hann ändras. */
  function sparaTyst() {
    if (!smutsigt || !server()) return;
    const v = doc, bild = JSON.stringify(resultat);
    window.API.json(vag(v), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resultat }),
    }).then(r => {
      cicache.clear();
      v.rattat = r.rattat || null;
      window.Dokument && window.Dokument.andrad && window.Dokument.andrad(v);
      window.Dokument && window.Dokument.rita && window.Dokument.rita();
      window.Utgang && window.Utgang.rita();
      if (doc === v && JSON.stringify(resultat) === bild) {
        smutsigt = false;
        rakna();
      }
    }).catch(() => {});
  }

  function spara() {
    const v = doc;
    if (!server()) {
      smutsigt = false;
      rakna();
      window.toast && window.toast('Sparat');
      return;
    }
    window.API.json(vag(v), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resultat }),
    }).then(r => {
      /* Profilen är räknad på de sparade raderna — sparas nya siffror är den
         gamla profilen ett svar på en fråga som inte längre gäller. */
      cicache.clear();
      if (doc === v) { las(r); smutsigt = false; rita(); }
      /* Utfallet är fakta om pappret och skrivs rakt på det — «Rättat · NN %»
         på kortet är samma siffra som klassrättningen ger, för det ÄR den. */
      v.rattat = r.rattat || null;
      window.Dokument && window.Dokument.andrad && window.Dokument.andrad(v);
      window.Dokument && window.Dokument.rita && window.Dokument.rita();
      window.Utgang && window.Utgang.rita();
      window.toast && window.toast(
        v.rattat ? `Sparat — klassen tog ${Math.round((v.rattat.andel || 0) * 100)} % av poängen`
          : 'Sparat', 'Ångra', () => {
          v.rattat = null;
          window.Dokument && window.Dokument.andrad && window.Dokument.andrad(v);
          window.Dokument && window.Dokument.rita();
          window.Utgang && window.Utgang.rita();
          window.API.json(vag(v), { method: 'DELETE' }).catch(() => {});
        });
    }).catch(e => {
      /* Ett svalt fel här är en förlorad rättning som SER sparad ut. */
      if (doc === v) $('#elevnot').textContent =
        (e && e.message) || 'Kunde inte spara — siffrorna står kvar, försök igen.';
    });
  }

  function skrivFeedback() {
    if (!server()) return;
    const v = doc;
    const knapp = $('#elevskriv');
    knapp.disabled = true;
    $('#elevnot').textContent = 'Skriver feedback …';
    window.API.strom(`/api/dokument/${v.id}/elevfeedback`, {}, {
      log: m => { $('#elevnot').textContent = m; },
    }).then(r => {
      knapp.disabled = false;
      if (doc !== v) return;
      feedback = Object.assign({}, (r && r.feedback) || {});
      rita();
      $('#elevnot').textContent = 'Feedbacken är skriven — läs igenom och ändra det du vill.';
    }).catch(e => {
      knapp.disabled = false;
      $('#elevnot').textContent = e.message || 'Feedbacken gick inte att skriva.';
    });
  }

  function sparaText() {
    const e = nuvarande();
    if (!e) return;
    const txt = $('#elevtextfalt').value.trim();
    if (txt === (feedback[String(e.id)] || '')) return;
    feedback[String(e.id)] = txt;
    if (!server()) return;
    window.API.json(`/api/dokument/${doc.id}/elevfeedback`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ feedback: { [e.id]: txt } }),
    }).catch(() => {});
  }

  /* ── Prototypens data ─────────────────────────────────────────────────── */

  const LATSASELEVER = ['Alva Nyström', 'Elis Hedlund', 'Freja Lindqvist',
                        'Ivar Sandell', 'Nora Wikström', 'Vidar Åkerlund'];
  const LATSASUPPGIFTER = [
    { nr: 1, t: 'Beräkna arean av triangeln.', p: 2, peca: [2, 0, 0] },
    { nr: 2, t: 'Lös ekvationen och redovisa hela lösningen.', p: 4,
      del: ['enkelt fall', 'fall med x på båda sidor'],
      delpeca: [[2, 0, 0], [0, 2, 0]] },
    { nr: 3, t: 'Avgör om påståendet är sant och motivera.', p: 3, peca: [0, 2, 1] },
    { nr: 4, t: 'Visa att sambandet gäller generellt.', p: 3, peca: [0, 0, 3] },
  ];

  /* ── Modalen ──────────────────────────────────────────────────────────── */

  const tangent = e => {
    if (e.key === 'Escape') {
      /* Escape trappar sig utåt: fältet släpper fokus, klasseditorn stängs,
         modalen sist. En inklistrad klasslista ska inte ryka på en tangent. */
      if (e.target && e.target.tagName === 'TEXTAREA') { e.target.blur(); return; }
      if ($('#elevklass').dataset.oppen && elever.length) {
        delete $('#elevklass').dataset.oppen;
        rita();
        return;
      }
      if (oversikt) { oversikt = false; rita(); fokusera(); return; }
      stang();
      return;
    }
    if (skal.hidden || $('#elevvy').hidden) return;
    if (e.target && e.target.tagName === 'TEXTAREA') return;
    if (e.key === 'Enter') { e.preventDefault(); byt(1); return; }
    /* Pilarna går inom gruppen — Tab går mellan grupperna (roving tabindex i
       ritaRad), så ett femtonradersprov är femton tabtryck, inte femtio. */
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      const grupp = e.target && e.target.closest && e.target.closest('.elevgrupp');
      if (!grupp) return;
      const knappar = [...grupp.querySelectorAll('.elevknapp')];
      const n = knappar[knappar.indexOf(e.target) + (e.key === 'ArrowRight' ? 1 : -1)];
      if (n) { e.preventDefault(); n.focus(); }
      return;
    }
    if (!/^[0-9]$/.test(e.key)) return;
    const grupp = e.target && e.target.closest && e.target.closest('.elevgrupp');
    if (!grupp) return;
    const knapp = grupp.querySelector(`.elevknapp[data-v="${e.key}"]`);
    if (!knapp) return;                     // siffran finns inte på den nivån
    e.preventDefault();
    knapp.click();
  };

  function oppna(v) {
    if (!v) return;
    doc = v;
    granser = null;
    resultat = {}; feedback = {}; index = 0; smutsigt = false; oversikt = false;
    /* Profilen hör till pappret som öppnas — och till kursen det ligger i. */
    cicache.clear();
    civem = 'Eleven';
    /* Prototypens klass visas när det inte finns någon serverväg för DET HÄR
       pappret — designprojektet har ingen server alls, och ett papper utan id
       har ingen rättning att hämta. Modalen ska gå att visa hela vägen ändå. */
    harServer = server();
    const uppg = (v.uppgifter || []).length ? v.uppgifter : LATSASUPPGIFTER;
    rader = window.Rattning && window.Rattning.bygg
      ? window.Rattning.bygg(uppg) : [];
    elever = harServer ? [] : LATSASELEVER.map((n, i) => ({ id: -(i + 1), namn: n, aktiv: true }));
    gruppId = null;
    delete $('#elevklass').dataset.oppen;
    $('#elevnamnfalt').value = elever.map(e => e.namn).join('\n');
    rita();
    hamta();
    skal.hidden = false;
    requestAnimationFrame(() => { skal.setAttribute('data-pa', ''); fokusera(); });
    document.addEventListener('keydown', tangent);
  }

  function stang() {
    if (skal.hidden) return;
    /* Osparat följer med ut — Escape, ✕ och klick utanför ska aldrig kasta en
       kvälls rättning. Utan server finns inget att skriva till; då står
       siffrorna kvar i minnet tills modalen öppnas om. */
    sparaTyst();
    skal.removeAttribute('data-pa');
    setTimeout(() => { skal.hidden = true; }, 220);
    document.removeEventListener('keydown', tangent);
  }

  /* Sista utvägen: stängs hela fliken med osparade poäng får webbläsaren
     fråga. Autosparningen gör att det nästan aldrig händer — nästan. */
  window.addEventListener('beforeunload', e => {
    if (smutsigt && server()) { e.preventDefault(); e.returnValue = ''; }
  });

  skal.addEventListener('click', e => { if (e.target === skal) stang(); });
  $('#elevstang').addEventListener('click', stang);
  $('#elevforra').addEventListener('click', () => byt(-1));
  $('#elevnasta').addEventListener('click', () => byt(1));
  $('#elevspara').addEventListener('click', spara);
  $('#elevskriv').addEventListener('click', skrivFeedback);
  $('#elevsparaklass').addEventListener('click', sparaKlassen);
  $('#elevtom').addEventListener('click', () => {
    const e = nuvarande();
    if (!e) return;
    resultat[String(e.id)] = {};
    smutsigt = true;
    rita();
  });
  $('#elevtextfalt').addEventListener('change', sparaText);
  /* Eleven eller klassen — samma aggregat, olika urval. Klassens svaga punkt
     är underlaget för vad som ska tas om gemensamt i stället för elev för elev. */
  const civaljare = document.querySelector('[data-seg="civem"]');
  if (civaljare) civaljare.addEventListener('click', e => {
    const b = e.target.closest('button');
    if (!b) return;
    civem = b.textContent.trim();
    [...civaljare.querySelectorAll('button')].forEach(
      x => x.setAttribute('aria-pressed', String(x === b)));
    ritaCi();
  });
  $('#elevklassavbryt').addEventListener('click', () => {
    delete $('#elevklass').dataset.oppen;
    rita();
  });
  $('#elevvisaoversikt').addEventListener('click', () => { oversikt = true; rita(); });
  $('#elevoversiktstang').addEventListener('click', () => { oversikt = false; rita(); fokusera(); });
  $('#elevkopiera').addEventListener('click', kopieraOversikt);
  $('#elevbytklass').addEventListener('click', () => {
    $('#elevklass').dataset.oppen = '1';
    $('#elevnamnfalt').value = elever.map(e => e.namn).join('\n');
    rita();
    $('#elevnamnfalt').focus();
  });
  $('#elevtillklass').addEventListener('click', () => {
    const v = doc;
    stang();
    setTimeout(() => window.Rattning && window.Rattning.oppna(v), 60);
  });

  window.Elever = { oppna };
})();
