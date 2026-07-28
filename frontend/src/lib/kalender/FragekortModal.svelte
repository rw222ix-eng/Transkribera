<script>
  // Frågekortet (calQ i gamla appen, STEG 1 i llm_client._cal_instr) — de 1-3
  // klargörande frågorna modellen ställer INNAN den föreslår en händelse.
  // tolkaFragor() (kalender/tagg.js) gör tolkningen och öppnar kal.fragor;
  // den här komponenten är bara UI:t ovanpå den storen.
  //
  // DELAS AV BÅDA VÄRDARNA (lektionschatt och arkivsvar) via props i stället
  // för att importera lektionschattens store/actions rakt av — kalender/ har
  // annars noll importer utanför sin egen mapp, och den egenskapen ska
  // gälla även UI-lagret. Varje mount (App.svelte) binder sin egen
  // `vardnyckel`, `onSkicka` och `skickar`.
  import { kal } from './stores.svelte.js';
  import { valjAlternativ, satFritext } from './actions.js';

  let { vardnyckel, onSkicka, skickar = false } = $props();

  let dialog = $state(null);

  // Bara MINA frågor — kal.fragor är ETT delat fält (se stores.svelte.js)
  // med en `vard` som pekar ut ägaren. Utan den här filtreringen skulle
  // BÅDA värdarnas instanser rendera samma innehåll samtidigt.
  const minaFragor = $derived(kal.fragor && kal.fragor.vard === vardnyckel ? kal.fragor : null);

  // Alltid monterad, aldrig {#if}-grindad (DESIGN-kravet, se
  // LektionschattModal.svelte — samma mönster). showModal() ger fokusfälla,
  // Escape och backdrop gratis, och top-layer gör att kortet lägger sig
  // ovanpå den redan öppna, redan modala lektionschatten utan eget z-index.
  $effect(() => {
    if (!dialog) return;
    if (minaFragor) {
      if (!dialog.open) {
        dialog.showModal();
        // Rutan själv: då läser skärmläsaren rubriken innan ett alternativ.
        dialog.focus();
      }
    } else if (dialog.open) {
      dialog.close();
    }
  });

  // Escape/backdrop stängs av webbläsaren, inte av oss — onclose nollställer
  // storen. Utan den raden kunde en NY [KALENDERFRÅGOR]-tagg inte öppna
  // kortet igen (samma resonemang som LektionschattModal.svelte:28-31).
  //
  // VAKTAD på `vard`: när kal.fragor byter ägare (den ANDRA värdens instans
  // öppnar sin dialog) stänger effekten ovan den här instansen
  // programmatiskt, vilket ÄVEN utlöser onclose — utan vakten skulle den
  // stängningen nollställa kal.fragor och släcka den nya ägarens frågor
  // innan de ens hunnit visas.
  function paClose() {
    if (kal.fragor && kal.fragor.vard === vardnyckel) kal.fragor = null;
  }

  const kanSkicka = $derived(
    !!minaFragor
      && (minaFragor.fragor.some((f) => f.val) || !!(minaFragor.fritext || '').trim()),
  );

  function byggText(skip) {
    const fr = minaFragor;
    if (skip) return 'Skapa kalenderhändelsen direkt med rimliga antaganden.';
    const delar = fr.fragor.map((f) => f.fraga + ' Svar: ' + (f.val || 'inget särskilt'));
    if ((fr.fritext || '').trim()) delar.push('Övrigt önskemål: ' + fr.fritext.trim());
    return delar.join(' · ') + ' — skapa nu kalenderhändelsen med en detaljerad anteckning utifrån detta.';
  }

  /**
   * D2 (rekon §11): gamla appens calQSubmit nollställde calQ FÖRE anropet
   * till sendLessonChat, som var en TYST no-op om ett svar redan strömmade
   * (S.lessonChatTyping) — lärarens val och fritext försvann spårlöst, utan
   * felmeddelande. Fixen är dubbel:
   *   1. `disabled={skickar}` på knapparna nedan gör dem otryckbara medan
   *      ett svar är i luften — spärrat, inte tyst.
   *   2. Samma villkor upprepas här, på funktionsnivå: kortet stängs ALDRIG
   *      (kal.fragor nollställs inte) förrän vi vet att sändningen
   *      faktiskt går iväg. Anroparens `onSkicka` (skickaFraga för
   *      lektionschatten, skickaKalenderSvar för arkivsvaret) har samma
   *      vakt, så det här är försvar i djupet snarare än den enda spärren —
   *      men det är just den ordningen (kolla FÖRE stängning, inte stäng
   *      och hoppas) som var bugg i gamla appen.
   *
   * I praktiken kan grenen inte nås via UI:t för lektionschatten:
   * showModal() gör dess skrivfält inert medan kortet är öppet. Arkivsvaret
   * har ingen motsvarande modal, men `stallFoljdfraga`/`skickaKalenderSvar`
   * har sin egen vakt (sokActions.js), så vakten här kostar en rad och tar
   * bort beroendet av att den ALLTID hinner före.
   */
  async function paSvara(skip) {
    if (skickar || !minaFragor) return;
    const text = byggText(skip);
    kal.fragor = null;
    await onSkicka(text);
  }
