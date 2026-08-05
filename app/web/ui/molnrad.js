/* ══════════ MOLNEN I HIMLEN ══════════
   Ett ärvt upplägg, och det som klassminnet fyllde i, är noteringar OM ett steg —
   inte beslut man fattar i det. De hör därför inte hemma i den vita rutan: de
   ligger ute i himlen bredvid, som ett moln med svansen mot stegets blå siffra.

   Placeringen kan inte göras i CSS. Marginalen mellan kortets kant och fönstret
   varierar med bredden, och molnet ska ligga i den marginalen, i höjd med sitt
   steg, utan att klippas av något som rullar. Därför flyttas molnet till <body>
   och sätts med position:fixed mot stegets siffra — och räknas om när sidan
   rullar, när fönstret ändras och när stegen fälls upp och ihop.

   Ryms det inte i himlen (smal skärm) faller molnet tillbaka in i steget. Formen
   är densamma; bara platsen skiljer. */
window.Molnrad = (() => {
  /* Molnet är en bild och rutan är bara dess läsbara mitt (app4.css). Måtten
     nedan är den mittens andel av bilden, räknade om till hur mycket himmel
     molnet behöver: hela bilden är FOT gånger rutans bredd, svansen tar SVANS av
     den till sin sida, och HOJD är den höjd bilden VILL ha vid den bredden — så
     molnet inte sträcks på höjden när texten är kort. STRACK är hur mycket
     bilden får tänjas innan molnet hellre går hem in i steget.

     Måtten gäller 4:3-molnen (assets/moln/*.png, 1600 × 1200). Med dem är HOJD
     0,60 i stället för 0,333 — bilden är dubbelt så hög i förhållande till sin
     bredd som de gamla, och bär därför tre rader i appens vanliga textstorlek.
     MIN 145 är räknad på just det: under den bredden bryts texten till fyra rader
     och molnet skulle behöva tänjas 70 %. Då går det hellre hem in i steget, där
     det får 200 px bredd och sin rätta form. I praktiken: himmel från ~1400 px
     fönsterbredd, steget därunder. */
  const MIN = 145, MAX = 240, LUFT = 8, FOT = 1.72, SVANS = 0.43, HOJD = 0.60, STRACK = 1.45;
  const bubblor = () => [...document.querySelectorAll('.bubbla')];
  const hem = new WeakMap();

  /* Vilket steg molnet talar om. Arvet står i sitt eget steg; minnet gäller det
     steg som är öppet, för förvalen det beskriver används där. */
  function mal(b) {
    if (b.dataset.mal === 'oppet') {
      const panel = document.querySelector('#vy-planering .panel');
      if (!panel) return null;
      return [...panel.querySelectorAll('.plansteg')].filter(s => !s.hidden).pop() || null;
    }
    return hem.get(b) || null;
  }

  /* Ett moln som slutar flyta måste tillbaka dit det hör hemma. Lämnas noden kvar
     som barn till <body> utan data-flyter ritas den som ett löst 340 px moln sist
     i dokumentet, och sidan växer med dess höjd. */
  function hemat(b, steg) {
    b.removeAttribute('data-flyter');
    b.removeAttribute('data-vand');
    /* Hemma hänger molnet till VÄNSTER om siffran — svansen ska peka höger. */
    b.dataset.sida = 'vanster';
    b.style.cssText = '';
    b.style.minHeight = '';
    const bo = steg || hem.get(b) || document.querySelector('#vy-planering .panel');
    /* Hem i ett steg betyder I RUBRIKRADEN — molnet är en notering om just den
       frågan och ska stå bredvid den, i samma höjd. Det får en egen liten yta
       (.molnbo) som ligger absolut i raden: ingen vit lucka i flödet, och både
       det krympta och det utfällda molnet lägger sig över kortet. */
    const rad = bo && bo.classList.contains('plansteg') ? (bo.querySelector('.steghuvud') || bo) : bo;
    if (rad && !(b.parentElement && b.parentElement.classList.contains('molnbo') && b.parentElement.parentElement === rad)) {
      let yta = b.parentElement && b.parentElement.classList.contains('molnbo') ? b.parentElement : null;
      if (!yta) { yta = document.createElement('div'); yta.className = 'molnbo'; yta.appendChild(b); }
      rad.appendChild(yta);
    }
  }

  function placera() {
    const panel = document.querySelector('#vy-planering .panel');
    const kort = panel && panel.closest('.skiva');
    if (!kort) return;
    const kr = kort.getBoundingClientRect();
    /* plats är den KROPPSBREDD som ryms i himlen på var sida — bilden runt
       kroppen är inräknad i FOT. */
    const plats = { vanster: (kr.left - LUFT) / FOT, hoger: (innerWidth - kr.right - LUFT) / FOT };
    const tagna = [];

    bubblor().forEach(b => {
      if (!hem.has(b)) hem.set(b, b.parentElement && b.parentElement.closest('.plansteg'));
      const steg = mal(b);
      /* Molnet talar om DET öppna steget — texten byts när steget byts, och finns
         inget förval i steget finns inget moln. */
      if (b.dataset.mal === 'oppet' && window.Profil && window.Profil.visaFor) window.Profil.visaFor(steg);
      const siffra = steg && steg.querySelector('.stegnr');
      const gomd = b.hasAttribute('hidden') || !siffra || steg.hidden;
      if (gomd) { hemat(b, steg); return; }

      /* Ett moln som pekar på en siffra utanför bild pekar på ingenting. Då tonar
         det ut och tar ingen plats i sidoräkningen — molnet får ALDRIG klämmas in
         eller skjutas undan för att synas, för då lossnar det från sitt steg. */
      const sr = siffra.getBoundingClientRect();
      const synligt = sr.bottom > 72 && sr.top < innerHeight - 40;

      /* Sidorna som har himmel nog, den öppnaste först. */
      const sidor = ['vanster', 'hoger'].filter(s => plats[s] >= MIN).sort((a, z) => plats[z] - plats[a]);
      if (!sidor.length) { hemat(b, steg); return; }
      /* Flyter molnet behövs ingen liten yta i steget längre. */
      const bo = b.parentElement;
      if (b.parentElement !== document.body) document.body.appendChild(b);
      if (bo && bo.classList && bo.classList.contains('molnbo')) bo.remove();
      b.dataset.flyter = '';
      b.style.opacity = synligt ? '1' : '0';
      b.style.pointerEvents = synligt ? '' : 'none';

      /* Höjden följer av siffran: svansen sitter 34 px ner i molnet. Ryms molnet
         inte under siffran vänds det, så svansen hamnar vid nederkanten i
         stället — aldrig en klämning, för då lossnar svansen från sitt steg. */
      const mitt = sr.top + sr.height / 2;
      const lagg = () => {
        const h = b.offsetHeight || 120;
        /* Bilden sticker ut ÖVER och UNDER rutan (top/bottom -54 % i app4.css) —
           det är bulorna och den plattade underkanten. Klämmer man rutan mot
           fönsterkanten kapas kronan, så det är BILDENS kant som ska hållas inne.
           Svansen är målad på bildens lodräta mitt: kroppens mitt ska ligga i
           siffrans höjd, inte 34 px ner som när svansen var ritad. */
        const utanfor = Math.round(h * 0.54) + 8;
        const golv = Math.min(utanfor, Math.max(16, innerHeight - h - utanfor));
        return { h, vand: false, topp: Math.max(golv, Math.min(innerHeight - h - utanfor, Math.round(mitt - h / 2))) };
      };
      let { h, vand, topp } = lagg();
      const krock = (s, t, hojd) => tagna.some(x => x.sida === s && t < x.slut + 14 && t + hojd > x.topp - 14);

      /* Möts två moln byter det andra SIDA i första hand — att skjuta det nedåt
         vore att flytta det bort från siffran det pekar på. Först när ingen sida
         är fri skjuts det i höjdled. */
      const sida = sidor.find(s => !krock(s, topp, h)) || sidor[0];
      b.dataset.sida = sida;
      const bredd = Math.round(Math.max(MIN, Math.min(MAX, plats[sida])));
      b.style.width = bredd + 'px';
      /* Kroppen är minst så hög som bilden vill vara — kort text sträcker då
         inte ut molnet på höjden. */
      b.style.minHeight = Math.round(bredd * HOJD) + 'px';
      /* Svansen slutar LUFT från kortets kant: kroppens ytterkant flyttas in
         svansens bredd. */
      b.style.left = sida === 'vanster'
        ? Math.round(kr.left - LUFT - bredd * (1 + SVANS)) + 'px'
        : Math.round(kr.right + LUFT + bredd * SVANS) + 'px';
      /* Ingen del av bilden får hamna utanför fönstret på andra sidan. */
      if (sida === 'vanster') b.style.left = Math.max(Math.round(bredd * 0.2), parseInt(b.style.left, 10)) + 'px';
      ({ h, vand, topp } = lagg());
      /* Molnet är ett foto — det tål att töjas några procent, inte att bli fyrkantigt.
         Behöver texten mer höjd än bilden vill ha vid den bredden går molnet hem in
         i steget i stället, där det får hela sin bredd och sin rätta form. */
      if (h > bredd * HOJD * STRACK) { hemat(b, steg); return; }
      b.toggleAttribute('data-vand', vand);
      if (synligt) {
        if (krock(sida, topp, h)) topp = Math.max(...tagna.filter(x => x.sida === sida).map(x => x.slut)) + 14;
        tagna.push({ sida, topp, slut: topp + h });
      }
      b.style.top = topp + 'px';
    });
  }

  let vantar = false;
  /* requestAnimationFrame stannar i en flik som inte ritas — och då fastnar
     vantar på true och molnet placeras aldrig mer. En timeout som backup gör
     att placeringen alltid blir av, i förgrunden på nästa bildruta. */
  const om = () => {
    if (vantar) return;
    vantar = true;
    let gjort = false;
    const kor = () => { if (gjort) return; gjort = true; vantar = false; placera(); };
    requestAnimationFrame(kor);
    setTimeout(kor, 140);
  };
  addEventListener('scroll', om, { passive: true });
  addEventListener('resize', om);
  const vakt = new MutationObserver(om);
  const start = () => {
    const panel = document.querySelector('#vy-planering .panel');
    if (panel) vakt.observe(panel, { attributes: true, attributeFilter: ['hidden'], subtree: true, childList: true });
    document.querySelectorAll('.bubbla').forEach(b => vakt.observe(b, { attributes: true, attributeFilter: ['hidden'] }));
    om();
  };
  if (document.readyState === 'loading') addEventListener('DOMContentLoaded', start);
  else start();
  /* Nya moln ritas av profil.js efter att sidan startat. */
  setInterval(om, 1200);

  return { placera: om };
})();
