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
  /* ── Tomraderna ──
     Modellens radbrytningar SKA synas: läraren bad om «A:» och «B:» på var sin
     rad och fick det (white-space:pre-line i blad.css och prov.css). Men den
     lagrade texten bär ofta tre, fyra eller fem radbrytningar i rad — «… Endast
     svar krävs.\n\n\nA: …\n\n\nB: …» — och varje extra tomrad är 24 px höjd.
     Fyra uppgifter växte då förbi bladkanten en och en, och delningen gav ett
     papper per uppgift. En tom rad är avstånd; tre är ett mätfel.

     Kollapsas vid RENDERING, aldrig i lagringen — texten läraren godkände rörs
     inte, och LaTeX-vägen gör ändå ett enda stycke av flera tomrader. Görs per
     TEXTBIT och aldrig inuti $…$: samma delning som mat() gör, för en formel
     som råkar bära radbrytningar är TeX-källa och inte sättning. */
  const luft = s => String(s == null ? '' : s)
    .split('$')
    .map((bit, i) => (i % 2 ? bit
      : bit.replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n')))
    .join('$')
    .replace(/^\s+/, '').replace(/\s+$/, '');
  /* Uppgiftstext: tomraderna först, matematiken sedan. */
  const brodtext = s => mat(luft(s));
  const BOKSTAV = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'];
  const versal = s => String(s || '').charAt(0).toUpperCase() + String(s || '').slice(1);

  /* ── KORT REFERENS ─────────────────────────────────
     Facit läses BREDVID uppgiftsarket, aldrig i stället för det — läraren har
     båda pappren i handen. Att trycka hela uppgiftstexten en gång till på facit
     var därför bara text att leta förbi: «Beräkna utan räknare. Gruppen ska
     enas om ett gemensamt svar på varje uttryck innan ni skriver ner det.
     A: … B: …» fyllde tre rader innan svaret ens började.

     Kvar blir det som IDENTIFIERAR uppgiften: brickan (som står i marginalen
     ändå) och det matematiska innehållet. Instruktionsprosan mitt i texten —
     arbetsordningen, hur man redovisar, vem som skriver — hör till elevens
     papper och kastas här.

     Reglerna, i ordning:
       1. Meningar som bär matematik ($…$) behålls: det är dem uppgiften
          handlar om.
       2. Den FÖRSTA meningen behålls alltid — det är där det imperativa verbet
          står («Bestäm arean.»), och utan den vet man inte vad som frågas.
       3. Allt däremellan faller.
       4. Resten kortas till TAK tecken, aldrig mitt i en formel.
     Föll något bort sätts «…» sist, så att det syns att texten är beskuren.

     Klipps ALDRIG inuti $…$: delningen görs på hela strängen, precis som mat()
     gör, och en formel tas med hel eller inte alls. En halv formel är obalanserade
     dollartecken, och då sätter mat() resten av arket som matematik. */
  const REF_TAK = 80;
  /* Meningsslut i den icke-matematiska delen. Punkt efter en ensam versal
     («A. ») är en bricka, inte ett meningsslut — men den vanliga formen på ett
     sånt led är «A: …», så det räcker att kräva blanksteg eller strängslut. */
  const MENING = /([^.!?]*[.!?]+)(?=\s|$)|([^.!?]+)$/g;
  function meningar(text) {
    /* Bitarna växlar text/matematik: jämnt index är text, udda är formel.
       Meningarna får bara brytas i textbitarna. */
    const bitar = String(text == null ? '' : text).split('$');
    const ut = [];
    let nu = '';
    bitar.forEach((bit, i) => {
      if (i % 2) { nu += '$' + bit + '$'; return; }
      const delar = String(bit).match(MENING) || [bit];
      delar.forEach((d, k) => {
        nu += d;
        /* Sista biten i en textdel fortsätter in i nästa formel — den avslutar
           bara meningen om den själv slutade på skiljetecken. */
        if (k < delar.length - 1 || /[.!?]\s*$/.test(d)) { ut.push(nu); nu = ''; }
      });
    });
    if (nu.trim()) ut.push(nu);
    return ut.filter(m => m.trim());
  }
  function kortref(text, tak) {
    const alla = meningar(text);
    if (alla.length < 2) return klipp(alla.join('') || String(text || ''), tak);
    /* Bär INGEN mening matematik finns ingenting att ankra i — då är prosan
       uppgiften («Två elever räknar olika och får olika svar. Avgör vem som har
       rätt.») och taket får sköta kortandet ensamt. Filtret slår bara till när
       det finns matematik att behålla i stället. */
    /* Meningarna bär sitt eget inledande blanksteg — de fogas därför ihop utan
       skarv, och bara där en mening HOPPATS ÖVER behövs ett mellanrum. */
    if (!alla.some(m => m.indexOf('$') >= 0)) return klipp(alla.join(''), tak);
    const valda = alla.filter((m, i) => i === 0 || m.indexOf('$') >= 0);
    const kortad = klipp(valda.join(' ').replace(/ {2,}/g, ' ').trim(), tak);
    return valda.length < alla.length && !/…$/.test(kortad) ? kortad + ' …' : kortad;
  }
  /* Klipper på ordgräns i en textbit; en formel tas med hel eller lämnas. */
  function klipp(text, tak) {
    const gr = Math.max(20, Number(tak) || REF_TAK);
    const s = String(text == null ? '' : text).trim();
    if (s.replace(/\$/g, '').length <= gr) return s;
    const bitar = s.split('$');
    let ut = '';
    let langd = 0;
    for (let i = 0; i < bitar.length; i++) {
      const bit = bitar[i];
      if (i % 2) {
        if (langd + bit.length > gr && ut.trim()) break;
        ut += '$' + bit + '$';
        langd += bit.length;
        continue;
      }
      if (langd + bit.length <= gr) { ut += bit; langd += bit.length; continue; }
      const rest = bit.slice(0, Math.max(0, gr - langd));
      const brott = rest.lastIndexOf(' ');
      ut += brott > 0 ? rest.slice(0, brott) : rest;
      break;
    }
    return ut.replace(/[\s,;:]+$/, '') + ' …';
  }
  /* Facitets uppgiftsrad: brickan bär numret, referensen bär matematiken.
     Tomraderna kollapsas först — .prtext bär pre-line även här, och ett facit
     där varje referens drar med sig tre tomrader fyller bladet med ingenting. */
  const ref = (t, tak) => mat(kortref(luft(t), tak));

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
  /* ── ETIKETTEN ÄR MATEMATIK, PRECIS SOM FRÅGAN ──
     Ledet framför en linje eller en kryssruterad bär TeX inom dollartecken
     («$\left(\frac{1}{8}\right)^{2} =$») — det är samma sträng LaTeX-vägen
     sätter i matteläge (exam_latex escape_mixed). esc() tryckte den ordagrant,
     så läraren fick rå LaTeX på skärmen medan PDF:en satte bråket. Samma fynd
     som enheten på svarsraden gjorde en gång, i en annan ruta.

     Kolonet hör till SÄTTNINGEN och inte till texten: slutar etiketten redan
     på «:», «=», «?» eller «$» sätts inget till. Spegel av exam_latex._FALT_SLUT
     — utan den läste raden «$…=$:», alltså ett kolon efter likhetstecknet. */
  const FALT_SLUT = /[:=?$]$/;
  const faltnamn = e => {
    const raw = String(e == null ? '' : e).trim();
    return mat(raw) + (FALT_SLUT.test(raw) ? '' : ':');
  };
  /* Kryssruteraden: en rad att fylla i, inte en flervalsfråga. Etiketten står
     där svarsradens namn står, rutorna där linjen skulle gå. */
  function rutor(r) {
    if (!r || !r.val) return '';
    return `<div class="gurad"><span class="gunamn">${faltnamn(r.etikett)}</span>`
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
    return f.map(e => `<div class="gurad"><span class="gunamn">${faltnamn(e)}</span>`
      + '<span class="gulinje"></span></div>').join('');
  }
  /* Enheten på svarsraden: ledet före linjen, enheten efter den.

     ENHETEN ÄR MATEMATIK och sätts som all annan matematik på pappret. Fältet
     bär TeX inom dollartecken — «cm$^2$», «$f'(x) =$» (exam_spec.enhet,
     samma sträng som LaTeX-mallen sätter i matteläge via escape_mixed) — och
     esc() tryckte den ordagrant: läraren fick «cm$^2$» med dollartecken och
     allt på svarsraden i förhandsvisningen medan PDF:en satte cm². mat() är
     samma delning som resten av bladet gör, så enheten renderas av KaTeX. */
  const enhetHtml = e => mat(e);
  function svarsradEnhet(enhet) {
    return `<div class="gurad gusvarsrad"><span class="gunamn">Svar:</span>`
      + `<span class="gulinje"></span>${enhet ? `<span class="prenhet">${enhetHtml(enhet)}</span>` : ''}</div>`;
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
  /* `siffra`: brickorna är 1, 2, 3 … Gruppuppgiften fick dem 2026-08-20 och
     ARBETSBLADET 2026-08-25 (lärarens val, efter det skarpa potensbladet) —
     skälet är detsamma på båda: deluppgifterna heter a) b) c), och bokstäver i
     marginalen bredvid dem är två bokstavsserier på samma papper. Just det som
     motiverade bokstäverna motiverar alltså att de går.
     Serien tog dessutom slut: BOKSTAV har åtta poster, och det skarpa bladet
     hade femton uppgifter — brickorna löd A…H och sedan 9, 10, 11. Halva
     bladet numrerade redan i siffror.
     Diagnosen står utanför och behåller sina bokstäver: dess rättningsblad
     paras mot brickan, och den formen är dess egen. */
  function kort(u, i, siffra) {
    const bricka = siffra ? String(i + 1) : (BOKSTAV[i] || String(i + 1));
    const alt = u.alt
      ? `<ul class="gudel guval">${u.alt.map((a, k) => `<li><i>${BOKSTAV[k]}.</i> ${mat(a)}</li>`).join('')}</ul>` : '';
    const del = u.del && u.del.length
      ? `<ul class="gudel">${u.del.map((d, k) => `<li>${'abcdef'[k]}) ${brodtext(d)}</li>`).join('')}</ul>` : '';
    /* Bildplatsen. `u.bild` är uppgiftens egen hänvisning till bildunderlaget
       (exam_spec: ett 1-baserat index bland de uppladdade bilderna). Den
       mappades till arket men ritades aldrig — PDF:en satte bilden och skärmen
       visade ingenting, så uppgiften hänvisade till en bild som inte fanns.
       Rutan är dessutom den yta lärarens egen bild landar i (blad.js rita,
       v.bilder).

       `data-bild` är rutans HANDTAG: blad.js hämtar sidan ur underlaget och
       lägger den här (Blad.underlag). Texten nedanför är vad som står kvar när
       dokumentet inte bär något underlag att hämta ur.

       `u.scen` är uppgiftens BILDBESTÄLLNING (exam_spec.Scen). LÄRARENS BESLUT
       2026-08-25: står «Plats för illustration» på ska platshållaren innehålla
       själva bildprompten, så att hon kan kopiera den till sitt
       ChatGPT-projekt, få en bild och släppa in den. Samma `scenruta` som
       provet, inte en kopia: plåtväljaren, «Kopiera scen» och släppytan sitter
       delegerade på `.prscen` och `[data-plat]` i plan.js, och en egen markup
       här hade varit två system att hålla i synk för samma sak.

       ── EN PLATSHÅLLARE UTAN PROMPT FINNS INTE ──
       LÄRARENS DOM samma kväll, om det skarpa potensbladet: tolv av femton
       uppgifter var rena räkneuppgifter, SCEN_REGEL förbjuder scen på dem, och
       varje sådan uppgift fick ändå en tom ruta med «plats för illustration».
       Tolv rutor som lovar en bild ingen har beställt, 110 px var — nästan två
       hela sidor papper. Rutan ritas därför bara när uppgiften bär en scen att
       måla efter; krysset styr vad MODELLEN får beställa (exam_gen BILD_PA /
       BILD_AV), inte om bladet ska reservera tomrum.

       Ingen migrering behövs: ett gammalt papper utan `scen` tappar bara en
       ruta som ändå aldrig gick att fylla. LaTeX-vägen har aldrig reserverat
       ytan — arbetsblad.tex.j2 sätter bilden bara när `u.bild_fil` finns. */
    const fig = u.fig ? ''
      : u.bild ? `<div class="gufigur guplats" data-bild="${Number(u.bild)}" style="height:110px"><span class="gufigtext">bild ${Number(u.bild)} ur underlaget — läggs in i canvas</span></div>`
        : u.scen ? scenruta(u) : '';
    /* Notisen står EFTER uppgiftens former och före svarsytan — samma plats som
       \notisruta har i mallarna (arbetsblad.tex.j2, gruppuppgift.tex.j2). */
    const notis = u.notis ? `<p class="gunotis">${brodtext(u.notis)}</p>` : '';
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
      ? `<div class="gutva"><div><p class="gufraga">${brodtext(u.t)}</p>${alt}${del}${former}${notis}${svarsyta(u)}</div>`
        + `<div>${egen}</div></div>`
      : `<p class="gufraga">${brodtext(u.t)}</p>${alt}${del}${former}${fig}${notis}${svarsyta(u)}`;
    return `<div class="gukort" data-ut="${u.ut || 'rakna'}">
      <span class="gubricka">${bricka}</span>
      ${kropp}
    </div>`;
  }

  /* Instruktionsbandet säger hur man arbetar — inte vad uppgifterna handlar om.
     Det står i uppgifterna.

     MALLEN ÄR RESERVEN, INTE SANNINGEN. Texterna nedan var hela bandet en
     gång, och då var rutan appens: läraren pekade på den i granskningen, bad
     att en mening skulle bort, och ingenting hände på pappret — det fanns
     ingen text i dokumentets JSON att skriva om. Nu äger dokumentet bandet
     (exam_spec.instruktion), och de här texterna gäller bara när fältet är
     tomt: gamla papper, prototypens egna och allt som skrevs innan fältet
     fanns ska se likadana ut som förut. */
  const BAND = {
    Arbetsblad: 'Skriv svaret på svarsraden där det står «Svar». De uppgifter som ska redovisas är märkta — skriv uppgiftens nummer överst på lösbladet. Visa hur du räknar, inte bara svaret.',
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
    /* Dokumentets eget band vinner. Nyckelfrågan står KVAR som eget fält och
       sätts fet efter texten — den är momentets metodregel, och läraren ska
       kunna byta den utan att röra arbetsregeln (samma delning som i PDF:en,
       exam_latex._grupp_vy). */
    const bandtext = (v.instruktion || '').trim();
    /* RUBRIKEN ÄR DOKUMENTETS. `titel` sparades ur serverns svar men ritades
       aldrig: pappret satte alltid momentets namn, så «döp om det till
       Repetition inför provet» var ett önskemål utan verkan — modellen skrev
       fältet, appen läste det inte. Tomt fält betyder som alltid «appens val
       gäller», och då står momentet där precis som förut. Fortsättningsbladets
       stämpelrad läser första bladets rubrik (blad.js delaArk) och följer
       därför med av sig själv. */
    const rubrik = (v.titel || '').trim() || versal(v.moment || o.titel || '');
    const harFigur = uppgifter.some(u => u && u.fig);
    const harSteg = uppgifter.some(u => u && u.stegtabell);
    const form = grupp ? 'gu' : (harFigur && harSteg ? 'gu6' : harFigur ? 'gu2' : 'gu1');
    return `<div class="gu" data-form="${form}">
      <div class="guhuv"><h1 class="gutitel">${esc(rubrik)}</h1>${
        /* Bladet som hör till EN elev säger det överst. Hon ska veta att det är
           hennes, och läraren ska kunna dela ut rätt papper utan att läsa
           uppgifterna. */
        v.elev ? `<span class="gumottagare">${esc(v.elev)}</span>` : ''}</div>
      <div class="gutopp">${rad.repeat(namnrader)}</div>
      ${/* Nyckelfrågan bär ofta matematik ($x = -b/(2a)$) — den ska sättas,
             inte visas som dollartecken. Pappret gör det (escape_mixed), och
             skärmen ska lova gruppen samma sak. */''}
      ${/* `data-egen` är ÄGARSKAPSTECKNET, och det behövs: blad.js grupphuvud
             klistrar annars på redovisningslöftet en gång till, och den mening
             läraren just strukit ur bandet kommer tillbaka. Vakten där var
             `/redovisas/i` — den räcker inte, för ett band hon skrivit om kan
             mycket väl sakna ordet. */''}
      <div class="guband"${bandtext ? ' data-egen' : ''}>${esc(bandtext || BAND[v.typ] || BAND.Arbetsblad)}${
        v.nyckelfraga ? ` <b>${mat(v.nyckelfraga)}</b>` : ''}</div>
      ${uppgifter.map((u, k) => kort(u, k, v.typ !== 'Diagnos')).join('')}
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
    /* Facit numrerar som uppgiftsarket: siffror på arbetsblad och
       gruppuppgift, bokstäver på diagnosen — annars pekar «1.» och «A.» på
       samma uppgift på två papper. */
    const siffra = v.typ !== 'Diagnos';
    /* Arbetsbladets facit bär inga poäng (lärarens dom 2026-08-26): bladet är
       övning utan betygsgränser, så «3 p» vid svaret är en siffra som inte
       delas ut någonstans. PDF:ns facitband skriver redan tomt där
       (arbetsblad.tex.j2, facitdelen) — skärmen ska lova samma sak.
       Gruppuppgiften behåller poängen: dess facit läses MED bedömningen. */
    const poang = u => v.typ === 'Arbetsblad' ? '' : `<span class="prvarde">${u.p} p</span>`;
    const post = (u, k) => `<div class="pruppg">
      <span class="prnr">${siffra ? k + 1 : (BOKSTAV[k] || k + 1)}.${poang(u)}</span>
      <div><p class="prtext" data-ref="">${ref(u.t)}</p>
        ${losvar(u)}${losvag(u)}
      </div></div>`;
    /* data-brytbar: facit är lika långt som sina lösningar, och ett svar på
       flera meningar sköt D-uppgiften ut under arkets nederkant. paginera
       (blad.js) mäter och flyttar det som inte ryms till ett nytt blad med
       samma huvud — precis som provet och lösningsförslaget. */
    /* Ledtexten är borta. Den sa två saker läraren redan vet — att poängen står
       vid steget den delas ut på, och att svar utan uträkning inte ger full
       poäng — och båda syns i sättningen: poängen STÅR vid steget. Två rader
       hon läser förbi varje gång är två rader svaren kunde ha haft. */
    return `<div class="ark" data-form="fa" data-brytbar="">
      <div class="lohuvud"><b>Facit</b><span>${esc(versal(v.moment || ''))}</span></div>
      <h1 class="lotitel">Svar och lösningsgång</h1>
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
    /* FIGUREN INNE I DELUPPGIFTEN. Förlagans 1(a) har grafen där frågan står,
       inte ovanför hela kortsvarssamlingen (exam_spec.SubItem.figur). Samma
       ruta som uppgiftens .prfig, bara ett steg in. */
    const delfigur = k => {
      const f = (u.delfig || [])[k];
      if (f) return `<div class="prfig" data-vantar="" data-figur="${attr(JSON.stringify(f))}"></div>`;
      const b = (u.delbild || [])[k];
      return b ? `<div class="prbild gufigur" data-bild="${Number(b)}" style="min-height:110px"><span class="gufigtext">bild ${Number(b)} ur underlaget — läggs in i canvas</span></div>` : '';
    };
    /* EN SVARSRAD PER DELUPPGIFT på kortsvaren — pappret sätter \svarsrad{Svar:}
       under varje a), b), c) (förlagans uppgift 1), och skärmen visade ingen
       alls: `behoverRad` nedan stänger av uppgiftens egen rad så fort det finns
       deluppgifter, och deluppgifterna hade ingen. Förhandsvisningen lovade
       alltså ett papper utan svarsplats. Bara kortsvar får raden; det som
       redovisas på lösblad ska inte ha en linje som inbjuder till motsatsen. */
    const delsvar = () => (u.ut === 'kort'
      ? '<div class="prsvar"><b class="prsvarnamn">Svar:</b><span class="prlinje"></span></div>' : '');
    const del = u.del && u.del.length
      ? `<ul class="prdel" data-avdelad="">${u.del.map((d, k) => `<li><i>${'abcdef'[k]})</i><span>${brodtext(d)}</span><span class="prpo">${delpoang(k)} p</span>${delfigur(k)}${delsvar()}</li>`).join('')}</ul>` : '';
    /* FIGUREN. Provets uppgift kan bära en ritad figur (exam_spec figur) — en
       graf, en triangel, en enhetscirkel — och den ritas i PDF:en av
       exam_figures. På skärmarket saknades den helt: uppgiften hänvisade till
       «figuren nedan» och där fanns ingen. Förlagans provblad har den i .prfig
       med sin bildtext under. */
    const figur = u.fig
      ? `<div class="prfig" data-vantar="" data-figur="${attr(JSON.stringify(u.fig))}"></div>`
        + (u.figkap ? `<p class="prfigkap">${mat(u.figkap)}</p>` : '')
      /* Uppgiftens bild ur underlaget (exam_spec: index bland de uppladdade
         bilderna). Den nådde arket men ritades aldrig, så provet hänvisade till
         en bild som bara fanns i PDF:en. Rutan är också den yta lärarens egen
         bild landar i (blad.js rita, v.bilder). `data-bild` är handtaget
         blad.js hämtar sidan till — se motsvarande ruta i `kort` ovan. */
      : u.bild
        ? `<div class="prbild gufigur" data-bild="${Number(u.bild)}" style="min-height:110px"><span class="gufigtext">bild ${Number(u.bild)} ur underlaget — läggs in i canvas</span></div>`
        : '';
    /* LEDTRÅDEN, INTE EN LÅDA. Provets mall är sedan lärarens förlaga kom in
       exam-klassen, och där är notisen en KURSIV rad under frågan («Tips: Gör
       en skiss och kalla bredden för x cm.») — ingen ram. Skärmen ritade en
       inramad ruta, och då lovade förhandsvisningen en form pappret inte har.
       Arbetsbladets .gunotis är kvar som ruta: det är dess egen form. */
    const notis = u.notis ? `<p class="prtips">${brodtext(u.notis)}</p>` : '';
    /* ── KRAVET AVGÖR SVARSRADEN, INGET ANNAT ──────────
       LÄRARENS DOM (2026-08-22, om uppgift 7 på hennes prov): «Fullständig
       lösning krävs ⇒ eleven skriver på lösblad ⇒ INGEN svarsrad på
       provpappret. Svar: ____ finns BARA på uppgifter/deluppgifter med Endast
       svar krävs.»

       Här stod «SVARET står alltid i provet — på båda delarna, på varje
       uppgift», och villkoret var bara «ingen annan svarsplats finns». En
       A-uppgift som ber eleven UNDERSÖKA och FÖRKLARA fick då en tom linje
       under sig, och linjen säger «skriv svaret här» — alltså raka motsatsen
       till kravraden två rader ovanför. Två löften om samma uppgift, och det
       eleven ser sist är linjen.

       Samma regel i papprets ände: prov.tex.j2 sätter \svarsrad{Svar:} bara
       under `endast_svar` (exam_latex: typ == "rutin"), och de namngivna
       ifyllnadsraderna med den (exam_latex._enhet_vy). `delsvar` nedan bär
       redan villkoret för deluppgifterna. */
    const behoverRad = u.ut === 'kort' && !u.alt && !(u.del && u.del.length) && !u.rutor;
    /* Enheten står EFTER linjen på provet, som i förlagan: «………… laddpunkter/år».
       Kryssrutorna ersätter raden helt — den som kryssar skriver inte. */
    /* «Svar:» STÅR FRAMFÖR LINJEN. Pappret skriver den etiketten (förlagans
       \svarsrad{Svar:}); en naken linje på skärmen och en märkt på pappret är
       två olika löften om samma ruta. */
    const svarsrad = u.rutor
      ? `<div class="prsvar"><b>${faltnamn(u.rutor.etikett)}</b><span class="gurutor">${
          (u.rutor.val || []).map(v => `<span class="guruta">${mat(v)}</span>`).join('')}</span></div>`
      : behoverRad
        ? `<div class="prsvar"><b class="prsvarnamn">Svar:</b><span class="prlinje"></span>${
            u.enhet ? `<span class="prenhet">${enhetHtml(u.enhet)}</span>` : ''}</div>`
        : '';
    /* KRAVET STÅR SOM PÅ PAPPRET. Förlagan skriver «Endast svar krävs.» eller
       «Fullständig lösning krävs.» i kursiv på uppgiftens första rad — det är
       den raden eleven läser för att veta om svaret skrivs här eller lösningen
       på lösblad. Skärmen satte i stället ordet «lösblad» litet i marginalen,
       och sa alltså samma sak med andra ord på en annan plats. */
    const krav = `<p class="prkrav">${u.ut === 'kort'
      ? 'Endast svar krävs.' : 'Fullständig lösning krävs.'}</p>`;
    /* Marginalen bär ETT format. «(totalt 3 p)» bredvid «1 p» läste sig som två
       olika fält; att poängen är en summa framgår av deluppgifternas egna. */
    const varde = `${u.p} p`;
    const former = tabell(u.tabell, 'prtab') + stegtabell(u.stegtabell);
    return `<div class="pruppg">
      <span class="prnr">${u.nr}.<span class="prvarde">${varde}</span></span>
      <div>${krav}<p class="prtext">${brodtext(u.t)}</p>${alt}${del}${former}${scenruta(u)}${figur}${notis}${svarsrad}</div>
    </div>`;
  }
  /* ══════════ BILDSTÖDET PÅ SKÄRMEN ══════════
     LÄRARENS BESLUT: «Skit i nyckeln, ingen API. Prompt bara, så skapar jag
     bilden med min prenumeration.» Appen genererar alltså ingen bild. Rutan
     nedan har därför två lägen, och det är hela funktionen:

       TRÄFF   — en plåt ur hennes egen katalog (E:\\Bildstil) ligger redan
                 målad för begreppet. Den visas, och väljaren låter henne byta
                 till en annan eller ta bort den. Hennes val vinner alltid.
       INGEN   — SCENE-stycket står framme med «Kopiera scen» och ett
                 filnamnsförslag. Hon klistrar in stycket i sitt eget
                 ChatGPT-projekt (projektet lägger basprompten framför själv,
                 så BARA stycket kopieras), och släpper sedan den färdiga
                 bilden på rutan. Släppytan är samma väg som alla andra bilder
                 går (plan.js valjBild → v.bilder), inte en ny.

     Rutan bär `data-plat` = uppgiftens nummer. Klickarna sitter delegerade i
     plan.js; markup:en här är ren och ritas om vid varje omritning. */
  function scenruta(u) {
    const s = u.scen;
    if (!s) return '';
    /* Tom sträng är «läraren valde bort plåten» och är INTE samma sak som
       att ingen plåt fanns: då ska SCENE-stycket fram igen, för hon ska kunna
       måla en egen. `null`/saknad betyder «appen hittade ingen». */
    const plat = s.plat || '';
    if (plat) {
      /* INTE `loading="lazy"`. Plåten är inte en illustration bredvid texten
         — den är ett par hundra pixlar av arkets höjd, och höjden styr var
         pappret bryts (blad.js paginera). En lat bild laddas först när den
         råkar närma sig fönstret, alltså långt efter mätningen, och ark tre
         mättes utan sin bild så länge läraren inte hade rullat dit. Det som
         klipptes var uppgiften EFTER bilden (lärarens prov 2026-08-22). Ett
         prov bär två till fyra plåtar från den egna maskinen; de får hämtas
         direkt. */
      return `<div class="prbild gufigur prplat" data-plat="${u.nr}">
        <img src="/api/platar/${encodeURIComponent(plat)}" alt="" />
        <div class="prplatfot"><span class="prplatnamn">${esc(plat)}</span>
          <button type="button" class="prplatbyt" data-plat-byt="${u.nr}">Byt plåt</button>
          <button type="button" class="prplatbort" data-plat-bort="${u.nr}">Ta bort</button>
        </div></div>`;
    }
    return `<div class="prbild gufigur prscen" data-plat="${u.nr}">
      <p class="prscenrub">Bild att skapa — ${esc(s.begrepp || '')}</p>
      <pre class="prscentext">${esc(s.scene || '')}</pre>
      <div class="prplatfot"><span class="prplatnamn">${esc(s.filnamn || '')}</span>
        <button type="button" class="prscenkopiera" data-plat-kopiera="${u.nr}">Kopiera scen</button>
        <button type="button" class="prplatbyt" data-plat-byt="${u.nr}">Välj plåt</button>
      </div>
      <p class="prscenhint">Släpp bilden här när den är klar — eller klicka.</p>
    </div>`;
  }
  /* ══════════ FÖRSÄTTSBLADETS PORTRÄTT ══════════
     Försättsbladet slutar i en halv sida tomt papper under betygstabellen, och
     den ytan var husets ENDA bildplats utan beställning: varenda annan ruta bär
     ett SCENE-stycke, den här sa bara «plats för bild — läggs in i canvas».

     LÄRARENS ORD (2026-08-23): «den här vetenskapsmannen eller matematikern som
     kom på det provet handlar om … Fast en fin bild, lite dramatiskt så att de
     blir inspirerade av att klara av provet.» Dokumentet bär personen och
     stycket (exam_spec.Forsattsbild), och rutan visar dem på EXAKT samma sätt
     som uppgifternas scener: samma .prscen-markup, samma «Kopiera scen», samma
     släppyta. Ingen egen CSS och ingen andra sorts bildruta — hade porträttet
     fått sin egen form vore det två system att hålla i synk för samma sak.

     Nyckeln är 'forsatt' och inte ett uppgiftsnummer: bilden hör till
     DOKUMENTET, inte till en uppgift. Den är också nyckeln lärarens egen
     släppta bild landar under (blad.js markera → data-el="forsatt", v.bilder).

     Saknas fältet — prototypens papper, ett prov skrivet innan fältet fanns —
     står platshållaren kvar precis som förut. Ingen migrering. */
  function forsattsbild(v) {
    const f = (v || {}).forsattsbild;
    if (!f || !(f.scene || '').trim()) {
      return '<div class="prbild gufigur"><span class="gufigtext">plats för bild — läggs in i canvas</span></div>';
    }
    return `<div class="prbild gufigur prscen" data-plat="forsatt">
      <p class="prscenrub">Bild att skapa — ${esc(f.person || '')}</p>
      <pre class="prscentext">${esc(f.scene || '')}</pre>
      <div class="prplatfot">
        <button type="button" class="prscenkopiera" data-plat-kopiera="forsatt">Kopiera scen</button>
      </div>
      <p class="prscenhint">Släpp bilden här när den är klar — eller klicka.</p>
    </div>`;
  }
  /* Provets rubrik, med dokumentets egen först. Samma regel som arkets: skrev
     modellen en titel är det den som står på pappret, annars appens «Prov —
     momentet». blad.js planvalProv skriver om raden efter planeringen och
     följer samma ordning — annars fick titeln stå i en bildruta och försvinna i
     nästa. */
  const provtitel = v => (v.titel || '').trim()
    || `${v.variant === 'Omprov' ? 'Omprov' : 'Prov'} — ${versal(v.moment || '')}`;

  function provforsatt(v) {
    return `<div class="ark" data-form="pr1">
      ${huvud(v)}
      <h1 class="prtitel">${esc(provtitel(v))}</h1>
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
  /* Interna delnamn i löptext → papprets, EN gång. Kedjan B→A, C→B, D→C skjuter
     varje namn ett steg neråt, så en redan översatt text översätts en gång till
     och två delar smälter ihop: «Del A utan räknare. Del B med räknare.» blev
     «Del A … Del A …». Det händer på riktigt — granskningen skickar SKÄRMENS
     text till modellen, som svarar med papprets namn. «Del A» finns inte i det
     interna namnrummet (delarna heter B/C/D) och är därför den entydiga
     markören för att arbetet redan är gjort. Spegel av
     exam_latex._delnamn_visning — samma regel, annars säger skärm och PDF
     olika saker om samma prov. */
  const DELNAMN_REDAN = /\b[Dd]el\s+A\b/;
  const delnamnVisning = t => {
    const s = String(t || '');
    return DELNAMN_REDAN.test(s) ? s : s
      .replace(/\b([Dd]el)\s+B\b/g, '$1 A')
      .replace(/\b([Dd]el)\s+C\b/g, '$1 B')
      .replace(/\b([Dd]el)\s+D\b/g, '$1 C');
  };
  function provblad(v, uppgifter, del) {
    const medHjalp = del === 'C';
    /* HJÄLPMEDELSREGELN ÄR DOKUMENTETS (exam_spec.ExamDoc.hjalpmedel). Bandet
       var en hårdkodad mall per del, och därför hände ingenting när läraren bad
       om att räknare skulle tillåtas på del A: regeln fanns inte i dokumentets
       JSON, den fanns i den här strängen. Fältet nådde bara PDF:ens
       försättsblad (prov.tex.j2, Hjälpmedel-raden).

       Äger dokumentet regeln säger pappret den EN gång, och appen slutar
       påstå något eget: delnamnet står naket i huvudet i stället för «Del A ·
       utan digitala hjälpmedel», och provtabellens delrader tappar sina fraser
       (blad.js planvalProv). Två regler som kan säga emot varandra är värre än
       en — eleven vet inte vilken som gäller. Tomt fält, prototypens papper:
       mallen nedan, precis som förut. */
    /* Modellen skriver regeln med de INTERNA delnamnen (prompten säger
       Del B/Del C) — pappret räknar från A. Samma översättning som
       exam_latex._delnamn_visning, så skärm och PDF säger samma namn. */
    const hjalp = delnamnVisning((v.hjalpmedel || '').trim());
    /* ── OBS-RUTAN ÄR BORTA ────────────────────────────
       «Det framgår redan på försättsbladet vad som är tillåtet» (läraren,
       2026-08-22). Rutan upprepade hjälpmedelsregeln, redovisningsregeln och
       lösbladsregeln överst på varje dels första ark — allt tre står redan på
       försättsbladet (prov.tex.j2: Hjälpmedel-raden, inlämningsraden och
       Instruktioner-listan), och varje uppgift bär dessutom sin egen kravrad
       «Endast svar krävs» / «Fullständig lösning krävs». En regel som står två
       gånger är en regel som kan glida isär, och rutan tog dessutom plats som
       en uppgift kunde haft. PDF:en har aldrig haft den.

       Delnamnet i sidhuvudet står kvar: det är vilket papper man håller i,
       inte en regel. */
    const etikett = del === '-' ? ''
      : hjalp ? DELNAMN[del]
        : `${DELNAMN[del]} · ${medHjalp ? 'räknare och digitala hjälpmedel' : 'utan digitala hjälpmedel'}`;
    return `<div class="ark" data-form="pr1${del.toLowerCase()}" data-brytbar="">
      ${huvud(v, etikett)}${uppgifter.map(provuppg).join('')}
    </div>`;
  }

  /* ── Lösningsförslaget ───────────────────────────── */

  /* ── SVARSRADEN: ALDRIG TOM, ALDRIG DUBBEL ENHET ──
     Två fynd ur lärarens granskning av det skarpa provet (2026-08-23), båda
     på samma rad:

     1. «Svar» stod tomt på uppgift 2 och 6. Det är uppgifter med
        deluppgifter: föräldern bär ingen egen losning (exam_spec kräver att
        den ligger på deluppgifterna), så `f` är tom sträng — och raden
        ritades ändå, med etikett och allt. Deluppgifternas svar finns i
        `vag` och ritas nedanför; den tomma raden är ren lögn och ska bort.
     2. «$T(8) = 0{,}1\cdot 256 = 25{,}6$ mm.» följt av ett kursivt «mm».
        Facittexten bar enheten OCH fältet `enhet` sattes ut efter den.
        Prompten säger numera att losning inte ska bära enheten när fältet
        finns (exam_gen.INSTRUCTION), men alla prov som redan ligger i basen
        gör det — och de skrivs ut i morgon. Därför mäts det här också: slutar
        svaret på enheten sätts den inte ut en gång till.

     Punkten sist i facittexten hör inte till enheten och räknas bort innan
     jämförelsen; «25,6 mm.» slutar med «mm». */
  const ENHET_SLUT = (f, enhet) => {
    const e = String(enhet || '').replace(/\$/g, '').trim();
    const s = String(f || '').replace(/\$/g, '').replace(/[.\s]+$/, '');
    return !!e && s.toLowerCase().endsWith(e.toLowerCase());
  };
  function losvar(u) {
    if (!u.f) return '';
    return `<div class="losvar"><b class="losetikett">Svar</b><span>${mat(u.f)}</span>${
      u.enhet && !ENHET_SLUT(u.f, u.enhet) ? `<em>${enhetHtml(u.enhet)}</em>` : ''}</div>`;
  }
  /* Vägen till svaret — och på en uppgift med deluppgifter ÄR den svaret:
     `vag` bär «a) …», «b) …» med sin poäng (plan.js franProv). */
  const losvag = u => (u.vag && u.vag.length
    ? `<ul class="lovag">${u.vag.map(s => `<li><span class="losteg">${mat(s[0])}<em>${esc(s[1])}</em></span></li>`).join('')}</ul>`
    : '');

  /* ── POÄNGTRAPPAN ──
     Nationella provets bedömningsanvisning: en rad per poäng, med nivån och
     vad som ger den. Lärarens dom 2026-08-23: «på fleruppgifter framgår inte
     vad varje poäng ges för.»

     Spegel av app/exam_spec.bedomningsrader — samma delning, samma tolerans
     mot de gamla dokumentens enradiga kommaform, för skärmen och PDF:en ska
     visa samma trappa. Ändras den ena ska den andra ändras. */
  const BEDSTEG = /^\+\s*(\d+)\s*([ECA])\b[\s.:—-]*([\s\S]*)$/;
  const BEDNOT = /^(vanligt fel|kommentar|obs)\b/i;
  function trappsteg(bed) {
    return String(bed || '').split(/\n|,\s*(?=\+\s*\d)|;\s*(?=vanligt fel|kommentar)/i)
      .map(s => s.trim()).filter(Boolean)
      .map(s => {
        const m = s.match(BEDSTEG);
        if (m) return { niva: `+${m[1]} ${m[2]}`, krav: m[3].trim() };
        return { niva: '', krav: BEDNOT.test(s) ? s[0].toUpperCase() + s.slice(1) : s };
      });
  }
  /* En trappa för hela uppgiften: förälderns egen, eller deluppgifternas i
     ordning med sin bokstav framför (en uppgift med deluppgifter har ingen
     egen bedömning — poängen ligger på a), b), c)). */
  function trapprader(u) {
    const rader = [];
    (u.beddel || []).forEach((b, k) => trappsteg(b).forEach(
      r => rader.push({ ...r, krav: `${BOKSTAVER[k] || k + 1}) ${r.krav}` })));
    if (!rader.length) trappsteg(u.bed).forEach(r => rader.push(r));
    return rader;
  }
  const trappaHtml = rader => (rader.length
    ? `<ul class="lotrappa">${rader.map(r => `<li${r.niva ? '' : ' data-not'}>${
      r.niva ? `<i>${esc(r.niva)}</i>` : '<i></i>'}<span>${mat(r.krav)}</span></li>`).join('')}</ul>`
    : '');
  const BOKSTAVER = 'abcdefghijkl';

  /* ══════════ BEDÖMNINGSTABELLEN ══════════
     Lärarens beställning 2026-08-23, ordagrant i sak: «per uppgift och per
     deluppgift som bär poäng — översta raden är facit med full pott och hela
     trappan bredvid, därunder en elevlösning per lägre steg med vilka poäng
     den fick och varför den inte fick nästa.»

     Formen är därför en TVÅSPALTSTABELL och inte två block under varandra:
     poängen ska stå BREDVID det papper de gäller, inte under. Läraren läser
     radvis — «så här ser 1 p ut, så här ser 2 p ut» — och det är den
     jämförelsen hela anvisningen finns för.

     Vänsterspalten är faksimil som förut (.loskann, handskriften); den bär
     facitraden i rak stil och elevraderna i skrivstil, för den ena är tryckt
     och de andra är påhittade elevpapper.

     FALLBACK: saknas elevlösningar (ett gammalt papper, eller en uppgift där
     bedömningspassets anrop föll — exam_gen.bedomningspass är fail-open)
     trycks bara facitraden. Ingen tom rad: en rad utan innehåll läses som ett
     fel i pappret, inte som en lucka i underlaget. */

  /* Vilka trappsteg en elevlösning fick. Trappan är stigande och har en rad
     per poäng (exam_spec.bedomningsrader), så «två C-poäng» ÄR dess två första
     C-rader. Det går att räkna ut och ska därför inte skrivas av modellen en
     gång till — två sanningar om samma poäng glider isär. */
  function fickrader(rader, poang) {
    const kvar = { E: poang[0] || 0, C: poang[1] || 0, A: poang[2] || 0 };
    return rader.filter(r => {
      const n = (String(r.niva).match(/([ECA])/) || [])[1];
      if (!n || !kvar[n]) return false;
      kvar[n] -= 1;
      return true;
    });
  }
  /* Elevlösningens poäng som trippel. Partierna summeras: pappret läraren bad
     om är EN rad per poängsteg, men gamla dokument (och förlagans lo4) delar
     lösningen i flera partier med var sin dom. */
  function elevpoang(e) {
    const ut = [0, 0, 0];
    (e.partier || []).forEach(p => {
      const t = Array.isArray(p.poang) ? p.poang : [Number(p.poang) || 0, 0, 0];
      t.forEach((x, i) => { if (i < 3) ut[i] += Number(x) || 0; });
    });
    return ut;
  }

  const UTAN_POANG = /^\s*inga\s+po[äa]ng\s*[.:;,—–-]*\s*/i;

  function bedrader(u) {
    const rader = [], vag = u.vag || [], beddel = u.beddel || [];
    /* Facitraden — en per poängbärande enhet. En uppgift med deluppgifter har
       ingen egen bedömning (poängen ligger på a), b), c)), så där blir det en
       facitrad per deluppgift med dess egen trappa bredvid. */
    if (beddel.length) {
      beddel.forEach((b, k) => rader.push({
        facit: true, etikett: `Facit ${BOKSTAVER[k] || k + 1}) · full pott`,
        vanster: `<div class="lobedfacit">${mat((vag[k] || [])[0] || '')}${
          (vag[k] || [])[1] ? `<em>${esc(vag[k][1])}</em>` : ''}</div>`,
        hoger: trappaHtml(trappsteg(b)) }));
    } else {
      rader.push({ facit: true, etikett: 'Facit · full pott',
        vanster: `<div class="lobedfacit">${losvar(u) || losvag(u)}</div>`,
        hoger: trappaHtml(trappsteg(u.bed)) });
    }
    const alla = trapprader(u);
    (u.elever || []).forEach(e => {
      const poang = elevpoang(e), total = poang[0] + poang[1] + poang[2];
      const skrivna = (e.partier || []).reduce((a, p) => a.concat(p.rader || []), []);
      /* NOLLRADEN SÄGER «INGA POÄNG» EN GÅNG. Rubriken står redan i
         högerspalten, och modellen skriver ofta kommentaren som en hel mening
         som börjar likadant: «Inga poäng. Svaret är rätt, men …». Två rader
         efter varandra som båda börjar med samma två ord. Prompten ber om det
         också (exam_gen.build_bedomning_prompt) — men prompten är ett önskemål
         och renderaren en regel, och papperen i basen skrevs innan önskemålet
         fanns. Spegel av app/exam_latex._utan_rubriken. */
      let dom = (e.partier || []).map(p => p.dom).filter(Boolean).join(' ');
      if (!total) {
        dom = dom.replace(UTAN_POANG, '').trim();
        if (dom) dom = dom[0].toUpperCase() + dom.slice(1);
      }
      rader.push({
        utan: !total, etikett: `${total} p`,
        vanster: `<div class="loskann">${skrivna.map(
          r => `<div class="loskannrad">${mat(r)}</div>`).join('')}</div>`,
        hoger: (total ? trappaHtml(fickrader(alla, poang))
          : '<p class="lobedinga">Inga poäng</p>')
          + (dom ? `<p class="lobedvarfor">${mat(dom)}</p>` : '') });
    });
    return rader;
  }

  const bedtabell = u => `<table class="lobed"><tbody>${bedrader(u).map(
    r => `<tr${r.facit ? ' data-facit' : ''}${r.utan ? ' data-utan' : ''}>
      <td><b class="lobedsteg">${esc(r.etikett)}</b>${r.vanster}</td>
      <td>${r.hoger}</td></tr>`).join('')}</tbody></table>`;

  /* Kortsvarsarket och lösningsgångsarket ritar SAMMA rad: läraren ska
     bedöma uppgift 3 likadant vare sig den ligger i del B eller del C, och
     «gäller varje uppgift i provet» var beställningens fjärde punkt. */
  function losRad(u) {
    return `<div class="pruppg">
      <span class="prnr">${u.nr}.<span class="prvarde">${u.p} p</span></span>
      <div><p class="prtext" data-ref="">${ref(u.t)}</p>
        ${bedtabell(u)}
      </div></div>`;
  }
  /* Kortsvarsfacit för del A, utskriven lösningsgång för del B. Ett facit som
     bara svarar på halva provet ska säga det — därför räknas uppgifterna. */
  function losning(v, uppgifter, delB) {
    const b = uppgifter.filter(u => u.nr <= delB);
    const c = uppgifter.filter(u => u.nr > delB);
    const ut = [];
    const spann = l => (l.length === 1 ? `uppgift ${l[0].nr}` : `uppgift ${l[0].nr}–${l[l.length - 1].nr}`);
    /* PAPPRETS NAMN ÄR «BEDÖMNINGSANVISNING» (lärarens beslut 2026-08-23).
       «Lösningsförslag» stod kvar från när arket bara bar facit; nu bär det
       trappan och ett elevpapper per poängsteg, och det är en anvisning att
       rätta efter. Namnet står likadant på fliken, i PDF:ens titel, i
       tryckpaketet och i kvittot — arbetsbladets och gruppuppgiftens facit
       heter fortfarande «Lösningsförslag» respektive «Facit». */
    if (b.length) ut.push(`<div class="ark" data-form="lo-b" data-brytbar="">
      <div class="lohuvud"><b>Bedömningsanvisning · kortsvar</b><span>${delB >= uppgifter.length ? versal(spann(b)) : DELNAMN.B + ' · ' + spann(b)}</span></div>
      <h1 class="lotitel">Endast svar krävs</h1>
      ${b.map(losRad).join('')}</div>`);
    if (c.length) ut.push(`<div class="ark" data-form="lo-c" data-brytbar="">
      <div class="lohuvud"><b>Bedömningsanvisning · ${DELNAMN.C.toLowerCase()}</b><span>${DELNAMN.C} · ${spann(c)}</span></div>
      <h1 class="lotitel">Hela lösningen krävs</h1>
      ${c.map(losRad).join('')}</div>`);
    return ut;
  }

  /* `kortref` delas med blad-boklos.js: bokens lösningsark ska korta på samma
     sätt som provets och arbetsbladets, annars är det två olika facit. */
  return { mat, kortref, ref, ark, arkfacit, anteckningar, provforsatt, provblad,
           forsattsbild, losning, provtitel, BOKSTAV, delnamnVisning };
})();
