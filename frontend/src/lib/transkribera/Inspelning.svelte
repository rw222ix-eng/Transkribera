<script>
  // Inspelningswidgeten i guidens steg 1. Speglar app.js:4424-4444 funktionellt,
  // men omstylad: gamla widgeten är ren inline-CSS med 8-12px hörn, vilket
  // DESIGN.md avvisar. Ingen literal hex, bara tokens.
  import { tr } from './stores.svelte.js';
  import {
    startRecording,
    stopRecording,
    cancelRecording,
    addRecMarker,
    recSupported,
    laddaOavslutade,
    aterstallOavslutad,
    slangOavslutad,
  } from './inspelning.svelte.js';

  const stods = recSupported();

  // Hämtas när widgeten monteras.
  //
  // AVSTEG från briefens kodblock, som motiverar effekten med "Skalet håller
  // vyn monterad hela sessionen, så det här körs inte om vid flikbyten eller
  // stegväxlingar". Halva påståendet stämmer inte HÄR: flikbyten monterar
  // mycket riktigt inte om något (App.svelte döljer vyerna med hidden), men
  // <Inspelning /> ligger inuti {#if tr.step === 'source'} i
  // TranskriberaView.svelte och avmonteras alltså på steg 2 — effekten körs om
  // varje gång läraren kommer tillbaka till källsteget.
  //
  // Det är önskvärt: listan blir färsk i stället för att spegla sidladdningen.
  //
  // OBS — omkörningen kan ske MITT I en inspelning. Här stod tidigare att den
  // inte kunde det, eftersom "Nästa: inställningar" är avstängd medan
  // tr.recording är sann. Det stämmer inte: den grinden sitter bara på den
  // knappen, medan addFiles sätter tr.step = 'config' ovillkorligt
  // (actions.js:37), och Dropzone, LankFalt, "ett exempel" och exempelfilen är
  // alla klickbara under pågående inspelning. Spela in → dra in en fil → steg
  // 2 → "Lägg till fler" → steg 1, så körs den här effekten om med mikrofonen
  // igång. laddaOavslutade hanterar det uttryckligen: den pågående sessionen
  // filtreras bort ur bannern (annars stod Släng och Återställ bredvid
  // "Spelar in") och räknas ändå som levande vid städningen. Väntande
  // markörsessioner skyddas på samma ställe.
  //
  // Effekten spårar ingenting: laddaOavslutade läser tillstånd först EFTER
  // sitt första await, och asynkrona läsningar registreras inte som beroenden.
  $effect(() => { laddaOavslutade(); });

  const tid = $derived.by(() => {
    const n = Math.max(0, Math.floor(tr.recElapsed || 0));
    return `${String(Math.floor(n / 60)).padStart(2, '0')}:${String(n % 60).padStart(2, '0')}`;
  });
</script>

<!--
  Oavslutade inspelningar — .part-filer som aldrig slutfördes (en krasch, ett
  strömavbrott, ett stängt fönster). Funktionen är porterad ur app.js:4409-4422,
  stilen är det INTE: originalet är inline-CSS med 10-12px hörn, en accent-tonad
  larmruta och en ⚠️-emoji. Här är den ett lugnt sänkt pappersskikt.

  Bannern är MEDVETET ingen live-region: den enda som finns är den hoistade
  .fel-sr i TranskriberaView.svelte, se kommentaren vid .rec-fel längre ned.
