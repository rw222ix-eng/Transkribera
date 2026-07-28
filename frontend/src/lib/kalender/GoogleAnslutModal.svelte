<script>
  // Den guidade Google-kopplingen (calSetupOpen i gamla appen): status, val
  // av OAuth-klientfil, inloggning. Enda ingången är startaAnslutning()
  // (kalender/actions.js), knappen i Forslagsbox.
  import { kal } from './stores.svelte.js';
  import { stangGuide, loggaIn, installeraKlientfil, oppnaGoogleConsole } from './actions.js';

  let dialog = $state(null);
  let filInput = $state(null);
  let besked = $state('');
  let beskedArt = $state('info'); // 'info' | 'fel'
  let konsolUrl = $state('');

  $effect(() => {
    if (!dialog) return;
    if (kal.guideOppen) {
      if (!dialog.open) {
        besked = '';
        beskedArt = 'info';
        konsolUrl = '';
        dialog.showModal();
        dialog.focus();
      }
    } else if (dialog.open) {
      dialog.close();
    }
  });

  function paClose() {
    stangGuide();
  }

  async function paOppnaKonsol() {
    konsolUrl = (await oppnaGoogleConsole()) || '';
  }

  function paValjFil() {
    if (filInput) filInput.click();
  }

  async function paFilVald(e) {
    const f = e.currentTarget.files && e.currentTarget.files[0];
    e.currentTarget.value = ''; // tillåt att välja samma fil igen (speglar app.js:2601)
    if (!f) return;
    const text = await f.text();
    const r = await installeraKlientfil(text);
    if (r.ok) {
      besked = 'Klientfil installerad.';
      beskedArt = 'info';
    } else {
      besked = r.fel;
      beskedArt = 'fel';
    }
  }

  async function paLoggaIn() {
    besked = '';
    const r = await loggaIn();
    if (!r.ok) {
      besked = r.fel;
      beskedArt = 'fel';
    }
  }
</script>

<dialog
  class="ruta"
  aria-label="Koppla Google Kalender"
  tabindex="-1"
  bind:this={dialog}
  onclose={paClose}
