<script>
  import { plan } from './stores.svelte.js';
  import { getJSON } from '../api.js';

  let { onGenerate = () => {} } = $props();

  let courses = $state([]);
  let groups = $state([]);
  let loadError = $state('');

  const canGenerate = $derived(plan.moment.trim().length > 0 && plan.phase !== 'running');

  $effect(() => {
    Promise.all([getJSON('/api/courses'), getJSON('/api/groups')])
      .then(([c, g]) => {
        courses = c?.courses ?? c ?? [];
        groups = g?.groups ?? g ?? [];
      })
      .catch((e) => {
        loadError = 'Kunde inte hämta kurser och klasser: ' + (e?.message || e);
      });
  });

  function pickCourse(id) {
    plan.courseId = plan.courseId === String(id) ? '' : String(id);
  }
</script>

<div class="panel">
  <div class="row">
    <span class="label">Moment</span>
    <input
      class="field"
      aria-label="Moment"
      placeholder="Moment — t.ex. derivatans definition"
      bind:value={plan.moment}
      onkeydown={(e) => { if (e.key === 'Enter' && canGenerate) onGenerate(); }}
    />
  </div>

  {#if groups.length}
    <div class="row">
      <span class="label">Klass</span>
      <select class="field" aria-label="Klass" bind:value={plan.groupId}>
        <option value="">Ingen klass</option>
        {#each groups as g (g.id)}
          <option value={String(g.id)}>{g.namn ?? g.name}</option>
        {/each}
      </select>
    </div>
  {/if}

  {#if courses.length}
    <div class="row start">
      <span class="label">Kurs</span>
      <div class="chips" role="group" aria-label="Kurs">
        {#each courses as c (c.id)}
          <button
            type="button"
            class="chip"
            aria-pressed={plan.courseId === String(c.id)}
            onclick={() => pickCourse(c.id)}
          >{c.namn ?? c.name}</button>
        {/each}
      </div>
    </div>
  {/if}

  <div class="row">
    <span class="label">När</span>
    <input class="field narrow" type="date" aria-label="Datum" bind:value={plan.datum} />
    <input class="field narrow" type="time" aria-label="Starttid" bind:value={plan.starttid} />
  </div>

  {#if loadError}
    <p class="note error">{loadError}</p>
  {/if}

  <div class="cta">
    <span class="note">
      {canGenerate ? 'Klart att skriva.' : 'Beskriv momentet ovan så kan tavlan skrivas.'}
    </span>
    <button class="primary" disabled={!canGenerate} onclick={() => onGenerate()}>
      {plan.phase === 'running' ? 'Skriver …' : 'Skriv tavlan'}
    </button>
  </div>
</div>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    gap: 14px;
    margin-top: 32px;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
  }
  .row.start { align-items: flex-start; }
  .label {
    flex: 0 0 74px;
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
  }
  .field {
    flex: 1;
    min-width: 240px;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 12px 14px;
    font-family: inherit;
    font-size: inherit;
    color: var(--ink);
  }
  .field.narrow { flex: 0 0 auto; min-width: 0; padding: 8px 10px; }
  .field:focus-visible { border-color: var(--accent); }
  .chips { flex: 1; display: flex; flex-wrap: wrap; gap: 6px; }
  .chip {
    font-family: inherit;
    font-size: inherit;
    padding: 6px 12px;
    border-radius: 3px;
    background: var(--surface);
    color: var(--ink-2);
    border: 1px solid var(--line);
    cursor: pointer;
  }
  .chip[aria-pressed='true'] {
    background: var(--accent-weak);
    color: var(--accent);
    border-color: var(--accent);
  }
  .cta {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
    padding-top: 14px;
    border-top: 1px solid var(--line);
  }
  .note { flex: 1; color: var(--ink-3); margin: 0; }
  .note.error { color: var(--bad); flex: none; }
  .primary {
    background: var(--btn-bg);
    color: var(--btn-fg);
    border: none;
    border-radius: 4px;
    padding: 12px 22px;
    font-family: inherit;
    font-size: inherit;
    font-weight: 500;
    cursor: pointer;
  }
  .primary:disabled { opacity: 0.55; cursor: default; }
</style>
