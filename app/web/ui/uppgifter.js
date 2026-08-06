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
    const u = alla();
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
  function synka() {
    const ny = nyckelNu();
    if (ny === nyckel) return false;
    nyckel = ny;
    forslag = forslaget();
    bort = new Set(forslag.map(f => f.nr));
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
    window.API.json(`/api/bocker/${id}/uppslag?fran=${s.fran}&till=${s.till}`)
      .then(d => {
        if (nyckelNu() !== nyck) return;         // spannet hann bytas
        serverdata = { nyckel: nyck, uppgifter: d.uppgifter || [] };
        forslag = forslaget();
        bort = new Set(forslag.map(f => f.nr));
        rita();
        window.planKoll && window.planKoll();
        if ((d.olasta || []).length) lasSidorna(id, s, nyck);
      })
      .catch(() => {});
  }

  function lasSidorna(id, s, nyck) {
    const host = $('#uppgsvar');
    if (!host || laser) return;
    laser = true;
    const klart = () => { laser = false; if (nyckelNu() === nyck) hamta(); };
    const jobb = ({ signal, log }) => window.API.strom(
      `/api/bocker/${id}/las`,
      { fran: s.fran, till: s.till, bara: 'fakta' }, { signal, log });
    if (window.Fraga && window.Fraga.kor) {
      window.Fraga.kor(host, {
        enkel: true, jobb,
        jobbtext: `Slår upp s. ${s.fran}–${s.till} i ${s.bok} …`,
        svar: r => r && r.uppgifter && r.uppgifter.length
          ? `Sidorna är uppslagna — ${r.uppgifter.length} uppgifter står där.`
          : 'Sidorna är uppslagna.',
        efterKlar: klart, efterFel: () => { laser = false; },
      });
    } else {
      jobb({}).then(klart, () => { laser = false; });
    }
  }
  const rort = () => {
    const f = new Set(forslag.map(x => x.nr));
    return bort.size !== f.size || [...bort].some(n => !f.has(n));
  };

  /* ── Panelen ───────────────────────────────────────
     Chipsen står i bokens ordning, tre rader — en per nivå. En bortvald uppgift
     försvinner inte ur listan, den får streck över: det är boken man läser av,
     och boken byter inte ordning för att man hoppar en uppgift. */
  const NIVA = [1, 2, 3];
  function rita() {
    const u = alla();
    vard.hidden = !u.length;
    if (!u.length) return;
    const kvar = u.filter(x => !bort.has(x.nr));
    const fanns = !!$('#uppgfraga');
    if (!fanns) {
      vard.innerHTML = `<div class="uppghuvud"><span class="minietikett" style="margin:0">Uppgifterna på sidorna</span><span class="uppgant" id="uppgant"></span></div>
        <p class="uppgforslag" id="uppgforslag"></p>
        <button class="lank uppgater" id="uppgater" type="button" hidden>Tillbaka till förslaget</button>
        <div class="uppgnivaer" id="uppgnivaer"></div>
        <div class="uppgfragarad"><input class="field" id="uppgfraga" autocomplete="off" aria-label="Ändra urvalet av uppgifter" /><button class="ghost" id="uppgskicka" type="button">Fråga</button></div>
        <div class="uppgsvar" id="uppgsvar" hidden></div>`;
      $('#uppgater').addEventListener('click', () => {
        bort = new Set(forslag.map(f => f.nr));
        $('#uppgsvar').hidden = true;
        rita();
        window.planKoll && window.planKoll();
      });
      $('#uppgskicka').addEventListener('click', () => fraga($('#uppgfraga').value));
      $('#uppgfraga').addEventListener('keydown', e => {
        if (e.key === 'Enter') { e.preventDefault(); fraga($('#uppgfraga').value); }
      });
    }
    $('#uppgant').textContent = `${kvar.length} av ${u.length} att räkna`;
    /* Fältet är för det man INTE kan klicka fram: att hoppa en hel nivå, att
       hålla sig till de tillämpade uppgifterna. En enskild uppgift klickas i
       listan ovanför, och ett exempel på just det i platshållaren fick läraren att
       skriva det i onödan. */
    $('#uppgfraga').placeholder = 'T.ex. «hoppa nivå 1» eller «bara de tillämpade uppgifterna»';
    if (!rort()) $('#uppgforslag').textContent = forslagsText(forslag);
    $('#uppgater').hidden = !rort();
    const rader = $('#uppgnivaer');
    rader.innerHTML = '';
    NIVA.forEach(n => {
      const del = u.filter(x => x.niva === n);
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
      rader.appendChild(rad);
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
    const u = alla();
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
    return alla().filter(x => !bort.has(x.nr) && f.includes(x.niva));
  };

  window.Uppgifter = {
    /* Steg 3 frågar om raden ska finnas alls: lösningsförslag till bokens
       uppgifter går bara att välja när boken faktiskt är en av källorna. */
    finns: () => !!(dorr && dorr.getAttribute('aria-pressed') === 'true' && alla().length),
    losningsantal: niva => losningarna(niva).length,
    avsnittsnamn: () => { const a = avsnittet(); return a ? `${a.nr} ${a.titel}` : 'avsnittet'; },
    /* Noten i steg 3 får bara plats på en rad, och där duger numret: rubriken står
       redan i kvittot ovanför. En not som radbryts sköt pricken upp på en egen rad. */
    avsnittsnr: () => { const a = avsnittet(); return a ? a.nr : 'avsnittet'; },
    /* Snapshot, inte uppslag: en tavla i Sparat ska peka på de uppgifter den
       skrevs för, även efter att spannet ändrats i planeringen. */
    urval(instans) {
      if (!window.Uppgifter.finns()) return null;
      const s = spann(), u = alla();
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
        losning: i.boklosning === false ? null : { niva: i.boklosniva || 'Nivå 2 och 3', antal: los.length, uppg: los.map(x => x.nr), poster: los.map(x => ({ nr: x.nr, niva: x.niva })), remsa: remsa(los.map(x => x.nr)) }
      };
    }
  };

  synka();
  rita();
})();
