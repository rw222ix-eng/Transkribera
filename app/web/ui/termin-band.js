/* ══════════ TERMINEN · RIKTNING 1 · BANDET ══════════
   Hela terminen på en rad: en ruta per vecka, fylld så högt som veckan har
   material. En tom ruta är en lucka, en streckad är ett lov, en röd ring är ett
   prov. Ingenting behöver räknas — man ser var hålen är, och klickar sig dit.

   Fyllnadshöjden är ett tal man inte behöver läsa: tre av fem lektioner ger en
   ruta som är tre femtedelar full. Det är samma mätning som förr stod som
   «2 av 85 lektioner har material», men i en form som svarar på frågan.

   Klick på en vecka går tillbaka till veckoläget, i den veckan. */
window.TerminBand = (() => {
  const $ = (s, r = document) => r.querySelector(s);

  function rita(m, ctx) {
    const { K, visa, tillstand, nationelltI, luckvar, kortDatum } = ctx;
    const el = document.createElement('div');
    el.className = 'tbandvy';

    const nat = document.createElement('div');
    nat.className = 'tbnat';
    nat.style.setProperty('--n', String(Math.max(1, m.rader.length)));
    /* Veckor efter att boken tagit slut har ingen räknad fortsättning — de står
       kvar som veckor, men veckonumret är tystare, för det finns inget avsnitt
       att lägga där. */
    const efter = m.prognos.bokenSlut && m.prognos.slutVecka ? m.prognos.slutVecka : '';

    m.rader.forEach(r => {
      const tl = tillstand(r);
      if (tl === 'lov') {
        const d = document.createElement('div');
        d.className = 'tblov';
        d.innerHTML = '<span class="tbnr"></span><span class="tblovruta">lov</span>';
        $('.tbnr', d).textContent = 'v' + r.nr;
        d.dataset.tip = `v${r.nr} · ${r.lov.map(x => x.namn).join(' · ')}`;
        nat.appendChild(d);
        return;
      }
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'tbv';
      b.dataset.mandag = r.mandag;
      if (r.nu) b.setAttribute('data-nu', '');
      if (r.forbi) b.setAttribute('data-forbi', '');
      if (efter && r.mandag > efter) b.setAttribute('data-efter', '');
      const del = r.lekt.length ? Math.round(r.klara / r.lekt.length * 100) : 0;
      const pr = r.prov[0];
      b.innerHTML = `<span class="tbnr"></span><span class="tbruta"${pr ? (nationelltI(r) ? ' data-nat' : ' data-prov') : ''}><span class="tbfyll" style="height:${del}%"></span></span>`;
      $('.tbnr', b).textContent = 'v' + r.nr;
      /* Titeln är en fördjupning, aldrig det enda stället svaret står: rutan,
         fyllningen och ringen går att läsa av utan att musen står still. */
      const vad = !r.lekt.length ? 'inga lektioner'
        : tl === 'klar' ? `alla ${r.lekt.length} lektionerna har material`
          : tl === 'lucka' ? `${r.lekt.length === 1 ? 'lektionen' : `alla ${r.lekt.length} lektionerna`} saknar material`
            : `${r.klara} av ${r.lekt.length} lektioner har material`;
      b.dataset.tip = `v${r.nr} · ${kortDatum(r.fran)}–${kortDatum(r.till)} — ${vad}${pr ? ` · ${pr.nationellt ? 'nationellt prov' : pr.skrivet ? 'prov, skrivet' : 'prov, inte skrivet'}` : ''}`;
      b.addEventListener('click', () => visa('vecka', r.mandag));
      nat.appendChild(b);
    });
    el.appendChild(nat);

    const fot = document.createElement('div');
    fot.className = 'tbfot';
    const svar = document.createElement('p');
    svar.className = 'tbsvar';
    svar.innerHTML = luckvar(m);
    fot.appendChild(svar);
    /* Tre tecken i legenden, inte fem: lovet säger sitt namn i rutan (LOV), och
       provets två slag är samma tecken med och utan streck — alltså en rad. */
    const leg = document.createElement('p');
    leg.className = 'tblegend';
    leg.innerHTML = `<span><i class="tbprick" data-full></i>har material</span>
      <span><i class="tbprick" data-tom></i>lucka</span>
      <span><i class="tbprick" data-prov></i>prov · streckat: nationellt</span>`;
    fot.appendChild(leg);
    el.appendChild(fot);
    return el;
  }
  return { rita };
})();
