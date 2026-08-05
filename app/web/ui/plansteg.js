/* ══════════ STAPELN — ett steg öppet, klara steg viker ihop sig ══════════
   Sidan växte men blev aldrig kortare: varje avklarat steg låg kvar i full
   höjd. Här blir ett klart steg en rad med sitt eget svar, kommande steg en
   streckad rad, och bara det aktiva steget har kropp. Ordningen är densamma —
   det är höjden som försvinner. */
(() => {
  const q = s => document.querySelector(s), qq = s => [...document.querySelectorAll(s)];
  const steg = qq('.plansteg[data-steg]');
  if (!steg.length) return;
  const moment = q('#moment');
  const sista = Math.max(...steg.map(e => +e.dataset.steg));
  /* Steg 1 frågade vilken lektion — den frågan ställs nu i veckan högst upp och
     finns inte längre i stapeln. Numren i koden står kvar (2–4), numren på
     skärmen kommer ur data-visnr, så läraren ser 1–3. */
  const forsta = Math.min(...steg.map(e => +e.dataset.steg));

  const rullaBox = (box, mal) => (window.rullaLada || ((b, y) => { b.scrollTop = y; }))(box, mal, 680);
  function mjuk(el) {
    const r = el.getBoundingClientRect();
    let p = el.parentElement, box = null;
    while (p) {
      const s = getComputedStyle(p);
      if (/auto|scroll/.test(s.overflowY) && p.scrollHeight > p.clientHeight + 4) { box = p; break; }
      p = p.parentElement;
    }
    if (box) {
      const br = box.getBoundingClientRect();
      rullaBox(box, box.scrollTop + r.top - br.top - 100);
    } else {
      const mal = Math.max(0, window.scrollY + r.top - 130);
      window.rullaTill ? window.rullaTill(mal, 680) : window.scrollTo(0, mal);
    }
  }

  /* ── Svaret varje klart steg visar ── */
  const typerna = () => window.LageText ? window.LageText() : (window.Lagen ? window.Lagen() : []).join(' + ');
  function svaret(n) {
    if (n === 1) {
      const k = q('#p-klass').value, ku = q('#p-kurs').value;
      const d = q('#p-datum').value;
      const nar = d && window.Kalender ? window.Kalender.ord(d) : '';
      const tid = q('#p-tid').value;
      const bit = [k, ku, [nar, tid].filter(Boolean).join(' ')].filter(Boolean);
      return bit.length ? bit.join(' · ') : 'Utan lektion ur schemat';
    }
    if (n === 2) return typerna() || 'Inget valt';
    if (n === 3) {
      const lekt = q('#valdalektioner').children.length;
      const sid = q('#sidminis').children.length;
      const forlaga = window.Dokument && window.Dokument.forlagan && window.Dokument.forlagan();
      const bit = [];
      /* Momentet kommer ur boken, och boken är en dörr man kan ha stängt. Står
         avsnittet här med dörren avslagen säger raden att pappret utgår från
         boken medan stegets eget kvitto inte har någon bokrad — två svar på
         samma fråga, tio pixlar isär. */
      const bokdorr = q('.kalla[data-dorr="bok"]');
      const bok = !bokdorr || bokdorr.getAttribute('aria-pressed') === 'true' ? moment.value.trim() : '';
      /* Sidorna står ofta redan i momentet («s. 244–249 ur …») — då ska de inte
         sägas en gång till efter det. */
      if (bok) bit.push(moment.dataset.sidor && !bok.includes(moment.dataset.sidor) ? `${bok} · ${moment.dataset.sidor}` : bok);
      if (forlaga) bit.push(window.Dokument.namn(forlaga));
      /* Ett rättat prov är ett underlag som påverkar innehållet mest av alla — det
       ska inte tystna i sammanfattningen. */
      const res = window.Dokument && window.Dokument.resultatet && window.Dokument.resultatet();
      if (res) {
        const sv = ((res.rattat || {}).svaga || []).map(s => s.kod).filter(Boolean);
        bit.push(sv.length ? `provets utfall (uppg ${sv.join(', ')})` : 'provets utfall');
      }
      if (lekt) bit.push(`${lekt} ${lekt === 1 ? 'lektion' : 'lektioner'}`);
      /* Papperen som följer med lektionen räknas — annars säger raden «1 lektion»
         medan tre saker faktiskt ligger som underlag. */
      const mat = window.Lektionsmaterial ? window.Lektionsmaterial.antal() : 0;
      if (mat) bit.push(`${mat} ${mat === 1 ? 'papper' : 'papper'} från lektionen`);
      if (sid) bit.push(`${sid} ${sid === 1 ? 'sida' : 'sidor'}`);
      return bit.length ? bit.join(' · ') : 'Inget underlag';
    }
    return '';
  }

  /* ── Raderna som ersätter ett hopfällt steg ── */
  const rader = {};
  steg.forEach(el => {
    const n = +el.dataset.steg;
    const rad = document.createElement('div');
    rad.className = 'stegrad';
    rad.hidden = true;
    rad.innerHTML = '<span class="stegbock">✓</span><span class="stegtext"><b></b><span></span></span><button class="lank stegandra" type="button">ändra</button>';
    rad.querySelector('b').textContent = `${el.dataset.visnr || n} · ${el.dataset.namn || 'Steg ' + n}`;
    rad.querySelector('.stegandra').addEventListener('click', () => { foreslagna.delete(n); gaTill(n); });
    el.parentElement.insertBefore(rad, el);

    const vant = document.createElement('button');
    vant.type = 'button';
    vant.className = 'stegvant';
    vant.hidden = true;
    vant.innerHTML = '<span class="stegring"></span><span class="stegtext"><b></b><span></span></span>';
    vant.querySelector('b').textContent = `${el.dataset.visnr || n} · ${el.dataset.namn || 'Steg ' + n}`;
    vant.querySelector('span span').textContent = el.dataset.vant || '';
    vant.addEventListener('click', () => { if (!vant.disabled) gaTill(n); });
    el.parentElement.insertBefore(vant, el.nextSibling);
    rader[n] = { rad, vant, el };

    /* Varje öppet steg behöver en synlig väg framåt — sista steget har sin
       skrivknapp, de andra får en. */
    if (n < sista) {
      const fot = document.createElement('div');
      fot.className = 'stegfot';
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'primar';
      b.textContent = 'Nästa';
      b.addEventListener('click', () => {
        if (b.disabled) return;
        if (n === forsta && window.PlanKo) window.PlanKo.starta();
        foreslagna.delete(n);
        klara.add(n); las(n + 1);
      });
      /* Steg 1 har ett krav: något måste vara valt. Utan spärren gick man vidare
         med «Inget valt» och fick ändå ett dokument — det som råkade ligga kvar i
         den dolda typväljaren. */
      if (n === forsta) {
        const spegla = () => {
          const har = window.Lagen ? window.Lagen().length : 1;
          b.disabled = !har;
          b.dataset.tip = har ? '' : 'Välj minst ett att skapa';
        };
        document.addEventListener('lagen', spegla);
        spegla();
      }
      fot.appendChild(b);
      /* «Du har inte markerat en lektion» hör till samma beslut som knappen och
         ska stå intill den, inte under korten. Foten ger raden sin plats; notis.js
         avgör när den syns. */
      if (n === forsta) { const obs = q('#lagenobs'); if (obs) fot.insertBefore(obs, b); }
      el.appendChild(fot);
    }
  });

  let nu = forsta;
  const klara = new Set();
  /* Svaret ett stängt steg visar. Nollställs bara av «Börja om». */
  const svarSnap = {};
  const TOMSVAR = /^(Inget underlag|Inget valt|Utan lektion ur schemat)$/;
  /* Skillnad på «jag valde det här» och «appen föreslog det». En förbockad rad
     man aldrig rört såg ut som ett beslut man tagit. */
  const foreslagna = new Set();

  function rita(rulla) {
    steg.forEach(el => {
      const n = +el.dataset.steg;
      const r = rader[n];
      const aktiv = n === nu;
      const klar = !aktiv && klara.has(n);
      el.hidden = !aktiv;
      el.toggleAttribute('data-nu', aktiv);
      el.removeAttribute('data-last');
      r.rad.hidden = !klar;
      r.vant.hidden = aktiv || klar;
      r.rad.toggleAttribute('data-foreslaget', klar && foreslagna.has(n));
      if (klar && foreslagna.has(n)) r.rad.dataset.tip = 'Föreslaget av appen — klicka ändra för att välja själv';
      else r.rad.removeAttribute('data-tip');
      /* En väntande rad går att klicka så snart steget före är avklarat — annars
       är den bara en upplysning om vad som kommer. */
      r.vant.disabled = !(n === forsta || klara.has(n - 1));
      if (aktiv) svarSnap[n] = svaret(n);
      if (klar) {
        const nytt = svaret(n);
        if (!TOMSVAR.test(nytt) || !svarSnap[n]) svarSnap[n] = nytt;
        r.rad.querySelector('.stegtext span').textContent = svarSnap[n];
      }
    });
    if (rulla) {
      const el = rader[nu] && rader[nu].el;
      if (el) setTimeout(() => mjuk(el), 60);
    }
  }

  function gaTill(n, rulla = true) {
    if (n < forsta || n > sista) return;
    nu = n;
    rita(rulla);
  }

  /* las(n) = «steget är nu tillgängligt»: allt före räknas som klart, och det
     öppna steget flyttas fram — aldrig bakåt, den som backat får stå kvar. */
  function las(n, rulla = true) {
    n = Math.min(n, sista);
    for (let i = forsta; i < n; i++) klara.add(i);
    if (nu < n) { nu = n; rita(rulla); } else { rita(false); }
  }

  /* Börja om på steg 1 utan att kasta det som redan är ifyllt. */
  function omstart(rulla = true) { klara.clear(); Object.keys(svarSnap).forEach(k => delete svarSnap[k]); nu = forsta; rita(rulla); }

  window.PlanSteg = { las, gaTill, omstart, rita: () => rita(false) };

  /* Är lektionen vald är steg 1 klart — oavsett om man gick vidare med Nästa
     eller hoppade i stapeln. Raden ska visa bocken, inte den tomma ringen. */
  const kollLektion = () => {
    const har = ($('#p-klass') || {}).value || ($('#p-datum') || {}).value
      || (window.PlanKo && window.PlanKo.valda && window.PlanKo.valda().length);
    if (har) { klara.add(1); rita(false); }
  };
  ['#p-klass', '#p-datum', '#p-tid'].forEach(s => {
    const f = q(s);
    if (f) f.addEventListener('change', kollLektion);
  });
  q('#schemagrid') && q('#schemagrid').addEventListener('click', () => setTimeout(kollLektion, 90), true);
  kollLektion();

  /* Momentet skrivet → steg 3. Låses upp medan man skriver, men sidan flyttar
     sig först när fältet är färdigt: att rycka undan mitt i en mening vore fel. */
  const kollMoment = (rulla) => { if (moment.value.trim() && (window.Lagen ? window.Lagen().length : 1)) las(3, rulla); };
  moment.addEventListener('input', () => { if (moment.value.trim()) klara.add(2); });
  moment.addEventListener('change', () => kollMoment(true));
  moment.addEventListener('blur', () => kollMoment(true));
  moment.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); moment.blur(); } });

  /* Underlag valt, eller överhoppat → sista steget */
  const vidareTre = () => las(sista);
  q('#hoppaunderlag').addEventListener('click', vidareTre);
  const chips = q('#valdalektioner'), minis = q('#sidminis');
  const obs = new MutationObserver(() => {
    if (chips.children.length || minis.children.length) {
      if (!klara.has(3)) foreslagna.add(3);
      klara.add(3); rita(false);
    }
  });
  obs.observe(chips, { childList: true });
  obs.observe(minis, { childList: true });
  rita(false);

  /* Dropzon — dra in sidor, eller välj lektioner / filer via länkarna */
  const zon = q('#dropzon'), utan = q('#utanrad');
  if (zon) {
    q('#dzlektioner').addEventListener('click', e => { e.stopPropagation(); q('#lektionsknapp').click(); });
    q('#dzfiler').addEventListener('click', e => { e.stopPropagation(); q('#sidknapp').click(); });
    zon.addEventListener('click', () => q('#sidknapp').click());
    ['dragenter', 'dragover'].forEach(n => zon.addEventListener(n, e => { e.preventDefault(); zon.setAttribute('data-over', ''); }));
    ['dragleave', 'dragend'].forEach(n => zon.addEventListener(n, () => zon.removeAttribute('data-over')));
    zon.addEventListener('drop', e => {
      e.preventDefault();
      zon.removeAttribute('data-over');
      const fil = q('#sidfil');
      if (e.dataTransfer && e.dataTransfer.files.length && fil) {
        fil.files = e.dataTransfer.files;
        fil.dispatchEvent(new Event('change'));
      }
    });
    /* Dropzonen syns numera så länge fotodörren står öppen — kallor.js äger
       synligheten. Den gamla speglingen gömde zonen så fort NÅGOT underlag var
       valt, vilket slog till redan när lektionen föreslogs av sig själv. */
    if (!window.Kallor) {
      const harVal = () => chips.children.length || minis.children.length;
      const speglaZon = () => {
        const valt = harVal();
        zon.hidden = valt;
        utan.hidden = valt;
      };
      new MutationObserver(speglaZon).observe(chips, { childList: true });
      new MutationObserver(speglaZon).observe(minis, { childList: true });
      speglaZon();
    }
  }

  /* Detaljer — hopfälld sammanfattning som standard */
  /* Klass, kurs och dag står redan i kalendern och fylls när lektionen klickas.
     Fälten finns kvar som appens minne — men ingen knapp frågar en andra gång. */
  const text = q('#detaljtext');
  function sammanfatta() {
    if (!text) return;
    const k = q('#p-klass').value || 'ingen klass';
    const ku = q('#p-kurs').value || 'ingen kurs';
    const dv = (q('#p-datum') || {}).value || '';
    const dt = q('#pdatumknapp').querySelector('.valjtext').textContent.trim();
    const nar = dv ? dt : 'inget datum';
    text.textContent = [k, ku, nar].join(' · ');
  }
  ['#p-klass', '#p-kurs'].forEach(s => q(s).addEventListener('change', sammanfatta));
  new MutationObserver(sammanfatta).observe(q('#pdatumknapp'), { subtree: true, childList: true, characterData: true });
  sammanfatta();
})();
