# Aktivera Google Kalender-integrationen

Transkribera kan skapa kalenderhändelser i din egen Google Kalender från
kalenderförslagen i lektionsvyn. Integrationen är **inbyggd och färdigkopplad**
— men den är avstängd tills du lägger in din egen OAuth-klientfil. Det här är
ett medvetet undantag från appens offline-princip: **bara** den titel och
anteckning du själv godkänner med **"Lägg till"** skickas till Google, aldrig
transkript, elevdata eller annat lektionsinnehåll.

## Enklaste vägen: det guidade fönstret i appen

Öppna en inspelning → ställ en fråga som rör tid/prov/läxa/påminnelse så dyker
kalenderförslaget upp → klicka **"Anslut Google-konto"**. Ett fönster
**"Koppla Google Kalender"** öppnas och tar dig igenom hela uppsättningen:

1. **Öppna Google Cloud Console** — knappen öppnar credentials-sidan i din
   webbläsare. Aktivera **Google Calendar API**, sätt upp *OAuth consent screen*
   (**External**, lägg dig själv som **testanvändare**) och skapa en
   **OAuth client ID** av typ **Desktop app**. Ladda ner klient-JSON:en.
2. **Välj klientfil …** — välj den nedladdade filen i appens filväljare. Appen
   sparar den som `google_client_secret.json` på rätt plats åt dig (du behöver
   inte leta upp basmappen). Filen är gitignorerad.
3. **Logga in med Google** — knappen blir klickbar när klienten är på plats.
   Din webbläsare öppnar Googles inloggning; godkänn. Token sparas lokalt i
   `google_token.json` (också gitignorerad).

Sen justerar du titel/tid/anteckning i förslaget och klickar **"Lägg till"** —
händelsen skapas i din primära kalender.

## Äkta ett-klick: bygg in klienten

Vill du att kopplingen ska vara ett rent **"Logga in med Google"** utan steg 1–2
(t.ex. i en paketerad app), lägg in OAuth-klienten på något av dessa sätt så
hittar appen den automatiskt (`client_ready` blir sant direkt):

- **Miljövariabel** `TRANSKRIBERA_GOOGLE_CLIENT` = klientens rå-JSON. Enklast att
  sätta i utvecklingsläge eller baka in vid bygget — ingen hemlighet i repot.
- **Inbyggd fil**: `google_client_secret.json` bredvid appen i PyInstaller-bundlen
  (`sys._MEIPASS`).

En OAuth-klient av typ *Desktop app* har ett "client secret" som Google
uttryckligen inte betraktar som konfidentiellt — men checka ändå aldrig in den
i repot.

## Manuellt (om du hellre gör det själv)

Skapa klienten enligt steg 1 ovan och lägg filen som **`google_client_secret.json`**
i appens basmapp (repo-roten i utvecklingsläge; bredvid exe:n i den paketerade
appen). Starta appen och klicka **"Anslut Google-konto" → "Logga in med Google"**.

## Felsökning

Om något saknas visar appen ett felmeddelande (en fel-toast nere på skärmen)
som talar om exakt vad som fattas:

- **"Google-biblioteken saknas …"** — kör `pip install -r requirements.txt`
  (paketen `google-api-python-client` och `google-auth-oauthlib`).
- **"Ingen OAuth-klientfil hittades …"** — du har inte lagt
  `google_client_secret.json` i basmappen (steg 5 ovan). Meddelandet visar
  den exakta sökväg appen letar i.
- **"Anslutningen misslyckades …"** — samtycket avbröts eller klienten är fel
  konfigurerad; kontrollera att Calendar API är aktiverat och att du är
  tillagd som testanvändare.

Ta bort `google_token.json` för att koppla från kontot.
