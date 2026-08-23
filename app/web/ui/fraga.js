/* ══════════ DELAD FRÅGEKOMPONENT ══════════
   Samma flöde överallt där appen frågar språkmodellen: materialet som läses,
   förfrågan som skickas, väntan hos Claude och svaret som kommer på en gång.
   Språkmodellsarbetet ligger hos Claude Code — därför finns ingen modell att
   ladda i minnet och ingenting att strömma. Väntan bärs av en klocka som räknar
   UPP, spannet den brukar landa i och appens egna steg. Ingen falsk procent.
   Anropas som window.Fraga.kor(vardElement, { … }). */
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const MODELL = { namn: 'Claude Code · Anthropic', mb: 0 };
  /* Spegeln kortar väntan till några sekunder men låter klockan gå i appens takt,
     så texten «brukar ta 1–2 min» stämmer mot det som visas. Med ett RIKTIGT
     jobb (o.jobb) går klockan i verklig tid — då finns inget att komprimera. */
  const TAKT = 22;
  let varm = false;

  const fas = (namn, extra = '') =>
    `<div class="ffas" data-lage="vantar"><span class="fikon"></span><span class="fnamn">${namn}</span><span class="fdetalj"></span>${extra}</div>`;

  /* Serverns loggrader är skrivna för EN rad, inte för ett stycke. De kortas
     till det som ryms — och kapningen får aldrig ge «… …»: raderna slutar
     nästan alltid på ett eget tankstreck («Skriver uppgift 4 av 12 …»). */
  const kortRad = (s, tak = 60) => {
    const t = String(s || '').replace(/\s+/g, ' ').trim();
    return t.length <= tak ? t
      : t.slice(0, tak - 1).replace(/[\s…]+$/, '') + '…';
  };

  /* Svarstexten målas likadant i båda lägena: [[tid|text]] blir källmarkör,
     *ord* blir markerat. */
  function malaText(str, node) {
    String(str || '').split(/(\[\[[^\]]+\]\]|\*[^*]+\*)/).forEach(del => {
      if (!del) return;
      const s = document.createElement('span');
      if (del.startsWith('[[') && del.endsWith(']]')) {
        const [tid, t] = del.slice(2, -2).split('|');
        s.className = 'kallmark';
        s.dataset.t = tid;
        s.tabIndex = 0;
        s.setAttribute('role', 'button');
        s.setAttribute('aria-label', 'Visa var i transkriptet');
        s.textContent = t || tid;
      } else if (del.length > 2 && del.startsWith('*') && del.endsWith('*')) {
        s.className = 'markt';
        s.textContent = del.slice(1, -1);
      } else {
        s.textContent = del;
      }
      node.appendChild(s);
    });
    node.setAttribute('data-in', '');
  }

  /* ── Enkelt läge ───────────────────────────────────
     Faslistan, klockan och «Claude svarade efter 1:10» hörde till en modell som
     kördes här på datorn, där varje steg gick att mäta. Claude Code tänker,
     skriver och svarar i ett svep — då är det enda sanna under väntan att det
     pågår och att det går att avbryta. En rad, sedan svaret. */
  function korEnkel(host, o) {
    const el = document.createElement('div');
    el.className = 'fsvar';
    el.dataset.lage = 'kor';
    el.dataset.enkel = '';
    el.innerHTML = '<div class="fjobb"><span class="fjobbprickar"><i></i><i></i><i></i></span><span class="fjobbtext"></span><span class="fjobbklocka"></span><button class="lank fstopp" type="button">Avbryt</button></div><p class="ftext"></p><div class="fatgard" hidden></div>';
    $('.fjobbtext', el).textContent = o.jobbtext || `Skriver om ${o.omfang || 'dokumentet'} …`;
    if (o.lagg) host.appendChild(el); else { host.innerHTML = ''; host.appendChild(el); }
    host.hidden = false;
    let stoppad = false;
    const jobb = $('.fjobb', el);
    /* En uppräknande klocka — inte fasmätning (det vore osant, se ovan), bara
       hur länge det pågått. En omskrivning tar 1–4 min; utan siffran går det
       inte att skilja «det jobbar» från «det hänger». */
    const start = Date.now();
    const klocka = setInterval(() => {
      const s = Math.floor((Date.now() - start) / 1000);
      const k = $('.fjobbklocka', el);
      if (k) k.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
    }, 1000);
    /* Samma `o.jobb` som i det stora läget: finns det väntar raden på ett
       riktigt anrop i stället för på en klocka, och Avbryt avbryter det. */
    const styrning = o.jobb ? new AbortController() : null;
    let svaret = null;
    const klarna = () => {
      if (stoppad) return;
      clearInterval(klocka);
      jobb.setAttribute('data-ut', '');
      setTimeout(() => jobb.remove(), 220);
      el.dataset.lage = 'klar';
      malaText(typeof o.svar === 'function' ? o.svar(svaret) : o.svar, $('.ftext', el));
      if (o.atgarder && o.atgarder.length) {
        const a = $('.fatgard', el);
        a.hidden = false;
        o.atgarder.forEach(x => {
          const b = document.createElement('button');
          b.className = x.stark ? 'primar' : 'ghost';
          b.textContent = x.namn;
          b.addEventListener('click', () => x.gor(el));
          a.appendChild(b);
        });
      }
      if (o.efterKlar) o.efterKlar(el, svaret);
    };
    /* Ett fel blir ett besked i samma ruta, med en väg tillbaka — inte en
       ändring som ser gjord ut men aldrig skedde. */
    const felade = e => {
      if (stoppad || (e && e.name === 'AbortError')) return;
      clearInterval(klocka);
      jobb.remove();
      el.dataset.lage = 'stoppad';
      malaText((e && e.message) || 'Det gick inte att skriva om.', $('.ftext', el));
      const a = $('.fatgard', el);
      a.hidden = false;
      a.innerHTML = '';
      const b = document.createElement('button');
      b.className = 'ghost';
      b.textContent = 'Försök igen';
      b.addEventListener('click', () => (o.onIgen ? o.onIgen() : korEnkel(host, o)));
      a.appendChild(b);
      if (o.efterFel) o.efterFel(e);
    };
    let t = null;
    if (o.jobb) {
      Promise.resolve()
        .then(() => o.jobb({
          signal: styrning.signal,
          /* Samma rader som i det smala läget (se `serverrad` i kor): under
             en iteration av provet är det de här som säger «Uppdaterar
             uppgift 3 …» i stället för en oföränderlig jobbtext. */
          log: m => { $('.fjobbtext', el).textContent = kortRad(m, 72); },
        }))
        .then(r => { svaret = r; klarna(); }, felade);
    } else {
      t = setTimeout(klarna, o.vantan || 1400);
    }
    const stoppa = etikett => {
      stoppad = true;
      if (styrning) { try { styrning.abort(); } catch (e) { /* redan klar */ } }
      clearTimeout(t);
      clearInterval(klocka);
      /* Avbrytandet är varken klart eller fel, och den som håller ett lås
         medan varvet går måste ändå få veta att det är över — annars satt
         granskningens formulär låst tills sidan laddades om. */
      if (o.efterStopp) o.efterStopp();
      jobb.remove();
      el.dataset.lage = 'stoppad';
      const a = $('.fatgard', el);
      a.hidden = false;
      a.innerHTML = '';
      const b = document.createElement('button');
      b.className = 'ghost';
      b.textContent = etikett || 'Försök igen';
      b.addEventListener('click', () => (o.onIgen ? o.onIgen() : korEnkel(host, o)));
      a.appendChild(b);
    };
    $('.fstopp', el).addEventListener('click', () => stoppa());
    return { el, stoppa };
  }

  function kor(host, o) {
    if (o && o.enkel) return korEnkel(host, o);
    const timers = [];
    const senare = (ms, fn) => timers.push(setTimeout(fn, ms));
    const el = document.createElement('div');
    el.className = 'fsvar';
    el.dataset.lage = 'kor';
    el.innerHTML = `<div class="fhuvud"><button class="lank fstopp" type="button">Avbryt</button></div>
      ${o.fraga ? '<p class="ffraga"></p>' : ''}
      <div class="fsmal"><div class="fsmalinre"><div class="fsmalrad"><span class="fsmaltext"></span><span class="fsmalbrukar"></span><span class="fsmalklocka"></span></div><div class="fsmalspar"><i></i></div></div></div>
      <div class="fvanta" hidden><div class="vtopp"><span class="vklocka">0:00</span><span class="vbrukar">brukar ta 1–2 min · Claude svarar allt på en gång</span></div><div class="vpuls"></div></div>
      <div class="ffaser">${fas('Läser igenom ' + (o.omfang || 'materialet'), '<span class="fsok"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></span>')}</div>
      <button class="ftankte" type="button" aria-expanded="true" hidden></button>
      <p class="ftext"></p>
      <div class="fkallor" hidden><p class="fkalletikett">Källor i transkripten</p></div>
      <div class="fatgard" hidden></div>`;
    if (o.fraga) $('.ffraga', el).textContent = o.fraga;
    if (o.lagg) host.appendChild(el); else { host.innerHTML = ''; host.appendChild(el); }
    host.hidden = false;

    /* ── Smalt läge (chatten) ───────────────────────────────────────
       Faslistan är ett eget dokument — i en chattbubbla är den högre än rutan
       och sköljer bort svaret när den fälls ihop. Här blir samma förlopp en rad:
       vad som pågår, hur långt det gått, hur länge det tagit. Den viker ut mjukt,
       hålls i mitten av vyn medan den går och lämnar plats åt svaret när den viker in. */
    const smalt = !!o.smal;
    const smalruta = $('.fsmal', el), smalfyll = $('.fsmalspar i', el);
    if (smalt) {
      el.dataset.smal = '';
      $('.fsmaltext', el).textContent = 'Förbereder …';
      /* «brukar ta 7–10 min» — MÄTT på lärarens egna körningar av provet, inte
         gissat, och därför satt av anroparen och inte här (plan.js). En rad som
         inte vet sitt spann skriver inget: ett påhittat spann är värre än
         inget, för det är det man går och tittar på. */
      if (o.brukar) $('.fsmalbrukar', el).textContent = o.brukar;
      $('.fsmalklocka', el).before($('.fstopp', el));
      /* setTimeout, inte rAF: raden ska vika ut även när fliken är i bakgrunden. */
      setTimeout(() => {
        smalruta.setAttribute('data-in', '');
        hallKvar(el, 'mitt');
        /* Raden är noll pixlar hög när den mounts — mäts den då hamnar själva spåret
           under kanten. Därför en andra mätning när utvikningen är klar. */
        smalruta.addEventListener('transitionend', function ut(ev) {
          if (ev.propertyName !== 'grid-template-rows') return;
          smalruta.removeEventListener('transitionend', ut);
          if (smalruta.hasAttribute('data-in')) hallKvar(el, 'botten');
        });
        setTimeout(() => { if (smalruta.isConnected && smalruta.hasAttribute('data-in')) hallKvar(el, 'botten'); }, 460);
      }, 16);
    } else {
      smalruta.remove();
    }
    /* ── MÄTAREN ─────────────────────────────────────────────────────
       Tre regler, och alla tre kommer ur vad raden gjorde fel:
       1. Den går ALDRIG bakåt. Stegen når hit i den ordning servern råkar
          skicka dem, och en mätare som hoppar tillbaka läses som ett fel.
       2. Den kryper mellan stegen. Ett steg kan vara minuter långt (en
          uppgift med fyra deluppgifter), och en mätare som står helt stilla
          är inte att skilja från en hängd app.
       3. Krypandet når ALDRIG nästa stegs golv. Det går asymptotiskt mot
          takets kant, så procenten är alltid ett löfte appen redan hållit —
          inte ett den hoppas hålla. `tak` är därför inte monotont: ett lägre
          tak fryser krypandet i stället för att dra siffran bakåt. */
    let golv = 0, tak = 0, nu = 0, kryp = null;
    const rita = () => { smalfyll.style.width = Math.max(4, Math.min(100, nu)).toFixed(1) + '%'; };
    const matare = (g, t) => {
      golv = Math.max(golv, g * 100);
      tak = Math.max(t * 100, nu);
      nu = Math.max(nu, golv);
      rita();
      if (kryp) return;
      kryp = setInterval(() => { nu += (tak - nu) * 0.05; rita(); }, 400);
      timers.push(kryp);
    };
    /* Har servern sagt något är DET raden. Faslistans egna namn får inte skriva
       över den — molnraden heter «Claude skriver provet» hela vägen, och det
       var precis den oföränderliga texten läraren satt och tittade på. */
    let serverSagt = false;
    const smal = (namn, g, t) => {
      if (!smalt || !smalruta.isConnected) return;
      if (namn) $('.fsmaltext', el).textContent = kortRad(namn);
      matare(g, t);
    };
    /* ── SERVERNS RAD, DÄR LÄRAREN TITTAR ────────────────────────────
       Loggraderna nådde klienten hela tiden — men skrevs bara i .fdetalj på
       faslistan, som är HOPFÄLLD medan jobbet går. I praktiken ingenstans.
       Här står de i den smala raden, och SIFFRAN I DEM flyttar mätaren:
       samma mening bär både texten och procenten, så de två kan inte säga emot
       varandra. Varför texten och inte ett eget pct-fält: se kommentaren vid
       log_cb i app/web/routes_exam.py. */
    const NUMMER = /uppgift (\d+)(?: av (\d+))?/i;
    function stegAv(m) {
      const d = NUMMER.exec(m);
      /* Med «n av N» får uppgiften sin egen skiva av bandet. Utan siffror
         räcker det till halva skivan — resten sparas åt det som faktiskt
         kommer, för då VET vi inte hur långt det gått. */
      const skiva = (a, b) => {
        if (!d || !d[2]) return [a, a + (b - a) * 0.5];
        const N = Math.max(1, +d[2]), n = Math.max(1, Math.min(N, +d[1]));
        return [a + (b - a) * (n - 1) / N, a + (b - a) * n / N];
      };
      /* Sättningen och trycket ligger sist: de raderna kommer ur godkännandet
         (routes_exam approve), som kroker sig på samma rad när den används. */
      if (/latex|\bpdf\b|\bA4\b|kompilerar|renderar|^sparar/i.test(m)) return [0.90, 1];
      if (/^(justerar|kontrollerar|räknar igenom|modellen svarade)/i.test(m)) return skiva(0.75, 0.90);
      if (/^(skriver|uppdaterar)/i.test(m)) return skiva(0.25, 0.75);
      return null;        // bokens sidor, faktapasset: text, men ingen procent
    }
    function serverrad(m) {
      const t = String(m || '').trim();
      if (!t || !smalt || !smalruta.isConnected) return;
      serverSagt = true;
      const s = stegAv(t);
      if (s) smal(t, s[0], s[1]);
      else $('.fsmaltext', el).textContent = kortRad(t);
    }
    const smalUt = () => {
      if (!smalt || !smalruta.isConnected) return;
      clearInterval(kryp);
      smalfyll.style.width = '100%';
      setTimeout(() => {
        smalruta.removeAttribute('data-in');
        setTimeout(() => smalruta.remove(), 420);
      }, 180);
    };

    const faser = $('.ffaser', el), text = $('.ftext', el);
    const kall = !varm;
    const t0 = Date.now();
    let stoppad = false;
    /* ── Riktigt jobb ────────────────────────────────────────────────
       Utan `o.jobb` spelas förloppet upp i prototypens takt: varje rad får sin
       tid, molnraden 1,5 sekunder, och svaret är det som stod i `o.svar`. Med
       ett jobb är raderna före anropet fortfarande appens egna — den läser
       verkligen igenom materialet här — men MOLNRADEN står kvar tills svaret
       kommit, klockan går i verklig tid, och Avbryt avbryter anropet på
       riktigt. Samma rader, samma ordning, samma texter. */
    const styrning = o.jobb ? new AbortController() : null;
    let svaret = null, jobbfel = null;

    const stoppa = (etikett) => {
      stoppad = true;
      if (styrning) { try { styrning.abort(); } catch (e) { /* redan klar */ } }
      timers.forEach(clearTimeout);
      /* Samma kontrakt som i korEnkel ovan: den som håller ett lås medan varvet
         går måste få veta att det är över, oavsett vilket läge raden kördes i.
         Här saknades anropet, och det är DET HÄR läget skrivvägen använder
         (smal:true) — läraren tryckte Avbryt, «Skriv» förblev disabled och
         bladkön pekade kvar på förra mottagaren tills sidan laddades om. */
      if (o.efterStopp) o.efterStopp();
      smalUt();
      el.dataset.lage = 'stoppad';
      $('.fstopp', el).hidden = true;
      $$('.ffas[data-lage="kor"]', el).forEach(f => { f.dataset.lage = 'vantar'; });
      const a = $('.fatgard', el);
      a.hidden = false;
      a.innerHTML = '';
      const b = document.createElement('button');
      b.className = 'ghost';
      b.textContent = etikett || 'Fråga igen';
      b.addEventListener('click', () => (o.onIgen ? o.onIgen() : kor(host, o)));
      a.appendChild(b);
    };
    $('.fstopp', el).addEventListener('click', () => stoppa());

    /* fas 1 — materialet läses här på datorn innan något skickas */
    const start2 = () => {
      const f = $$('.ffas', el)[0];
      f.dataset.lage = 'kor';
      const n = o.antal || 43;
      let i = 0;
      /* Appens egna steg får bandets första sjundedel: läsningen sker här på
         datorn och är över på ett par sekunder. Skrivfasen är den långa. */
      smal('Läser igenom ' + (o.omfang || 'materialet'), 0.04, 0.06);
      const steg = setInterval(() => {
        i = Math.min(n, i + Math.max(1, Math.ceil(n / 9)));
        $('.fdetalj', f).textContent = `${i} av ${n}`;
        if (!serverSagt) smal('Läser igenom ' + (o.omfang || 'materialet'),
                              0.04 + (i / n) * 0.10, 0.14);
        if (i >= n) {
          clearInterval(steg);
          f.dataset.lage = 'klar';
          const s = $('.fsok', f);
          if (s) s.remove();
          plan();
        }
      }, 110);
    };
    senare(60, start2);

    /* fas 2 — appens egna steg runt anropet. Det som händer hos Claude går inte
       att mäta, så den raden bär klockan i stället för en mätare. */
    const paus = ms => new Promise(los => senare(ms, los));

    async function plan() {
      const egna = o.plan && o.plan.length ? o.plan : [
        { namn: 'Väljer ut relevanta avsnitt', detalj: '4 avsnitt' },
        { namn: 'Läser avsnitten i sin helhet', detalj: '00:42–28:05' }
      ];
      const rader = [
        ...egna,
        { namn: 'Skickar förfrågan', detalj: 'texten lämnar datorn', kort: true },
        { namn: o.molnsteg || 'Claude skriver svaret', detalj: 'inget att visa förrän det är klart', vanta: true },
        ...(o.reparationer || []).map((r, i) => ({
          namn: r.namn || r, detalj: `rond ${i + 1} av ${(o.reparationer || []).length}`, vanta: true, rond: true
        })),
        { namn: o.kontrollsteg || 'Kontrollerar svaret', detalj: '', kort: true }
      ];
      rader.forEach(r => faser.insertAdjacentHTML('beforeend', fas(r.namn) ));
      const noder = $$('.ffas', el).slice(-rader.length);
      noder.forEach((n, i) => { if (rader[i].rond) n.setAttribute('data-rond', ''); });

      /* Jobbet startas HÄR, samtidigt som «Skickar förfrågan» tänds — inte när
         molnraden nås. Annars hade appens egna rader varit ren väntetid. */
      let jobbet = null;
      if (o.jobb) {
        jobbet = Promise.resolve()
          .then(() => o.jobb({
            signal: styrning.signal,
            /* Serverns loggrader står som detalj på molnraden — OCH i den
               smala raden, som är den läraren faktiskt ser (serverrad ovan).
               Faslistan är hopfälld medan jobbet går. */
            log: m => { const n = noder.find((x, i) => rader[i].vanta && x.dataset.lage === 'kor');
                        if (n) $('.fdetalj', n).textContent = kortRad(m, 72);
                        serverrad(m); },
          }))
          .then(r => { svaret = r; }, e => { jobbfel = e; });
      }

      /* Bandet delas efter vad som TAR TID, inte efter hur många rader det
         råkar bli: appens egna steg 14→25 %, molnets skrivning 25→75 % (den
         som tar sju minuter, och den enda där servern kan säga hur långt det
         gått), rundorna och domarna 75→90, appens avslutning 90→100. */
      const molnet = rader.findIndex(r => r.vanta);
      const efter = Math.max(1, rader.length - molnet - 1);
      for (let i = 0; i < rader.length; i++) {
        if (stoppad) return;
        const r = rader[i];
        noder[i].dataset.lage = 'kor';
        if (i < molnet) smal(serverSagt ? null : r.namn,
                             0.14 + 0.11 * (i / molnet), 0.14 + 0.11 * ((i + 1) / molnet));
        else if (i === molnet) smal(serverSagt ? null : r.namn, 0.25, 0.30);
        else smal(r.namn, 0.90 + 0.10 * ((i - molnet - 1) / efter),
                  0.90 + 0.10 * ((i - molnet) / efter));
        vantelage(!!r.vanta);
        if (r.vanta && jobbet) await jobbet;
        else await paus(r.vanta ? 1500 : r.kort ? 260 : 340);
        if (stoppad) return;
        /* Gick jobbet fel är det ett besked, inte en tavla: raderna som ligger
           efter spelas aldrig upp. */
        if (jobbfel) { vantelage(false); felade(jobbfel); return; }
        noder[i].dataset.lage = 'klar';
        if (!(r.vanta && jobbet)) $('.fdetalj', noder[i]).textContent = r.detalj || '';
        else if (!$('.fdetalj', noder[i]).textContent) $('.fdetalj', noder[i]).textContent = r.detalj || '';
      }
      vantelage(false);
      visaSvar();
    }

    /* Ett fel ur jobbet blir ett besked med en väg vidare — aldrig en tom ruta
       och aldrig ett JS-fel i konsolen. */
    function felade(e) {
      const avbrutet = e && (e.name === 'AbortError' || /abort/i.test(e.message || ''));
      if (avbrutet) return;
      timers.forEach(clearTimeout);
      el.dataset.lage = 'stoppad';
      smalUt();
      $('.fstopp', el).hidden = true;
      $$('.ffas[data-lage="kor"]', el).forEach(f => { f.dataset.lage = 'fel'; });
      malaText((e && e.message) || 'Det gick inte att skriva dokumentet.', text);
      const a = $('.fatgard', el);
      a.hidden = false;
      a.innerHTML = '';
      const b = document.createElement('button');
      b.className = 'ghost';
      b.textContent = 'Försök igen';
      b.addEventListener('click', () => (o.onIgen ? o.onIgen() : kor(host, o)));
      a.appendChild(b);
      if (o.efterFel) o.efterFel(e);
    }

    /* Klockan räknar upp — den enda ärliga siffran när svaret kommer på en gång.
       Och den mäter från KÖRNINGENS start, inte från den fas som råkar vänta:
       förr stod 0:22 i rutan och «svarade efter 4:49» i raden efteråt. */
    let klockan = null;
    const vantaruta = $('.fvanta', el);
    const gangen = () => Math.max(0, Math.round((Date.now() - t0) / 1000 * (o.jobb ? 1 : TAKT)));
    const klocktext = s => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
    function vantelage(pa) {
      vantaruta.hidden = smalt || !pa;
      if (!pa) { clearInterval(klockan); klockan = null; return; }
      if (klockan) return;
      const skriv = () => {
        const t = klocktext(gangen());
        $('.vklocka', el).textContent = t;
        if (smalt && smalruta.isConnected) $('.fsmalklocka', el).textContent = t;
      };
      skriv();
      klockan = setInterval(skriv, 250);
      timers.push(klockan);
    }
    let vantatSek = 0;

    /* fas 3 — svaret kommer på en gång och stiger in. Ingen strömmande text:
       det finns ingen ström att visa när svaret kommer i ett stycke. */
    function visaSvar() {
      if (stoppad) return;
      /* Med ett riktigt jobb kan svarstexten säga vad som FAKTISKT kom tillbaka
         — hur många reparationsrundor det tog, vad som inte gick att rätta. */
      malaText(typeof o.svar === 'function' ? o.svar(svaret) : o.svar, text);
      klar();
    }

    function klar() {
      el.dataset.lage = 'klar';
      smalUt();
      vantelage(false);
      $('.fstopp', el).hidden = true;
      const s = gangen();
      const t = $('.ftankte', el);
      t.hidden = false;
      t.textContent = `Claude svarade efter ${klocktext(s)}`;
      t.setAttribute('aria-expanded', 'false');
      faser.hidden = true;
      t.addEventListener('click', () => {
        const oppen = t.getAttribute('aria-expanded') === 'true';
        t.setAttribute('aria-expanded', String(!oppen));
        faser.hidden = oppen;
      });
      const rutan = $('.fkallor', el);
      (o.kallor || []).forEach(k => {
        const grupp = document.createElement('span');
        grupp.className = 'kkalla';
        const b = document.createElement('button');
        b.className = 'kchip';
        b.type = 'button';
        b.innerHTML = '<b></b>' + (k.tid ? `<span class="ktid">${k.tid}</span>` : '');
        $('b', b).textContent = k.titel;
        b.addEventListener('click', () => o.onKalla && o.onKalla(k));
        grupp.appendChild(b);
        /* Ljudet kommer till svaret — 20 sekunder runt tidsstämpeln, på plats,
           utan att lektionen behöver öppnas. */
        if (k.tid) {
          const s = document.createElement('button');
          s.className = 'kspela';
          s.type = 'button';
          s.setAttribute('aria-label', `Spela 20 sekunder från ${k.tid}`);
          s.innerHTML = '<span class="kspelikon">▶</span><span class="kspeltext">20 s</span>';
          s.addEventListener('click', ev => { ev.stopPropagation(); spelaBit(s, k); });
          grupp.appendChild(s);
        }
        rutan.appendChild(grupp);
      });
      rutan.hidden = !(o.kallor || []).length;
      if (o.atgarder && o.atgarder.length) {
        const a = $('.fatgard', el);
        a.hidden = false;
        o.atgarder.forEach(x => {
          const b = document.createElement('button');
          b.className = x.stark ? 'primar' : 'ghost';
          b.textContent = x.namn;
          b.addEventListener('click', () => x.gor(el));
          a.appendChild(b);
        });
      }
      if (o.efterKlar) o.efterKlar(el, svaret);
      /* Svaret ska stå i vyn när det kommer — ingen jakt neråt efteråt. */
      if (smalt) setTimeout(() => { if (el.isConnected) hallKvar(el, 'topp'); }, 240);
    }

    return { el, stoppa };
  }

  /* Närmaste rullbara förälder — chattråden, inte sidan. */
  function rullbox(node) {
    let p = node.parentElement;
    while (p && p !== document.body) {
      const ov = getComputedStyle(p).overflowY;
      if ((ov === 'auto' || ov === 'scroll') && p.scrollHeight > p.clientHeight + 4) return p;
      p = p.parentElement;
    }
    return null;
  }
  function hallKvar(node, lage) {
    const box = rullbox(node);
    const r = node.getBoundingClientRect();
    if (!box) {
      /* Ingen rullbar låda — då är det sidan som ska följa med, mjukt, så att
         förloppet står i synfältet i stället för att hända under kanten. */
      const h = window.innerHeight;
      let mal;
      if (lage === 'botten') {
        const under = r.bottom - (h - 40);
        if (under <= 0) return;
        mal = window.scrollY + under;
      } else if (lage === 'mitt' && r.height < h - 140) {
        mal = window.scrollY + r.top - (h - r.height) / 2;
      } else {
        mal = window.scrollY + r.top - 130;
      }
      mal = Math.max(0, mal);
      (window.rullaTill || ((y) => window.scrollTo(0, y)))(mal, 620);
      return;
    }
    const b = box.getBoundingClientRect();
    const topp = box.scrollTop + (r.top - b.top);
    let mal;
    if (lage === 'botten') {
      /* Hela rutan — text, spår och klocka — ska stå innanför underkanten. */
      const under = r.bottom - (b.bottom - 16);
      if (under <= 0) return;
      mal = box.scrollTop + under;
    } else if (lage === 'mitt' && r.height < box.clientHeight - 40) {
      mal = topp - (box.clientHeight - r.height) / 2;
    } else {
      mal = topp - 20;
    }
    (window.rullaLada || ((x, y) => { x.scrollTop = y; }))(box, mal, 560);
  }

  window.Fraga = { kor, get varm() { return varm; }, MODELL };

  /* En kort uppspelning i svaret: knappen blir ett spår som fylls, och raden ur
     transkriptet står under källorna medan den spelas. */
  function spelaBit(knapp, k) {
    const grupp = knapp.parentElement;
    if (grupp.hasAttribute('data-spelar')) return;
    grupp.setAttribute('data-spelar', '');
    const gammal = knapp.innerHTML;
    knapp.innerHTML = '<span class="kspelspar"><span></span></span>';
    const fyll = $('.kspelspar > span', knapp);
    const rad = document.createElement('p');
    rad.className = 'kspelrad';
    rad.innerHTML = '<span class="ktid2"></span><span class="kspeltxt"></span>';
    $('.ktid2', rad).textContent = k.tid;
    $('.kspeltxt', rad).textContent = k.text || 'Spelar de tjugo sekunderna runt tidsstämpeln.';
    grupp.after(rad);
    let p = 0;
    const t = setInterval(() => {
      p += 4.2;
      fyll.style.width = Math.min(100, p) + '%';
      if (p < 100) return;
      clearInterval(t);
      grupp.removeAttribute('data-spelar');
      knapp.innerHTML = gammal;
      rad.remove();
    }, 90);
  }
})();
