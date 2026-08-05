/* ══════════ MOLNET ══════════
   Språkmodellsarbetet ligger hos Claude Code, ljudet stannar här. Tre saker:
   härkomstraden vid knappen som skickar, listan över vad som faktiskt går ut,
   och tillståndet «Claude Code saknas eller är inte inloggad» — som aldrig får
   bli en tyst tom utdata mitt i en förberedelse. */
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
    poster.push(['Stannar', 'Ljudfilerna, videon, boksidornas foton och alla tidsstämplar', false]);
    lista.innerHTML = poster.map(p => rad(p[0], p[1], p[2])).join('') +
      '<p class="harfot">Går till Anthropic via Claude Code på din prenumeration. Svaret sparas här och skickas inte vidare.</p>';
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
       i «Var arbetet körs» och vid knappen som inte går att trycka. ── */
  let ansluten = true;
  const skriv = $('#skriv');
  function sattLage() {
    const s = $('#claudestatus');
    if (s) {
      s.textContent = ansluten ? 'ansluten' : 'inte inloggad';
      s.toggleAttribute('data-fel', !ansluten);
    }
    const fel = $('#claudefel');
    if (fel) fel.hidden = ansluten;
    const byt = $('#claudebyt');
    if (byt) byt.textContent = ansluten ? 'Simulera utloggad' : 'Simulera inloggad';
    const har = $('#harkomst-plan');
    if (har) {
      const t = har.querySelector('.hartext');
      t.innerHTML = ansluten
        ? '<b>Texten skickas till Claude</b> · ljudet stannar på datorn'
        : '<b>Claude Code är inte inloggat</b> · transkribering och ljudrättning påverkas inte';
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
  if (igen) igen.addEventListener('click', () => { ansluten = true; sattLage(); window.toast && window.toast('Claude Code är inloggad'); });

  window.Moln = { get ansluten() { return ansluten; } };
})();
