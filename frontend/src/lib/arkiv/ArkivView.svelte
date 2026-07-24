<script>
  import { arkiv } from './stores.svelte.js';
  import { getJSON } from '../api.js';
  import ArkivList from './ArkivList.svelte';
  import ArkivSearch from './ArkivSearch.svelte';

  $effect(() => {
    arkiv.loading = true;
    getJSON('/api/planning/archive')
      .then((d) => {
        arkiv.items = d?.items ?? [];
        arkiv.error = '';
      })
      .catch((e) => {
        arkiv.error = 'Kunde inte hämta arkivet: ' + (e?.message || e);
      })
      .finally(() => {
        arkiv.loading = false;
      });
  });
</script>

<section class="arkiv">
  <p class="eyebrow">ARKIV</p>
  <h2 class="rubrik">Sparade tavlor och prov</h2>
  <ArkivSearch />
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
