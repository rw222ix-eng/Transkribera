<script>
  // Provets/arbetsbladets parametrar — omfång, delning och referensprov.
  // Motsvarar gamla appens "Omfång"-rad (app.js:5840-5874), men Provtid och
  // Del B/C-delningen gäller bara typ "prov" (arbetsbladet skickar ändå sina
  // defaultvärden till servern, se generateExam i actions.js).
  import { plan } from '../planering/stores.svelte.js';
  import { prov } from './stores.svelte.js';

  // Bara godkända PROV duger som referens — samma filter som gamla appen
  // (app.js:3577-3578). Ett ogodkänt utkast eller ett arbetsblad är inget
  // man vill bygga ett nytt prov ifrån.
  const referensval = $derived(
    prov.historik.filter((h) => h.status === 'godkänt' && (h.typ || 'prov') === 'prov'),
  );
</script>

<div class="params">
  <div class="row">
    <span class="label">Omfång</span>
    <div class="fields">
      <label class="mini">
        <input
          type="number"
          class="num"
          min={plan.typ === 'prov' ? 6 : 3}
          max="20"
          aria-label="Antal uppgifter"
          bind:value={prov.antal}
        />
        uppgifter
      </label>
      {#if plan.typ === 'prov'}
        <label class="mini">
          <input
            type="number"
            class="num"
            min="30"
            max="300"
            step="10"
            aria-label="Provtid (minuter)"
            bind:value={prov.tid}
          />
          min
        </label>
        <label class="mini check">
          <input type="checkbox" bind:checked={prov.delar} />
          Dela i Del B/C
        </label>
      {/if}
    </div>
  </div>

  {#if referensval.length}
    <div class="row">
      <span class="label">Utgå från</span>
      <select class="field narrow" aria-label="Utgå från tidigare prov" bind:value={prov.referensId}>
        <option value="">Inget referensprov</option>
        {#each referensval as h (h.id)}
          <option value={String(h.id)}>{h.titel || 'Prov'}{h.datum ? ' · ' + h.datum : ''}</option>
        {/each}
      </select>
    </div>
  {/if}
</div>

<style>
  .params {
    display: flex;
    flex-direction: column;
    gap: 14px;
    margin-top: 14px;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
  }
  .label {
    flex: 0 0 74px;
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
  }
  .fields {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
  }
  .mini {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: var(--ink-3);
  }
  .num {
    width: 56px;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 3px;
    padding: 8px 9px;
    font-family: inherit;
    font-size: inherit;
    color: var(--ink-2);
    font-variant-numeric: tabular-nums;
  }
  .num:focus-visible { border-color: var(--accent); }
  .check {
    cursor: pointer;
    color: var(--ink-2);
  }
  .check input {
    accent-color: var(--accent);
  }
  .field {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 12px 14px;
    font-family: inherit;
    font-size: inherit;
    color: var(--ink);
  }
  .field.narrow { flex: 0 0 auto; min-width: 240px; }
  .field:focus-visible { border-color: var(--accent); }
</style>
