/* ══════════ UPPGIFTERNA UR BOKEN ══════════
   Spannet i remsan säger vilka uppgifter som FINNS på sidorna. Det här säger
   vilka som gäller — och det är sällan alla: någon uppgift ligger utanför
   momentet, någon kräver fem lösningssteg utan att eleven lär sig något nytt.
   Urvalet gjordes förr i huvudet och skrevs på tavlan i förbifarten. Boken
   ligger inläst i appen, så modellen har läst sidorna innan panelen ens öppnas:
   förslaget står framme före första tangenttrycket, och det säger bara vad som
   ska HOPPAS ÖVER. Att de andra ska räknas är underförstått — en lista över allt
   man ska göra läser man i boken ändå.

   Urvalet bär vidare på tre ställen och alla tre måste säga samma sak:
   lösningsförslagen i steg 3 skrivs bara till de uppgifter som är kvar, tavlans
   vänsterspalt skriver upp sidorna och uppgifterna åt eleverna, och paketet i
   Att skriva ut lägger lösningsförslaget som ett eget ark. */
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const vard = $('#uppgblock');
  if (!vard || !window.Bok) return;

  const grans = a => String(a.sid).split('–').map(Number);
  const spann = () => (window.Uppslag && window.Uppslag.spann ? window.Uppslag.spann() : null);
  const reg = () => {
    const s = spann();
    return window.Bok.registerForBok ? window.Bok.registerForBok(s ? s.bok : window.Bok.namn) : window.Bok.avsnitt;
  };
  /* Boken numrerar uppgifterna efter avsnitt: 5.1 blir 5101, 5102 … Samma nummer
     som läraren läser i boken ska stå på tavlan och i lösningsförslaget — ett
     eget löpnummer i appen hade tvingat en översättning i huvudet. */
  const nummer = (nr, i) => {
    const [k, a] = String(nr).split('.').map(Number);
    return k * 1000 + a * 100 + i + 1;
  };
  const versal = s => s.charAt(0).toUpperCase() + s.slice(1);

  /* Uppgifterna ligger inte jämnt över avsnittets sidor i verkligheten — teorin
     tar de första — men appens bok är indexerad per avsnitt, inte per uppgift.
     Fördelningen är därför en uppskattning, och den måste vara STABIL: byter
     listan uppgifter varje gång panelen ritas om byter förslaget uppgifter mitt
     i planeringen, och då är det inget förslag. */
  /* ══════════ UPPGIFTERNA UR BOKEN PÅ RIKTIGT ══════════
     Fördelningen nedan är en uppskattning ur avsnittets uppgiftsantal — den
     var det enda prototypen kunde. En inläst bok VET: uppgiftsnumren står på
     sidorna och läses därifrån (app/bok_ocr.py faktapasset), med sin nivå ur
     de färgade markörerna. Då gissas ingenting.

     Sidorna läses när uppslaget väljs, inte vid import: en bok är 313 sidor
     och en sida kostar ~96 sekunder. Tills faktapasset är klart står listan
     tom — den ritar hellre ingenting än chips för uppgifter ingen sett. */
  let serverdata = null;      // {nyckel, uppgifter: [{nr, sida, niva}]}
  let laser = false;
  const bokId = () => {
    const s = spann();
    return s && window.Bok && window.Bok.bokId ? window.Bok.bokId(s.bok) : null;
  };
  const nyckelNu = () => { const s = spann(); return s ? `${s.bok}|${s.fran}|${s.till}` : ''; };

  function alla() {
    const s = spann();
    if (!s || !s.fran) return [];
    if (bokId()) {
      if (!serverdata || serverdata.nyckel !== nyckelNu()) return [];
      const a = avsnittet();
      return serverdata.uppgifter.map(u => ({
        nr: u.nr, sida: u.sida || s.fran, niva: u.niva || 1,
        /* Genomräknat exempel — numrerat som en uppgift, men löst i boken.
           Saknas fältet (sidor lästa före konsekvensregeln) är svaret okänt,
           och okänt behandlas som vanlig uppgift: så såg panelen ut förut. */
        exempel: !!u.exempel,
        avsnitt: reg().find(x => { const [f, t] = grans(x); return u.sida >= f && u.sida <= t; }) || a,
      }));
    }
    const ut = [];
    reg().forEach(a => {
      const [f, t] = grans(a);
      if (t < s.fran || f > s.till) return;
      const n = a.uppg, sidor = t - f + 1;
      /* Nivåerna följer bokens tre block: de lätta först, de svåraste sist. */
      const n1 = Math.round(n * 0.45), n2 = Math.round(n * 0.33);
      for (let i = 0; i < n; i++) {
        const sida = f + Math.floor(i * sidor / n);
        if (sida < s.fran || sida > s.till) continue;
        ut.push({ nr: nummer(a.nr, i), sida, niva: i < n1 ? 1 : i < n1 + n2 ? 2 : 3, avsnitt: a });
      }
    });
    return ut;
  }
  /* Uppgifterna klassen ska RÄKNA — allt utom bokens genomräknade exempel.
     1101 och 1102 i Matematik 5000+ 1a är numrerade som uppgifter men lösta i
     teoritexten; de står kvar i listan (de STÅR på sidorna, och en lucka i
     numren hade sett ut som en misslyckad läsning) men de är ingenting att dela
     ut. Allt som räknar, väljer bort eller föreslår går därför genom den här,
     och bara ritningen ser hela `alla()`. */
  const raknade = () => alla().filter(x => !x.exempel);
  const avsnittet = () => {
    const s = spann();
    if (!s) return null;
    return reg().find(a => { const [f, t] = grans(a); return s.fran >= f && s.fran <= t; }) || null;
  };

  /* Nummerlistan skrivs som läraren skriver den på tavlan: löpande nummer blir
     ett spann. «5104, 5106, 5108–5112» i stället för nio nummer i rad. */
  function remsa(nummerlista) {
    const n = [...nummerlista].sort((a, b) => a - b);
    const delar = [];
    let i = 0;
    while (i < n.length) {
      let j = i;
      while (j + 1 < n.length && n[j + 1] === n[j] + 1) j++;
      delar.push(j - i >= 2 ? `${n[i]}–${n[j]}` : n.slice(i, j + 1).join(', '));
      i = j + 1;
    }
    return delar.join(', ');
  }
  const ochLista = n => n.length < 2 ? n.join('') : n.slice(0, -1).join(', ') + ' och ' + n[n.length - 1];

  /* ── Modellens förslag ─────────────────────────────
     Två skäl att hoppa en uppgift, och de är lärarens egna: den hör inte till
     det centrala innehåll man håller på med, eller den är onödigt komplicerad —
     många lösningssteg utan ny insikt. Valet är en hash av spannet, inte slump:
     samma sidor ska ge samma förslag varje gång. */
  const hash = s => { let h = 7; for (const c of String(s)) h = (h * 31 + c.charCodeAt(0)) % 99991; return h; };
  function forslaget() {
    const u = raknade();
    if (u.length < 6) return [];
    const s = spann();
    const nyckel = `${s.bok}|${s.fran}|${s.till}`;
    const h = hash(nyckel);
    /* Det är på nivå 2 och 3 uppgifterna spårar ur — de lätta är korta och lika
       varandra, och att hoppa en av dem sparar ingenting. */
    const kandidater = u.filter(x => x.niva >= 2);
    if (!kandidater.length) return [];
    const A = reg();
    const efter = A[Math.min(A.length - 1, A.findIndex(a => a.nr === (avsnittet() || A[0]).nr) + 1)];
    const forst = kandidater[h % kandidater.length];
    const andra = kandidater[(h * 7 + 3) % kandidater.length];
    const valda = forst === andra ? [forst] : [forst, andra].sort((a, b) => a.nr - b.nr);
    return valda.map((x, i) => Object.assign({}, x, {
      skal: (i === 0 && efter && efter.nr !== (avsnittet() || {}).nr)
        ? `ligger utanför momentet — den bygger på ${efter.nr} ${efter.titel}`
        : 'kräver många lösningssteg utan att lägga till något nytt'
    }));
  }
  function forslagsText(valda) {
    if (!valda.length) return 'Alla uppgifterna på sidorna hör till momentet — jag skulle inte hoppa någon.';
    if (valda.length === 1) return `Hoppa ${valda[0].nr}. Den ${valda[0].skal}.`;
    return `Hoppa ${ochLista(valda.map(v => String(v.nr)))}. Den första ${valda[0].skal}, den andra ${valda[1].skal}.`;
  }

  /* ── Läget ─────────────────────────────────────────
     `bort` är de uppgifter som INTE ska räknas. Byter spannet är det ett nytt
     urval, och då ska modellens förslag gälla igen — annars ligger tre bortvalda
     uppgifter kvar från ett avsnitt man lämnat. */
  let nyckel = '';
  let bort = new Set();
  let forslag = [];
  /* Uppgifterna läraren SJÄLV skrivit på lektionen i kalendern («uppg.
     1101–1103, 1105–1119»). Finns de är det de som gäller, och allt annat på
     sidorna hoppas över — modellen ska inte föreslå bort något ur en lista
     läraren redan gjort. null = ingen sådan lista, förslaget gäller som förut. */
  let onskade = null;
  /* VARIFRÅN listan kom, som en dag att citera: tomt = lektionens egen
     kalenderrad, ett datum = grovplaneringens rad för samma sidor men en annan
     dag. Raden ovanför chipsen säger läraren vilket det är (kalendertext). */
  let onskadNar = '';
  /* Utgångsläget för `bort`, och det enda stället som avgör vad «tillbaka till
     förslaget» betyder. Numren ur kalendern gäller bara om de faktiskt står på
     sidorna — annars pekar de på ett annat spann, och då hade allt strukits. */
  function standardbort() {
    const u = raknade();
    if (onskade && u.some(x => onskade.has(x.nr))) return new Set(u.filter(x => !onskade.has(x.nr)).map(x => x.nr));
    return new Set(forslag.map(f => f.nr));
  }
  /* Lärarens egen lista, läst ur hennes skrivning. Två vägar hit — lektionens
     kalenderrad (profil.js) och grovplaneringen för sidorna (nedan) — och de
     skiljs bara åt av `nar`, dagen raden ska citera. */
  function las(text, nar) {
    const t = String(text || '');
    const vill = new Set();
    /* Ett spann är alla numren i det: «1101–1103» är tre uppgifter, inte två.
       Boken numrerar dem i följd, så mellanrummen finns på sidorna. */
    t.split(/[,;]/).forEach(del => {
      const par = del.match(/(\d{3,4})\s*[–—-]\s*(\d{3,4})/);
      if (par) { for (let n = +par[1]; n <= +par[2] && n - +par[1] < 200; n++) vill.add(n); return; }
      (del.match(/\d{3,4}/g) || []).forEach(n => vill.add(+n));
    });
    if (!vill.size) return false;
    onskade = vill;
    onskadNar = nar || '';
    bort = standardbort();
    rita();
    window.planKoll && window.planKoll();
    return true;
  }

  /* ── NÄR LÄRAREN VÄLJER SPANNET SJÄLV ──────────────
     Lektionen hon planerar har inte alltid en bokplanering i kalendern — och
     drar hon remsan till andra sidor än de kalendern gav har den ingen heller.
     Panelen föll då tillbaka på modellens hoppa-över-förslag, fast svaret stod
     skrivet i hennes GROVPLANERING sedan i somras: någon annan lektion täcker
     just de sidorna och bär uppgifterna. Hennes eget urval slår modellens,
     vilken dag hon än skrev det (kalender.js uppgifterForSpann).

     Lektionens EGEN rad vinner ändå: profil.js sätter spannet först — då körs
     det här — och ropar franKalendern efter. Den ordningen är kontraktet.

     Klass och kurs står i steg 1, och steg 1 är ifyllt innan förvalen sätts
     (plankon.js fyll). Utan dem gör kalendern ingenting: en annan klass
     uppgifter är värre än inga.

     Provet hoppas över. Panelen är fälld där, och uppgifterna på
     sidorna är det klassen ÖVADE med — inte det den prövas på (plan.js
     HELHETSTYPER). */
  function franPlaneringen() {
    const K = window.Kalender, s = spann();
    if (!K || !K.uppgifterForSpann || !s || !s.fran) return;
    if (window.Helhetstyp && window.Helhetstyp()) return;
    const p = K.uppgifterForSpann(($('#p-klass') || {}).value || '',
                                  ($('#p-kurs') || {}).value || '', s.fran, s.till);
    if (p) las(p.uppg, p.nar);
  }

  function synka() {
    const ny = nyckelNu();
    if (ny === nyckel) return false;
    nyckel = ny;
    /* Nytt spann är en ny lektion: kalenderns lista hörde till det förra. */
    onskade = null;
    onskadNar = '';
    forslag = forslaget();
    bort = standardbort();
    /* …men grovplaneringen har ofta ett svar om de NYA sidorna också. Frågas
       här, alltså vid varje spannbyte — remsan, avsnittslistan, bokbytet och
       lektionsvalet går alla genom `synka`. Före `hamta`: `onskade` behöver
       inte uppgifterna för att gälla, standardbort slår till av sig själv när
       sidorna kommer. */
    franPlaneringen();
    hamta();
    return true;
  }

  /* Vad står på sidorna? Servern svarar med det den redan läst, och säger
     vilka sidor som inte är lästa än. Är någon oläst körs faktapasset —
     ett anrop per åtta sidor, en dryg minut — och listan fylls i efterhand. */
  function hamta() {
    const id = bokId(), s = spann();
    serverdata = null;
    if (!id || !s || !(window.API && window.API.pa)) return;
    const nyck = nyckelNu();
    const ta = d => {
      if (nyckelNu() !== nyck) return;         // spannet hann bytas
      serverdata = { nyckel: nyck, uppgifter: d.uppgifter || [],
                     olasta: (d.olasta || []).length,
                     /* Numren servern SÅG saknas mitt i följden på lästa
                        sidor. Odefinierat från en äldre server — då härleds
                        frågan här i stället (iLucka). */
                     luckor: d.luckor };
      forslag = forslaget();
      bort = standardbort();
      rita();
      window.planKoll && window.planKoll();
    };
    /* SWR: läraren bläddrar fram och tillbaka mellan samma sidspann hela
       planeringen igenom, och uppslaget är samma svar varje gång tills sidorna
       lästs om. Cachen ritar listan direkt; servern ritar om den bara om något
       ändrats.

       Faktapasset hänger däremot på DET FÄRSKA svaret och inget annat — och på
       varje färskt svar, även när det är identiskt med cachen. Vore beslutet
       lagt i `vidFarskt` (som tiger när svaret är oförändrat) hade ett spann med
       olästa sidor aldrig lästs mer än en gång per webbläsare. */
    window.API.jsonSWR(`/api/bocker/${id}/uppslag?fran=${s.fran}&till=${s.till}`, {
      vidCache: ta, vidFarskt: ta,
    }).then(d => {
      if (nyckelNu() !== nyck) return;
      /* Faktapasset fyller panelen — och för provet är panelen
         fälld (rita ovan). Ett provspann över trettio sidor hade blivit
         minuters LLM-anrop för en lista ingen ser, så passet hoppas här och
         tas av servern när det skrivs (routes_planning.bok_las_text), där
         väntan redan syns i molnraden. `hoppat` minns hoppet så att ett byte
         tillbaka till lektionsmaterial tar passet direkt (spegla). */
      const helhet = !!(window.Helhetstyp && window.Helhetstyp());
      hoppat = helhet && (d.utan_fakta || []).length > 0;
      if ((d.utan_fakta || []).length && !helhet) lasSidorna(id, s, nyck);
    }).catch(() => {});
  }
  let hoppat = false;

  /* Ett faktapass per spann, aldrig fler. Passet är gratis andra gången —
     servern svarar «redan lästa» direkt — och just därför skulle en sida det
     inte fick fram (modellen hoppade den) annars ge hämta → läs → hämta i
     evighet, hundra anrop i sekunden. Nollställs vid fel så att ett avbrutet
     pass går att göra om när man kommer tillbaka till spannet. */
  let bett = '';
  function lasSidorna(id, s, nyck) {
    const host = $('#uppgsvar');
    if (!host || laser || bett === nyck) return;
    laser = true;
    bett = nyck;
    /* Passet skrivs genom API.strom, som går utanför json() och därför inte
       glömmer något av sig själv. Uppslaget läraren just väntade på är precis
       det cachade svaret som nu är osant. */
    const klart = () => {
      laser = false;
      window.API.swrGlom && window.API.swrGlom('/api/bocker/' + id + '/uppslag');
      if (nyckelNu() === nyck) hamta();
    };
    /* Felet från passet får ALDRIG bli en tom ruta. Fraga.kor ritar
       `e.message` och en «Försök igen»-knapp, så meningen som kastas här är
       den läraren läser — och serverns egen text hänger med efter kolonet
       («PDF:en gick inte att öppna: … Data format error»). Morgonen
       2026-09-06 föll just det här jobbet i skrivbordsappen och läraren såg
       ingenting alls; se app/pdfvakt.py för varför det föll. */
    const jobb = ({ signal, log }) => window.API.strom(
      `/api/bocker/${id}/las`,
      { fran: s.fran, till: s.till, bara: 'fakta' }, { signal, log })
      .catch(e => {
        if (e && e.name === 'AbortError') throw e;
        const m = (e && e.message) || '';
        throw new Error(`Sidorna ${s.fran}–${s.till} kunde inte läsas`
                        + (m ? `: ${m}` : '.'));
      });
    if (window.Fraga && window.Fraga.kor) {
      window.Fraga.kor(host, {
        enkel: true, jobb,
        jobbtext: `Slår upp s. ${s.fran}–${s.till} i ${s.bok} …`,
        svar: r => r && r.uppgifter && r.uppgifter.length
          ? `Sidorna är uppslagna — ${r.uppgifter.length} uppgifter står där.`
          : 'Sidorna är uppslagna.',
        efterKlar: klart, efterFel: () => { laser = false; bett = ''; },
      });
    } else {
      jobb({}).then(klart, () => { laser = false; bett = ''; });
    }
  }
  /* Raden citerar LÄRAREN, och då måste den citera rätt.
     Den skrevs förr ur SKÄRNINGEN mellan hennes lista och de uppgifter som
     hunnit läsas ur sidorna: stod «1101–1103, 1105–1119» i kalendern och sidan
     med 1116–1119 inte var inläst sa raden «… i kalendern: 1101–1103,
     1105–1115» — hennes egen mening, med hennes siffror, ändrad utan att någon
     sa det. Hela listan står här nu, och det som inte gick att hitta på
     uppslaget sägs rakt ut i stället för att tystas bort. Chipsen nedanför är
     kvar som de var: de kan bara visa uppgifter som faktiskt lästs. */
  function kalendertext(u) {
    /* Två källor, två meningar — och den andra får inte låtsas vara den första.
       Lektionens egen kalenderrad är det läraren skrev om DEN dagen; kommer
       numren i stället ur grovplaneringens rad för samma sidor är det en annan
       dag hon citeras från, och raden säger vilken. */
    const bas = onskadNar
      ? `Ur din planering (${onskadNar}): ${remsa([...onskade])}.`
      : `Uppgifterna du skrivit på lektionen i kalendern: ${remsa([...onskade])}.`;
    const saknas = [...onskade].filter(n => !u.some(x => x.nr === n));
    if (!saknas.length) return bas;
    const s = spann();
    /* Tre skäl att ett planerat nummer inte står bland chipsen, och de betyder
       helt olika saker för läraren:

       * det ligger i en LUCKA mellan lästa grannummer — då finns det på sidan
         och avläsningen missade det (servern räknar fram luckorna, bok.luckor),
       * sidorna är inte inlästa än,
       * eller numret finns helt enkelt inte på uppslaget.

       Att säga «står inte på s. 2–6» om en lucka är ett påstående om BOKEN som
       bygger på ett fel i läsningen — läraren letar då efter en uppgift hon
       skrivit och tror att hon mindes fel. */
    const luckna = saknas.filter(iLucka);
    const rest = saknas.filter(n => !iLucka(n));
    const rader = [bas];
    if (luckna.length) rader.push(`${remsa(luckna)} kunde inte läsas från sidan.`);
    if (rest.length) rader.push(serverdata && serverdata.olasta
      ? `${remsa(rest)} har inte lästs in än.`
      : `${remsa(rest)} står inte på s. ${s.fran}–${s.till}.`);
    return rader.join(' ');
  }
  /* Ligger numret i en lucka? Servern svarar när den kan (uppslagsrutten
     räknar fram `luckor` ur det den läst). En äldre server — eller ett svar
     utan fältet — får samma fråga ställd här: numret ska ha ett läst grannummer
     på var sida i SAMMA hundratalsserie, och hålet får inte vara orimligt stort
     (då är det ett serieskifte, inte en miss). Samma regel som app/bok.py. */
  const LUCKTAK = 20;
  function iLucka(n) {
    if (serverdata && Array.isArray(serverdata.luckor)) return serverdata.luckor.includes(n);
    const serie = Math.floor(n / 100);
    const syskon = alla().filter(x => Math.floor(x.nr / 100) === serie).map(x => x.nr);
    const under = syskon.filter(x => x < n);
    const over = syskon.filter(x => x > n);
    if (!under.length || !over.length) return false;
    return Math.min(...over) - Math.max(...under) - 1 <= LUCKTAK;
  }

  const rort = () => {
    const f = standardbort();
    return bort.size !== f.size || [...bort].some(n => !f.has(n));
  };

  /* ── Panelen ───────────────────────────────────────
     Chipsen står i bokens ordning, tre rader — en per nivå. En bortvald uppgift
     försvinner inte ur listan, den får streck över: det är boken man läser av,
     och boken byter inte ordning för att man hoppar en uppgift. */
  const NIVA = [1, 2, 3];
  function rita() {
    const u = alla();
    /* «Uppgifterna på sidorna» är en LEKTIONSGEST: det här räknar vi, det här
       hoppar vi över. Provet utgår från helheten klassen tränat
       på, och där hör blocket inte hemma — dessutom listar det bara uppgifter
       på de sidor som hunnit läsas in, så på ett provspann över trettio sidor
       visade det tre av dem och såg ut som ett svar. Bokdörren visar spannet
       som förut; det är urvalet som går ner. plan.js äger regeln
       (window.Helhetstyp) och ropar hit via window.Uppgifter.spegla. */
    vard.hidden = !u.length || !!(window.Helhetstyp && window.Helhetstyp());
    if (!u.length || vard.hidden) return;
    /* Räkningen gäller det klassen ska GÖRA. Bokens genomräknade exempel står
       kvar bland chipsen men hör inte hemma i «X av Y att räkna» — de är redan
       lösta på sidan. */
    const rakn = raknade();
    const kvar = rakn.filter(x => !bort.has(x.nr));
    const fanns = !!$('#uppgfraga');
    if (!fanns) {
      vard.innerHTML = `<div class="uppghuvud"><span class="minietikett" style="margin:0">Uppgifterna på sidorna</span><span class="uppgant" id="uppgant"></span></div>
        <p class="uppgforslag" id="uppgforslag"></p>
        <button class="lank uppgater" id="uppgater" type="button" hidden>Tillbaka till förslaget</button>
        <div class="uppgnivaer" id="uppgnivaer"></div>
        <div class="uppgfragarad"><input class="field" id="uppgfraga" autocomplete="off" aria-label="Ändra urvalet av uppgifter" /><button class="ghost" id="uppgskicka" type="button">Fråga</button></div>
        <div class="uppgsvar" id="uppgsvar" hidden></div>`;
      $('#uppgater').addEventListener('click', () => {
        bort = standardbort();
        $('#uppgsvar').hidden = true;
        rita();
        window.planKoll && window.planKoll();
      });
      $('#uppgskicka').addEventListener('click', () => fraga($('#uppgfraga').value));
      $('#uppgfraga').addEventListener('keydown', e => {
        if (e.key === 'Enter') { e.preventDefault(); fraga($('#uppgfraga').value); }
      });
    }
    $('#uppgant').textContent = `${kvar.length} av ${rakn.length} att räkna`;
    /* Fältet är för det man INTE kan klicka fram: att hoppa en hel nivå, att
       hålla sig till de tillämpade uppgifterna. En enskild uppgift klickas i
       listan ovanför, och ett exempel på just det i platshållaren fick läraren att
       skriva det i onödan. */
    $('#uppgfraga').placeholder = 'T.ex. «hoppa nivå 1» eller «bara de tillämpade uppgifterna»';
    /* Kom urvalet ur kalendern är det inte ett förslag att ta ställning till —
       raden säger var det kommer ifrån, så att ingen tror att appen valt. */
    if (!rort()) $('#uppgforslag').textContent = (onskade && u.some(x => onskade.has(x.nr)))
      ? kalendertext(u) : forslagsText(forslag);
    $('#uppgater').hidden = !rort();
    const rader = $('#uppgnivaer');
    rader.innerHTML = '';
    /* Ett block i taget, nivåerna inuti blocket. Boken lägger uppgifterna i
       block efter varje teoridel och börjar om på NIVÅ 1 i nästa — «1101 … 1110,
       1116, 1117» på samma rad var bokens ordning men inte bokens mening: 1116
       är lätt i kubikrötter, inte en fortsättning på kvadratrötternas nivå 1.
       Blocket byts när avsnittet byts ELLER när nivån faller tillbaka, och det
       senare är det som fångar två block inuti samma avsnitt — 1.1 heter
       «Kvadratrötter och kubikrötter» och har ett block för vardera. Ett enda
       block får ingen rubrik: den hade upprepat det som står över remsan. */
    const block = [];
    u.forEach(x => {
      const f = block[block.length - 1];
      const nytt = !f || (x.avsnitt || {}).nr !== (f.avsnitt || {}).nr || x.niva < f.niva;
      if (nytt) block.push({ avsnitt: x.avsnitt, niva: x.niva, uppg: [x] });
      else { f.uppg.push(x); f.niva = x.niva; }
    });
    block.forEach((g, i) => {
      let host = rader;
      if (block.length > 1) {
        host = document.createElement('div');
        host.className = 'uppgavsnitt';
        const namn = document.createElement('span');
        namn.className = 'uppgavsnittnamn';
        /* Sidorna alltid — de skiljer två block i samma avsnitt åt. Avsnittet
           bara när det faktiskt byts, annars står samma rubrik två gånger. */
        const sidor = g.uppg.map(x => x.sida);
        const s1 = Math.min(...sidor), s2 = Math.max(...sidor);
        const bytt = !i || (g.avsnitt || {}).nr !== (block[i - 1].avsnitt || {}).nr;
        namn.textContent = (bytt && g.avsnitt ? `${g.avsnitt.nr} ${g.avsnitt.titel} · ` : '')
          + `s. ${s1 === s2 ? s1 : s1 + '–' + s2}`;
        host.appendChild(namn);
        rader.appendChild(host);
      }
      NIVA.forEach(n => {
        const del = g.uppg.filter(x => x.niva === n);
        if (!del.length) return;
        const rad = document.createElement('div');
        rad.className = 'uppgniva';
        rad.innerHTML = `<span class="uppgnivanamn">Nivå ${n}</span><div class="uppgchips"></div>`;
        const box = $('.uppgchips', rad);
        del.forEach(x => {
          const b = document.createElement('button');
          b.className = 'uppgchip';
          b.type = 'button';
          b.textContent = x.nr;
          /* Bokens eget exempel: numret står där, så det ska synas — annars
             ser listan ut att sakna 1102 — men det är ingenting att välja bort
             eller dela ut. Gråat och dött, med sitt skäl i tipset. */
          if (x.exempel) {
            b.toggleAttribute('data-exempel', true);
            b.disabled = true;
            b.dataset.tip = `s. ${x.sida} · genomräknat exempel i boken`;
            box.appendChild(b);
            return;
          }
          const av = bort.has(x.nr);
          b.setAttribute('aria-pressed', String(!av));
          b.toggleAttribute('data-bort', av);
          b.dataset.tip = `s. ${x.sida} · ${av ? 'klicka för att räkna den ändå' : 'klicka för att hoppa över'}`;
          b.addEventListener('click', () => {
            if (bort.has(x.nr)) bort.delete(x.nr); else bort.add(x.nr);
            rita();
            window.planKoll && window.planKoll();
          });
          box.appendChild(b);
        });
        host.appendChild(rad);
      });
    });
  }

  /* ── Att bolla urvalet ─────────────────────────────
     Modellen vet redan vilka uppgifter som står på sidorna, så det man skriver
     behöver inte vara en fullständig lista — ett nummer och ett verb räcker.
     Ändringen görs när svaret kommer, inte innan: annars säger chipsen en sak
     medan raden under fortfarande skriver en annan. */
  function fraga(text) {
    const t = String(text || '').trim();
    if (!t) return;
    const u = raknade();
    const namnda = (t.match(/\d{3,4}/g) || []).map(Number).filter(n => u.some(x => x.nr === n));
    const tarMed = /(ta med|behåll|tillbaka|inkludera|kör|räkna)/i.test(t);
    const hoppar = /(hoppa|skippa|ta bort|strunta|utan)/i.test(t);
    const nivan = (t.match(/niv[åa]\s*([123])/i) || [])[1];
    /* Svaret räknar på det urval ändringen GER, inte på det som står nu — säger
       raden «14 kvar» medan chipsen redan visar 16 tror man att appen räknat fel. */
    let svar = '';
    let gor = null;
    const efterat = andring => { const prov = new Set(bort); andring(prov); return u.filter(x => !prov.has(x.nr)).length; };
    const kvarText = n => `${n} ${n === 1 ? 'uppgift' : 'uppgifter'} att räkna`;

    if (namnda.length) {
      const till = tarMed ? false : hoppar ? true : !bort.has(namnda[0]);
      gor = m => namnda.forEach(n => { if (till) m.add(n); else m.delete(n); });
      const listan = ochLista(namnda.map(String));
      svar = till
        ? `Hoppar ${listan} också. Då blir det ${kvarText(efterat(gor))}.`
        : `${versal(listan)} är tillbaka i urvalet — ${kvarText(efterat(gor))}.`;
    } else if (nivan) {
      const n = Number(nivan);
      const del = u.filter(x => x.niva === n);
      const till = !(tarMed && !hoppar);
      gor = m => del.forEach(x => { if (till) m.add(x.nr); else m.delete(x.nr); });
      svar = till
        ? `Hoppar hela nivå ${n} — ${del.length} uppgifter. Kvar blir ${kvarText(efterat(gor))}.`
        : `Nivå ${n} är med igen, alla ${del.length} uppgifterna. Då blir det ${kvarText(efterat(gor))}.`;
    } else if (/alla/i.test(t) && tarMed) {
      gor = m => m.clear();
      svar = `Alla ${u.length} uppgifterna på sidorna är med. Ingen hoppas över.`;
    } else {
      svar = 'Jag hittade ingen uppgift i det du skrev. Skriv numret som det står i boken — till exempel «ta med 5123» eller «hoppa nivå 1».';
    }

    const host = $('#uppgsvar');
    const klart = () => {
      if (gor) gor(bort);
      $('#uppgfraga').value = '';
      rita();
      window.planKoll && window.planKoll();
    };
    if (window.Fraga && window.Fraga.kor) {
      window.Fraga.kor(host, { enkel: true, jobbtext: 'Läser sidorna igen …', vantan: 900, svar, efterKlar: klart });
    } else {
      host.hidden = false;
      host.textContent = svar;
      klart();
    }
  }

  /* Spannet ändras i remsan, i avsnittslistan och när boken byts — alla tre
     skriver momentfältet, så det är den händelsen panelen lyssnar på. Steg 3 får
     veta i samma andetag: raden om lösningsförslag finns bara när boken är en av
     källorna, och den frågan svarar på att dörren just öppnats. */
  const speglaSteg3 = () => { window.planKoll && window.planKoll(); };
  const moment = $('#moment');
  if (moment) moment.addEventListener('input', () => { synka(); rita(); speglaSteg3(); });
  const dorr = document.querySelector('.kalla[data-dorr="bok"]');
  if (dorr) dorr.addEventListener('click', () => setTimeout(() => { synka(); rita(); speglaSteg3(); }, 0));
  /* Servern svarade med lärarens hylla: spannet pekar på en annan bok nu, och
     uppgifterna hör till den. */
  document.addEventListener('bok-redo', () => { nyckel = ''; synka(); rita(); speglaSteg3(); });

  const NIVAFILTER = { 'Inga': [], 'Alla': [1, 2, 3], 'Nivå 2 och 3': [2, 3], 'Bara nivå 3': [3] };
  const losningarna = niva => {
    const f = NIVAFILTER[niva] || NIVAFILTER['Nivå 2 och 3'];
    return raknade().filter(x => !bort.has(x.nr) && f.includes(x.niva));
  };

  window.Uppgifter = {
    /* Steg 3 frågar om raden ska finnas alls: lösningsförslag till bokens
       uppgifter går bara att välja när boken faktiskt är en av källorna. */
    finns: () => !!(dorr && dorr.getAttribute('aria-pressed') === 'true' && alla().length),
    /* Skrivtypen bytte — rita om så att blocket följer med ner (provet)
       eller upp igen (tavla, arbetsblad, gruppuppgift). Hoppades faktapasset
       för att en mätning skrevs tas det nu: panelen är uppe igen och behöver
       sina uppgifter. `hoppat` skrivs om av hämtningen själv, så varvet
       stannar. */
    spegla: () => {
      rita();
      if (hoppat && !(window.Helhetstyp && window.Helhetstyp())) hamta();
    },
    /* Uppgifterna som stod på lektionen i kalendern, i bokens egen skrivning:
       «1101–1103, 1105–1119». Anropas när en lektion väljs (profil.js) — spannet
       är redan satt då, så listan gäller de sidor som just slogs upp. Sidorna
       kan komma från servern i efterhand; `onskade` ligger kvar och slår till
       när uppgifterna dyker upp (standardbort). Tom källdag med flit: den här
       vägen ÄR lektionens egen rad, och raden citerar henne därefter. */
    franKalendern: text => las(text, ''),
    losningsantal: niva => losningarna(niva).length,
    avsnittsnamn: () => { const a = avsnittet(); return a ? `${a.nr} ${a.titel}` : 'avsnittet'; },
    /* Noten i steg 3 får bara plats på en rad, och där duger numret: rubriken står
       redan i kvittot ovanför. En not som radbryts sköt pricken upp på en egen rad. */
    avsnittsnr: () => { const a = avsnittet(); return a ? a.nr : 'avsnittet'; },
    /* Snapshot, inte uppslag: en tavla i Sparat ska peka på de uppgifter den
       skrevs för, även efter att spannet ändrats i planeringen. */
    urval(instans) {
      if (!window.Uppgifter.finns()) return null;
      const s = spann(), u = raknade();
      const kvar = u.filter(x => !bort.has(x.nr));
      const i = instans || {};
      const los = losningarna(i.boklosniva);
      return {
        bok: s.bok, sidor: `${s.fran}–${s.till}`, avsnitt: window.Uppgifter.avsnittsnamn(),
        /* Bokens id på servern följer med pappret: ett dokument ska kunna peka
           tillbaka på de sidor det skrevs ur, också nästa termin. null för
           prototypens böcker — de finns ingenstans att peka på. */
        bokId: bokId(),
        uppg: kvar.map(x => x.nr), bort: [...bort].sort((a, b) => a - b),
        remsa: remsa(kvar.map(x => x.nr)), bortremsa: remsa([...bort]),
        /* Posterna bär NIVÅN, inte bara numret: lösningsbladet sätter nivå 3 som
           bedömd elevlösning och nivå 1–2 som svarsfacit, och utan nivån här kan
           det inte veta vilken form uppgiften ska få. */
        /* Inget lösningsblad till bokens uppgifter för provet:
           de har sitt eget lösningsförslag och sitt formelblad, och bokens
           lösningar är det klassen ÖVADE med. Utan raden här hade tryck.js
           lagt en «Lösningsförslag · boken»-flik i provets paket, eftersom
           bokuppg.losning är det enda den läser. Upplägget kan sakna fälten
           helt (typen har ingen sådan rad) — också det är ett nej. */
        losning: (i.boklosning === false || i.boklosniva === undefined
                  || (window.Helhetstyp && window.Helhetstyp()))
          ? null
          : { niva: i.boklosniva || 'Nivå 2 och 3', antal: los.length, uppg: los.map(x => x.nr), poster: los.map(x => ({ nr: x.nr, niva: x.niva })), remsa: remsa(los.map(x => x.nr)) }
      };
    }
  };

  synka();
  rita();
})();
