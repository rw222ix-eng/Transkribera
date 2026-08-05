/* ══════════ LEKTIONENS LÄSNING ══════════
   Filen hette förr utgångspunkterna och ritade kort ovanför veckokalendern: ett
   för klassens senast rättade prov, ett för den senaste transkriberade
   lektionen. Båda är borta, och båda av samma skäl — de sa samma sak en gång
   till, på fel plats. Transkriptet bor i kalendern där lektionen väljs; provet
   har sin egen dörr med sin egen lista. Kortet ovanför kalendern kunde dessutom
   peka på ett prov i maj medan kalendern stod på en lektion i juni, och då
   räknade «Följer med från lektionen» upp juni-lektionens papper under provets
   rubrik. Läraren läste det som ett och samma val.

   Kvar finns läsningen av transkriptet och överraden — veckokalendern lånar dem
   — och rutan #utgangnat, som töms och göms. Den står kvar i DOM:en eftersom
   kallor.js läser den när panelen är tom. */
(() => {
  const $ = (s, r) => (r || document).querySelector(s);
  const nat = $('#utgangnat');
  if (!nat) return;

  /* Överraden ska gå att läsa i en blick: veckodag, datum, vecka och en längd i
     ord — inte 42:11, som är en tid på dygnet i läsarens huvud. */
  const dagdatum = d => {
    const x = new Date(String(d) + 'T12:00:00');
    if (isNaN(x)) return String(d || '');
    const dag = x.toLocaleDateString('sv-SE', { weekday: 'short' }).replace('.', '');
    const kort = x.toLocaleDateString('sv-SE', { day: 'numeric', month: 'short' }).replace(/\./g, '');
    return dag.charAt(0).toUpperCase() + dag.slice(1) + ' ' + kort;
  };
  const veckan = d => (d && window.Kalender && window.Kalender.veckonr) ? 'v' + window.Kalender.veckonr(d) : '';
  const langden = t => {
    const m = String(t || '').match(/(\d{1,2})[:.](\d{2})/);
    return m ? `${+m[1]} min ${+m[2]} s` : String(t || '');
  };
  const overrad = (datum, langd) => [dagdatum(datum), veckan(datum), langden(langd)].filter(Boolean).join(' · ');

  /* Transkriptets läsning. I appen kommer den ur den faktiska transkriptionen;
     i spegeln är den simulerad men stabil per lektion — samma lektion ger samma
     läsning, annars läser man en tärning. */
  function las(l) {
    const frö = [...l.namn].reduce((a, c) => a + c.charCodeAt(0), 0);
    const total = 7, hann = 5 - (frö % 2);
    const kvarnamn = ['övningen i par', 'sammanfattningen', 'det sista exemplet'].slice(0, total - hann - 4 > 0 ? 3 : 2);
    return {
      rad: `Ni hann ${hann} av ${total} moment — ${kvarnamn.join(' och ')} nämns aldrig i transkriptet.`,
      punkter: [
        `${kvarnamn[0][0].toUpperCase()}${kvarnamn[0].slice(1)} hanns inte med`,
        'Du säger mot slutet att ni tar om det nästa gång',
        `${2 + (frö % 3)} elever var klara med bokens uppgifter före tiden`,
        'Två frågor om samma steg i uträkningen'
      ]
    };
  }

  function rita() {
    nat.innerHTML = '';
    nat.hidden = true;
  }

  window.Utgang = { rita, las, overrad, langden, dagdatum, veckan };
  rita();
})();
