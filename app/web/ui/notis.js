/* ══════════ OBS-RADEN I STEG 1 ══════════
   Att ingen lektion är markerad var förr en toast som flög upp ur fönstrets
   underkant tio sekunder efter att man klickat på ett lägeskort. Den kom i ett
   annat rum än frågan den handlade om — man höll på med «vad ska du skapa?» och
   fick svaret nere vid skärmkanten — och när remsan tickat ut fanns inget spår
   av vad appen just sagt. Nu står det som en rad i själva steget, till vänster
   om Nästa: den tänds i samma klick som lägeskortet och står kvar så länge ingen
   lektion är markerad. Den hindrar ingen. Nästa gör precis som förut. */
(() => {
  const $ = s => document.querySelector(s);
  const obs = $('#lagenobs');
  if (!obs) return;
  /* Raden «Ingen lektion vald» i kvittot ÄR sanningen om läget — plan.js och
     plankon.js styr den. OBS-raden läser av den i stället för att räkna ut samma
     sak en andra gång; står samma sanning på två ställen blir de osams. */
  const ingenVald = () => { const p = $('#planingen'); return !!p && !p.hidden; };
  /* Raden är ett svar på något man gjort, inte ett tillstånd som ligger framme:
     förvalet «Tavla» är inget val läraren tagit, och då har appen inget att säga
     än. Först när ett kort klickas börjar man skapa. */
  let rort = false;
  const rita = () => { obs.hidden = !(rort && ingenVald()); };
  document.addEventListener('click', e => {
    if (!e.target.closest || !e.target.closest('#lagesval .lagekort')) return;
    rort = true;
    rita();
  });
  /* Markeras en lektion är raden klar. Släpps lektionen igen ska den inte komma
     tillbaka av sig själv — den hör till klicket på korten, inte till veckan. */
  const p = $('#planingen');
  if (p) new MutationObserver(() => { if (!ingenVald()) rort = false; rita(); })
    .observe(p, { attributes: true, attributeFilter: ['hidden'] });
  rita();
})();
