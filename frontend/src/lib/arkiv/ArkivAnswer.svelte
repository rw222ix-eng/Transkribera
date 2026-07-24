<script>
  import { arkiv } from './stores.svelte.js';
</script>

{#if arkiv.askedFor}
  <section class="svar">
    <p class="fraga">{arkiv.askedFor}</p>

    {#if arkiv.scan.length}
      <ul class="scan" aria-live="polite">
        {#each arkiv.scan as s (s.key)}
          <li>{s.name}{#if s.hits != null} — {s.hits} träffar{/if}</li>
        {/each}
      </ul>
    {/if}

    {#if arkiv.askError}
      <p class="text fel">{arkiv.askError}</p>
    {:else if arkiv.answer}
      <p class="text">{arkiv.answer}</p>
    {:else if arkiv.asking}
      <p class="text muted">Läser arkivet …</p>
    {/if}

    {#if !arkiv.askError && arkiv.sources.length}
      <p class="kallor">
        Bygger på: {arkiv.sources.map((s) => s.titel ?? s.name ?? s).join(' · ')}
      </p>
    {/if}
  </section>
{/if}

<style>
  .svar {
    margin: 24px 0 0;
    padding-top: 16px;
    border-top: 1px solid var(--line);
  }
  .fraga {
    font-family: var(--serif);
    font-style: italic;
    font-size: 1.5rem;
    line-height: 1.15;
    color: var(--ink);
    margin: 0 0 12px;
  }
  .text {
    margin: 0;
    max-width: 68ch;
    color: var(--ink);
    white-space: pre-wrap;
  }
  .text.muted { color: var(--ink-3); }
  .text.fel { color: var(--bad); }
  .scan { list-style: none; margin: 0 0 12px; padding: 0; color: var(--ink-3); }
  .kallor { margin: 12px 0 0; color: var(--ink-3); }
</style>
