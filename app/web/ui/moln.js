/* ══════════ MOLNET ══════════
   Två hus utanför datorn, inte ett: ljudet transkriberas hos OpenAI
   (gpt-transcribe) och språkmodellsarbetet görs av Claude Code hos Anthropic.
   Tidsstämplarna och alla filer ligger kvar här.

   Tre saker: härkomstraden vid knappen som skickar, listan över vad som
   faktiskt går ut, och tillståndet «Claude Code saknas eller är inte inloggad» —
   som aldrig får bli en tyst tom utdata mitt i en förberedelse.

   Texten här är ett löfte till läraren. Den fick inte stå kvar som den var: förr
   påstod raden att ljudfilerna aldrig lämnar datorn, och det slutade vara sant
   den dagen transkriberingen flyttade till molnet. */
(() => {
  const $ = s => document.querySelector(s);
  const rad = (nyckel, varde, ut = true) =>
    `<div class="harpost"${ut ? '' : ' data-ut="nej"'}><span class="harnyckel">${nyckel}</span><span class="harvarde"></span></div>`;

  /* ── Vad skickas? Räknas ur formuläret varje gång, aldrig en generell text ── */
  function bygg() {
    const lista = $('#harlista');
    if (!lista) return;
    const moment = ($('#moment') || {}).value || '';
    const kurs = ($('#p-kurs') || {}).value || '';
    const valda = [...document.querySelectorAll('#valdalektioner .lchip span')].map(s => s.textContent);
    const sidor = document.querySelectorAll('#sidminis > *').length;
    const poster = [];
    if (valda.length) poster.push(['Går ut', `Transkript ur ${valda.length} ${valda.length === 1 ? 'lektion' : 'lektioner'} — ${valda.join(' · ')}. Elevnamn kan förekomma.`, true]);
    if (moment.trim()) poster.push(['Går ut', `Momentet du skrev: ”${moment.trim()}”`, true]);
    if (kurs) poster.push(['Går ut', `${kurs}: centralt innehåll och senast godkända upplägg`, true]);
    if (sidor) poster.push(['Går ut', `Tolkningen av ${sidor} inlästa boksidor — som text, inte som bild`, true]);
    /* Ljudet gick ut vid transkriberingen, inte här. Det står med ändå: läraren
       ska kunna läsa hela sanningen om en lektion på ett ställe. */
    poster.push(['Gick ut', 'Ljudet, när lektionen transkriberades — till OpenAI', true]);
    poster.push(['Stannar', 'Ljudfilerna och videon på disken, boksidornas foton och bilden ur videon', false]);
    lista.innerHTML = poster.map(p => rad(p[0], p[1], p[2])).join('') +
      '<p class="harfot">Texten går till Anthropic via Claude Code på din prenumeration. Ljudet gick till OpenAI. Svaren sparas här och skickas inte vidare.</p>';
    [...lista.querySelectorAll('.harvarde')].forEach((el, i) => { el.textContent = poster[i][1]; });
  }

  const knapp = $('#harvad');
  if (knapp) {
    knapp.addEventListener('click', () => {
      const oppen = knapp.getAttribute('aria-expanded') === 'true';
      if (!oppen) bygg();
      knapp.setAttribute('aria-expanded', String(!oppen));
      knapp.textContent = oppen ? 'Vad skickas?' : 'Dölj';
      $('#harlista').hidden = oppen;
    });
  }

  /* ── Claude Code: ansluten eller inte. Beskedet finns på två ställen —
       i «Var arbetet körs» och vid knappen som inte går att trycka.

       Med server kommer läget från /api/var-kors (claude auth status). Utan
       server finns knappen «Simulera utloggad» kvar, så att tillståndet går att
       visa i designen utan att logga ut på riktigt. ── */
  let ansluten = true;
  let epost = '';
  const skriv = $('#skriv');
  function sattLage() {
    const s = $('#claudestatus');
    if (s) {
      s.textContent = ansluten ? (epost ? 'ansluten som ' + epost : 'ansluten') : 'inte inloggad';
      s.toggleAttribute('data-fel', !ansluten);
    }
    const fel = $('#claudefel');
    if (fel) fel.hidden = ansluten;
    const byt = $('#claudebyt');
    if (byt) {
      byt.hidden = !!(window.API && window.API.pa);
      byt.textContent = ansluten ? 'Simulera utloggad' : 'Simulera inloggad';
    }
    const har = $('#harkomst-plan');
    if (har) {
      const t = har.querySelector('.hartext');
      t.innerHTML = ansluten
        ? '<b>Texten skickas till Claude</b> · det här steget skickar inget ljud'
        : '<b>Claude Code är inte inloggat</b> · transkriberingen påverkas inte, den körs hos OpenAI';
      har.querySelector('.harprick').toggleAttribute('data-ut', true);
    }
    if (skriv) {
      skriv.toggleAttribute('data-molnlast', !ansluten);
      if (!ansluten) skriv.disabled = true;
      else if (window.planKoll) window.planKoll();
    }
    const not = $('#plannot');
    if (not && !ansluten) not.textContent = 'Claude Code är inte inloggat — kör claude login i en terminal och kontrollera igen.';
    else if (not && window.planKoll) window.planKoll();
  }
  const byt = $('#claudebyt');
  if (byt) byt.addEventListener('click', () => { ansluten = !ansluten; sattLage(); });
  const igen = $('#claudeigen');
  if (igen) igen.addEventListener('click', async () => {
    if (window.API && window.API.pa) {
      try {
        const s = await window.API.json('/api/claude/kontrollera', { method: 'POST' });
        ansluten = !!s.inloggad;
        epost = s.epost || '';
        sattLage();
        window.toast && window.toast(ansluten ? 'Claude Code är inloggad' : s.fel);
        return;
      } catch (e) { /* servern svarade inte — falla tillbaka nedan */ }
    }
    ansluten = true;
    sattLage();
    window.toast && window.toast('Claude Code är inloggad');
  });

  document.addEventListener('api-redo', () => {
    const v = window.API.varKors;
    if (!v) return;
    ansluten = !!v.moln.sprakmodell.inloggad;
    epost = v.moln.sprakmodell.epost || '';
    sattLage();
  });

  window.Moln = { get ansluten() { return ansluten; }, sattLage };
})();
