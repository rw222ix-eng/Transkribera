// Skalets tillstånd: vilken flik som visas och vilket tema som gäller.
// Motsvarar st.tab och st.theme i gamla appen (app.js:601-607).
export const nav = $state({
  tab: 'transkribera',   // transkribera | inspelningar | planering
  // Temat sparas inte mellan starter — gamla appen gör inte heller det
  // (toggleTheme, app.js:601, skriver bara till tillståndet).
  theme: 'light',        // light | dark
});

/** Byter flik. */
export function setTab(t) {
  nav.tab = t;
}

/** Växlar mellan ljust och mörkt. */
export function toggleTheme() {
  nav.theme = nav.theme === 'light' ? 'dark' : 'light';
}
