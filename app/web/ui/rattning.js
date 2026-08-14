/* ══════════ RÄTTNINGEN — DÄR PROVET LIGGER ══════════
   Rättningen är inte en ruta som dyker upp på planeringssidan. Provet ligger i
   Sparat, och det är där man säger hur det gick: en rad per uppgift och
   delfråga, klassens totalpoäng medan högen ligger framme. Maxpoängen räknas ur
   provet självt (uppgiftens poäng × antal elever), så det enda som skrivs är
   den siffra läraren ändå har framför sig. Inga namn, ingen elev för sig.

   Resultatet blir en utgångspunkt: nästa gång något ska skapas ligger provet
   som ett kort i steg 3, med det klassen föll på redan utläst. */
(() => {
  const $ = (s, r) => (r || document).querySelector(s);
  const skal = $('#rattskal');
  if (!skal) return;

  let doc = null, poster = [], varden = {}, elever = 22, serverrader = null;

  const FORMAGA = [
    [/egna ord|innebär|begrepp/i, 'Begreppsförståelse'],
    [/skissa|graf|lutning/i, 'Grafisk tolkning'],
    [/härled|visa att|gäller generellt|bevis/i, 'Härledning'],
    [/olika svar|var felet|räknar olika/i, 'Felsökning i andras lösning'],
    [/avgör|påstånd|sant/i, 'Resonemang'],
    [/redovisa|hela lösningen|kommunicer|följa/i, 'Redovisning'],
    [/modellera|värdera rimlig/i, 'Modellering'],
    [/sammanhang|tolka svaret/i, 'Tillämpning i sammanhang'],
    [/beräkna|räkna/i, 'Räkning i standardfall']
  ];
  const formaga = t => (FORMAGA.find(([r]) => r.test(t)) || [0, 'Metoden i momentet'])[1];
  const ren = t => String(t || '').replace(/<[^>]*>/g, '').trim();
  const BOK = 'abcdef';

  /* Radens maxpoäng per NIVÅ — [E, C, A]. Klassrättningen bryr sig inte, men
     elevens betyg går inte att räkna ur en klumpsumma: C kräver sin andel av
     C- och A-poängen. Bär pappret tripeln (plan.js franProv) ÄR den radens
     poäng; annars läggs hela poängen på uppgiftens nivå, som är det bästa som
     finns på ett handskrivet papper. Samma regel som app/rattning.py. */
  const tripel = v => {
    if (!Array.isArray(v) || v.length !== 3) return null;
    const t = v.map(x => Math.max(0, Math.round(Number(x) || 0)));
    return t[0] + t[1] + t[2] > 0 ? t : null;
  };
  const pecaFall = (p, niva) => {
    const ut = [0, 0, 0];
    ut[{ C: 1, A: 2 }[String(niva || 'E').trim().toUpperCase()[0]] || 0] = Math.max(0, p || 0);
    return ut;
  };

  /* En rad per uppgift — eller per delfråga, eftersom en tvåpoängsuppgift oftast
     är a) räkningen och b) resonemanget, och det är just skillnaden man vill se. */
  function bygg(uppg) {
    const ut = [];
    uppg.forEach((u, i) => {
      const nr = u.nr || i + 1;
      const text = ren(u.t || u.text) || 'Uppgift ' + nr;
      const p = Math.max(1, u.p || 2);
      /* Uppgiftens CI-koder fryses på raden, precis som förmågan: det som stod
         på uppgiften när läraren rättade är det som gäller. Deluppgifterna ärver
         förälderns — provet taggar uppgiften, inte delfrågan. Samma regel som
         app/rattning.py bygg(). */
      const ci = (u.ci || []).filter(Boolean);
      const del = (u.del || []).filter(Boolean);
      if (del.length > 1) {
        ut.push({ grupp: true, nr: String(nr), text });
        const bas = Math.max(1, Math.floor(p / del.length));
        const dpeca = Array.isArray(u.delpeca) ? u.delpeca : [];
        del.forEach((d, j) => {
          const sista = j === del.length - 1;
          const eca = tripel(dpeca[j]);
          const dp = eca ? eca[0] + eca[1] + eca[2]
            : (sista ? Math.max(1, p - bas * (del.length - 1)) : bas);
          ut.push({
            nyckel: `${nr}${BOK[j]}`, kod: `${nr}${BOK[j]}`, nr: BOK[j] + ')',
            text: ren(d), p: dp, peca: eca || pecaFall(dp, u.niva),
            formaga: formaga(ren(d) + ' ' + text), ci: ci.slice()
          });
        });
      } else {
        const eca = tripel(u.peca);
        const up = eca ? eca[0] + eca[1] + eca[2] : p;
        ut.push({ nyckel: String(nr), kod: String(nr), nr: String(nr), text, p: up,
                  peca: eca || pecaFall(up, u.niva), formaga: formaga(text),
                  ci: ci.slice() });
      }
    });
    return ut;
  }

  function rita() {
    if (!doc) return;
    const uppg = (doc.uppgifter || []).length
      ? doc.uppgifter
      : Array.from({ length: 6 }, (_, i) => ({ nr: i + 1, t: 'Uppgift ' + (i + 1), p: 3 }));
    /* Serverns rader är samma rader — byggda av app/rattning.py ur samma
       uppgifter — men med provets EGNA förmågor i stället för gissningen ur
       texten. Ett prov Claude skrivit vet vad varje uppgift prövar. */
    poster = serverrader || bygg(uppg);
    $('#rattelever').value = elever;
    $('#rattningtitel').textContent = (window.Dokument ? window.Dokument.namn(doc) : 'Provet').replace(/^Prov — /, 'Prov · ') +
      (doc.klass ? ' · ' + doc.klass : '');

    const lista = $('#rattninglista');
    lista.innerHTML = '';
    poster.forEach(p => {
      const rad = document.createElement('div');
      if (p.grupp) {
        rad.className = 'rattgrupp';
        rad.innerHTML = '<span class="rattnr"></span><span class="rattupp"></span>';
        rad.querySelector('.rattnr').textContent = p.nr;
        rad.querySelector('.rattupp').textContent = p.text;
        lista.appendChild(rad);
        return;
      }
      rad.className = 'rattrad';
      rad.dataset.nyckel = p.nyckel;
      rad.innerHTML = '<span class="rattnr"></span><span class="rattupp"></span><span class="rattmax"></span>' +
        '<input class="rattfalt" type="number" min="0" step="1" inputmode="numeric" placeholder="—" />' +
        '<span class="rattandel"><span class="rattstapel"><i></i></span><span class="rattproc">—</span></span>';
      rad.querySelector('.rattnr').textContent = p.nr;
      rad.querySelector('.rattupp').textContent = p.text;
      const falt = rad.querySelector('.rattfalt');
      falt.value = varden[p.nyckel] != null ? varden[p.nyckel] : '';
      falt.setAttribute('aria-label', `Klassens totalpoäng på uppgift ${p.kod}`);
      falt.addEventListener('input', () => {
        const v = falt.value.trim();
        if (v === '') delete varden[p.nyckel];
        else varden[p.nyckel] = Math.max(0, Math.min(p.p * elever, Math.round(Number(v) || 0)));
        rakna();
      });
      lista.appendChild(rad);
    });
    rakna();
  }

  function rakna() {
    elever = Math.max(1, Math.min(40, Math.round(Number($('#rattelever').value) || 22)));
    const rader = poster.filter(p => !p.grupp);
    const maxProv = rader.reduce((a, p) => a + p.p, 0);
    $('#rattmaxnot').textContent = `skrev provet. Provet är ${maxProv} p — klassens tak ${maxProv * elever} p, eftersom maxpoängen per uppgift är uppgiftens poäng × ${elever}.`;

    let summa = 0, tak = 0, ifyllda = 0;
    rader.forEach(p => {
      const rad = $(`.rattrad[data-nyckel="${p.nyckel}"]`);
      if (!rad) return;
      const max = p.p * elever;
      rad.querySelector('.rattmax').textContent = max + ' p';
      const v = varden[p.nyckel];
      const har = v != null;
      if (har) { summa += v; tak += max; ifyllda++; }
      p.andel = har ? v / max : null;
      rad.querySelector('.rattstapel i').style.width = har ? Math.round(p.andel * 100) + '%' : '0%';
      rad.querySelector('.rattproc').textContent = har ? Math.round(p.andel * 100) + ' %' : '—';
      if (har && p.andel < 0.5) rad.setAttribute('data-svag', ''); else rad.removeAttribute('data-svag');
    });

    $('#rattsumma').innerHTML = ifyllda
      ? `Klassen tog <b>${summa}</b> av <b>${tak}</b> möjliga poäng på de ${ifyllda} ${ifyllda === 1 ? 'rad' : 'rader'} som är ifyllda — <b>${Math.round((summa / (tak || 1)) * 100)} %</b>.`
      : `Provet har ${rader.length} rader att fylla i. Skriv summan klassen tog på varje uppgift.`;

    const spara = $('#rattningspara');
    spara.textContent = ifyllda ? `Spara — ${ifyllda} av ${rader.length} ifyllda` : 'Spara';
    spara.disabled = !ifyllda;
    $('#rattningsnot').textContent = doc && doc.rattat
      ? 'Sparat på provet — ändra en siffra och spara igen om något blev fel.'
      : 'Inga namn sparas · tabb går vidare till nästa uppgift.';
    analys(rader);
  }

  /* Modellen läser provets innehåll mot poängen: uppgifterna finns i datan, så
     det går att säga VAD som föll, inte bara att något föll. */
  function svagaste(rader) {
    const med = rader.filter(p => p.andel != null);
    if (med.length < 2) return null;
    const sorterad = med.slice().sort((a, b) => a.andel - b.andel);
    const svaga = sorterad.filter(p => p.andel < 0.6).slice(0, 3);
    return { lista: svaga.length ? svaga : sorterad.slice(0, 2), bast: sorterad[sorterad.length - 1] };
  }
  const rada = a => a.length < 2 ? (a[0] || '') : a.slice(0, -1).join(', ') + ' och ' + a[a.length - 1];

  function analys(rader) {
    const box = $('#rattanalys');
    const s = svagaste(rader);
    if (!s) { box.hidden = true; return; }
    const proc = p => Math.round(p.andel * 100);
    const unika = [...new Set(s.lista.map(p => p.formaga))];
    const moment = (doc.moment || 'momentet').toLowerCase();
    const delfraga = s.lista.some(p => /[a-f]$/.test(p.kod));
    $('#rattlas').textContent =
      `${s.bast.formaga} sitter — uppgift ${s.bast.kod} gav ${proc(s.bast)} % av sin maxpoäng. ` +
      `Det som faller är ${rada(unika.map(f => f.toLowerCase()))}: uppgift ${rada(s.lista.map(p => p.kod))} landar på ${proc(s.lista[0])}–${proc(s.lista[s.lista.length - 1])} %. ` +
      (delfraga
        ? `Poängen ligger på delfrågan, inte på hela uppgiften, så det är den delen av ${moment} som ska tas om.`
        : `Det är hela uppgifter som faller, inte enstaka delfrågor — ${unika.length > 1 ? 'de förmågorna' : 'den förmågan'} behöver en egen genomgång i ${moment}.`);
    const ut = $('#rattsvaga');
    ut.innerHTML = '';
    s.lista.forEach(p => {
      const rad = document.createElement('div');
      rad.className = 'rattsvagrad';
      rad.innerHTML = '<span class="rattkod"></span><span class="rattamne"><span></span></span><span class="rattproc"></span>';
      rad.querySelector('.rattkod').textContent = 'Uppg ' + p.kod;
      rad.querySelector('.rattamne').insertBefore(document.createTextNode(p.formaga), rad.querySelector('.rattamne span'));
      rad.querySelector('.rattamne span').textContent = p.text;
      rad.querySelector('.rattproc').textContent = proc(p) + ' %';
      ut.appendChild(rad);
    });
    box.hidden = false;
  }

  /* ══════════ SERVERN ══════════
     Rättningen räknas på servern (app/rattning.py) av samma skäl som allt
     annat i planeringen: utfallet är en KÄLLA. «Läser provets utfall · 4b, 7
     föll» är en rad i skrivplanen och det som föll går in i nästa prompt — och
     ett tal som räknas på två ställen blir förr eller senare två tal.

     Utan server räknar den här filen själv, precis som förut. Designprojektet
     har ingen server, och prototypen ska stå kvar. */
  const server = () => !!(window.API && window.API.pa && doc && doc.id);
  const vag = v => '/api/dokument/' + v.id + '/rattning';

  /* Modalen öppnas på egna rader direkt — den som rättar ska inte vänta på
     nätet — och ritas om när servern svarat. */
  function hamta() {
    if (!server()) return;
    const v = doc;
    window.API.json(vag(v)).then(r => {
      if (doc !== v || !r || !(r.rader || []).length) return;
      serverrader = r.rader;
      if (r.elever) elever = r.elever;
      /* Serverns siffror gäller bara om ingenting står i fälten: har man
         börjat skriva ska det man skrivit inte bytas ut under handen. */
      if (!Object.keys(varden).length && r.varden) varden = Object.assign({}, r.varden);
      rita();
    }).catch(() => {});
  }

  /* Kvittot, inte källan: siffrorna ligger redan på skärmen. Svarar servern
     något annat än vad som räknades här vinner den — den läste pappret ur
     databasen — och pappret skrivs om en gång till. */
  function spara(v, lokal) {
    if (!(window.API && window.API.pa && v && v.id)) return;
    window.API.json(vag(v), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ elever: lokal.elever, varden: lokal.varden }),
    }).then(r => {
      if (!r || !r.rattat || !v.rattat) return;
      if (JSON.stringify(r.rattat) === JSON.stringify(v.rattat)) return;
      v.rattat = r.rattat;
      window.Dokument && window.Dokument.andrad && window.Dokument.andrad(v);
      window.Dokument && window.Dokument.rita && window.Dokument.rita();
      window.Utgang && window.Utgang.rita();
    }).catch(() => {});
  }

  function slapp(v) {
    if (!(window.API && window.API.pa && v && v.id)) return;
    window.API.json(vag(v), { method: 'DELETE' }).catch(() => {});
  }

  /* ── Modalen ─────────────────────────────────────── */
  const tangent = e => { if (e.key === 'Escape') stang(); };
  function oppna(v) {
    if (!v) return;
    doc = v;
    serverrader = null;
    varden = v.rattat && v.rattat.varden ? Object.assign({}, v.rattat.varden) : {};
    elever = (v.rattat && v.rattat.elever) || 22;
    rita();
    hamta();
    skal.hidden = false;
    requestAnimationFrame(() => skal.setAttribute('data-pa', ''));
    document.addEventListener('keydown', tangent);
  }
  function stang() {
    if (skal.hidden) return;
    skal.removeAttribute('data-pa');
    setTimeout(() => { skal.hidden = true; }, 220);
    document.removeEventListener('keydown', tangent);
  }
  skal.addEventListener('click', e => { if (e.target === skal) stang(); });
  $('#rattstang').addEventListener('click', stang);
  $('#rattelever').addEventListener('input', rakna);

  /* Lägesväxeln: samma prov, två sätt att rätta det. Klassläget är kvällen då
     högen ligger framme och man bara vill ha summan; elevläget är när eleverna
     ska få veta hur det gick. Modalerna är skilda åt för att raderna ser olika
     ut — en summa per rad mot en knapprad per nivå — och en modal som gör båda
     hade blivit två modaler i en fil. */
  $('#rattilelev').addEventListener('click', () => {
    const v = doc;
    stang();
    setTimeout(() => window.Elever && window.Elever.oppna(v), 60);
  });

  $('#rattningspara').addEventListener('click', () => {
    if (!doc) return;
    /* Pappret hålls fast här: modalen kan hinna öppnas på ett annat prov innan
       toasten hinner ångras, och då är det DET HÄR provets rättning som ska
       tas bort — inte det som råkar ligga framme. */
    const v = doc;
    const rader = poster.filter(p => !p.grupp && p.andel != null);
    const summa = rader.reduce((a, p) => a + varden[p.nyckel], 0);
    const tak = rader.reduce((a, p) => a + p.p * elever, 0) || 1;
    const s = svagaste(poster.filter(p => !p.grupp));
    v.rattat = {
      elever, varden: Object.assign({}, varden), andel: summa / tak,
      svaga: s ? s.lista.map(p => ({ kod: p.kod, formaga: p.formaga, text: p.text, andel: p.andel })) : []
    };
    /* Utfallet är fakta om pappret och skrivs rakt på det — ingen ny version att
       ångra. Utan det här överlever «Rättat · NN %» inte en omladdning, och
       källdörr 5 («Läser provets utfall») har inget att läsa. */
    window.Dokument && window.Dokument.andrad && window.Dokument.andrad(v);
    window.Dokument && window.Dokument.rita && window.Dokument.rita();
    window.Utgang && window.Utgang.rita();
    spara(v, v.rattat);
    window.toast && window.toast(
      s ? `Sparat — uppgift ${rada(s.lista.map(p => p.kod))} ligger som utgångspunkt när du planerar` : 'Sparat',
      'Ångra', () => {
        v.rattat = null;
        window.Dokument && window.Dokument.andrad && window.Dokument.andrad(v);
        window.Dokument && window.Dokument.rita();
        window.Utgang && window.Utgang.rita();
        slapp(v);
      });
    stang();
  });

  /* `bygg` delas med elever.js: raderna är samma rader i båda lägena, och två
     radbyggare hade förr eller senare byggt två olika prov. */
  window.Rattning = { oppna, bygg };
})();
