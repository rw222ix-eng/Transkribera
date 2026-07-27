<script>
  import { kal } from './stores.svelte.js';
  import { evDagar, isoEtikett } from './tid.js';
  import { avfarda, satTitel, satAnteckning, satDag, satTid, laggTillHandelse } from './actions.js';
  import { satBesked, annonsera } from '../lektionschatt/actions.js';

  // Idag som ISO — undre gräns för dagväljaren. Modellens egen instruktion
  // säger redan "datumet får aldrig ligga före idag" (llm_client._cal_instr),
  // men fältet ska hålla samma regel även när läraren väljer manuellt.
  const idag = evDagar()[0].iso;

  function paTitel(e) {
    satTitel(e.currentTarget.value);
  }
  function paAnteckning(e) {
    satAnteckning(e.currentTarget.value);
  }
  function paDag(e) {
    const iso = e.currentTarget.value;
    if (!iso) return;
    const etikett = isoEtikett(iso);
    if (etikett) satDag(iso, etikett);
  }
  function paTid(e) {
    if (e.currentTarget.value) satTid(e.currentTarget.value);
  }

  async function paLaggTill() {
    const titel = kal.forslag ? kal.forslag.titel : '';
    const r = await laggTillHandelse();
    if (!r.ok) satBesked(r.fel, 'fel');
    else annonsera('Tillagd i Google Kalender — ' + titel);
  }
</script>

{#if kal.forslag}
  {@const f = kal.forslag}
  <section class="box" aria-label="Kalenderförslag">
    <p class="eyebrow">Förslag → Kalender</p>

    {#if f.tillagd}
      <p class="klar">
        Tillagd i Google Kalender — {f.titel}
        {#if f.lank}
          <a href={f.lank} target="_blank" rel="noopener noreferrer">Öppna i Google Kalender</a>
        {/if}
      </p>
    {:else}
      <input
        class="falt titelfalt"
        type="text"
        value={f.titel}
        oninput={paTitel}
        aria-label="Titel på händelsen"
      />

      <div class="tidrad">
        <input
          class="falt datumfalt"
          type="date"
          value={f.startIso || idag}
          min={idag}
          onchange={paDag}
          aria-label="Datum"
        />
        <input
          class="falt tidfalt"
          type="time"
          value={(f.nar || '').slice(-5) || '08:00'}
          onchange={paTid}
          aria-label="Tid"
        />
        {#if f.slutDag}<span class="slut">→ {f.slutDag}</span>{/if}
      </div>

      <textarea
        class="falt anteckningsfalt"
        rows="2"
        placeholder="Anteckning i kalenderposten …"
        value={f.anteckning}
        oninput={paAnteckning}
        aria-label="Anteckning i kalenderposten"
      ></textarea>

      <p class="status" class:ansluten={kal.ansluten === true} class:ejansluten={kal.ansluten === false}>
        {#if kal.ansluten === null}
          Kontrollerar Google-anslutningen …
        {:else if kal.ansluten}
          Ansluten till Google Kalender
        {:else}
          Inte ansluten till Google Kalender{kal.hint ? ' — ' + kal.hint : ' ännu'}
        {/if}
      </p>

      <div class="knappar">
        <button type="button" class="primar" disabled={f.upptagen} onclick={paLaggTill}>
          {f.upptagen ? 'Lägger till …' : 'Lägg till'}
        </button>
        <!-- Avfärda inaktiveras medan en begäran är i luften, av samma
             skäl som kalender/actions.js:laggTillHandelse beskriver: gamla
             appens dismissEvent (app.js:2703) kunde köras UTAN att kolla
             busy, så en händelse kunde skapas i Google efter att förslaget
             redan setts som avfärdat i UI:t. Det kvarstår fortfarande om
             läraren stänger hela chatten mitt i — se laggTillHandelse. -->
        <button type="button" class="ghost" disabled={f.upptagen} onclick={avfarda}>Avfärda</button>
      </div>

      <p class="hjalp">
        Ändra via chatten — "flytta till onsdag 14:30", "kortare titel" eller "pågå till fredag" för flera dagar.
      </p>
    {/if}
  </section>
{/if}

<style>
  .box {
    flex: 0 0 auto;
    border: 1px dashed var(--line-2);
    background: var(--sunken);
    border-radius: 5px;
    padding: 12px 14px;
    margin-top: 10px;
  }
  .eyebrow {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
    margin: 0 0 8px;
  }
  .klar {
    margin: 0;
    color: var(--ok);
    font-weight: 500;
  }
  .klar a {
    color: inherit;
    margin-left: 6px;
  }

  /* Receptet är Skrivrad.svelte:53-65:s (frontend/src/lib/lektionschatt/Skrivrad.svelte). */
  .falt {
    background: var(--surface);
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 3px;
    padding: 8px 10px;
    font-family: inherit;
    font-size: 1.03rem;
    line-height: 1.45;
  }
  .falt:focus-visible { border-color: var(--accent); }
  .titelfalt { width: 100%; box-sizing: border-box; font-weight: 500; }

  .tidrad {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 8px;
  }
  /* Datum och tider är data, inte etiketter: sans med tabular-nums, aldrig
     var(--mono) — DESIGN.md §Typography. */
  .datumfalt,
  .tidfalt {
    font-variant-numeric: tabular-nums;
  }
  .slut {
    color: var(--ink-2);
    font-variant-numeric: tabular-nums;
  }

  .anteckningsfalt {
    width: 100%;
    box-sizing: border-box;
    resize: vertical;
    margin-top: 8px;
  }

  .status {
    font-family: var(--mono);
    font-size: 0.72rem;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: var(--ink-3);
    margin: 10px 0 0;
  }
  .status.ansluten { color: var(--ok); }
  .status.ejansluten { color: var(--ink-3); }

  .knappar {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 10px;
  }
  /* Identisk med .primar i frontend/src/lib/transkribera/Korning.svelte:286-296. */
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
  /* Identisk med .ghost i frontend/src/lib/transkribera/Korning.svelte:297-306. */
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

  .hjalp {
    font-size: 0.72rem;
    color: var(--ink-3);
    margin: 8px 0 0;
  }
</style>
