<script>
  // Anteckningsmodalen — läsning OCH redigering i en och samma ruta. Gamla
  // appen hade två (ovDescView läste, descModal redigerade, växlade via
  // descModalFor). Den här modalen slår ihop läs- och redigeringsläget till
  // EN modal — descModalFor behövs alltså inte — men delas ändå av BÅDA
  // värdarna (lektionschatt och arkivsvar): `kal.anteckningOppen` bär
  // VÄRDNYCKELN för förslaget som redigeras i stället för en ren boolean
  // (se stores.svelte.js), så en enda global modalinstans (App.svelte)
  // räcker utan en egen `vardnyckel`-prop.
  import { kal } from './stores.svelte.js';
  import { satAnteckning, stangAnteckning } from './actions.js';

  let dialog = $state(null);

  const vard = $derived(kal.anteckningOppen);
  const f = $derived(vard ? kal.forslag[vard] : null);

  // Stängs också om förslaget försvinner medan rutan är öppen (Avfärda,
  // Lägg till, eller ett nytt [KALENDERFÖRSLAG] som ersätter det gamla) —
  // annars stod textarean kvar bunden till ett förslag som inte längre
  // finns.
  $effect(() => {
    if (!dialog) return;
    if (vard && f) {
      if (!dialog.open) {
        dialog.showModal();
        dialog.focus();
      }
    } else if (dialog.open) {
      dialog.close();
    }
  });

  /**
   * D8 (rekon §11): läsmodalen (ovDescView) saknade Escape-hantering HELT i
   * gamla appen — Escape föll då vidare till lektionsoverlayens egen
   * Escape-gren och stängde HELA chatten, med förslaget kvar dolt bakom.
   * showModal() ger Escape gratis och skopat till BARA den här dialogen:
   * native <dialog>-beteende stänger den TOPPMODALA dialogen, aldrig dess
   * förfäder. Det är hela fixen — ingen egen keydown-hanterare behövs.
   *
   * Tandkontrollerat (se kalender-2-report.md): byts showModal() nedan ut
   * mot dialog.show() (icke-modal) återkommer exakt den gamla buggen,
   * eftersom Escape då i stället hanteras av lektionschattens EGEN,
   * fortfarande modala dialog.
   */
  function paClose() {
    stangAnteckning();
  }

  function paAnteckning(e) {
    satAnteckning(vard, e.currentTarget.value);
  }
</script>

<dialog
  class="ruta"
  aria-label="Anteckning i kalenderposten"
  tabindex="-1"
  bind:this={dialog}
  onclose={paClose}
>
  {#if f}
    <div class="topp">
      <h2 class="titel">Anteckning i kalenderposten</h2>
      <button type="button" class="ghost" onclick={stangAnteckning}>Stäng</button>
    </div>
    <textarea
      class="falt"
      rows="10"
      value={f.anteckning}
      oninput={paAnteckning}
      aria-label="Anteckning i kalenderposten"
    ></textarea>
    <p class="hjalp">Sparas direkt · Escape eller Stäng för att gå tillbaka.</p>
  {/if}
</dialog>

<style>
  /* Receptet är LektionschattModal.svelte:87-104:s. */
  .ruta {
    width: min(94vw, 560px);
    max-height: 90vh;
    overflow: auto;
    background: var(--surface);
    color: var(--ink);
    border: 1px solid var(--line);
    border-radius: 5px;
    box-shadow: var(--shadow);
    padding: 20px 22px;
  }
  .ruta[open] { display: block; }
  .ruta::backdrop { background: color-mix(in srgb, var(--ink) 42%, transparent); }
  .ruta:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

  .topp {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 12px;
  }
  /* Identisk med .titel i LektionschattModal.svelte:117-124. */
  .titel {
    font-family: var(--sans);
    font-size: 1.125rem;
    font-weight: 600;
    line-height: 1.3;
    margin: 0;
    overflow-wrap: anywhere;
  }
  /* Identisk med .ghost i transkribera/Korning.svelte:284-293. */
  .ghost {
    background: transparent;
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 9px 16px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }

  .falt {
    width: 100%;
    box-sizing: border-box;
    background: var(--surface);
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 3px;
    padding: 10px 12px;
    font-family: inherit;
    font-size: 1.03rem;
    line-height: 1.55;
    resize: vertical;
  }
  .falt:focus-visible { border-color: var(--accent); }

  /* Identisk med .hjalp i Forslagsbox.svelte:225-229. */
  .hjalp {
    font-size: 0.72rem;
    color: var(--ink-3);
    margin: 8px 0 0;
  }
</style>
