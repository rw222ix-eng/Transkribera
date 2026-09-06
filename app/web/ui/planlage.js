/* ══════════ Lägeskorten — vad ska skapas, ett eller två ══════════
   Tavlan och gruppuppgiften hör ihop den lektion de tillhör. Väljer man två
   skrivs det andra PÅ det första — förlagan är utkastet, inte en andra tom
   prompt. Fler än två blir en hög, inte en samklang. */
(() => {
  const vard = document.querySelector('#lagesval');
  if (!vard) return;
  const kort = [...vard.querySelectorAll('.lagekort')];
  const spegel = [...document.querySelectorAll('[data-seg="skrivtyp"] button')];
  const not = document.querySelector('#lagenot');
  const andra = document.querySelector('#andrahand');
  let valda = ['Tavla'];
  /* andraHand = typen som redan är skriven och godkänd. Då är det här steget inte
     längre ett val: det andra i paret är bestämt sedan första rundan. */
  let andraHand = null;
  /* Vad lektionen redan har. Ett förval som föreslår en andra tavla till en
     lektion som redan har en är inte ett förval, det är en dubblett. */
  let finnsRedan = [];
  /* Böjningen bor i en tabell och inte i en kedja av frågetecken sedan
     anteckningarna kom: de är PLURAL («anteckningarna», «nya anteckningar»),
     och en femte gren i kedjan hade tigit om det. */
  const BEST = { Tavla: 'tavlan', Prov: 'provet', Arbetsblad: 'arbetsbladet', Gruppuppgift: 'gruppuppgiften', Anteckningar: 'anteckningarna' };
  const best = t => BEST[t] || String(t || '').toLowerCase();
  /* Rubriken är inte dekor: den säger vad man håller på att göra, och följer därför
     valet i det här steget — ett, två, eller det andra i ett par. */
  const RUB = { Tavla: 'Dagens tavla', Prov: 'Nytt prov', Arbetsblad: 'Nytt arbetsblad', Gruppuppgift: 'Ny gruppuppgift', Anteckningar: 'Nya anteckningar' };
  const OBEST = { Tavla: 'en tavla', Prov: 'ett prov', Arbetsblad: 'ett arbetsblad', Gruppuppgift: 'en gruppuppgift', Anteckningar: 'anteckningar' };
  const versal = s => s.charAt(0).toUpperCase() + s.slice(1);
  function ritaRubrik() {
    const h = document.querySelector('#planrubrik');
    if (!h) return;
    const omprov = window.Dokument && window.Dokument.arOmprov && window.Dokument.arOmprov();
    /* Rubriken får inte gå före valet: innan en lektion är vald står hela sidans
       fråga kvar, hur förvalt «Tavla» än är i steg 1. Annars öppnar Planering med
       «Dagens tavla» utan att någon tavla är påbörjad. */
    const nagon = !!(window.PlanKo && window.PlanKo.valda && window.PlanKo.valda().length);
    h.textContent = !valda.length || !nagon ? 'Vad ska du planera?'
      : omprov ? 'Omprovet'
      : andraHand ? `${versal(best(valda[0]))} till ${best(andraHand)}`
      : valda.length === 1 ? (RUB[valda[0]] || valda[0])
      : `${RUB[valda[0]] || valda[0]} och ${OBEST[valda[1]] || valda[1].toLowerCase()}`;
  }
  function rita() {
    const laast = !!andraHand;
    vard.hidden = laast;
    if (not) not.hidden = laast;
    if (andra) {
      andra.hidden = !laast;
      if (laast) document.querySelector('#andrahandtext').textContent = `${valda[0]} — skrivs på ${best(andraHand)} du godkände`;
    }
    kort.forEach(k => k.setAttribute('aria-pressed', String(valda.includes(k.dataset.lage))));
    kort.forEach(k => k.toggleAttribute('data-foljd', valda[1] === k.dataset.lage));
    kort.forEach(k => k.toggleAttribute('data-finns', finnsRedan.includes(k.dataset.lage)));
    const dubbel = valda.filter(v => finnsRedan.includes(v));
    if (not) not.textContent = dubbel.length
      ? `${dubbel.map(v => versal(best(v))).join(' och ')} finns redan på lektionen — skriver du ändå blir det ett till.`
      : valda.length > 1
        ? `${valda[0]} först, sedan ${best(valda[1])} — den skrivs på det färdiga utkastet, inte vid sidan av.`
        : valda.length
          ? 'Välj två om de hör ihop — då skrivs de i samklang, med det andra byggt på det första.'
          : 'Välj minst ett — klicka igen för att ångra, två om de hör ihop.';
    const mal = spegel.find(s => s.textContent.trim() === valda[0]);
    if (mal && mal.getAttribute('aria-pressed') !== 'true') mal.click();
    ritaRubrik();
    document.dispatchEvent(new CustomEvent('lagen', { detail: valda.slice() }));
  }
  vard.addEventListener('click', e => {
    const b = e.target.closest('.lagekort');
    if (!b) return;
    const lage = b.dataset.lage;
    if (valda.includes(lage)) {
      /* Ett klick till ångrar valet — även det sista. Ingenting valt är ett
         giltigt mellanläge; det är knappen framåt som behöver ett val. */
      valda = valda.filter(v => v !== lage);
    } else if (valda.length < 2) {
      valda.push(lage);
    } else {
      valda = [lage];
    }
    rita();
  });
  window.Lagen = () => valda.slice();
  /* Svaret den hopfällda raden visar — i andra hand står det vad den bygger på. */
  window.LageText = () => andraHand ? `${valda[0]} · bygger på ${best(andraHand)}` : valda.join(' + ');
  window.SattAndraHand = (typ, forlagaTyp) => {
    if (!kort.some(k => k.dataset.lage === typ)) return;
    andraHand = forlagaTyp;
    valda = [typ];
    rita();
  };
  window.SlappAndraHand = () => { if (andraHand) { andraHand = null; rita(); } };
  /* Kön äger frågan «planeras någon lektion?» — rubriken läser den, så den måste
     kunna ropa tillbaka när valet i veckan ändras. */
  window.PlanRubrik = ritaRubrik;
  andra && document.querySelector('#andrahandbyt').addEventListener('click', () => window.SlappAndraHand());
  /* Kalendern kan veta typen i förväg — ett prov i schemat ska inte behöva
     väljas som prov en gång till. */
  window.SattLage = lage => {
    const lista = (Array.isArray(lage) ? lage : [lage]).filter(l => kort.some(k => k.dataset.lage === l)).slice(0, 2);
    if (!lista.length) return;
    andraHand = null;
    valda = lista;
    rita();
  };
  /* Vad lektionen redan bär. Appen f\u00e5r g\u00e4rna f\u00f6resl\u00e5 \u2014 men inte f\u00f6resl\u00e5 en kopia
     av det som redan ligger d\u00e4r: \u00e4r hela f\u00f6rvalet dubbletter t\u00f6ms det, och
     l\u00e4raren v\u00e4ljer sj\u00e4lv vad som saknas. */
  window.SattFinns = lista => {
    finnsRedan = (lista || []).filter(t => kort.some(k => k.dataset.lage === t));
    if (finnsRedan.length && valda.length && valda.every(v => finnsRedan.includes(v))) valda = [];
    rita();
  };
  rita();
})();
