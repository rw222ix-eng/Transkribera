<script>
  import { arkiv } from './stores.svelte.js';
  import { sendFollow } from './actions.js';
</script>

{#if arkiv.askedFor}
  <section class="svar">
    <p class="fraga">{arkiv.askedFor}</p>

    {#if arkiv.scan.length}
      <ul class="scan" aria-live="polite">
        {#each arkiv.scan as s (s.key)}
          <!-- Separatorn ligger INUTI uttrycket: Svelte trimmar bara statiska
               text-noder vid {#if}-gränsen, aldrig utvärderade uttryck. -->
          <li>{s.name}{#if s.hits != null}{" — " + s.hits + " träffar"}{/if}</li>
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

    {#each arkiv.followups as f, i (i)}
      <div class="foljd">
        <p class="fq">{f.q}</p>
        {#if f.error}
          <p class="fa fel">{f.error}</p>
        {:else if f.a}
          <p class="fa">{f.a}</p>
        {:else if f.typing}
          <p class="fa muted">Tänker …</p>
        {/if}
      </div>
    {/each}

    {#if arkiv.answer && !arkiv.asking}
      <div class="foljdrad">
        <input
          class="field"
          aria-label="Ställ en följdfråga"
          placeholder="Ställ en följdfråga …"
          bind:value={arkiv.followInput}
          onkeydown={(e) => { if (e.key === 'Enter') sendFollow(); }}
        />
        <button class="send" onclick={() => sendFollow()}>Skicka</button>
      </div>
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

  .foljd { margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--line); }
  .fq { margin: 0 0 6px; color: var(--ink); font-weight: 600; }
  .fa { margin: 0; max-width: 68ch; color: var(--ink); white-space: pre-wrap; }
  .fa.muted { color: var(--ink-3); }
  .fa.fel { color: var(--bad); }
  .foljdrad { display: flex; gap: 10px; align-items: center; margin-top: 16px; flex-wrap: wrap; }
  .field {
    flex: 1; min-width: 220px;
    background: var(--surface); border: 1px solid var(--line); border-radius: 4px;
    padding: 11px 13px; font-family: inherit; font-size: inherit; color: var(--ink);
  }
  .send {
    background: var(--btn-bg); color: var(--btn-fg); border: none; border-radius: 4px;
    padding: 11px 18px; font-family: inherit; font-size: inherit; font-weight: 500; cursor: pointer;
  }
</style>
