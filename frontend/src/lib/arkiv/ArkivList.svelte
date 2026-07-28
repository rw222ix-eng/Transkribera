<script>
  import { arkiv } from './stores.svelte.js';
  import { openArkivItem } from './actions.js';
  import Snippet from '../Snippet.svelte';
  import { groupByWeek } from './week.js';

  /** "prov"/"arbetsblad"/"tavla" → kort etikett. */
  function typLabel(typ) {
    if (typ === 'prov') return 'PROV';
    if (typ === 'arbetsblad') return 'ARBETSBLAD';
    return 'TAVLA';
  }

  const rows = $derived(arkiv.hits ?? arkiv.items);
  const weeks = $derived(groupByWeek(rows));
</script>

{#if arkiv.loading}
  <p class="note">Hämtar arkivet …</p>
{:else if arkiv.error}
  <p class="note error">{arkiv.error}</p>
{:else if !rows.length}
  <p class="note">
    {arkiv.hits ? 'Inga träffar.' : 'Inget sparat än — godkänn en tavla så samlas den här.'}
  </p>
{:else}
  {#if arkiv.openError}
    <p class="note error">{arkiv.openError}</p>
  {/if}
  {#each weeks as w (w.key)}
    <section class="week">
      <header class="whead">
        <span class="wlabel">{w.label}</span>
        {#if w.range}<span class="wrange">{w.range}</span>{/if}
        <span class="wcount">{w.count}</span>
      </header>
      <ul class="rows">
        {#each w.rows as it (it.typ + ':' + it.id)}
          <li class="row">
            <button
              type="button"
              class="rowbtn"
              onclick={() => openArkivItem(it)}
              aria-label={'Öppna ' + typLabel(it.typ).toLowerCase() + ': ' + it.titel}
            >
              <span class="typ">{typLabel(it.typ)}</span>
              <span class="titel">{it.titel}</span>
              <span class="rowmeta">
                {[it.course, it.group, it.datum].filter(Boolean).join(' · ')}
              </span>
              {#if it.snippet}
                <Snippet text={it.snippet} />
              {/if}
            </button>
          </li>
        {/each}
      </ul>
    </section>
  {/each}
{/if}

<style>
  .note { color: var(--ink-3); margin: 16px 0 0; }
  .note.error { color: var(--bad); }
  .week { margin-top: 28px; }
  .whead {
    display: flex;
    align-items: baseline;
    gap: 12px;
    flex-wrap: wrap;
  }
  .wlabel {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink);
  }
  .wrange { color: var(--ink-3); }
  .wcount { margin-left: auto; color: var(--ink-3); }
  .rows { list-style: none; margin: 8px 0 0; padding: 0; }
  .row { border-top: 1px solid var(--line); }
  .rowbtn {
    display: flex;
    align-items: baseline;
    gap: 12px;
    width: 100%;
    padding: 12px 4px;
    margin: 0 -4px;
    border: none;
    border-radius: 3px;
    background: transparent;
    font-family: inherit;
    font-size: inherit;
    text-align: left;
    color: inherit;
    cursor: pointer;
    flex-wrap: wrap;
  }
  .rowbtn:hover { background: var(--sunken); }
  .typ {
    flex: 0 0 92px;
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    color: var(--ink-3);
  }
  .titel { flex: 1; min-width: 200px; color: var(--ink); }
  .rowmeta { color: var(--ink-3); }
  .rowbtn :global(.snippet) { flex: 1 0 100%; }
</style>
