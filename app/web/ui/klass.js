/* ══════════ KLASSVYN ══════════
   Materialet bor inte i ett arkiv — det bor på lektionen. Klassvyn är samma
   vecka som planeringen arbetar i, fast bakåt och framåt: klass för klass, eller
   alla klasser samtidigt (hela lärarens schema, som det kommer från skolan).
   Lektionen ÄR valet: klick markerar den, klick igen avmarkerar, och flera går
   bra — också över klassgränsen. Klicket är också starten: förvalen ur
   klassprofilen sätts direkt och steg 2 låses upp, så det finns ingen knapp
   emellan. Ingen «Allt sparat»-hög längre: allt godkänt ligger på sin lektion,
   i den vecka det gäller. */
window.Klass = (() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const grid = $('#schemagrid');
  const K = window.Kalender;
  if (!grid || !K) return { rita() {}, fragan: () => null };

  let vald = 'alla';
  const oppningsvecka = () => (K.nastaSkolvecka ? K.nastaSkolvecka(K.idag())
                                                : K.mandagen(K.idag()));
  let mandag = oppningsvecka();
  /* Öppningsveckan räknas ur schemat OCH loven — och de kommer från servern en
     stund efter att den här filen kört. Räknades den bara en gång stod veckan
     kvar på PROTOTYPENS lov: en lärare vars skola har lov en annan vecka fick
     appen öppnad i fel vecka, och den rättade sig aldrig. Nu räknas den om när
     servern svarat — men bara om läraren inte redan bläddrat själv. */
  let styrd = false;
  if (K.redo && K.redo.then) K.redo.then(() => {
    if (styrd) return;
    const ny = oppningsvecka();
    if (ny === mandag) return;
    mandag = ny;
    rita();
  });
  let avvisat = false;
  /* Klassprofilen är fälld ihop som förval: klicket på en klass ska filtrera
     veckan, inte fylla skärmen med minnet av klassen. */
  let visaProfil = false;

  const dok = () => (window.Dokument && window.Dokument.sparade ? window.Dokument.sparade() : []);
  const start = t => String(t || '').split('–')[0].trim();
  const kort = k => String(k || '').replace('Matematik ', 'Ma ');
  const dagen = iso => new Date(iso + 'T12:00:00');
  const flytta = (iso, n) => { const d = dagen(iso); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };
  const kvarTill = iso => Math.round((dagen(iso) - dagen(K.idag())) / 86400000);
  const namnPa = v => window.Dokument && window.Dokument.namn ? window.Dokument.namn(v) : v.typ;
  const versal = s => String(s || '').charAt(0).toUpperCase() + String(s || '').slice(1);

  /* ── Klasserna ─────────────────────────────────────
     Listan är schemat: varje klass läraren har lektioner med. Egna klasser
     läggs in i samma schema och blir därför likadana här och i planeringen. */
  function klasser() {
    const lista = [];
    K.schema.forEach(s => {
      if (!s.klass) return;
      let t = lista.find(x => x.klass === s.klass);
      if (!t) lista.push(t = { klass: s.klass, kurser: [] });
      if (s.kurs && !t.kurser.includes(s.kurs)) t.kurser.push(s.kurs);
    });
    return lista;
  }
  const lektionerna = d => (d.lov ? [] : d.schema.filter(s => vald === 'alla' || s.klass === vald))
    .slice().sort((a, b) => start(a.tid).localeCompare(start(b.tid)));
  /* Vilken kurs läser klassen ett visst datum? En extralektion i kalendern bär
     bara klassen, och kortet ska ändå kunna säga vad timmen är. Schemaraden som
     GÄLLER den dagen svarar först (en klass kan byta kurs mitt i läsåret),
     annars klassens första rad, annars ingenting alls. */
  const kursFor = (klass, datum) => {
    const rader = K.schema.filter(s => s.klass === klass);
    const gallande = rader.find(s => (!s.fran || datum >= s.fran) && (!s.till || datum <= s.till));
    return (gallande || rader[0] || {}).kurs || '';
  };

  /* Ett dokument hör till lektionen: samma dag, samma klass, samma kurs — och
     samma klockslag när dokumentet vet sitt klockslag. */
  const dokFor = (datum, s) => dok().filter(v => v.datum === datum && (v.klass || '') === (s.klass || '')
    && (!v.tid || !s.tid || start(v.tid) === start(s.tid))
    && (!v.kurs || !s.kurs || v.kurs === s.kurs));

  /* Kalenderposter som bara speglar ett sparat dokument ska inte stå två gånger. */
  const spegling = p => dok().some(v => v.datum === p.datum && (v.klass || '') === (p.klass || '')
    && new RegExp('^(' + v.typ + (v.variant ? '|' + v.variant : '') + ')', 'i').test(p.titel || ''));
  /* Synken märker proven den läser (calendar_google.provslag), och då är slaget
     svaret — titeln gissas bara på när slaget saknas: prototypens poster och
     det läraren själv skrivit in. Skolans NP heter «NP MAT nivå 1c», aldrig
     «nationellt prov», och gick därför inte att känna igen på titeln alls. */
  const PROVSLAG = ['prov', 'diagnos', 'np'];
  const arProv = p => (p.slag ? PROVSLAG.includes(p.slag)
                              : /prov/i.test(p.titel || '')) && !egetProv(p);
  /* Diagnosen är ett prov i allt som rör veckan — den tar en lektion i anspråk
     och behöver material — men den heter diagnos, och korten ska säga det. */
  const provOrd = p => p.slag === 'diagnos' ? 'Diagnos' : 'Prov';
  /* Ett nationellt prov är inte lärarens att skriva — det ligger i kalendern som
     en tid att hålla, inte som en uppgift att göra. */
  const egetProv = p => p.slag === 'np' || /nationell/i.test(p.titel || '');
  const posterFor = d => K.poster.filter(p => p.datum === d.datum && !spegling(p)
    && (vald === 'alla' ? true : p.klass === vald));
  /* Ligger posten i en lektionsruta? Då handlar den OM lektionen och ska inte
     stå som ett eget kort bredvid ett tomt lektionskort — schemaraden säger
     att det brukar vara lektion måndag 08:10, kalendern säger vad det är den
     24 augusti («Hämta läromedel i läromedelscentralen, hela passet»).
     Provet får matcha utan klockslag — en heldagspost är ändå provet — men
     allt annat måste ligga på lektionens tid: «Öppet hus» hela dagen är inte
     klassens lektion. */
  const iRutan = (p, s) => (p.klass || '') === (s.klass || '')
    && (arProv(p) ? (!p.tid || !s.tid || start(p.tid) === start(s.tid))
                  : !!(p.tid && s.tid && start(p.tid) === start(s.tid)));

  /* ── Att gå från schemat till planeringen ──────────
     Klicket väljer lektionen i kön, låser upp steg 2 och rullar upp. Ingen ny
     väg in i appen — samma väg som veckan i steg 1, bara startad härifrån. */
  function rullaNer() {
    const panel = $('#vy-planering .panel');
    if (!panel) return;
    const y = Math.max(0, panel.getBoundingClientRect().top + window.scrollY - 96);
    (window.rullaTill || (v => window.scrollTo(0, v)))(y, 700);
  }
  function rullaUpp() {
    const ruta = $('#klassvyn');
    if (!ruta) return;
    const y = Math.max(0, ruta.getBoundingClientRect().top + window.scrollY - 84);
    (window.rullaTill || (v => window.scrollTo(0, v)))(y, 700);
  }
  /* Klassprofilen öppnas där den ligger — mellan veckan och terminen. I
     terminsläget låg den förut under hela terminsvyn, alltså flera tusen pixlar
     ner, och klicket såg ut att inte göra något. Ordningen är löst i app.html;
     den här rullningen tar de sista pixlarna när panelen hamnar under kanten. */
  function rullaTillProfil() {
    const pr = $('#klassprofil');
    if (!pr || pr.hidden) return;
    const r = pr.getBoundingClientRect();
    if (r.top > 80 && r.bottom < window.innerHeight) return;
    const y = Math.max(0, r.top + window.scrollY - 96);
    const fran = window.scrollY;
    (window.rullaTill || (v => window.scrollTo(0, v)))(y, 620);
    /* Tweenen går genom requestAnimationFrame. Levereras ingen ram — fliken låg i
       bakgrunden, eller en annan rullning avbröt den — står sidan kvar där den
       stod, och då «händer ingenting» när man klickar Profil: exakt det fel som
       rättades i granskning 8. Kontrollen tar de pixlarna direkt i stället. */
    setTimeout(() => {
      if (Math.abs(window.scrollY - fran) < 2 && Math.abs(y - fran) > 2) window.scrollTo(0, y);
    }, 260);
  }
  const narOrd = post => dagen(post.datum).toLocaleDateString('sv-SE', { weekday: 'long', day: 'numeric', month: 'long' });

  /* Förvalen hör till den lektion som FAKTISKT planeras — köns första — inte
     till den man råkade klicka sist. Annars fick man 9A ur kön och Matematik 4
     ur klicket: en kombination som inte finns i schemat. */
  const planeras = post => (window.PlanKo && window.PlanKo.aktiv && window.PlanKo.aktiv()) || post;
  /* Är det samma lektion? Dag, timme och klass räcker — kursen kan skrivas om
     under kön när schemat läses om (plankon farsk). */
  const nyckeln = p => p ? `${p.datum}|${p.tid}|${p.klass}` : '';
  /* Vad lektionen redan har på sig — så att steg 1 kan säga det i stället för att
     föreslå en kopia. */
  function speglaFinns(post) {
    if (!window.SattFinns) return;
    const p = post || planeras(post);
    window.SattFinns(p ? [...new Set(dokFor(p.datum, p).filter(v => !v.losningsblad).map(v => v.typ))] : []);
  }

  /* Kön vet vilka lektioner som är avklarade — men veckan sa bara «Vald» om dem
     alla. Med två klasser i kön är det just skillnaden man behöver se. */
  const arKlar = post => !!(window.PlanKo && window.PlanKo.arKlar && window.PlanKo.arKlar(post));

  function planera(post, typ) {
    if (window.PlanKo) {
      if (!window.PlanKo.har(post)) window.PlanKo.vaxla(post);
      window.PlanKo.starta();
    }
    if (typ && window.SattLage) window.SattLage(typ);
    if (window.PlanSteg) window.PlanSteg.las(2, false);
    /* Klassprofilen fyller i resten: kurs, bok, sidorna efter förra lektionen och
       det centrala innehållet som följer av sidorna. */
    const ur = window.Profil && window.Profil.anvand ? window.Profil.anvand(planeras(post), typ) : null;
    speglaFinns(planeras(post));
    rita();
    rullaNer();
    window.toast && window.toast(`${typ ? typ + ' till' : 'Planerar'} ${post.klass || 'lektionen'} ${narOrd(post)} ${start(post.tid) || ''}${ur && ur.length ? ' — förvalen kommer ur klassprofilen' : ' — välj vad det ska utgå från'}`);
  }

  /* ── Att markera lektioner ─────────────────────────
     Klicket på kortet ÄR starten. Förr låg det en rad under veckan med «Planera
     dem» — men den gjorde valet till ett halvt val: lektionen blev blå utan att
     något hände, och förvalen kom först när man hittade knappen. Nu sätter
     klicket förvalen ur klassprofilen direkt och låser upp steg 2. Läraren
     rullar själv ner till «Vad ska du skapa?» — flera lektioner går bra, de
     planeras en i taget i turordning. */
  function markera(post, el) {
    if (omprovDok) return omprovDag(post);
    if (!window.PlanKo) return;
    /* Vilken lektion som planerades INNAN klicket — se avmarkeringen nedan. */
    const fore = planeras(null);
    const pa = window.PlanKo.vaxla(post);
    if (el) el.toggleAttribute('data-vald', pa);
    const valda = window.PlanKo.valda ? window.PlanKo.valda() : [];
    if (!pa) {
      /* Sista lektionen avmarkerad: förvalen som appen själv satte släpper med. */
      if (!valda.length && window.Profil && window.Profil.slapp) window.Profil.slapp(true);
      if (!valda.length) speglaFinns(null);
      /* Tog man bort den lektion som PLANERADES tar nästa i kön över. Fälten
         fylldes om av kön (plankon fyll), men förvalen stod kvar hos den
         borttagna: TE26A:s lektion blev stående med NA26F:s s. 2–6 fast
         kalendern säger s. 2–4 om den. Den nya lektionen ska ha sina egna. */
      else {
        const nu = planeras(null);
        if (nu && (!fore || nyckeln(nu) !== nyckeln(fore))) {
          window.Profil && window.Profil.anvand && window.Profil.anvand(nu, nu.slag === 'prov' ? 'Prov' : null);
          speglaFinns(nu);
        }
      }
      rita(true);
      return;
    }
    if (window.PlanSteg) window.PlanSteg.las(2, false);
    /* Remsan och förvalen hör till den lektion som FAKTISKT planeras — köns
       första — inte till den man råkade klicka sist. */
    const nu = planeras(post);
    const ur = window.Profil && window.Profil.anvand ? window.Profil.anvand(nu, post.slag === 'prov' ? 'Prov' : null) : null;
    speglaFinns(nu);
    rita(true);
    /* Köns remsa säger redan vilken lektion som planeras. Syns den på skärmen är
       pillret bara samma mening en andra gång — ovanpå den första. */
    const remsan = $('#vy-planering .konrad');
    if (remsan && !remsan.hidden) {
      const r = remsan.getBoundingClientRect();
      if (r.height && r.top > 60 && r.bottom < window.innerHeight - 90) return;
      /* Första valet, och skapandet ligger under vikningen: ta med läraren
         dit i stället för att bara berätta om det i ett piller nere i hörnet.
         En ny användare såg annars en kalender och inget mer — prov och
         arbetsblad fanns inte förrän hon råkade rulla. */
      if (valda.length === 1 && r.height && r.top >= window.innerHeight - 90) {
        const mal = Math.max(0, r.top + window.scrollY - 120);
        if (window.rullaTill) window.rullaTill(mal);
        else window.scrollTo({ top: mal, behavior: 'smooth' });
        return;
      }
    }
    window.toast && window.toast(valda.length > 1
      ? `${valda.length} lektioner valda — de planeras en i taget, först ${nu.klass || 'lektionen'} ${narOrd(nu)} ${start(nu.tid) || ''}`
      : `Planerar ${post.klass || 'lektionen'} ${narOrd(post)} ${start(post.tid) || ''}${ur && ur.length ? ' — förvalen kommer ur klassprofilen' : ''}`);
  }

  /* ── Omprovet väljer bara sin dag ───────────────────
     Provet vet redan klassen, det centrala innehållet, underlaget och provtiden.
     Därför är omprovet inget nytt formulär: bandet står över veckan och nästa
     klick på en lektion är dagen. */
  let omprovDok = null;
  /* Chipet som just nu dras mot en annan lektion. Draget är kopiering, aldrig
     flytt: NA-klassen och TE-klassen läser samma kapitel i otakt, och samma
     tavla ska kunna läggas på båda utan att skrivas om (Dokument.aterAnvand). */
  let dragDok = null;
  /* Städningen efter draget ligger på DOKUMENTET, inte bara på chipet: bläddrar
     man veckan under draget river rita() käll-chipet, och då eldar dess dragend
     i tomma luften utan att nå hit. Utan den centrala städningen läckte dragDok
     vidare, och nästa klick i veckan lästes av släppytorna som ett pågående
     drag. */
  function stadaDrag() {
    dragDok = null;
    $$('.lekt[data-drop]').forEach(x => x.removeAttribute('data-drop'));
    [$('#schemafram'), $('#schemabak')].forEach(p => p && p.removeAttribute('data-dragmal'));
  }
  document.addEventListener('dragend', stadaDrag);
  document.addEventListener('drop', stadaDrag);
  function valjOmprov(v) {
    omprovDok = v;
    if (v.klass) vald = v.klass;
    /* Omprovet ligger framåt — veckan öppnas där skolan är igång igen. */
    mandag = K.nastaSkolvecka ? K.nastaSkolvecka(K.idag()) : K.mandagen(K.idag());
    avvisat = true;
    rita();
    rullaUpp();
    window.toast && window.toast(`Omprov av ${namnPa(v)} — välj dagen i veckan, allt annat är förvalt`);
  }
  function slappOmprov(tyst) {
    if (!omprovDok) return;
    omprovDok = null;
    window.Dokument && window.Dokument.slappOmprov && window.Dokument.slappOmprov();
    rita();
    if (!tyst) window.toast && window.toast('Omprovet avbrutet');
  }
  function omprovDag(post) {
    const v = omprovDok;
    omprovDok = null;
    if (window.PlanKo && window.PlanKo.enbart) window.PlanKo.enbart(Object.assign({}, post, { slag: 'prov' }));
    if (window.SattLage) window.SattLage(v.typ);
    /* Sista steget: upplägget står redan ifyllt — kvar är att skriva provet. */
    if (window.PlanSteg) window.PlanSteg.las(9, false);
    rita();
    rullaNer();
    window.toast && window.toast(`Omprovet ligger ${narOrd(post)} ${start(post.tid) || ''} — klass, innehåll och upplägg är förvalt. Skriv provet.`);
  }
  function ritaOmprovband() {
    const b = $('#omprovband');
    if (!b) return;
    b.hidden = !omprovDok;
    if (!omprovDok) return;
    $('#omprovbandtext').textContent = `Omprov av ${namnPa(omprovDok)}${omprovDok.klass ? ' · ' + omprovDok.klass : ''} — klassen, det centrala innehållet, underlaget och provtiden följer med. Klicka lektionen då omprovet ska skrivas.`;
  }
  $('#omprovavbryt') && $('#omprovavbryt').addEventListener('click', () => slappOmprov());
  $('#planbyt') && $('#planbyt').addEventListener('click', rullaUpp);

  /* ── Klassremsan: veckans filter ─────────────────────
     Hela lärarens schema på en gång är rätt när man vill se dagen, men fel när
     man vill veta vad EN klass har kvar. Remsan är därför ett filter: «Alla
     klasser» eller en klass, och veckan behåller sina tider, salar och kurser.
     Räknaren på chipet säger hur stor del av veckan som redan har material — det
     är den siffran man annars måste byta klass för att läsa av. */
  function veckolaget(kl) {
    const bild = K.veckoBild(mandag);
    let n = 0, klara = 0;
    bild.dagar.forEach(d => {
      if (d.lov) return;
      d.schema.forEach(s => {
        if (kl !== 'alla' && s.klass !== kl) return;
        n++;
        if (dokFor(d.datum, s).length) klara++;
      });
    });
    return { n, klara };
  }
  function ritaKlassrad() {
    const rad = $('#klassrad');
    if (!rad) return;
    rad.innerHTML = '';
    const gor = (namn, varde, kurser) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'klasschip';
      b.setAttribute('aria-pressed', String(vald === varde));
      const l = veckolaget(varde);
      b.dataset.tip = varde === 'alla'
        ? `Hela schemat — ${l.klara} av ${l.n} lektioner i veckan har material`
        : `Visa bara ${namn} i veckan — ${l.klara} av ${l.n} lektioner har material. Tid, sal och kurs står kvar.`;
      b.innerHTML = `<span></span>${kurser && kurser.length ? `<span class="kkurs">${kurser.map(kort).join(' · ')}</span>` : ''}`
        + (l.n ? `<span class="klage"${l.klara >= l.n ? ' data-klar' : ''}>${l.klara}/${l.n}</span>` : '');
      $('span', b).textContent = namn;
      b.addEventListener('click', () => {
        vald = varde;
        avvisat = false;
        if (varde === 'alla') visaProfil = false;
        rita();
      });
      rad.appendChild(b);
    };
    gor('Alla klasser', 'alla');
    /* Klasserna läggs inte in för hand — de kommer ur kalendern med kurs, tid och
       sal. Det behöver inte stå i remsan: synkraden ovanför säger det redan. */
    /* Kursen står på varje lektionskort i veckan — den behöver inte stå på chipet
       också. Utan den får hela filtret plats på veckans egen rad. */
    klasser().forEach(k => gor(k.klass, k.klass));
    if (vald !== 'alla') {
      const p = document.createElement('button');
      p.type = 'button';
      p.className = 'profilknapp';
      p.setAttribute('aria-pressed', String(visaProfil));
      p.innerHTML = 'Profil<span class="valjpil"></span>';
      p.dataset.tip = 'Vad appen minns om klassen — kurs, bok, takt och vanor. Ligger under veckan.';
      p.addEventListener('click', () => {
        visaProfil = !visaProfil;
        rita(true);
        /* Panelen ligger under veckan — och i terminsläget under hela terminen,
           alltså flera tusen pixlar bort. Ett klick som «inte gör något» är värre
           än en panel som ligger långt ner: ordningen står kvar (schemat trycks
           aldrig ur bild när man väljer klass) och vi rullar dit i stället. */
        if (visaProfil) rullaTillProfil();
      });
      rad.appendChild(p);
    }
  }

  /* Chipsremsan är densamma på en lektion och på ett löst dokument. */
  function dokremsa(docs, insp, post) {
    const remsa = document.createElement('div');
    remsa.className = 'lektdok';
    insp.forEach(p => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'dokchip';
      b.setAttribute('data-insp', '');
      b.dataset.tip = `${p.namn} — lyssna, fråga transkriptet och hoppa till stället i inspelningen`;
      b.textContent = `▶ ${p.langd || 'Inspelning'}`;
      b.addEventListener('click', e => { e.stopPropagation(); window.Lektion && window.Lektion.oppna && window.Lektion.oppna(p.el); });
      remsa.appendChild(b);
    });
    docs.forEach(v => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'dokchip';
      if (v.losningsblad) b.setAttribute('data-los', '');
      b.dataset.tip = `${namnPa(v)} — öppna, granska eller ladda ner som PDF`;
      /* Två arbetsblad på samma lektion är inte samma papper: det ena är
         klassens, det andra hör till en elev (Etapp 4). Brickan säger vem —
         annars går de inte att skilja åt i remsan. */
      b.textContent = v.losningsblad ? (v.typ === 'Prov' ? 'Lösningar' : 'Facit')
        : (v.variant || (v.elev ? `${v.typ} · ${v.elev.split(' ')[0]}` : v.typ));
      b.addEventListener('click', e => { e.stopPropagation(); window.Dokument && window.Dokument.visa && window.Dokument.visa(dok().indexOf(v)); });
      /* Chipet går att DRA till en annan lektion — släpp, och kopian lägger sig
         där (aterAnvand). Målet behöver inte ligga i den ritade veckan: håller
         man chipet över veckopilen bläddrar den under draget (pilDrag). Prov
         sprids inte mellan klasser, facit hör till sitt blad och elevpapper
         till sin elev — de dras inte. */
      if (!v.losningsblad && !v.elev && v.typ !== 'Prov') {
        b.draggable = true;
        b.dataset.tip += ' — eller dra till en annan lektion; pilarna bläddrar veckan under draget';
        b.addEventListener('dragstart', e => {
          dragDok = v;
          e.dataTransfer.setData('text/plain', namnPa(v));
          e.dataTransfer.effectAllowed = 'copy';
          /* Pilarna lyser upp: de är en del av gesten så länge draget pågår. */
          [$('#schemafram'), $('#schemabak')].forEach(p => p && p.setAttribute('data-dragmal', ''));
        });
        /* Chipets EGNA dragend står kvar bredvid dokumentets: bläddrar man
           veckan mitt i draget rivs chipet av rita(), och ett rivet element
           bubblar inte längre upp till document. Den som fortfarande hänger
           kvar i DOM:en städas alltså här, resten av stadaDrag. */
        b.addEventListener('dragend', stadaDrag);
      }
      remsa.appendChild(b);
    });
    /* Provet bär sina två skyldigheter där det ligger: rättningen efteråt och
       omprovet för dem som missade. Ingen hög att gå till. */
    const provet = docs.find(v => v.typ === 'Prov' && !v.losningsblad);
    if (provet) {
      const ra = document.createElement('button');
      ra.type = 'button';
      ra.className = 'dokchip';
      ra.setAttribute('data-atgard', '');
      if (provet.rattat) ra.setAttribute('data-klar', '');
      ra.textContent = provet.rattat ? `Rättat · ${Math.round((provet.rattat.andel || 0) * 100)} %` : 'Rätta';
      ra.dataset.tip = provet.rattat ? 'Ändra klassens poäng' : 'Mata in klassens poäng per uppgift';
      ra.addEventListener('click', e => { e.stopPropagation(); window.Rattning && window.Rattning.oppna(provet); });
      remsa.appendChild(ra);
      const om = document.createElement('button');
      om.type = 'button';
      om.className = 'dokchip';
      om.setAttribute('data-atgard', '');
      om.textContent = 'Nytt omprov';
      om.dataset.tip = 'Samma prov en gång till — allt förvalt utom dagen';
      om.addEventListener('click', e => { e.stopPropagation(); window.Dokument && window.Dokument.omprov && window.Dokument.omprov(provet); });
      remsa.appendChild(om);
    }
    if (post) {
      const mer = document.createElement('button');
      mer.type = 'button';
      mer.className = 'dokchip';
      mer.setAttribute('data-mer', '');
      mer.textContent = docs.length ? '+ Mer' : '+ Skriv';
      mer.dataset.tip = 'Skapa något till den här lektionen';
      mer.addEventListener('click', e => { e.stopPropagation(); planera(post); });
      remsa.appendChild(mer);
    }
    return remsa;
  }

  /* Ett godkänt dokument kan ligga på en dag utan lektion — ett prov på «annan
     dag». Då får det ett eget kort där det ligger, med samma chips som på en
     lektion. Utan det här försvann provet ur veckan helt. */
  function dokkort(d, docs) {
    const el = document.createElement('article');
    el.className = 'lekt';
    el.setAttribute('data-klar', '');
    if (docs.some(v => v.typ === 'Prov')) el.setAttribute('data-prov', '');
    if (d.datum < K.idag()) el.setAttribute('data-forbi', '');
    const f = docs[0];
    el.innerHTML = `<div class="lekttopp"><span class="lekttid">${start(f.tid) || 'Hela dagen'}</span>${f.klass ? '<span class="lektklass"></span>' : ''}</div><p class="lektnamn"></p>`;
    if (f.klass) $('.lektklass', el).textContent = f.klass;
    $('.lektnamn', el).textContent = f.kurs ? kort(f.kurs) : namnPa(f);
    el.appendChild(dokremsa(docs, [], null));
    el.insertAdjacentHTML('beforeend', '<span class="lektbokat">Utanför schemat</span>');
    return el;
  }

  /* ── Vad lektionen handlar om ──────────────────────
     Lärarens egen grovplanering står i kalendern, rad för rad: sidorna,
     uppgifterna och hjälpmedlen per lektion (calendar_google → innehallFor).
     Förvalen har alltid läst den — men VECKAN sa ingenting. Kortet fick en text
     bara när läraren råkat lägga en egen post i lektionens timme, så av tolv
     lektioner med sidor i kalendern visade två vad de handlade om, och resten
     stod som anonyma rutor med tid och klass.

     Sidorna säger sitt riktiga namn när kursens bok finns på hyllan: registret
     översätter s. 2–4 till «1.1 Kvadratrötter och kubikrötter». Utan bok för
     kursen står sidorna för sig själva — sant, och mer än ingenting. */
  const sidorna = (f, t) => f === t ? `s. ${f}` : `s. ${f}–${t}`;
  function innehallsrad(inn, kurs) {
    /* TRE STEG, I FALLANDE NÄRHET TILL LÄRARENS EGNA ORD.
       1. Delarnas rubriker: hon skriver dem framför sidspannet i beskrivningen,
          «Kvadratrötter: s. 2–4», och de är hennes ord om var DEL. De vet något
          boken inte kan veta: avsnitt 1.1 heter «Kvadratrötter och kubikrötter»
          och går över s. 2–6, så registret lovade dubbelt så mycket.
       2. Titelns rubrik: «NA26F: Faktorisering och förkortning» är hennes ord
          om HELA lektionen. Utan den stod «del av 1.3 Uttryck» på en lektion
          hon aldrig kallat så, för beskrivningen bar bara sidorna.
       3. Boken, som bara vet avsnittsnamnet. */
    const egna = (inn.delar || []).filter(d => d && d.rubrik);
    if (egna.length) return egna.map(d => `${d.rubrik}, ${sidorna(d.fran, d.till)}`).join(' · ');
    if (inn.rubrik) return `${inn.rubrik}, ${sidorna(inn.fran, inn.till)}`;
    const A = (kurs && window.Bok && window.Bok.registerFor) ? (window.Bok.registerFor(kurs) || []) : [];
    const del = (window.Bok && window.Bok.avsnitten) ? window.Bok.avsnitten(A, inn.fran, inn.till) : [];
    if (!del.length) return sidorna(inn.fran, inn.till);
    /* Ett spann över ett halvt kapitel ska inte rada upp åtta rubriker på ett
       kort — då säger första och sista mer än alla däremellan. */
    if (del.length > 3) {
      return `${del[0].a.nr}–${del[del.length - 1].a.nr} ${del[del.length - 1].a.titel}, ${sidorna(inn.fran, inn.till)}`;
    }
    /* Kommat binder avsnittet till SINA sidor, mittpunkten skiljer avsnitten åt:
       «1.1 Kvadratrötter och kubikrötter, s. 5–6 · 1.2 Tal i potensform, s. 7–9».

       «Del av» är inte pynt. Avsnitt 1.1 heter «Kvadratrötter och kubikrötter»
       och går över s. 2–6; lektionen på s. 2–4 är kvadratrötterna. Kortet
       påstod hela rubriken och sa alltså mer än kalendern gjorde — läraren såg
       «kubikrötter» på en lektion hon skrivit «kvadratrötter» om. Rubriken är
       bokens, sidorna är lektionens, och att de inte täcker varandra ska
       synas. (Vilken HALVA av avsnittet det är vet appen inte: registret är
       innehållsförteckningen, och lärarens egna ord i beskrivningen får inte
       sparas — se INTEGRITET i calendar_google.) */
    return del.map(d => `${d.hela ? '' : 'del av '}${d.a.nr} ${d.a.titel}, ${sidorna(d.fran, d.till)}`).join(' · ');
  }

  /* ── Lektionskortet ────────────────────────────────── */
  function lektkort(d, s) {
    const docs = dokFor(d.datum, s);
    /* Inspelningen är vad som HÄNDE på lektionen — den hänger på lektionen,
       före materialet som skrevs efteråt. */
    const insp = (window.Inspelningar && window.Inspelningar.forLektion) ? window.Inspelningar.forLektion(d.datum, s) : [];
    const post = { datum: d.datum, tid: s.tid, kurs: s.kurs, klass: s.klass, sal: s.sal };
    const bokatProv = K.poster.find(p => p.datum === d.datum && arProv(p) && !spegling(p) && iRutan(p, s));
    /* Vad kalendern säger att rutan är just den här dagen, när det inte är ett
       prov. Följer med i posten: förvalen ska inte gissa fram en sidsträcka ur
       klassprofilen på en lektion där läraren skrivit att klassen hämtar
       böcker — tystnaden om sidor är ett besked, inte ett tomrum (profil.js). */
    const rutan = bokatProv ? null
      : (K.poster.find(p => p.datum === d.datum && !spegling(p) && iRutan(p, s)) || null);
    if (rutan) post.rutan = rutan.titel;
    const el = document.createElement('article');
    el.className = 'lekt';
    /* Raden kommer inte ur veckoschemat utan ur kalendern (se ritaVeckan). Den
       ska bete sig som en lektion i allt, men märkningen finns så att CSS och
       tester kan skilja den extra timmen från den återkommande. */
    if (s.extra) el.setAttribute('data-extra', '');
    if (d.datum < K.idag()) el.setAttribute('data-forbi', '');
    if (docs.length) el.setAttribute('data-klar', '');
    /* Streckad kant betyder «här saknas material». Säger kalendern vad rutan
       är gör den inte det — det är ingen lucka att fylla. */
    else if (!rutan) el.setAttribute('data-tom', '');
    if (bokatProv || docs.some(v => v.typ === 'Prov')) el.setAttribute('data-prov', '');
    if (window.PlanKo && window.PlanKo.har(post)) el.setAttribute('data-vald', '');
    if (arKlar(post)) el.setAttribute('data-koklar', '');
    if (window.PlanKo && window.PlanKo.arNu(post)) el.setAttribute('data-nu', '');
    el.setAttribute('data-valjbar', '');
    /* Posten stannar på kortet: då kan markeringen uppdateras PÅ PLATS när man
       väljer, i stället för att hela veckan ritas om — en omritning kastar bort
       ringens animation och läses som ett hopp. */
    el.dataset.post = JSON.stringify(post);
    el.dataset.tip = omprovDok ? 'Klicka för att lägga omprovet här' : 'Klicka för att välja lektionen — flera går bra';
    el.addEventListener('click', e => { if (e.target.closest('button')) return; markera(post, el); });
    /* Släppytan för ett draget chip. Kopiering, aldrig flytt — och aldrig till
       samma lektion som originalet redan ligger på. */
    el.addEventListener('dragover', e => {
      if (!dragDok) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'copy';
      el.setAttribute('data-drop', '');
    });
    el.addEventListener('dragleave', () => el.removeAttribute('data-drop'));
    el.addEventListener('drop', e => {
      if (!dragDok) return;
      e.preventDefault();
      el.removeAttribute('data-drop');
      const v = dragDok;
      dragDok = null;
      if (v.datum === post.datum && (v.klass || '') === (post.klass || '')
          && (!v.tid || !post.tid || start(v.tid) === start(post.tid))) {
        window.toast && window.toast(`${namnPa(v)} ligger redan på den här lektionen`);
        return;
      }
      window.Dokument && window.Dokument.aterAnvand && window.Dokument.aterAnvand(v, post);
    });
    el.innerHTML = `<div class="lekttopp"><span class="lekttid">${start(s.tid) || ''}</span>${s.sal ? `<span class="lektsal">${s.sal}</span>` : ''}<span class="lektklass"></span></div><p class="lektnamn"></p>`;
    $('.lektklass', el).textContent = s.klass || '—';
    $('.lektnamn', el).textContent = kort(s.kurs) || 'Lektion';
    /* Har läraren skrivit en egen rubrik i timmen står den redan längre ner,
       ordagrant — då säger raden här samma sak en gång till. Provet har sitt
       eget besked och ska inte få en sidsträcka bredvid sig. */
    const inn = (rutan || bokatProv || !K.innehallFor) ? null : K.innehallFor(d.datum, s.klass, s.kurs, s.tid);
    if (inn) {
      const r = document.createElement('p');
      r.className = 'lektinnehall';
      r.textContent = innehallsrad(inn, s.kurs);
      el.appendChild(r);
    }

    if (docs.length || insp.length) {
      el.appendChild(dokremsa(docs, insp, post));
    } else if (bokatProv) {
      el.insertAdjacentHTML('beforeend', '<span class="lektbokat">Prov bokat · inte skrivet</span>');
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'lektplanera';
      b.textContent = 'Skriv provet';
      b.addEventListener('click', e => { e.stopPropagation(); planera(Object.assign({}, post, { slag: 'prov' }), 'Prov'); });
      el.appendChild(b);
    } else if (rutan) {
      /* Kalenderns egen rubrik, ordagrant — den säger vad timmen är, och det är
         ett bättre besked än «Tavla saknas» på en lektion som inte ska ha en
         tavla. Titeln är lärarens text och sätts som text, aldrig som HTML. */
      const t = document.createElement('span');
      t.className = 'lektbokat';
      t.textContent = rutan.titel;
      el.appendChild(t);
    } else {
      const nara = kvarTill(d.datum);
      if (nara >= 0 && nara <= 3) {
        el.setAttribute('data-bradskar', '');
        el.insertAdjacentHTML('beforeend', '<span class="lektsaknas">Tavla saknas</span>');
      } else if (vald !== 'alla' && d.datum >= K.idag()) {
        /* Filtrerar man ner till EN klass är frågan «vad har jag kvar?» — då ska
           varje tom lektion säga det själv. I hela schemat vore samma etikett
           tretton gånger bara brus, och där räcker den streckade kanten. */
        el.insertAdjacentHTML('beforeend', '<span class="lektsaknas" data-blek>Inget material än</span>');
      }
    }
    /* Ingen knapp: kortet är knappen. Bocken visar att den ligger i kön — och
       den måste finnas på alla kort, också de som redan har material, annars
       går den valda lektionen inte att skilja från den färdiga. */
    el.insertAdjacentHTML('beforeend', '<span class="lektvald"><span class="lvbock">✓</span><span class="lvtext">' + (arKlar(post) ? 'Klar' : 'Vald') + '</span></span>');
    return el;
  }

  function postkort(d, p) {
    const el = document.createElement('article');
    el.className = 'lekt';
    const prov = arProv(p);
    if (prov) el.setAttribute('data-prov', '');
    if (egetProv(p)) el.setAttribute('data-prov', '');
    /* Salen står i schemat, inte i kalenderposten — men läraren behöver den lika
       mycket för ett bokat prov som för en lektion. Vi läser den ur dagens
       schema: samma klass, samma klockslag om posten har ett. */
    const sal = (K.schemaFor(p.datum).find(s => s.klass === p.klass
      && (!p.tid || !s.tid || start(p.tid) === start(s.tid))) || {}).sal || '';
    el.innerHTML = `<div class="lekttopp"><span class="lekttid">${start(p.tid) || 'Hela dagen'}</span>${sal ? '<span class="lektsal"></span>' : ''}${p.klass ? '<span class="lektklass"></span>' : ''}</div><p class="lektnamn"></p>`;
    if (sal) $('.lektsal', el).textContent = sal;
    if (p.klass) $('.lektklass', el).textContent = p.klass;
    $('.lektnamn', el).textContent = p.titel;
    if (!prov) { el.insertAdjacentHTML('beforeend', `<span class="lektbokat">${egetProv(p) ? 'Nationellt prov · skrivs inte här' : 'Ur kalendern'}</span>`); return el; }
    const ord = provOrd(p);
    el.insertAdjacentHTML('beforeend', `<span class="lektbokat">${ord === 'Diagnos' ? 'Diagnos bokad · inte skriven' : 'Prov bokat · inte skrivet'}</span>`);
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'lektplanera';
    b.textContent = ord === 'Diagnos' ? 'Skriv diagnosen' : 'Skriv provet';
    /* Står det diagnos i kalendern är det en DIAGNOS som ska skrivas, inte ett
       prov. Knappen sa redan rätt sak men öppnade fel typ, och läraren fick
       börja med att välja om i steg 2. */
    b.addEventListener('click', () => planera({ datum: p.datum, tid: p.tid || '', kurs: p.kurs || (K.schemaFor(p.datum).find(s => s.klass === p.klass) || {}).kurs || '', klass: p.klass || '', titel: p.titel, slag: p.slag === 'diagnos' ? 'diagnos' : 'prov' }, ord === 'Diagnos' ? 'Diagnos' : 'Prov'));
    el.appendChild(b);
    return el;
  }

  /* ── Veckan ────────────────────────────────────────── */
  function ritaVeckan() {
    const bild = K.veckoBild(mandag);
    /* En missad bildruta får aldrig lämna veckan osynlig. */
    if (!byter) { grid.style.opacity = '1'; grid.style.transform = 'none'; }
    grid.innerHTML = '';
    let lektioner = 0, klara = 0;
    bild.dagar.forEach(d => {
      const kol = document.createElement('div');
      kol.className = 'skdag';
      if (d.datum === K.idag()) kol.setAttribute('data-idag', '');
      if (d.datum < K.idag()) kol.setAttribute('data-forbi', '');
      const namn = document.createElement('p');
      namn.className = 'skdagnamn';
      namn.textContent = d.namn;
      kol.appendChild(namn);
      if (d.lov) {
        const l = document.createElement('p');
        l.className = 'skdaglov';
        l.textContent = d.lov.namn;
        kol.appendChild(l);
        /* Lovet tar bort lektionerna — inte det som faktiskt står bokat i
           kalendern. En post som ligger på en lovdag är en krock läraren måste
           få se, inte något appen ska gömma. */
        posterFor(d).forEach(p => {
          const kort = postkort(d, p);
          kort.setAttribute('data-lovkrock', '');
          kort.insertAdjacentHTML('beforeend', `<span class="lektbokat" data-krock>Ligger i ${d.lov.namn.toLowerCase()}</span>`);
          kol.appendChild(kort);
        });
        grid.appendChild(kol);
        return;
      }
      const lekt = lektionerna(d);
      /* Extralektionen. En kalenderpost med BÅDE klass och klockslag som inte
         ligger i någon schemaruta är en lektion utanför det ordinarie schemat
         («BA26B: Överslagsräkning», en torsdag när schemat inte har BA26B).
         Den ritades förut som ett postkort, alltså «Ur kalendern» utan klick,
         och läraren kunde varken välja timmen eller göra material till den.
         Prov och NP har sina egna kort med sina egna knappar och rörs inte,
         och en post utan klass är inget klassen har (Kaggdag, ämneslagsmöte). */
      const extra = [];
      posterFor(d).forEach(p => {
        if (!p.klass || !p.tid || arProv(p) || egetProv(p)) return;
        if (lekt.some(s => iRutan(p, s))) return;
        /* Två poster i samma timme är fortfarande en enda lektion. */
        if (extra.some(s => s.klass === p.klass && start(s.tid) === start(p.tid))) return;
        extra.push({ tid: p.tid, kurs: kursFor(p.klass, d.datum), klass: p.klass, sal: '', extra: true });
      });
      /* Härifrån är den extra timmen en lektion som alla andra: den ska inte
         ritas en gång till som postkort, dokumenten som skrivits för den ska
         hamna PÅ kortet i stället för i en egen «lös» hög, och den räknas med. */
      const alla = lekt.concat(extra);
      const poster = posterFor(d).filter(p => !alla.some(s => iRutan(p, s)));
      /* Dokument som inte hänger på någon lektion den dagen — provet som lades
         på en annan dag. De får ett eget kort, ett per klass och klockslag. */
      const losa = {};
      dok().filter(v => v.datum === d.datum
        && (vald === 'alla' || (v.klass || '') === vald)
        && !alla.some(s => (v.klass || '') === (s.klass || '') && (!v.tid || !s.tid || start(v.tid) === start(s.tid))))
        .forEach(v => { const n = (v.klass || '') + '|' + start(v.tid); (losa[n] = losa[n] || []).push(v); });
      const rader = alla.map(s => ({ tid: start(s.tid), el: () => lektkort(d, s), s }))
        .concat(poster.map(p => ({ tid: start(p.tid) || '23:59', el: () => postkort(d, p) })))
        .concat(Object.values(losa).map(g => ({ tid: start(g[0].tid) || '23:59', el: () => dokkort(d, g) })))
        .sort((a, b) => a.tid.localeCompare(b.tid));
      alla.forEach(s => { lektioner++; if (dokFor(d.datum, s).length) klara++; });
      if (!rader.length) kol.insertAdjacentHTML('beforeend', '<p class="sktom">Ingen lektion</p>');
      rader.forEach(r => kol.appendChild(r.el()));
      grid.appendChild(kol);
    });
    $('#schemavecka').textContent = `Vecka ${bild.vecka}`;
    /* Kort spann: samma månad skrivs en gång — «17–21 augusti», inte
       «17 augusti – 21 augusti». Raden bär nu också klassfiltret. */
    const m1 = new Date(bild.mandag + 'T12:00:00').getMonth();
    const m2 = new Date(bild.fredag + 'T12:00:00').getMonth();
    $('#schemaspann').textContent = m1 === m2
      ? `${new Date(bild.mandag + 'T12:00:00').getDate()}–${K.ord(bild.fredag)}`
      : `${K.ord(bild.mandag)} – ${K.ord(bild.fredag)}`;
    /* Ingen sammanräkning: korten säger själva vad som finns och vad som saknas.
       Raden står kvar bara när veckan är tom — då finns det inget att läsa av. */
    const sum = $('#schemasum');
    sum.hidden = lektioner > 0;
    sum.textContent = lektioner ? '' : (bild.helLov ? 'Hela veckan är lov — ingenting att planera.' : 'Inga lektioner den här veckan.');
    ritaNuknapp(lektioner);
  }

  /* Knappen bredvid veckan har två jobb och ska bara ha ett åt gången: hem till
     den här veckan, eller — när man redan står i en tom lovvecka — fram till
     nästa vecka där det faktiskt finns lektioner. */
  function ritaNuknapp(lektioner) {
    const b = $('#schemanu');
    if (!b) return;
    const nu = K.mandagen(K.idag());
    const hemma = nu === mandag;
    const nasta = K.nastaSkolvecka ? K.nastaSkolvecka(K.idag()) : nu;
    if (!hemma) {
      b.hidden = false; b.disabled = false;
      b.dataset.gor = 'nu';
      b.textContent = 'Den här veckan';
      b.dataset.tip = 'Hoppa till veckan vi är i';
      return;
    }
    if (!lektioner && nasta && nasta !== mandag) {
      b.hidden = false; b.disabled = false;
      b.dataset.gor = 'nasta';
      b.textContent = 'Nästa skolvecka';
      b.dataset.tip = 'Första veckan med lektioner igen';
      return;
    }
    /* Står man redan i veckan har knappen inget att göra — då ska den vara borta,
       inte stå kvar avstängd och ta plats i raden. */
    b.hidden = true;
    b.disabled = true;
    b.dataset.gor = 'nu';
    b.textContent = 'Den här veckan';
    b.dataset.tip = 'Du står i den här veckan';
  }

  /* ── Förslaget: kalendern, schemat och boken lästa ihop ──────────
     Provet kommer inte ur ingenstans. Det ligger antingen redan bokat i
     kalendern, eller där kapitlet tar slut enligt boken och antalet lektioner
     klassen har i veckan. Appen räknar ut vilket och frågar en gång. */
  function kapitelKvar(kurs, klass) {
    const B = window.Bok;
    if (!B || !B.nasta) return null;
    /* Kursens eget register: «Boken står på 5.1 Derivatans definition» är fel bok
       för en klass som läser Matematik 4 — den boken har inget 5.1. */
    const A = (B.registerFor ? B.registerFor(kurs) : B.avsnitt) || B.avsnitt;
    const a = B.nasta(kurs, klass);
    const lista = A.filter(x => x.kap === a.kap);
    const i = Math.max(0, lista.indexOf(a));
    const sidor = lista.slice(i).reduce((n, x) => {
      const m = String(x.sid).match(/(\d+)\s*[–-]\s*(\d+)/);
      return n + (m ? +m[2] - +m[1] + 1 : 0);
    }, 0);
    return { avsnitt: a, kap: a.kap, kvar: lista.length - i, sidor };
  }
  function provdagen(veckor, kl) {
    let m = K.mandagen(flytta(K.mandagen(K.idag()), veckor * 7));
    if (K.nastaSkolvecka) m = K.nastaSkolvecka(m);
    const b = K.veckoBild(m);
    const dagar = b.dagar.filter(d => !d.lov && d.schema.some(s => s.klass === kl));
    const sista = dagar[dagar.length - 1];
    if (!sista) return null;
    const lek = sista.schema.filter(s => s.klass === kl).sort((a, b2) => start(a.tid).localeCompare(start(b2.tid))).pop();
    return { datum: sista.datum, lektion: lek, vecka: b.vecka };
  }
  function forslaget() {
    const kl = vald !== 'alla' ? vald : (klasser()[0] || {}).klass;
    if (!kl) return null;
    const idag = K.idag();
    const kurs = (K.schema.find(s => s.klass === kl) || {}).kurs || '';
    const bokat = K.poster.filter(p => p.klass === kl && arProv(p) && p.datum >= idag && !spegling(p))
      .sort((a, b) => a.datum.localeCompare(b.datum))[0];
    const senast = dok().filter(v => v.typ === 'Prov' && !v.losningsblad && v.klass === kl && v.datum && v.datum < idag)
      .sort((a, b) => b.datum.localeCompare(a.datum))[0];
    const bok = kapitelKvar(kurs, kl);
    const lektPerVecka = K.schema.filter(s => s.klass === kl).length || 2;
    /* Bakgrunden hålls i tre delar: provet bakåt, boken och själva slängen om
       nästa prov. Frågesvaret skriver om den första delen till ett citat och
       ska då inte få den i dubbel upplaga. */
    const senastSats = senast
      ? `Senaste provet med ${kl} var ${K.ord(senast.datum)} — ${versal(senast.moment)}.`
      : `Det finns inget skrivet prov bakåt för ${kl}.`;
    const bokSats = bok ? `Boken står på ${bok.avsnitt.nr} ${bok.avsnitt.titel}; ${bok.kap.replace(/^Kapitel /, 'kapitel ')} har ${bok.sidor} sidor kvar, ungefär ${(n => `${n} ${n === 1 ? 'lektion' : 'lektioner'}`)(Math.max(1, Math.round(bok.sidor / 4)))}.` : '';
    const ihop = (karna, extra) => Object.assign({
      klass: kl, senast, senastSats, bokSats, karna,
      text: [senastSats, bokSats, karna].filter(Boolean).join(' ')
    }, extra);
    if (bokat) {
      return ihop(`Provet ${K.ord(bokat.datum)} står redan i kalendern men är inte skrivet — <b>${bokat.titel}</b>${bokat.tid ? `, ${bokat.tid}` : ''}. Det ska täcka hela kapitlet, och tavlorna för ${kl} ligger som underlag.`, {
        knapp: 'Skriv provet nu',
        gor: () => {
          mandag = K.mandagen(bokat.datum);
          planera({ datum: bokat.datum, tid: bokat.tid || '', kurs, klass: kl, titel: bokat.titel, slag: 'prov' }, 'Prov');
        }
      });
    }
    if (!bok) return null;
    const veckor = Math.max(1, Math.ceil(Math.max(1, Math.round(bok.sidor / 4)) / lektPerVecka));
    const dag = provdagen(veckor, kl);
    if (!dag) return null;
    const nar = dagen(dag.datum).toLocaleDateString('sv-SE', { weekday: 'long', day: 'numeric', month: 'long' });
    return ihop(`Med ${lektPerVecka} ${lektPerVecka === 1 ? 'lektion' : 'lektioner'} i veckan är kapitlet slut om ${veckor} ${veckor === 1 ? 'vecka' : 'veckor'} — provet ligger rimligen <b>${nar}</b>${dag.lektion ? `, ${dag.lektion.tid}` : ''}, sista lektionen innan nästa kapitel börjar.`, {
      knapp: 'Skapa provet redan nu',
      gor: () => {
        mandag = K.mandagen(dag.datum);
        planera({ datum: dag.datum, tid: (dag.lektion || {}).tid || '', kurs, klass: kl, sal: (dag.lektion || {}).sal || '', slag: 'prov' }, 'Prov');
      }
    });
  }
  function ritaForslag() {
    const ruta = $('#schemaforslag');
    if (!ruta) return;
    const f = avvisat ? null : forslaget();
    if (!f) { ruta.hidden = true; ruta.innerHTML = ''; return; }
    ruta.hidden = false;
    ruta.innerHTML = `<p class="fsetikett">Nästa prov · ${f.klass}</p><p class="fstext">${f.text}</p>
      <div class="fsknappar"><button class="primar" type="button" data-gor></button><button class="lank" type="button" data-nej>Inte nu</button></div>`;
    $('[data-gor]', ruta).textContent = f.knapp;
    $('[data-gor]', ruta).addEventListener('click', f.gor);
    $('[data-nej]', ruta).addEventListener('click', () => { avvisat = true; ritaForslag(); });
  }

  /* ── Frågan: schemat svarar, inte bara högen ────────
     Fråga AI ligger över båda flikarna. Handlar frågan om tid — prov, nästa
     vecka, vad som hunnits — läses schemat och boken med i svaret. */
  function fragan(q) {
    if (!/prov|nästa|nasta|när|nar|vecka|planera|hinner|kapitel|klar/i.test(q)) return null;
    const f = forslaget();
    if (!f) return null;
    const kl = f.klass;
    const lank = v => `[[dok:${dok().indexOf(v)}|${namnPa(v)}]]`;
    const bok = kapitelKvar((K.schema.find(s => s.klass === kl) || {}).kurs || '', kl);
    /* Provet bakåt skrivs som citat i stället för som mening — samma faktum,
       en gång, men klickbart. */
    const bakat = f.senast ? `Sist skrev ni ${lank(f.senast)} ${K.ord(f.senast.datum)}.` : f.senastSats;
    return {
      omfang: `${dok().length} sparade dokument, schemat och boken`,
      antal: Math.max(1, dok().length + K.schema.length),
      svar: `${[bakat, f.bokSats, f.karna.replace(/<\/?b>/g, '”')].filter(Boolean).join(' ')}${bok ? ` Boken är inläst, så innehållet är redan avgränsat: ${bok.avsnitt.nr}–kapitlets slut.` : ''}`,
      plan: [
        { namn: 'Läser kalendern och schemat', detalj: (() => { const n = K.schema.filter(s => s.klass === kl).length; return `${n} ${n === 1 ? 'lektion' : 'lektioner'} i veckan`; })() },
        { namn: 'Väger in var boken står', detalj: bok ? `${bok.sidor} sidor kvar` : 'boken saknas' },
        { namn: 'Skriver svar med källor', detalj: '' }
      ],
      kallor: [],
      atgarder: [{ namn: f.knapp, stark: true, gor: () => f.gor() }]
    };
  }

  /* Veckobytet ska kännas som att bläddra — samma glid som planeringsveckan:
     veckan glider ut åt det håll man lämnar och nästa kommer in från andra sidan. */
  let byter = false;
  /* Klick under bytet kastades förr bort — vill man tre veckor framåt fick man
     två. Nu köas de och spelas upp när glidet är klart. */
  let koat = 0;
  function byt(steg, tillDatum) {
    if (!steg && !tillDatum) return;
    styrd = true;                 /* läraren har valt vecka — rör den inte */
    if (byter) { if (!tillDatum) koat += steg; return; }
    byter = true;
    const ut = steg > 0 ? -1 : 1;
    const huvud = $('#schemahuvudtext');
    grid.style.transition = 'opacity 170ms var(--ease),transform 170ms var(--ease)';
    grid.style.opacity = '0';
    grid.style.transform = `translateX(${ut * 28}px)`;
    if (huvud) { huvud.style.transition = 'opacity 170ms var(--ease)'; huvud.style.opacity = '0'; }
    setTimeout(() => {
      mandag = tillDatum || flytta(mandag, steg * 7);
      rita();
      grid.style.transition = 'none';
      grid.style.opacity = '0';
      grid.style.transform = `translateX(${-ut * 28}px)`;
      /* setTimeout, inte rAF: veckan måste glida in även när fliken ligger i
         bakgrunden — annars står rutnätet kvar genomskinligt och låser pilarna. */
      setTimeout(() => {
        grid.style.transition = 'opacity 300ms var(--ease),transform 300ms var(--ease)';
        grid.style.opacity = '1';
        grid.style.transform = 'none';
        if (huvud) huvud.style.opacity = '1';
      }, 20);
      setTimeout(() => {
        byter = false;
        if (koat) { const n = koat; koat = 0; byt(n); }
      }, 330);
    }, 175);
  }
  $('#schemafram').addEventListener('click', () => byt(1));
  $('#schemabak').addEventListener('click', () => byt(-1));
  /* Draget slutade förr vid veckans kant: pappret kunde bara läggas på en
     lektion som råkade vara uppritad. Nu bläddrar pilen medan chipet hålls över
     den — samma glid som ett klick, en vecka i taget.
     Kön (koat) används INTE här. Den samlar övertramp, och ett chip som vilar på
     pilen i två sekunder skulle hoppa fyra veckor extra när man släpper. Låset
     `byter` är hela throttlingen: nästa steg tas först när glidet är klart. */
  function pilDrag(knapp, steg) {
    if (!knapp) return;
    knapp.addEventListener('dragover', e => {
      if (!dragDok) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'copy';
      if (byter) return;
      byt(steg);
    });
    /* Släpper man PÅ pilen har inget hänt — pappret får inte försvinna tyst. */
    knapp.addEventListener('drop', e => {
      if (!dragDok) return;
      e.preventDefault();
      window.toast && window.toast('Pilen bläddrar bara veckan — släpp pappret på en lektion');
    });
  }
  pilDrag($('#schemafram'), 1);
  pilDrag($('#schemabak'), -1);
  /* «Idag» pekar ut dagen, inte bara veckan: ringen pulserar två gånger och är
     sedan borta igen — ett svar på frågan «var är jag?», inte ett nytt tillstånd. */
  function pulseraIdag() {
    setTimeout(() => {
      const kol = grid && grid.querySelector('.skdag[data-idag]');
      if (!kol) return;
      kol.removeAttribute('data-idagpuls');
      void kol.offsetWidth;
      kol.setAttribute('data-idagpuls', '');
      setTimeout(() => kol.removeAttribute('data-idagpuls'), 3100);
    }, 40);
  }
  $('#schemanu').addEventListener('click', () => {
    const b = $('#schemanu');
    if (b.disabled) return;
    const mal = b.dataset.gor === 'nasta' && K.nastaSkolvecka
      ? K.nastaSkolvecka(K.idag())
      : K.mandagen(K.idag());
    if (mal === mandag) { pulseraIdag(); return; }
    byt(mal > mandag ? 1 : -1, mal);
    if (b.dataset.gor !== 'nasta') setTimeout(pulseraIdag, 520);
  });
  /* Hoppar man till en annan vecka ur ett förslag ska den också glida in. */
  function till(datum) {
    const mal = K.mandagen(datum);
    if (mal === mandag) { rita(); return; }
    byt(mal > mandag ? 1 : -1, mal);
  }

  /* ── Kalendersynken ────────────────────────────────
     En rad, inte en förklaring. Att schemat kommer från Google och att pappret
     stannar i appen behöver sägas EN gång, inte varje gång veckan ritas: här står
     bara källan, tiden och vägen att synka om. Resten ligger i knappens titel. */
  let synkad = new Date();
  /* VILKET Google-konto veckan kom ur. En synk mot fel konto ser annars ut
     precis som en lyckad synk — appen läste en gång tillbaka sitt eget
     utskrivna exempelschema ur ett gammalt konto och sa bara «Synkad 19:07».
     Kontot står i knappens titel, inte i raden: det är svaret på en fråga man
     ställer när något ser fel ut, inte något man behöver läsa varje vecka. */
  let konto = '';
  /* Efter API.redo: sonderingen av servern är async, och frågan är meningslös
     innan den svarat (api.js). */
  if (window.API && window.API.redo) {
    /* SWR: kontot byts en gång om året och står i en knapptitel. Cachen gör att
       titeln är rätt från första bildrutan i stället för efter ett nätanrop. */
    const taKonto = s => { if (s && s.konto) { konto = s.konto; ritaSynk(); } };
    window.API.redo
      .then(() => window.API.pa
        ? window.API.jsonSWR('/api/calendar/status', { vidCache: taKonto, vidFarskt: taKonto })
        : null)
      .catch(() => { /* kontot är en upplysning, inte ett krav */ });
  }
  function ritaSynk() {
    const r = $('#synkrad');
    if (!r || r.dataset.lage) return;
    const tid = synkad.toLocaleTimeString('sv-SE', { hour: '2-digit', minute: '2-digit' });
    const stod = 'Läser om schemat, salarna och loven på nytt. Tavlor och prov du godkänner skrivs tillbaka som poster — PDF:erna stannar i appen.'
      + (konto ? ` Läser kalendern för ${konto}.` : '');
    r.innerHTML = `<button class="synkknapp" type="button" data-synk data-tip="Synka med Google Kalender" data-tipstod="${stod}"><span class="synkprick"></span><span class="synktext">Synkad ${tid}</span></button>`;
    $('[data-synk]', r).addEventListener('click', () => {
      r.dataset.lage = 'synkar';
      $('.synktext', r).textContent = 'Synkar …';
      window.Tips && window.Tips.gom();
      /* Raden ritas om av rita() medan synken pågår — ritaSynk går ur på
         data-lage, så «Synkar …» står kvar tills svaret kommit. */
      const klar = besked => {
        r.removeAttribute('data-lage');
        synkad = new Date();
        ritaSynk();
        window.toast && window.toast(besked);
      };
      /* Med server läser synken om schemat, salarna och loven ur Google
         Kalender på riktigt. Utan server är den prototypens uppvisning, i
         samma takt som förut. */
      if (K.synka) {
        K.synka().then(sv => {
          if (sv && sv.konto) konto = sv.konto;
          klar(
            sv && sv.fel ? sv.fel
              : sv && sv.prototyp
                ? 'Kalendern är synkad — schemat, salarna och loven oförändrade'
                /* VAD som lästes och UR VEMS kalender. Ett blankt «synkad»
                   såg likadant ut när schemat kom ur fel konto. Posterna
                   reglerna inte kunde avgöra läste Claude — det ska stå,
                   inte döljas bakom ett allmänt «synkad». */
                : `Kalendern är synkad${sv && sv.konto ? ` ur ${sv.konto}` : ''} — ${
                    sv && sv.lektioner
                      ? `${sv.lektioner} ${sv.lektioner === 1 ? 'lektion' : 'lektioner'} i veckoschemat`
                      : 'inga lektioner i veckoschemat'}${
                    sv && sv.bedomda ? ` · ${sv.bedomda} ${sv.bedomda === 1 ? 'post' : 'poster'} tolkade av Claude` : ''}${
                    /* Notiser andra program lagt i kalendern hoppades över —
                       det ska stå, annars ser det ut som att de tappats bort. */
                    sv && sv.notiser ? ` · ${sv.notiser} ${sv.notiser === 1 ? 'notis' : 'notiser'} överhoppade` : ''}`);
        });
      } else {
        setTimeout(() => klar('Kalendern är synkad — schemat, salarna och loven oförändrade'), 1100);
      }
    });
  }

  /* Bara markeringarna, utan att bygga om veckan. */
  function friskaVal() {
    if (!window.PlanKo) return;
    $$('.lekt[data-post]', grid).forEach(el => {
      let post; try { post = JSON.parse(el.dataset.post); } catch (e) { return; }
      el.toggleAttribute('data-vald', !!window.PlanKo.har(post));
      el.toggleAttribute('data-koklar', arKlar(post));
      el.toggleAttribute('data-nu', !!window.PlanKo.arNu(post));
      const t = el.querySelector('.lvtext');
      if (t) t.textContent = arKlar(post) ? 'Klar' : 'Vald';
    });
  }
  function rita(bevaraVeckan) {
    ritaSynk();
    ritaKlassrad();
    window.Profil && window.Profil.rita();
    /* Profilen ritas alltid om, men visas bara när man bett om den. */
    const pr = $('#klassprofil');
    if (pr && !(visaProfil && vald !== 'alla')) pr.hidden = true;
    ritaOmprovband();
    bevaraVeckan ? friskaVal() : ritaVeckan();
    ritaForslag();
    /* Terminen läser samma material och samma klassfilter — den ska aldrig ligga
       kvar och visa en vecka som inte finns längre. */
    window.Termin && window.Termin.rita();
    /* Och veckobriefen: den sammanfattar den vecka schemat står i, filtrerad som
       remsan står — alltså måste den ritas om av samma anrop. */
    window.Brief && window.Brief.rita();
  }
  rita();
  /* Hyllan kommer ur servern och är sällan inne när veckan ritas första gången.
     Innehållsraden på korten läser bokens register för att kunna säga
     «5.4 Extrempunkter» i stället för «s. 210–215» — utan omritning stod
     veckan kvar med bara sidnummer tills något annat råkade rita om den. */
  document.addEventListener('bok-redo', () => rita());
  /* ritaVal: bara markeringarna. Planeringskön ropar på den när kön ändras eller
     släpps — utan den satt «Vald» kvar på korten efter «Börja om». */
  /* Terminsvyn har EN meny: kursraden. Den namnger klass OCH kurs, alltså allt
     klassremsan sa och mer — därför sätter den också veckans filter, så att man
     inte behöver välja klass på två ställen. */
  function filtrera(k) {
    if (vald === k) return;
    vald = k;
    avvisat = false;
    if (k === 'alla') visaProfil = false;
    rita();
  }
  return { rita, ritaVal: friskaVal, fragan, klass: () => vald, veckan: () => mandag, filtrera, till, valjOmprov, slappOmprov, speglaFinns };
})();
