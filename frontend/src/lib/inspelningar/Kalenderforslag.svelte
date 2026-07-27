<script>
  // Kalenderförslaget under arkivsvaret. Speglar lessonEventBox och evBoxVM
  // (app/web/static/app.js:2807-2832 och 5280+).
  //
  // GOOGLE KALENDER ÄR APPENS ENDA VÄG UT UR MASKINEN. Allt annat i
  // Transkribera körs lokalt; ett godkänt förslag skickar titel, tid och
  // beskrivning till Googles servrar. Därför är "Lägg till" ett medvetet
  // klick, aldrig något som sker automatiskt när modellen föreslår något.
  import { sok } from './sok.svelte.js';
  import { EV_TIDER, evDagar } from './kalender.js';
  import {
    satHandelseFalt,
    valjDag,
    valjTid,
    avfardaHandelse,
    laggTillHandelse,
    anslutCal,
  } from './sokActions.js';

  const dagar = evDagar();
  const ev = $derived(sok.handelse);
  const nar = $derived(ev ? ev.when + (ev.endDag ? ` → ${ev.endDag}` : '') : '');
  const valdDag = $derived(ev ? (ev.when || ' · ').split(' · ')[0] : '');
  const valdTid = $derived(ev ? (ev.when || '').slice(-5) : '');
</script>

{#if ev}
  <section class="forslag">
    {#if ev.added}
      <p class="klar">Händelsen är tillagd i Google Kalender.</p>
      <p class="klarmeta">{ev.title} · {nar}</p>
    {:else}
      <p class="etikett">Kalenderhändelse</p>

      <label class="falt">
        <span class="faltnamn">Titel</span>
        <input
          class="input"
          value={ev.title}
          oninput={(e) => satHandelseFalt('title', e.currentTarget.value)}
        />
      </label>

      <div class="falt">
        <span class="faltnamn">När</span>
        <button
          class="nar"
          onclick={() => (sok.evValjare = !sok.evValjare)}
          aria-expanded={sok.evValjare}
        >{nar}</button>
      </div>

      {#if sok.evValjare}
        <div class="valjare">
          <ul class="dagar">
            {#each dagar as d (d.iso)}
              <li>
                <button class="val" aria-pressed={valdDag === d.etikett} onclick={() => valjDag(d.etikett, d.iso)}>
                  {d.pre || d.etikett}
                </button>
              </li>
            {/each}
          </ul>
          <ul class="tider">
            {#each EV_TIDER as t (t)}
              <li>
                <button class="val" aria-pressed={valdTid === t} onclick={() => valjTid(t)}>{t}</button>
              </li>
            {/each}
          </ul>
        </div>
      {/if}

      <label class="falt">
        <span class="faltnamn">Anteckning</span>
        <textarea
          class="anteckning"
          rows="3"
          value={ev.desc}
          oninput={(e) => satHandelseFalt('desc', e.currentTarget.value)}
        ></textarea>
      </label>

      <!--
        Google-kopplingens tre lägen. Statusen hämtas först när ett förslag
        dykt upp, så calAnsluten är null tills dess.
      -->
      {#if sok.calAnsluten === false && sok.calKlientKlar}
        <p class="notis">
          Kontot är inte anslutet än.
          <button class="lank" onclick={anslutCal}>Logga in med Google</button>
        </p>
      {:else if sok.calAnsluten === false && !sok.calKlientKlar}
        <!--
          Det guidade uppsättningsfönstret (OAuth-klientfilen, Google Cloud
          Console) är inte porterat. Samma hållning som resten av migrationen:
          säg var läraren kan gå i stället för att bygga en halv guide.
        -->
        <p class="notis">
          Google Kalender är inte uppsatt på den här datorn. Uppsättningen görs
          i den gamla appen; den migreras i en senare plan.
        </p>
      {/if}

      <div class="knappar">
        <button class="ghost" onclick={avfardaHandelse}>Avfärda</button>
        <button
          class="primar"
          onclick={laggTillHandelse}
          disabled={ev.busy || sok.calAnsluten !== true}
        >
          {ev.busy ? 'Lägger till …' : 'Lägg till'}
        </button>
      </div>
    {/if}
  </section>
{/if}

<style>
  /* Egen ram i accentens svaga ton — förslaget är det enda i vyn som skickar
     något ut ur maskinen, och det ska synas att det är en handling som väntar
     på godkännande, inte ännu ett textstycke. */
  .forslag {
    background: var(--surface);
    border: 1px solid var(--accent);
    border-radius: 4px;
    padding: 14px 16px;
    margin-top: 16px;
  }

  .etikett {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--accent);
    margin: 0 0 10px;
  }

  .falt {
    display: block;
    margin-bottom: 10px;
  }
  .faltnamn {
    display: block;
    font-size: 0.72rem;
    color: var(--ink-3);
    margin-bottom: 4px;
  }
  .input,
  .anteckning {
    width: 100%;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 3px;
    padding: 8px 10px;
    font-family: inherit;
    font-size: 1.03rem;
    color: var(--ink);
    resize: vertical;
  }
  .input:focus-visible,
  .anteckning:focus-visible { border-color: var(--accent); }

  .nar {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 3px;
    padding: 8px 10px;
    font-family: inherit;
    font-size: 1.03rem;
    color: var(--ink);
    cursor: pointer;
    text-align: left;
  }
  .nar:hover { border-color: var(--line-2); }

  .valjare { margin: 0 0 10px; }
  .dagar,
  .tider {
    list-style: none;
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    margin: 0 0 6px;
    padding: 0;
  }
  .val {
    background: transparent;
    border: 1px solid var(--line);
    border-radius: 3px;
    padding: 4px 9px;
    font-family: inherit;
    font-size: 0.72rem;
    color: var(--ink-2);
    cursor: pointer;
    font-variant-numeric: tabular-nums;
  }
  .val:hover { border-color: var(--line-2); color: var(--ink); }
  .val[aria-pressed='true'] {
    background: var(--accent-weak);
    border-color: var(--accent);
    color: var(--accent);
  }

  .notis {
    font-size: 1.03rem;
    color: var(--ink-2);
    max-width: 52ch;
    margin: 0 0 10px;
  }
  /* Knapp som ser ut som en länk: åtgärden hör till meningen den står i. */
  .lank {
    background: none;
    border: 0;
    padding: 0;
    font-family: inherit;
    font-size: inherit;
    color: var(--accent);
    text-decoration: underline;
    cursor: pointer;
  }

  .knappar {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
    margin-top: 12px;
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
  .primar:disabled { cursor: default; opacity: 0.5; }

  .klar {
    font-size: 1.03rem;
    color: var(--ink);
    margin: 0;
  }
  .klarmeta {
    font-size: 0.72rem;
    color: var(--ink-3);
    margin: 3px 0 0;
    font-variant-numeric: tabular-nums;
  }
</style>
