/* ══════════ UTSKRIFTSPAKETET ══════════
   «Det här ska skrivas ut» som en enda gest. Appen vet vad lektionen består av
   och packar högen själv: tavlan överst, elevernas papper under, facit sist.
   Anpassade kopior (post 11) är rader i paketet — en egenskap hos KOPIAN, aldrig
   en etikett på pappret. Sammanräkningen står i knappen, före utskriften. */
(() => {
  const $ = s => document.querySelector(s);
  const ruta = $('#tryckruta');
  if (!ruta) return;

  const SIDOR = { Tavla: 1, Prov: 3, Arbetsblad: 2, Gruppuppgift: 1, Anteckningar: 1 };
  /* Sidantalet ska vara bladens, inte en tabell som gissar: formen vet exakt hur
     många ark dokumentet består av. En tavla är ett ark — den stod som två. */
  const sidorFor = v => {
    /* Tavlan är ETT papper i förhandsvisningen men ett bräde per sida i
       utskriften — räkningen ska vara högens, inte skärmens. */
    if (v.typ === 'Tavla' && window.TavlaBild) return window.TavlaBild.antal(v);
    const f = window.Blad && window.Blad.form ? window.Blad.form(v) : null;
    return (f && f.length) || SIDOR[v.typ] || 2;
  };
  let rader = [], titel = '';

  function packa(namnPaPaketet, dokument) {
    titel = namnPaPaketet;
    /* Anteckningarna ligger överst i högen, före tavlan: det är pappret läraren
       håller i medan hon säger det som står på tavlan. */
    const ordning = { Anteckningar: -1, Tavla: 0, Prov: 1, Arbetsblad: 1, Facit: 2 };
    /* Elevmaterialet trycks i klassuppsättning, lärarens papper i ETT exemplar.
       Anteckningarna är lärarens — tjugotvå kopior av hennes stödpapper är
       tjugoett papper i papperskorgen. */
    const LARARENS = { Tavla: 1, Anteckningar: 1 };
    rader = dokument.map(v => ({
      v,
      namn: window.Dokument.namn(v),
      typ: v.losningsblad ? 'Facit' : v.typ,
      under: v.losningsblad
        ? 'Din kopia · enkelsidig'
        : v.typ === 'Tavla' ? 'Din genomgång · enkelsidig'
        : v.typ === 'Anteckningar' ? 'Ditt stödpapper · enkelsidig'
        : 'Standard · dubbelsidig',
      antal: v.losningsblad ? 1 : LARARENS[v.typ] || 22,
      sidor: sidorFor(v),
      med: true
    })).sort((a, b) => (ordning[a.typ] ?? 1) - (ordning[b.typ] ?? 1));
    /* Formelbladet är en bilaga i provet — samma dokument, sista sidan — men
       den kan skrivas ut med eller utan i paketet. Ingen fjärde dokumenttyp. */
    const prov = rader.find(r => r.typ === 'Prov' && r.v.inst && r.v.inst.formelblad);
    if (prov) rader.splice(rader.indexOf(prov) + 1, 0, {
      v: prov.v, namn: 'Formelblad · ' + (prov.v.kurs || 'kursen'), typ: 'Bilaga',
      under: `Bilaga, sida ${sidorFor(prov.v) + 1} — härledd ur uppgifterna, skrivs ut med provet`,
      antal: prov.antal, sidor: 1, med: true
    });
    /* Lösningsförslaget till BOKENS uppgifter är lärarens eget ark, inte ett
       facit till uppgifter appen skrivit — det hör därför sist i högen, där
       facit ligger, och räknas som en kopia. Urvalet är dokumentets egen lista
       (v.bokuppg), samma som tavlans vänsterspalt skriver upp. */
    rader.filter(r => !r.v.losningsblad && r.v.bokuppg && r.v.bokuppg.losning && r.v.bokuppg.losning.antal)
      .forEach(r => {
        const l = r.v.bokuppg.losning;
        rader.push({
          v: r.v, bok: true,
          namn: `Lösningsförslag · boken s. ${r.v.bokuppg.sidor}`, typ: 'Facit',
          under: `${l.antal} uppgifter (${l.niva.toLowerCase()}) · uppg ${l.remsa} · din kopia · enkelsidig`,
          /* Sidorna är arken BokLosning faktiskt sätter — svarsfacit, bedömd
             elevlösning per nivå 3-uppgift, nivå 3-facit — inte en gissning ur
             uppgiftsantalet. Paginerar ett ark sig blir det ändå en sida till;
             raden är alltså en undre gräns, och kvittot räknar det riktiga. */
          antal: 1, med: true,
          sidor: Math.max(1, (window.BladBild && window.BladBild.antal(r.v))
                              || Math.ceil(l.antal / 4))
        });
      });
    rita();
    ruta.hidden = false;
  }

  function rita() {
    $('#trycktitel').textContent = 'Att skriva ut · ' + titel;
    const lista = $('#trycklista');
    lista.innerHTML = '';
    rader.forEach((r, i) => {
      const rad = document.createElement('div');
      rad.className = 'tryckrad';
      rad.innerHTML = `<span class="refminis" data-typ="${r.typ}">${r.typ[0]}</span><span><span class="trycknamn"></span><span class="tryckunder"></span></span><span class="tryckantal">${r.antal} ex · ${r.sidor} sid</span><button class="lank" type="button">${r.med ? 'Utelämna' : 'Ta med'}</button>`;
      rad.querySelector('.trycknamn').textContent = r.namn;
      rad.querySelector('.tryckunder').textContent = r.under;
      rad.style.opacity = r.med ? '1' : '.45';
      rad.querySelector('button').addEventListener('click', () => { rader[i].med = !rader[i].med; rita(); });
      lista.appendChild(rad);
    });
    const med = rader.filter(r => r.med);
    const sidor = med.reduce((a, r) => a + r.antal * r.sidor, 0);
    $('#tryckskicka').textContent = `Skriv ut ${med.length} ${med.length === 1 ? 'dokument' : 'dokument'} · ${sidor} sidor`;
    $('#tryckskicka').disabled = !med.length;
  }

  /* Anpassad kopia: förlängd tid, färre uppgifter, luftigare sättning. Väljs
     per kopia, syns bara i sättningen och i dokumentkoden i foten. */
  $('#tryckanpassad').addEventListener('click', () => {
    const bas = rader.find(r => r.typ === 'Prov' || r.typ === 'Arbetsblad');
    if (!bas) return;
    if (rader.some(r => r.anpassad)) { window.toast && window.toast('Det finns redan en anpassad kopia i paketet'); return; }
    const i = rader.indexOf(bas);
    rader.splice(i + 1, 0, {
      v: bas.v, namn: bas.namn, typ: bas.typ, anpassad: true,
      under: '4 uppgifter · 150 min · luftigare sättning, 13 pt · koden i foten skiljer den',
      antal: 2, sidor: bas.sidor, med: true
    });
    bas.antal = Math.max(1, bas.antal - 2);
    rita();
    window.toast && window.toast('Anpassad kopia tillagd — ingen etikett på pappret', 'Ångra', () => {
      rader = rader.filter(r => !r.anpassad);
      bas.antal += 2;
      rita();
    });
  });

  /* ══════════ PAKETET PÅ RIKTIGT ══════════
     Knappen räknade ihop högen och sa «Utskrivet» efter niohundra
     millisekunder. Servern bygger den nu: provets och arbetsbladets PDF:er
     (byggda vid godkännandet), tavlan som bild, facit bredvid provet — i den
     här ordningen, med kopiorna I FILEN. En lärare som ska ha 22 elevark, en
     tavla och ett facit kan inte säga det i en skrivardialog som har ETT
     kopieantal för hela jobbet.

     Utan server spelas prototypens kvittering upp precis som förut. */
  const serverPa = () => !!(window.API && window.API.pa);
  /* Tavlan finns bara som ritad DOM i webbläsaren — servern kan inte rendera om
     den, för motorn bor här och inte där. Den ritas därför av på klienten
     (tavla-bild.js) och skickas med som PNG; servern lägger bilden på ett A4
     överst i paketet. Går avritningen inte igenom hamnar tavlan i `saknas` och
     kvittot säger det, i stället för att paketet tyst blir en sida kortare. */

  function paketkropp() {
    const med = rader.filter(r => r.med);
    return Promise.all(med.map(r => {
      const d = { namn: r.namn, typ: r.typ, kopior: r.antal };
      /* Lösningsförslaget till BOKENS uppgifter ritas bara i webbläsaren
         (BokLosning) — det finns ingen byggd fil på servern. Raden delar
         dokument med sitt original, så utan den här avfarten skulle den få
         originalets EGEN pdf under bokens namn.
         Förr slutade avfarten här: utan id hamnade raden i `saknas`, och
         kvittot sa det. Sant, men inte till någon nytta — läraren såg arken på
         skärmen och fick dem aldrig på papper. Nu ritas de av precis som
         tavlan (blad-bild.js) och skickas som en lista PNG:er, ett ark per
         sida. `saknas`-vägen står kvar som fallback: går avritningen inte
         igenom skickas ingen bild, och kvittot säger det igen. */
      if (r.bok) {
        if (!window.BladBild) return d;
        return window.BladBild.boklos(r.v)
          .then(ark => (ark.length ? Object.assign(d, { png: ark.map(a => a.png) }) : d))
          .catch(() => d);
      }
      /* Anteckningarna ligger i samma tabell som proven på servern, så
         paketets exam-gren hämtar deras PDF utan en rad ny kod — men utan
         bedömning och utan anpassad kopia: det finns ingen bedömning att lägga
         bredvid, och en anpassad kopia av lärarens eget papper är ingenting. */
      if (r.v && r.v.antId) d.exam_id = r.v.antId;
      if (r.v && r.v.provId) {
        d.exam_id = r.v.provId;
        /* Provets lösningsförslag ÄR bedömningsanvisningen; arbetsbladets är
           det separata facit. Två skilda filer, båda bredvid dokumentets egen
           PDF. Raden bad förut om bedömningen för båda, och arbetsbladets
           facit hamnade därför alltid i `saknas`. */
        if (r.typ === 'Facit') d[r.v.typ === 'Prov' ? 'bedomning' : 'facit'] = true;
        if (r.anpassad) d.anpassad = {
          /* Samma anpassning som raden beskriver: förlängd tid, färre
             uppgifter, och en kod i foten som skiljer kopian. */
          tid_min: 150, antal: 4,
          kod: `${(r.v.klass || 'kopia')}-${(r.v.datum || '').slice(5)}`,
        };
      }
      if (r.typ !== 'Tavla' || !window.TavlaBild) return d;
      /* Ett bräde per sida, som en lista — samma väg som bokens ark. Hela
         remsan i en bild blev en rand mitt på ett A4; nu fyller varje bräde
         sin egen liggande sida (tryck.png_till_pdf väljer orienteringen). */
      return window.TavlaBild.sidor(r.v)
        .then(png => Object.assign(d, { png }))
        .catch(() => d);      /* utan bild går raden till `saknas` — och sägs */
    })).then(dokument => ({ titel, dokument }));
  }

  function bygg(knapp, tillagg, efterat) {
    const text = knapp.textContent;
    knapp.disabled = true;
    /* Avritningen av tavlan tar sina hundradelar och sker före anropet —
       knappen ska säga vad den gör, inte stå tyst. */
    knapp.textContent = rader.some(r => r.med && (r.typ === 'Tavla' || r.bok))
      ? 'Ritar av …' : 'Bygger paketet …';
    const ater = () => { knapp.textContent = text; knapp.disabled = false; };
    paketkropp().then(kropp => {
      knapp.textContent = 'Bygger paketet …';
      return window.API.strom('/api/tryck', Object.assign(kropp, tillagg), {
        log: m => { knapp.textContent = String(m || '').slice(0, 40); },
      });
    }).then(res => {
      if (!res) throw new Error('Servern slutade svara mitt i bygget.');
      efterat(res);
      ater();
    }).catch(e => {
      ater();
      window.toast && window.toast(e.message || 'Paketet gick inte att bygga.');
    });
  }

  $('#tryckskicka').addEventListener('click', () => {
    const b = $('#tryckskicka');
    if (!serverPa()) {
      const text = b.textContent;
      b.disabled = true;
      b.textContent = 'Skickar till skrivaren …';
      setTimeout(() => {
        b.textContent = 'Utskrivet';
        window.toast && window.toast('Papperen ligger i rätt ordning i utskriftskön');
        setTimeout(() => { b.textContent = text; b.disabled = false; }, 1600);
      }, 900);
      return;
    }
    /* «Skriv ut» förblir EN hopfogad fil — det är hela poängen med högen:
       kopiorna ligger i den och bunten är rätt när den kommer ur maskinen. */
    bygg(b, {}, res => {
      /* Paketet öppnas i systemets PDF-läsare — där skrivardialogen bor.
         Appen har ingen egen skrivarkö och ska inte låtsas ha det. */
      window.API.json('/api/open', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: res.path }),
      }).catch(() => {});
      window.toast && window.toast(kvittotext(res));
    });
  });
  /* Nedladdningen är motsatsen: skilda filer i en egen mapp. En lärare som
     sparar undan lektionens material vill ha tavlan, provet och facit var för
     sig — inte en enda PDF att bläddra i när hon letar efter facit. Zip valdes
     bort (ett steg till att packa upp) och likaså flera nedladdningar i rad
     (webbläsare stoppar dem som «multipla nedladdningar»). */
  $('#trycksampdf').addEventListener('click', () => {
    const b = $('#trycksampdf');
    if (!serverPa()) { window.toast && window.toast('Nedladdade — ett dokument per fil'); return; }
    bygg(b, { separat: true }, res => {
      window.API.json('/api/reveal', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: res.path }),
      }).catch(() => {});
      window.toast && window.toast(kvittotext(res));
    });
  });

  /* Kvittot säger vad som FAKTISKT hamnade i filen — och vad som inte gjorde
     det. Ett paket som tyst blev en sida kortare upptäcks framför kopiatorn. */
  const kvittotext = res => {
    const sidor = `${res.sidor} ${res.sidor === 1 ? 'sida' : 'sidor'}`;
    const antal = (res.filer || []).length;
    const brist = (res.saknas || []).length
      ? ` ${res.saknas.join(', ')} kom inte med: ett papper som inte är godkänt har ingen PDF än.`
      : '';
    if (res.mapp) return `${antal} ${antal === 1 ? 'fil' : 'filer'} i en egen mapp — ${sidor}, mappen är öppnad.${brist}`;
    /* «I rätt ordning» sägs bara när ordningen faktiskt är hel. */
    return brist ? `Paketet är byggt — ${sidor}.${brist}`
                 : `Paketet är byggt — ${sidor} i rätt ordning.`;
  };

  function fram() {
    const r = ruta.getBoundingClientRect();
    (window.rullaTill || (y => window.scrollTo(0, y)))(Math.max(0, window.scrollY + r.top - 110));
  }

  /* Öppnas från lektionen i veckan, från veckobriefen och från planeringskön när
     lektionens papper är godkända. */
  const dagord = d => (window.Kalender && window.Kalender.ord ? window.Kalender.ord(d) : d);
  window.Tryck = {
    /* Allt som är godkänt för EN lektion — det är den hög läraren bär in. */
    lektion(post) {
      if (!post || !post.datum) return false;
      const s = (window.Dokument && window.Dokument.sparade()) || [];
      const valda = s.filter(v => v.datum === post.datum && (!post.klass || v.klass === post.klass));
      if (!valda.length) return false;
      packa([post.klass, dagord(post.datum)].filter(Boolean).join(' · '), valda);
      fram();
      return true;
    },
    oppna(namnPaPaketet) {
      const s = (window.Dokument && window.Dokument.sparade()) || [];
      const valda = namnPaPaketet
        ? s.filter(v => window.Dokument.namn(v).includes(namnPaPaketet.replace(/^Prov — /, '')))
        : s.slice(-3);
      packa(namnPaPaketet || 'nästa lektion', valda.length ? valda : s.slice(-2));
      fram();
    }
  };
})();