-->
{#if tr.incompleteRecs.length}
  <div class="oavslutad">
    <p class="oav-titel">Oavslutad inspelning hittad</p>
    <!-- Nyckeln är sessions-id:t: stabilt och unikt (filnamnsstammen för
         .part-filen). Listan ersätts i dag alltid i sin helhet av
         laddaOavslutade, så nyckeln ändrar ingenting just nu — men den kostar
         ingenting och krävs så fort en rad får eget tillstånd. -->
    {#each tr.incompleteRecs as p (p.session)}
      <!--
        "18,8 MB · 30 jan", inte sessions-id:t. Backend levererar redan en
        färdig människoläsbar storlek och ett datum (server.py:796-806), och
        gamla appen bygger sin etikett av exakt de två fälten (app.js:4054).
        Datumet är det enda som låter läraren skilja passet hon tappade i
        morse från en gammal rest; "rec_1738…" säger henne ingenting. Den
        egenräknade kB-siffran ligger kvar som fallback ifall size skulle
        saknas. aria-label på knapparna: med flera rader läser en skärmläsare
        annars "Släng, Släng, Släng" utan åtskillnad.
      -->
      {@const etikett =
        (p.size || `${Math.round((p.bytes || 0) / 1024)} kB`) + (p.modified ? ` · ${p.modified}` : '')}
      <div class="oav-rad">
        <span class="oav-namn">{etikett}</span>
        <button
          type="button"
          class="ghost"
          aria-label="Återställ inspelning {etikett}"
          onclick={() => aterstallOavslutad(p.session)}
        >Återställ</button>
        <button
          type="button"
          class="ghost fara"
          aria-label="Släng inspelning {etikett}"
          onclick={() => slangOavslutad(p.session)}
        >Släng</button>
      </div>
    {/each}
  </div>
{/if}

<div class="rad">
  <span class="etikett">ELLER SPELA IN</span>

  <div class="ruta" class:kor={tr.recording}>
    {#if tr.recording}
      <span class="prick" aria-hidden="true"></span>
      <span class="text">Spelar in</span>
      <span class="tid">{tid}</span>
      <div class="matare" title="Mikrofonnivå">
        <div class="fyllnad" class:tyst={tr.recSilent} style:transform={`scaleX(${tr.recLevel})`}></div>
      </div>
      {#if tr.recSilent}<span class="ingen">Ingen signal?</span>{/if}
      <span class="spacer"></span>
      <button type="button" class="ghost" onclick={addRecMarker} title="Markera ett viktigt ögonblick">
        Markera{tr.recMarkerCount ? ` (${tr.recMarkerCount})` : ''}
      </button>
      <button type="button" class="ghost" onclick={cancelRecording}>Avbryt</button>
      <button type="button" class="primar" onclick={stopRecording}>Stoppa och lägg till</button>
    {:else}
      <span class="text" class:av={!stods}>
        {stods
          ? 'Spela in lektionen direkt — ljudet sparas lokalt'
          : 'Inspelning kräver mikrofonåtkomst i webbläsaren'}
      </span>
      <span class="spacer"></span>
      <button type="button" class="primar" disabled={!stods} onclick={startRecording}>
        Starta inspelning
      </button>
    {/if}
  </div>
</div>

<!--
  SYNLIG kopia av inspelningsfelet — den annonseras INTE. Det som skärmläsaren
  läser är den hoistade live-regionen i TranskriberaView.svelte, som ligger
  permanent i DOM:en och numera bär både tr.fileError och tr.recError. Raden
  hade tidigare role="status" och monterades in via {#if} tillsammans med sin
  text, och en live-region som förs in i DOM:en samtidigt som sin text
  annonseras inte pålitligt — det träffade precis de besked en skärmläsar-
  användare mest behöver (nekad mikrofon, ingen mikrofon hittad, "Mikrofonen
  försvann"). Samma uppdelning som .fel/.fel-sr redan har.

  Noden är permanent och aria-hidden, så :empty { display: none } är riskfritt
  här: den tar bort raden ur layouten, inte ur tillgänglighetsträdet — och
  raden finns inte i tillgänglighetsträdet från början.
-->
<p class="rec-fel" aria-hidden="true">{tr.recError}</p>

<style>
  /* Bannern för oavslutade inspelningar. Sänkt pappersskikt med hårfin kant,
     samma geometri som .ruta nedan (5px hörn, 14/16px luft) — DESIGN.md vill
     ha tonala skikt och linjer i stället för färgade larmrutor, och ett fynd
     här är ingen katastrof: ljudet finns kvar, det är bara inte inlagt än. */
  .oavslutad {
    background: var(--sunken);
    border: 1px solid var(--line);
    border-radius: 5px;
    padding: 14px 16px;
    margin: 20px 0 0;
  }
  /* Hel mening, alltså sans — var(--mono) är reserverat för korta versala
     mikroetiketter som .etikett nedan. */
  .oav-titel { color: var(--ink); font-size: 1.03rem; font-weight: 500; margin: 0 0 10px; }
  .oav-rad { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .oav-rad + .oav-rad { margin-top: 8px; }
  /* Etiketten är kort och bryter på mellanslag ("18,8 MB · 30 jan"), så ingen
     overflow-wrap behövs — den fanns bara för det obrytbara sessions-id:t. */
  .oav-namn {
    flex: 1;
    min-width: 0;
    color: var(--ink-2);
    font-size: 1.03rem;
  }
  .rad { margin: 20px 0 0; }
  /* Mikroetiketten är den ENDA platsen mono får stå på i widgeten — versal,
     kort, en rubrik för raden under. DESIGN.md reserverar var(--mono) för
     just det; tider, meningar och knapptexter går i sans. */
  .etikett {
    display: block;
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    color: var(--ink-3);
    margin: 0 0 10px;
  }
  .ruta {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 5px;
    padding: 14px 16px;
  }
  /* Pågående inspelning markeras med en tydligare kant, inte med en färgad
     yta — panelen ska förbli papper, inte bli en larmruta. */
  .ruta.kor { border-color: var(--line-2); }
  /* 8px bred, 4px radie = en exakt cirkel, och håller sig inom 2-5px-regeln. */
  /* MEDVETET AVSTEG från DESIGN.md, rätta inte: tokenet var(--bad) är enligt
     "Tertiary — Status" reserverat för fel och destruktiv bekräftelse, och
     live-tillstånd ska bäras av accenten. Den röda inspelningspricken är ändå
     en så stark branschkonvention (varje kamera, varje bandspelare, varje
     mötesverktyg) att den vinner över regeln just här — en blå prick läses
     helt enkelt inte som "spelar in". Avsteget gäller BARA pricken;
     tystnadsindikatorn nedan bär var(--warn) som sig bör. */
  .prick {
    width: 8px;
    height: 8px;
    border-radius: 4px;
    background: var(--bad);
    flex: none;
    animation: pulsera 1.6s ease-in-out infinite;
  }
  /* Komponent-scopad — gamla appens globala `pulse` i style.css hör till den
     gamla appen och får inte dupliceras hit. */
  @keyframes pulsera {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.35; }
  }
  @media (prefers-reduced-motion: reduce) {
    .prick { animation: none; }
  }
  .text { color: var(--ink-2); font-size: 1.03rem; }
  .text.av { color: var(--ink-3); }
  .tid { color: var(--ink); font-size: 1.03rem; font-variant-numeric: tabular-nums; }
  .matare {
    width: 96px;
    height: 3px;
    background: var(--track);
    border-radius: 2px;
    overflow: hidden;
    flex: none;
  }
  /* scaleX sätts inline ur tr.recLevel (0-1). transform-origin måste vara
     vänsterkanten, annars växer stapeln åt båda hållen från mitten. */
  .fyllnad {
    height: 100%;
    background: var(--ok);
    transform: scaleX(0);
    transform-origin: left center;
  }
  /* Tystnad är en VARNING, inte ett fel: inspelningen rullar vidare, inget har
     gått sönder och ingenting är förlorat — mikrofonen kan mycket väl vara
     avstängd med flit. Därför var(--warn) ("Mustard … also the warning tone",
     DESIGN.md), inte var(--bad) som är reserverat för fel. */
  .fyllnad.tyst { background: var(--warn); }
  .ingen { color: var(--warn); font-size: 1.03rem; }
  .spacer { flex: 1; }
  /* Samma knapputseende som Korning.svelte och Installningar.svelte — widgeten
     uppfinner inga egna knappklasser. */
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
  .primar:disabled { opacity: 0.55; cursor: default; }
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
  /* Släng raderar ljudet permanent. Ingen ny knappform — samma ghost, målad i
     var(--bad), som DESIGN.md reserverar för fel och destruktiv bekräftelse. */
  .ghost.fara { color: var(--bad); }
  /* Inspelningens fel bär en EGEN synlig rad, inte guidens delade tr.fileError —
     ett mikrofonfel hör inte hemma i samma statusrad som filformatsfel. För
     skärmläsaren delas de däremot på en enda hoistad live-region, se markupen
     ovan och kommentaren i TranskriberaView.svelte. */
  .rec-fel { color: var(--bad); margin: 12px 0 0; }
  /* Samma teknik som .fel i TranskriberaView.svelte: noden är permanent, men
     ska inte lägga beslag på 12px marginal när det inte finns något fel. */
  .rec-fel:empty { display: none; }
</style>
