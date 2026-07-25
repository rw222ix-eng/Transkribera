<script>
  // Guidens steg 3 — körningen. Speglar viewTranscribe:s stepProcess-gren
  // (app/web/static/app.js:4582-4668), omstylad till designsystemet.
  import { tr } from './stores.svelte.js';
  import { stageNames, stageBounds, phaseIndex } from './korning.js';
  import { cancelRun, resumeRun, retryRun, toggleLog, goSource, nyTranskribering } from './actions.js';
  import Kolista from './Kolista.svelte';

  const faser = $derived(stageNames());
  const granser = $derived(stageBounds());
  const klar = $derived(tr.run === 'done');
  const nuFas = $derived(phaseIndex(tr.dispProgress, klar));

  const aktiv = $derived(tr.queue.find((q) => q.id === tr.activeId) || tr.queue[0] || null);

  // Finns det fler filer som inte körts än? Då är körningen inte färdig, även
  // om den AKTUELLA filen är klar — kedjan i startRun startar nästa efter
  // 800 ms. Klarbeskedet får bara visas när hela kön är tömd.
  const nagotKvar = $derived(!!tr.queue.find((q) => (tr.qStatus[q.id] || 'pending') === 'pending'));

  const status = $derived(
    tr.run === 'running' ? 'Kör' :
    tr.run === 'done' ? 'Klar' :
    tr.run === 'error' ? 'Fel' :
    tr.run === 'cancelled' ? 'Avbruten' : 'Väntar',
  );

  const tid = $derived.by(() => {
    const n = Math.max(0, Math.floor(tr.elapsed || 0));
    return String(Math.floor(n / 60)).padStart(2, '0') + ':' + String(n % 60).padStart(2, '0');
  });

  /** Hur långt fas i är fylld, 0-100. */
  function fasFyllnad(i) {
    const fran = granser[i];
    const till = granser[i + 1];
    if (tr.dispProgress >= till) return 100;
    if (tr.dispProgress <= fran) return 0;
    return ((tr.dispProgress - fran) / (till - fran)) * 100;
  }
</script>

<p class="eyebrow">STEG 3 — TRANSKRIBERING</p>
<h1 class="display">Bearbetar <span class="ser">lokalt</span></h1>
<p class="lede">Ljudet lämnar aldrig datorn. Du kan lämna fönstret öppet så länge det behövs.</p>

