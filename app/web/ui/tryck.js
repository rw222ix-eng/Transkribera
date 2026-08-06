/* ══════════ UTSKRIFTSPAKETET ══════════
   «Det här ska skrivas ut» som en enda gest. Appen vet vad lektionen består av
   och packar högen själv: tavlan överst, elevernas papper under, facit sist.
   Anpassade kopior (post 11) är rader i paketet — en egenskap hos KOPIAN, aldrig
   en etikett på pappret. Sammanräkningen står i knappen, före utskriften. */
(() => {
  const $ = s => document.querySelector(s);
  const ruta = $('#tryckruta');
  if (!ruta) return;

  const SIDOR = { Tavla: 1, Prov: 3, Arbetsblad: 2, Gruppuppgift: 1 };
  /* Sidantalet ska vara bladens, inte en tabell som gissar: formen vet exakt hur
     många ark dokumentet består av. En tavla är ett ark — den stod som två. */
  const sidorFor = v => {
    const f = window.Blad && window.Blad.form ? window.Blad.form(v) : null;
    return (f && f.length) || SIDOR[v.typ] || 2;
  };
  let rader = [], titel = '';

  function packa(namnPaPaketet, dokument) {
    titel = namnPaPaketet;
    const ordning = { Tavla: 0, Prov: 1, Arbetsblad: 1, Facit: 2 };
    rader = dokument.map(v => ({
      v,
      namn: window.Dokument.namn(v),
      typ: v.losningsblad ? 'Facit' : v.typ,
      under: v.losningsblad
        ? 'Din kopia · enkelsidig'
        : v.typ === 'Tavla' ? 'Din genomgång · enkelsidig' : 'Standard · dubbelsidig',
      antal: v.losningsblad ? 1 : v.typ === 'Tavla' ? 1 : 22,
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
          v: r.v, namn: `Lösningsförslag · boken s. ${r.v.bokuppg.sidor}`, typ: 'Facit',
          under: `${l.antal} uppgifter (${l.niva.toLowerCase()}) · uppg ${l.remsa} · din kopia · enkelsidig`,
          antal: 1, sidor: Math.max(1, Math.ceil(l.antal / 4)), med: true
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
  /* Tavlan kan ännu INTE följa med i paketet. Den finns bara som ritad DOM i
     webbläsaren — ingen bild och ingen PDF — och servern kan inte rendera om
     den (motorn bor här, inte där). Den som ska ha tavlan skriver ut den från
     sidan så länge. Servern lägger den i `saknas` och kvittot säger det, i
     stället för att paketet tyst blir en sida kortare. Nästa steg är en
     PNG-export ur whiteboard-motorn — rutten som tar emot den finns redan
     (/api/planning/export). */

  function paketkropp() {
    return {
      titel,
      dokument: rader.filter(r => r.med).map(r => {
        const d = { namn: r.namn, typ: r.typ, kopior: r.antal };
        if (r.v && r.v.provId) {
          d.exam_id = r.v.provId;
          if (r.typ === 'Facit') d.bedomning = true;
          if (r.anpassad) d.anpassad = {
            /* Samma anpassning som raden beskriver: förlängd tid, färre
               uppgifter, och en kod i foten som skiljer kopian. */
            tid_min: 150, antal: 4,
            kod: `${(r.v.klass || 'kopia')}-${(r.v.datum || '').slice(5)}`,
          };
        }
        return d;
      }),
    };
  }

  function bygg(knapp, efterat) {
    const text = knapp.textContent;
    knapp.disabled = true;
    knapp.textContent = 'Bygger paketet …';
    const ater = () => { knapp.textContent = text; knapp.disabled = false; };
    window.API.strom('/api/tryck', paketkropp(), {
      log: m => { knapp.textContent = String(m || '').slice(0, 40); },
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
    bygg(b, res => {
      /* Paketet öppnas i systemets PDF-läsare — där skrivardialogen bor.
         Appen har ingen egen skrivarkö och ska inte låtsas ha det. */
      window.API.json('/api/open', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: res.path }),
      }).catch(() => {});
      window.toast && window.toast(kvittotext(res));
    });
  });
  $('#trycksampdf').addEventListener('click', () => {
    const b = $('#trycksampdf');
    if (!serverPa()) { window.toast && window.toast('Nedladdad som en PDF — alla dokument i ordning'); return; }
    bygg(b, res => {
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
    return (res.saknas || []).length
      ? `Paketet är byggt — ${sidor}. ${res.saknas.join(', ')} kom inte med: tavlan skrivs ut från sidan, och ett papper som inte är godkänt har ingen PDF än.`
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