</script>

<dialog
  class="ruta"
  aria-label="Kalenderhändelsen — några frågor först"
  tabindex="-1"
  bind:this={dialog}
  onclose={paClose}
>
  {#if minaFragor}
    <p class="eyebrow">Kalenderhändelsen</p>
    <h2 class="titel">Några frågor först</h2>
    <p class="lede">
      Svara på det som känns relevant så blir händelsen detaljerad och rätt —
      resten antar jag åt dig.
    </p>

    <ol class="fragor">
      <!-- INDEXNYCKEL, avsiktligt: frågekortet sätts i sin helhet av modellen
           och listan ändrar aldrig längd medan den visas — bara f.val muteras.
           qi är dessutom den identitet svaren lagras under. -->
      {#each minaFragor.fragor as f, qi (qi)}
        <li class="fraga-rad">
          <p class="fraga">{f.fraga}</p>
          <div class="alternativ" role="group" aria-label={f.fraga}>
            {#each f.alternativ as a (a)}
              <button
                type="button"
                class="chip"
                aria-pressed={f.val === a}
                onclick={() => valjAlternativ(qi, a)}
              >{a}</button>
            {/each}
          </div>
        </li>
      {/each}
    </ol>

    <label class="fritext-etikett">
      <span class="etikett">Egna önskemål</span>
      <textarea
        class="falt"
        rows="2"
        placeholder="Egna önskemål — t.ex. exakt vad anteckningen ska innehålla …"
        value={minaFragor.fritext}
        oninput={(e) => satFritext(e.currentTarget.value)}
      ></textarea>
    </label>

    {#if skickar}
      <p class="vantar">Väntar på föregående svar — knapparna går att trycka igen om ett ögonblick.</p>
    {/if}

    <div class="knappar">
      <button type="button" class="ghost" disabled={skickar} onclick={() => paSvara(true)}>
        Skapa direkt utan svar
      </button>
      <button
        type="button"
        class="primar"
        disabled={skickar || !kanSkicka}
        onclick={() => paSvara(false)}
      >Skapa förslaget</button>
    </div>
  {/if}
</dialog>

<style>
  /* Receptet är LektionschattModal.svelte:87-104:s — samma centrering via
     showModal(), samma display-fälla (se kommentaren där: en författarregel
     slår webbläsarens dialog:not([open]) { display: none } oavsett
     specificitet). */
  .ruta {
    width: min(94vw, 540px);
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

  /* Identisk med .eyebrow i Forslagsbox.svelte:124-131. */
  .eyebrow {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
    margin: 0 0 6px;
  }
  /* Identisk med .titel i LektionschattModal.svelte:117-124. */
  .titel {
    font-family: var(--sans);
    font-size: 1.125rem;
    font-weight: 600;
    line-height: 1.3;
    margin: 0 0 8px;
    overflow-wrap: anywhere;
  }
  .lede {
    color: var(--ink-2);
    margin: 0 0 16px;
  }

  .fragor {
    list-style: none;
    margin: 0 0 14px;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .fraga-rad { margin: 0; }
  .fraga { margin: 0 0 6px; font-weight: 500; }
  .alternativ { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip {
    background: var(--sunken);
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 3px;
    padding: 6px 12px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
  .chip[aria-pressed='true'] {
    background: var(--accent-weak);
    color: var(--accent);
    border-color: var(--accent);
  }

  .fritext-etikett {
    display: flex;
    flex-direction: column;
    gap: 5px;
    margin: 0 0 6px;
  }
  .etikett { font-size: 0.72rem; color: var(--ink-3); }
  /* Receptet är Skrivrad.svelte:53-65:s. */
  .falt {
    background: var(--surface);
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 3px;
    padding: 8px 10px;
    font-family: inherit;
    font-size: 1.03rem;
    line-height: 1.45;
    resize: vertical;
    width: 100%;
    box-sizing: border-box;
  }
  .falt:focus-visible { border-color: var(--accent); }

  /* Samma stil som Forslagsbox.svelte:225-229:s .hjalp — en hjälptext, inte
     en live-region: se paSvara()-kommentaren om varför grenen inte går att
     nå via UI:t. */
  .vantar {
    font-size: 0.72rem;
    color: var(--ink-3);
    margin: 0 0 8px;
  }

  .knappar {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 6px;
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
  .ghost:disabled { opacity: 0.55; cursor: default; }
  /* Identisk med .primar i transkribera/Korning.svelte:273-283. */
  .primar {
    background: var(--btn-bg);
    color: var(--btn-fg);
    border: none;
    border-radius: 4px;
    padding: 9px 16px;
    font-family: inherit;
    font-size: inherit;
    font-weight: 500;
    cursor: pointer;
  }
  .primar:disabled { opacity: 0.55; cursor: default; }
</style>
