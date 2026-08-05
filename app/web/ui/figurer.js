/* ══════════ FIGURKATALOGEN ══════════
   Uppgifterna beskriver sina figurer som data, inte som ritningar. Katalogen gör
   om beskrivningen till CeTZ-källa. Skälet är konsekvens: alla grafer får samma
   axeltjocklek, samma streckning, samma etikettstorlek — det gör inte handritade
   figurer. Och «ändra vinkeln till 60°» blir en siffra i stället för en omritning.

   Varje post tar ett objekt och returnerar CeTZ-kod. Ramen (sida, snitt, canvas,
   grundstil) ägs av figur.js — här står bara innehållet. */
window.Figurer = (() => {
  const n = (v, f) => (v === undefined || v === null ? f : v);
  const t = s => String(s).replace(/\]/g, '');
  /* ── Storleken är EN regel, inte en inställning per blad ──
     Figuren ska läsas av en elev som sitter med pappret på en bänk, inte av en
     designer som zoomar. Måtten är centimeter på papper: en figur under fem
     centimeter blir en miniatyr där etiketterna inte går att skilja åt. Ändras
     de här talen ändras alla figurer i appen — prov, arbetsblad, tavlor och
     gruppuppgifter — på en gång, vilket är hela poängen. */
  const BREDD = 11;
  const HOJD = 7;
  /* Cirkelgeometrin mäts inte i grafens mått: en cirkel behöver bara vara stor
     nog att rymma sina beteckningar, och tre cirkelfigurer på ett blad ska rymmas
     på samma papper. Radien står därför för sig. */
  const RADIE = 2.6;

  /* ── Funktionsgraf ──────────────────────────────────
     En kurva i första kvadranten med läshjälp: streckad linje vid ett tak och en
     lodrät nedgång till x-axeln där de möts. Det är precis vad en elev ska göra
     med grafen — läsa av — så figuren visar hur. */
  /* Skalan är inte en inställning — den finns ALLTID på båda axlar. Steget väljs
     ur 1–2–5-serien så att gradering hamnar på runda tal och antalet streck landar
     mellan fem och åtta: fler blir ett rutnät, färre blir ingen skala. */
  function steg(max) {
    const ra = Math.abs(max) / 6;
    if (!(ra > 0)) return 1;
    const exp = Math.floor(Math.log10(ra));
    const bas = ra / Math.pow(10, exp);
    const m = bas <= 1 ? 1 : bas <= 2 ? 2 : bas <= 5 ? 5 : 10;
    return m * Math.pow(10, exp);
  }
  /* Talen på axeln skrivs som på svenska: decimalkomma, tusental särade. */
  function tal(v) {
    const r = Math.round(v * 1000) / 1000;
    let s = String(r).replace('.', ',');
    if (Math.abs(r) >= 10000 && Number.isInteger(r)) s = s.replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
    return s;
  }

  function graf(o) {
    const b = n(o.bredd, BREDD), h = n(o.hojd, HOJD);
    const uttryck = o.uttryck || 'x => calc.pow(1.15, x)';
    const xmax = n(o.xmax, 18), ymax = n(o.ymax, 12000);
    const tak = o.tak, skarning = o.skarning;
    const rader = [];
    rader.push(`let bx = ${b}`, `let by = ${h}`, `let f = ${uttryck}`);
    rader.push(`let sx = x => x / ${xmax} * bx`, `let sy = y => y / ${ymax} * by`);
    rader.push(`line((0,0), (bx + 0.4, 0), mark: (end: "straight"))`);
    rader.push(`line((0,0), (0, by + 0.4), mark: (end: "straight"))`);
    /* Kurvan klipps mot axelfönstret. En kurva som fortsätter ovanför y-axelns
       slut säger att skalan inte gäller, och då går figuren inte att läsa av. */
    rader.push(`let punkter = range(0, 241).map(i => { let x = i / 240 * ${xmax}; (sx(x), sy(f(x))) }).filter(p => p.at(1) <= by + 0.0001 and p.at(1) >= -0.0001)`);
    rader.push(`if punkter.len() > 1 { line(..punkter, stroke: (thickness: 1.8pt)) }`);
    /* ── Skalan ── */
    const xs = n(o.xsteg, steg(xmax)), ys = n(o.ysteg, steg(ymax));
    const nara = (a, b, s) => Math.abs(a - b) < s * 0.55;
    const egnaX = (o.xmarken || []).map(m => Number(m.vid)).concat(o.skarning !== undefined ? [Number(o.skarning)] : []);
    const egnaY = (o.ymarken || []).map(m => Number(m.vid)).concat(o.tak !== undefined ? [Number(o.tak)] : []);
    for (let v = xs; v <= xmax + 1e-9; v += xs) {
      if (egnaX.some(e => nara(e, v, xs))) continue;
      rader.push(`line((sx(${v}), 0), (sx(${v}), -0.14))`);
      rader.push(`content((sx(${v}), -0.28), anchor: "north")[${tal(v)}]`);
    }
    for (let v = ys; v <= ymax + 1e-9; v += ys) {
      if (egnaY.some(e => nara(e, v, ys))) continue;
      rader.push(`line((0, sy(${v})), (-0.14, sy(${v})))`);
      rader.push(`content((-0.28, sy(${v})), anchor: "east")[${tal(v)}]`);
    }
    rader.push(`content((-0.24, -0.24), anchor: "north-east")[0]`);
    if (tak !== undefined) {
      rader.push(`line((0, sy(${tak})), (bx, sy(${tak})), stroke: (thickness: 0.7pt, dash: "dashed", paint: black))`);
      rader.push(`content((-0.28, sy(${tak})), anchor: "east")[${t(o.taketikett || tak)}]`);
    }
    if (skarning !== undefined) {
      rader.push(`line((sx(${skarning}), 0), (sx(${skarning}), sy(f(${skarning}))), stroke: (thickness: 0.7pt, dash: "dashed", paint: black))`);
      rader.push(`circle((sx(${skarning}), sy(f(${skarning}))), radius: 0.09, fill: black, stroke: none)`);
      rader.push(`content((sx(${skarning}), -0.28), anchor: "north")[${t(o.skarningsetikett || skarning)}]`);
    }
    /* Egna märken UTÖVER skalan. xmarken och ymarken är avläsningar på axeln:
       ett kraftigare streck och talet utanför axeln, samma semantik som bladen är
       skrivna för. En punkt PÅ kurvan är något annat och har egen nyckel. */
    (o.xmarken || []).forEach(m => {
      rader.push(`line((sx(${m.vid}), 0), (sx(${m.vid}), -0.14), stroke: (thickness: 1.2pt))`);
      rader.push(`content((sx(${m.vid}), -0.28), anchor: "north")[${t(m.text)}]`);
    });
    (o.punkter || []).forEach(m => {
      rader.push(`circle((sx(${m.vid}), sy(f(${m.vid}))), radius: 0.09, fill: black, stroke: none)`);
      rader.push(`content((sx(${m.vid}), sy(f(${m.vid})) + 0.22), anchor: "south")[${t(m.text)}]`);
    });
    (o.ymarken || []).forEach(m => {
      rader.push(`line((0, sy(${m.vid})), (-0.14, sy(${m.vid})), stroke: (thickness: 1.2pt))`);
      rader.push(`content((-0.28, sy(${m.vid})), anchor: "east")[${t(m.text)}]`);
    });
    rader.push(`content((bx + 0.46, 0), anchor: "west")[#emph[${t(o.xnamn || 't')}]]`);
    rader.push(`content((0, by + 0.48), anchor: "south")[#emph[${t(o.ynamn || 'N')}]]`);
    return rader.join('\n');
  }

  /* ── Cirkelgeometri ─────────────────────────────────
     Medelpunkt, korda och en punkt på bågen — de tre delarna varje randvinkel-
     uppgift består av. Vinkelbågen ritas där vinkeln står, aldrig som dekor. */
  function cirkel(o) {
    const r = n(o.radie, RADIE);
    const gA = n(o.gradA, 168), gB = n(o.gradB, 12), gC = n(o.gradC, 268);
    const rader = [];
    rader.push(`let r = ${r}`, `let p = g => (r * calc.cos(g * 1deg), r * calc.sin(g * 1deg))`);
    rader.push(`circle((0,0), radius: r, stroke: (thickness: 1pt))`);
    if (o.medelpunkt !== false) {
      rader.push(`circle((0,0), radius: 0.055, fill: black, stroke: none)`);
      rader.push(`content((-0.12, -0.16), anchor: "north-east")[${t(o.medelpunktsnamn || 'O')}]`);
    }
    /* Etiketten placeras RADIELLT: ankaret pekar tillbaka mot medelpunkten, så
       texten trycks ut från cirkeln oavsett var på randen punkten sitter. Den
       gamla öst/väst-regeln lade etiketten rakt ut i sidan, och en punkt längst
       ner fick därför sin bokstav ovanpå randen. */
    const ankare = g => {
      const v = ((g % 360) + 360) % 360;
      const s = ['west', 'south-west', 'south', 'south-east', 'east', 'north-east', 'north', 'north-west'];
      return s[Math.round(v / 45) % 8];
    };
    /* Punkterna heter det uppgiften kallar dem — P och Q i en tangentuppgift,
       A och B i en kordauppgift. Hårdkodade bokstäver ljuger mot texten. */
    /* punkter: false ger en ren cirkel — den figur en uppgift behöver när det är
       ELEVEN som ska sätta ut hörnen. En tom streckad ruta är ingen figur. */
    [o.namnA || 'A', o.namnB || 'B', o.namnC || 'C'].forEach((namn, i) => {
      if (o.punkter === false) return;
      const g = [gA, gB, gC][i];
      if (i === 2 && o.punktC === false) return;
      rader.push(`circle(p(${g}), radius: 0.055, fill: black, stroke: none)`);
      rader.push(`content(p(${g}), anchor: "${ankare(g)}", padding: 0.16)[${t(namn)}]`);
    });
    if (o.korda !== false && o.punkter !== false) rader.push(`line(p(${gA}), p(${gB}))`);
    if (o.medelpunktsvinkel) {
      rader.push(`line((0,0), p(${gA}))`, `line((0,0), p(${gB}))`);
      /* Bågen måste hålla sig INNANFÖR kordan AB. Kordans avstånd från
         medelpunkten är r·cos(Δ/2), så en fast radie på 0,45 skar rakt igenom
         sträckan så snart A och B låg nära varandras motsatta sidor. */
      const delta = (((gA - gB) % 360) + 360) % 360;
      const halva = Math.min(delta, 360 - delta) / 2;
      const kordaAvst = r * Math.cos(halva * Math.PI / 180);
      const bagradie = Math.max(0.2, Math.min(0.46, kordaAvst * 0.6));
      const mitt = gB + (delta <= 180 ? delta / 2 : delta / 2 - 180);
      rader.push(`arc((0,0), start: ${gB} * 1deg, stop: ${gA} * 1deg, radius: ${bagradie.toFixed(3)}, anchor: "origin", stroke: (thickness: 0.5pt))`);
      const lr = (bagradie + 0.3).toFixed(3);
      rader.push(`content((${lr} * calc.cos(${mitt.toFixed(1)} * 1deg), ${lr} * calc.sin(${mitt.toFixed(1)} * 1deg)))[${t(o.medelpunktsvinkel)}]`);
    }
    if (o.randvinkel) {
      rader.push(`line(p(${gC}), p(${gA}))`, `line(p(${gC}), p(${gB}))`);
      /* Randvinkeln står vid C, en bit in mot medelpunkten — inte på en fast
         plats under cirkeln, där den krockar med randen. */
      rader.push(`content((p(${gC}).at(0) * 0.62, p(${gC}).at(1) * 0.62))[${t(o.randvinkel)}]`);
    }
    if (o.tangentVid !== undefined) {
      const g = o.tangentVid;
      rader.push(`let q = p(${g})`, `let tv = (-calc.sin(${g} * 1deg), calc.cos(${g} * 1deg))`);
      rader.push(`line((q.at(0) - tv.at(0) * 1.5, q.at(1) - tv.at(1) * 1.5), (q.at(0) + tv.at(0) * 1.5, q.at(1) + tv.at(1) * 1.5), stroke: (thickness: 1pt))`);
    }
    return rader.join('\n');
  }

  /* ── Triangel med utsatta mått ──────────────────────
     Måtten står på sidorna, den okända som bokstav. Rätvinkligheten markeras med
     en liten kvadrat, som i boken — inte med en punkt. */
  function triangel(o) {
    const A = o.A || [0, 0], B = o.B || [BREDD * 0.82, 0], C = o.C || [BREDD * 0.82, HOJD * 0.78];
    const rader = [];
    rader.push(`let a = (${A[0]}, ${A[1]})`, `let b = (${B[0]}, ${B[1]})`, `let c = (${C[0]}, ${C[1]})`);
    rader.push(`line(a, b, c, close: true, stroke: (thickness: 1.8pt))`);
    if (o.rattVid) {
      const h = { A: 'a', B: 'b', C: 'c' }[o.rattVid] || 'b';
      const grann = h === 'b' ? ['a', 'c'] : h === 'a' ? ['b', 'c'] : ['a', 'b'];
      rader.push(`let e1 = ((${grann[0]}.at(0) - ${h}.at(0)), (${grann[0]}.at(1) - ${h}.at(1)))`);
      rader.push(`let e2 = ((${grann[1]}.at(0) - ${h}.at(0)), (${grann[1]}.at(1) - ${h}.at(1)))`);
      rader.push(`let l1 = calc.sqrt(e1.at(0) * e1.at(0) + e1.at(1) * e1.at(1))`);
      rader.push(`let l2 = calc.sqrt(e2.at(0) * e2.at(0) + e2.at(1) * e2.at(1))`);
      rader.push(`let s = 0.3`);
      rader.push(`let u = (${h}.at(0) + e1.at(0) / l1 * s, ${h}.at(1) + e1.at(1) / l1 * s)`);
      rader.push(`let v = (${h}.at(0) + e2.at(0) / l2 * s, ${h}.at(1) + e2.at(1) / l2 * s)`);
      rader.push(`line(u, (u.at(0) + v.at(0) - ${h}.at(0), u.at(1) + v.at(1) - ${h}.at(1)), v, stroke: (thickness: 0.5pt))`);
    }
    /* ── Vinkeln i hörnet ──
       En vinkel som bara står i bildtexten hör inte till figuren: eleven måste
       då hålla två bilder i huvudet. Bågen ritas i hörnet med gradtalet vid
       bisektrisen, och sveparriktningen väljs så att bågen alltid går INUTI
       triangeln — det korta av de två möjliga hållen. */
    if (o.vinkelVid) {
      const P = { A, B, C }[o.vinkelVid] || B;
      const grannar = { A: [B, C], B: [A, C], C: [A, B] }[o.vinkelVid] || [A, C];
      const vinkel = (Q) => Math.atan2(Q[1] - P[1], Q[0] - P[0]) * 180 / Math.PI;
      let v1 = vinkel(grannar[0]), v2 = vinkel(grannar[1]);
      let d = ((v2 - v1) % 360 + 360) % 360;
      if (d > 180) { const tmp = v1; v1 = v2; v2 = tmp; d = 360 - d; }
      const r = n(o.vinkelradie, 0.62);
      rader.push(`arc((${P[0]}, ${P[1]}), start: ${v1.toFixed(2)} * 1deg, stop: ${(v1 + d).toFixed(2)} * 1deg, radius: ${r}, anchor: "origin", stroke: (thickness: 0.8pt))`);
      if (o.vinkelnamn) {
        const m = (v1 + d / 2) * Math.PI / 180, lr = r + 0.42;
        rader.push(`content((${(P[0] + lr * Math.cos(m)).toFixed(3)}, ${(P[1] + lr * Math.sin(m)).toFixed(3)}))[${t(o.vinkelnamn)}]`);
      }
    }
    const hornnamn = o.hornnamn !== false;
    if (hornnamn) {
      rader.push(`content(a, anchor: "north-east", padding: 0.1)[${t(o.namnA || 'A')}]`);
      rader.push(`content(b, anchor: "north-west", padding: 0.1)[${t(o.namnB || 'B')}]`);
      rader.push(`content(c, anchor: "south-west", padding: 0.1)[${t(o.namnC || 'C')}]`);
    }
    if (o.sidaAB) rader.push(`content(((a.at(0) + b.at(0)) / 2, (a.at(1) + b.at(1)) / 2), anchor: "north", padding: 0.14)[${t(o.sidaAB)}]`);
    if (o.sidaBC) rader.push(`content(((b.at(0) + c.at(0)) / 2, (b.at(1) + c.at(1)) / 2), anchor: "west", padding: 0.14)[${t(o.sidaBC)}]`);
    if (o.sidaCA) rader.push(`content(((c.at(0) + a.at(0)) / 2, (c.at(1) + a.at(1)) / 2), anchor: "south-east", padding: 0.1)[${t(o.sidaCA)}]`);
    return rader.join('\n');
  }

  /* ── Cylinder i genomskärning ───────────────────────
     Tanken, nivån och flödena. Genomskärning i stället för perspektiv: eleven ska
     se höjden h, inte en tunna. */
  function cylinder(o) {
    const b = n(o.bredd, BREDD * 0.48), h = n(o.hojd, HOJD), niva = n(o.niva, 0.42);
    const rader = [];
    rader.push(`let w = ${b}`, `let ht = ${h}`, `let nv = ht * ${niva}`);
    rader.push(`rect((0, 0), (w, ht), stroke: (thickness: 1pt))`);
    rader.push(`rect((0, 0), (w, nv), stroke: none, fill: gray.lighten(70%))`);
    rader.push(`line((0, nv), (w, nv), stroke: (thickness: 0.7pt))`);
    if (o.inflode) {
      rader.push(`line((w * 0.32, ht + 0.62), (w * 0.32, ht + 0.08), mark: (end: "straight"))`);
      rader.push(`content((w * 0.32, ht + 0.72), anchor: "south")[${t(o.inflode)}]`);
    }
    if (o.utflode) {
      rader.push(`line((w * 0.32, -0.08), (w * 0.32, -0.62), mark: (end: "straight"))`);
      rader.push(`content((w * 0.32, -0.72), anchor: "north")[${t(o.utflode)}]`);
    }
    if (o.nivanamn !== false) {
      rader.push(`line((w + 0.3, 0), (w + 0.3, nv), mark: (start: "straight", end: "straight"), stroke: (thickness: 0.5pt))`);
      rader.push(`content((w + 0.42, nv / 2), anchor: "west")[#emph[${t(o.nivanamn || 'h')}]]`);
    }
    /* Bredden mäts UNDER tanken. Ovanför står inflödet, och två mått på samma
       kant lägger sig över varandra hur små de än är. */
    if (o.radienamn) {
      const y = o.utflode ? '-1.05' : '-0.35';
      rader.push(`line((0, ${y}), (w, ${y}), mark: (start: "straight", end: "straight"), stroke: (thickness: 0.5pt))`);
      rader.push(`content((w / 2, ${y} - 0.1), anchor: "north")[${t(o.radienamn)}]`);
    }
    return rader.join('\n');
  }

  /* ── Tallinje med intervall ─────────────────────────
     Fylld ring = med, tom ring = utan. Den skillnaden är hela poängen med
     figuren, så den ritas och skrivs aldrig ut i ord. */
  function tallinje(o) {
    const b = n(o.bredd, BREDD), fran = n(o.fran, -3), till = n(o.till, 3);
    const rader = [];
    rader.push(`let w = ${b}`, `let sx = x => (x - ${fran}) / ${till - fran} * w`);
    rader.push(`line((-0.2, 0), (w + 0.3, 0), mark: (end: "straight"))`);
    (o.marken || []).forEach(m => {
      rader.push(`line((sx(${m.vid}), -0.09), (sx(${m.vid}), 0.09))`);
      rader.push(`content((sx(${m.vid}), -0.2), anchor: "north")[${t(m.text !== undefined ? m.text : m.vid)}]`);
    });
    (o.intervall || []).forEach(iv => {
      rader.push(`line((sx(${iv.fran}), 0.3), (sx(${iv.till}), 0.3), stroke: (thickness: 1.6pt))`);
      rader.push(`circle((sx(${iv.fran}), 0.3), radius: 0.08, fill: ${iv.medFran ? 'black' : 'white'}, stroke: (thickness: 0.7pt))`);
      rader.push(`circle((sx(${iv.till}), 0.3), radius: 0.08, fill: ${iv.medTill ? 'black' : 'white'}, stroke: (thickness: 0.7pt))`);
      if (iv.text) rader.push(`content(((sx(${iv.fran}) + sx(${iv.till})) / 2, 0.5), anchor: "south")[${t(iv.text)}]`);
    });
    return rader.join('\n');
  }

  /* ── Stapeldiagram ──────────────────────────────────
     Grå staplar, hårlinje som baslinje. Ingen ram, inget rutnät: staplarnas höjd
     ÄR datat och allt annat är brus. */
  function staplar(o) {
    const b = n(o.bredd, BREDD * 0.9), h = n(o.hojd, HOJD * 0.8);
    const data = o.data || [];
        const max = n(o.max, Math.max(...data.map(d => d.varde), 1));
    const rader = [];
    rader.push(`let w = ${b}`, `let ht = ${h}`, `let bredd = w / ${Math.max(1, data.length)} * 0.6`);
    rader.push(`line((0, 0), (w, 0), stroke: (thickness: 1pt))`);
    data.forEach((d, i) => {
      const x = `(${i} + 0.5) * w / ${data.length}`;
      rader.push(`rect((${x} - bredd / 2, 0), (${x} + bredd / 2, ${d.varde / max} * ht), fill: gray.lighten(55%), stroke: (thickness: 0.5pt))`);
      rader.push(`content((${x}, -0.18), anchor: "north")[${t(d.namn)}]`);
      if (o.visaVarden) rader.push(`content((${x}, ${d.varde / max} * ht + 0.1), anchor: "south")[${t(d.varde)}]`);
    });
    if (o.ynamn) rader.push(`content((-0.15, ht), anchor: "east")[${t(o.ynamn)}]`);
    return rader.join('\n');
  }

  const katalog = { graf, cirkel, triangel, cylinder, tallinje, staplar };

  /* ── Vilken figur uppgiften vill ha ─────────────────
     Momentets ord säger vad som ska ritas. Heuristiken är med flit grov: hittar
     den inget returnerar den null, och då blir det ingen figur — en gissad figur
     som inte hör till uppgiften är värre än ingen. */
  function forslagFor(moment, kurs) {
    const m = String(moment || '').toLowerCase();
    if (/cirkel|randvinkel|korda|tangent|båge|bage|medelpunkt/.test(m)) return {
      fig: { typ: 'cirkel', gradA: 168, gradB: 18, gradC: 274, medelpunktsvinkel: 'v' },
      kapning: 'Figuren hör till uppgiften — markera det ni vet direkt i den.'
    };
    if (/triangel|pythagoras|hypotenusa|katet|sinus|cosinus|tangens|trigonometri/.test(m)) return {
      fig: { typ: 'triangel', rattVid: 'B', sidaAB: 'a', sidaBC: 'b', sidaCA: 'c' },
      kapning: 'Sätt in de mått ni får ur texten innan ni räknar.'
    };
    if (/volym|cylinder|tank|behållare|behallare|rätblock|ratblock|prisma/.test(m)) return {
      fig: { typ: 'cylinder', inflode: 'in', utflode: 'ut', nivanamn: 'h', radienamn: 'r' },
      kapning: 'Genomskärning — höjden h mäts från botten.'
    };
    if (/olikhet|intervall|tallinje|absolutbelopp|definitionsmängd|definitionsmangd/.test(m)) return {
      fig: { typ: 'tallinje', fran: -4, till: 4, marken: [{ vid: -2 }, { vid: 0 }, { vid: 2 }], intervall: [{ fran: -1, till: 3, medFran: true, medTill: false }] },
      kapning: 'Fylld ring = värdet ingår, tom ring = det gör det inte.'
    };
    if (/statistik|diagram|fördelning|fordelning|medelvärde|medelvarde|frekvens/.test(m)) return {
      fig: { typ: 'staplar', data: [{ namn: 'E', varde: 8 }, { namn: 'C', varde: 14 }, { namn: 'A', varde: 5 }], visaVarden: true },
      kapning: 'Läs av staplarna — värdena står över dem.'
    };
    if (/derivat|funktion|graf|exponent|logaritm|tillväxt|tillvaxt|avtag|potens|ekvation/.test(m)) return {
      fig: { typ: 'graf', uttryck: 'x => calc.pow(1.14, x)', xmax: 20, ymax: 14, xnamn: 'x', ynamn: 'y' },
      kapning: 'Grafen är till för att läsa av — jämför med ert räknade svar.'
    };
    return null;
  }

  /* Beskrivningen till CeTZ-källa. Okänd typ ger ingen tom ruta utan ett tydligt
     fel i konsolen — en figur som saknas är en bugg, inte ett designval. */
  function kalla(fig) {
    if (!fig || !fig.typ) return null;
    const g = katalog[fig.typ];
    if (!g) { console.warn('Okänd figurtyp:', fig.typ); return null; }
    return g(fig);
  }

  return { kalla, katalog, forslagFor, matt: { BREDD, HOJD }, typer: () => Object.keys(katalog) };
})();
