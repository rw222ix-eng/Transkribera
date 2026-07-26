<script>
  // Filterraden. TVÅ OLIKA SORTERS FILTER, medvetet hållna isär:
  //
  //   KLASS + KURS  → SERVERN. De ligger i querysträngen till /api/lessons, så
  //                   valjKlass/valjKurs anropar laddaLektioner() explicit.
  //   MÅNAD         → KLIENTEN. Filtrerar den redan hämtade listan i
  //                   InspelningarView. Inget nätverksanrop.
  //
  // Slås de ihop till en enda reaktiv kedja slutar omhämtningen tyst att ske,
  // och klass-/kursfiltret ser ut att fungera medan det bara filtrerar en
  // föråldrad lista.
  //
  // Vanliga <select>, inte gamla appens popover-menyer (filterDrop,
  // app.js:5232): en native select är tangentbordstillgänglig gratis och
  // popovern bär ingen mening som selecten saknar.
  import { insp } from './stores.svelte.js';
  import { valjKlass, valjKurs, valjManad, rensaFilter } from './actions.js';

  // Månaderna härleds ur den HÄMTADE listan, inte ur en egen endpoint — samma
  // sak som gamla appen gör (app.js:3443). Nyaste först.
  const manader = $derived.by(() => {
    const s = new Set();
    for (const l of insp.lessons) {
      const m = String(l.datum || '').slice(0, 7);
      if (m) s.add(m);
    }
    // Den VALDA månaden hålls kvar även om ingen kvarvarande lektion har den.
    // Ett klassbyte kan annars ta bort den ur listan medan insp.filterMonth
    // står kvar: Svelte hittar då ingen matchande option, sätter
    // selectedIndex = -1, och läraren ser en tom ruta över ett tomt kartotek
    // utan att kunna se vad som filtrerar bort allt — eller välja bort det.
    if (insp.filterMonth && !s.has(insp.filterMonth)) s.add(insp.filterMonth);
    return [...s].sort().reverse();
  });

  // MÅNADEN ÄR MED HÄR OCH MEDVETET INTE i tomtillståndets villkor i
  // InspelningarView.svelte. Skillnaden ser ut som en slarvig dubblett och är
  // det inte — harmonisera dem inte, det återinför precis det fel Task 3:s
  // granskning fångade.
  //
  //   HÄR frågar villkoret "döljer något av filtren något?" — och månaden
  //   döljer, den filtrerar den hämtade listan på klienten. Utan den kan läraren
  //   välja en månad, se kartoteket krympa, och sakna vägen tillbaka: Rensa alla
  //   syns inte.
  //
  //   DÄR frågar villkoret "kan ett filter förklara att insp.lessons är TOM?" —
  //   och det kan månaden aldrig, eftersom den inte rör hämtningen. Är listan
  //   tom är den tom av andra skäl; är den inte tom faller fallet till andra
  //   tomtillståndsgrenen ändå. Läggs månaden till där får en lärare med
  //   verkligt tomt arkiv beskedet "Inga inspelningar matchar dina filter".
  const nagotAktivt = $derived(!!(insp.filterGroup || insp.filterCourse || insp.filterMonth));
</script>

<div class="filter">
  <label class="falt">
    <span class="etikett">KLASS</span>
    <select value={insp.filterGroup} onchange={(e) => valjKlass(e.currentTarget.value)}>
      <option value="">Alla klasser</option>
      {#each insp.groups as g (g.id)}<option value={String(g.id)}>{g.namn}</option>{/each}
    </select>
  </label>

  <label class="falt">
    <span class="etikett">KURS</span>
    <select value={insp.filterCourse} onchange={(e) => valjKurs(e.currentTarget.value)}>
      <option value="">Alla kurser</option>
      {#each insp.courses as c (c.id)}<option value={String(c.id)}>{c.namn}</option>{/each}
    </select>
  </label>

  <label class="falt">
    <span class="etikett">MÅNAD</span>
    <select value={insp.filterMonth} onchange={(e) => valjManad(e.currentTarget.value)}>
      <option value="">Alla månader</option>
      {#each manader as m (m)}<option value={m}>{m}</option>{/each}
    </select>
  </label>

  {#if nagotAktivt}
    <button type="button" class="rensa" onclick={rensaFilter}>Rensa alla</button>
  {/if}
</div>

<style>
  .filter {
    display: flex;
    flex-wrap: wrap;
    align-items: end;
    gap: 12px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--line);
  }
  .falt {
    display: flex;
    flex-direction: column;
    gap: 5px;
    min-width: 0;
  }
  /* Den ENDA platsen i den här vyn där var(--mono) hör hemma: en kort, versal
     mikroetikett. Kortens och veckorubrikernas texter är löpande text och
     bär den inte. */
  .etikett {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    color: var(--ink-3);
  }
  select {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 3px;
    padding: 8px 10px;
    font-family: inherit;
    font-size: 1.03rem;
    color: var(--ink);
    max-width: 100%;
  }
  select:focus-visible { border-color: var(--accent); }
  /* Samma form som .ghost i Lektionskort.svelte — knappen är sekundär och ska
     inte konkurrera med selecterna. margin-left: auto lägger den sist på raden. */
  .rensa {
    margin-left: auto;
    background: transparent;
    color: var(--ink-2);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 9px 18px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
</style>
