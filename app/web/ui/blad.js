/* ══════════ BLADEN — appens dokument i sin riktiga sättning ══════════
   Appen skrev förr sina egna generiska mallar: numrerade rader, «Beräkna med
   hjälp av …», en grå panel per uppgift. Formen är sedan länge bestämd någon
   annanstans — i «Arbetsblad prov och tavlor — femton former» — och det är DEN
   som ska visas: A4 vid 96 dpi, feta rubriker, hårlinjer, poängparenteser,
   bokstavsbrickor, och tavlan satt som en riktig whiteboard.

   Här bor valet och ritningen. Bladen själva byggs i blad-bygg.js (försättsblad,
   provblad, ark, facit och bokens lösningsblad via blad-boklos.js) och tavlan i
   blad-tavla.js, som kör whiteboard-motorn i tavla-wb.js.

     Blad.rita(mal, v)     ritar dokumentet v i mal
     Blad.uppgifter(v)     uppgiftslistan bladet faktiskt bär (poäng, nivå)
     Blad.form(v)          vilka blad formen består av

   Vilken form ett dokument får följer av momentet — inte av en slumpad mall:
   geometri får figurspalt, ekvationslösning får den radbundna, en uppgift som
   handlar om att hitta felet får jämförelsetabellen. */
window.Blad = (() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const T = () => window.BladTavla || {};

  const ord = m => String(m || '').toLowerCase();
  const TEORI = /sats|teori|regel|begrepp|definition|härled|harled/;
  const I = () => window.Innehall;
  const B = () => window.BladBygg;

  /* ── Vilka uppgifter dokumentet bär ──────────────────
     Uppgifterna kommer ur AVSNITTET, inte ur en fast förlaga. Ett prov om
     «4.2 Logaritmlagar» innehåller därför logaritmuppgifter, och tavlan till
     samma moment lär ut samma sak. Rättningen, metaraderna och arket läser
     samma lista. */
  const arE = u => u.niva === 'E';
  function varva(prim, sek, takt) {
    const ut = [];
    let a = 0, b = 0;
    while (a < prim.length || b < sek.length) {
      for (let n = 0; n < takt && a < prim.length; n++) ut.push(prim[a++]);
      if (b < sek.length) ut.push(sek[b++]);
    }
    return ut;
  }

  /* Provet prövar det klassen har läst — dagens avsnitt och de före det.
     Del A är E-uppgifterna (utan digitala hjälpmedel), del B resten (med räknare
     och GeoGebra); gränsen räknas ur listan och inte ur ett fast uppgiftsnummer,
     så ett prov utan C- och A-uppgifter helt enkelt saknar del B. */
  function provplock(v) {
    const i = v.inst || {};
    const pool = I() ? I().provpool(v.moment, 12) : [];
    if (!pool.length) return [];
    const b = pool.filter(arE), c = pool.filter(u => !arE(u));
    const mix = i.nivamix || 'Balanserat';
    const valj = mix === 'Bara E' ? b
      : mix === 'E-tyngd' ? varva(b, c, 2)
        : mix === 'C/A-tyngd' ? varva(c, b, 2)
          : varva(b, c, 1);
    const antal = Math.max(1, Math.min(valj.length, Number(i.antal) || Math.min(12, valj.length)));
    const ut = valj.slice(0, antal).sort((x, z) => (arE(z) ? 1 : 0) - (arE(x) ? 1 : 0) || x.nr - z.nr);
    /* Numren på pappret börjar alltid på 1 — ett prov som hoppar från 2 till 5
       läses som att två sidor saknas. `orig` är platsen i avsnittslistan. */
    return ut.map((u, k) => ({ ...u, orig: u.nr, nr: k + 1 }));
  }
  const provval = provplock;
  const delBAntal = v => uppgifter(v).filter(arE).length;

  /* Arbetsbladet och gruppuppgiften håller sig till dagens avsnitt — och till
     den nivå läraren valde. «Nivå» var förr en etikett på metaraden; nu väljer
     den vilka uppgifter som sätts ut. */
  const NIVA = { 'E-nivå': ['E'], 'C-nivå': ['C'], 'A-nivå': ['A'] };
  function arkval(v) {
    const i = v.inst || {};
    const pool = I() ? I().arkpool(v.moment) : [];
    if (!pool.length) return [];
    const vill = NIVA[i.niva];
    let valj;
    if (vill) {
      valj = pool.filter(u => vill.includes(u.niva));
      /* Ett avsnitt med bara en A-uppgift ska inte ge ett halvtomt blad — då
         fylls det på med närmaste nivå, i stigande svårighet. */
      if (valj.length < 3) valj = valj.concat(pool.filter(u => !valj.includes(u)));
    } else {
      /* Blandat: en per nivå i tur och ordning, så tre uppgifter blir E, C, A
         och inte tre E-uppgifter i rad. */
      const hinkar = ['E', 'C', 'A'].map(n => pool.filter(u => u.niva === n));
      valj = [];
      for (let k = 0; valj.length < pool.length && k < 60; k++) {
        const h = hinkar[k % 3];
        if (h.length) valj.push(h.shift());
      }
    }
    const antal = Math.max(1, Math.min(valj.length, Number(i.antal) || 3));
    return valj.slice(0, antal).map((u, k) => ({ ...u, nr: k + 1 }));
  }

  /* Tavlan har inga uppgifter i egen mening — men rättningen och metaraderna
     vill ändå veta vad lektionen bestod av. */
  function tavuppg(v) {
    const av = I() ? I().hitta(v.moment) : null;
    const rent = s => (window.BladTavla && window.BladTavla.platt ? window.BladTavla.platt(s) : String(s || ''));
    if (!av) return [];
    return [
      { nr: 1, p: 2, t: 'Receptet: ' + rent(av.tavla.recept.slice(0, 2).join(' ')) },
      { nr: 2, p: 3, t: 'Exemplet på tavlan — ' + av.rubrik.toLowerCase() + '.' },
      { nr: 3, p: 2, t: 'Elevuppgift i par, återsamling om vanligaste felet.' }
    ];
  }

  /* Ett prov eller arbetsblad som SERVERN skrivit bär sina egna uppgifter.
     De får aldrig bytas mot avsnittspoolens: nyVersion räknar om uppgifterna
     vid varje ändring, och utan den här grinden hade en itererad tavla eller
     ett rättat prov tappat allt Claude skrev och tyst fyllts med prototypens
     uppgifter i stället. */
  const franServern = v => !!(v && v.provId && (v.uppgifter || []).length);
  function uppgifter(v) {
    if (franServern(v)) return v.uppgifter;
    if (v.typ === 'Prov') return provval(v);
    if (v.typ === 'Tavla') return tavuppg(v);
    /* Anteckningarna har inga uppgifter och ska inte låtsas ha det: hämtades
       de ur avsnittspoolen skulle rättningen, poängsummorna och «6 uppgifter»
       räkna på uppgifter som aldrig står på pappret. */
    if (v.typ === 'Anteckningar') return [];
    return arkval(v);
  }

  /* ── Bladen dokumentet består av ─────────────────────
     Byggaren sätter dem ur uppgifterna; formen är förlagans. */
  function bladen(v) {
    const bb = B();
    if (!bb) return [];
    if (v.typ === 'Anteckningar') return [bb.anteckningar(v, anteckningarnaFor(v))];
    if (v.typ === 'Prov') {
      const u = uppgifter(v);
      if (!u.length) return [];
      const b = u.filter(arE), c = u.filter(x => !arE(x));
      const enDel = (v.inst || {}).delprov === 'En del' || !b.length || !c.length;
      if (v.losningsblad) return bb.losning(v, u, enDel ? u.length : b.length);
      const ut = [bb.provforsatt(v)];
      if (enDel) ut.push(bb.provblad(v, u, '-', true));
      else { ut.push(bb.provblad(v, b, 'B', true)); ut.push(bb.provblad(v, c, 'C', true)); }
      return ut;
    }
    const u = uppgifter(v);
    if (!u.length) return [];
    if (v.losningsblad) return [bb.arkfacit(v, u)];
    const ut = [bb.ark(v, u, {})];
    /* Diagnosen bär ALLTID sin rättning i samma dokument — det är dess form
       (app/templates/diagnos.tex.j2), och läraren ska inte behöva hålla reda på
       två papper för att pricka av en klass. */
    if ((v.inst || {}).facit === 'Facit i bladet' || v.typ === 'Diagnos') ut.push(bb.arkfacit(v, u));
    return ut;
  }

  /* plan.js läser formen för att säga «2 sid» i utskriftspaketet — den behöver
     antalet ark, inte deras namn. */
  function form(v) {
    if (v.typ === 'Tavla') return ['tav'];
    return bladen(v).map((_, i) => 'ark' + i);
  }

  /* Anteckningarna språkmodellen skrev (notes_gen) — eller, utan server,
     lärarens egen text lagd på pappret.

     Prototypens andra former hämtar innehåll ur avsnittspoolen (innehall.js),
     men det går inte här: pappret handlar om boken, upplägget och rutinerna,
     och ett påhittat sådant innehåll vore ett påstående om lärarens kurs.
     Det hon SJÄLV skrev i rutan är däremot sant, och att se det satt som ett
     A4 är precis vad förhandsvisningen ska visa. */
  function anteckningarnaFor(v) {
    if (v.ant && (v.ant.sektioner || []).length) return v.ant;
    const onskad = ((v.inst || {}).onskemal || '').trim();
    const stycken = onskad.split(/\n{2,}/).map(s => s.trim()).filter(Boolean);
    return {
      titel: versal(v.moment || 'Anteckningar'),
      sektioner: stycken.length
        ? stycken.map((s, i) => ({ rubrik: i ? 'Att säga' : 'Det här ska med',
                                   stycken: [s] }))
        : [{ rubrik: 'Inget skrivet än',
             stycken: ['Skriv i rutan vad pappret ska innehålla, eller välj '
                       + 'ett möte att bygga det på.'] }],
    };
  }

  /* ══════ PLANERINGEN PÅ PAPPRET ══════
     Förlagan bär formen, planeringen bär identiteten: rubriken, dagen,
     klockslagen, provtiden, vilka uppgifter som står där och vad de summerar
     till. Utan det här steget sa steg 3 en sak och arket en annan. */
  const versal = s => String(s || '').charAt(0).toUpperCase() + String(s || '').slice(1);
  const iMin = t => { const m = String(t || '').match(/(\d{1,2})[:.](\d{2})/); return m ? +m[1] * 60 + +m[2] : null; };
  const kl = m => `${String(Math.floor((((m % 1440) + 1440) % 1440) / 60)).padStart(2, '0')}.${String(((m % 60) + 60) % 60).padStart(2, '0')}`;

  /* Provtiden på pappret måste gå att lita på. Är provet längre än lektionen
     det ligger på skrivs inget slutklockslag ut — «kl. 11.15–12.45» på en
     lektion som slutar 12.00 är ett löfte skolan inte kan hålla. Varningen i
     steg 3 säger samma sak; pappret ska inte säga något annat. */
  function provtidText(v) {
    const i = v.inst || {};
    const min = Number(i.provminuter) || 90;
    const spann = String(v.lektionstid || v.tid || '').split('–');
    const start = iMin(spann[0] || i.narTid);
    const slut = iMin(spann[1] || '');
    const egenDag = i.nar === 'Annan dag';
    if (start == null) return `${min} minuter.`;
    if (!egenDag && slut != null && start + min > slut) {
      return `${min} minuter, från kl. ${kl(start)}. Provet är längre än lektionen (${slut - start} min) — kontrollera tiden med eleverna.`;
    }
    return `${min} minuter, kl. ${kl(start)}–${kl(start + min)}.`;
  }

  const omrade = (a, b) => (a === b ? `uppgift ${a}` : `uppgift ${a}–${b}`);

  function planvalProv(trav, v) {
    const i = v.inst || {};
    const plock = uppgifter(v);
    const kvar = new Map(plock.map((u, k) => [u.nr, k + 1]));
    const antalB = plock.filter(arE).length;
    const summa = plock.reduce((a, u) => a + u.p, 0);
    const sumB = plock.filter(arE).reduce((a, u) => a + u.p, 0);
    const enDel = i.delprov === 'En del' || !antalB || antalB === plock.length;

    $$('.pruppg', trav).forEach(el => {
      const bricka = $('.prnr', el);
      const nr = parseInt((bricka || {}).textContent || '', 10);
      if (!bricka || !nr) return;
      const nytt = kvar.get(nr);
      if (!nytt) { el.remove(); return; }
      if (bricka.firstChild && bricka.firstChild.nodeType === 3) bricka.firstChild.nodeValue = nytt + '.';
    });
    /* Ett blad utan uppgifter kvar är ett tomt papper i traven — det ska bort. */
    $$('.blad', trav).forEach(bl => {
      const ark = $('.ark[data-form]', bl);
      if (!ark || ark.dataset.form === 'pr1') return;
      if (!$('.pruppg', ark)) bl.remove();
    });
    const sista = $$('.blad', trav).pop();
    /* Vändpilen betyder «det finns mer» och hör därför till varje blad UTOM det
       sista. Förr tog första raden bort pilen från alla blad som INTE var det
       sista, och andra raden tog bort den från det sista också — nettot var att
       pilen försvann överallt. */
    $$('[data-vand]', trav).forEach(p => { if (sista && sista.contains(p)) p.remove(); });

    if (enDel) {
      $$('.prhuvud b:nth-child(2)', trav).forEach(b => b.remove());
      /* «En del» betyder att delarna inte finns — då får ingen fot säga «Slut
         på del A». Placeringen bestäms av TRAVEN, inte av vilka rader som
         råkade matcha: slutraden hör till det sista bladet som bär uppgifter. */
      $$('.prslut[data-slut]', trav).forEach(p => { if (/slut på del /i.test(p.textContent)) p.remove(); });
      const sistaMedUppg = $$('.blad', trav).filter(bl => $('.pruppg', bl)).pop();
      const ark = sistaMedUppg && $('.ark[data-form]', sistaMedUppg);
      if (ark) {
        const rad = document.createElement('p');
        rad.className = 'prslut';
        rad.setAttribute('data-slut', '');
        rad.textContent = 'Slut på provet';
        ark.appendChild(rad);
      }
    } else {
      /* Varje delprov ska säga var det slutar och vad det är värt. Förr saknade
         delproven fot helt: bladet slutade i tomt papper och eleven fick själv
         räkna ut hur mycket delen kunde ge. Foten pinnas till bladkanten av
         .prslut{margin:auto 0 0} — den ramar in den tomma ytan i stället för att
         låta bladet bara ta slut. */
      [['pr1b', 'A', sumB], ['pr1c', 'B', summa - sumB]].forEach(([form, namn, po]) => {
        const blad = $$('.blad', trav).filter(bl => {
          const a = $('.ark[data-form]', bl);
          return a && a.dataset.form === form && $('.pruppg', a);
        }).pop();
        const ark = blad && $('.ark[data-form]', blad);
        if (!ark || $('.prslut[data-slut]', ark)) return;
        const rad = document.createElement('p');
        rad.className = 'prslut';
        rad.setAttribute('data-slut', '');
        rad.textContent = `Slut på del ${namn} — delen ger högst ${po} poäng`;
        ark.appendChild(rad);
      });
      /* Och varje blad som inte är sista i sin del får vändpilen. */
      ['pr1b', 'pr1c'].forEach(form => {
        const blad = $$('.blad', trav).filter(bl => {
          const a = $('.ark[data-form]', bl);
          return a && a.dataset.form === form;
        });
        blad.slice(0, -1).forEach(bl => {
          const ark = $('.ark[data-form]', bl);
          if (!ark || $('.prslut[data-vand]', ark)) return;
          const rad = document.createElement('p');
          rad.className = 'prslut';
          rad.setAttribute('data-vand', '');
          rad.textContent = 'Fortsätter på nästa sida';
          ark.appendChild(rad);
        });
      });
    }

    const titel = $('.prtitel', trav);
    if (titel && v.moment) titel.textContent = `${v.variant === 'Omprov' ? 'Omprov' : 'Prov'} — ${versal(v.moment)}`;

    const meta = $('.prmeta tbody', trav);
    if (meta) {
      const rad = (n, t) => `<tr><th>${n}</th><td>${t}</td></tr>`;
      /* Hjälpmedlen är det som skiljer del A från del B — därför står de i
         delraderna och inte som ett blankt förbud på hjälpmedelsraden. Svaret
         skrivs i provet på båda delarna; redovisningen på lösblad på båda. */
      const redovisas = 'Svaret skrivs i provet, redovisningen på lösblad.';
      meta.innerHTML = rad('Provtid', provtidText(v))
        + rad('Hjälpmedel', `${i.formelblad ? 'Formelblad och linjal' : 'Linjal'}.${enDel ? ' Inga digitala hjälpmedel.' : ''}`)
        + (enDel
          ? rad('Uppgifter', `${versal(omrade(1, plock.length))}. ${redovisas}`)
          : rad('Del A', `${versal(omrade(1, antalB))}. Utan digitala hjälpmedel. ${redovisas}`)
            + rad('Del B', `${versal(omrade(antalB + 1, plock.length))}. Räknare och digitala hjälpmedel tillåtna. ${redovisas}`));
    }
    const not = $('.prnot', trav);
    if (not) not.innerHTML = `Provet ger högst <b>${summa} poäng</b>${enDel ? '' : ` — ${sumB} på del A och ${summa - sumB} på del B`}. Efter varje uppgift står hur många poäng den kan ge.${enDel ? '' : ' Uppgifter märkta «lösblad» redovisas på separat lösblad — visa hur du räknar och förklara varför.'} Skriv ditt namn på alla papper du lämnar in.${plock.some(u => !arE(u)) ? '' : ' Provet prövar E-nivån — det finns inga uppgifter för C och A på det här provet.'}`;

    const betyg = $('.prbetyg', trav);
    if (betyg) {
      const g = a => Math.max(1, Math.round(summa * a));
      const kravC = enDel ? '' : `, minst ${Math.max(1, Math.round((summa - sumB) * .23))} av dem på del B`;
      const kravA = enDel ? '' : `, minst ${Math.max(1, Math.round((summa - sumB) * .45))} av dem på del B`;
      const kropp = $('tbody', betyg), fot = $('tfoot td:last-child', betyg);
      /* Ett prov som bara bär E-uppgifter kan inte ge C eller A. Står gränserna
         där ändå lovar pappret ett betyg uppgifterna inte kan bära. */
      const harC = plock.some(u => !arE(u));
      if (kropp) kropp.innerHTML = `<tr><td>E</td><td>${g(.3)} poäng</td></tr>`
        + (harC ? `<tr><td>C</td><td>${g(.53)} poäng${kravC}</td></tr><tr><td>A</td><td>${g(.77)} poäng${kravA}</td></tr>` : '');
      if (fot) fot.textContent = `${summa} poäng`;
    }

    /* Försättsbladet slutar i en halv sida tomt papper. Där hör lektionens bild
       hemma — omslagsfiguren, skolans märke, en formelruta — och den läggs in i
       canvas som vilken annan bild som helst. */
    const forsta = $('.ark[data-form="pr1"]', trav);
    if (forsta && !$('.prforsatt', forsta)) {
      const p = document.createElement('div');
      p.className = 'prforsatt';
      p.innerHTML = '<div class="prbild gufigur"><span class="gufigtext">plats för bild — läggs in i canvas</span></div>';
      forsta.appendChild(p);
    }
  }

  /* Gruppuppgiftens tre val är inte appens interna sak: eleverna behöver veta hur
     många de är i gruppen, hur lång tid de har och hur det ska redovisas. Står
     det inte på pappret finns det inte i klassrummet. Namnraderna följer
     gruppstorleken av samma skäl. */
  function grupphuvud(trav, v) {
    if (!v || v.typ !== 'Gruppuppgift' || v.losningsblad) return;
    const i = v.inst || {};
    const n = Math.max(2, Math.min(6, Number(i.grupp) || 3));
    const REDOV = { 'Muntligt': 'muntlig redovisning', 'Skriftligt': 'skriftlig redovisning', 'Poster': 'redovisas som poster' };
    /* Redovisningsformen är ett löfte till gruppen om hur det slutar. Står den
       bara som en etikett vet ingen vad som förväntas — så den sägs i klartext i
       instruktionsbandet också. */
    const HUR = {
      'Muntligt': 'Redovisas muntligt: två minuter per grupp, och alla i gruppen säger något.',
      'Skriftligt': 'Redovisas skriftligt: ett gemensamt svar per grupp lämnas in vid lektionens slut.',
      'Poster': 'Redovisas som poster: skriv lösningen stort på ett blad som sätts upp i salen.'
    };
    const rad = [`${n} elever per grupp`, `${Number(i.langd) || 45} minuter`, REDOV[i.redovisning] || 'muntlig redovisning'].join(' · ');
    $$('.gu', trav).forEach(gu => {
      const huv = $('.guhuv', gu);
      if (huv) {
        let p = $('.gumeta', huv);
        if (!p) { p = document.createElement('p'); p.className = 'gumeta'; huv.appendChild(p); }
        p.textContent = rad;
      }
      const topp = $('.gutopp', gu);
      const mall = topp && $('.gurad', topp);
      const band = $('.guband', gu);
      const hur = HUR[i.redovisning] || HUR.Muntligt;
      if (band && !/redovisas/i.test(band.textContent)) band.insertAdjacentHTML('beforeend', ` ${hur}`);
      if (!topp || !mall) return;
      let rader = $$('.gurad', topp);
      while (rader.length > n) { rader.pop().remove(); }
      while (rader.length < n) { topp.appendChild(mall.cloneNode(true)); rader = $$('.gurad', topp); }
    });
  }

  /* ── Arbetsbladets metarad ──────────────────────────
     Formen delas med gruppuppgiften — skillnaden står i tilltalet (byggaren
     väljer instruktionsband per typ) och i den här raden: hur många uppgifter,
     vilken nivå och att arbetet är enskilt. */
  function arkhuvud(trav, v) {
    if (!v || v.typ !== 'Arbetsblad' || v.losningsblad) return;
    const i = v.inst || {};
    const antal = arkval(v).length;
    const rad = [`${antal} ${antal === 1 ? 'uppgift' : 'uppgifter'}`, (i.niva || 'Blandat').toLowerCase(), 'enskilt arbete'].join(' · ');
    $$('.gu', trav).forEach(gu => {
      const huv = $('.guhuv', gu);
      if (!huv) return;
      let p = $('.gumeta', huv);
      if (!p) { p = document.createElement('p'); p.className = 'gumeta'; huv.appendChild(p); }
      p.textContent = rad;
    });
  }

  function planval(trav, v) {
    if (!v) return;
    if (v.typ === 'Prov' && !v.losningsblad) planvalProv(trav, v);
  }

  /* ── Sidhuvudet är dokumentets, inte förlagans ──────
     Uppgifterna och sättningen står fast; kurs, klass och termin kommer ur
     planeringen, så bladet är lärarens eget papper.
     Lösningsförslaget rörs INTE: där är första fetstilen etiketten («Svarsfacit
     · kortsvar», «Bedömd elevlösning») — det som säger vad man håller i. Skrevs
     kursraden dit försvann etiketten, och bladet slutade se ut som förlagan. */
  const termin = v => {
    if (!v.datum) return '';
    const d = new Date(v.datum + 'T12:00:00');
    return (d.getMonth() < 6 ? 'vt ' : 'ht ') + d.getFullYear();
  };
  function huvud(rot, v) {
    const rad = [v.kurs || 'Matematik', v.klass, termin(v)].filter(Boolean).join(' · ');
    $$('.prhuvud b:first-child', rot).forEach(b => { b.textContent = rad; });
  }

  /* ── Elementen canvas kan peka på ────────────────────
     Granskningen fäster kommentarer och bilder på [data-el]. Bladen är sättning,
     så nålarna sätts här i stället för i markupen. */
  const BOKSTAV = 'ABCDEFGH';
  function markera(rot, v) {
    const andrat = v.andrat || [];
    const salt = (el, nyckel, namn) => {
      el.dataset.el = nyckel;
      el.dataset.namn = namn;
      if (andrat.includes(nyckel)) el.classList.add('andrad');
    };
    $$('.prhuvud, .guhuv, .lohuvud, .anhuv', rot).forEach(el => salt(el, 'rubrik', 'Sidhuvudet'));
    /* Anteckningarnas sektioner är papprets uppgifter: det är dem läraren
       pekar på i canvas när hon vill ha en rad ändrad. Nålen får sitt namn ur
       rubriken, så listan i granskningen säger «Boken» och inte «Avsnitt 2». */
    $$('.ansekt', rot).forEach((el, n) => salt(
      el, 'sekt' + (n + 1),
      (($('.anrubrik', el) || {}).textContent || '').trim() || 'Avsnitt ' + (n + 1)));
    $$('.ankom', rot).forEach(el => salt(el, 'komihag', 'Kom ihåg-rutan'));
    $$('.probs, .guband', rot).forEach(el => salt(el, 'instr', 'Instruktionen'));
    $$('.gutopp', rot).forEach(el => salt(el, 'namn', 'Namnraderna'));
    $$('.prmeta, .prbetyg', rot).forEach((el, n) => salt(el, 'avtal' + n, n ? 'Betygsgränserna' : 'Provtabellen'));
    $$('.prforsatt', rot).forEach(el => salt(el, 'forsatt', 'Bilden på försättsbladet'));
    $$('.pruppg', rot).forEach(el => {
      const nr = parseInt(($('.prnr', el) || {}).textContent || '', 10);
      if (nr) salt(el, 'uppg' + nr, 'Uppgift ' + nr);
    });
    $$('.gukort', rot).forEach((el, n) => {
      const b = ($('.gubricka', el) || {}).textContent || BOKSTAV[n];
      salt(el, 'uppg' + (BOKSTAV.indexOf(b) + 1 || n + 1), 'Uppgift ' + b);
    });
    $$('.gutab', rot).forEach(el => salt(el, 'tabell', 'Jämförelsetabellen'));
    $$('.lopost', rot).forEach((el, n) => salt(el, 'facit' + (n + 1), 'Facit ' + (n + 1)));
    $$('.loskann', rot).forEach((el, n) => salt(el, 'elev' + (n + 1), 'Elevlösning ' + BOKSTAV[n]));
  }

  /* ── Figurerna och matematiken ───────────────────────
     Figurerna står som CeTZ-källa i data-figur och kompileras till SVG i
     webbläsaren; formlerna sätts av KaTeX. Båda är asynkrona — rutorna har sin
     höjd redan, så sättningen hoppar inte medan de fylls. */
  function kompilera(rot) {
    $$('[data-figur]', rot).forEach(el => {
      if (el.dataset.cetz || !window.Figurer) return;
      try {
        const fig = JSON.parse(el.dataset.figur);
        const kalla = window.Figurer.kalla(fig);
        if (fig.storlek) el.dataset.storlek = fig.storlek;
        if (kalla) el.dataset.cetz = kalla;
      } catch (e) { console.warn('Figuren kunde inte läsas:', e && e.message); }
    });
    if (window.Figur) window.Figur.ritaAlla(rot);
    if (window.Matte) window.Matte.satt(rot);
  }

  /* ── Tavlan ──
     Whiteboardmotorn MÄTER: den mäter varje sektion, flödar dem i spalter och
     binärsöker en skala så att spalten fylls utan att spilla. Två saker följer
     av det, och båda gick fel när tavlan först flyttades in i appen.

     Ett: tavlan måste ritas i sin verkliga storlek (1400 px). Krymps värden med
     zoom INNAN den ritas mäter motorn zoomade pixlar mot omätta budgetar och
     spalterna spiller över varandra. Därför ritas den stor och krymps efteråt
     med transform, som inte rör det motorn redan räknat ut.

     Två: handskriften är Caveat. Är typsnittet inte inne när motorn mäter blir
     varje textbredd fel — och då hamnar allt huller om buller. Därför ritas
     tavlan om när typsnitten är klara. */
  /* Canvasen fäster kommentarer på [data-el]. Tavlan har ingen markup att salta i
     förväg — motorn skriver den — så nålarna sätts när den är ritad. */
  /* Namnet är det läraren pekar på i canvasen — det måste därför skilja sex
     formler åt. Förr hette de alla «Formeln», och teckentabellen hette
     «x<111–33>3f'+0−0+»: en etikett man inte kan välja på. Nu numreras varje
     sort inom sin spalt, och tabeller och grafer får riktiga namn. */
  function tavnamn(el, rubrik, raknare) {
    const numrera = sort => {
      raknare[sort] = (raknare[sort] || 0) + 1;
      return raknare[sort];
    };
    if (el.classList.contains('wb-math')) {
      const n = numrera('math');
      return rubrik ? `${rubrik} · formel ${n}` : 'Formel ' + n;
    }
    if (el.querySelector && el.querySelector('table')) return rubrik ? `${rubrik} · tabellen` : 'Tabellen';
    if (el.tagName.toLowerCase() === 'svg' || el.classList.contains('wb-svg') || (el.querySelector && el.querySelector('svg'))) {
      /* En understrykning är också en svg — men den är inte en figur, och att
         kalla den «Kurvan · figuren» gör elementvalet till en gissningslek. */
      const h = el.getBoundingClientRect ? el.getBoundingClientRect().height : 40;
      if (h && h < 24) return 'Understrykningen';
      const n = numrera('fig');
      return rubrik ? `${rubrik} · figuren` : 'Figur ' + n;
    }
    const t = (el.textContent || '').replace(/\s+/g, ' ').trim();
    if (!t) return 'Rutan';
    if (t.length <= 34) return t;
    /* Ett block med flera rader har ingen egen mening att heta efter — då hör det
       till rubriken ovanför. «Receptet» är ett namn; «1.Derivera.2.Lös f′(x)…»
       är innehållet en gång till. */
    return rubrik ? `${rubrik} · blocket` : t.slice(0, 33) + '…';
  }
  function taggaTavla(host, v) {
    const andrat = (v && v.andrat) || [];
    let rubrik = '';
    const raknare = {};
    $$('.wb-element', host).forEach((el, n) => {
      el.dataset.el = 'tav' + n;
      el.dataset.namn = tavnamn(el, rubrik, raknare);
      const t = (el.textContent || '').replace(/\s+/g, ' ').trim();
      if (el.classList.contains('wb-text') && t && t.length <= 24) rubrik = t.replace(/[:.]+$/, '');
      if (andrat.includes('tav' + n)) el.classList.add('andrad');
    });
  }

  /* Specen bär funktioner (graferna) och överlever därför inte JSON i ett
     attribut. Rutan bär ett nummer i stället, och specen ligger kvar här —
     så kan en KLONAD tavla (canvasen) ritas om ur samma spec. */
  const tavlor = new Map();
  let tavnr = 0;

  /* ── Kurvorna ──
     I wb-json-v1 är en grafs kurva en UTTRYCKSSTRÄNG (plots[].expr):
     språkmodellen får inte skicka JS-funktioner. Motorn vill ha en funktion
     (plots[].fn), och utan det här steget ritades axlar och rutnät men ingen
     kurva — tavlan såg färdig ut och saknade det den handlade om. Prototypens
     egna specar (innehall.js) bär redan fn och rörs inte.
     Kompileringen görs av WBExpr (whitelist-parser, ingen eval) som bor i
     /static/whiteboard/expr.js — samma fil app/whiteboard_spec.py speglar
     grammatiken ur serversidigt. Ett uttryck som inte går att kompilera blir
     en [WB]-varning och kurvan hoppas över: hellre en tavla utan kurva än
     ingen tavla, och varningen går vidare till reparationsrundan. */
  function kurvor(x) {
    if (Array.isArray(x)) return x.map(kurvor);
    if (!x || typeof x !== 'object') return x;
    const ut = {};
    Object.keys(x).forEach(k => { ut[k] = kurvor(x[k]); });
    if (ut.kind === 'graph' && Array.isArray(ut.plots)) {
      ut.plots = ut.plots.filter(p => {
        if (typeof p.fn === 'function') return true;
        if (!p.expr) return false;
        if (!window.WBExpr) { console.warn('[WB] uttrycksparsern saknas — kurvan kunde inte ritas'); return false; }
        try { p.fn = window.WBExpr.compile(p.expr); return true; }
        catch (e) { console.warn(`[WB] ogiltigt uttryck i plots[].expr: '${p.expr}' — ${e.message}`); return false; }
      });
    }
    return ut;
  }

  function ritaTavlan(ruta, spec, v, naturlig) {
    if (!spec || !window.WBLayout || !ruta.isConnected) return;
    let host = $('.tavhost', ruta);
    if (!host) { host = document.createElement('div'); host.className = 'tavhost'; ruta.appendChild(host); }
    host.innerHTML = '';
    host.style.transform = '';
    ruta.style.height = '';
    /* Motorn skriver sina invändningar som «[WB] …» i konsolen medan den mäter:
       innehåll som inte ryms, element som krockar. En tavla skriven av
       språkmodellen kan REPARERAS på dem — därför fångas de här i stället för
       att bara rulla förbi. Se window.Tavla.varnade i plan.js. */
    const varningar = [];
    const forraWarn = console.warn;
    console.warn = function (...a) {
      if (String(a[0] || '').startsWith('[WB]')) varningar.push(String(a[0]));
      forraWarn.apply(console, a);
    };
    /* Tavlan kan vara ETT bräde (prototypens form ur innehall.js) eller ett helt
       dokument med flera (det språkmodellen skriver, wb-json-v1). */
    try { window.WBLayout.renderWhiteboard(kurvor(spec.boards ? spec : { boards: [spec] }), host); }
    catch (e) { console.warn = forraWarn; forraWarn.call(console, 'Tavlan kunde inte ritas:', e && e.message); return; }
    finally { console.warn = forraWarn; }
    if (varningar.length && window.Tavla && window.Tavla.varnade) window.Tavla.varnade(v, varningar);
    const tavla = host.firstElementChild;
    if (!tavla) return;
    taggaTavla(host, v);
    const nat = tavla.getBoundingClientRect();
    if (naturlig) { ruta.style.height = Math.round(nat.height) + 'px'; return; }
    const bredd = ruta.clientWidth || (ruta.parentElement || {}).clientWidth || 794;
    const k = Math.min(1, bredd / (nat.width || 1440));
    host.style.transformOrigin = 'top left';
    host.style.transform = `scale(${k})`;
    ruta.style.height = Math.round(nat.height * k) + 'px';
  }

  function ritaTavla(ruta, host, spec, v) {
    if (!spec) return;
    const id = String(++tavnr);
    ruta.dataset.tav = id;
    tavlor.set(id, { spec, v });
    if (tavlor.size > 24) tavlor.delete(tavlor.keys().next().value);
    const rita = () => ritaTavlan(ruta, spec, v, false);
    /* Förhandsvisningen ritar dokumentet MEDAN modalen ännu är gömd. Då mäter
       motorn nollor och tavlan blir en tom ruta — så ritningen väntar tills
       rutan har en bredd att mätas mot. */
    nar(ruta, () => {
      rita();
      if (document.fonts && document.fonts.status !== 'loaded') document.fonts.ready.then(rita);
    });
  }

  /* Canvasen KLONAR pappret. En klonad tavla är bara en bild av förhandsvisningens
     krympta skala — här ritas den om i sin verkliga storlek, så zoomen har något
     att zooma i och elementen går att peka på. */
  function omritaTavlor(rot) {
    $$('.tavruta[data-tav]', rot).forEach(ruta => {
      const post = tavlor.get(ruta.dataset.tav);
      if (post) ritaTavlan(ruta, post.spec, post.v, true);
    });
  }
  /* Kör nu om elementet är synligt, annars första gången det blir det.
     ResizeObserver rapporterar INTE när ett element går från display:none till
     synligt — och förhandsvisningens modal är precis det. Därför en tickare
     bredvid vakten: utan den blev varje sparad tavla ett tomt papper. */
  function nar(el, fn) {
    if (el.clientWidth > 0) { fn(); return; }
    let klar = false, vakt = null;
    const fran = Date.now();
    const prova = () => {
      if (klar) return;
      if (el.clientWidth > 0) {
        klar = true;
        if (vakt) vakt.disconnect();
        fn();
        return;
      }
      if (!el.isConnected || Date.now() - fran > 20000) { klar = true; if (vakt) vakt.disconnect(); return; }
      setTimeout(prova, 150);
    };
    if (typeof ResizeObserver === 'function') {
      vakt = new ResizeObserver(prova);
      vakt.observe(el);
    }
    setTimeout(prova, 80);
  }

  /* ── Skalan ──
     Bladet är 794 px brett på riktigt och tavlan 1440. Rutan är smalare, så
     traven zoomas — måtten i sättningen förblir de tryckta. */
  function skala(trav) {
    const satt = () => {
      const bredd = trav.clientWidth || (trav.parentElement || {}).clientWidth || 794;
      trav.style.setProperty('--bladskala', String(Math.min(1, bredd / 794)));
    };
    satt();
    nar(trav, satt);
  }

  /* ── Att få bladet att gå ihop med pappret ───────────
     Bladet bär bara uppgifter, svarsrader och lösbladshänvisningar — ingen
     skrivyta att krympa eller blåsa upp. Spiller det ändå delas det i två. */
  /* Bladet har fast höjd, så scrollHeight kan inte skilja «precis fullt» från
     «halvtomt». Måttet som duger är avståndet mellan sista kortets underkant och
     pappersmarginalen: positivt är luft kvar, negativt är spill. */
  /* MÄT I LAYOUTPIXLAR, aldrig i skärmpixlar. Traven skalas med zoom (blad.css)
     och lektionsvyn visar bladet nedskalat — då ger getBoundingClientRect()
     SKALADE mått, medan höjden vi sätter och paddingen vi läser ur computed style
     är oskalade. Blandningen gav negativ eller för stor restyta: skrivlinjerna
     kunde få 45 rader på 130 px, alltså ett grått raster i stället för linjer att
     skriva på. offsetTop/offsetHeight/clientHeight är oskalade — använd dem. */
  function ledigt(gu) {
    const kort = Array.from(gu.querySelectorAll('.gukort'));
    const sist = kort[kort.length - 1];
    if (!sist) return 0;
    const cs = getComputedStyle(gu);
    const botten = gu.clientHeight - parseFloat(cs.paddingBottom || 0);
    return Math.floor(botten - (sist.offsetTop + sist.offsetHeight));
  }

  /* Passningen körs om när matematiken satts och typsnitten laddats — en
     KaTeX-formel är högre än platshållartexten, och mätte man före växte bladet
     efteråt. Därför måste den kunna köras flera gånger utan att räkna av två
     gånger: varje kort återställs först till sin budget. */
  /* Passningen körs om när matematiken satts och typsnitten laddats — en
     KaTeX-formel är högre än platshållartexten, och mätte man före växte bladet
     efteråt. Därför måste den kunna köras flera gånger utan att räkna av två
     gånger: allt den lägger till tas bort först. */
  function ater(gu) {
    $$('.guplats', gu).forEach(p => { p.style.height = ''; });
  }

  /* ── Delningen måste kunna ÅNGRAS ────────────────────
     formge() körs fyra gånger (direkt, nästa bildruta, efter 260 ms och när
     typsnitten laddats) eftersom en KaTeX-formel är högre än platshållaren.
     passa() tål det — den återställer varje kort först. delaArk() gjorde det
     inte: den delade ovanpå förra körningens delning, så samma arbetsblad kunde
     bli 2 blad en gång och 5 nästa, med «— fortsättning — fortsättning …»
     staplat i rubriken. Därför slås delningarna ihop före varje mätning: efter
     det finns exakt ett blad per dokument igen, och delningen räknas ur ett
     färdigsatt blad i stället för ur ett halvsatt. */
  function atervand(trav, v) {
    for (let varv = 0; varv < 8; varv++) {
      const del = $$('.gu[data-forts]', trav)[0];
      if (!del) break;
      const alla = $$('.gu', trav);
      const forra = alla[alla.indexOf(del) - 1];
      if (!forra) { del.removeAttribute('data-forts'); continue; }
      $$('.gukort', del).forEach(k => forra.appendChild(k));
      (del.closest('.blad') || del).remove();
    }
    $$('.gu .gutitel[data-titel]', trav).forEach(t => { t.textContent = t.dataset.titel; });
  }

  /* ── Passningen ──────────────────────────────────────
     Bladet bär bara svarsrader och lösbladshänvisningar, så det finns inga
     skrivytor att fördela. Kvar är en enda sak: bildplatsen får ge vika när det
     är trångt. Vilka uppgifter som går på lösblad säger uppgiften själv, där den
     står — bandet ska inte upprepa det. */
  function passa(trav, v) {
    if (v.typ !== 'Arbetsblad' && v.typ !== 'Gruppuppgift') return;
    $$('.gu', trav).forEach(gu => {
      ater(gu);
      /* Bildplatsen är det enda på bladet som kan ge vika, och den krymper i steg.
         Räcker inte det får bladet spilla — då delar delaArk() det. Att tyst
         kasta illustrationen vore att ta tillbaka ett val läraren gjort. */
      for (const h of ['92px', '76px', '60px']) {
        if (ledigt(gu) >= 0) break;
        $$('.guplats', gu).forEach(p => { p.style.height = h; });
      }
      /* Restluften rörs INTE. Mallen har 34 px mellan varje uppgift på vartenda
         blad — även #gu1, som har 345 px kvar nederst. Luften som blir över lägger
         sig nederst; ett blad med tre uppgifter ska inte spännas ut till att låta
         som sex. */
    });
  }

  /* Ett blad med fler uppgifter än som får plats delas — men först efter att
     bildplatserna krympt. Två papper är dyrare än en mindre bildruta. */
  /* En sida till kostar papper. Ett blad som spiller mindre än en rad (24 px)
     spiller inom mätfelet — figurer och formler sätter sig ett par pixlar hit
     eller dit — och ska inte bli två sidor. */
  const SPILL = 10;
  function delaArk(trav) {
    for (let varv = 0; varv < 4; varv++) {
      const gu = $$('.gu', trav).find(g => ledigt(g) < -SPILL && $$('.gukort', g).length > 1);
      if (!gu) break;
      const blad = gu.closest('.blad');
      const nytt = document.createElement('div');
      nytt.className = 'blad';
      const kopia = gu.cloneNode(false);
      kopia.dataset.forts = '';
      ['.guhuv', '.gutopp', '.guband'].forEach(sel => { const el = $(sel, gu); if (el) kopia.appendChild(el.cloneNode(true)); });
      nytt.appendChild(kopia);
      (blad || gu).insertAdjacentElement('afterend', nytt);
      for (let n = 0; n < 12; n++) {
        const kort = $$('.gukort', gu);
        if (kort.length <= 1 || ledigt(gu) >= 0) break;
        const sist = kort[kort.length - 1];
        const forsta = $('.gukort', kopia);
        if (forsta) forsta.before(sist); else kopia.appendChild(sist);
      }
    }
    /* Rubrikerna sätts EFTERÅT, ur den färdiga travens ordning: «forts. 2 (av 3)»
       säger var man är. Förr fick varje delning ' — fortsättning' klistrat på
       förra bladets redan klistrade rubrik — fyra staplade suffix i en 25 px
       rubrik. Originaltiteln sparas i data-titel så återvändningen kan läsa den. */
    const gruppen = $$('.gu', trav);
    const sidor = gruppen.length;
    if (sidor < 2) return;
    gruppen.forEach((g, n) => {
      const t = $('.guhuv .gutitel', g);
      if (!t) return;
      if (!t.dataset.titel) t.dataset.titel = t.textContent;
      t.textContent = n ? `${t.dataset.titel} — forts. ${n + 1} (av ${sidor})` : t.dataset.titel;
    });
  }

  /* ── Provet: ett ark som svämmar över får ett till ───
     Uppgifterna är inte lika stora, så del B ryms ibland på ett blad och
     ibland inte. I stället för att gissa mäts arket, och de uppgifter som inte
     får plats flyttas till ett nytt blad med samma huvud. */
  function paginera(trav) {
    for (let varv = 0; varv < 8; varv++) {
      const trangt = $$('.blad', trav).find(bl => {
        const ark = $('.ark[data-brytbar]', bl);
        return ark && ark.scrollHeight - ark.clientHeight > 0 && $$('.pruppg', ark).length > 1;
      });
      if (!trangt) break;
      const ark = $('.ark[data-brytbar]', trangt);
      const nytt = document.createElement('div');
      nytt.className = 'blad';
      const kopia = ark.cloneNode(false);
      const huvudet = $('.prhuvud', ark) || $('.lohuvud', ark);
      if (huvudet) kopia.appendChild(huvudet.cloneNode(true));
      nytt.appendChild(kopia);
      trangt.insertAdjacentElement('afterend', nytt);
      /* Flytta bakifrån tills arket ryms — och lämna alltid minst en uppgift kvar. */
      for (let n = 0; n < 12; n++) {
        const uppg = $$('.pruppg', ark);
        if (uppg.length <= 1 || ark.scrollHeight - ark.clientHeight <= 0) break;
        const sist = uppg[uppg.length - 1];
        if (kopia.firstElementChild && kopia.children.length > 1) kopia.children[1].before(sist);
        else kopia.appendChild(sist);
      }
      /* De flyttade hamnade i omvänd ordning om de sattes in före varandra —
         ordningen läses ur numret, som redan står på brickan. */
      const kvar = $$('.pruppg', kopia).sort((x, z) => parseInt($('.prnr', x).textContent, 10) - parseInt($('.prnr', z).textContent, 10));
      kvar.forEach(el => kopia.appendChild(el));
    }
  }

  /* ── Ritningen ───────────────────────────────────── */
  /* Tavlans hörnrad och rubrik.
     Förlagan bär en egen dag, längd och boksida. Står de kvar säger tavlan
     «To 14/1 · 90 min» medan planeringen säger måndag 45 min — och då tror man
     inte på någon av dem. Specen delas mellan dokument, så bara de objekt som
     faktiskt byts får en egen kopia — resten delas, och då överlever grafernas
     funktioner. */
  const DAGKORT = ['Sö', 'Må', 'Ti', 'On', 'To', 'Fr', 'Lö'];
  /* Sista raden på tavlan är inte en fotnot om förlagans bok — det är det
     eleverna ska skriva av: var man arbetar och vilka ord lektionen handlar om. */
  function tavlafot(v) {
    const bit = ['Välkomna!'];
    if (v.sidor) bit.push(`Arbeta i boken s. ${v.sidor}`);
    const begrepp = (v.gy || []).slice(0, 3).map(g => String(g).toLowerCase());
    if (begrepp.length) bit.push(`Begrepp: ${begrepp.join(', ')}`);
    return bit.join(' · ');
  }
  function tavlaSpec(spec, v) {
    if (!spec || !v) return spec;
    const min = Number((v.inst || {}).langd) || null;
    const dag = v.datum ? new Date(v.datum + 'T12:00:00') : null;
    /* Står en gruppuppgift på samma lektion hör den hemma i tavlans hörnrad — det
       är där läraren läser av lektionens uppsättning. */
    const gru = (window.Dokument && window.Dokument.sparade ? window.Dokument.sparade() : [])
      .filter(x => x && !x.losningsblad && x.typ === 'Gruppuppgift' && x.datum === v.datum && (!v.klass || x.klass === v.klass)).pop();
    const hornet = [
      dag && !isNaN(dag) ? `${DAGKORT[dag.getDay()]} ${dag.getDate()}/${dag.getMonth() + 1}` : null,
      min ? min + ' min' : null,
      gru ? `gruppuppgift ${Number((gru.inst || {}).langd) || 10} min` : null,
      (v.referenser || []).length ? v.referenser.map(r => r.namn).join(', ') : null
    ].filter(Boolean).join(' · ');
    const gjort = { horn: !hornet, rubrik: !v.moment, fot: false };
    const foten = tavlafot(v);
    const ga = x => {
      if (Array.isArray(x)) {
        let bytt = false;
        const ut = x.map(o => { const n = ga(o); if (n !== o) bytt = true; return n; });
        return bytt ? ut : x;
      }
      if (!x || typeof x !== 'object') return x;
      let ut = x;
      const satt = (k, val) => { if (ut === x) ut = Object.assign({}, x); ut[k] = val; };
      if (!gjort.horn && x.kind === 'text' && /^\S+ \d+\/\d+ · /.test(String(x.text || ''))) { satt('text', hornet); gjort.horn = true; }
      if (!gjort.rubrik && x.kind === 'heading') { satt('text', versal(v.moment)); gjort.rubrik = true; }
      if (!gjort.fot && x.kind === 'text' && /^Suddas efter lektionen/.test(String(x.text || ''))) { satt('text', foten); gjort.fot = true; }
      Object.keys(x).forEach(k => {
        const b = x[k];
        if (!b || typeof b !== 'object') return;
        const ny = ga(b);
        if (ny !== b) satt(k, ny);
      });
      return ut;
    };
    /* Vilka sidor och uppgifter som gäller skrivs upp i VÄNSTERSPALTEN — det är
       där läraren alltid skriver dem, och det är det första eleverna kopierar.
       Utan raden räknar någon på fel sida. */
    return attRakna(ga(spec), v);
  }

  /* Listan är dokumentets egen (v.bokuppg), inte planeringens nuvarande: en tavla
     som redan ligger i Sparat ska peka på de uppgifter den skrevs för även efter
     att sidspannet ändrats i planeringen. Samma snärt gäller kvittot i Att skriva
     ut — båda läser samma snål lista. */
  function attRakna(spec, v) {
    const b = v.bokuppg;
    if (!spec || !b || !b.remsa || !spec.columns || !spec.columns.length) return spec;
    const kol = spec.columns[0];
    const rader = kol.sections.slice();
    /* Spaltens sista rad är den röda linjen under felnoten. Utan luft under den
       läses «Att räkna» som en del av varningen. */
    const sist = rader[rader.length - 1];
    if (sist && sist.kind === 'underline') rader[rader.length - 1] = Object.assign({}, sist, { gapAfter: 20 });
    rader.push({ kind: 'text', text: 'Att räkna', size: 22, weight: 'bold', gapAfter: 6 });
    rader.push({ kind: 'text', text: `Boken s. ${v.sidor || b.sidor}`, size: 19, gapAfter: 2 });
    rader.push({ kind: 'text', text: `Uppg ${b.remsa}`, size: 19, gapAfter: 2 });
    const ut = Object.assign({}, spec, { height: (spec.height || 460) + 78 });
    ut.columns = spec.columns.slice();
    ut.columns[0] = Object.assign({}, kol, { sections: rader });
    return ut;
  }

  /* Tavlan språkmodellen skrivit (wb-json-v1) om den finns — annars prototypens
     form ur innehall.js. Formen är densamma för motorn; det som skiljer är
     varifrån innehållet kom. */
  function tavlanFor(v) {
    const lage = TEORI.test(ord(v.moment)) ? 'teori' : 'genomgang';
    const skriven = v.wb && (v.wb.boards || []).length ? v.wb : null;
    return tavlaSpec(skriven || (T().spec ? T().spec(v.moment, lage) : null), v);
  }

  /* Tavlan ritad i sin verkliga storlek någon annanstans än på pappret.
     Bildproducenten (tavla-bild.js) ska ha SAMMA spec och SAMMA motor som
     förhandsvisningen — annars är bilden av en annan tavla än den läraren
     godkände. Returnerar brädenas container, eller null om tavlan inte gick
     att rita. Målet måste sitta i dokumentet: motorn mäter. */
  function tavlaTill(mal, v) {
    if (!mal || !v || v.typ !== 'Tavla') return null;
    const ruta = document.createElement('div');
    ruta.className = 'tavruta';
    mal.appendChild(ruta);
    ritaTavlan(ruta, tavlanFor(v), v, true);
    return $('.boards-container', ruta);
  }

  function rita(mal, v) {
    if (!mal || !v) return;
    mal.innerHTML = '';
    const trav = document.createElement('div');
    trav.className = 'bladtrav';
    trav.dataset.typ = v.typ;
    mal.appendChild(trav);

    if (v.typ === 'Tavla') {
      const ruta = document.createElement('div');
      ruta.className = 'tavruta';
      const host = document.createElement('div');
      host.className = 'tavhost';
      ruta.appendChild(host);
      trav.appendChild(ruta);
      ritaTavla(ruta, host, tavlanFor(v), v);
    } else {
      bladen(v).forEach(html => {
        const skal = document.createElement('div');
        skal.className = 'blad';
        skal.innerHTML = html;
        trav.appendChild(skal);
      });
    }

    /* Lösningsförslaget till bokens uppgifter är lärarens eget papper och ligger
       sist i samma trav — inte i ett eget dokument. Urvalet är dokumentets egen
       lista (v.bokuppg), samma som tavlans vänsterspalt skriver upp; ett
       lösningsblad får det inte en andra gång. */
    if (window.BokLosning && !v.losningsblad) window.BokLosning.blad(v).forEach(html => {
      const skal = document.createElement('div');
      skal.className = 'blad';
      skal.innerHTML = html;
      trav.appendChild(skal);
    });

    huvud(trav, v);
    planval(trav, v);
    grupphuvud(trav, v);
    arkhuvud(trav, v);
    markera(trav, v);
    skala(trav);
    kompilera(trav);
    /* Sättningen måste vara klar innan bladet mäts: en KaTeX-formel är högre än
       platshållaren, och en figur högre än sin tomma ruta. */
    /* Ångra, dela på de FULLA ytorna, passa sedan varje blad för sig. Delade man
       efter passningen såg delaArk ett blad som «nästan rymdes» — därför att
       passningen kastat ut alla skrivytor till lösblad. */
    const formge = () => { atervand(trav, v); delaArk(trav); passa(trav, v); paginera(trav); };
    formge();
    requestAnimationFrame(formge);
    setTimeout(formge, 260);
    if (document.fonts && document.fonts.status !== 'loaded') document.fonts.ready.then(() => setTimeout(formge, 60));
    /* Bilderna läraren själv lagt in på en uppgift följer dokumentet, inte formen. */
    Object.entries(v.bilder || {}).forEach(([nyckel, src]) => {
      const el = $(`[data-el="${nyckel}"] .prbild, [data-el="${nyckel}"] .gufigur`, trav);
      if (el) el.innerHTML = `<img src="${src}" alt="" style="display:block;width:100%;height:auto" />`;
    });
    return trav;
  }

  return { rita, form, uppgifter, skala, omritaTavlor, tavlaTill };
})();
