/* ══════════ PRICKARNA — markeringen som lugnar sig ══════════
   `.andrad` sätts av blad.js på de element servern säger sig ha skrivit om
   (app/dokumentdiff.py). Markeringen blinkade tre gånger och låg sedan kvar
   för evigt: läraren som skrivit om fem saker satt till slut med ett papper
   där halva ytan lyste, och kunde inte längre se vilken ändring som var den
   nya. Ett papper där allt är markerat säger lika lite som ett omarkerat.

   Så här ser varvet ut nu:

   1. Några sekunder med den tydliga markeringen — det är den man ser i
      ögonvrån och som säger «här hände det».
   2. Sedan krymper den till en PRICK i elementets kant. Övergången är en
      CSS-transition på `[data-lugn]`, och attributet sätts av en timer här —
      inte av animationens slut. Testerna kan då fråga efter tillståndet i
      stället för att vänta ut en tid.
   3. Hovra pricken → före/efter i en bubbla. Paret kommer från granskningen
      (window.Granska.diffFor) — samma kapade text som `.gdiff` i panelen, för
      en prick som säger något annat än panelen vore värre än ingen prick.
   4. Klicka pricken → panelen hoppar till varvets rad.

   Att tiden räknas från `v.andradVid` och inte från renderingen är med flit:
   pappret ritas om vid zoom, versionsbyten och när typsnitten är inne. Räknade
   vi från renderingen skulle markeringen blossa upp igen varje gång, och ett
   varv man tittat på i en minut skulle se nytt ut. Bläddrar läraren tillbaka
   till ett äldre varv står dess prickar därför lugna direkt.

   Bilden och utskriften bär inga prickar: `@media print` gömmer dem, och
   bildproducenterna (tavla-bild.js, blad-bild.js) river dem ur sin kopia. Ett
   papper som kommer ur skrivaren är lärarens, inte appens anteckningsbok. */
window.Prickar = (() => {
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));

  /* Hur länge den tydliga markeringen står. Fyra sekunder är lagom för att
     hinna hitta den utan att den blir en flagga man slutar se. */
  const LUGN_MS = 4000;

  let bubbla = null;

  function bubblan() {
    if (bubbla) return bubbla;
    bubbla = document.createElement('div');
    bubbla.className = 'aprickbubbla gdiff';
    bubbla.hidden = true;
    /* På <body> och inte inne i elementet: canvasen står i en egen
       transform-skala, och en bubbla inne i pappret hade krympt med zoomen
       till oläslighet. */
    document.body.appendChild(bubbla);
    return bubbla;
  }

  function visaBubbla(prick) {
    const par = window.Granska && window.Granska.diffFor
      ? window.Granska.diffFor(prick.dataset.prick) : null;
    const b = bubblan();
    if (!par || (!par.fore && !par.efter)) { b.hidden = true; return; }
    b.innerHTML = '<p style="margin:0"><span class="gfore"></span><span class="gefter"></span></p>';
    $('.gfore', b).textContent = par.fore;
    $('.gefter', b).textContent = par.efter;
    b.hidden = false;
    /* Mätt mot skärmen, inte mot pappret — se kommentaren vid bubblan(). */
    const r = prick.getBoundingClientRect();
    const bb = b.getBoundingClientRect();
    const x = Math.min(Math.max(8, r.left + r.width / 2 - bb.width / 2),
                       window.innerWidth - bb.width - 8);
    /* Ovanför pricken när det finns plats, annars under — en bubbla som hamnar
       utanför rutan är en bubbla man inte läser. */
    const over = r.top - bb.height - 10;
    b.style.left = x + 'px';
    b.style.top = (over > 8 ? over : r.bottom + 10) + 'px';
  }

  function doljBubbla() {
    if (bubbla) bubbla.hidden = true;
  }

  function prick(elId) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'aprick';
    /* `data-prick` och INTE `data-el`: granskningen sveper över
       `.gdok [data-el]` både när den tar sin ögonblicksbild och när den letar
       upp ett element att sätta en nål på. En prick med `data-el` blev en
       andra, tom «tav0» i den bilden — och diffen läste den tomma. */
    b.dataset.prick = elId || '';
    /* Ingen textnod heller, av samma skäl: `ogonblick()` läser textContent, och
       ett ord här hade blivit en «ändring». */
    b.setAttribute('aria-label', 'Visa ändringen');
    b.addEventListener('pointerenter', () => visaBubbla(b));
    b.addEventListener('focus', () => visaBubbla(b));
    b.addEventListener('pointerleave', doljBubbla);
    b.addEventListener('blur', doljBubbla);
    b.addEventListener('click', e => {
      e.stopPropagation();          // inte ett elementval — ett hopp i listan
      doljBubbla();
      const g = window.Granska;
      if (g && g.visaVarv) g.visaVarv(g.senasteVarv);
    });
    return b;
  }

  /* Sätt prickar på det som är markerat i `rot`, och starta lugnandet.
     Anropas av blad.js efter att markeringarna satts — både på pappret och på
     tavlan. */
  function pa(rot, v) {
    if (!rot) return;
    $$('.andrad', rot).forEach(el => {
      /* Tiden stämplas PÅ elementet: canvasen visar en KLON av pappret, och
         cloneNode kopierar attribut men varken timers eller lyssnare. Utan
         stämpeln stod klonens markering tydlig för evigt — originalet lugnade
         sig bakom överlägget medan läraren såg på klonen. Granskningen ropar
         pa(klon) utan version; då räknas resttiden ur stämpeln i stället. */
      if (v && v.andradVid) el.dataset.andradVid = v.andradVid;
      const vid = (v && v.andradVid) || Number(el.dataset.andradVid) || 0;
      const gatt = vid ? Date.now() - vid : LUGN_MS;
      /* En medklonad prick är en död knapp — byt den mot en levande. */
      const gammal = $(':scope > .aprick', el);
      if (gammal) gammal.remove();
      el.appendChild(prick(el.dataset.el));
      if (gatt >= LUGN_MS) { el.setAttribute('data-lugn', ''); return; }
      el.removeAttribute('data-lugn');
      /* Noden kan vara borta när timern går — då gör setAttribute ingenting,
         och det är hela städningen som behövs. */
      setTimeout(() => el.setAttribute('data-lugn', ''), LUGN_MS - gatt);
    });
  }

  /* Riv markeringarna ur en KOPIA av pappret. Bildproducenterna serialiserar
     sin klon rakt in i ett <foreignObject>, och app2.css följer inte med dit —
     en kvarglömd prick hade blivit en ostylad liten knapp mitt i PDF:en. */
  function riv(kopia) {
    if (!kopia) return kopia;
    $$('.aprick', kopia).forEach(p => p.remove());
    /* Roten själv också: klonas EN ruta (som canvasens element) är det den som
       bär `.andrad`, och den fångas inte av en sökning bland barnen. */
    [kopia].concat($$('.andrad', kopia)).forEach(el => {
      if (!el.classList) return;
      el.classList.remove('andrad');
      el.removeAttribute('data-lugn');
      el.removeAttribute('data-andrad-vid');
    });
    return kopia;
  }

  return { pa, riv, LUGN_MS };
})();
