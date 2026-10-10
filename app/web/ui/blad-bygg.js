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
  /* ── EN HÄRLEDNING ÄR FLERA LED, INTE EN LÅDA ──
     Läraren om prov 40 (2026-09-06): elevlösningarna i bedömningsanvisningen
     hade en vågrät rullningslist i cellen, «ser jättefult ut».

     Skälet: modellen skriver hela härledningen i ETT dollarpar, «$A(15) =
     120 - 4 \cdot 15 = 120 - 60 = 60$», och den är en enda oböjlig låda.
     `.mat` är white-space:nowrap (matte.css) och KaTeX bryter aldrig inuti ett
     uttryck; dessutom sätter matte.js `\sf ` framför hela texten, så allt
     hamnar i EN .base som inte ens white-space:normal på .katex kan dela.
     Cellen (.lobed td, overflow-x:auto) fick därför en scrollbar.

     Delningen görs där en människa också bryter: vid likhetstecknet. Varje led
     blir en egen .mat-låda och `<wbr>` mellan dem ger webbläsaren stället att
     bryta på. Likhetstecknet INLEDER nästa led, för det är så ledet läses («=
     120 − 60»), och korta uttryck rörs inte alls. En delad «$x = 4$» vore två
     lådor där en räcker.

     Djupräkningen: bara `=` på toppnivå delar. Ett likhetstecken inuti
     `\begin{cases}`, ett bråk eller en parentes hör till sitt led, och `\=`
     är ett tecken och inte en operator (backslash hoppar över nästa tecken). */
  const MATBRYT_MIN = 24;
  function texled(tex) {
    const ut = [];
    let djup = 0, start = 0;
    for (let i = 0; i < tex.length; i++) {
      const c = tex[i];
      if (c === '\\') { i++; continue; }
      if (c === '{' || c === '(' || c === '[') djup++;
      else if (c === '}' || c === ')' || c === ']') djup--;
      else if (c === '=' && djup === 0 && i > start) { ut.push(tex.slice(start, i)); start = i; }
    }
    ut.push(tex.slice(start));
    return ut.filter(b => b.trim());
  }
  /* `fet` lindar varje led i KaTeX \pmb: bedömningsanvisningens svar står i
     fetstil, och KaTeX bryr sig inte om font-weight (se enhetRader). */
  const matBryt = (s, fet) => String(s == null ? '' : s).split('$').map((bit, i) => {
    if (!(i % 2)) return esc(bit);
    /* Ett led som BÖRJAR med likhetstecknet saknar vänsterled, och då sätter
       KaTeX inget mellanrum före tecknet: facit visade «P= 49 + 13,5 · 14=
       49 + 189= 238» (blad 133, 2026-09-24). Den tomma gruppen `{}` ger
       relationen ett vänsterled och därmed samma luft som i en hel formel. */
    const led = (bit.length > MATBRYT_MIN ? texled(bit) : [bit])
      .map((b, k) => (k && /^\s*=/.test(b) ? `{}${b}` : b));
    return led.map(b => `<span class="mat" data-tex="${attr(fet ? `\\pmb{${b}}` : b)}"></span>`).join('<wbr>');
  }).join('');
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
  /* MENINGARNA I ETT STYCKE (lärarens dom 2026-09-25, exam 126 9a och exam
     130 uppgift 9–10): «På Pizzeria Roma kostar en pizza 108 kr. Bestäm
     pizzans diameter.» på samma rad, ingen tom rad före frågan. Gäller både
     deluppgiften och uppgiftens stam. En rad som bara är en formel står kvar
     för sig, utom först i raden. Spegel av exam_latex._ihop.

     Arbetsbladet också (Rickard 2026-09-25: samma disposition som provet).
     Bladen bar länge sina deluppgifter i uppgiftstexten, «a) Beräkna …» på
     egen rad, och en sådan rad börjar ett nytt stycke i stället för att
     klistras efter frågan. */
  const ENSAM_FORMEL = /^\$[^$]+\$$/;
  const DELRAD = /^[a-h]\)\s/;
  const ihop = s => {
    const ut = [];
    let buf = [];
    String(s == null ? '' : s).split('\n').map(r => r.trim()).filter(Boolean)
      .forEach(r => {
        if (ENSAM_FORMEL.test(r) && (ut.length || buf.length)) {
          if (buf.length) { ut.push(buf.join(' ')); buf = []; }
          ut.push(r);
        } else if (DELRAD.test(r) && buf.length) {
          ut.push(buf.join(' '));
          buf = [r];
        } else buf.push(r);
      });
    if (buf.length) ut.push(buf.join(' '));
    /* «2 000» får inte brytas mellan raderna nu när texten flödar
       (exam_latex._HARD_TUSEN_RE): hårt mellanslag utanför matten. */
    return ut.join('\n').split('$')
      .map((bit, i) => (i % 2 ? bit : bit.replace(/(\d) (?=\d{3}(?!\d))/g, '$1 ')))
      .join('$');
  };
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
  const ref = (t, tak) => mat(kortref(luft(utanRaknarmarke(t)), tak));

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

  /* ── DELUPPGIFTENS EGNA FORMER ────────────────────
     Samma tre former som föräldern får, en nivå in: tabellen att räkna på,
     stegtabellen att granska och kryssruteraden att fylla i. PDF:en sätter dem
     på VARJE deluppgift (`former.kropp(d)` i arbetsblad.tex.j2,
     gruppuppgift.tex.j2 och prov.tex.j2) och _former.tex.j2 säger i sin egen
     rubrik att det är «samma former som på skärmarket» — men skärmen ritade
     bara deluppgiftens text.

     Det gick illa på lärarens gruppuppgift 2026-08-26: uppgift 2 b) bad
     eleverna markera den första felaktiga raden i «Melvins lösning», och
     stegtabellen med Melvins rader låg på deluppgiften. Pappret på skärmen bar
     alltså en fråga om en uträkning som inte stod någonstans — uppgiften gick
     inte att räkna på, och ingen omskrivning kunde laga det, för i dokumentets
     JSON var den redan komplett.

     Fälten kommer från plan.js franProv och är TOMMA på ett papper som inte
     bär dem, så ett gammalt dokument ritas exakt som förut. */
  const delform = (u, k, tabellklass) =>
    tabell((u.deltabell || [])[k], tabellklass)
    + stegtabell((u.delsteg || [])[k]);
  /* Flervalet på en deluppgift. Det rätta alternativet står ALDRIG här —
     `ratt_alternativ` stannar i provets JSON, som på föräldern. */
  function delflerval(u, k, klass) {
    const a = (u.delalt || [])[k];
    if (!a || !a.length) return '';
    return `<ul class="${klass} guval">${
      a.map((x, j) => `<li><i>${BOKSTAV[j]}.</i> ${mat(x)}</li>`).join('')}</ul>`;
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
     bladet numrerade redan i siffror. */
  /* ── RÄKNARBESKEDET ÄR EN ETIKETT, INTE EN MENING ─────────────
     exam_gen.satt_raknarmarkering skriver «Utan räknare.» eller «Räknare
     tillåten.» först i varje uppgiftstext på övningspappret. LÄRARENS BESKED
     2026-09-23: beskedet ska stå som etikett bredvid numret, «UTAN RÄKNARE»
     eller «MED RÄKNARE», som på repetitionsbladen i Drive — inte som första
     mening i frågan. Markeringen lyfts därför ur texten här och i facits
     kortreferens (ref nedan). Samma sil som exam_gen._RAKNARMARKE. */
  const RAKNARMARKE = /^\s*(Räknare tillåten|Utan räknare)\.\s*/;
  const utanRaknarmarke = t => String(t == null ? '' : t).replace(RAKNARMARKE, '');
  function kort(u, i, typ) {
    const bricka = String(i + 1);
    /* Stammen och deluppgiften i ETT stycke med frågan direkt efter, som på
       provet (ihop). Bara arbetsbladet: gruppuppgiftens text är en
       arbetsbeskrivning med en mening per rad, och ingen har bett om att den
       ska flöda. */
    const flod = t => (typ === 'Arbetsblad' ? ihop(t) : t);
    const marke = RAKNARMARKE.exec(String(u.t || ''));
    const fraga = marke ? utanRaknarmarke(u.t) : u.t;
    const raknare = marke
      ? `<span class="guraknare">${marke[1] === 'Utan räknare' ? 'Utan räknare' : 'Med räknare'}</span>` : '';
    const alt = u.alt
      ? `<ul class="gudel guval">${u.alt.map((a, k) => `<li><i>${BOKSTAV[k]}.</i> ${mat(a)}</li>`).join('')}</ul>` : '';
    /* Deluppgiften bär numera sin egen kropp — formerna, ledtråden och de
       namngivna raderna — i den ordning pappret sätter dem (gruppuppgift.tex.j2
       rad 45–53): text, kropp, notis, och sist svarsplatsen. */
    const delnotis = k => {
      const n = (u.delnotis || [])[k];
      return n ? `<p class="gunotis">${brodtext(n)}</p>` : '';
    };
    /* EN SVARSRAD PER DELUPPGIFT PÅ ARBETSBLADET, som på provet (Rickard
       2026-09-25, samma disposition): a) och b) med «Endast svar» fick en
       enda «Svar:» under båda, och eleven visste inte var b) skulle stå.
       Deluppgiften sätts då också i frågans grad (data-blad i blad.css).
       Gruppuppgiften står som förut. */
    /* Deluppgiftens EGEN typ styr (plan.js franProv `delut`): en uppgift
       «problem» kan ha ett kortsvar i a) och en lösning i b) (129 E7).
       Utan fältet, ett äldre papper, gäller förälderns. */
    const delUt = k => (u.delut || [])[k] || u.ut;
    const perDel = typ === 'Arbetsblad' && !(u.falt && u.falt.length) && !u.rutor;
    const delsvar = k => (perDel && delUt(k) === 'kort' && !((u.delrutor || [])[k])
      && !(((u.delfalt || [])[k] || []).length)
      ? svarsradEnhet((u.delenhet || [])[k]) : '');
    const del = u.del && u.del.length
      ? `<ul class="gudel"${typ === 'Arbetsblad' ? ' data-blad=""' : ''}>${u.del.map((d, k) => `<li>${'abcdef'[k]}) ${brodtext(flod(d))}`
        + delform(u, k, 'gutab')
        + rutor((u.delrutor || [])[k])
        + delflerval(u, k, 'gudel')
        + delnotis(k)
        + falt((u.delfalt || [])[k])
        + delsvar(k)
        + '</li>').join('')}</ul>` : '';
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
       provet, inte en kopia: plåtväljaren, «Kopiera basprompt + scen» och
       släppytan sitter delegerade på `.prscen` och `[data-plat]` i plan.js,
       och en egen markup här hade varit två system att hålla i synk för
       samma sak.

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
    /* BOKFÖREBILDEN (exam_spec.Forebild): «Som bokens 1279», med domarens
       mening som titel. Den står ÖVERST i kortet och inte vid texten, för den
       är inte en del av uppgiften — den är lärarens kvitto på att uppgiften
       hör till de sidor hon slog upp, och det är det första hon vill se när
       hon granskar.

       Den är LÄRARENS RUTA och står varken på elevens ark eller i PDF:en:
       blad-bild.js river den ur sin kopia, precis som prickarna, och
       LaTeX-mallarna har aldrig sett fältet. */
    const forebild = (u.forebild && u.forebild.nr)
      ? `<p class="guforebild" title="${attr(String(u.forebild.sort || ''))}">Som bokens ${Number(u.forebild.nr)}</p>`
      : '';
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
    /* FORMERNA STÅR FÖRE DELUPPGIFTERNA, inte efter dem. Stammens tabell är
       DATAT a) och b) räknar på, och den stod under frågorna som använde den —
       lärarens gruppuppgift 2026-08-26 hade alltså «Beräkna skillnaden» och
       «Markera den första rad som är fel» ovanför morgontemperaturerna. Pappret
       har aldrig haft den ordningen: gruppuppgift.tex.j2 och arbetsblad.tex.j2
       sätter former.kropp(u) FÖRE \begin{deluppgift}. */
    const former = tabell(u.tabell, 'gutab') + stegtabell(u.stegtabell);
    /* Lösbladsraden en gång, sist, när någon deluppgift ska redovisas. */
    const yta = perDel && u.del && u.del.length
      ? (u.del.some((_, k) => delUt(k) !== 'kort') ? `<p class="gulos">${losblad}</p>` : '')
      : svarsyta(u);
    /* BILDEN FÖRE DELUPPGIFTERNA, som på provet: stammen, bilden, a), b)
       (slutkollen 2026-09-25, 130 E7). Utan deluppgifter står den som förut
       efter frågan och före svarsraden. */
    const figFore = del ? fig : '';
    const figEfter = del ? '' : fig;
    const kropp = egen
      ? `<div class="gutva"><div><p class="gufraga">${brodtext(flod(fraga))}</p>${alt}${former}${del}${notis}${yta}</div>`
        + `<div>${egen}</div></div>`
      : `<p class="gufraga">${brodtext(flod(fraga))}</p>${alt}${former}${figFore}${del}${figEfter}${notis}${yta}`;
    return `<div class="gukort" data-ut="${u.ut || 'rakna'}">
      ${raknare
        ? `<div class="guraknarrad"><span class="gubricka">${bricka}</span>${raknare}</div>`
        : `<span class="gubricka">${bricka}</span>`}
      ${forebild}${kropp}
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
    /* «Bestäm vem som skriver» struken 2026-09-23: ingen skriver för gruppen,
       för inget lämnas in (exam_latex._GRUPPBAND säger samma sak). */
    Gruppuppgift: 'Läs uppgiften tillsammans innan ni börjar räkna. Alla i gruppen ska kunna förklara lösningen efteråt.'
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
       Gruppuppgiften behåller «gu»: fyra rutor med namnrader på ett A4, och
       det ÄR dess form. (gruppark.css, som bar tätheten för plan.js gamla
       ritaGrupp, togs bort 2026-10-07; ingen levande ritare satte klassen.)

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
    /* Formnyckeln räknar också DELUPPGIFTERNAS former. Ligger bladets enda
       stegtabell på en deluppgift bär bladet ändå tre former och behöver gu6:s
       tätare sättning — nyckeln såg den inte, och bladet spillde. */
    const nagot = (u, falt, del) => !!(u && (u[falt] || (u[del] || []).some(Boolean)));
    const harFigur = uppgifter.some(u => nagot(u, 'fig', 'delfig'));
    const harSteg = uppgifter.some(u => nagot(u, 'stegtabell', 'delsteg'));
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
      ${/* HJÄLPMEDLEN STÅR I BANDET (lärarens beställning 2026-09-21: «det
             måste stå om det ska användas räknare eller inte på vilka
             uppgifter, lite kort»). Provet säger det på försättsbladet
             (prov.tex.j2); gruppuppgiften och arbetsbladet har inget
             försättsblad, och dokumentets `hjalpmedel» («Räknare: uppgift 3.
             Övriga räknas utan.») nådde därför aldrig pappret. Raden står
             fet efter arbetsregeln och före nyckelfrågan, en gång. */''}
      <div class="guband"${bandtext ? ' data-egen' : ''}>${esc(bandtext || BAND[v.typ] || BAND.Arbetsblad)}${
        (v.hjalpmedel || '').trim() ? ` <b>${esc(v.hjalpmedel.trim())}</b>` : ''}${
        v.nyckelfraga ? ` <b>${mat(v.nyckelfraga)}</b>` : ''}</div>
      ${uppgifter.map((u, k) => kort(u, k, v.typ)).join('')}
    </div>`;
  }

  /* ── Facit till arbetsbladet ─────────────────────── */
  function arkfacit(v, uppgifter) {
    if (v.typ === 'Arbetsblad') return bladfacit(v, uppgifter);
    /* Gruppuppgiftens facit behåller poängen och uppgiftsraden: det läses MED
       bedömningen. Arbetsbladets facit är bladfacit nedan. */
    const poang = u => v.typ === 'Arbetsblad' ? '' : `<span class="prvarde">${u.p} p</span>`;
    /* Deluppgifterna i arbetsbladets facit: samma svarsrad som en uppgift med
       «a) … b) …» i texten, alltså a) och b) under SVAR och uträkningen
       under sitt svar. `vag` bär deluppgiftens poäng («1 p») för gruppens
       facit, och på arbetsbladet stod den kvar i grönt trots domen ovan
       (blad 141 uppgift 7 och 12, 2026-09-24). */
    const svaret = u => (v.typ === 'Arbetsblad' && !u.f && u.vag && u.vag.length
      ? losvar({ f: u.vag.map(s => s[0]).join('\n') })
      : `${losvar(u)}${losvag(u)}`);
    const post = (u, k) => `<div class="pruppg">
      <span class="prnr">${k + 1}.${poang(u)}</span>
      <div><p class="prtext" data-ref="">${ref(u.t)}</p>
        ${svaret(u)}
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
  /* ── KURSRADEN STÅR BARA PÅ FÖRSÄTTSBLADET ──
     Läraren om prov 40 (2026-09-06): «Att ha denna typ av text på varje
     provblad är onödigt. Det krävs bara på försättsidan. Däremot kan del A och
     del B i högra hörnet vara kvar.»

     `andra === undefined` ÄR försättsbladet: provforsatt anropar huvud(v) utan
     andra argument, provblad alltid huvud(v, etikett), och etiketten är TOM
     sträng när provet har «En del». Skillnaden mellan «ingen etikett» och
     «tom etikett» är alltså skillnaden mellan de två pappren, och en
     sanningsvärdesprövning hade gjort «En del»-arket till ett försättsblad.

     Första <b> står kvar TOM på uppgiftsbladen: .prhuvud är flex med
     space-between (prov.css), och utan den vänstra lådan hade delbokstaven
     hamnat till vänster i stället för i högra hörnet.

     Spegel av blad.js huvud(), som fyller raden om igen efter planeringen. */
  function huvud(v, andra) {
    const forsatt = andra === undefined;
    const t = forsatt
      ? [v.kurs || 'Matematik', v.klass || '', 'ht 2026'].filter(Boolean).join(' · ') : '';
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
    /* Deluppgiftens EGNA former (tabell, stegtabell, kryssruterad, flerval,
       ledtråd). Provets mall sätter dem — prov.tex.j2 rad 220 anropar
       `former.*` på `d` — och skärmen hoppade över dem helt.
       Allt går i EN ruta: raden är ett rutnät med tre spalter, och varje nytt
       barn tar nästa ruta (samma fälla som deluppgiftens figur gick i). Rutan
       spänner textspalten via .prdelform i prov.css, och står EFTER figuren —
       samma ordning som mallen (prov.tex.j2: figur, sedan former.*). */
    const delform_pr = k => {
      const kropp = tabell((u.deltabell || [])[k], 'prtab')
        + stegtabell((u.delsteg || [])[k])
        + (((u.delrutor || [])[k])
          ? `<div class="prsvar"><b>${faltnamn((u.delrutor[k]).etikett)}</b><span class="gurutor">${
              ((u.delrutor[k]).val || []).map(v => `<span class="guruta">${mat(v)}</span>`).join('')}</span></div>`
          : '')
        + delflerval(u, k, 'prdel prval')
        + (((u.delnotis || [])[k]) ? `<p class="prtips">${brodtext(u.delnotis[k])}</p>` : '');
      return kropp ? `<div class="prdelform">${kropp}</div>` : '';
    };
    const del = u.del && u.del.length
      ? `<ul class="prdel" data-avdelad="">${u.del.map((d, k) => `<li><i>${'abcdef'[k]})</i><span>${brodtext(ihop(d))}</span><span class="prpo">${delpoang(k)} p</span>${delfigur(k)}${delform_pr(k)}${delsvar()}</li>`).join('')}</ul>` : '';
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
    /* Etiketterna i vardagsord sedan 2026-10-10 (Rickard, språkkollen på
       omprov 174), samma som pappret (exam_latex._KRAV_TEXT). */
    const krav = `<p class="prkrav">${u.ut === 'kort'
      ? 'Skriv bara svaret.' : 'Visa hur du räknar.'}</p>`;
    /* Marginalen bär ETT format. «(totalt 3 p)» bredvid «1 p» läste sig som två
       olika fält; att poängen är en summa framgår av deluppgifternas egna. */
    const varde = `${u.p} p`;
    /* Stammens former står FÖRE deluppgifterna, som i mallen (prov.tex.j2
       sätter former.tabellbok/steg/rutor före \begin{parts}). Tabellen är
       datat a) och b) räknar på, och den stod under de frågor som använde
       den. */
    const former = tabell(u.tabell, 'prtab') + stegtabell(u.stegtabell);
    return `<div class="pruppg">
      <span class="prnr">${u.nr}.<span class="prvarde">${varde}</span></span>
      <div>${krav}<p class="prtext">${brodtext(ihop(u.t))}</p>${alt}${former}${del}${scenruta(u)}${figur}${notis}${svarsrad}</div>
    </div>`;
  }
  /* ══════════ BILDSTÖDET PÅ SKÄRMEN ══════════
     LÄRARENS BESLUT: «Skit i nyckeln, ingen API. Prompt bara, så skapar jag
     bilden med min prenumeration.» Appen genererar alltså ingen bild. Rutan
     nedan har därför två lägen, och det är hela funktionen:

       TRÄFF:  en plåt ur hennes egen katalog (E:\\Bildstil) ligger redan
               målad för begreppet. Den visas, och väljaren låter henne byta
               till en annan eller ta bort den. Hennes val vinner alltid.
       INGEN:  SCENE-stycket står framme med «Kopiera basprompt + scen» och
               ett filnamnsförslag. Knappen kopierar hela meddelandet till
               hennes ChatGPT-projekt, med basprompten framför stycket
               (plan.js kopieraScen, app/platar.py bildmeddelande). Hon
               släpper sedan den färdiga bilden på rutan. Släppytan är samma
               väg som alla andra bilder går (plan.js valjBild → v.bilder),
               inte en ny.

     Rutan bär `data-plat` = uppgiftens nummer. Klickarna sitter delegerade i
     plan.js; markup:en här är ren och ritas om vid varje omritning. */
  /* Etiketten och tooltipen säger vad som hamnar i urklippet. Knappen hette
     «Kopiera scen» när den bara kopierade stycket i rutan, och det namnet
     hade fått läraren att tro att basprompten fortfarande saknades. */
  const KOPIERA_TITEL = 'Kopierar hela meddelandet till ChatGPT-projektet: '
    + 'ordern att måla utan referensbilder, basprompten och SCENE-stycket.';
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
        <button type="button" class="prscenkopiera" data-plat-kopiera="${u.nr}" title="${KOPIERA_TITEL}">Kopiera basprompt + scen</button>
        <button type="button" class="prplatbyt" data-plat-byt="${u.nr}">Välj plåt</button>
      </div>
      <p class="prscenhint">Släpp bilden här när den är klar — eller klicka.</p>
    </div>`;
  }
  /* ══════════ BILDLAGRET ══════════
     LÄRARENS DOM 2026-10-02, om arbetsbladen till BA26B men för alla blad:
     där uppgiften beskriver något med mycket text (Negativa tal uppg 5,
     gångtunneln med taket på −1 m och golvet på −4 m) ska bilden ha pilar som
     pekar på rätt sak och lite ritat ovanpå, så att eleven direkt ser vad det
     handlar om. Samma grepp som matematikvideorna.

     Tvålagersprincipen (app/platar.py) gäller oförändrad. Plåten är bara
     målning, utan text, siffror eller pilar. Allt som går att läsa ritas här,
     i kod, ovanpå bilden. En siffra i själva målningen går inte att rätta när
     uppgiften skrivs om, och ChatGPT målar fel siffror.

     DATAN bor i dokumentet, bredvid bilderna: `v.bildlager = {uppg5: [...]}`,
     samma nyckel som `v.bilder`. Den ligger INTE i exam_json, av tre skäl.
     Bilden själv har aldrig legat där (plan.js: lärarens egna bilder bor bara
     i dokumentet), och ett lager utan sin bild är koordinater på ingenting.
     En omskrivning går genom modellen och exam_spec, som varken känner fältet
     eller ska lära sig det (kassettregeln: prompterna är orörda). Och PDF:en
     är skärmens avritning (blad-bild.js), så det som står i dokumentet är det
     som trycks. Versionerna och godkännandet bär hela dokumentet, alltså
     följer lagret med av sig självt.

     Elementen, koordinater relativt bilden (0 till 1 i bredd och höjd, origo
     uppe till vänster). tools/bildlager.py validerar samma form:
       {typ:'pil', fran:[x,y], till:[x,y], text?, textvid?:'svans'|'spets'}
       {typ:'matt', fran:[x,y], till:[x,y], text}   måttlinje med tvärstreck
       {typ:'etikett', plats:[x,y], text}            text i vit ruta med kant
       {typ:'linje', fran:[x,y], till:[x,y], streckad?, text?}
       {typ:'ring', mitt:[x,y], r, text?}            r i andel av bildbredden
       {typ:'vinkel', mitt:[x,y], fran:[x,y], till:[x,y], r?, text?}
                                 båge i hörnet `mitt`, alltid den mindre
                                 vinkeln; r som ringens, standard 0,06
                                 (Rickard 2026-10-08, vinkeln v i prov 163)
     Alla med text tar också `sida` (var texten ligger mot sin punkt: mitt,
     upp, ner, vanster, hoger, upp-hoger, upp-vanster, ner-hoger, ner-vanster)
     och `textplats` [x,y] som flyttar texten. Matematik skrivs «$-4$ m» och
     sätts av KaTeX som resten av bladet.

     UTSEENDET är tryckets: svart linje med vit kontur, så att den syns både
     mot mörk tunnel och ljus himmel, och text på vit botten. Linjerna är en
     SVG med bildens egna proportioner (viewBox 1000 brett), texterna är HTML
     i procent ovanpå, för KaTeX är HTML och en <foreignObject> i en SVG som
     själv hamnar i avritningens <foreignObject> är en fälla för mycket.
     Strecken är `non-scaling-stroke`, alltså lika tjocka i pixlar hur stor
     bilden än ritas.

     blad.js lägger lagret på bilden när bilden väl ligger i rutan (lärarens
     egen eller plåten). Ett dokument utan `bildlager` ritas exakt som förut. */
  const BL_SIDOR = {
    mitt: [-50, -50, 0, 0], upp: [-50, -100, 0, -1], ner: [-50, 0, 0, 1],
    vanster: [-100, -50, -1, 0], hoger: [0, -50, 1, 0],
    'upp-hoger': [0, -100, 1, -1], 'upp-vanster': [-100, -100, -1, -1],
    'ner-hoger': [0, 0, 1, 1], 'ner-vanster': [-100, 0, -1, 1],
  };
  const blPunkt = p => (Array.isArray(p) && p.length === 2
    && p.every(t => typeof t === 'number' && isFinite(t)))
    ? [Math.min(1, Math.max(0, p[0])), Math.min(1, Math.max(0, p[1]))] : null;
  const blTal = n => Math.round(n * 10) / 10;
  /* Bildens proportioner ur en PNG:s data-URL, utan att vänta på avkodningen.
     IHDR står på byte 16 till 23 (bredd, höjd), alltså räcker de första 32
     base64-tecknen. Lagret ritas då rätt redan när arket byggs, och canvasens
     klon (granska.js) får det med sig. Allt annat ger 0, och då väntar blad.js
     in bildens `load`. */
  function bildForhallande(src) {
    const m = /^data:image\/png;base64,/.exec(String(src || ''));
    if (!m) return 0;
    try {
      const b = atob(String(src).slice(m[0].length, m[0].length + 32));
      const tal = i => ((b.charCodeAt(i) << 24) >>> 0) + (b.charCodeAt(i + 1) << 16)
        + (b.charCodeAt(i + 2) << 8) + b.charCodeAt(i + 3);
      const w = tal(16), h = tal(20);
      return w > 0 && h > 0 ? w / h : 0;
    } catch (e) { return 0; }
  }
  function bildlager(lista, forhallande) {
    if (!Array.isArray(lista) || !lista.length) return '';
    const W = 1000;
    const H = Math.round(W / (forhallande > 0 ? forhallande : 16 / 9));
    const xy = p => [p[0] * W, p[1] * H];
    const halo = [], black = [], lappar = [];
    const streck = (a, b, streckad) => {
      const d = `x1="${blTal(a[0])}" y1="${blTal(a[1])}" x2="${blTal(b[0])}" y2="${blTal(b[1])}"`;
      halo.push(`<line ${d} stroke="#fff" stroke-width="6" stroke-linecap="round" vector-effect="non-scaling-stroke"/>`);
      black.push(`<line ${d} stroke="#000" stroke-width="2"${streckad ? ' stroke-dasharray="14 9"' : ' stroke-linecap="round"'} vector-effect="non-scaling-stroke"/>`);
    };
    /* Spetsen pekar från `bak` mot `spets`. Linjen kortas så att den runda
       ändan inte sticker ut genom spetsen. */
    const L = 26, B2 = 10, T = 13;
    const enhet = (a, b) => {
      const dx = b[0] - a[0], dy = b[1] - a[1], n = Math.hypot(dx, dy) || 1;
      return [dx / n, dy / n];
    };
    const spets = (bak, tip) => {
      const [ux, uy] = enhet(bak, tip);
      const bas = [tip[0] - ux * L, tip[1] - uy * L];
      const pts = [tip, [bas[0] - uy * B2, bas[1] + ux * B2], [bas[0] + uy * B2, bas[1] - ux * B2]]
        .map(p => `${blTal(p[0])},${blTal(p[1])}`).join(' ');
      halo.push(`<polygon points="${pts}" fill="#fff" stroke="#fff" stroke-width="4" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>`);
      black.push(`<polygon points="${pts}" fill="#000"/>`);
      return [tip[0] - ux * L * 0.7, tip[1] - uy * L * 0.7];
    };
    const tvars = (p, u) => streck([p[0] - u[1] * T, p[1] + u[0] * T], [p[0] + u[1] * T, p[1] - u[0] * T]);
    /* Texten läggs på den sida av punkten som linjen INTE går åt, så att den
       aldrig ligger över sin egen pil. */
    const bort = (fran, mot) => {
      const dx = fran[0] - mot[0], dy = fran[1] - mot[1];
      if (Math.abs(dx) > Math.abs(dy)) return dx < 0 ? 'vanster' : 'hoger';
      return dy < 0 ? 'upp' : 'ner';
    };
    const lapp = (text, p, sida, ram) => {
      if (text == null || String(text).trim() === '' || !p) return;
      const s = BL_SIDOR[sida] || BL_SIDOR.mitt;
      const tx = s[2] ? `calc(${s[0]}% + ${s[2] * 6}px)` : `${s[0]}%`;
      const ty = s[3] ? `calc(${s[1]}% + ${s[3] * 6}px)` : `${s[1]}%`;
      lappar.push(`<span class="bllapp${ram ? ' blram' : ''}" style="left:${blTal(p[0] * 100)}%;top:${blTal(p[1] * 100)}%;transform:translate(${tx},${ty})">${mat(String(text))}</span>`);
    };
    lista.forEach(e => {
      if (!e || typeof e !== 'object') return;
      const egen = blPunkt(e.textplats);
      const fran = blPunkt(e.fran), till = blPunkt(e.till);
      if (e.typ === 'pil' && fran && till) {
        const a = xy(fran), b = xy(till);
        streck(a, spets(a, b));
        const vidSpets = e.textvid === 'spets';
        const p = egen || (vidSpets ? till : fran);
        lapp(e.text, p, e.sida || (egen ? 'mitt' : vidSpets ? bort(b, a) : bort(a, b)));
      } else if (e.typ === 'matt' && fran && till) {
        const a = xy(fran), b = xy(till), u = enhet(a, b);
        streck(spets(b, a), spets(a, b));
        tvars(a, u); tvars(b, u);
        lapp(e.text, egen || [(fran[0] + till[0]) / 2, (fran[1] + till[1]) / 2], e.sida || 'mitt');
      } else if (e.typ === 'linje' && fran && till) {
        streck(xy(fran), xy(till), !!e.streckad);
        lapp(e.text, egen || fran, e.sida || 'upp-hoger');
      } else if (e.typ === 'ring') {
        const m = blPunkt(e.mitt);
        const r = Number(e.r);
        if (!m || !(r > 0)) return;
        const c = xy(m), rr = Math.min(r, 0.5) * W;
        const d = `cx="${blTal(c[0])}" cy="${blTal(c[1])}" r="${blTal(rr)}" fill="none"`;
        halo.push(`<circle ${d} stroke="#fff" stroke-width="6" vector-effect="non-scaling-stroke"/>`);
        black.push(`<circle ${d} stroke="#000" stroke-width="2" vector-effect="non-scaling-stroke"/>`);
        lapp(e.text, egen || [m[0], Math.max(0, m[1] - rr / H)], e.sida || 'upp');
      } else if (e.typ === 'etikett') {
        lapp(e.text, egen || blPunkt(e.plats), e.sida || 'mitt', true);
      } else if (e.typ === 'vinkel') {
        /* Bågen går den kortaste vägen mellan strålarna. Etiketten sitter på
           bisektrisen, längre ut ju spetsigare vinkeln är, och högst tre
           radier bort (samma regel som provets PDF, app/bildlager_rita.py). */
        const m = blPunkt(e.mitt);
        if (!m || !fran || !till) return;
        const c = xy(m), a = xy(fran), b = xy(till);
        const r = Number(e.r);
        const rr = (r > 0 && r <= 0.5 ? r : 0.06) * W;
        const ta = Math.atan2(a[1] - c[1], a[0] - c[0]);
        let d = Math.atan2(b[1] - c[1], b[0] - c[0]) - ta;
        while (d > Math.PI) d -= 2 * Math.PI;
        while (d < -Math.PI) d += 2 * Math.PI;
        if (Math.hypot(a[0] - c[0], a[1] - c[1]) < 1 || Math.hypot(b[0] - c[0], b[1] - c[1]) < 1) return;
        const p1 = [c[0] + rr * Math.cos(ta), c[1] + rr * Math.sin(ta)];
        const p2 = [c[0] + rr * Math.cos(ta + d), c[1] + rr * Math.sin(ta + d)];
        const dd = `d="M${blTal(p1[0])} ${blTal(p1[1])} A${blTal(rr)} ${blTal(rr)} 0 0 ${d > 0 ? 1 : 0} ${blTal(p2[0])} ${blTal(p2[1])}" fill="none"`;
        halo.push(`<path ${dd} stroke="#fff" stroke-width="6" vector-effect="non-scaling-stroke"/>`);
        black.push(`<path ${dd} stroke="#000" stroke-width="2" vector-effect="non-scaling-stroke"/>`);
        const mid = ta + d / 2;
        const avst = Math.min(Math.max(rr + 30, 18 / Math.sin(Math.max(Math.abs(d) / 2, 0.02)) + 12), rr * 3);
        lapp(e.text, egen || [Math.min(1, Math.max(0, (c[0] + avst * Math.cos(mid)) / W)),
          Math.min(1, Math.max(0, (c[1] + avst * Math.sin(mid)) / H))], e.sida || 'mitt');
      }
    });
    if (!halo.length && !lappar.length) return '';
    const svg = halo.length
      ? `<svg class="blsvg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">`
        + `<g>${halo.join('')}</g><g>${black.join('')}</g></svg>` : '';
    return svg + lappar.join('');
  }
  /* ══════════ FÖRSÄTTSBLADETS PORTRÄTT ══════════
     Försättsbladet slutar i en halv sida tomt papper under betygstabellen, och
     den ytan var husets ENDA bildplats utan beställning: varenda annan ruta bär
     ett SCENE-stycke, den här sa bara «plats för bild — läggs in i canvas».

     LÄRARENS ORD (2026-08-23): «den här vetenskapsmannen eller matematikern som
     kom på det provet handlar om … Fast en fin bild, lite dramatiskt så att de
     blir inspirerade av att klara av provet.» Dokumentet bär personen och
     stycket (exam_spec.Forsattsbild), och rutan visar dem på EXAKT samma sätt
     som uppgifternas scener: samma .prscen-markup,
     samma «Kopiera basprompt + scen», samma
     släppyta. Ingen egen CSS och ingen andra sorts bildruta — hade porträttet
     fått sin egen form vore det två system att hålla i synk för samma sak.

     Nyckeln är 'forsatt' och inte ett uppgiftsnummer: bilden hör till
     DOKUMENTET, inte till en uppgift. Den är också nyckeln lärarens egen
     släppta bild landar under (blad.js markera → data-el="forsatt", v.bilder).

     Saknas fältet — prototypens papper, ett prov skrivet innan fältet fanns —
     står platshållaren kvar precis som förut. Ingen migrering. */
  /* ── BILDTEXTEN LIGGER UTANFÖR BILDRUTAN ──
     Fältet är dokumentets (exam_spec.Forsattsbild.bildtext, högst 400 tecken
     sedan läraren bad om två till tre meningar 2026-09-06: vad man ser, vem
     personen är och vad hen kom på, och hur det hör ihop med provet)
     och säger vem eleven ser och varför hen hör hit. Den skrivs EFTER
     .prbild-rutan och inte inuti den, för blad.js byter hela .prbild:s
     innerHTML mot lärarens egen släppta bild (v.bilder.forsatt). Hade
     bildtexten legat inne i rutan hade den försvunnit i samma ögonblick som
     bilden kom på plats, alltså precis när den behövs. */
  function forsattsbild(v) {
    const f = (v || {}).forsattsbild;
    const bildtext = ((f || {}).bildtext || '').trim();
    const under = bildtext ? `<p class="prbildtext">${esc(bildtext)}</p>` : '';
    if (!f || !(f.scene || '').trim()) {
      return '<div class="prbild gufigur"><span class="gufigtext">plats för bild — läggs in i canvas</span></div>' + under;
    }
    return `<div class="prbild gufigur prscen" data-plat="forsatt">
      <p class="prscenrub">Bild att skapa — ${esc(f.person || '')}</p>
      <pre class="prscentext">${esc(f.scene || '')}</pre>
      <div class="prplatfot">
        <button type="button" class="prscenkopiera" data-plat-kopiera="forsatt" title="${KOPIERA_TITEL}">Kopiera basprompt + scen</button>
      </div>
      <p class="prscenhint">Släpp bilden här när den är klar — eller klicka.</p>
    </div>${under}`;
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
  /* «utan digitala hjälpmedel» heter «utan räknare» (lärarens dom
     2026-09-23), också på prov som redan bär den gamla meningen. Spegel av
     exam_latex._HJALPMEDELSORD. */
  const hjalpmedelsord = t => String(t || '')
    .replace(/\butan digitala hjälpmedel\b/g, 'utan räknare')
    .replace(/\bUtan digitala hjälpmedel\b/g, 'Utan räknare')
    .replace(/\binga digitala hjälpmedel\b/g, 'ingen räknare');
  const delnamnVisning = t => {
    const s = hjalpmedelsord(t);
    return DELNAMN_REDAN.test(s) ? s : s
      .replace(/\b([Dd]el)\s+B\b/g, '$1 A')
      .replace(/\b([Dd]el)\s+C\b/g, '$1 B')
      .replace(/\b([Dd]el)\s+D\b/g, '$1 C');
  };
  /* ── HJÄLPMEDLEN PER DEL, SOM PAPPRET SÄGER DEM ─────
     Nycklarna är planeringens val (plan.js HJALPMEDELSVAL) och värdena är de
     fraser pappret bar innan valet fanns — `Inga digitala` ger ordagrant den
     gamla del A-frasen och `Räknare` den gamla del B-frasen. Det är med flit:
     ett prov som aldrig rört raden ska se ut precis som förut.

     Spegel av app/exam_gen.HJALPMEDEL_KLAUSUL, som skriver samma sak in i
     dokumentets `hjalpmedel` och därmed på PDF:ens försättsblad. Säger de två
     listorna olika saker säger skärmen och pappret olika saker om samma prov
     — det är hela skälet till att regeln bara får stå EN gång (se nedan). */
  /* Del A heter «utan räknare», inte «utan digitala hjälpmedel» (lärarens
     dom 2026-09-23). Nycklarna står kvar: de är sparade i planeringarna. */
  const HJALPMEDELSFRAS = {
    'Inga digitala': 'Utan räknare.',
    'Formelblad': 'Formelbladet är tillåtet, ingen räknare.',
    /* «Räknare» och inget mer — «digitala hjälpmedel» var för vagt (lärarens
       dom 2026-09-18); datorn skriver hon själv när en uppgift kräver den. */
    'Räknare': 'Räknare tillåten.',
    'Räknare och formelblad': 'Räknare och formelblad tillåtna.',
    /* Datorn med GeoGebra, aldrig räknaren (lärarens dom 2026-09-22). */
    'Digitala verktyg och formelblad': 'GeoGebra på datorn och formelblad tillåtna.'
  };
  /* Kortformen i delens sidhuvud («Del A · utan räknare»). */
  const HJALPMEDELSETIKETT = {
    'Inga digitala': 'utan räknare',
    'Formelblad': 'formelblad, utan räknare',
    'Räknare': 'räknare',
    'Räknare och formelblad': 'räknare och formelblad',
    'Digitala verktyg och formelblad': 'GeoGebra på datorn och formelblad'
  };
  /* Del A är `hjalpmedelA`, del B `hjalpmedelB` — och «En del» är ett prov med
     bara den första. Ett papper utan fälten (allt som skrevs före
     2026-09-06) faller tillbaka på dagens standard. */
  const HJALPMEDELSFORVAL = { B: 'Inga digitala', C: 'Räknare', '-': 'Inga digitala' };
  function hjalpmedelsval(v, del) {
    const i = (v || {}).inst || {};
    const valt = del === 'C' ? i.hjalpmedelB : i.hjalpmedelA;
    return HJALPMEDELSFRAS[valt] ? valt : HJALPMEDELSFORVAL[del] || 'Inga digitala';
  }
  const hjalpmedelsfras = (v, del) => HJALPMEDELSFRAS[hjalpmedelsval(v, del)];

  function provblad(v, uppgifter, del) {
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
    /* Utan dokumentets regel står PLANERINGENS val i huvudet i stället för den
       gamla hårdkodade frasen (spåret 2026-09-06: «formelblad tillåtet på del
       A och B»). Rör läraren inte raden är texten ordagrant den förra. */
    const etikett = del === '-' ? ''
      : hjalp ? DELNAMN[del]
        : `${DELNAMN[del]} · ${HJALPMEDELSETIKETT[hjalpmedelsval(v, del)]}`;
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
  /* Svaret är FÖRSTA raden i losning, uträkningen raderna efter
     («$K = 468 + 1{,}2E$» och sedan stegen). Enheten hör till svaret och står
     direkt efter det: i ett enda spann hamnade den till höger om den bredaste
     uträkningsraden, långt från talet («238 ……… kr», blad 133, 2026-09-24).
     En radbrytning inuti $…$ är TeX-källa och delar inte, så bara en
     radbrytning med ett jämnt antal dollartecken före räknas. */
  function svarOchSteg(f) {
    const s = String(f || '');
    let dollar = 0;
    for (let i = 0; i < s.length; i++) {
      if (s[i] === '$') dollar++;
      else if (s[i] === '\n' && dollar % 2 === 0) return [s.slice(0, i), s.slice(i + 1).trim()];
    }
    return [s, ''];
  }
  function losvar(u) {
    if (!u.f) return '';
    /* matBryt och inte mat: en hel härledning i ett dollarpar är en enda
       oböjlig låda, och i en smal spalt gav den en scrollbar (se matBryt
       ovan). */
    /* Enheten står INNE i svarets spann, och spannet tar resten av raden
       (.lossvar). Annars bröts ett långt svar till en egen rad under
       etiketten, till vänster om de indragna uträkningsraderna. */
    /* Granskningen 2026-09-24 natt: «Svar: 3» under etiketten SVAR stod
       dubbelt, «$n =$» som enhet hamnade EFTER svaret (133:3, 145:2), och
       «%» efter «2,5 per år (…)» (146:6). Samma regler som
       bedömningsanvisningens svaret() nedan: ett led («$n =$») står före
       svaret, en enhet bara efter ett tal. */
    const [rad, steg] = svarOchSteg(u.f);
    const svar = rad.replace(/^\s*svar\s*:\s*/i, '');
    const e = String(u.enhet || '').trim();
    const fore = e && arLed(e) && !svar.includes('=') ? `${matBryt(e)} ` : '';
    const efter = e && !arLed(e) && SVAR_TAL.test(svar) && !ENHET_SLUT(svar, e)
      ? ` <em>${enhetHtml(e)}</em>` : '';
    return `<div class="losvar"><b class="losetikett">Svar</b><span class="lossvar">${fore}${matBryt(svar)}${efter}</span>${
      steg ? `<span class="losrader">${matBryt(steg)}</span>` : ''}</div>`;
  }
  /* Vägen till svaret — och på en uppgift med deluppgifter ÄR den svaret:
     `vag` bär «a) …», «b) …» med sin poäng (plan.js franProv). */
  const losvag = u => (u.vag && u.vag.length
    ? `<ul class="lovag">${u.vag.map(s => `<li><span class="losteg">${matBryt(s[0])}<em>${esc(s[1])}</em></span></li>`).join('')}</ul>`
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
        if (m) return { niva: m[2], poang: Number(m[1]), krav: m[3].trim() };
        return { niva: '', poang: 0, krav: BEDNOT.test(s) ? s[0].toUpperCase() + s.slice(1) : s };
      });
  }
  const BOKSTAVER = 'abcdefghijkl';

  /* ══════════ BEDÖMNINGSANVISNINGEN I NATIONELLA PROVETS FORM ══════════
     Lärarens dom 2026-09-23: «Hela bedömningsanvisningen skulle vi kunna
     bygga mycket tydligare … lik det som finns på nationella proven. För just
     nu känns det som att det är väldigt mycket text och det är svårt för mig
     att rätta snabbt.» Formen hon valde är PRIM-gruppens häften (NP 1c vt22):

       20.  x = 6
            Förenklar vänsterled genom att multiplicera parenteserna.   +C
            Lösning med korrekt svar.                                   +C
            (0/2/0)

     Tre spalter per uppgift: numret (.prnr), svaret och kraven, poängen. En
     rad per poäng, per deluppgift när den bär poäng. Uppgiftstexten står inte
     här (den har hon på provet bredvid sig), inte heller lösningsgången (den
     står i lösningsförslaget) eller elevexemplen (de har ett eget ark sist,
     se elevark). Tabellen förut, facit överst och ett elevpapper per lägre
     poängsteg under, gjorde varje uppgift till en halv sida att läsa förbi.

     Spegel av app/exam_latex (_svaret, _svarsrad, _kravrad, _marke,
     _elevexempel) och app/templates/bedomning.tex.j2. Ändras den ena ska den
     andra ändras, annars säger skärm och PDF olika saker om samma poäng. */

  /* «löser ekvation (1), $x = 7$» blir «Löser ekvation (1), $x = 7$.». NP
     skriver varje krav som en mening. En rad som börjar med matematik
     behåller sin början. */
  function kravmening(krav) {
    const s = String(krav || '').trim();
    if (!s) return '';
    const v = /^\p{L}/u.test(s) ? s[0].toUpperCase() + s.slice(1) : s;
    return /[.!?…]$/.test(v) ? v : v + '.';
  }
  /* «KORREKT SVAR.» OCH INGET MER, som NP skriver när poängen ges för svaret
     (lärarens dom 2026-09-23). Raderna upprepade annars svaret som står i
     fetstil precis ovanför: «Rätt svar 3.», «Korrekt svar x⁸/2.». Bara när
     resten av raden ÄR svaret (eller ingenting) kortas den; «Korrekt
     förenkling till a⁶» säger något mer och står kvar. Flervalet får
     «Korrekt alternativ.». Jämförelsen tål dollartecken, mellanrum, {,} och
     en inledande variabel («d = 30 cm» mot svaret «30 cm»). `jamfor` är det
     raden kan upprepa: svaret med och utan enhet, flervalets bokstav. Spegel
     av exam_latex._kravrad. */
  /* «korrekt lösning med svaret x = 12» blir «Korrekt lösning.» (126:10c,
     2026-09-26). Spegel av exam_latex._KORREKT_RE. */
  const KORREKT = /^(?:för\s+)?(?:rätt|korrekt)\s+(svar|alternativ|lösning\s+med\s+(?:rätt\s+|korrekt\s+)?svar(?:et)?)\b[\s,:;–-]*([\s\S]*?)[\s.]*$/i;
  const LEDPREFIX = /^[a-zåäö][a-z0-9_']*(?:\([^()]*\))?=$/;
  const jamforbar = s => String(s || '').toLowerCase().replace(/\{,\}/g, ',')
    .replace(/\\[,;: ]|~|\$|\s/g, '').replace(/\.+$/, '');
  function sammaSvar(rest, svar) {
    const a = jamforbar(rest), b = jamforbar(svar);
    if (!a || !b) return false;
    if (a === b) return true;
    const [kort, lang] = a.length <= b.length ? [a, b] : [b, a];
    return lang.endsWith(kort) && LEDPREFIX.test(lang.slice(0, lang.length - kort.length));
  }
  function kravrad(krav, jamfor) {
    const m = String(krav || '').trim().match(KORREKT);
    const samma = m && (jamfor || []).some(k => k && sammaSvar(m[2], k));
    if (m && /^lösning/i.test(m[1])) {
      if (m[2].trim() && samma) return 'Korrekt lösning.';
    } else if (m && (!m[2].trim() || samma)) {
      return m[1].toLowerCase() === 'alternativ' ? 'Korrekt alternativ.' : 'Korrekt svar.';
    }
    return kravmening(krav);
  }
  /* NP:s märke, «+C», ett per poäng. «+1 C» var appens egen form, och ettan
     säger ingenting när varje rad är en poäng. */
  const marke = r => Array.from({ length: Math.max(r.poang, 0) }, () => '+' + r.niva).join(' ');

  /* SVARET ÄR FÖRSTA RADEN I `losning`. Fältet är med flit kort, «svaret
     först, ett par räkneled» (exam_spec._Uppgiftsbas), och räkneleden hör till
     lösningsförslaget. Enheten följer med när svaret är ett tal och inte
     redan bär den; ett led står före svaret när svaret inte redan är en
     likhet. Spegel av exam_latex._svaret. */
  /* Raden fram till första meningsslutet utanför matematiken, när nästa
     mening börjar med versal, siffra eller en formel och är en uträkning (ett
     likhetstecken följer). Prov 124 (2026-09-23) hade svar och uträkning på
     samma rad, och hela raden stod fet. Spegel av exam_latex._forsta_meningen. */
  const FORKORTNING = /(?:^|\s)(?:t\.ex|bl\.a|s\.k|d\.v\.s|dvs|osv|m\.m|ca|jfr|resp|kl|nr|obs)$/i;
  function forstaMeningen(rad) {
    let iMat = false;
    for (let i = 0; i < rad.length; i++) {
      if (rad[i] === '$' && (i === 0 || rad[i - 1] !== '\\')) iMat = !iMat;
      else if (rad[i] === '.' && !iMat && /^\s+[A-ZÅÄÖ0-9$]/.test(rad.slice(i + 1))
               && !FORKORTNING.test(rad.slice(0, i)) && rad.slice(i + 1).includes('=')) {
        return rad.slice(0, i).trimEnd();
      }
    }
    return rad;
  }
  const forstaRad = s => forstaMeningen(
    String(s || '').split('\n').map(r => r.trim()).find(Boolean) || '');
  const arLed = e => String(e || '').trim().replace(/[$\s]+$/, '').endsWith('=');
  const SVAR_TAL = /(\$|\d)\s*\.?$/;
  function svaret(losning, enhet) {
    const s = forstaRad(losning);
    const e = String(enhet || '').trim();
    if (!s || !e) return s;
    if (arLed(e)) return s.includes('=') ? s : `${e} ${s}`;
    if (!SVAR_TAL.test(s) || ENHET_SLUT(s, e)) return s;
    const m = s.match(/^([\s\S]*?)(\.?)$/);
    return `${m[1]} ${e}${m[2]}`;
  }
  /* Flervalets bokstav först, sedan svaret, versal först. Rutornas och
     stegtabellens facit når aldrig skärmarket (plan.js franProv), så de står
     bara på PDF:en (exam_latex._svarsrad). */
  function bedsvar(bokstav, svar) {
    const delar = [];
    if (bokstav && svar.replace(/^[ .]+|[ .]+$/g, '') !== bokstav) delar.push(bokstav);
    if (svar) delar.push(svar);
    const t = delar.join(', ');
    return /^\p{L}/u.test(t) ? t[0].toUpperCase() + t.slice(1) : t;
  }
  /* En poängbärande enhet som tabellrader: svaret och en rad per poäng.
     Enhetens poäng som trippel, «(0/0/1)», står inte sist längre (lärarens
     dom 2026-09-26: den behövs inte; samma i bedomning.tex.j2). Svaret i
     fetstil, och matematiken i det med KaTeX egen \pmb: KaTeX ignorerar
     font-weight, och utan den blev «2,5 km» ett magert tal och en fet enhet.
     PDF:en gör samma sak (exam_latex.escape_mixed fet). */
  function enhetRader(namn, svar, bed, jamfor) {
    /* NOTRADEN TRYCKS INTE. «Vanligt fel»-raden bär ingen poäng, och
       läraren om prov 40 (2026-09-06): «detta med vanliga fel kan vi ta bort
       helt och hållet så att vi sparar plats». Parsern läser den fortfarande
       (de gamla dokumenten bär den), det är sättningen som väljer bort den. */
    const rader = trappsteg(bed).filter(r => r.niva);
    const ut = [];
    /* Ett svar som är en MENING (minst fem ord utanför matematiken) står i
       vanlig vikt; i fetstil såg det ut som en rubrik (126:10b, 2026-09-26).
       Spegel av exam_latex._ar_mening. */
    const mening = String(svar || '').split('$').filter((_b, k) => k % 2 === 0)
      .join(' ').match(/[A-Za-zÅÄÖåäöÉé]+/g);
    const svarHtml = mening && mening.length >= 5
      ? `<span class="lobedsvar" data-mening="">${matBryt(svar)}</span>`
      : `<b class="lobedsvar">${matBryt(svar, true)}</b>`;
    if (namn || svar) {
      ut.push(`<tr data-svar><td>${namn ? `<b class="lobeddel">${esc(namn)}</b>` : ''}${
        svar ? svarHtml : ''}</td><td></td></tr>`);
    }
    rader.forEach(r => ut.push(`<tr><td class="lobedkrav">${mat(kravrad(r.krav, jamfor))}</td><td><b class="lobedniva">${
      esc(marke(r))}</b></td></tr>`));
    return ut.join('');
  }

  /* `table` och inte grid: blad.js delaUppgift delar en uppgift som är högre
     än pappret mellan två ark rad för rad (`.lobed tbody > tr`), och det
     kontraktet står kvar. */
  function bedtabell(u) {
    const beddel = u.beddel || [], vag = u.vag || [];
    /* En uppgift med deluppgifter har ingen egen bedömning: poängen ligger på
       a), b), c). Deras svar står i `vag` med bokstaven först (plan.js
       franProv), och bokstaven står redan i namnet. Saknas `beddel` (ett
       gammalt papper) men `vag` finns och `f` är tom, är `vag` ändå
       deluppgifternas svar. */
    const antal = Math.max(beddel.length, u.f ? 0 : vag.length);
    const utanBokstav = s => String(s || '').replace(/^\s*[a-l]\)\s*/, '');
    const kropp = antal
      ? Array.from({ length: antal }, (_, k) => {
        const los = utanBokstav((vag[k] || [])[0]);
        const svar = svaret(los, (u.delenhet || [])[k]);
        return enhetRader(`${BOKSTAVER[k] || k + 1})`, svar, beddel[k],
                          [svar, svaret(los)]);
      }).join('')
      : (() => {
        const bokstav = u.alt && u.ratt != null ? BOKSTAV[u.ratt] || '' : '';
        const svar = svaret(u.f, u.enhet);
        return enhetRader('', bedsvar(bokstav, svar), u.bed,
                          [svar, svaret(u.f)].concat(bokstav ? [bokstav, `(${bokstav})`] : []));
      })();
    return `<table class="lobed"><tbody>${kropp}</tbody></table>`;
  }

  /* ══════════ ARBETSBLADETS FACIT I BEDÖMNINGSANVISNINGENS FORM ══════════
     Rickard 2026-09-25: facit ska bli mycket tydligare för eleverna, i samma
     form som provens bedömningsanvisning. Förut stod uppgiftstexten i liten
     stil, etiketten SVAR i kapitäler, svaret stort, enheten liten och stegen
     stora: fem grader på samma uppgift. Nu: numret, svaret i fetstil, ett
     steg per rad i samma grad, luft före nästa deluppgift och en linje
     mellan uppgifterna, som bedtabell ovan. Inga poäng (lärarens dom
     2026-08-26) och ingen uppgiftstext: eleven har bladet bredvid sig, som
     läraren har provet bredvid anvisningen.

     `losning` bär svaret på första raden och stegen på raderna efter
     (exam_spec, «svaret först»). En rad som börjar med «a)» börjar en ny
     deluppgift: bladen bar länge deluppgifterna i uppgiftstexten, och då
     står alla svaren i samma fält. Spegel av exam_latex._facit_grupper. */
  const DELSTART = /^([a-h])\)\s*/;
  /* Raderna i `losning`. En radbrytning inuti $…$ är TeX-källa och delar
     inte (samma regel som svarOchSteg). */
  function losrader(s) {
    const ut = [];
    let dollar = 0, start = 0;
    const t = String(s == null ? '' : s);
    for (let i = 0; i < t.length; i++) {
      if (t[i] === '$') dollar++;
      else if (t[i] === '\n' && dollar % 2 === 0) { ut.push(t.slice(start, i)); start = i + 1; }
    }
    ut.push(t.slice(start));
    return ut.map(r => r.trim()).filter(Boolean);
  }
  /* Svaret och resten av första raden. Delas vid första meningsslutet utanför
     matematiken («Nej. Talet framför …») eller vid «, eftersom» («$5$,
     eftersom $5 \cdot 5 \cdot 5 = 125$»): det som följer är ett steg. */
  const ORSAK = /^,?\s+(eftersom|för att)\s+/;
  function delaSvaret(rad) {
    const s = rad.replace(/^\s*svar\s*:\s*/i, '');
    let iMat = false;
    for (let i = 0; i < s.length; i++) {
      if (s[i] === '$' && (i === 0 || s[i - 1] !== '\\')) { iMat = !iMat; continue; }
      if (iMat) continue;
      if (s[i] === '.' && /^\s+[A-ZÅÄÖ0-9$]/.test(s.slice(i + 1)) && !FORKORTNING.test(s.slice(0, i))) {
        return [s.slice(0, i).trimEnd(), s.slice(i + 1).trim()];
      }
      const m = ORSAK.exec(s.slice(i));
      if ((s[i] === ',' || s[i] === ' ') && m && i > 0) {
        return [s.slice(0, i).trimEnd(), versal(m[1]) + ' ' + s.slice(i + m[0].length).trim()];
      }
    }
    return [s, ''];
  }
  /* Enheten efter ett tal, ledet före ett svar som inte redan är en likhet.
     Samma regel som svaret() ovan. */
  function medEnhet(s, enhet) {
    const e = String(enhet || '').trim();
    if (!s || !e) return s;
    if (arLed(e)) return s.includes('=') ? s : `${e} ${s}`;
    if (!SVAR_TAL.test(s) || ENHET_SLUT(s, e)) return s;
    const m = s.match(/^([\s\S]*?)(\.?)$/);
    return `${m[1]} ${e}${m[2]}`;
  }
  function facitGrupper(losning, enhet) {
    const grupper = [];
    losrader(losning).forEach(r => {
      const m = DELSTART.exec(r);
      if (m || !grupper.length) grupper.push({ namn: m ? `${m[1]})` : '', rader: [] });
      grupper[grupper.length - 1].rader.push(m ? r.slice(m[0].length) : r);
    });
    return grupper.map(g => {
      /* En figurrad är aldrig svaret: står den först är gruppens svar tomt
         och figuren första steget (app/facitfigur, lärarens dom 2026-10-02). */
      if (FACITFIGUR.arFigurrad(elevradDelar(g.rader[0] || '')[0])) {
        return { namn: g.namn, svar: '', steg: g.rader.slice() };
      }
      const [svar, rest] = delaSvaret(g.rader[0] || '');
      const steg = (rest ? [rest] : []).concat(g.rader.slice(1));
      /* Enheten hör till hela uppgiften och sätts bara när det finns ett svar. */
      return { namn: g.namn, svar: grupper.length === 1 ? medEnhet(svar, enhet) : svar, steg };
    }).filter(g => g.svar || g.steg.length);
  }
  /* ══════════ FIGURRADER I FACIT (lärarens dom 2026-10-02) ══════════
     «Starta på 3 på tallinjen», och eleverna frågar «vad då tallinje?».
     Facit ska VISA tallinjen och pilen, brädan som sågas och de hundra
     rutorna. En rad i `losning` som är en hakparentes med en figurtyp först,
     «[tallinje start 3 hopp -9]», «[bräda delar 4 hela 2 stryk 3]»,
     «[procent 10 av 2400 enhet kr]», ritas som SVG i facitgruppen där den
     står. Skärmen är PDF:ens förlaga (blad-bild.js serialiserar arket), så
     SVG:en följer med till pappret. Svart-vitt: grått, skrafferat och
     mörkgrått.

     Tolkningen och layouten är en spegel av app/facitfigur.py, primitiv för
     primitiv (LaTeX-facit ritar samma primitiver som TikZ). Formen och
     nyckelorden står där. En rad som inte går att tolka står som text utan
     hakparenteser, aldrig som ett trasigt papper. */
  const FACITFIGUR = (() => {
    const TYPER = { tallinje: 'tallinje', 'bräda': 'brada', brada: 'brada',
                    'bråk': 'brada', brak: 'brada', procent: 'procent' };
    const RAD = /^\s*\[\s*([A-Za-zÅÄÖåäö]+)([^[\]]*)\]\s*\.?\s*$/;
    const TAL = /^[+-]?\d+(?:[.,]\d+)?$/;
    const BRAK = /^([+-]?\d+)\/(\d+)$/;
    const TUSEN = /^\d{3}$/;
    const NYCKLAR = {
      tallinje: { start: 'tal', hopp: 'lista', markera: 'lista', 'lodrät': 'flagga',
                  'lodrätt': 'flagga', lodrat: 'flagga', 'vågrät': 'flagga',
                  vagrat: 'flagga', enhet: 'text', noll: 'text' },
      brada: { delar: 'tal', hela: 'tal', 'färga': 'lista', farga: 'lista', stryk: 'tal' },
      procent: { av: 'tal', ruta: 'flagga', stapel: 'flagga', enhet: 'text' },
    };
    const ALIAS = { 'lodrätt': 'lodrät', lodrat: 'lodrät', vagrat: 'vågrät', farga: 'färga' };
    const arFigurrad = rad => {
      const m = RAD.exec(String(rad || ''));
      return !!m && Object.prototype.hasOwnProperty.call(TYPER, m[1].toLowerCase());
    };
    const normalisera = s => s.replace(/\{,\}/g, ',').replace(/\\,/g, '').replace(/\$/g, '')
      .replace(/[−–—]/g, '-').replace(/[   ]/g, ' ').replace(/[=:%]/g, ' ');
    function talet(token) {
      const t = token.trim();
      if (TAL.test(t)) return [parseFloat(t.replace(',', '.')), 1];
      const m = BRAK.exec(t);
      if (m && Number(m[2]) > 0) return [Number(m[1]) / Number(m[2]), Number(m[2])];
      return null;
    }
    const tokens = rest => normalisera(rest).split(/\s+/).map(t => t.replace(/[,;]+$/, '')).filter(Boolean);
    function talen(toks, namn) {
      return toks.map(t => {
        const v = talet(t);
        if (!v) throw new Error(`«${t}» efter «${namn}» är inget tal`);
        if (Math.abs(v[0]) > 1e6) throw new Error(`«${t}» är för stort`);
        return v;
      });
    }
    function ettTal(toks, namn) {
      if (toks.length > 1 && toks.slice(1).every(t => TUSEN.test(t))) toks = [toks.join('')];
      const t = talen(toks, namn);
      if (t.length !== 1) throw new Error(`«${namn}» ska ha ett tal`);
      return t[0];
    }
    const text = toks => (toks || []).join(' ').slice(0, 24);
    function heltal(toks, namn, lo, hi) {
      const [x] = ettTal(toks, namn);
      if (x !== Math.trunc(x) || x < lo || x > hi) throw new Error(`«${namn}» ska vara ett heltal ${lo}–${hi}`);
      return x;
    }
    function tolkaTallinje(v, flaggor) {
      const fri = v[''] || []; delete v[''];
      if (fri.length) {
        if (v.start || v.hopp) throw new Error(`«${fri[0]}» står utan nyckelord`);
        v.start = fri.slice(0, 1); v.hopp = fri.slice(1);
      }
      const namnare = [1];
      let start = null;
      if (v.start && v.start.length) { const [s, d] = ettTal(v.start, 'start'); start = s; namnare.push(d); }
      const hopp = talen(v.hopp || [], 'hopp'), markera = talen(v.markera || [], 'markera');
      hopp.concat(markera).forEach(([, d]) => namnare.push(d));
      if (hopp.length && start === null) throw new Error('hopp kräver start');
      if (start === null && !markera.length) throw new Error('tallinjen behöver start eller markera');
      if (hopp.length > 6 || markera.length > 6) throw new Error('högst sex hopp och sex markerade tal');
      if (hopp.some(([h]) => h === 0)) throw new Error('ett hopp kan inte vara 0');
      return { typ: 'tallinje', start, hopp: hopp.map(h => h[0]), markera: markera.map(x => x[0]),
               lodrat: flaggor.has('lodrät'), enhet: text(v.enhet), noll: text(v.noll),
               namnare: Math.max(...namnare.filter(d => d <= 12)) };
    }
    function tolkaBrada(v) {
      const fri = v[''] || []; delete v[''];
      if (fri.length) {
        const m = fri.length === 1 ? BRAK.exec(fri[0]) : null;
        if (!m || v.delar || v['färga']) throw new Error(`«${fri.join(' ')}» står utan nyckelord`);
        v.delar = [m[2]]; v['färga'] = [m[1]];
      }
      if (!v.delar || !v.delar.length) throw new Error('bräda behöver «delar»');
      const delar = heltal(v.delar, 'delar', 2, 12);
      let hela = v.hela && v.hela.length ? heltal(v.hela, 'hela', 1, 6) : null;
      let farga = talen(v['färga'] || [], 'färga').map(([x]) => {
        if (x !== Math.trunc(x) || x < 0) throw new Error('«färga» ska vara heltal');
        return x;
      });
      if (farga.length > 3) throw new Error('högst tre grupper i «färga»');
      if (!farga.length) {
        if (hela === null) throw new Error('bräda behöver «hela» eller «färga»');
        farga = [hela * delar];
      }
      const totalt = farga.reduce((a, b) => a + b, 0);
      if (hela === null) hela = Math.max(1, Math.ceil(totalt / delar));
      if (hela > 6) throw new Error('högst sex brädor');
      if (totalt > hela * delar) throw new Error('fler färgade delar än brädorna har');
      const stryk = v.stryk && v.stryk.length ? heltal(v.stryk, 'stryk', 0, 72) : 0;
      if (stryk > totalt) throw new Error('fler strukna delar än färgade');
      return { typ: 'brada', delar, hela, farga, stryk };
    }
    function tolkaProcent(v, flaggor) {
      const fri = v[''] || []; delete v[''];
      if (!fri.length) throw new Error('procent behöver ett tal, t.ex. [procent 10 av 2400]');
      const [p] = ettTal(fri, 'procent');
      const ruta = flaggor.has('ruta');
      if (!(p > 0 && p <= (ruta ? 100 : 200))) {
        throw new Error(`procenttalet ska vara större än 0 och högst ${ruta ? 100 : 200}`);
      }
      let av = null, enhet = text(v.enhet);
      if (v.av && v.av.length) {
        const talord = v.av.filter(t => talet(t) || TUSEN.test(t));
        const ord = v.av.filter(t => !talord.includes(t));
        [av] = ettTal(talord, 'av');
        if (!(av > 0)) throw new Error('«av» ska vara större än 0');
        enhet = enhet || text(ord);
      }
      return { typ: 'procent', p, av, enhet, ruta };
    }
    /* [figur, null] eller [null, felet]; ingen figurrad → [null, null]. */
    function tolka(rad) {
      const m = RAD.exec(String(rad || ''));
      if (!m || !Object.prototype.hasOwnProperty.call(TYPER, m[1].toLowerCase())) return [null, null];
      const typ = TYPER[m[1].toLowerCase()];
      const nycklar = NYCKLAR[typ];
      const v = {}, flaggor = new Set();
      let nyckel = '';
      tokens(m[2]).forEach(t => {
        const l = t.toLowerCase(), n = ALIAS[l] || l;
        if (nycklar[l]) {
          if (nycklar[l] === 'flagga') { flaggor.add(n); nyckel = ''; }
          else { nyckel = n; v[n] = v[n] || []; }
          return;
        }
        (v[nyckel] = v[nyckel] || []).push(t);
      });
      try {
        if (typ === 'tallinje') return [tolkaTallinje(v, flaggor), null];
        if (typ === 'brada') return [tolkaBrada(v), null];
        return [tolkaProcent(v, flaggor), null];
      } catch (e) { return [null, e.message]; }
    }
    const textreserv = rad => String(rad || '').trim().replace(/\.$/, '').trim()
      .replace(/^\[/, '').replace(/\]$/, '').trim();

    /* Svensk sättning: «−1,5», «2 400», «1 1/4» när talen var bråk. */
    function tal(x, namnare = 1) {
      const tecken = x < -1e-9 ? '−' : '';
      const a = Math.abs(x);
      const gcd = (p, q) => (q ? gcd(q, p % q) : p);
      if (namnare > 1 && Math.abs(a * namnare - Math.round(a * namnare)) < 1e-6
          && Math.abs(a - Math.round(a)) > 1e-6) {
        const t = Math.round(a * namnare), hel = Math.floor(t / namnare), rest = t % namnare;
        const g = gcd(rest, namnare);
        const b = `${rest / g}/${namnare / g}`;
        return tecken + (hel ? `${hel} ${b}` : b);
      }
      const r = Math.round(a * 10000) / 10000;
      let hel, dec = '';
      if (Math.abs(r - Math.round(r)) < 1e-9) hel = String(Math.round(r));
      else [hel, dec] = r.toFixed(4).replace(/0+$/, '').split('.');
      if (hel.length > 3) hel = hel.replace(/\B(?=(\d{3})+$)/g, ' ');
      return tecken + hel + (dec ? ',' + dec : '');
    }

    /* ── Layouten, primitiv för primitiv som app/facitfigur.py ── */
    const GRA = '#b5b5b5', MORK = '#6e6e6e', TEXT = 13;
    function pilspets(fran, till, storlek = 7) {
      const dx = till[0] - fran[0], dy = till[1] - fran[1];
      const n = Math.hypot(dx, dy) || 1, ux = dx / n, uy = dy / n;
      const bas = [till[0] - ux * storlek, till[1] - uy * storlek], v = storlek * 0.45;
      return { t: 'poly', fyll: '#000000',
               p: [[till[0], till[1]], [bas[0] - uy * v, bas[1] + ux * v], [bas[0] + uy * v, bas[1] - ux * v]] };
    }
    function bage(a, b, hojd, normal) {
      const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
      const k = [mx + normal[0] * hojd * 2, my + normal[1] * hojd * 2];
      return [{ t: 'bage', p: [a.slice(), k, b.slice()], w: 1.6 }, pilspets(k, b, 6.5)];
    }
    const STEG = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000,
                  5000, 10000, 20000, 50000, 100000];
    const multipel = (x, s) => Math.abs(x / s - Math.round(x / s)) < 1e-6;
    function skala(varden, namnare) {
      const lo = Math.min(...varden), hi = Math.max(...varden);
      const kand = (namnare > 1 ? [1 / namnare] : []).concat(STEG.filter(s => namnare === 1 || s >= 1));
      const span = hi - lo;
      let steg;
      if (varden.every(v => multipel(v, 1)) && span <= 14) steg = 1;
      else {
        const delare = kand.filter(s => varden.every(v => multipel(v, s)));
        steg = delare.length ? delare[delare.length - 1] : kand[0];
        while (span / steg < 4) {
          const finare = kand.filter(s => s < steg && multipel(steg, s));
          if (!finare.length) break;
          steg = finare[finare.length - 1];
        }
      }
      let i = Math.max(0, kand.indexOf(steg));
      while (span / steg > 14 && i + 1 < kand.length) steg = kand[++i];
      let loT = Math.floor(lo / steg + 1e-9) * steg - steg, hiT = Math.ceil(hi / steg - 1e-9) * steg + steg;
      while (Math.round((hiT - loT) / steg) < 4) { loT -= steg; hiT += steg; }
      return [steg, loT, hiT];
    }
    function tallinje(f) {
      const lodrat = f.lodrat;
      const pos = f.start === null ? [] : [f.start];
      f.hopp.forEach(h => pos.push(pos[pos.length - 1] + h));
      const punkter = pos.concat(f.markera);
      const varden = punkter.slice();
      const lo = Math.min(...varden), hi = Math.max(...varden);
      if (f.noll || (lo <= 0 && 0 <= hi) || Math.min(Math.abs(lo), Math.abs(hi)) <= 0.5 * (hi - lo)) varden.push(0);
      const [steg, loT, hiT] = skala(varden, f.namnare);
      const n = Math.round((hiT - loT) / steg);
      const p = [];
      let sp, bredd, hojd, xy, ax = 66, topp = 26, x0 = 30, y0 = 0;
      if (lodrat) {
        sp = Math.max(16, Math.min(26, 300 / n));
        xy = (t, nrm = 0) => [ax + nrm, topp + (hiT - t) / steg * sp];
        bredd = 236; hojd = topp + n * sp + 20;
      } else {
        bredd = 360; sp = (bredd - 60) / n;
      }
      const hoppen = [];
      f.hopp.forEach((h, i) => {
        const a = pos[i], b = pos[i + 1];
        let niva = 0;
        while (hoppen.some(o => o.niva === niva && Math.min(Math.max(a, b), Math.max(o.a, o.b))
               - Math.max(Math.min(a, b), Math.min(o.a, o.b)) > 1e-9)) niva++;
        const sma = Math.abs(steg - 1) < 1e-9 && Math.abs(h - Math.round(h)) < 1e-9
          && Math.abs(h) <= 12 && niva === 0;
        hoppen.push({ a, b, h, niva, sma });
      });
      const apex = o => (o.sma ? 9 : 22 + 26 * o.niva);
      const hogst = Math.max(0, ...hoppen.map(apex));
      if (!lodrat) {
        y0 = Math.max(30, hogst + 22);
        xy = (t, nrm = 0) => [x0 + (t - loT) / steg * sp, y0 - nrm];
      }
      const punkt = xy;
      const normal = lodrat ? [1, 0] : [0, -1];
      let a, b;
      if (lodrat) { a = [ax, punkt(loT)[1] + 12]; b = [ax, punkt(hiT)[1] - 16]; }
      else { a = [punkt(loT)[0] - 14, y0]; b = [punkt(hiT)[0] + 16, y0]; }
      p.push({ t: 'linje', p: [a, b], w: 1.6, streck: false }, pilspets(a, b, 8));
      if (f.enhet) {
        p.push(lodrat
          ? { t: 'text', x: ax + 9, y: b[1] + 4, s: f.enhet, ank: 'start', fet: false, g: 12 }
          : { t: 'text', x: b[0], y: y0 - 9, s: f.enhet, ank: 'slut', fet: false, g: 12 });
      }
      if (f.noll && lodrat) {
        const y = punkt(0)[1];
        p.push({ t: 'linje', p: [[ax - 6, y], [bredd - 4, y]], w: 1.0, streck: true },
               { t: 'text', x: bredd - 4, y: y - 4, s: f.noll, ank: 'slut', fet: false, g: 12 });
      }
      const nd = f.namnare;
      const etiketter = [], sedda = [];
      punkter.forEach(t => {
        if (sedda.some(s => Math.abs(t - s) < 1e-9)) return;
        sedda.push(t);
        const rad = !lodrat && etiketter.some(e => Math.abs(punkt(t)[0] - punkt(e[0])[0]) < 24 && e[3] === 0) ? 1 : 0;
        etiketter.push([t, tal(t, nd), true, rad]);
      });
      let varannan = sp >= 26 ? 1 : (sp * 2 >= 26 ? 2 : 5);
      if (lodrat) varannan = sp >= 16 ? 1 : 2;
      for (let k = 0; k <= n; k++) {
        let t = loT + k * steg;
        if (Math.abs(t) < 1e-9) t = 0;
        const [x, y] = punkt(t);
        p.push(lodrat ? { t: 'linje', p: [[x - 5, y], [x + 5, y]], w: 1.2, streck: false }
                      : { t: 'linje', p: [[x, y - 5], [x, y + 5]], w: 1.2, streck: false });
        if (Math.round(t / steg) % varannan) continue;
        if (nd > 1 && Math.abs(t - Math.round(t)) > 1e-9) continue;
        const krock = etiketter.some(e => e[2] && Math.abs((lodrat ? punkt(e[0])[1] : punkt(e[0])[0])
          - (lodrat ? y : x)) < (lodrat ? 13 : 22));
        if (!krock) etiketter.push([t, tal(t, nd), false, 0]);
      }
      etiketter.forEach(([t, s, fet, rad]) => {
        const [x, y] = punkt(t);
        p.push(lodrat ? { t: 'text', x: x - 9, y: y + 4.5, s, ank: 'slut', fet, g: TEXT }
                      : { t: 'text', x, y: y + 20 + 14 * rad, s, ank: 'mitt', fet, g: TEXT });
      });
      sedda.forEach(t => { const [x, y] = punkt(t); p.push({ t: 'prick', x, y, r: 3.4 }); });
      const rader = 1 + Math.max(0, ...etiketter.map(e => e[3]));
      if (f.noll && !lodrat) {
        const [x, y] = punkt(0);
        p.push({ t: 'text', x, y: y + 20 + 14 * rader, s: f.noll, ank: 'mitt', fet: false, g: 11 });
      }
      hoppen.forEach(o => {
        const etikett = (o.h > 0 ? '+' : '−') + tal(Math.abs(o.h), nd) + (f.enhet ? ' ' + f.enhet : '');
        if (o.sma) {
          const r = o.h > 0 ? 1 : -1;
          for (let k = 0; k < Math.abs(Math.round(o.h)); k++) {
            const ta = o.a + r * k;
            p.push(...bage(punkt(ta), punkt(ta + r), 9, normal));
          }
        } else p.push(...bage(punkt(o.a), punkt(o.b), apex(o), normal));
        const mitt = (o.a + o.b) / 2;
        if (lodrat) {
          const [x, y] = punkt(mitt, apex(o) + 7);
          p.push({ t: 'text', x, y: y + 4.5, s: etikett, ank: 'start', fet: true, g: TEXT });
        } else {
          const [x, y] = punkt(mitt, apex(o) + 6);
          p.push({ t: 'text', x, y, s: etikett, ank: 'mitt', fet: true, g: TEXT });
        }
      });
      if (!lodrat) hojd = y0 + 10 + 14 * rader + (f.noll ? 14 : 0);
      return { b: bredd, h: hojd, p };
    }
    function skraffering(x, y, b, h, avstand = 6) {
      const ut = [];
      for (let s = -h; s < b; s += avstand) {
        const tmin = Math.max(0, -s), tmax = Math.min(h, b - s);
        if (tmin < tmax) {
          ut.push({ t: 'linje', p: [[x + s + tmin, y + h - tmin], [x + s + tmax, y + h - tmax]], w: 0.9, streck: false });
        }
      }
      return ut;
    }
    function brakText(x, y, taljare, namnare, g = TEXT, fet = false) {
      const b = 6 + 0.62 * g * Math.max(String(taljare).length, String(namnare).length);
      return [{ t: 'text', x, y: y - 3, s: String(taljare), ank: 'mitt', fet, g },
              { t: 'linje', p: [[x - b / 2, y + 1], [x + b / 2, y + 1]], w: 1.1, streck: false },
              { t: 'text', x, y: y + g + 1, s: String(namnare), ank: 'mitt', fet, g }];
    }
    function brada(f) {
      const { delar, hela, farga, stryk } = f;
      const totalt = farga.reduce((a, b) => a + b, 0);
      const bredd = 360, kol = Math.min(hela, 3), rader = Math.ceil(hela / kol);
      const gap = 16, bh = 28;
      const bb = Math.min(150, (bredd - 16 - gap * (kol - 1)) / kol);
      const cell = bb / delar, radhojd = bh + 46;
      const p = [], kvar = new Array(hela).fill(0);
      for (let k = 0; k < hela * delar; k++) {
        const bi = Math.floor(k / delar), ci = k % delar;
        const bx = 8 + (bi % kol) * (bb + gap), by = 8 + Math.floor(bi / kol) * radhojd;
        const x = bx + ci * cell;
        let grupp = -1, kum = 0;
        for (let g = 0; g < farga.length; g++) { kum += farga[g]; if (k < kum) { grupp = g; break; } }
        const struken = totalt - stryk <= k && k < totalt;
        if (grupp === 0) p.push({ t: 'rekt', x, y: by, b: cell, h: bh, fyll: GRA, w: 0 });
        else if (grupp === 1) p.push(...skraffering(x, by, cell, bh));
        else if (grupp === 2) p.push({ t: 'rekt', x, y: by, b: cell, h: bh, fyll: MORK, w: 0 });
        p.push({ t: 'rekt', x, y: by, b: cell, h: bh, fyll: '', w: 1.0 });
        if (struken) {
          p.push({ t: 'linje', p: [[x + 3, by + 3], [x + cell - 3, by + bh - 3]], w: 2.4, streck: false },
                 { t: 'linje', p: [[x + cell - 3, by + 3], [x + 3, by + bh - 3]], w: 2.4, streck: false });
        } else if (grupp >= 0) kvar[bi]++;
      }
      for (let bi = 0; bi < hela; bi++) {
        const bx = 8 + (bi % kol) * (bb + gap), by = 8 + Math.floor(bi / kol) * radhojd;
        p.push({ t: 'rekt', x: bx, y: by, b: bb, h: bh, fyll: '', w: 2.2 },
               ...brakText(bx + bb / 2, by + bh + 19, kvar[bi], delar));
      }
      return { b: bredd, h: 8 + rader * radhojd - 4, p };
    }
    function procentstapel(f) {
      const { p: pr, av, enhet } = f;
      const x0 = 24, x1 = 336, sk = Math.max(100, pr);
      const px = q => x0 + q / sk * (x1 - x0);
      const lagen = [...new Set([0, 10, pr, 100])].sort((a, b) => a - b);
      const nere = q => tal(av * q / 100) + (enhet && q ? ' ' + enhet : '');
      const rad = new Map(), senast = [[-1e9, 0], [-1e9, 0]];
      lagen.forEach(q => {
        const b = 0.56 * 12 * Math.max((tal(q) + ' %').length, av !== null ? nere(q).length : 0);
        const x = px(q), [fx, fb] = senast[0];
        const r = x - fx >= (b + fb) / 2 + 6 ? 0 : 1;
        rad.set(q, r); senast[r] = [x, b];
      });
      const flera = Math.max(...rad.values());
      const yb = 24 + 14 * flera, hb = 28;
      const p = [{ t: 'rekt', x: x0, y: yb, b: px(Math.min(pr, 100)) - x0, h: hb, fyll: GRA, w: 0 }];
      if (pr > 100) {
        p.push(...skraffering(px(100), yb, px(pr) - px(100), hb),
               { t: 'rekt', x: px(100), y: yb, b: px(pr) - px(100), h: hb, fyll: '', w: 1.6 });
      }
      for (let k = 1; k < 10; k++) p.push({ t: 'linje', p: [[px(10 * k), yb], [px(10 * k), yb + hb]], w: 1.0, streck: false });
      p.push({ t: 'rekt', x: x0, y: yb, b: px(100) - x0, h: hb, fyll: '', w: 2.2 });
      lagen.forEach(q => {
        const x = px(q), r = rad.get(q), fet = Math.abs(q - pr) < 1e-9;
        if (r) p.push({ t: 'linje', p: [[x, yb - 14 * r - 4], [x, yb]], w: 0.8, streck: false });
        p.push({ t: 'text', x, y: yb - 6 - 14 * r, s: tal(q) + ' %', ank: 'mitt', fet, g: 12 });
        if (av !== null) {
          const s = tal(av * q / 100) + (enhet && q ? ' ' + enhet : '');
          if (r) p.push({ t: 'linje', p: [[x, yb + hb], [x, yb + hb + 14 * r + 4]], w: 0.8, streck: false });
          p.push({ t: 'text', x, y: yb + hb + 17 + 14 * r, s, ank: 'mitt', fet, g: 12 });
        }
      });
      return { b: 360, h: yb + hb + (av !== null ? 24 + 14 * flera : 8), p };
    }
    function procentruta(f) {
      const { p: pr, av, enhet } = f;
      const c = 15, x0 = 8, y0 = 8, p = [];
      const hela = Math.floor(pr + 1e-9);
      for (let k = 0; k < hela; k++) {
        p.push({ t: 'rekt', x: x0 + (k % 10) * c, y: y0 + Math.floor(k / 10) * c, b: c, h: c, fyll: GRA, w: 0 });
      }
      const rest = pr - hela;
      if (rest > 1e-9 && hela < 100) {
        p.push({ t: 'rekt', x: x0 + (hela % 10) * c, y: y0 + Math.floor(hela / 10) * c,
                 b: c * rest, h: c, fyll: MORK, w: 0 });
      }
      for (let k = 1; k < 10; k++) {
        p.push({ t: 'linje', p: [[x0 + k * c, y0], [x0 + k * c, y0 + 10 * c]], w: 0.7, streck: false },
               { t: 'linje', p: [[x0, y0 + k * c], [x0 + 10 * c, y0 + k * c]], w: 0.7, streck: false });
      }
      p.push({ t: 'rekt', x: x0, y: y0, b: 10 * c, h: 10 * c, fyll: '', w: 2.2 });
      const e = enhet ? ' ' + enhet : '';
      const rader = av !== null
        ? [['100 rutor = 100 % = ' + tal(av) + e, false], ['1 ruta = 1 % = ' + tal(av / 100) + e, false]]
          .concat(Math.abs(pr - 1) > 1e-9 ? [[tal(pr) + ' % = ' + tal(av * pr / 100) + e, true]] : [])
        : [['100 rutor = 100 %', false], ['1 ruta = 1 %', false]]
          .concat(Math.abs(pr - 1) > 1e-9 ? [[tal(pr) + ' rutor = ' + tal(pr) + ' %', true]] : []);
      rader.forEach(([s, fet], i) => p.push({ t: 'text', x: x0 + 10 * c + 14, y: y0 + 34 + 24 * i,
                                              s, ank: 'start', fet, g: TEXT }));
      return { b: 360, h: y0 + 10 * c + 8, p };
    }
    function layout(f) {
      if (f.typ === 'tallinje') return tallinje(f);
      if (f.typ === 'brada') return brada(f);
      return f.ruta ? procentruta(f) : procentstapel(f);
    }

    /* ── SVG ── Bredden följer facitets grad (--fsk, blad.js fyll), så
       figuren växer med texten när arket skalas upp. */
    const r2 = x => String(Math.round(x * 100) / 100);
    const pkt = pts => pts.map(([x, y]) => `${r2(x)},${r2(y)}`).join(' ');
    function svg(f, rad) {
      const lay = layout(f);
      const ank = { mitt: 'middle', start: 'start', slut: 'end' };
      const kropp = lay.p.map(q => {
        if (q.t === 'linje') {
          return `<polyline points="${pkt(q.p)}" fill="none" stroke="#000" stroke-width="${q.w}"${
            q.streck ? ' stroke-dasharray="4.5 3.4"' : ''} stroke-linecap="round"/>`;
        }
        if (q.t === 'bage') {
          const [[ax, ay], [kx, ky], [bx, by]] = q.p;
          return `<path d="M${r2(ax)},${r2(ay)} Q${r2(kx)},${r2(ky)} ${r2(bx)},${r2(by)}" fill="none" stroke="#000" stroke-width="${q.w}"/>`;
        }
        if (q.t === 'poly') return `<polygon points="${pkt(q.p)}" fill="${q.fyll}"/>`;
        if (q.t === 'rekt') {
          return `<rect x="${r2(q.x)}" y="${r2(q.y)}" width="${r2(q.b)}" height="${r2(q.h)}" fill="${
            q.fyll || 'none'}"${q.w ? ` stroke="#000" stroke-width="${q.w}"` : ''}/>`;
        }
        if (q.t === 'prick') return `<circle cx="${r2(q.x)}" cy="${r2(q.y)}" r="${q.r}" fill="#000"/>`;
        return `<text x="${r2(q.x)}" y="${r2(q.y)}" text-anchor="${ank[q.ank]}" font-size="${q.g}"${
          q.fet ? ' font-weight="700"' : ''}>${esc(q.s)}</text>`;
      }).join('');
      return `<svg class="lofigur" data-figur="${f.typ}" viewBox="0 0 ${r2(lay.b)} ${r2(lay.h)}" role="img" aria-label="${
        attr(rad)}" style="display:block;width:calc(${r2(lay.b)}px * var(--fsk, 1));max-width:100%;height:auto;overflow:visible" font-family="Arimo, Arial, sans-serif" fill="#000">${kropp}</svg>`;
    }
    /* HTML för en figurrad, eller null när raden inte är en figurrad. En rad
       som inte går att tolka blir texten utan hakparenteser. */
    function html(rad) {
      if (!arFigurrad(rad)) return null;
      const [f] = tolka(rad);
      if (!f) return { html: matBryt(textreserv(rad)), figur: false };
      try { return { html: svg(f, rad), figur: true }; }
      catch (e) { return { html: matBryt(textreserv(rad)), figur: false }; }
    }
    return { arFigurrad, tolka, tal, layout, html, textreserv };
  })();

  /* FACIT FÖR ELEVERNA (Rickard 2026-09-26: «lösningarna är ganska svåra att
     förstå»). Ett steg med förklaring, «rad ← not» (elevradDelar), står som
     steget till vänster och «← förklaring» till höger på samma höjd, samma
     form som bedömningsanvisningens elevlösningar. En pil på svarsraden
     stryks: svaret är bara svaret. Spegel av exam_latex._facit_vy och
     \facitsteg. */
  function facitRader(grupper, bokstav) {
    return grupper.map((g, i) => {
      const bara = elevradDelar(g.svar)[0];
      const svar = i === 0 && bokstav ? bedsvar(bokstav, bara) : bara;
      return `<tr data-svar><td>${g.namn ? `<b class="lobeddel">${esc(g.namn)}</b>` : ''}${
        svar ? `<b class="lobedsvar">${matBryt(svar, true)}</b>` : ''}</td></tr>`
        + g.steg.map(s => {
          const [rad, not] = elevradDelar(s);
          /* Figurraden: tallinjen, brädan eller procentstapeln där steget
             står, med förklaringen bredvid som andra steg. */
          const fig = FACITFIGUR.html(rad);
          if (fig) {
            return not
              ? `<tr><td class="lobedsteg" data-not=""${fig.figur ? ' data-figur="" style="align-items:center"' : ''}><span class="lofacitrad">${fig.html}</span><span class="lofacitnot">← ${mat(not)}</span></td></tr>`
              : `<tr><td class="lobedsteg"${fig.figur ? ' data-figur=""' : ''}>${fig.html}</td></tr>`;
          }
          return not
            ? `<tr><td class="lobedsteg" data-not=""><span class="lofacitrad">${matBryt(rad)}</span><span class="lofacitnot">← ${mat(not)}</span></td></tr>`
            : `<tr><td class="lobedsteg">${matBryt(rad)}</td></tr>`;
        }).join('');
    }).join('');
  }
  function bladfacit(v, uppgifter) {
    const post = (u, k) => {
      /* Deluppgifterna bär var sin lösning i `vag`, «a) …» (plan.js franProv). */
      const kropp = !u.f && u.vag && u.vag.length
        ? u.vag.map((s, j) => facitRader(facitGrupper(s[0], (u.delenhet || [])[j])
          .map(g => (g.namn ? g : Object.assign(g, { namn: `${BOKSTAVER[j]})` }))))).join('')
        : facitRader(facitGrupper(u.f, u.enhet),
                     u.alt && u.ratt != null ? BOKSTAV[u.ratt] || '' : '');
      return `<div class="pruppg">
      <span class="prnr">${k + 1}.</span>
      <div><table class="lobed" data-facit=""><tbody>${kropp}</tbody></table></div></div>`;
    };
    return `<div class="ark" data-form="fa" data-brytbar="">
      <div class="lohuvud"><b>Facit</b><span>${esc(versal(v.moment || ''))}</span></div>
      <h1 class="lotitel">Svar och lösningsgång</h1>
      ${uppgifter.map(post).join('')}
    </div>`;
  }

  /* Kortsvarsarket och lösningsgångsarket ritar SAMMA rad: läraren ska
     bedöma uppgift 3 likadant vare sig den ligger i del B eller del C, och
     «gäller varje uppgift i provet» var beställningens fjärde punkt.

     Numret står ensamt i spalten. «2 p» under det sa samma sak som trippeln
     under raderna, och NP har bara numret. */
  function losRad(u) {
    return `<div class="pruppg">
      <span class="prnr">${u.nr}.</span>
      <div>${bedtabell(u)}</div></div>`;
  }

  /* ══════════ BEDÖMDA ELEVLÖSNINGAR ══════════
     Eget ark sist, som i NP (lärarens dom 2026-09-23). Per uppgift ett
     elevpapper per rad: elevens rader till vänster i handskriften (.loskann),
     poängen de ges («0/1/0») och kommentaren till höger. Läraren läser radvis,
     «så här ser 1 p ut, så här ser 2 p ut», och det syns bara när papper och
     poäng står bredvid varandra (beställningen 2026-08-23).

     Varje uppgift är en egen .pruppg med sitt nummer: blad.js markera ger den
     samma data-el som uppgiften i tabellen (uppg{n}), och elevlösningarna
     (.loskann) ärver det. En kommentar i canvas på en elevlösning gäller
     alltså fortfarande sin uppgift. Spegel av exam_latex._elevexempel. */

  /* Elevlösningens poäng som trippel. Partierna summeras: gamla dokument (och
     förlagans lo4) delar lösningen i flera partier med var sin dom. */
  function elevpoang(e) {
    const ut = [0, 0, 0];
    (e.partier || []).forEach(p => {
      const t = Array.isArray(p.poang) ? p.poang : [Number(p.poang) || 0, 0, 0];
      t.forEach((x, i) => { if (i < 3) ut[i] += Number(x) || 0; });
    });
    return ut;
  }

  /* NOLLRADEN SÄGER «INGA POÄNG» EN GÅNG. «0/0/0» står redan bredvid
     papperet, och modellen skriver ofta kommentaren som en hel mening som
     börjar likadant: «Inga poäng. Svaret är rätt, men …». Prompten ber om det
     också (exam_gen.build_bedomning_prompt), men prompten är ett önskemål och
     renderaren en regel, och papperen i basen skrevs innan önskemålet fanns.
     Spegel av app/exam_latex._utan_rubriken. */
  const UTAN_POANG = /^\s*inga\s+po[äa]ng\s*[.:;,—–-]*\s*/i;
  /* KOMMENTAREN FÅR INTE RÄKNA POÄNG EN GÅNG TILL. Poängen står redan
     bredvid, och modellen skrev «+1 E för 27, men i b testas bara ett
     exempel.», och läraren räknade märkena (prov 81, uppgift 12). Ledet fram
     till första kommat klipps när kommentaren börjar med ett poängmärke;
     utan komma stryks bara märkena. Kommat i $8{,}9$ står i klammer och
     räknas inte. Spegel av app/exam_latex._utan_stegen. */
  const POANGMARKE = /\+\s*\d+\s*[ECA]\b/g;
  const LEDET = /^\s*\+\s*\d+\s*[ECA]\b(?:\{,\}|[^,;])*[,;]\s*(?:men|och|sedan)?\s*/i;
  function utanStegen(dom) {
    const text = String(dom || '');
    let kvar = text.replace(LEDET, '');
    if (kvar === text) kvar = text.replace(POANGMARKE, '');
    kvar = kvar.replace(/\s{2,}/g, ' ').replace(/\s+([,;.])/g, '$1')
      .trim().replace(/^[,;]\s*/, '');
    return kvar ? kvar[0].toUpperCase() + kvar.slice(1) : '';
  }

  /* ── PER DELUPPGIFT OCH MED PILAR (lärarens dom 2026-09-26) ──
     «0/0/0 och en massa text under hjälper mig inte.» Varje deluppgift för
     sig med luft emellan, elevens rader med en not vid raden där poängen
     gavs («← +C korrekt ekvation», grön) och där det blev fel («← byter inte
     tecken», röd), och sist poängen i ord, «0 poäng» eller «+1 C», med
     kommentaren. Noten står i raden efter en pil utanför $…$, deluppgiften
     i etiketten («a) 0 p»). Spegel av app/exam_spec.elevrad_delar,
     elevgrupp och app/exam_latex.poangrubrik. */
  const ELEVNOT = '←';
  function elevradDelar(rad) {
    const s = String(rad == null ? '' : rad);
    let dollar = 0;
    for (let i = 0; i < s.length; i++) {
      if (s[i] === '$') dollar++;
      else if (s[i] === ELEVNOT && dollar % 2 === 0) return [s.slice(0, i).trimEnd(), s.slice(i + 1).trim()];
    }
    return [s, ''];
  }
  function elevgrupp(etikett) {
    const m = /^\s*([a-l])\)/.exec(String(etikett || ''));
    return m ? m[1] + ')' : '';
  }
  function poangrubrik(p) {
    if (!(p[0] + p[1] + p[2])) return '0 poäng';
    return p.map((n, i) => (n ? `+${n} ${'ECA'[i]}` : '')).filter(Boolean).join(', ');
  }
  const NOTMARKE = /^\+\s*(?:1\s*)?([ECA])\b[\s:.,]*/;
  function elevNot(not) {
    if (!not) return '';
    const m = NOTMARKE.exec(not);
    return m
      ? `<span class="loelevnot" data-slag="plus">← <b>+${m[1]}</b> ${mat(not.slice(m[0].length).trim())}</span>`
      : `<span class="loelevnot" data-slag="fel">← ${mat(not)}</span>`;
  }

  /* INGA ELEVLÖSNINGAR DÄR BARA SVARET RÄTTAS (lärarens dom 2026-09-26):
     «där kollar jag bara på svaren». En enhet med «Endast svar krävs» (ut
     «kort», per deluppgift `delut`) får inga bedömda elevlösningar, också
     på gamla papper som bär dem. Spegel av app/exam_spec.elevlosning_behovs. */
  function elevBehovs(u, e) {
    const del = u.delut || [];
    if (!del.length) return u.ut !== 'kort';
    const g = elevgrupp(e.etikett);
    if (g) return del['abcdefghijkl'.indexOf(g[0])] === 'rakna';
    return del.some(t => t !== 'kort');
  }
  const eleverna = u => (u.elever || []).filter(e => elevBehovs(u, e));

  function elevRad(u) {
    let forra = null;
    const rader = eleverna(u).map(e => {
      const poang = elevpoang(e), total = poang[0] + poang[1] + poang[2];
      const skrivna = (e.partier || []).reduce((a, p) => a.concat(p.rader || []), []);
      let dom = (e.partier || []).map(p => p.dom).filter(Boolean).join(' ');
      if (!total) {
        dom = dom.replace(UTAN_POANG, '').trim();
        if (dom) dom = dom[0].toUpperCase() + dom.slice(1);
      } else {
        dom = utanStegen(dom);
      }
      /* En rad med deluppgiftens bokstav före första lösningen i gruppen, med
         luft ovanför när den inte är uppgiftens första (data-del). */
      const grupp = elevgrupp(e.etikett);
      const rubrik = grupp && grupp !== forra
        ? `<tr data-del${forra === null ? ' data-forsta' : ''}><td colspan="2"><b class="loelevdel">${esc(grupp)}</b></td></tr>` : '';
      forra = grupp;
      /* Elevens rader är det som fick scrollbaren: bedömningspasset skriver
         «$A(15) = 120 - 4 \cdot 15 = 120 - 60 = 60$» som EN formel. matBryt
         delar den vid likhetstecknen så att raden kan brytas i spalten. */
      return `${rubrik}<tr${total ? '' : ' data-utan'}>
        <td colspan="2"><div class="loskann">${skrivna.map(r => {
          const [rad, not] = elevradDelar(r);
          return `<div class="loskannrad"><span class="loelevrad">${matBryt(rad)}</span>${elevNot(not)}</div>`;
        }).join('')}</div>
        <p class="lobedelevrad"><b class="lobedelevpoang">${poangrubrik(poang)}</b>${
          dom ? ` <span class="lobedvarfor">${mat(dom)}</span>` : ''}</p></td></tr>`;
    }).join('');
    return `<div class="pruppg">
      <span class="prnr">${u.nr}.</span>
      <div><table class="lobed" data-elev=""><tbody>${rader}</tbody></table></div></div>`;
  }

  const spann = l => (l.length === 1 ? `uppgift ${l[0].nr}` : `uppgift ${l[0].nr}–${l[l.length - 1].nr}`);
  function elevark(uppgifter) {
    const med = uppgifter.filter(u => eleverna(u).length);
    if (!med.length) return '';
    return `<div class="ark" data-form="lo-elev" data-brytbar="">
      <div class="lohuvud"><b>Bedömningsanvisning · elevlösningar</b><span>${versal(spann(med))}</span></div>
      <h1 class="lotitel">Exempel på lösningar med bedömning</h1>
      ${med.map(elevRad).join('')}</div>`;
  }

  /* Kortsvarsfacit för del A, utskriven lösningsgång för del B, och de
     bedömda elevlösningarna sist. Ett facit som bara svarar på halva provet
     ska säga det, därför räknas uppgifterna. */
  function losning(v, uppgifter, delB) {
    const b = uppgifter.filter(u => u.nr <= delB);
    const c = uppgifter.filter(u => u.nr > delB);
    const ut = [];
    /* PAPPRETS NAMN ÄR «BEDÖMNINGSANVISNING» (lärarens beslut 2026-08-23).
       «Lösningsförslag» stod kvar från när arket bara bar facit; nu bär det
       poängraderna och de bedömda elevlösningarna, och det är en anvisning
       att rätta efter. Namnet står likadant på fliken, i PDF:ens titel, i
       tryckpaketet och i kvittot — arbetsbladets och gruppuppgiftens facit
       heter fortfarande «Lösningsförslag» respektive «Facit». */
    /* EN GÅNG, under första arkets rubrik (lärarens dom 2026-09-23).
       Notisen stod förut under varje uppgift som hade elevexempel, alltså
       under nästan alla, och det var just den sortens upprepade text hon
       ville bort ifrån. Bara när det finns ett ark att hänvisa till. PDF:en
       säger samma sak efter kravgränsraden (bedomning.tex.j2). */
    const inledning = uppgifter.some(u => eleverna(u).length)
      ? '<p class="lolede">Exempel på lösningar med bedömning står sist i häftet.</p>' : '';
    if (b.length) ut.push(`<div class="ark" data-form="lo-b" data-brytbar="">
      <div class="lohuvud"><b>Bedömningsanvisning · kortsvar</b><span>${delB >= uppgifter.length ? versal(spann(b)) : DELNAMN.B + ' · ' + spann(b)}</span></div>
      <h1 class="lotitel">Endast svar krävs</h1>${inledning}
      ${b.map(losRad).join('')}</div>`);
    if (c.length) ut.push(`<div class="ark" data-form="lo-c" data-brytbar="">
      <div class="lohuvud"><b>Bedömningsanvisning · ${DELNAMN.C.toLowerCase()}</b><span>${DELNAMN.C} · ${spann(c)}</span></div>
      <h1 class="lotitel">Hela lösningen krävs</h1>${b.length ? '' : inledning}
      ${c.map(losRad).join('')}</div>`);
    const elever = elevark(uppgifter);
    if (elever) ut.push(elever);
    return ut;
  }

  /* `kortref` delas med blad-boklos.js: bokens lösningsark ska korta på samma
     sätt som provets och arbetsbladets, annars är det två olika facit. */
  return { mat, kortref, ref, ark, arkfacit, provforsatt, provblad,
           forsattsbild, losning, provtitel, BOKSTAV, delnamnVisning,
           hjalpmedelsfras, hjalpmedelsval, bildlager, bildForhallande,
           facitfigur: FACITFIGUR };
})();
