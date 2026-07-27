<script>
  // Modellens klargörande frågor innan den skapar en kalenderhändelse.
  // Speglar calQ-modalen (app/web/static/app.js:2719-2764).
  //
  // Frågorna kommer som en maskinläsbar [KALENDERFRÅGOR]-rad med två till fyra
  // alternativ var — ett klick per fråga, aldrig fritext som enda väg. Läraren
  // ska kunna hoppa över alltihop: att tvingas svara på tre frågor för att få
  // en kalenderhändelse är värre än en händelse som gissar rimligt.
  import { sok } from './sok.svelte.js';
  import { valjFragesvar, satFrageExtra, skickaFragesvar, stangFragor } from './sokActions.js';
  import { nav } from '../shell/nav.svelte.js';

  // NATIVE <dialog> + showModal(), alltid monterad. Samma val och samma skäl
  // som RedigeraLektion.svelte och Kallmodal.svelte — läs kommentarerna där.
  let ruta = $state(null);
  $effect(() => {
    if (!ruta) return;
    if (sok.kalFragor && nav.tab === 'inspelningar') {
      if (!ruta.open) {
        ruta.showModal();
        ruta.focus();
      }
    } else if (ruta.open) {
      ruta.close();
    }
  });
</script>

<dialog
  bind:this={ruta}
  class="fragor"
  aria-label="Frågor om kalenderhändelsen"
  onclose={stangFragor}
  tabindex="-1"
>
  {#if sok.kalFragor}
    <p class="etikett">Innan händelsen skapas</p>

    {#each sok.kalFragor.fragor as f, i (i)}
      <fieldset class="fraga">
        <legend class="fragetext">{f.q}</legend>
        <div class="alternativ">
          {#each f.alternativ as alt (alt)}
            <button class="alt" aria-pressed={f.val === alt} onclick={() => valjFragesvar(i, alt)}>
              {alt}
            </button>
          {/each}
        </div>
      </fieldset>
    {/each}

    <label class="falt">
      <span class="faltnamn">Något mer?</span>
      <input
        class="input"
        value={sok.kalFragor.extra}
        oninput={(e) => satFrageExtra(e.currentTarget.value)}
        placeholder="Valfritt"
      />
    </label>

    <div class="knappar">
      <button class="ghost" onclick={() => skickaFragesvar(true)}>Hoppa över</button>
      <button class="primar" onclick={() => skickaFragesvar(false)}>Skapa händelsen</button>
    </div>
  {/if}
</dialog>

<style>
  .fragor {
    width: min(520px, calc(100vw - 48px));
    max-height: min(80vh, 620px);
    overflow: auto;
    background: var(--surface);
    color: var(--ink);
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 16px 18px;
  }
  /* Samma backdrop som vyns övriga dialoger. */
  .fragor::backdrop { background: color-mix(in srgb, var(--ink) 42%, transparent); }
  .fragor:focus-visible { outline: none; }

  .etikett {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
    margin: 0 0 14px;
  }

  /* fieldset/legend, inte div/p: varje fråga med sina alternativ ÄR en grupp,
     och då hör frågetexten ihop med knapparna även för en skärmläsare. */
  .fraga {
    border: 0;
    padding: 0;
    margin: 0 0 14px;
  }
  .fragetext {
    padding: 0;
    font-size: 1.03rem;
    color: var(--ink);
    margin-bottom: 6px;
  }
  .alternativ {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .alt {
    background: transparent;
    border: 1px solid var(--line);
    border-radius: 3px;
    padding: 5px 11px;
    font-family: inherit;
    font-size: 1.03rem;
    color: var(--ink-2);
    cursor: pointer;
  }
  .alt:hover { border-color: var(--line-2); color: var(--ink); }
  .alt[aria-pressed='true'] {
    background: var(--accent-weak);
    border-color: var(--accent);
    color: var(--accent);
  }

  .falt { display: block; margin-bottom: 4px; }
  .faltnamn {
    display: block;
    font-size: 0.72rem;
    color: var(--ink-3);
    margin-bottom: 4px;
  }
  .input {
    width: 100%;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 3px;
    padding: 8px 10px;
    font-family: inherit;
    font-size: 1.03rem;
    color: var(--ink);
  }
  .input:focus-visible { border-color: var(--accent); }

  .knappar {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
    margin-top: 16px;
  }
  /* Identiska med .ghost och .primar i RedigeraLektion.svelte:287-307. */
  .ghost {
    background: transparent;
    color: var(--ink-2);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 8px 16px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
  .ghost:hover { border-color: var(--ink); color: var(--ink); }
  .primar {
    background: var(--btn-bg);
    color: var(--btn-fg);
    border: 1px solid var(--btn-bg);
    border-radius: 4px;
    padding: 8px 18px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
</style>
