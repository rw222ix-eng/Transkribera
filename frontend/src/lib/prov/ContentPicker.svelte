<script>
  // Kursinnehållet grupperat per Gy25-rubrik, ihopfällbart per grupp.
  // Motsvarar gamla appens exContentGroups (app.js:3543) och content-markup
  // (app.js:5811-5838), men med Svelte 5-runes i stället för setState-diffar.
  import { plan } from '../planering/stores.svelte.js';
  import { prov } from './stores.svelte.js';

  // Grupperar i den ordning rubrikerna först dyker upp i listan (fallback
  // 'Övrigt' för punkter utan rubrik).
  const groups = $derived.by(() => {
    const byRubrik = new Map();
    for (const p of prov.punkter) {
      const rubrik = p.rubrik || 'Övrigt';
      if (!byRubrik.has(rubrik)) byRubrik.set(rubrik, []);
      byRubrik.get(rubrik).push(p);
    }
    return Array.from(byRubrik, ([rubrik, punkter]) => ({
      rubrik,
      punkter,
      valda: punkter.filter((p) => !!prov.valda[p.id]).length,
    }));
  });

  const total = $derived(Object.values(prov.valda).filter(Boolean).length);

  // Ihopfällt-läge är ren UI-state (inte i storen) — öppen som standard.
  let closed = $state({});
  function isOpen(rubrik) {
    return !closed[rubrik];
  }
  function toggleOpen(rubrik) {
    closed = { ...closed, [rubrik]: isOpen(rubrik) };
  }

  function togglePunkt(id) {
    const next = { ...prov.valda };
    if (next[id]) delete next[id];
    else next[id] = true;
    prov.valda = next;
  }

  function toggleGrupp(g) {
    const alla = g.valda === g.punkter.length;
    const next = { ...prov.valda };
    for (const p of g.punkter) {
      if (alla) delete next[p.id];
      else next[p.id] = true;
    }
    prov.valda = next;
  }
</script>

<div class="picker">
  <div class="row">
    <span class="label">Innehåll</span>
    <div class="content">
      {#if prov.contentError}
        <p class="note error">{prov.contentError}</p>
      {:else if !plan.courseId}
        <p class="note">Välj kurs ovan för att se kursens innehåll.</p>
      {:else if !prov.punkter.length}
        <p class="note">Kursen har inget registrerat innehåll ännu.</p>
      {:else}
        <div class="groups">
          {#each groups as g (g.rubrik)}
            <div class="group">
              <div class="head">
                <button
                  type="button"
                  class="toggle"
                  aria-expanded={isOpen(g.rubrik)}
                  onclick={() => toggleOpen(g.rubrik)}
                >
                  <svg class="caret" viewBox="0 0 16 16" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 4l4 4-4 4" /></svg>
                  <span class="rubrik">{g.rubrik}</span>
                </button>
                <span class="count">{g.valda} valda av {g.punkter.length}</span>
                <button type="button" class="selectall" onclick={() => toggleGrupp(g)}>
                  {g.valda === g.punkter.length ? 'Avmarkera alla' : 'Markera alla'}
                </button>
              </div>
              {#if isOpen(g.rubrik)}
                <div class="points">
                  {#each g.punkter as p (p.id)}
                    <button
                      type="button"
                      class="point"
                      aria-pressed={!!prov.valda[p.id]}
                      onclick={() => togglePunkt(p.id)}
                    >
                      <span class="ck" aria-hidden="true">
                        {#if prov.valda[p.id]}
                          <svg viewBox="0 0 12 12" width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 6.5l2.4 2.4 4.6-5.3" /></svg>
                        {/if}
                      </span>
                      {#if p.kod}<span class="kod">{p.kod}</span>{/if}
                      <span class="text">{p.text}</span>
                      <span class="markers">
                        {#if p.behandlad}<span class="marker">BEHANDLAT</span>{/if}
                        {#if p.provad}<span class="marker on">PRÖVAT</span>{/if}
                      </span>
                    </button>
                  {/each}
                </div>
              {/if}
            </div>
          {/each}
        </div>
        <p class="total">
          {#if total}
            {total} {total === 1 ? 'punkt vald' : 'punkter valda'} — uppgifterna byggs på dem.
          {:else}
            Inget valt — utan val väljer modellen fritt ur kursens innehåll.
          {/if}
        </p>
      {/if}
    </div>
  </div>
</div>

<style>
  .picker { margin-top: 14px; }
  .row {
    display: flex;
    align-items: flex-start;
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
    padding-top: 10px;
  }
  .content { flex: 1; min-width: 260px; }
  .note { margin: 0; padding-top: 10px; color: var(--ink-3); }
  .note.error { color: var(--bad); }

  .groups {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .group {
    border: 1px solid var(--line);
    border-radius: 4px;
    background: var(--surface);
  }
  .head {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 12px;
  }
  .toggle {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
    border: none;
    background: transparent;
    padding: 0;
    font-family: inherit;
    font-size: inherit;
    color: var(--ink);
    cursor: pointer;
  }
  .caret {
    flex: 0 0 auto;
    color: var(--ink-3);
    transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  }
  .toggle[aria-expanded='true'] .caret { transform: rotate(90deg); }
  .rubrik {
    font-family: var(--sans);
    font-weight: 600;
    font-size: 1.125rem;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .count {
    flex: 0 0 auto;
    margin-left: auto;
    font-family: var(--mono);
    font-size: 0.72rem;
    letter-spacing: 0.05em;
    color: var(--ink-3);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .selectall {
    flex: 0 0 auto;
    border: none;
    background: transparent;
    font-family: var(--mono);
    font-size: 0.72rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--ink-2);
    text-decoration: underline;
    text-underline-offset: 3px;
    cursor: pointer;
  }

  .points {
    padding: 2px 10px 10px;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 1px 16px;
  }
  .point {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    width: 100%;
    border: none;
    border-radius: 3px;
    background: transparent;
    padding: 6px;
    font-family: inherit;
    font-size: inherit;
    text-align: left;
    color: var(--ink-2);
    cursor: pointer;
  }
  .point:hover { background: var(--sunken); }
  .point[aria-pressed='true'] .text { color: var(--ink); }
  .ck {
    flex: 0 0 auto;
    width: 15px;
    height: 15px;
    margin-top: 2px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--line-2);
    border-radius: 3px;
    color: var(--on-accent);
  }
  .point[aria-pressed='true'] .ck {
    background: var(--accent);
    border-color: var(--accent);
  }
  .kod {
    flex: 0 0 auto;
    margin-top: 1px;
    font-family: var(--mono);
    font-size: 0.72rem;
    letter-spacing: 0.02em;
    color: var(--ink-3);
  }
  .text {
    flex: 1;
    min-width: 0;
    line-height: 1.35;
  }
  .markers {
    flex: 0 0 auto;
    display: flex;
    gap: 4px;
    margin-top: 1px;
  }
  .marker {
    font-family: var(--mono);
    font-size: 0.72rem;
    letter-spacing: 0.04em;
    color: var(--ink-3);
    background: var(--sunken);
    border: 1px solid var(--line);
    border-radius: 3px;
    padding: 1px 5px;
    white-space: nowrap;
  }
  .marker.on {
    color: var(--accent);
    background: var(--accent-weak);
    border-color: var(--accent);
  }

  .total {
    margin: 10px 0 0;
    color: var(--ink-3);
  }
</style>