<div class="kort">
  <div class="topp">
    <!--
      role="status" sitter HÄR, precis som i gamla appen (app.js:4618). Spannet
      ligger permanent i DOM:en hela steg 3 och dess text ÄR utfallet:
      Kör → Klar / Fel / Avbruten. Rollen får inte flyttas till ett
      {#if}-grindat block — varken klarbeskedet nedan eller fel-/avbrutet-korten
      — för en live-region som monteras in samtidigt som sin text annonseras
      inte pålitligt; exakt det mönster plan A2:s fixrunda underkände och
      ersatte med den hoistade regionen i TranskriberaView.svelte:47. Utan den
      här raden får en lärare som startar en körning och går därifrån inget
      besked när den MISSLYCKAS.
      GRÄNS: "går därifrån" betyder inom appen på steg 3. Byter läraren FLIK
      döljs hela panelen med hidden (App.svelte:15, .pane[hidden] {display:none})
      och regionen tystnar. Det är paritet med gamla appen, som inte ens har
      noden i DOM:en då. Ska utfallet överleva ett flikbyte krävs en region på
      skalnivå — egen plan.
    -->
    <span
      class="status"
      role="status"
      class:kor={tr.run === 'running'}
      class:ok={klar}
      class:fel={tr.run === 'error'}
    >
      {status}
    </span>
    <span class="fil">{aktiv?.name || ''}</span>
    <span class="spacer"></span>
    <span class="matt"><span class="matt-etikett">Tid</span> {tid}</span>
    <span class="matt"><span class="matt-etikett">Klart</span> {Math.round(tr.dispProgress)} %</span>
  </div>

  {#if tr.run !== 'error' && tr.run !== 'cancelled'}
    <div class="faser">
      {#each faser as namn, i}
        <div class="fas" class:passerad={i < nuFas} class:pagar={i === nuFas}>
          <div class="spar"><div class="fyllnad" style:width={fasFyllnad(i) + '%'}></div></div>
          <span class="fasnamn">{namn}</span>
        </div>
      {/each}
    </div>
  {/if}

  {#if tr.run === 'error'}
    <div class="besked fel-besked">
      <p class="besked-titel">{tr.runError?.title || 'Transkriberingen misslyckades'}</p>
      <p class="besked-text">{tr.runError?.detail || ''}</p>
      <div class="knappar">
        <button type="button" class="primar" onclick={retryRun}>Försök igen</button>
        <button type="button" class="ghost" onclick={goSource}>Byt fil</button>
      </div>
    </div>
  {:else if tr.run === 'cancelled'}
    <div class="besked">
      <p class="besked-titel">Transkriberingen avbröts</p>
      <p class="besked-text">Du stoppade körningen — inget sparades. Återuppta där du var, eller byt fil.</p>
      <div class="knappar">
        <button type="button" class="primar" onclick={resumeRun}>Återuppta</button>
        <button type="button" class="ghost" onclick={goSource}>Byt fil</button>
      </div>
    </div>
  {:else if tr.run === 'running'}
    <div class="knappar">
      <button type="button" class="ghost" onclick={cancelRun}>Avbryt</button>
    </div>
  {/if}
</div>

<div class="logg">
  <button type="button" class="loggknapp" aria-expanded={tr.logExpand} onclick={toggleLog}>
    <span class="label">Logg</span>
    <span>{tr.logExpand ? 'Dölj' : 'Visa'} — {tr.log.length} rader</span>
  </button>
  {#if tr.logExpand}
    <ol class="loggrader">
      {#each tr.log as rad}<li>{rad}</li>{/each}
    </ol>
  {/if}
</div>

{#if tr.run === 'done' && !nagotKvar}
  <!-- Ingen egen role="status" här. Blocket är {#if}-grindat och monteras in
       samtidigt som sin text, vilket inte annonseras pålitligt. Beskedet om att
       körningen gick i mål bärs i stället av statusbrickan högst upp i kortet,
       som ligger permanent i DOM:en och går Kör → Klar. -->
  <div class="klar-besked">
    <p class="klar-titel">Klart — lektionen är sparad.</p>
    {#if tr.resultFiles.length}
      <ul class="filer">
        <!-- Servern skickar filerna som objekt ({path, name, ext, kind, size},
             se app/output_store.py:_file_entry), inte som strängar — utan
             .name skulle raden bli "[object Object]". `|| f` behåller stödet
             för en ren sträng om kontraktet någonsin förenklas. -->
        {#each tr.resultFiles as f}<li>{f.name || f}</li>{/each}
      </ul>
    {/if}
    <p class="senare">
      Inspelningar — där lektionen går att öppna, läsa och söka i — migreras i en
      senare plan. Tills dess finns den i den gamla appen.
    </p>
    <!-- nyTranskribering, INTE goSource: guiden måste börja om från ett tomt
         körtillstånd, annars ligger den nyss sparade filen kvar i kön och körs
         om först nästa gång (se actions.js). -->
    <button type="button" class="ghost" onclick={nyTranskribering}>Transkribera något mer</button>
  </div>
{/if}

{#if tr.queue.length > 1}
  <!-- Räkna genom KÖN, inte genom tr.qStatus: removeFromQueue tar bort posten
       men lämnar kvar dess qStatus-nyckel (actions.js:54-63), så en borttagen
       klar fil skulle fortsätta räknas och ge "3 av 2 klara". Speglar gamla
       appens doneCount (app.js:3363). -->
  <p class="kolabel">Kö — {tr.queue.filter((q) => tr.qStatus[q.id] === 'done').length} av {tr.queue.length} klara</p>
  <Kolista visaStatus={true} />
{/if}

<style>
  .eyebrow {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    color: var(--ink-3);
    margin: 0 0 14px;
  }
  .display {
    font-family: var(--sans);
    font-weight: 700;
    font-size: 1.5rem;
    line-height: 1.15;
    letter-spacing: -0.02em;
    color: var(--ink);
    margin: 0 0 10px;
  }
  .display .ser {
    font-family: var(--serif);
    font-style: italic;
    font-weight: 400;
    font-size: 2.375rem;
    line-height: 1.05;
    letter-spacing: -0.01em;
  }
  .lede { max-width: 62ch; color: var(--ink-2); margin: 0 0 28px; }
  .kort {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 5px;
    padding: 18px 20px;
  }
  .topp {
    display: flex;
    align-items: baseline;
    gap: 14px;
    flex-wrap: wrap;
    margin-bottom: 18px;
  }
  .status {
    font-family: var(--mono);
    font-size: 0.72rem;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: var(--ink-3);
  }
  .status.kor { color: var(--accent); }
  .status.ok { color: var(--ok); }
  .status.fel { color: var(--bad); }
  .fil {
    color: var(--ink-2);
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .spacer { flex: 1; }
  .matt { color: var(--ink); font-variant-numeric: tabular-nums; }
  .matt-etikett {
    font-family: var(--mono);
    font-size: 0.72rem;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: var(--ink-3);
  }
  .faser { display: flex; gap: 8px; }
  .fas { flex: 1; display: flex; flex-direction: column; gap: 7px; min-width: 0; }
  .spar {
    height: 3px;
    background: var(--track);
    border-radius: 2px;
    overflow: hidden;
  }
  .fyllnad { height: 100%; background: var(--accent); }
  .fas.passerad .fyllnad { background: var(--ok); }
  .fasnamn {
    font-size: 0.72rem;
    color: var(--ink-3);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .fas.pagar .fasnamn { color: var(--ink); }
  /* Fel-, avbrutet- och körningsbeskeden delar en yta ovanför faserna, eller
     ersätter dem helt (felet och avbrottet döljer .faser ovan). */
  .besked {
    margin-top: 18px;
    padding-top: 18px;
    border-top: 1px solid var(--line);
  }
  .besked-titel {
    font-weight: 600;
    font-size: 1.125rem;
    color: var(--ink);
    margin: 0 0 6px;
  }
  .fel-besked .besked-titel { color: var(--bad); }
  .besked-text {
    color: var(--ink-2);
    margin: 0;
  }
  .knappar {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    margin-top: 16px;
  }
  .primar {
    background: var(--btn-bg);
    color: var(--btn-fg);
    border: none;
    border-radius: 4px;
    padding: 10px 20px;
    font-family: inherit;
    font-size: inherit;
    font-weight: 500;
    cursor: pointer;
  }
  .ghost {
    background: transparent;
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 9px 18px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
  .logg { margin-top: 20px; }
  .loggknapp {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
    width: 100%;
    background: transparent;
    border: none;
    padding: 0;
    color: var(--ink-2);
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
    text-align: left;
  }
  .loggknapp .label {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
  }
  /* Loggraderna är hela meningar, inte mikroetiketter — därför sans, inte mono
     (DESIGN.md: mono är reserverad för små versala etiketter). Samma regel som
     PlaneringView.svelte tillämpar på sin logg. */
  .loggrader {
    list-style: none;
    margin: 12px 0 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .loggrader li {
    color: var(--ink-2);
    font-variant-numeric: tabular-nums;
  }
  /* Klarbeskedet. Guiden stannar kvar på steg 3 — Inspelningar är inte
     migrerad än, så det finns ingenstans att navigera. Beskedet säger det
     rakt ut i stället för att låtsas. */
  .klar-besked {
    margin-top: 28px;
    padding-top: 20px;
    border-top: 1px solid var(--line);
  }
  .klar-titel {
    font-weight: 600;
    font-size: 1.125rem;
    color: var(--ink);
    margin: 0 0 12px;
  }
  .filer {
    list-style: none;
    margin: 0 0 14px;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .filer li { color: var(--ink-2); }
  .senare { max-width: 62ch; color: var(--ink-2); margin: 0 0 16px; }
  .kolabel {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
    margin: 28px 0 0;
  }
</style>
