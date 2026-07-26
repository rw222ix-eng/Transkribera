<script>
  // Veckogrupperna. Nyaste veckan först; lektioner utan tolkningsbart datum
  // hamnar sist i gruppen "Tidigare" (weekInfo ger dem start 0).
  import { weekInfo } from '../week.js';
  import Lektionskort from './Lektionskort.svelte';

  let { lektioner, onRedigera, onRadera } = $props();

  const grupper = $derived.by(() => {
    const karta = new Map();
    for (const l of lektioner) {
      // l.datum är ISO-strängen. l.date är serverns formaterade etikett
      // ("Idag · 14:32") och går INTE att räkna på — blandas de ihop grupperas
      // allt tyst fel.
      const v = weekInfo(l.datum || '');
      if (!karta.has(v.key)) karta.set(v.key, { ...v, kort: [] });
      karta.get(v.key).kort = [...karta.get(v.key).kort, l];
    }
    return [...karta.values()].sort((a, b) => b.start - a.start);
  });
</script>

{#each grupper as g (g.key)}
  <div class="grupp">
    <div class="rubrik">
      <!-- Rubriknivå, inte bara stil: vyns <h1> följs av korten på <h3>, så utan
           en <h2> per vecka finns ingen väg för en skärmläsare att hoppa mellan
           veckorna. Storleken är redan satt av .vecka, så inget syns. -->
      <h2 class="vecka">{g.label}</h2>
      {#if g.range}<span class="spann">{g.range}</span>{/if}
      <span class="antal">
        {g.kort.length} {g.kort.length === 1 ? 'inspelning' : 'inspelningar'}
      </span>
    </div>
    <div class="grid">
      {#each g.kort as l (l.id)}
        <Lektionskort {l} {onRedigera} {onRadera} />
      {/each}
    </div>
  </div>
{/each}

<style>
  .grupp { margin-top: 28px; }
  .rubrik {
    display: flex;
    align-items: baseline;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 10px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--line);
  }
  /* margin: 0 nollar <h2>:ans 0.83em-marginaler, som annars hade brutit
     baslinjeraden i .rubrik. Resten är oförändrat mot <span>-versionen. */
  .vecka {
    font-size: 1.03rem;
    font-weight: 600;
    color: var(--ink);
    margin: 0;
  }
  .spann {
    font-size: 0.72rem;
    color: var(--ink-3);
  }
  .antal {
    margin-left: auto;
    font-size: 0.72rem;
    color: var(--ink-3);
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 12px;
    align-items: start;
  }
</style>
