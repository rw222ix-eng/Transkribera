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
     så texten «brukar ta 1–2 min» stämmer mot det som visas. */
  const TAKT = 22;
  let varm = false;

  const fas = (namn, extra = '') =>
    `<div class="ffas" data-lage="vantar"><span class="fikon"></span><span class="fnamn">${namn}</span><span class="fdetalj"></span>${extra}</div>`;

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
    el.innerHTML = '<div class="fjobb"><span class="fjobbprickar"><i></i><i></i><i></i></span><span class="fjobbtext"></span><button class="lank fstopp" type="button">Avbryt</button></div><p class="ftext"></p><div class="fatgard" hidden></div>';
    $('.fjobbtext', el).textContent = o.jobbtext || `Skriver om ${o.omfang || 'dokumentet'} …`;
    if (o.lagg) host.appendChild(el); else { host.innerHTML = ''; host.appendChild(el); }
    host.hidden = false;
    let stoppad = false;
    const jobb = $('.fjobb', el);
    const t = setTimeout(() => {
      if (stoppad) return;
      jobb.setAttribute('data-ut', '');
      setTimeout(() => jobb.remove(), 220);
      el.dataset.lage = 'klar';
      malaText(o.svar, $('.ftext', el));
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
      if (o.efterKlar) o.efterKlar(el);
    }, o.vantan || 1400);
    const stoppa = etikett => {
      stoppad = true;
      clearTimeout(t);
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
      <div class="fsmal"><div class="fsmalinre"><div class="fsmalrad"><span class="fsmaltext"></span><span class="fsmalklocka"></span></div><div class="fsmalspar"><i></i></div></div></div>
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
    const smal = (namn, frac) => {
      if (!smalt || !smalruta.isConnected) return;
      $('.fsmaltext', el).textContent = namn;
      smalfyll.style.width = Math.round(Math.max(4, Math.min(100, frac * 100))) + '%';
    };
    const smalUt = () => {
      if (!smalt || !smalruta.isConnected) return;
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

    const stoppa = (etikett) => {
      stoppad = true;
      timers.forEach(clearTimeout);
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
      smal('Läser igenom ' + (o.omfang || 'materialet'), 0.06);
      const steg = setInterval(() => {
        i = Math.min(n, i + Math.max(1, Math.ceil(n / 9)));
        $('.fdetalj', f).textContent = `${i} av ${n}`;
        smal('Läser igenom ' + (o.omfang || 'materialet'), 0.06 + (i / n) * 0.18);
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
    function plan() {
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
      let t = 0;
      rader.forEach((r, i) => {
        const langd = r.vanta ? 1500 : r.kort ? 260 : 340;
        const nu = t;
        senare(nu, () => {
          noder[i].dataset.lage = 'kor';
          smal(r.namn, 0.24 + ((i + 1) / rader.length) * 0.72);
          vantelage(!!r.vanta);
        });
        senare(nu + langd - 20, () => {
          noder[i].dataset.lage = 'klar';
          $('.fdetalj', noder[i]).textContent = r.detalj || '';
          if (i === rader.length - 1) { vantelage(false); visaSvar(); }
        });
        t += langd;
      });
    }

    /* Klockan räknar upp — den enda ärliga siffran när svaret kommer på en gång.
       Och den mäter från KÖRNINGENS start, inte från den fas som råkar vänta:
       förr stod 0:22 i rutan och «svarade efter 4:49» i raden efteråt. */
    let klockan = null;
    const vantaruta = $('.fvanta', el);
    const gangen = () => Math.max(0, Math.round((Date.now() - t0) / 1000 * TAKT));
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
      malaText(o.svar, text);
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
      if (o.efterKlar) o.efterKlar(el);
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
