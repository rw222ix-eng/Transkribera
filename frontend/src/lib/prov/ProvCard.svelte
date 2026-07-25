<script>
  // Provkortet: det genererade eller redan godkända dokumentet, med
  // uppgifter, poängbalans/kravgränser, dubblettvarningar och handlingarna
  // (godkänn → PDF, öppna PDF/TeX, radera). Motsvarar exam-card-markupen i
  // app.js (rad ~5992-6046), men bygger på prov.doc i stället för S.exam.
  //
  // KaTeX är utanför scope här (se task-4-brief.md): uppgiftstexten kan
  // innehålla $…$-matte som gamla appen renderar med KaTeX. Här visas texten
  // rå — matte-uttryck syns alltså som LaTeX-källkod, inte satt matematik.
  import { prov } from './stores.svelte.js';
  import { approveExam, openPdf, openTex, deleteExam, closeExam } from './actions.js';

  const typLabel = $derived(prov.doc?.typ === 'arbetsblad' ? 'Arbetsblad' : 'Prov');

  // Delordningen provet trycks i (B, C, D, del-lösa) — samma sekvens som
  // exam_spec.DEL_ORDNING/examNumbered (app.js:1332-1344), så "Uppgift N"
  // här är samma nummer som på den kompilerade sidan.
  const DEL_ORDNING = ['B', 'C', 'D', null];

  const numbered = $derived.by(() => {
    const uppgifter = prov.doc?.exam?.uppgifter || [];
    const out = [];
    let n = 0;
    for (const del of DEL_ORDNING) {
      for (const u of uppgifter) {
        if ((u.del || null) !== del) continue;
        n += 1;
        out.push({ nummer: n, del: u.del || '', text: u.text || '', poang: poangOf(u) });
      }
    }
    return out;
  });

  // En uppgift med deluppgifter bär själv poäng [0,0,0] (schemakravet) — de
  // riktiga poängen är barnens summa. Speglar poangStr, app.js:3635-3646.
  function poangOf(u) {
    const d = u.deluppgifter;
    if (d && d.length) {
      return d.reduce((acc, x) => {
        const p = x.poang || [0, 0, 0];
        return [acc[0] + p[0], acc[1] + p[1], acc[2] + p[2]];
      }, [0, 0, 0]);
    }
    return u.poang || [0, 0, 0];
  }

  const summor = $derived(prov.doc?.summor || null);
  const granser = $derived(prov.doc?.granser || null);
  const errors = $derived(prov.doc?.errors || []);
  const dubbletter = $derived(prov.doc?.dubbletter || []);

  // Aktuell version ur versions-listan (högst versionsnummer) — samma
  // uträkning som hasPdf/hasTex, app.js:3612-3622.
  const current = $derived.by(() => {
    const vs = prov.doc?.versions || [];
    let cur = null;
    for (const v of vs) if (!cur || v.version > cur.version) cur = v;
    return cur;
  });
  const hasPdf = $derived(!!current?.pdf_path);
  const hasTex = $derived(!!current?.tex_path);

  function errText(e) {
    if (typeof e === 'string') return e;
    return (e?.path ? e.path + ': ' : '') + (e?.message || '');
  }

  function armDelete() {
    prov.deleteArm = true;
  }
  function cancelDelete() {
    prov.deleteArm = false;
  }
</script>

