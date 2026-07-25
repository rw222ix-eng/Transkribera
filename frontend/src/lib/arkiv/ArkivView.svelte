<script>
  import { arkiv, loadArkiv } from './stores.svelte.js';
  import ArkivList from './ArkivList.svelte';
  import ArkivSearch from './ArkivSearch.svelte';
  import ArkivAnswer from './ArkivAnswer.svelte';

  $effect(() => {
    loadArkiv();
  });
</script>

<section class="arkiv">
  <p class="eyebrow">ARKIV</p>
  <div class="rubrikrad">
    <h2 class="rubrik">Sparade tavlor och prov</h2>
    {#if arkiv.items.length}
      <span class="total">{arkiv.items.length} {arkiv.items.length === 1 ? 'post' : 'poster'}</span>
    {/if}
  </div>
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
  .rubrikrad {
    display: flex;
    align-items: baseline;
    gap: 12px;
    flex-wrap: wrap;
  }
  .rubrik {
    font-family: var(--sans);
    font-weight: 600;
    font-size: 1.125rem;
    letter-spacing: -0.011em;
    color: var(--ink);
    margin: 0;
  }
  .total { margin-left: auto; color: var(--ink-3); }
</style>
