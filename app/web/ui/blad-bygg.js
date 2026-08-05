/* ══════════ BLADBYGGAREN ══════════
   Sätter arbetsblad, gruppuppgift, prov och facit ur avsnittets innehåll
   (innehall.js) i förlagans klasser. Förlagan bestämmer fortfarande UTSEENDET;
   det som byggs här är VAD som står på pappret.

   Matematik skrivs «$…$» i innehållet och blir KaTeX här. */
window.BladBygg = (() => {
  const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const attr = s => String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
  /* Texten är text — utom mellan dollartecken. Delningen görs på hela strängen
     så att en formel aldrig kan halveras av HTML-escapen. */
  const mat = s => String(s == null ? '' : s).split('$').map((bit, i) =>
    i % 2 ? `<span class="mat" data-tex="${attr(bit)}"></span>` : esc(bit)).join('');
  const BOKSTAV = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'];
  const versal = s => String(s || '').charAt(0).toUpperCase() + String(s || '').slice(1);

  /* ── Svarsutrymmet: en rad eller ett lösblad. Inget annat. ──
     Eleven gör en av två saker: skriver bara svaret, eller löser hela uppgiften
     på rutat lösblad. Ett linjerat fält mitt i bladet ger varken det ena eller
     det andra — för litet att räkna i, för stort att bara svara på — och mallen
     bär inte ett enda. Samma val som provet gör. */
  const losblad = 'Lösningen skrivs på lösblad.';
  const svarsrad = '<div class="gurad gusvarsrad"><span class="gunamn">Svar:</span><span class="gulinje"></span></div>';

  function svarsyta(u) {
    return u.ut === 'kort' ? svarsrad : `<p class="gulos">${losblad}</p>`;
  }

  /* ── Arbetsbladet och gruppuppgiften ─────────────── */
  function kort(u, i, illustration) {
    const bricka = BOKSTAV[i] || String(i + 1);
    const alt = u.alt
      ? `<ul class="gudel guval">${u.alt.map((a, k) => `<li><i>${BOKSTAV[k]}.</i> ${mat(a)}</li>`).join('')}</ul>` : '';
    const del = u.del && u.del.length
      ? `<ul class="gudel">${u.del.map((d, k) => `<li>${'abcdef'[k]}) ${mat(d)}</li>`).join('')}</ul>` : '';
    const fig = illustration && !u.fig
      ? '<div class="gufigur guplats" style="height:110px"><span class="gufigtext">plats för illustration</span></div>' : '';
    const egen = u.fig ? `<div class="gufigur" data-vantar="" data-figur="${attr(JSON.stringify(u.fig))}"></div>` : '';
    return `<div class="gukort" data-ut="${u.ut || 'rakna'}">
      <span class="gubricka">${bricka}</span>
      <p class="gufraga">${mat(u.t)}</p>${alt}${del}${egen}${fig}${svarsyta(u)}
    </div>`;
  }

  /* Instruktionsbandet säger hur man arbetar — inte vad uppgifterna handlar om.
     Det står i uppgifterna. */
  const BAND = {
    Arbetsblad: 'Skriv svaret på svarsraden där det står «Svar». De uppgifter som ska redovisas är märkta — skriv uppgiftens bokstav överst på lösbladet. Visa hur du räknar, inte bara svaret.',
    Gruppuppgift: 'Läs uppgiften tillsammans innan ni börjar räkna. Bestäm vem som skriver. Alla i gruppen ska kunna förklara lösningen efteråt.'
  };

  function ark(v, uppgifter, o) {
    const i = v.inst || {};
    const grupp = v.typ === 'Gruppuppgift';
    const namnrader = grupp ? Math.max(2, Math.min(6, Number(i.grupp) || 3)) : 1;
    const rad = '<div class="gurad"><span class="gunamn">Namn:</span><span class="gulinje"></span></div>';
    return `<div class="gu" data-form="${grupp ? 'gu' : 'ab'}">
      <div class="guhuv"><h1 class="gutitel">${esc(versal(v.moment || o.titel || ''))}</h1></div>
      <div class="gutopp">${rad.repeat(namnrader)}</div>
      <div class="guband">${esc(BAND[v.typ] || BAND.Arbetsblad)}</div>
      ${uppgifter.map((u, k) => kort(u, k, !!i.illustration)).join('')}
    </div>`;
  }

  /* ── Facit till arbetsbladet ─────────────────────── */
  function arkfacit(v, uppgifter) {
    const post = (u, k) => `<div class="pruppg">
      <span class="prnr">${BOKSTAV[k] || k + 1}.<span class="prvarde">${u.p} p</span></span>
      <div><p class="prtext">${mat(u.t)}</p>
        <div class="losvar"><b class="losetikett">Svar</b><span>${mat(u.f)}</span>${u.enhet ? `<em>${esc(u.enhet)}</em>` : ''}</div>
        ${u.vag ? `<ul class="lovag">${u.vag.map(s => `<li><span class="losteg">${mat(s[0])}<em>${esc(s[1])}</em></span></li>`).join('')}</ul>` : ''}
      </div></div>`;
    return `<div class="ark" data-form="fa">
      <div class="lohuvud"><b>Facit</b><span>${esc(versal(v.moment || ''))}</span></div>
      <h1 class="lotitel">Svar och lösningsgång</h1>
      <p class="lolede">Poängen står vid det steg den delas ut på. Ett svar utan uträkning ger inte full poäng på uppgifter som kräver lösning.</p>
      ${uppgifter.map(post).join('')}
    </div>`;
  }

  /* ── Provet ──────────────────────────────────────
     Skelettet är förlagans; blad.js fyller provtid, poäng och betygsgränser
     efter planeringen (planvalProv). Här sätts uppgifterna. */
  function huvud(v, andra) {
    const t = [v.kurs || 'Matematik', v.klass || '', 'ht 2026'].filter(Boolean).join(' · ');
    return `<div class="prhuvud"><b>${esc(t)}</b>${andra ? `<b>${esc(andra)}</b>` : ''}</div>`;
  }
  function provuppg(u) {
    const alt = u.alt
      ? `<ul class="prdel prval">${u.alt.map((a, k) => `<li><i>${BOKSTAV[k]}.</i>${mat(a)}</li>`).join('')}</ul>` : '';
    const del = u.del && u.del.length
      ? `<ul class="prdel" data-avdelad="">${u.del.map((d, k) => `<li><i>${'abcdef'[k]})</i><span>${mat(d)}</span><span class="prpo">${Math.max(1, Math.round(u.p / u.del.length))} p</span></li>`).join('')}</ul>` : '';
    /* SVARET står alltid i provet — på båda delarna, på varje uppgift. Förr
       hängde raden på u.ut === 'kort', och en uppgift som saknade den märkningen
       blev en fråga utan svarsplats mitt bland två som hade det. Alternativ
       (kryssrutor) och deluppgifter bär sin egen plats. */
    const behoverRad = !u.alt && !(u.del && u.del.length);
    const svarsrad = behoverRad ? '<div class="prsvar"><span class="prlinje"></span></div>' : '';
    /* REDOVISNINGEN görs aldrig i provet, alltid på separat lösblad. Uppgifter
       som kräver en redovisad lösning märks i marginalen under numret — samma
       plats som poängen, för båda avgörs innan man läst uppgiften. */
    const losblad = !u.alt && u.ut !== 'kort' ? '<span class="prlosblad">lösblad</span>' : '';
    /* Marginalen bär ETT format. «(totalt 3 p)» bredvid «1 p» läste sig som två
       olika fält; att poängen är en summa framgår av deluppgifternas egna. */
    const varde = `${u.p} p`;
    return `<div class="pruppg">
      <span class="prnr">${u.nr}.<span class="prvarde">${varde}</span>${losblad}</span>
      <div><p class="prtext">${mat(u.t)}</p>${alt}${del}${svarsrad}</div>
    </div>`;
  }
  function provforsatt(v) {
    return `<div class="ark" data-form="pr1">
      ${huvud(v)}
      <h1 class="prtitel">${v.variant === 'Omprov' ? 'Omprov' : 'Prov'} — ${esc(versal(v.moment || ''))}</h1>
      <div class="prrad"><b>Namn</b><span class="prlinje"></span></div>
      <table class="prmeta"><tbody></tbody></table>
      <p class="prnot"></p>
      <table class="prbetyg"><thead><tr><th>Betyg</th><th>Poäng som krävs</th></tr></thead><tbody></tbody><tfoot><tr><td>Maxpoäng</td><td></td></tr></tfoot></table>
    </div>`;
  }
  /* Provet har TVÅ delar och skillnaden mellan dem är HJÄLPMEDLEN, inte
     svarsformen: del A utan digitala hjälpmedel, del B med räknare och GeoGebra.
     Båda delarna bär korta svar OCH uppgifter som ska redovisas — och
     redovisningen görs på separat lösblad, aldrig i provet.

     data-form heter pr1b/pr1c: det är förlagans egna nycklar («Arbetsblad prov
     och tavlor — femton former»), och det är dem prov.css sätter uppgiftsavstånd,
     svarsrad och deluppgifter efter. Förr hette de prb/prc — namn som ingen regel
     kände — och då fick appens provblad basvärdena i stället för mallens
     sättning. DELNAMN är det enda som syns.

     Kvar att avgöra: 'ab' (arbetsblad), 'gu' (gruppuppgift), 'fa' (facit) och
     'lo-b'/'lo-c' har ingen motsvarighet bland förlagans former (gu1, gu2, gu6,
     lo4) och får därför basvärdena ur blad.css i stället för en per-form-sättning.
     Det är ett VAL vilken av förlagans fyra arbetsbladsformer appens arbetsblad
     ska vara — inte en bugg att rätta blint. */
  const DELNAMN = { B: 'Del A', C: 'Del B' };
  function provblad(v, uppgifter, del, forsta) {
    const medHjalp = del === 'C';
    const obs = forsta && del !== '-'
      ? `<p class="probs"><b>OBS!</b> ${medHjalp
        ? 'Räknare och digitala hjälpmedel (t.ex. GeoGebra) är tillåtna.'
        : 'Räknare och digitala hjälpmedel är inte tillåtna.'} Svaret skrivs på raden här i provet. Uppgifter märkta «lösblad» redovisas på separat rutat lösblad — en uppgift per sida, med uppgiftens nummer och ditt namn.</p>`
      : '';
    const etikett = del === '-' ? '' : `${DELNAMN[del]} · ${medHjalp ? 'räknare och digitala hjälpmedel' : 'utan digitala hjälpmedel'}`;
    return `<div class="ark" data-form="pr1${del.toLowerCase()}" data-brytbar="">
      ${huvud(v, etikett)}${obs}${uppgifter.map(provuppg).join('')}
    </div>`;
  }

  /* ── Lösningsförslaget ───────────────────────────── */
  function losKort(u) {
    return `<div class="pruppg">
      <span class="prnr">${u.nr}.<span class="prvarde">${u.p} p</span></span>
      <div><p class="prtext">${mat(u.t)}</p>
        <div class="losvar"><b class="losetikett">Svar</b><span>${mat(u.f)}</span>${u.enhet ? `<em>${esc(u.enhet)}</em>` : ''}</div>
      </div></div>`;
  }
  function losVag(u) {
    return `<div class="pruppg">
      <span class="prnr">${u.nr}.<span class="prvarde">${u.p} p</span></span>
      <div><p class="prtext">${mat(u.t)}</p>
        <ul class="lovag">${(u.vag || []).map(s => `<li><span class="losteg">${mat(s[0])}<em>${esc(s[1])}</em></span></li>`).join('')}</ul>
        <div class="losvar"><b class="losetikett">Svar</b><span>${mat(u.f)}</span></div>
      </div></div>`;
  }
  /* Kortsvarsfacit för del A, utskriven lösningsgång för del B. Ett facit som
     bara svarar på halva provet ska säga det — därför räknas uppgifterna. */
  function losning(v, uppgifter, delB) {
    const b = uppgifter.filter(u => u.nr <= delB);
    const c = uppgifter.filter(u => u.nr > delB);
    const ut = [];
    const spann = l => (l.length === 1 ? `uppgift ${l[0].nr}` : `uppgift ${l[0].nr}–${l[l.length - 1].nr}`);
    if (b.length) ut.push(`<div class="ark" data-form="lo-b" data-brytbar="">
      <div class="lohuvud"><b>Svarsfacit · kortsvar</b><span>${delB >= uppgifter.length ? versal(spann(b)) : DELNAMN.B + ' · ' + spann(b)}</span></div>
      <h1 class="lotitel">Endast svar krävs</h1>
      ${b.map(losKort).join('')}</div>`);
    if (c.length) ut.push(`<div class="ark" data-form="lo-c" data-brytbar="">
      <div class="lohuvud"><b>Lösningsförslag · ${DELNAMN.C.toLowerCase()}</b><span>${DELNAMN.C} · ${spann(c)}</span></div>
      <h1 class="lotitel">Hela lösningen krävs</h1>
      ${c.map(losVag).join('')}</div>`);
    return ut;
  }

  return { mat, ark, arkfacit, provforsatt, provblad, losning, BOKSTAV };
})();
