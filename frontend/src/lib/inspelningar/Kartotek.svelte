<script>
  // Veckogrupperna. Nyaste veckan först; lektioner utan tolkningsbart datum
  // hamnar sist i gruppen "Tidigare" (weekInfo ger dem start 0).
  import { weekInfo } from '../week.js';
  import Lektionskort from './Lektionskort.svelte';

  let { lektioner, onRedigera, onRadera, stadier = new Map() } = $props();

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
    <div class="lista">
      {#each g.kort as l (l.id)}
        <!--
          OMSLAG PER RAD, inte ett attribut på Lektionskort: den filen har
          varken rest-props eller attributspridning, så data-stage går inte
          att skicka in utifrån.

          Omslaget bär också hårlinjen mellan raderna (se .hylsa + .hylsa
          nedan) — den hör till listan, inte till raden.
        -->
        <div class="hylsa" data-stage={stadier.get(l.id) || null}>
          <Lektionskort {l} {onRedigera} {onRadera} />
        </div>
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
  /* LISTA, inte rutnät. repeat(auto-fill, minmax(240px, 1fr)) gjorde
     kartoteket till det kortrutnät DESIGN.md förbjuder; se den långa
     kommentaren i Lektionskort.svelte för hela skälet. */
  .lista { display: flex; flex-direction: column; }

  /* SEPARATORN ÄGS AV LISTAN. Raden bär ingen egen ram — hade den gjort det
     skulle den första raden i varje vecka dubblera grupprubrikens
     border-bottom. Samma lösning som Agenda.svelte:178. */
  .hylsa + .hylsa { border-top: 1px solid var(--line); }

  .hylsa {
    border-radius: 3px;
    transition: opacity 0.42s ease, box-shadow 0.42s ease;
  }
  /* Dämpningen bärs av opacitet ensam. Gamla appens saturate(.5) och
     scale(.965) följer inte med — se specens avsnitt 5. */
  .hylsa[data-stage='dim'] { opacity: 0.34; }
  /* LYFTET är en DUBBEL SKUGGA, inte border-color: omslaget har ingen ram att
     färga, och en genomskinlig ram hade kostat 2px i varje riktning i ett tätt
     rutnät. Kortets overflow: hidden klipper ingenting, eftersom skuggan ligger
     på FÖRÄLDERN. Ingen floaty-animation. */
  .hylsa[data-stage='lift'] {
    box-shadow: 0 0 0 1px var(--accent), 0 0 0 4px var(--accent-weak);
  }
  @media (prefers-reduced-motion: reduce) {
    .hylsa { transition: none; }
  }
</style>
