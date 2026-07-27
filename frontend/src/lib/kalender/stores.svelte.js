// Kalenderförslaget som kan uppstå ur BÅDA lektionschatten och arkivsvaret,
// plus de tre modalerna som hör till kalenderflödet: frågekortet (STEG 1),
// anteckningsmodalen och Google-kopplingsguiden.
//
// TVÅ VÄRDAR, en värdnyckel: 'lektion' (lektionschatten) och 'arkiv'
// (arkivsvaret, "Fråga ditt arkiv" i Inspelningar-fliken). Speglar gamla
// appens `_EVKEY`-mönster (app/web/static/app.js:2654-2660), som höll
// `lessonChatEvent` och `askEvent` som TVÅ separata fält i stället för ett
// globalt — samma idé, en nyckel i stället för två fältnamn. Varje förslag
// hör till EN konversation och nollställs av den konversationens egen
// nollställning (lektionschatt/actions.js:nollstall() resp.
// inspelningar/sokActions.js:nollstallFraga()), via
// kalender/actions.js:nollstallForslag(vard).
export const kal = $state({
  // { lektion: {...} | null, arkiv: {...} | null }. Varje värde är
  // {titel, nar, startIso, slutIso, slutDag, anteckning, tillagd, upptagen,
  // lank} eller null. `nar` är etikettformen "fre 17 jul · 14:30" —
  // `startIso` vinner vid Lägg till (se tid.js:starttidFor). Svenska
  // motsvarigheter till gamla appens lessonChatEvent/askEvent (app.js:57,
  // 2646).
  forslag: { lektion: null, arkiv: null },

  // Google-anslutningen är INTE värdbunden — det finns bara ETT Google-konto,
  // oavsett vilken konversation som utlöste guiden. null = ännu inte
  // kontrollerad. D18-LIKNANDE AVVÄGNING: en tidigare version nollställde
  // dessa fält när ETT samtal nollställdes (jfr D18, rekon §11) — det höll så
  // länge det bara fanns EN värd. Nu skulle det tömma bort en redan känd
  // status åt den ANDRA värden bara för att den FÖRSTA stängdes, så
  // nollstallForslag(vard) rör inte de här fälten.
  ansluten: null,
  klientKlar: null,
  // Serverns förklaring när något saknas (t.ex. "Ingen OAuth-klientfil
  // hittades"). D6 (rekon §11): gamla appen sparade denna men läste den
  // aldrig — visas nu både i Forslagsboxens statusrad och i
  // GoogleAnslutModal, i just den guide där hjälptexten faktiskt behövs.
  hint: '',

  // Kalendermodalens klargörande frågor (calQ i gamla appen, STEG 1 i
  // llm_client._cal_instr). null = inget frågekort öppet. ETT delat fält,
  // inte ett per värd — bara EN frågeomgång kan pågå åt gången i praktiken
  // (lektionschattens modal gör resten av appen inert medan den är öppen),
  // så `vard` pekar ut ÄGAREN i stället för en egen nyckel per värd. Speglar
  // gamla appens `calQ.which` ('lesson'|'ask', app.js:2734).
  fragor: null, // {vard, fragor: [{fraga, alternativ, val}], fritext: string} | null

  // Anteckningsmodalen — läser OCH redigerar forslag[vard].anteckning i ett
  // större fält än Forslagsboxens klippta förhandsvisning. null = stängd,
  // annars värdnyckeln för FÖRSLAGET som redigeras (samma enda-slot-skäl som
  // `fragor` ovan).
  anteckningOppen: null,

  // Google-kopplingsguiden (calSetupOpen i gamla appen). Inte värdbunden, av
  // samma skäl som ansluten/klientKlar/hint ovan.
  guideOppen: false,
  guideBusy: false, // installation/inloggning pågår
});
