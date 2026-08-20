/* ══════════ BÖRJA OM ══════════
   En väg tillbaka till tomt bord. Planeringen minns mycket med flit — klass,
   kurs, dag, källor, moment — och just därför behövs en enda knapp som släpper
   allt och lämnar en på första steget. Den står tyst ovanför stapeln och blir bara
   framträdande när det faktiskt finns något att rensa. */
(() => {
  const q = (s, r = document) => r.querySelector(s);
  const qq = (s, r = document) => [...r.querySelectorAll(s)];
  const panel = q('#vy-planering .panel');
  if (!panel) return;

  const rad = document.createElement('div');
  rad.className = 'omstartrad';
  rad.innerHTML = '<button class="lank omstartknapp" type="button" data-tip="Rensa allt och börja om">Börja om</button>';
  panel.insertBefore(rad, panel.firstChild);
  const knapp = q('.omstartknapp', rad);

  const harNagot = () =>
    !!(qq('#valdalektioner .lchip').length
      || q('#sidminis') && q('#sidminis').children.length
      || (q('#moment') || {}).value
      || (q('#p-klass') || {}).value
      || (q('#planvald') && !q('#planvald').hidden)
      || (window.PlanKo && window.PlanKo.valda && window.PlanKo.valda().length));

  function spegla() { rad.toggleAttribute('data-aktiv', harNagot()); }

  function rensa() {
    /* Underlaget: dörrar av, valda lektioner och sidor bort, förlagan släppt.
       «sparat» hörde hit lika mycket som de tre andra — utan den stod dörren
       «Ett tidigare papper» kvar påslagen efter att allt annat rensats. */
    if (window.Kallor) ['lektion', 'bok', 'foton', 'sparat'].forEach(d => window.Kallor.satt(d, false, true));
    qq('#valdalektioner .lchip').forEach(c => c.click());
    qq('#sidminis .sidbort').forEach(b => b.click());
    /* Utkastet hörde hit lika mycket som källorna och lektionen: «Allt rensat»
       lämnade pappret liggande i rutan, och eftersom utkastet plockas upp igen
       vid varje laddning var det tillbaka nästa gång appen öppnades — efter att
       läraren uttryckligen bett om ett tomt bord. Tyst slängning: rensningen
       har en egen toast, och den säger det i stället.
       Men den ska ha en väg tillbaka. Varje annan slängning i appen bär Ångra;
       den här var den enda som var slutgiltig — ett felklick på «Börja om» tog
       pappret och hela dess ångra-historik för gott. `slangUtkast` lämnar
       tillbaka återställningen, och den hängs i rensningens egen toast. */
    const slangt = window.Dokument && window.Dokument.slangUtkast
      ? window.Dokument.slangUtkast(true) : false;
    if (window.Dokument && window.Dokument.slappForlaga) window.Dokument.slappForlaga();
    if (window.Dokument && window.Dokument.slappFoljd) window.Dokument.slappFoljd();
    if (window.Dokument && window.Dokument.slappOmprov) window.Dokument.slappOmprov();
    if (window.Klass && window.Klass.slappOmprov) window.Klass.slappOmprov();
    window.SlappAndraHand && window.SlappAndraHand();
    /* Steg 1 hör också till det som rensas: skrev man ett par stod «Gruppuppgift»
       kvar markerad efter «Börja om», och nästa planering började i förra
       rundans val i stället för på förvalet. */
    window.SattLage && window.SattLage('Tavla');
    const m = q('#moment');
    if (m) { m.value = ''; m.removeAttribute('data-gissad'); m.dispatchEvent(new Event('input', { bubbles: true })); }

    /* Minnesraden och de punkter appen själv satte hör till den släppta planeringen. */
    window.Profil && window.Profil.slapp && window.Profil.slapp(true);

    /* Lektionen: kön tömd, klass, kurs och dag glömda. */
    if (window.PlanKo && window.PlanKo.avbryt) window.PlanKo.avbryt();
    ['#p-klass', '#p-kurs', '#p-datum', '#p-tid'].forEach(s => {
      const f = q(s);
      if (f) { f.value = ''; f.dispatchEvent(new Event('change', { bubbles: true })); }
    });
    const pv = q('#planvald');
    if (pv) { pv.hidden = true; pv.textContent = ''; }
    const pi = q('#planingen');
    if (pi) pi.hidden = false;

    window.Utgang && window.Utgang.rita();
    window.PlanSteg && window.PlanSteg.omstart();
    spegla();
    /* Slängningen sägs bara när det fanns något att slänga — annars påstår
       toasten att ett papper försvann som aldrig låg framme. Ångra-knappen
       lägger tillbaka just pappret; det övriga (klass, källor, moment) är redan
       rensat och det var det knappen hette. Därför «Ångra utkastet» och inte
       «Ångra» — den ska inte lova mer än den gör. */
    if (slangt) {
      window.toast && window.toast(
        'Allt rensat — utkastet är slängt, välj lektionen i veckan igen',
        'Ångra utkastet', slangt);
    } else {
      window.toast && window.toast('Allt rensat — välj lektionen i veckan igen');
    }
  }

  knapp.addEventListener('click', rensa);
  ['#valdalektioner', '#sidminis'].forEach(s => {
    const el = q(s);
    if (el) new MutationObserver(spegla).observe(el, { childList: true });
  });
  const kl = q('#p-klass');
  if (kl) kl.addEventListener('change', spegla);
  const grid = q('#schemagrid');
  if (grid) grid.addEventListener('click', () => setTimeout(spegla, 80), true);
  spegla();
})();
