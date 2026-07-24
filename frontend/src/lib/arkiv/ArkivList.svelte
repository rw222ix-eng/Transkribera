<script>
  import { arkiv } from './stores.svelte.js';
  import Snippet from './Snippet.svelte';

  /** "prov"/"arbetsblad"/"tavla" → kort etikett. */
  function typLabel(typ) {
    if (typ === 'prov') return 'PROV';
    if (typ === 'arbetsblad') return 'ARBETSBLAD';
    return 'TAVLA';
  }

  const rows = $derived(arkiv.hits ?? arkiv.items);
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
  <ul class="rows">
    {#each rows as it (it.typ + ':' + it.id)}
      <li class="row">
        <span class="typ">{typLabel(it.typ)}</span>
        <span class="titel">{it.titel}</span>
        <span class="meta">
          {[it.course, it.group, it.datum].filter(Boolean).join(' · ')}
        </span>
        {#if it.snippet}
          <Snippet text={it.snippet} />
        {/if}
      </li>
    {/each}
  </ul>
{/if}

<style>
  .note { color: var(--ink-3); margin: 16px 0 0; }
  .note.error { color: var(--bad); }
  .rows { list-style: none; margin: 16px 0 0; padding: 0; }
  .row {
    display: flex;
    align-items: baseline;
    gap: 12px;
    padding: 12px 0;
    border-top: 1px solid var(--line);
    flex-wrap: wrap;
  }
  .typ {
    flex: 0 0 92px;
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    color: var(--ink-3);
  }
  .titel { flex: 1; min-width: 200px; color: var(--ink); }
  .meta { color: var(--ink-3); }
  .row :global(.snippet) { flex: 1 0 100%; }
</style>