{#if prov.doc?.id}
  <div class="card" data-key="exam-card">
    <div class="head">
      <span class="titel">{prov.doc.exam?.titel || typLabel}</span>
      <span class="tag">{typLabel}</span>
      <span class="tag" class:on={prov.doc.status === 'godkänt'}>{prov.doc.status}</span>
      <span class="spacer"></span>
      <button
        type="button"
        class="close"
        aria-label={'Stäng ' + (typLabel === 'Arbetsblad' ? 'arbetsbladet' : 'provet')}
        title="Stäng — tillbaka till inställningarna"
        onclick={closeExam}
      >✕</button>
    </div>

    {#if summor}
      <p class="sums">
        Totalt {summor.total} p — E {summor.e} · C {summor.c} · A {summor.a}
      </p>
      <p class="sums muted">
        {#each Object.entries(summor.formagor) as [f, p], i}{i ? ' · ' : ''}{f} {p} p{/each}
      </p>
    {/if}
    {#if granser}
      <p class="sums muted">
        Kravgränser: E minst {granser.E.minst} p · C minst {granser.C.minst} p
        (varav {granser.C.varav_ca} C/A) · A minst {granser.A.minst} p
        (varav {granser.A.varav_a} A)
      </p>
    {/if}

    {#if errors.length}
      <div class="errors" role="status">
        <span class="strong">{errors.length} problem kvarstår:</span>
        {#each errors as e}<span class="line">{errText(e)}</span>{/each}
      </div>
    {/if}

    {#if dubbletter.length}
      <div class="dupes" role="status">
        <span class="strong">
          {dubbletter.length} uppgift{dubbletter.length === 1 ? '' : 'er'} liknar tidigare prov:
        </span>
        {#each dubbletter as d}
          <span class="line">"{d.text}" ≈ {d.mot_titel} ({Math.round(d.likhet * 100)} % likhet)</span>
        {/each}
      </div>
    {/if}

    <ol class="tasks">
      {#each numbered as n (n.nummer)}
        <li>
          <div class="taskhead">
            <span class="nr">Uppgift {n.nummer}</span>
            {#if n.del}<span class="del">DEL {n.del}</span>{/if}
            <span class="poang">E {n.poang[0]} · C {n.poang[1]} · A {n.poang[2]}</span>
          </div>
          <div class="text">{n.text}</div>
        </li>
      {/each}
    </ol>

    <div class="actions">
      <button
        type="button"
        class="primary"
        disabled={prov.phase === 'running'}
        onclick={approveExam}
      >
        {prov.phase === 'running' ? 'Arbetar …' : 'Godkänn och skapa PDF'}
      </button>
      {#if hasPdf}
        <button type="button" class="ghost" onclick={openPdf}>Öppna PDF</button>
      {/if}
      {#if hasTex}
        <button type="button" class="ghost" onclick={openTex}>Öppna TeX</button>
      {/if}
      {#if prov.msg}
        <span class="receipt" role="status">{prov.msg}</span>
      {/if}
      <span class="spacer"></span>
      {#if prov.deleteArm}
        <span class="confirm">
          <span class="warn-text">Raderas permanent, även filerna.</span>
          <button type="button" class="danger" onclick={deleteExam}>Ja, radera</button>
          <button type="button" class="ghost" onclick={cancelDelete}>Avbryt</button>
        </span>
      {:else}
        <button
          type="button"
          class="text-btn"
          aria-label={'Ta bort ' + (typLabel === 'Arbetsblad' ? 'arbetsbladet' : 'provet')}
          title={'Raderar ' + (typLabel === 'Arbetsblad' ? 'arbetsbladet' : 'provet') + ' och dess filer permanent'}
          onclick={armDelete}
        >Radera</button>
      {/if}
    </div>
  </div>
{/if}

<style>
  .card {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 5px;
    padding: 20px 22px;
    margin-top: 24px;
  }
  .head {
    display: flex;
    align-items: baseline;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 10px;
  }
  .titel {
    font-weight: 600;
    font-size: 1.125rem;
    color: var(--ink);
  }
  .tag {
    font-family: var(--mono);
    font-size: 0.72rem;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: var(--ink-3);
  }
  .tag.on { color: var(--ok); }
  .spacer { flex: 1; }
  .close {
    border: none;
    background: transparent;
    color: var(--ink-3);
    cursor: pointer;
    font-size: inherit;
    line-height: 1;
    padding: 5px 8px;
    border-radius: 3px;
    font-family: inherit;
  }
  .close:hover { background: var(--sunken); }

  .sums {
    margin: 0 0 4px;
    color: var(--ink-2);
    font-variant-numeric: tabular-nums;
  }
  .sums.muted { color: var(--ink-3); }

  .errors, .dupes {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin: 12px 0 0;
  }
  .errors { color: var(--bad); }
  .dupes { color: var(--warn); }
  .strong { font-weight: 600; }
  .line { color: var(--ink-2); }

  .tasks {
    list-style: none;
    margin: 16px 0 0;
    padding: 0;
    display: flex;
    flex-direction: column;
  }
  .tasks li {
    border-top: 1px solid var(--line);
    padding: 12px 0;
  }
  .tasks li:first-child { border-top: none; }
  .taskhead {
    display: flex;
    align-items: baseline;
    gap: 10px;
    flex-wrap: wrap;
    margin-bottom: 4px;
  }
  .nr { font-weight: 600; color: var(--ink); }
  .del {
    font-family: var(--mono);
    font-size: 0.72rem;
    letter-spacing: 0.06em;
    color: var(--ink-3);
  }
  .poang {
    font-family: var(--mono);
    font-size: 0.72rem;
    color: var(--ink-3);
    font-variant-numeric: tabular-nums;
  }
  .text { color: var(--ink); line-height: 1.5; }

  .actions {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    margin-top: 18px;
  }
  .primary {
    background: var(--btn-bg);
    color: var(--btn-fg);
    border: none;
    border-radius: 4px;
    padding: 11px 20px;
    font-family: inherit;
    font-size: inherit;
    font-weight: 500;
    cursor: pointer;
  }
  .primary:disabled { opacity: 0.55; cursor: default; }
  .ghost {
    background: transparent;
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 10px 16px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
  .receipt { color: var(--ink-3); word-break: break-all; }
  .text-btn {
    border: none;
    background: transparent;
    color: var(--ink-3);
    border-radius: 4px;
    padding: 10px 12px;
    font-family: inherit;
    font-size: inherit;
    font-weight: 500;
    cursor: pointer;
  }
  .confirm {
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }
  .warn-text { color: var(--bad); }
  .danger {
    border: 1px solid var(--bad);
    background: transparent;
    color: var(--bad);
    border-radius: 4px;
    padding: 9px 14px;
    font-family: inherit;
    font-size: inherit;
    font-weight: 500;
    cursor: pointer;
  }
</style>
