<script>
  // Det guidade fönstret för att koppla Google Kalender. Speglar gamla appens
  // calSetup-modal (app/web/static/app.js:2591-2628).
  //
  // Tre steg, i den ordning de faktiskt måste göras: skapa en OAuth-klient i
  // Google Cloud Console, installera klientfilen, logga in. Steg ett och två
  // görs EN gång per dator; steg tre en gång per konto.
  import { sok } from './sok.svelte.js';
  import {
    stangCalSetup,
    oppnaGoogleConsole,
    installeraKlientfil,
    anslutCal,
  } from './sokActions.js';
  import { nav } from '../shell/nav.svelte.js';

  let ruta = $state(null);
  let filfalt = $state(null);

  // NATIVE <dialog> + showModal(), alltid monterad. Samma val och samma skäl
  // som vyns övriga dialoger — läs kommentarerna i RedigeraLektion.svelte.
  $effect(() => {
    if (!ruta) return;
    if (sok.calSetupOppen && nav.tab === 'inspelningar') {
      if (!ruta.open) {
        ruta.showModal();
        ruta.focus();
      }
    } else if (ruta.open) {
      ruta.close();
    }
  });

  function valdFil(e) {
    const fil = e.currentTarget.files && e.currentTarget.files[0];
    // Nollställ fältet så samma fil går att välja igen efter ett misslyckat
    // försök — annars ger en andra chans ingen change-händelse alls.
    e.currentTarget.value = '';
    if (fil) installeraKlientfil(fil);
  }
</script>

<dialog
  bind:this={ruta}
  class="setup"
  aria-label="Koppla Google Kalender"
  onclose={stangCalSetup}
  tabindex="-1"
>
  <div class="huvud">
    <p class="etikett">Koppla Google Kalender</p>
    <button class="stang" onclick={stangCalSetup} aria-label="Stäng">✕</button>
  </div>

  <p class="ingress">
    Kalenderhändelser skickas till ditt Google-konto. Allt annat i Transkribera
    stannar på den här datorn.
  </p>

  <ol class="steg">
    <li class="steget">
      <p class="stegtext">Skapa en OAuth-klient i Google Cloud Console.</p>
      <button class="ghost" onclick={oppnaGoogleConsole}>Öppna Google Cloud Console</button>
    </li>

    <li class="steget">
      <p class="stegtext">
        Välj klientfilen du laddade ner.
        {#if sok.calKlientKlar}<span class="klar">Installerad.</span>{/if}
      </p>
      <!-- Dolt fält, egen knapp: en rå filväljare ser inte ut som resten av
           appen och går inte att formulera på svenska. -->
      <input
        class="dold"
        type="file"
        accept=".json,application/json"
        bind:this={filfalt}
        onchange={valdFil}
        tabindex="-1"
        aria-hidden="true"
      />
      <button class="ghost" onclick={() => filfalt?.click()} disabled={sok.calUpptagen}>
        {sok.calKlientKlar ? 'Byt klientfil' : 'Välj klientfil'}
      </button>
    </li>

    <li class="steget">
      <p class="stegtext">
        Logga in och godkänn åtkomsten.
        {#if sok.calAnsluten}<span class="klar">Anslutet.</span>{/if}
      </p>
      <!--
        Anropet BLOCKERAR tills Googles samtyckesflöde är klart i webbläsaren
        (server.py:1344-1348) — det kan stå öppet i minuter, och knappen är
        låst under tiden.
      -->
      <button
        class="primar"
        onclick={anslutCal}
        disabled={!sok.calKlientKlar || sok.calUpptagen || sok.calAnsluten === true}
      >
        {sok.calUpptagen ? 'Väntar på Google …' : 'Logga in med Google'}
      </button>
    </li>
  </ol>
</dialog>

<style>
  .setup {
    width: min(520px, calc(100vw - 48px));
    max-height: min(80vh, 620px);
    overflow: auto;
    background: var(--surface);
    color: var(--ink);
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 16px 18px;
  }
  .setup::backdrop { background: color-mix(in srgb, var(--ink) 42%, transparent); }
  .setup:focus-visible { outline: none; }

  .huvud { display: flex; align-items: baseline; gap: 12px; }
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

  .ingress {
    font-size: 1.03rem;
    color: var(--ink-2);
    max-width: 52ch;
    margin: 12px 0 0;
  }

  .steg {
    list-style: decimal;
    margin: 16px 0 0;
    padding-left: 20px;
  }
  .steget {
    margin-bottom: 16px;
    padding-left: 4px;
  }
  .steget:last-child { margin-bottom: 0; }
  .stegtext {
    font-size: 1.03rem;
    color: var(--ink);
    margin: 0 0 6px;
    max-width: 52ch;
  }
  .klar { color: var(--ok); }

  /* Filväljaren är dold men INTE display:none — en dold input går inte att
     klicka programmatiskt i alla webbläsare om den tagits ur layouten. */
  .dold {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
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
  .ghost:hover:not(:disabled) { border-color: var(--ink); color: var(--ink); }
  .ghost:disabled { cursor: default; opacity: 0.6; }
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
  .primar:disabled { cursor: default; opacity: 0.5; }
</style>
