<script>
  // Källmodalen: klick på en sifferkälla i svaret visar själva stället i
  // transkriptionen, med träffraderna markerade. Speglar openCitePeek och dess
  // markup (app/web/static/app.js:2413-2449 och 5678-5709).
  import { sok } from './sok.svelte.js';
  import { stangKalla } from './sokActions.js';
  import { nav } from '../shell/nav.svelte.js';

  // NATIVE <dialog> + showModal(). Ger fokusfälla, Escape, backdrop och
  // top-layer gratis — allt annat blir handskriven kod för det webbläsaren
  // redan gör. Samma val som RedigeraLektion.svelte, läs kommentarerna där.
  //
  // ALLTID MONTERAD, utan {#if}: avmonteras komponenten i stängningsögonblicket
  // hinner close() aldrig köras, och då uteblir webbläsarens återställning av
  // fokus till sifferkällan som öppnade rutan.
  //
  // nav.tab är med i villkoret av samma skäl som i RedigeraLektion: en förfader
  // med display:none gör att dialogen inte RITAS men lämnar den `open`, och
  // showModal() håller då fortfarande hela dokumentet inert.
  let ruta = $state(null);
  $effect(() => {
    if (!ruta) return;
    if (sok.kalla && nav.tab === 'inspelningar') {
      if (!ruta.open) {
        ruta.showModal();
        // Rutan själv, inte en knapp: då läses källans namn innan fokus står
        // på något som går att trycka på.
        ruta.focus();
      }
    } else if (ruta.open) {
      ruta.close();
    }
  });
</script>

<dialog bind:this={ruta} class="kalla" aria-label="Källa i transkriptionen" onclose={stangKalla} tabindex="-1">
  {#if sok.kalla}
    <div class="huvud">
      <p class="etikett">Källa i transkriptionen</p>
      <button class="stang" onclick={stangKalla} aria-label="Stäng">✕</button>
    </div>

    <p class="namn">{sok.kalla.namn}</p>
    {#if sok.kalla.meta}<p class="meta">{sok.kalla.meta}</p>{/if}

    <div class="text">
      {#if sok.kalla.laddar}
        <p class="notis">Hämtar transkriptionen …</p>
      {:else if sok.kalla.fel}
        <p class="notis">Kunde inte hämta transkriptionen.</p>
      {:else if !sok.kalla.rader.length}
        <p class="notis">Transkriptionen är tom.</p>
      {:else}
        <ul class="rader">
          <!-- INDEXNYCKEL, avsiktligt: raderna sätts i sin helhet när källan
               hämtas och muteras aldrig. Någon stabilare identitet finns inte
               att vinna något på — transkriptrader saknar id. -->
          {#each sok.kalla.rader as r, i (i)}
            <li class={['rad', { traff: r.traff }]}>
              <span class="tid">{r.tid}</span>
              <span class="replik">{r.text}</span>
            </li>
          {/each}
        </ul>
        {#if sok.kalla.fler}
          <p class="notis">
            + {sok.kalla.fler}
            {sok.kalla.fler === 1 ? 'ställe' : 'ställen'} till i transkriptionen.
          </p>
        {/if}
      {/if}
    </div>

    <!--
      Vad B3c INTE gör, utskrivet i stället för antytt. Gamla appens
      "Öppna i chattvyn" går till lektionschatten, som byggs i B4 av den
      parallella arbetsströmmen. Samma hållning som B1, B3a och B3b tog: säg
      var läraren kan gå, navigera inte till en platshållare.
    -->
    <p class="senare">
      Att öppna hela transkriptet migreras i en senare plan. Tills dess finns
      det i den gamla appen.
    </p>
  {/if}
</dialog>

<style>
  .kalla {
    width: min(560px, calc(100vw - 48px));
    max-height: min(80vh, 640px);
    overflow: auto;
    background: var(--surface);
    color: var(--ink);
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 16px 18px;
  }
  /* Samma backdrop som vyns två andra dialoger (RedigeraLektion.svelte:207 och
     InspelningarView.svelte:540) — tokeniserad, inte en literal färg. */
  .kalla::backdrop { background: color-mix(in srgb, var(--ink) 42%, transparent); }
  .kalla:focus-visible { outline: none; }

  .huvud {
    display: flex;
    align-items: baseline;
    gap: 12px;
  }
  /* Den enda platsen i komponenten där var(--mono) hör hemma: en kort, versal
     mikroetikett. */
  .etikett {
    flex: 1;
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
    margin: 0;
  }
  .stang {
    background: transparent;
    border: 0;
    color: var(--ink-3);
    font-family: inherit;
    font-size: 1.03rem;
    line-height: 1;
    padding: 2px 6px;
    cursor: pointer;
  }
  .stang:hover { color: var(--ink); }

  .namn {
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--ink);
    margin: 12px 0 0;
    overflow-wrap: anywhere;
  }
  .meta {
    font-size: 0.72rem;
    color: var(--ink-3);
    font-variant-numeric: tabular-nums;
    margin: 2px 0 0;
  }

  .text { margin-top: 14px; }

  .rader { list-style: none; margin: 0; padding: 0; }
  .rad {
    display: flex;
    gap: 12px;
    align-items: flex-start;
    padding: 6px 8px;
    margin: 0 -8px;
    border-radius: 3px;
  }
  /* Träffraden markeras med accentens svaga ton — samma markering som
     Snippet.svelte använder för ordsökets utdrag, så de två läses likadant. */
  .rad.traff { background: var(--accent-weak); }
  .rad.traff .tid { color: var(--accent); }

  .tid {
    flex: none;
    font-family: var(--mono);
    font-size: 0.72rem;
    color: var(--ink-3);
    font-variant-numeric: tabular-nums;
    padding-top: 3px;
  }
  .replik {
    min-width: 0;
    font-size: 1.03rem;
    line-height: 1.6;
    color: var(--ink);
    overflow-wrap: anywhere;
  }

  .notis {
    font-size: 1.03rem;
    color: var(--ink-2);
    max-width: 52ch;
    margin: 8px 0 0;
  }
  .senare {
    font-size: 0.72rem;
    color: var(--ink-3);
    max-width: 52ch;
    margin: 16px 0 0;
  }

  /* MEDVETET ingen Stäng-knapp i en fot. Modalen är en läsvy: ✕ och Escape
     räcker, och en andra knapp med samma tillgängliga namn ("Stäng") hade gett
     dialogen två identiska namn — dåligt för en skärmläsare och tvetydigt för
     varje lokator som pekar på den. */
</style>
