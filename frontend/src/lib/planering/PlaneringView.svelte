<script>
  // Planering — tavelflödet, plus prov/arbetsblad (dokumenttypväljaren i
  // BuildPanel). Delkomponenter kopplas in i senare steg.
  import BuildPanel from './BuildPanel.svelte';
  import BoardPreview from './BoardPreview.svelte';
  import ChangeChat from './ChangeChat.svelte';
  import ContentPicker from '../prov/ContentPicker.svelte';
  import ProvParams from '../prov/ProvParams.svelte';
  import ProvCard from '../prov/ProvCard.svelte';
  import { plan } from './stores.svelte.js';
  import { prov } from '../prov/stores.svelte.js';
  import { generateBoard, approveBoard } from './actions.js';
  import { loadContent, loadHistorik, generateExam } from '../prov/actions.js';

  // Innehållslistan (och historiken) laddas om vid varje kurs-/klassbyte —
  // se app.js:1197-1206 (byggPickCourse/byggPickGroup). Effekten läser
  // AVSIKTLIGT bara plan.courseId/plan.groupId: loadContent/loadHistorik
  // skriver till prov.punkter/prov.valda/prov.historik, och skulle effekten
  // läsa den staten också triggade den sig själv i en oändlig loop.
  $effect(() => {
    plan.courseId;
    plan.groupId;
    loadContent();
    loadHistorik();
  });
</script>

<section class="view">
  <p class="eyebrow">PLANERING</p>
  <h1 class="rubrik">
    {#if plan.typ === 'tavla'}Dagens tavla
    {:else if plan.typ === 'prov'}Nytt prov
    {:else}Nytt arbetsblad{/if}
  </h1>
  <!--
    LEDEN ÄR BORTTAGEN, samma behandling som de två andra vyerna fick. Här är
    förlusten STÖRST av de tre: raden var inte en dubblering utan den enda
    texten som förklarade vad vyn gör ("Beskriv momentet … så skrivs tavlan som
    du annars hade skrivit för hand"). Vyn öppnar nu direkt i ett formulär.

    BuildPanel bär redan sina egna fältetiketter och en CTA-rad som skriver ut
    varför knappen är låst ("Beskriv momentet ovan så kan tavlan skrivas"), så
    en förstagångsanvändare är inte helt utan ledning — men ingressen som
    ramade in hela flödet finns inte längre.
  -->

  <BuildPanel onGenerate={plan.typ === 'tavla' ? generateBoard : generateExam} />
  {#if plan.typ !== 'tavla'}
    <ContentPicker />
    <ProvParams />
    {#if prov.log.length}
      <ol class="log" aria-live="polite">
        {#each prov.log as line}
          <li class={{ failed: line.startsWith('Fel:') }}>{line}</li>
        {/each}
      </ol>
    {/if}
    {#if prov.errors.length}
      <ul class="errors">
        {#each prov.errors as err}<li>{err}</li>{/each}
      </ul>
    {/if}
    <ProvCard />
  {/if}
  <!-- BoardPreview villkoras aldrig bort — iframen måste stå monterad hela
       tiden (se kommentaren i BoardPreview.svelte). Den göms visuellt via sin
       egen idle-klass när typen inte är tavla. -->
  <BoardPreview />
  {#if plan.typ === 'tavla' && plan.phase === 'running' && plan.liveSections > 0}
    <p class="live" aria-live="polite">
      Ritar live — {plan.liveSections}
      {plan.liveSections === 1 ? 'sektion' : 'sektioner'} hittills …
    </p>
  {/if}
  <ChangeChat />

  {#if plan.typ === 'tavla' && plan.id && plan.phase === 'done'}
    <div class="approve">
      <button class="primary" disabled={plan.saving} onclick={() => approveBoard()}>
        {plan.saving ? 'Sparar …' : 'Godkänn och spara'}
      </button>
      {#if plan.savedPath}
        <span class="receipt" role="status">Sparad: {plan.savedPath}</span>
      {/if}
      {#if plan.saveError}
        <span class="receipt error" role="status">{plan.saveError}</span>
      {/if}
    </div>
  {/if}

  {#if plan.typ === 'tavla'}
    {#if plan.log.length}
      <ol class="log" aria-live="polite">
        {#each plan.log as line}
          <li class={{ failed: line.startsWith('Fel:') }}>{line}</li>
        {/each}
      </ol>
    {/if}

    {#if plan.errors.length}
      <ul class="errors">
        {#each plan.errors as err}<li>{err}</li>{/each}
      </ul>
    {/if}
  {/if}
</section>

<style>
  .view {
    max-width: 860px;
    margin: 0 auto;
    padding: 56px 24px 96px;
  }
  .eyebrow {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    color: var(--ink-3);
    margin: 0 0 14px;
  }
  /* Vyrubriken. Identisk form i alla tre vyer — en röst i Instrument Serif
     kursiv på hero-steget 3.2rem, i rent #000. Både steget och färgen är
     dokumenterade i DESIGN.md (§3 respektive undantaget i §2).

     Marginalen är 26px, inte 10px: avståndet ned till byggpanelen bars
     tidigare av leden som stod emellan. .lede är borttagen med den. */
  .rubrik {
    font-family: var(--serif);
    font-style: italic;
    font-weight: 400;
    font-size: 3.2rem;
    line-height: 1.05;
    letter-spacing: -0.01em;
    color: #000000;
    margin: 0 0 26px;
    text-wrap: balance;
  }
  /* Loggraderna är hela meningar, inte mikroetiketter — därför sans, inte mono
     (DESIGN.md: mono är reserverad för små versala etiketter). */
  .log {
    margin: 24px 0 0;
    padding-left: 20px;
    color: var(--ink-3);
  }
  /* En körning som havererar ska synas, inte drunkna bland framstegsraderna. */
  .log .failed {
    color: var(--bad);
  }
  .errors {
    margin: 16px 0 0;
    padding-left: 20px;
    color: var(--bad);
  }
  .approve {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
    margin-top: 24px;
  }
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
  .receipt { color: var(--ink-3); }
  .receipt.error { color: var(--bad); }
  .live {
    margin: 10px 0 0;
    color: var(--ink-3);
  }
</style>
