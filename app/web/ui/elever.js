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
      for (let p = 0; p <= peca[i]; p++) {
        const k = document.createElement('button');
        k.type = 'button';
        k.className = 'elevknapp';
        k.dataset.v = String(p);
        k.textContent = String(p);
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
    $('#elevklass').hidden = harKlass && !redigerar;
    $('#elevvy').hidden = !harKlass || redigerar;
    $('#elevbytklass').hidden = !harKlass || redigerar;
    $('#elevklassavbryt').hidden = !harKlass;
    $('#elevspara').hidden = redigerar;
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

  function satt(r, niva, poang, knapp) {
    const e = nuvarande();
    if (!e) return;
    const v = varden(e);
    const nu = (v[r.nyckel] || [null, null, null]).slice();
    nu[niva] = nu[niva] === poang ? null : poang;   // klick på vald siffra ångrar
    v[r.nyckel] = nu;
    const grupp = knapp.closest('.elevgrupp');
    [...grupp.querySelectorAll('.elevknapp')].forEach(k => {
      if (Number(k.dataset.v) === nu[niva]) k.setAttribute('data-vald', '');
      else k.removeAttribute('data-vald');
    });
    smutsigt = true;
    rakna();
    if (nu[niva] != null) nasta(grupp);
  }

  /* Nästa grupp att fylla i — nästa nivå på raden, annars nästa rads första. */
  function nasta(grupp) {
    const alla = [...skal.querySelectorAll('.elevgrupp')];
    const i = alla.indexOf(grupp);
    const n = alla[i + 1];
    if (n) n.querySelector('.elevknapp').focus();
  }

  function byt(steg) {
    if (!elever.length) return;
    index = (index + steg + elever.length) % elever.length;
    rita();
    const forsta = skal.querySelector('.elevknapp');
    if (forsta) forsta.focus();
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
    }).catch(() => {});
  }

  function sparaKlassen() {
    const namn = $('#elevnamnfalt').value.split('\n')
      .map(s => s.trim()).filter(Boolean);
    if (!namn.length) return;
    delete $('#elevklass').dataset.oppen;
    if (!server() || !gruppId) {
      /* Utan server (Claude Design) finns klassen bara i den här sessionen.
         Prototypen ska ändå gå att visa hela vägen. */
      elever = namn.map((n, i) => ({ id: -(i + 1), namn: n, aktiv: true }));
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
    }).catch(() => {});
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
    if (e.key === 'Escape') { stang(); return; }
    if (skal.hidden || $('#elevvy').hidden) return;
    if (e.target && e.target.tagName === 'TEXTAREA') return;
    if (e.key === 'Enter') { e.preventDefault(); byt(1); return; }
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
    resultat = {}; feedback = {}; index = 0; smutsigt = false;
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
    requestAnimationFrame(() => skal.setAttribute('data-pa', ''));
    document.addEventListener('keydown', tangent);
  }

  function stang() {
    if (skal.hidden) return;
    skal.removeAttribute('data-pa');
    setTimeout(() => { skal.hidden = true; }, 220);
    document.removeEventListener('keydown', tangent);
  }

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
  $('#elevklassavbryt').addEventListener('click', () => {
    delete $('#elevklass').dataset.oppen;
    rita();
  });
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
