<script>
  import { chatt } from './stores.svelte.js';
  import { fmtTid } from '../transkript/tid.js';

  let panel = $state(null);

  // MATCHNING PÅ SEGMENTINDEX, inte på tidsträng. Gamla appen jämför
  // st.lessonChatHitT === seg.time (app.js:4153), alltså "mm:ss" som text —
  // vilket markerar TVÅ rader när två segment delar tidsstämpel.
  const valdIndex = $derived(chatt.valtCitat ? chatt.valtCitat.segIndex : -1);

  $effect(() => {
    const i = valdIndex;
    if (i < 0 || !panel) return;
    panel.querySelector(`[data-seg="${i}"]`)?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  });
</script>

<!-- Renderas bara när ett citat är valt. Gamla appens ovRows
     (app.js:4152-4155) mappar hela transkriptet vid VARJE render — även när
     panelen inte visas, och även mellan varje token i en ström. -->
{#if chatt.valtCitat}
  <aside class="kallor" aria-label="Källan i transkriptet">
    <p class="rubrik">Källa</p>
    <ol class="rader" bind:this={panel}>
      {#each chatt.segment as s, i (i)}
        <li class={['rad', { vald: i === valdIndex }]} data-seg={i}>
          <span class="tid">{fmtTid(s.start)}</span>
          <span class="text">{s.text}</span>
        </li>
      {/each}
    </ol>
  </aside>
{/if}

<style>
  /* Medvetet avskalad: en läsbar källkolumn, inte transkriptvyn. Ingen
     spelare, ingen sökning, ingen redigering — den som vill ha det trycker
     på Transkript och får B2:s vy ovanpå. */
  .kallor {
    flex: 0 0 clamp(280px, 34%, 400px);
    display: flex;
    flex-direction: column;
    min-height: 0;
    border-left: 1px solid var(--line);
    padding-left: 14px;
  }
  .rubrik {
    flex: 0 0 auto;
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
    margin: 0 0 8px;
  }
  .rader {
    list-style: none;
    margin: 0;
    padding: 0;
    overflow-y: auto;
    flex: 1 1 auto;
    min-height: 0;
  }
  .rad {
    display: flex;
    align-items: baseline;
    gap: 10px;
    padding: 4px 6px;
    border-radius: 3px;
  }
  /* Bara bakgrunden, ingen färgad vänsterkant — DESIGN.md §Don't. */
  .rad.vald { background: var(--accent-weak); }
  /* Tidkoden är data: sans med tabular-nums, aldrig var(--mono).
     Identisk med .tid i frontend/src/lib/transkript/Transkriptlista.svelte. */
  .tid {
    flex: 0 0 auto;
    font-family: var(--sans);
    font-size: 0.72rem;
    font-variant-numeric: tabular-nums;
    color: var(--ink-3);
  }
  .text { overflow-wrap: anywhere; }
</style>
