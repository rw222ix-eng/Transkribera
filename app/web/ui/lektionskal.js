/* ══════════ LEKTIONERNA I TIDEN ══════════
   «Förra lektionen» sa förr bara «1 lektion i vecka 24». Ett veckonummer är
   ingen tidpunkt man känner igen. Här är samma vecka som resten av appen visar,
   fast i litet och bara för den klass planeringen gäller: fem dagar, klassens
   lektioner som brickor, och på varje bricka syns om lektionen är transkriberad
   eller inte.

   Brickan ÄR valet. En transkriberad lektion går att klicka på och klicka bort
   igen — därför behövs ingen «välj en annan lektion»-lista under kalendern.
   En lektion utan transkription står kvar men är blek och död: det finns inget
   att utgå från i den. */
(() => {
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => [...(r || document).querySelectorAll(s)];
  const kropp = $('.kpanel[data-panel="lektion"] .kpkropp');
  const K = window.Kalender;
  if (!kropp || !K) return;

  const start = t => String(t || '').split('–')[0].split('-')[0].trim();
  const klassen = () => ($('#p-klass') || {}).value || '';
  const vald = namn => !!(window.Dokument && window.Dokument.harLektion && window.Dokument.harLektion(namn));

  /* Inspelningarna är facit på vad som finns transkriberat. De knyts till
     lektionen på datum + klass, och på klockslag när båda har ett. */
  function inspelningar() {
    return $$('#inspelningar .kort').map(kort => ({
      namn: ($('.namn', kort) || {}).textContent ? $('.namn', kort).textContent.trim() : '',
      klass: kort.dataset.klass || '',
      datum: kort.dataset.datum || '',
      tid: start(kort.dataset.tid || ''),
      langd: ($('.tumtid', kort) || {}).textContent || ''
    })).filter(l => l.namn && l.datum);
  }
  /* En inspelning hör till EN lektion. Utan den här paren skulle en inspelning
     utan klockslag matcha varje lektion samma dag, och en hel dag såg vald ut. */
  function para(insp, dagar) {
    const par = new Map();
    const tagna = new Set();
    const sok = (d, s, exakt) => insp.find(x => !tagna.has(x) && x.datum === d.datum
      && (!x.klass || !s.klass || x.klass === s.klass)
      && (!exakt || !x.tid || !start(s.tid) || x.tid === start(s.tid)));
    /* Två varv: först klockslag mot klockslag, sedan resten mot dagens lediga
       lektioner. Annars tappas en inspelning vars tid inte står i schemat. */
    [true, false].forEach(exakt => dagar.forEach(d => d.lekt.forEach(s => {
      if (par.has(s)) return;
      const i = sok(d, s, exakt);
      if (i) { tagna.add(i); par.set(s, i); }
    })));
    return par;
  }

  const el = document.createElement('div');
  el.className = 'minivecka';
  el.id = 'lektionskal';
  kropp.insertBefore(el, $('#lektionsvalj'));

  let mandag = null;

  /* 42:11 läses som ett klockslag. «42 min 11 s» läses som en längd. */
  const langden = t => {
    const m = String(t || '').match(/(\d{1,2})[:.](\d{2})/);
    return m ? `${+m[1]} min ${+m[2]} s` : String(t || '');
  };
  /* Överraden på den valda lektionen: veckodag, datum, veckonummer, längd. */
  function metaFor(i) {
    if (!i) return '';
    const x = new Date(String(i.datum) + 'T12:00:00');
    const dag = isNaN(x) ? '' : x.toLocaleDateString('sv-SE', { weekday: 'long' });
    return [
      dag ? dag.charAt(0).toUpperCase() + dag.slice(1) : '',
      K.ord ? K.ord(i.datum) : i.datum,
      K.veckonr ? 'v' + K.veckonr(i.datum) : '',
      langden(i.langd)
    ].filter(Boolean).join(' · ');
  }

  /* Kalendern öppnar där lektionen ligger — inte i den vecka man råkade lämna. */
  function hemvecka(insp, kl) {
    const mina = insp.filter(i => !kl || i.klass === kl);
    const valdIn = mina.filter(i => vald(i.namn)).sort((a, z) => a.datum.localeCompare(z.datum)).pop();
    const senast = mina.slice().sort((a, z) => a.datum.localeCompare(z.datum)).pop();
    const d = (valdIn || senast || {}).datum || K.idag();
    return K.mandagen(d);
  }

  /* Veckobytet ska kännas som att bläddra — samma glid som schemat högst upp:
     veckan glider ut åt det håll man lämnar och nästa kommer in från andra sidan. */
  let byter = false;
  function byt(steg, tillDatum) {
    if (byter || !steg) return;
    byter = true;
    const ut = steg > 0 ? -1 : 1;
    const nat = $('.mvnat', el), huvud = $('.mvmitt', el);
    if (!nat) { mandag = tillDatum; rita(); byter = false; return; }
    nat.style.transition = 'opacity 170ms var(--ease),transform 170ms var(--ease)';
    nat.style.opacity = '0';
    nat.style.transform = `translateX(${ut * 24}px)`;
    if (huvud) { huvud.style.transition = 'opacity 170ms var(--ease)'; huvud.style.opacity = '0'; }
    setTimeout(() => {
      mandag = tillDatum;
      rita();
      const ny = $('.mvnat', el);
      if (!ny) { byter = false; return; }
      ny.style.transition = 'none';
      ny.style.opacity = '0';
      ny.style.transform = `translateX(${-ut * 24}px)`;
      setTimeout(() => {
        ny.style.transition = 'opacity 300ms var(--ease),transform 300ms var(--ease)';
        ny.style.opacity = '1';
        ny.style.transform = 'none';
        const h = $('.mvmitt', el);
        if (h) h.style.opacity = '1';
      }, 20);
      setTimeout(() => { byter = false; }, 330);
    }, 175);
  }

  /* «Idag» pekar ut DAGEN, inte bara veckan: ringen pulserar två gånger och är
     sedan borta — ett svar på «var är jag?», inte ett nytt tillstånd. */
  function pulseraIdag() {
    setTimeout(() => {
      const kol = $('.mvdag[data-idag]', el);
      if (!kol) return window.toast && window.toast('Ingen av dagens lektioner ligger i den här veckan');
      kol.removeAttribute('data-idagpuls');
      void kol.offsetWidth;
      kol.setAttribute('data-idagpuls', '');
      setTimeout(() => kol.removeAttribute('data-idagpuls'), 3100);
    }, 40);
  }

  function rita() {
    const kl = klassen();
    const insp = inspelningar();
    if (!mandag) mandag = hemvecka(insp, kl);
    const bild = K.veckoBild(mandag);
    const nu = K.idag();

    /* Klockslagen först: paren ska bli desamma som ögat gör när det läser dagen
       uppifrån och ner. */
    const dagar = bild.dagar.slice(0, 5).map(d => ({
      datum: d.datum,
      lov: d.lov,
      lekt: (d.lov ? [] : d.schema.filter(s => !kl || s.klass === kl))
        .slice().sort((a, z) => start(a.tid).localeCompare(start(z.tid)))
    }));
    const par = para(insp, dagar);

    let antalTr = 0, antalLekt = 0;
    const valda = [];
    /* Har klassen två kurser i veckan är tiden inte nog för att veta vilken lektion
       man pekar på — då ska kursen stå på brickan. Har den bara en är den underförstådd
       av «Lektioner med 9B», och en upprepning per bricka är bara brus. */
    const kurser = [...new Set(dagar.flatMap(d => d.lekt.map(s => s.kurs).filter(Boolean)))];
    const flerKurser = kurser.length > 1;
    const kortkurs = s => String(s || '').replace('Matematik ', 'Ma ');
    const kolumner = dagar.map(d => {
      const dagnamn = new Date(d.datum + 'T12:00:00')
        .toLocaleDateString('sv-SE', { weekday: 'short', day: 'numeric' }).replace('.', '');
      const lekt = d.lekt;
      antalLekt += lekt.length;
      const brickor = lekt.map(s => {
        const i = par.get(s);
        if (i) antalTr++;
        const pa = i && vald(i.namn);
        if (pa && !valda.includes(i)) valda.push(i);
        const tid = start(s.tid) || '—';
        const sal = s.sal ? `<span class="mvsal">${s.sal}</span>` : '';
        const kurs = flerKurser && s.kurs ? `<span class="mvkurs">${kortkurs(s.kurs)}</span>` : '';
        /* Brickan är liten — vad den betyder får plats i tipset, inte på den. */
        const nar = `${s.tid || tid}${s.kurs ? ' · ' + s.kurs : ''}${s.sal ? ' · sal ' + s.sal : ''}`;
        if (!i) {
          return `<span class="mvpost" data-tom tabindex="0" data-tip="Ingen transkription" data-tipstod="${nar} — lektionen ligger i schemat men blev aldrig inspelad, så det finns inget att utgå från."><span class="mvtid">${tid}</span>${kurs}${sal}</span>`;
        }
        return `<button class="mvpost" type="button" data-tr data-namn="${i.namn}" aria-pressed="${pa}" data-tip="${i.namn}" data-tipstod="Transkriberad${i.langd ? ' · ' + langden(i.langd) : ''} · ${nar} — ${pa ? 'klicka för att släppa den' : 'klicka för att välja den också'}">${pa ? '<span class="mvbock">✓</span>' : ''}<span class="mvtid">${tid}</span>${kurs}${sal}</button>`;
      }).join('');
      return `<div class="mvdag"${d.datum === nu ? ' data-idag' : ''}${d.lov ? ' data-lov' : ''}>
        <p class="mvdagnamn">${dagnamn}</p>${brickor || (d.lov ? '<span class="mvlov">Lov</span>' : '')}</div>`;
    }).join('');

    /* Den valda lektionen är planeringens underlag — den ska synas som ett kort
       under kalendern, inte som en rad text. Klickar man på det står allt
       transkriptet faktiskt säger: hur långt ni kom och vad som aldrig nämndes.
       Etiketten säger «Vald lektion», inte «Utgår från»: steget har redan ett
       kvitto med den rubriken tio pixlar ovanför, och två «Utgår från» med olika
       räckvidd läses som ett fel. */
    const fot = valda.length
      ? `<div class="mkvalda">${valda.map((i, n) => `<div class="mkvalpost"><button class="mkval" type="button" aria-expanded="false"><span class="mkvaltopp"><span class="mkvaletikett">Vald lektion${valda.length > 1 ? ` · ${n + 1} av ${valda.length}` : ''}</span><span class="mkvalmeta">${metaFor(i)}</span></span><b class="mkvalnamn">${i.namn}</b><span class="mkvalmer">Vad säger den? ▾</span></button><div class="mkvalpanel" hidden></div></div>`).join('')}</div>`
      : `<p class="mkfot">${antalTr ? 'Klicka en eller flera transkriberade lektioner att utgå från' : 'Ingen transkriberad lektion den här veckan'}</p>`;

    el.innerHTML = `<div class="mkhuv"><span class="mketikett">Lektioner med ${kl || 'klassen'}</span><span class="mkant">${antalTr} av ${antalLekt} transkriberade</span></div>
      <div class="mvhuvud"><button class="kalpil" type="button" data-gar="-1" aria-label="Föregående vecka" data-tip="Föregående vecka">‹</button><span class="mvmitt"><span class="mvvecka">Vecka ${bild.vecka} · ${K.ord(bild.mandag)} – ${K.ord(bild.fredag)}</span><button class="mvidag" type="button" data-idagknapp data-tip="Idag" data-tipstod="Hoppar till den här veckan och pekar ut dagens datum.">Idag</button></span><button class="kalpil" type="button" data-gar="1" aria-label="Nästa vecka" data-tip="Nästa vecka">›</button></div>
      <div class="mvnat">${kolumner}</div>
      ${fot}`;

    $$('.kalpil', el).forEach(b => b.addEventListener('click', () => {
      const d = new Date(mandag + 'T12:00:00');
      d.setDate(d.getDate() + 7 * Number(b.dataset.gar));
      byt(Number(b.dataset.gar), K.mandagen(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`));
    }));
    const idagK = $('[data-idagknapp]', el);
    if (idagK) idagK.addEventListener('click', () => {
      const mal = K.mandagen(K.idag());
      if (mal === mandag) return pulseraIdag();
      byt(mal > mandag ? 1 : -1, mal);
      setTimeout(pulseraIdag, 520);
    });
    /* Kortet fälls ut på plats — ett svar man kan läsa utan att lämna veckan. */
    $$('.mkvalpost', el).forEach((post, n) => {
      const mk = $('.mkval', post), panel = $('.mkvalpanel', post), i = valda[n];
      if (!mk || !panel || !i) return;
      const l = window.Utgang && window.Utgang.las ? window.Utgang.las({ namn: i.namn }) : null;
      const m = metaFor(i);
      panel.innerHTML = (l
        ? `<p class="mkvalrad">${l.rad}</p>${l.punkter.map(p => `<p class="mkvalpunkt">${p}</p>`).join('')}`
        : '') + `<p class="mkvalfot">Transkript${i.klass ? ' · ' + i.klass : kl ? ' · ' + kl : ''}${m ? ' · ' + m : ''}</p>`;
      mk.addEventListener('click', () => {
        const pa = panel.hidden;
        panel.hidden = !pa;
        mk.setAttribute('aria-expanded', String(pa));
        $('.mkvalmer', mk).textContent = pa ? 'Dölj ▴' : 'Vad säger den? ▾';
      });
    });
    $$('.mvpost[data-namn]', el).forEach(b => b.addEventListener('click', () => {
      if (!window.Dokument) return;
      const namn = b.dataset.namn;
      const av = vald(namn);
      /* Flera lektioner får väljas — precis som i schemat högst upp. Två korta
         genomgångar om samma sak är ett bättre underlag än en halv. */
      av ? window.Dokument.slappLektion(namn) : window.Dokument.valjLektion(namn);
      window.Utgang && window.Utgang.rita();
      window.toast && window.toast(av ? 'Lektionen släppt' : `Utgår från ${namn}`);
      rita();
      /* Ringen ska växa fram på just den bricka man tryckte på. */
      const ny = $(`.mvpost[data-namn="${namn.replace(/"/g, '\\"')}"]`, el);
      if (ny) { ny.setAttribute('data-nyss', ''); setTimeout(() => ny.removeAttribute('data-nyss'), 420); }
    }));
  }

  $('#p-klass') && $('#p-klass').addEventListener('change', () => { mandag = null; rita(); });
  const vakt = new MutationObserver(() => rita());
  const chips = $('#valdalektioner');
  if (chips) vakt.observe(chips, { childList: true });
  window.Lektionskal = { rita };
  rita();
})();
