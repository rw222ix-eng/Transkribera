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

  /* ── DE FEM FORMERNA ──────────────────────────────
     Datatabellen, kryssruteraden och stegtabellen är samma former som i
     förlagan («Arbetsblad prov och tavlor — femton former») och samma som
     LaTeX-mallarna sätter (_former.tex.j2). De byggs här EN gång och används
     av både arbetsbladet och provet — en form som sätts på två ställen glider
     isär på ett av dem.

     Facit står ALDRIG här: vilket kryss som är rätt och vilket steg som
     brister hör till lärarens papper (bedomning.tex.j2). */
  function tabell(t, klass) {
    if (!t || !t.rubriker) return '';
    const rad = celler => `<tr>${celler.map(c => `<td>${mat(c)}</td>`).join('')}</tr>`;
    return `<table class="${klass}"><thead><tr>${
      t.rubriker.map(r => `<th>${esc(r)}</th>`).join('')}</tr></thead><tbody>${
      (t.rader || []).map(rad).join('')}</tbody></table>`;
  }
  /* Kryssruteraden: en rad att fylla i, inte en flervalsfråga. Etiketten står
     där svarsradens namn står, rutorna där linjen skulle gå. */
  function rutor(r) {
    if (!r || !r.val) return '';
    return `<div class="gurad"><span class="gunamn">${esc(r.etikett)}:</span>`
      + `<span class="gurutor">${r.val.map(v => `<span class="guruta">${mat(v)}</span>`).join('')}</span></div>`;
  }
  /* Stegtabellen: en färdig lösning rad för rad, med en kryssrutekolumn där
     eleven markerar det FÖRSTA felet. */
  function stegtabell(s) {
    if (!s || !s.steg) return '';
    const kol = s.kolumner || [];
    return `<table class="gutab"><thead><tr><th class="gusteg">Steg</th>${
      kol.map(k => `<th>${esc(k)}</th>`).join('')}<th class="gukryss">Fel</th></tr></thead><tbody>${
      s.steg.map((st, i) => `<tr><td class="gusteg">${i + 1}</td>${
        (st.celler || []).map(c => `<td>${mat(c)}</td>`).join('')
      }<td class="gukryss"><span></span></td></tr>`).join('')}</tbody></table>`;
  }
  /* Namngivna ifyllnadsrader: «Ekvation: ______», «Svar i ord: ______».
     Samma två element som förlagans form 2 sätter dem med — etiketten i
     .gunamn, linjen i .gulinje — så en ny form aldrig drar med sig ett nytt
     utseende. Besluten skrivs på pappret, räkningen på lösblad. */
  function falt(f) {
    if (!f || !f.length) return '';
    return f.map(e => `<div class="gurad"><span class="gunamn">${esc(e)}:</span>`
      + '<span class="gulinje"></span></div>').join('');
  }
  /* Enheten på svarsraden: ledet före linjen, enheten efter den. */
  function svarsradEnhet(enhet) {
    return `<div class="gurad gusvarsrad"><span class="gunamn">Svar:</span>`
      + `<span class="gulinje"></span>${enhet ? `<span class="prenhet">${esc(enhet)}</span>` : ''}</div>`;
  }

  /* ── Svarsutrymmet: en rad eller ett lösblad. Inget annat. ──
     Eleven gör en av två saker: skriver bara svaret, eller löser hela uppgiften
     på rutat lösblad. Ett linjerat fält mitt i bladet ger varken det ena eller
     det andra — för litet att räkna i, för stort att bara svara på — och mallen
     bär inte ett enda. Samma val som provet gör. */
  const losblad = 'Lösningen skrivs på lösblad.';
  const svarsrad = '<div class="gurad gusvarsrad"><span class="gunamn">Svar:</span><span class="gulinje"></span></div>';

  function svarsyta(u) {
    /* Kryssrutorna ÄR svarsytan när de finns — den som kryssar skriver inte.
       Detsamma gäller de namngivna raderna: den som fyllt i «Ekvation» och
       «Svar i ord» har svarat, och en svarslinje till under dem är en rad
       ingen vet vad hon ska skriva på. Hänvisningen till lösbladet står kvar —
       det är DÄR räkningen görs, och det är hela poängen med formen. */
    if (u.falt && u.falt.length) {
      return falt(u.falt)
        + (u.ut !== 'kort' ? `<p class="gulos">${losblad}</p>` : '');
    }
    if (u.rutor) return rutor(u.rutor);
    if (u.ut !== 'kort') return `<p class="gulos">${losblad}</p>`;
    return u.enhet ? svarsradEnhet(u.enhet) : svarsrad;
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
    /* Figuren står BREDVID frågan, aldrig ovanför den — det är hela skillnaden
       mellan förlagans form 1 (radbunden) och form 2 (figurspalt), och eleven
       måste kunna läsa båda samtidigt. Förr lades figuren under uppgiften utan
       spalt: samma innehåll, en annan form än den som var ritad. */
    const egen = u.fig
      ? `<div class="gufigur" data-vantar="" data-figur="${attr(JSON.stringify(u.fig))}"></div>`
        + (u.figkap ? `<p class="gufigkap">${mat(u.figkap)}</p>` : '')
      : '';
    // Formerna står mellan frågan och svaret: tabellen att räkna på, lösningen
    // att granska, och sedan svarsytan.
    const former = tabell(u.tabell, 'gutab') + stegtabell(u.stegtabell);
    const kropp = egen
      ? `<div class="gutva"><div><p class="gufraga">${mat(u.t)}</p>${alt}${del}${former}${svarsyta(u)}</div>`
        + `<div>${egen}</div></div>`
      : `<p class="gufraga">${mat(u.t)}</p>${alt}${del}${former}${fig}${svarsyta(u)}`;
    return `<div class="gukort" data-ut="${u.ut || 'rakna'}">
      <span class="gubricka">${bricka}</span>
      ${kropp}
    </div>`;
  }

  /* Instruktionsbandet säger hur man arbetar — inte vad uppgifterna handlar om.
     Det står i uppgifterna. */
  const BAND = {
    Arbetsblad: 'Skriv svaret på svarsraden där det står «Svar». De uppgifter som ska redovisas är märkta — skriv uppgiftens bokstav överst på lösbladet. Visa hur du räknar, inte bara svaret.',
    Gruppuppgift: 'Läs uppgiften tillsammans innan ni börjar räkna. Bestäm vem som skriver. Alla i gruppen ska kunna förklara lösningen efteråt.',
    /* Diagnosens band är det enda som säger åt eleven att HOPPA ÖVER. Det är
       hela mätningen: ett tomrum som eleven kämpat sig förbi med en gissning
       ser ut som ett hål som inte finns, och då tas fel moment om. */
    Diagnos: 'Diagnosen sätter inget betyg — den tar reda på vad som behöver tas om. Svara på det du kan och hoppa över det du inte kan. Korta svar räcker.'
  };

  function ark(v, uppgifter, o) {
    const i = v.inst || {};
    const grupp = v.typ === 'Gruppuppgift';
    const namnrader = grupp ? Math.max(2, Math.min(6, Number(i.grupp) || 3)) : 1;
    const rad = '<div class="gurad"><span class="gunamn">Namn:</span><span class="gulinje"></span></div>';
    /* FORMNYCKELN. Arbetsbladet är en av förlagans fyra former, inte en femte:
       har någon uppgift en figur är det form 2 (figurspalt), annars form 1
       (radbunden). Förr stod «ab» här — en nyckel ingen regel i blad.css känner
       — och bladet fick basvärdena i stället för formens egen sättning
       (radhöjder, bandets padding, figurspaltens bredd, figurhöjden).
       Gruppuppgiften behåller «gu»: den bär sin egen täthet i gruppark.css,
       fyra rutor med namnrader på ett A4, och det ÄR dess form.

       FORM 6 saknades. Förlagans sjätte form är «1 + 2 + 3»: basen, tvåans
       figurspalt OCH treans stegtabell på samma blad — tre former kostar höjd,
       och blad.css bär hela dess tätare sättning ([data-form="gu6"]: radhöjder,
       tabellens cellpadding, figurspaltens bredd, figurhöjden). Renderaren
       kunde aldrig nå den: ett blad med både figur och stegtabell fick gu2,
       som är satt för ETT figurtungt blad och spiller när tabellen läggs till.
       Samma sorts fel som «ab» var — en form som fanns i stilbladet men inte i
       nyckeln. */
    const harFigur = uppgifter.some(u => u && u.fig);
    const harSteg = uppgifter.some(u => u && u.stegtabell);
    const form = grupp ? 'gu' : (harFigur && harSteg ? 'gu6' : harFigur ? 'gu2' : 'gu1');
    return `<div class="gu" data-form="${form}">
      <div class="guhuv"><h1 class="gutitel">${esc(versal(v.moment || o.titel || ''))}</h1>${
        /* Bladet som hör till EN elev säger det överst. Hon ska veta att det är
           hennes, och läraren ska kunna dela ut rätt papper utan att läsa
           uppgifterna. */
        v.elev ? `<span class="gumottagare">${esc(v.elev)}</span>` : ''}</div>
      <div class="gutopp">${rad.repeat(namnrader)}</div>
      ${/* Nyckelfrågan bär ofta matematik ($x = -b/(2a)$) — den ska sättas,
             inte visas som dollartecken. Pappret gör det (escape_mixed), och
             skärmen ska lova gruppen samma sak. */''}
      <div class="guband">${esc(BAND[v.typ] || BAND.Arbetsblad)}${
        v.nyckelfraga ? ` <b>${mat(v.nyckelfraga)}</b>` : ''}</div>
      ${uppgifter.map((u, k) => kort(u, k, !!i.illustration)).join('')}
    </div>`;
  }

  /* ── Anteckningar: lärarens eget stödpapper ────────
     Femte dokumenttypen, och den enda som inte är elevmaterial. Inga
     uppgifter, inga brickor, inga ifyllnadsrader — bara rubriker och löptext,
     satt så att en blick ner på pappret räcker för att hitta rätt rad. Formen
     är därför sin egen (data-form="an") och inte en variant av arbetsbladet:
     det som gör ett arbetsblad läsbart (brickor, svarsytor, täthet) är precis
     det som gör ett stödpapper oläsbart.

     `ant` är dokumentet servern skrev (app/notes_gen.py). Utan server finns
     inget — se blad.js anteckningarnaFor, som då sätter lärarens egen text på
     pappret i stället för att hitta på ett innehåll hon aldrig bett om. */
  function anteckningar(v, ant) {
    const a = ant || {};
    const meta = ['Anteckningar', v.klass, v.datum].filter(Boolean).join(' · ');
    const sekt = (a.sektioner || []).map(s => `<section class="ansekt">
      <h2 class="anrubrik">${esc(s.rubrik || '')}</h2>
      ${(s.stycken || []).map(p => `<p class="anstycke">${mat(p)}</p>`).join('')}
      ${(s.punkter || []).length ? `<ul class="anpunkter">${
        s.punkter.map(p => `<li>${mat(p)}</li>`).join('')}</ul>` : ''}
    </section>`).join('');
    const kom = (a.kom_ihag || []).length
      ? `<div class="ankom"><b class="ankomrub">Kom ihåg</b>${
          a.kom_ihag.map(k => `<p>${mat(k)}</p>`).join('')}</div>`
      : '';
    return `<div class="gu" data-form="an">
      <div class="anhuv"><h1 class="antitel">${esc(a.titel || versal(v.moment || ''))}</h1>
      <p class="anmeta">${esc(meta)}</p></div>
      ${sekt}${kom}
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
    /* Deluppgifternas poäng är provets EGNA, inte totalen delad på antalet.
       Jämnt fördelat blev «2 p» på en deluppgift som ger 1 och «2 p» på en som
       ger 3 — och det är poängen eleven planerar sin tid efter. Prototypens
       uppgifter saknar delp; då står den gamla uppskattningen kvar. */
    const delpoang = k => (u.delp && u.delp[k] != null
      ? u.delp[k] : Math.max(1, Math.round(u.p / u.del.length)));
    const del = u.del && u.del.length
      ? `<ul class="prdel" data-avdelad="">${u.del.map((d, k) => `<li><i>${'abcdef'[k]})</i><span>${mat(d)}</span><span class="prpo">${delpoang(k)} p</span></li>`).join('')}</ul>` : '';
    /* FIGUREN. Provets uppgift kan bära en ritad figur (exam_spec figur) — en
       graf, en triangel, en enhetscirkel — och den ritas i PDF:en av
       exam_figures. På skärmarket saknades den helt: uppgiften hänvisade till
       «figuren nedan» och där fanns ingen. Förlagans provblad har den i .prfig
       med sin bildtext under. */
    const figur = u.fig
      ? `<div class="prfig" data-vantar="" data-figur="${attr(JSON.stringify(u.fig))}"></div>`
        + (u.figkap ? `<p class="prfigkap">${mat(u.figkap)}</p>` : '')
      : '';
    /* SVARET står alltid i provet — på båda delarna, på varje uppgift. Förr
       hängde raden på u.ut === 'kort', och en uppgift som saknade den märkningen
       blev en fråga utan svarsplats mitt bland två som hade det. Alternativ
       (kryssrutor) och deluppgifter bär sin egen plats. */
    const behoverRad = !u.alt && !(u.del && u.del.length) && !u.rutor;
    /* Enheten står EFTER linjen på provet, som i förlagan: «………… laddpunkter/år».
       Kryssrutorna ersätter raden helt — den som kryssar skriver inte. */
    const svarsrad = u.rutor
      ? `<div class="prsvar"><b>${esc(u.rutor.etikett)}:</b><span class="gurutor">${
          (u.rutor.val || []).map(v => `<span class="guruta">${mat(v)}</span>`).join('')}</span></div>`
      : behoverRad
        ? `<div class="prsvar"><span class="prlinje"></span>${
            u.enhet ? `<span class="prenhet">${esc(u.enhet)}</span>` : ''}</div>`
        : '';
    /* REDOVISNINGEN görs aldrig i provet, alltid på separat lösblad. Uppgifter
       som kräver en redovisad lösning märks i marginalen under numret — samma
       plats som poängen, för båda avgörs innan man läst uppgiften. */
    const losblad = !u.alt && u.ut !== 'kort' ? '<span class="prlosblad">lösblad</span>' : '';
    /* Marginalen bär ETT format. «(totalt 3 p)» bredvid «1 p» läste sig som två
       olika fält; att poängen är en summa framgår av deluppgifternas egna. */
    const varde = `${u.p} p`;
    const former = tabell(u.tabell, 'prtab') + stegtabell(u.stegtabell);
    return `<div class="pruppg">
      <span class="prnr">${u.nr}.<span class="prvarde">${varde}</span>${losblad}</span>
      <div><p class="prtext">${mat(u.t)}</p>${alt}${del}${former}${figur}${svarsrad}</div>
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
  /* ── Kommenterad elevlösning (förlagans lo4) ──────
     Samma uppgift löst två eller tre gånger, i stigande ordning, med domen
     INNE i det parti den gäller — inte i en lista under. Det är gränsen mellan
     poängen som är svår att dra, och den syns bara när lösningarna står
     bredvid varandra. Lärarens papper: eleven ser dem aldrig. */
  /* Partiets poäng är en TRIPPEL (E, C, A) — samma språk som resten av
     dokumentet, se exam_spec.Parti. Den lästes här som ett ensamt tal, och i
     JavaScript är `0 + [1,0,0]` inte 1 utan strängen «01,0,0»: bedömningen
     tryckte «+1,0,0 p» i marginalen och «01,0,0 av 2 poäng» i huvudet, medan
     designsidans lo4 visar «+1 p» och «2 av 2 poäng · full pott». Prototypens
     egna facit bär ett tal, serverns prov en trippel — båda ska räknas. */
  const partipoang = p => (Array.isArray(p.poang)
    ? p.poang.reduce((a, x) => a + (Number(x) || 0), 0)
    : Number(p.poang) || 0);

  function elevlosningar(u) {
    if (!u.elever || !u.elever.length) return '';
    return u.elever.map(e => {
      const total = (e.partier || []).reduce((a, p) => a + partipoang(p), 0);
      const partier = (e.partier || []).map(p => `<div class="loparti"${partipoang(p) ? '' : ' data-utan'}>${
        (p.rader || []).map(r => `<div class="loskannrad">${mat(r)}</div>`).join('')
      }<div class="lodom"><i${partipoang(p) ? '' : ' data-utan'}>${partipoang(p) ? '+' : ''}${partipoang(p)} p</i><p>${mat(p.dom)}</p></div></div>`).join('');
      const full = total >= (u.p || 0) && total > 0;
      return `<div class="loelev"><b>${esc(e.etikett)}</b><span${
        total ? (full ? ' data-full' : '') : ' data-utan'}>${total} av ${u.p} poäng${
        full ? ' · full pott' : ''}</span></div><div class="loskann">${partier}</div>`;
    }).join('');
  }

  function losVag(u) {
    return `<div class="pruppg">
      <span class="prnr">${u.nr}.<span class="prvarde">${u.p} p</span></span>
      <div><p class="prtext">${mat(u.t)}</p>
        <ul class="lovag">${(u.vag || []).map(s => `<li><span class="losteg">${mat(s[0])}<em>${esc(s[1])}</em></span></li>`).join('')}</ul>
        <div class="losvar"><b class="losetikett">Svar</b><span>${mat(u.f)}</span></div>
        ${elevlosningar(u)}
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

  return { mat, ark, arkfacit, anteckningar, provforsatt, provblad, losning, BOKSTAV };
})();
