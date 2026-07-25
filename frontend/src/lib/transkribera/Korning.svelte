<script>
  // Guidens steg 3 — körningen. Speglar viewTranscribe:s stepProcess-gren
  // (app/web/static/app.js:4582-4668), omstylad till designsystemet.
  import { tr } from './stores.svelte.js';
  import { stageNames, stageBounds, phaseIndex } from './korning.js';
  import Kolista from './Kolista.svelte';

  const faser = $derived(stageNames());
  const granser = $derived(stageBounds());
  const klar = $derived(tr.run === 'done');
  const nuFas = $derived(phaseIndex(tr.dispProgress, klar));

  const aktiv = $derived(tr.queue.find((q) => q.id === tr.activeId) || tr.queue[0] || null);

  const status = $derived(
    tr.run === 'running' ? 'Kör' :
    tr.run === 'done' ? 'Klar' :
    tr.run === 'error' ? 'Fel' :
    tr.run === 'cancelled' ? 'Avbruten' : 'Väntar',
  );

  const tid = $derived.by(() => {
    const n = Math.max(0, Math.floor(tr.elapsed || 0));
    return String(Math.floor(n / 60)).padStart(2, '0') + ':' + String(n % 60).padStart(2, '0');
  });

  /** Hur långt fas i är fylld, 0-100. */
  function fasFyllnad(i) {
    const fran = granser[i];
    const till = granser[i + 1];
    if (tr.dispProgress >= till) return 100;
    if (tr.dispProgress <= fran) return 0;
    return ((tr.dispProgress - fran) / (till - fran)) * 100;
  }
</script>

<p class="eyebrow">STEG 3 — TRANSKRIBERING</p>
<h1 class="display">Bearbetar <span class="ser">lokalt</span></h1>
<p class="lede">Ljudet lämnar aldrig datorn. Du kan lämna fönstret öppet så länge det behövs.</p>

<div class="kort">
  <div class="topp">
    <span class="status" class:kor={tr.run === 'running'} class:ok={klar} class:fel={tr.run === 'error'}>
      {status}
    </span>
    <span class="fil">{aktiv?.name || ''}</span>
    <span class="spacer"></span>
    <span class="matt"><span class="matt-etikett">Tid</span> {tid}</span>
    <span class="matt"><span class="matt-etikett">Klart</span> {Math.round(tr.dispProgress)} %</span>
  </div>

  {#if tr.run !== 'error' && tr.run !== 'cancelled'}
    <div class="faser">
      {#each faser as namn, i}
        <div class="fas" class:passerad={i < nuFas} class:pagar={i === nuFas}>
          <div class="spar"><div class="fyllnad" style:width={fasFyllnad(i) + '%'}></div></div>
          <span class="fasnamn">{namn}</span>
        </div>
      {/each}
    </div>
  {/if}
</div>

{#if tr.queue.length > 1}
  <p class="kolabel">Kö — {Object.values(tr.qStatus).filter((s) => s === 'done').length} av {tr.queue.length} klara</p>
  <Kolista visaStatus={true} />
{/if}

<style>
  .eyebrow {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    color: var(--ink-3);
    margin: 0 0 14px;
  }
  .display {
    font-family: var(--sans);
    font-weight: 700;
    font-size: 1.5rem;
    line-height: 1.15;
    letter-spacing: -0.02em;
    color: var(--ink);
    margin: 0 0 10px;
  }
  .display .ser {
    font-family: var(--serif);
    font-style: italic;
    font-weight: 400;
    font-size: 2.375rem;
    line-height: 1.05;
    letter-spacing: -0.01em;
  }
  .lede { max-width: 62ch; color: var(--ink-2); margin: 0 0 28px; }
  .kort {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 5px;
    padding: 18px 20px;
  }
  .topp {
    display: flex;
    align-items: baseline;
    gap: 14px;
    flex-wrap: wrap;
    margin-bottom: 18px;
  }
  .status {
    font-family: var(--mono);
    font-size: 0.72rem;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: var(--ink-3);
  }
  .status.kor { color: var(--accent); }
  .status.ok { color: var(--ok); }
  .status.fel { color: var(--bad); }
  .fil {
    color: var(--ink-2);
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .spacer { flex: 1; }
  .matt { color: var(--ink); font-variant-numeric: tabular-nums; }
  .matt-etikett {
    font-family: var(--mono);
    font-size: 0.72rem;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: var(--ink-3);
  }
  .faser { display: flex; gap: 8px; }
  .fas { flex: 1; display: flex; flex-direction: column; gap: 7px; min-width: 0; }
  .spar {
    height: 3px;
    background: var(--track);
    border-radius: 2px;
    overflow: hidden;
  }
  .fyllnad { height: 100%; background: var(--accent); }
  .fas.passerad .fyllnad { background: var(--ok); }
  .fasnamn {
    font-size: 0.72rem;
    color: var(--ink-3);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .fas.pagar .fasnamn { color: var(--ink); }
  .kolabel {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
    margin: 28px 0 0;
  }
</style>
