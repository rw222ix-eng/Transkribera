<script>
  // De tre stegen överst i guiden. Speglar stepItems (app.js:3228-3239).
  // Delas med A2 och A3 — ändra inte stegordningen utan att ändra tr.step.
  import { tr } from './stores.svelte.js';

  const STEG = [
    ['source', 'Källa'],
    ['config', 'Inställningar'],
    ['process', 'Transkribering'],
  ];

  const nuIdx = $derived(STEG.findIndex(([id]) => id === tr.step));
</script>

<ol class="steg">
  {#each STEG as [id, etikett], i}
    <li class={{ klar: i < nuIdx, aktiv: i === nuIdx }} aria-current={i === nuIdx ? 'step' : undefined}>
      <span class="nr" aria-hidden="true">{i < nuIdx ? '✓' : i + 1}</span>
      <span class="etikett">{etikett}</span>
      {#if i < STEG.length - 1}<span class="strack" aria-hidden="true"></span>{/if}
    </li>
  {/each}
</ol>

<style>
  .steg {
    display: flex;
    align-items: center;
    gap: 9px;
    list-style: none;
    margin: 0 0 28px;
    padding: 0;
  }
  .steg li {
    display: flex;
    align-items: center;
    gap: 9px;
    flex: 0 0 auto;
    color: var(--ink-3);
  }
  .steg li:not(:last-child) { flex: 1; }
  .nr {
    width: 22px;
    height: 22px;
    border-radius: 50%;
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.72rem;
    font-weight: 600;
    border: 1px solid var(--line-2);
  }
  .etikett { white-space: nowrap; }
  .steg li.aktiv { color: var(--ink); }
  .steg li.aktiv .nr {
    background: var(--ink);
    color: var(--btn-fg);
    border-color: var(--ink);
  }
  .steg li.klar { color: var(--ink-2); }
  .steg li.klar .nr {
    background: var(--ok);
    color: var(--on-ok);
    border-color: var(--ok);
  }
  .strack {
    flex: 1;
    height: 1px;
    background: var(--line);
    min-width: 16px;
  }
</style>
