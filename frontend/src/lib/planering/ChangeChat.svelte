<script>
  // Den gemensamma ändringschatten: ett fält, samma beteende för alla tre
  // typer — ruttar till tavlans respektive provets refine-endpoint. Speglar
  // sendByggChat, app.js:945-957, och byggChat*-fälten runt app.js:3518-3530.
  import { plan } from './stores.svelte.js';
  import { refineBoard } from './actions.js';
  import { prov, clearProvSel } from '../prov/stores.svelte.js';
  import { refineExam, listaSv } from '../prov/actions.js';

  const isBoard = $derived(plan.typ === 'tavla');
  // Vilka uppgifter ändringen riktas mot. Utan den här raden är scopingen
  // osynlig och läraren kan inte se varför en ändring bara träffade en
  // uppgift. Gamla appen visar samma sak som chips ovanför fältet
  // (app.js:6053-6060). Tavlan har sin egen markering och rörs inte.
  const valdaRad = $derived(
    !isBoard && prov.sel.length
      ? 'Ändringen gäller uppgift ' + listaSv(prov.sel.map((s) => s.nummer)) + '.'
      : '',
  );
  const docFinns = $derived(isBoard ? !!plan.id : !!prov.doc?.id);
  const upptagen = $derived(isBoard ? plan.phase === 'running' : prov.phase === 'running');
  const canSend = $derived(plan.chatInput.trim().length > 0 && docFinns && !upptagen);

  const etikett = $derived(
    isBoard ? 'Ändra tavlan' : plan.typ === 'arbetsblad' ? 'Ändra arbetsbladet' : 'Ändra provet',
  );
  const placeholder = $derived(
    isBoard
      ? 'Ändra tavlan — t.ex. byt exempel 2 mot ett med decimaltal'
      : plan.typ === 'arbetsblad'
        ? 'Ändra arbetsbladet — t.ex. gör uppgift 3 svårare, byt kontext'
        : 'Ändra provet — t.ex. gör uppgift 3 svårare, lägg till en A-uppgift',
  );

  function send() {
    if (!canSend) return;
    if (isBoard) refineBoard();
    else refineExam();
  }
</script>

{#if docFinns}
  {#if valdaRad}
    <p class="scope" aria-live="polite">
      {valdaRad}
      <button type="button" class="clear" onclick={clearProvSel}>Rensa markeringen</button>
    </p>
  {/if}
  <div class={['chat', { tight: !!valdaRad }]}>
    <span class="label">Ändra</span>
    <input
      class="field"
      aria-label={etikett}
      {placeholder}
      bind:value={plan.chatInput}
      onkeydown={(e) => { if (e.key === 'Enter' && canSend) send(); }}
    />
    <button class="send" disabled={!canSend} onclick={send}>Skicka</button>
  </div>
{/if}

<style>
  .chat {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
    margin-top: 24px;
  }
  /* Raden ovanför hör ihop med fältet — kortare luft emellan dem. */
  .chat.tight { margin-top: 8px; }
  .scope {
    display: flex;
    align-items: baseline;
    gap: 10px;
    flex-wrap: wrap;
    /* Linjerar med fältet, förbi etikettspalten (.label: 74px + 14px gap). */
    margin: 24px 0 0 88px;
    color: var(--ink-2);
  }
  .clear {
    border: none;
    background: transparent;
    color: var(--ink-3);
    font-family: inherit;
    font-size: inherit;
    padding: 0;
    cursor: pointer;
    text-decoration: underline;
    text-underline-offset: 3px;
  }
  .clear:hover { color: var(--ink-2); }
  .label {
    flex: 0 0 74px;
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
  }
  .field {
    flex: 1;
    min-width: 240px;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 12px 14px;
    font-family: inherit;
    font-size: inherit;
    color: var(--ink);
  }
  .send {
    background: transparent;
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 11px 18px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
  .send:disabled { opacity: 0.55; cursor: default; }
</style>
