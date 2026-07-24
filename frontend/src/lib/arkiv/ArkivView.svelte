<script>
  import { loadArkiv } from './stores.svelte.js';
  import ArkivList from './ArkivList.svelte';
  import ArkivSearch from './ArkivSearch.svelte';
  import ArkivAnswer from './ArkivAnswer.svelte';

  $effect(() => {
    loadArkiv();
  });
</script>

<section class="arkiv">
  <p class="eyebrow">ARKIV</p>
  <h2 class="rubrik">Sparade tavlor och prov</h2>
  <ArkivSearch />
  <ArkivAnswer />
  <ArkivList />
</section>

<style>
  .arkiv {
    max-width: 860px;
    margin: 0 auto;
    padding: 0 24px 96px;
  }
  .eyebrow {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    color: var(--ink-3);
    margin: 0 0 12px;
  }
  .rubrik {
    font-family: var(--sans);
    font-weight: 600;
    font-size: 1.125rem;
    letter-spacing: -0.011em;
    color: var(--ink);
    margin: 0;
  }
</style>
