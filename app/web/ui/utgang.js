/* ══════════ LEKTIONENS LÄSNING ══════════
   Filen hette förr utgångspunkterna och ritade kort ovanför veckokalendern: ett
   för klassens senast rättade prov, ett för den senaste transkriberade
   lektionen. Båda är borta, och båda av samma skäl — de sa samma sak en gång
   till, på fel plats. Kortet ovanför kalendern kunde dessutom peka på ett prov
   i maj medan kalendern stod på en lektion i juni, och då räknade «Följer med
   från lektionen» upp juni-lektionens papper under provets rubrik. Läraren
   läste det som ett och samma val.

   Transkriptets läsning och överraden lånades av minikalendern i
   lektionspanelen (lektionskal.js), som togs bort med arkivet 2026-10-07. Kvar
   är rutan #utgangnat, som töms och göms. Den står kvar i DOM:en eftersom
   kallor.js läser den när panelen är tom. */
(() => {
  const nat = document.querySelector('#utgangnat');
  if (!nat) return;

  function rita() {
    nat.innerHTML = '';
    nat.hidden = true;
  }

  window.Utgang = { rita };
  rita();
})();