>
  <div class="topp">
    <h2 class="titel">Koppla Google Kalender</h2>
    <button type="button" class="ghost" onclick={stangGuide}>Stäng</button>
  </div>

  <!-- En annonserande nod för DEN HÄR dialogen — tillåtet: "en modal som
       öppnas ovanpå får ha sin egen" (lektionschattens role="status",
       LektionschattModal.svelte:61, är inert medan den här dialogen är
       modal, så de två kan aldrig konkurrera). Bär busy-/fel-/klar-besked
       under installation och inloggning — INTE kal.hint, som är statisk
       information snarare än en händelse att annonsera; den visas separat
       nedan som vanlig text. -->
  <p class="annons-sr" role="status">{besked}</p>
  <p class="besked" class:fel={beskedArt === 'fel'} aria-hidden="true">{besked}</p>

  {#if kal.ansluten}
    <p class="klar">Ansluten till Google Kalender</p>
    <p class="lede">Nu kan du lägga till kalenderförslag med ett klick.</p>
    <button type="button" class="primar" onclick={stangGuide}>Klart</button>
  {:else}
    <p class="lede">
      Händelser skapas i din egen Google Kalender. Det behövs en OAuth-klient
      en gång — sen räcker inloggningen. Bara den titel och anteckning du
      godkänner skickas, aldrig transkript eller elevdata.
    </p>

    {#if kal.hint}
      <!-- D6 (rekon §11): serverns hjälptext ("Google-biblioteken saknas
           — installera …" / "Ingen OAuth-klientfil hittades …") sattes
           men lästes ALDRIG i gamla appen. Visas nu, i exakt den guide
           där den behövs. -->
      <p class="hint">{kal.hint}</p>
    {/if}

    {#if kal.klientKlar}
      <p class="steg-klar">Google-klient klar — det enda som återstår är inloggningen.</p>
    {:else}
      <ol class="steg">
        <li>
          <p class="steg-titel">Steg 1 · Skapa en Google-klient (engång)</p>
          <p class="steg-text">
            Aktivera Google Calendar API och skapa en OAuth-klient av typen
            Desktop app. Ladda sedan ner klient-JSON:en.
          </p>
          <button type="button" class="ghost" onclick={paOppnaKonsol}>Öppna Google Cloud Console</button>
          {#if konsolUrl}
            <!-- D13 (rekon §11): gamla appen läste aldrig svaret och svalde
                 alla fel — misslyckades webbläsaröppningen fick läraren
                 INGEN indikation. Backenden returnerar redan {ok, url}
                 (server.py:1381-1390); den här länken är en ren
                 frontend-läsning av ett svar som redan fanns. -->
            <p class="fallback-lank">
              Öppnades inget fönster?
              <a href={konsolUrl} target="_blank" rel="noopener noreferrer">Öppna länken manuellt</a>.
            </p>
          {/if}
        </li>
        <li>
          <p class="steg-titel">Steg 2 · Installera klientfilen</p>
          <p class="steg-text">
            Välj den nedladdade JSON-filen — appen lägger den på rätt plats åt dig
            (inget behöver flyttas manuellt).
          </p>
          <button type="button" class="ghost" onclick={paValjFil}>Välj klientfil …</button>
          <input
            bind:this={filInput}
            type="file"
            accept="application/json,.json"
            onchange={paFilVald}
            hidden
          />
        </li>
      </ol>
    {/if}

    <button
      type="button"
      class="primar inloggning"
      disabled={!kal.klientKlar || kal.guideBusy}
      onclick={paLoggaIn}
    >{kal.guideBusy ? 'Loggar in …' : 'Logga in med Google'}</button>

    {#if kal.guideBusy}
      <!-- Rekon §7.4/§"Vad jag inte hittade": POST /api/calendar/connect
           BLOCKERAR utan timeout tills Googles samtyckesflöde är klart i
           webbläsaren. Utan den här raden ser appen ut att ha hängt sig —
           knappen är avstängd och ingenting förklarar varför. -->
      <p class="vantar">
        Ett webbläsarfönster har öppnats för Google-inloggningen — appen
        väntar tills du är klar där. Stäng inte fliken; det kan låsa
        inloggningen tills appen startas om.
      </p>
    {:else if !kal.klientKlar}
      <p class="hjalp">Knappen blir klickbar när klientfilen är installerad (steg 2).</p>
    {/if}
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

  /* Klippande teknik, identisk med .annons-sr i LektionschattModal.svelte. */
  .annons-sr {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
  .besked { color: var(--ink-2); margin: 0 0 8px; }
  .besked.fel { color: var(--bad); }
  .besked:empty { display: none; }

  .klar { color: var(--ok); font-weight: 500; margin: 0 0 4px; }
  .lede { color: var(--ink-2); margin: 0 0 14px; }

  .hint {
    background: var(--sunken);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 10px 12px;
    color: var(--ink-2);
    margin: 0 0 14px;
  }

  .steg-klar { color: var(--ink-2); margin: 0 0 14px; }
  .steg {
    list-style: none;
    margin: 0 0 14px;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  .steg-titel { margin: 0 0 4px; font-weight: 500; }
  .steg-text { margin: 0 0 8px; color: var(--ink-2); }
  .fallback-lank { font-size: 0.72rem; color: var(--ink-3); margin: 8px 0 0; }
  .fallback-lank a { color: var(--accent); }

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
  .inloggning { margin-top: 4px; }

  /* Identisk med .hjalp i Forslagsbox.svelte:225-229. */
  .hjalp, .vantar {
    font-size: 0.72rem;
    color: var(--ink-3);
    margin: 8px 0 0;
  }
</style>
