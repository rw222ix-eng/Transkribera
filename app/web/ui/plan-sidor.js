/* ── Sidor ur läroboken: PDF/foto som referens för genomgången ── */
(() => {
  const q = s => document.querySelector(s);
  const knapp = q('#sidknapp'), fil = q('#sidfil'), ut = q('#sidminis'), not = q('#sidnot'), ruta = q('#sidrad');
  if (!knapp) return;
  const lista = [], grund = not.textContent;
  window.Sidor = { lista: () => lista.map(r => ({ namn: r.namn, typ: r.typ })) };
  /* Sidorna ligger som små papper i en rad — dragbara, med appens tolkning under.
     Utan tolkningsraden vet läraren aldrig varför utkastet blev som det blev. */
  function rita() {
    ut.innerHTML = lista.map((r, i) => `<div class="sidmini" draggable="true" data-i="${i}">${r.url ? `<img class="sidbild" src="${r.url}" alt="" />` : '<span class="sidpdf">PDF</span>'}<span class="sidtext"><span class="sidnamn">${r.tolkning || r.namn}</span><span class="sidmeta">${i + 1} · ${r.typ} · ${r.namn}</span></span><button class="sidbort" type="button" data-i="${i}" aria-label="Ta bort ${r.namn}">×</button></div>`).join('');
    not.textContent = lista.length ? `${lista.length} ${lista.length === 1 ? 'fil' : 'filer'} lästa — bilderna stannar på datorn, bara tolkningen skickas.` : grund;
    knapp.querySelector('.valjtext').textContent = lista.length ? 'Lägg till fler' : 'Lägg till filer';
  }
  /* Fältet ersätts inte av bilden — det fylls i av sidans rubrik och bär
     gissningens streckade ram, precis som klass och kurs i kön. */
  function gissaMoment(tolkat) {
    const f = document.querySelector('#moment'), not2 = document.querySelector('#momentgissat');
    if (!f || !tolkat || f.value.trim()) return;
    f.value = tolkat.rubrik;
    f.setAttribute('data-gissad', '');
    if (not2) not2.hidden = false;
    f.dispatchEvent(new Event('input', { bubbles: true }));
    f.dispatchEvent(new Event('change', { bubbles: true }));
  }
  const momentfalt = document.querySelector('#moment');
  if (momentfalt) momentfalt.addEventListener('input', e => {
    if (!e.isTrusted) return;
    momentfalt.removeAttribute('data-gissad');
    const n = document.querySelector('#momentgissat');
    if (n) n.hidden = true;
  });
  function lagg(filer) {
    let forsta = null;
    [...filer].forEach(f => {
      const bild = (f.type || '').startsWith('image/');
      const tolkat = window.Bok ? window.Bok.tolka(f.name, lista.length) : null;
      lista.push({ namn: f.name, typ: bild ? 'foto' : 'pdf', url: bild ? URL.createObjectURL(f) : '', tolkning: tolkat ? tolkat.text : '' });
      if (!forsta) forsta = tolkat;
    });
    rita();
    gissaMoment(forsta);
  }
  /* Ordningen dras om — sidorna läses i den ordning de ligger */
  let drag = null;
  ut.addEventListener('dragstart', e => { const m = e.target.closest('.sidmini'); if (!m) return; drag = +m.dataset.i; e.dataTransfer.effectAllowed = 'move'; });
  ut.addEventListener('dragover', e => { e.preventDefault(); });
  ut.addEventListener('drop', e => {
    const m = e.target.closest('.sidmini');
    if (!m || drag === null) return;
    e.preventDefault();
    e.stopPropagation();
    const till = +m.dataset.i;
    lista.splice(till, 0, lista.splice(drag, 1)[0]);
    drag = null;
    rita();
  });
  knapp.addEventListener('click', () => fil.click());
  fil.addEventListener('change', () => { lagg(fil.files); fil.value = ''; });
  ut.addEventListener('click', e => {
    const b = e.target.closest('.sidbort');
    if (!b) return;
    const r = lista.splice(+b.dataset.i, 1)[0];
    if (r && r.url) URL.revokeObjectURL(r.url);
    rita();
  });
  ['dragover', 'dragenter'].forEach(t => ruta.addEventListener(t, e => { e.preventDefault(); ruta.setAttribute('data-over', ''); }));
  ['dragleave', 'drop'].forEach(t => ruta.addEventListener(t, e => { e.preventDefault(); ruta.removeAttribute('data-over'); }));
  ruta.addEventListener('drop', e => { if (e.dataTransfer && e.dataTransfer.files.length) lagg(e.dataTransfer.files); });
})();
