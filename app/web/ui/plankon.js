/* ══════════ PLANERINGSKÖN ══════════
   Veckan är ett val, inte en genväg. Man klickar de lektioner man vill planera
   i klassvyn och de STANNAR blå — flera går bra, också över klassgränsen. Valet
   ÄR starten: kön sätts i samma klick, och sedan
   planeras en lektion i taget: hela stapeln för den ena, klart, upp igen, nästa.
   Remsan högst upp säger alltid vilken lektion man står i och hur många som
   är kvar, så att steg 2–4 aldrig blir anonyma. */
window.PlanKo = (() => {
  const $ = (s, r = document) => r.querySelector(s);
  const panel = $('#vy-planering .panel');
  if (!panel) return { vaxla: () => false, har: () => false, arNu: () => false, starta: () => true, klar: () => {} };

  const K = window.Kalender;
  const nyckel = p => `${p.datum}|${p.tid}|${p.klass}|${p.kurs || p.titel || ''}`;
  const dagtext = d => new Date(d + 'T12:00:00').toLocaleDateString('sv-SE', { weekday: 'short', day: 'numeric', month: 'short' }).replace(/\./g, '');
  const etikett = p => [p.titel || p.kurs, p.klass, `${dagtext(p.datum)} ${p.tid}`].filter(Boolean).join(' · ');
  const kortnamn = p => `${(p.titel || p.kurs).replace('Matematik ', 'Ma ')}${p.klass ? ' · ' + p.klass : ''} ${p.tid.split('–')[0]}`;

  /* ── Schemat äger kursen ──
     En post i kön kan bli ÄLDRE än schemat: kalendern synkas om medan man
     planerar, och rutan som var «Matematik, nivå 2c» när man klickade är
     «Matematik, nivå 1c» nästa gång veckan ritas. Posten låg kvar med sin gamla
     kurs, och eftersom `nyckel` bär kursen kände `har()` inte igen kortet — ett
     nytt klick la in samma lektion en gång till, och den GAMLA sorterades först
     och blev den som planerades. Följderna var tysta: remsan sa 2c på en
     1c-lektion, hyllan har ingen bok märkt 2c så boken föll tillbaka på den
     inlärda, och kalenderns sidor för dagen hittades inte alls (innehallFor
     slår på kursen — «sidorna var inte förvalda»).

     Finns en schemarad för dagen, klassen och timmen är dess kurs sanningen.
     Utanför schemat — prov på annan dag, ett eget kort — står postens egen kvar. */
  const minut = t => { const m = String(t || '').match(/(\d{1,2})[:.](\d{2})/); return m ? +m[1] * 60 + +m[2] : null; };
  function farsk(post) {
    if (!post || !post.datum || !K || !K.schemaFor) return post;
    const t = minut(post.tid);
    const rad = K.schemaFor(post.datum)
      .find(s => s.klass === post.klass && (t == null || minut(s.tid) === t));
    if (!rad || !rad.kurs || rad.kurs === post.kurs) return post;
    return Object.assign({}, post, { kurs: rad.kurs, sal: rad.sal || post.sal });
  }

  let valda = [], ko = [], i = -1, slutfort = false;

  const remsa = document.createElement('div');
  remsa.className = 'konrad';
  remsa.hidden = true;
  remsa.innerHTML = '<span class="konnu"></span><span class="konlekt"></span><span class="konprickar"></span><span class="konknappar"></span>';
  panel.insertBefore(remsa, panel.firstChild);

  /* Läses schemat om medan kön står kvar ska kön följa med — och två poster som
     visar sig vara SAMMA lektion blir en. Utan hopslagningen låg den gamla kvar
     först i turordningen (samma dag och timme sorterar lika) och var den som
     planerades. */
  function friska(lista) {
    const ut = [];
    lista.forEach(p => {
      const f = farsk(p);
      if (!ut.some(x => nyckel(x) === nyckel(f))) ut.push(f);
    });
    return ut;
  }
  const ordna = () => {
    valda = friska(valda).sort((a, b) => (a.datum + a.tid).localeCompare(b.datum + b.tid));
    if (i > -1 && ko.length) {
      const forra = ko[i];
      ko = friska(ko);
      i = ko.length ? Math.max(0, ko.findIndex(p => nyckel(p) === nyckel(farsk(forra)))) : -1;
    }
  };

  function fyll(post) {
    const p = farsk(post);
    const k = $('#p-klass'), ku = $('#p-kurs'), d = $('#p-datum'), t = $('#p-tid');
    /* Ingen lektion vald betyder tomma fält. Står de kvar stämplas nästa dokument
       med en lektion läraren just tagit bort. */
    if (!p) {
      [ku, k, d, t].forEach(f => { if (f && f.value) { f.value = ''; f.dispatchEvent(new Event('change', { bubbles: true })); } });
      return;
    }
    if (ku) { ku.value = p.kurs; ku.dispatchEvent(new Event('change', { bubbles: true })); }
    if (k) { k.value = p.klass; k.dispatchEvent(new Event('change', { bubbles: true })); }
    if (d) { d.value = p.datum; d.dispatchEvent(new Event('change', { bubbles: true })); }
    if (t) { t.value = p.tid || ''; t.dispatchEvent(new Event('change', { bubbles: true })); }
    /* Står det prov i kalendern är typen redan bestämd — steg 2 öppnar med Prov. */
    if (p.slag === 'prov' && window.SattLage) window.SattLage('Prov');
    window.Utgang && window.Utgang.rita();
  }

  function ritaVal() {
    const rad = $('#planvald'), ingen = $('#planingen');
    if (ingen) ingen.hidden = valda.length > 0;
    window.Klass && window.Klass.ritaVal && window.Klass.ritaVal();
    window.PlanRubrik && window.PlanRubrik();
    if (!rad) return;
    if (!valda.length) { rad.hidden = true; rad.textContent = ''; return; }
    rad.hidden = false;
    rad.innerHTML = valda.length === 1
      ? 'Planerar <b></b>'
      : '<b></b> — de planeras en i taget, i turordning';
    $('b', rad).textContent = valda.length === 1 ? etikett(valda[0]) : `${valda.length} lektioner valda`;
  }

  /* Läget i kön står i klartext. Prickar går inte att läsa av: man ser att det
     finns två, inte om den ena är avklarad. */
  function lagetext(klara) {
    const kvar = Math.max(0, ko.length - klara);
    return `<span class="konlage"><b>${klara}</b> klar${klara === 1 ? '' : 'a'} · <b>${kvar}</b> kvar</span>`;
  }

  /* Remsan ligger utanför flödet — då måste panelen själv göra plats för den,
     annars trycker den mot steg 1:s rubrik. */
  const konTag = () => panel.toggleAttribute('data-kon', !remsa.hidden);

  function ritaRemsa() {
    /* Remsan och kvittoraden säger samma sak — så en av dem åt gången. Ligger en
       lektion i kön är remsan sanningen; annars står kvittot där. */
    const kvitto = $('#lektionsrad');
    if (kvitto) kvitto.hidden = i > -1;
    if (i < 0 || !ko.length) { remsa.hidden = true; remsa.removeAttribute('data-lage'); konTag(); return; }
    remsa.hidden = false;
    konTag();
    const p = ko[i];
    const klarLage = remsa.dataset.lage === 'klar' || remsa.dataset.lage === 'slut';
    $('.konprickar', remsa).innerHTML = lagetext(i);
    if (!klarLage) {
      remsa.dataset.lage = 'planerar';
      $('.konnu', remsa).textContent = ko.length > 1 ? `Planerar ${i + 1} av ${ko.length}` : 'Planerar';
      $('.konlekt', remsa).textContent = etikett(p);
      $('.konknappar', remsa).innerHTML = '<button class="lank" type="button" data-avbryt>Avbryt kön</button>';
    }
  }

  /* ── Valet i veckan ──
     Valet är kön: det finns ingen startknapp mellan dem. Så länge man står på
     första lektionen skrivs kön om vid varje klick i schemat — lägger man till en
     fjärde lektion planeras fyra. Har man planerat sig vidare (i > 0) ligger kön
     fast, och nya klick lägger bara till sist. */
  function synk() {
    if (i > 0) return;
    ko = valda.slice();
    i = valda.length ? 0 : -1;
    slutfort = false;
    remsa.removeAttribute('data-lage');
    fyll(valda[0]);
    ritaRemsa();
    window.Klass && window.Klass.rita && window.Klass.rita();
  }
  function vaxla(post) {
    valda = friska(valda);
    const n = nyckel(farsk(post));
    const fanns = valda.findIndex(p => nyckel(p) === n);
    if (fanns > -1) valda.splice(fanns, 1);
    else valda.push(Object.assign({}, farsk(post)));
    ordna();
    synk();
    ritaVal();
    return fanns === -1;
  }
  /* Igenkänningen går genom `farsk` på BÅDA sidor: annars slutar kortet i veckan
     matcha sin egen post i kön så fort schemat läses om, och lektionen ser
     omarkerad ut trots att den ligger i kön. */
  const samma = (a, b) => nyckel(farsk(a)) === nyckel(farsk(b));
  const har = post => valda.some(p => samma(p, post));
  const arNu = post => i > -1 && ko[i] && samma(ko[i], post);
  /* Avklarade lektioner är de kön redan passerat. Veckan läser av dem för att
     kunna säga «Klar» i stället för «Vald» — med två klasser i kön är det den
     enda platsen där man ser var man är. */
  const arKlar = post => (slutfort ? ko : ko.slice(0, Math.max(0, i))).some(p => samma(p, post));

  /* ── Kön ── */
  function starta() {
    if (!valda.length || i > -1) return true;
    ko = valda.slice();
    i = 0;
    fyll(ko[0]);
    remsa.removeAttribute('data-lage');
    ritaRemsa();
    window.Klass && window.Klass.rita && window.Klass.rita();
    return true;
  }

  /* Ett dokument är skrivet — lektionen är planerad. Kön går vidare av sig själv
     vid godkännandet, så det här läget är alltid det sista: kvar står vad som
     händer efter planeringen — att bära in papperen. */
  function klar() {
    if (i < 0 || !ko.length) return;
    remsa.hidden = false;
    konTag();
    slutfort = true;
    window.Klass && window.Klass.ritaVal && window.Klass.ritaVal();
    remsa.dataset.lage = 'slut';
    $('.konnu', remsa).textContent = ko.length > 1
      ? `Alla ${ko.length} lektioner planerade`
      : 'Lektionen är planerad';
    $('.konlekt', remsa).textContent = etikett(ko[i]);
    /* En kö på EN lektion behöver ingen räknare: «1 klar · 0 kvar» säger samma sak
       som «Lektionen är planerad», och tar den plats lektionens namn behöver. */
    $('.konprickar', remsa).innerHTML = ko.length > 1 ? lagetext(i + 1) : '';
    const papper = ((window.Dokument && window.Dokument.sparade()) || [])
      .some(v => v.datum === ko[i].datum && (!ko[i].klass || v.klass === ko[i].klass));
    $('.konknappar', remsa).innerHTML = (papper ? '<button class="chip" type="button" data-tryck>Skriv ut papperen</button>' : '')
      + '<button class="lank" type="button" data-avbryt>Stäng</button>';
    setTimeout(() => {
      const r = remsa.getBoundingClientRect();
      const mal = Math.max(0, r.top + window.scrollY - 120);
      window.rullaTill ? window.rullaTill(mal, 700) : window.scrollTo(0, mal);
    }, 420);
  }

  /* Det andra dokumentet i paret är kvar innan lektionen är klar. Remsan ska
     säga det — inte stå kvar och påstå att ingenting hänt. */
  function vantar(typ) {
    if (i < 0 || !ko.length) return;
    remsa.hidden = false;
    konTag();
    remsa.dataset.lage = 'klar';
    $('.konprickar', remsa).innerHTML = lagetext(i);
    $('.konnu', remsa).textContent = ko.length > 1 ? `Planerar ${i + 1} av ${ko.length}` : 'Planerar';
    $('.konlekt', remsa).textContent = `${etikett(ko[i])} — ${String(typ).toLowerCase()} kvar att skriva`;
    $('.konknappar', remsa).innerHTML = '<button class="lank" type="button" data-avbryt>Avbryt kön</button>';
  }

  function nasta() {
    if (i >= ko.length - 1) return avbryt();
    const forra = ko[i];
    i++;
    const samma = !!(forra && ko[i] && forra.kurs === ko[i].kurs);
    /* Men kalendern kan säga vad just DEN lektionen ska göra — lärarens egen
       grovplanering, rad för rad (innehallFor). Då är «samma kurs» inget skäl
       att låta förra lektionens spann stå kvar: NA26F har nittio minuter och
       s. 2–6, TE26A har sextio och s. 2–4, båda i Matematik, nivå 1c samma dag.
       Förvalet blev NA26F:s sidor på TE26A:s lektion. Står ingenting om den nya
       lektionen gäller boköppningen som förut — det är då det enda vi vet. */
    const kalendern = !!(K && K.innehallFor && ko[i]
      && K.innehallFor(ko[i].datum, ko[i].klass, ko[i].kurs, ko[i].tid));
    const bevara = samma && !kalendern;
    fyll(ko[i]);
    const m = $('#moment');
    if (m) { m.value = ''; m.dispatchEvent(new Event('input', { bubbles: true })); }
    /* Nästa lektion är ofta en annan klass. Då får ingenting följa med som hör
       till den förra: förlagan, det centrala innehållet och boksidorna pekar alla
       på fel kurs. De sätts om ur klassprofilen för den nya klassen i stället. */
    window.Dokument && window.Dokument.slappForlaga && window.Dokument.slappForlaga();
    if (!samma && window.GyVal && window.GyVal.rensa) window.GyVal.rensa();
    remsa.removeAttribute('data-lage');
    ritaRemsa();
    window.Klass && window.Klass.rita && window.Klass.rita();
    window.SlappAndraHand && window.SlappAndraHand();
    if (window.PlanSteg) { window.PlanSteg.omstart(false); window.PlanSteg.las(2); }
    /* Momentet följer INTE med till nästa lektion: nästa klass är ofta en annan
       kurs, och «5.1 Derivatans definition» i Matematik 4 är fel bok. Uppslaget
       sätts om bara när kursen är densamma. */
    if (bevara && window.Uppslag && window.Uppslag.satt) {
      const s = window.Uppslag.spann();
      if (s && s.fran) window.Uppslag.satt(s.fran, s.till);
    }
    /* Samma förval som när man klickar lektionen i veckan — klassens bok, sidorna
       efter dess förra lektion, dess centrala innehåll och det den brukar få. */
    if (!bevara && window.Profil && window.Profil.anvand) window.Profil.anvand(ko[i], ko[i].slag === 'prov' ? 'Prov' : null);
    window.Klass && window.Klass.speglaFinns && window.Klass.speglaFinns(ko[i]);
    window.toast && window.toast(`Planerar ${kortnamn(ko[i])} — ${ko.length - i - 1} kvar efter den`);
    /* Man ska landa i steg 1 för nästa klass, inte där förra dokumentet låg. */
    setTimeout(() => {
      const r = panel.getBoundingClientRect();
      const mal = Math.max(0, r.top + window.scrollY - 96);
      window.rullaTill ? window.rullaTill(mal, 700) : window.scrollTo(0, mal);
    }, 140);
  }

  function avbryt() {
    ko = []; i = -1; valda = []; slutfort = false;
    remsa.hidden = true;
    konTag();
    remsa.removeAttribute('data-lage');
    const kvitto = $('#lektionsrad');
    if (kvitto) kvitto.hidden = false;
    window.Profil && window.Profil.slapp && window.Profil.slapp(true);
    window.Dokument && window.Dokument.slappForlaga && window.Dokument.slappForlaga();
    fyll(null);
    ritaVal();
    window.Klass && window.Klass.rita && window.Klass.rita();
  }

  remsa.addEventListener('click', e => {
    if (e.target.closest('[data-tryck]')) {
      const p = ko[i];
      if (!(window.Tryck && window.Tryck.lektion && window.Tryck.lektion(p))) {
        window.toast && window.toast('Inga godkända papper på den här lektionen än');
      }
      return;
    }
    if (e.target.closest('[data-nasta]')) nasta();
    else if (e.target.closest('[data-avbryt]')) avbryt();
  });

  /* Omprovet väljer EN dag och startar direkt. Kön sätts om i ett svep — utan
     avbryt(), som också skulle släppa förvalen omprovet just har fyllt i. */
  function enbart(post) {
    valda = [Object.assign({}, farsk(post))];
    ko = valda.slice();
    i = 0;
    fyll(ko[0]);
    ritaVal();
    remsa.removeAttribute('data-lage');
    ritaRemsa();
    return true;
  }

  return { vaxla, har, arNu, arKlar, starta, klar, nasta, avbryt, enbart, vantar, harFler: () => i > -1 && i < ko.length - 1, aktiv: () => (i > -1 ? ko[i] : null), valda: () => valda.slice() };
})();
