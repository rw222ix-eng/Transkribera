/* ============================================================
   card-modal.js — click any card to zoom it into a large modal.
   Used on schema.html (.scard) and bedomning.html (.flow_step).

   The cards also have a hover "magnify" (scale 1.36) + a sibling
   "out of focus" blur. That hover state fights the modal on the way
   out (the grid gets revealed mid-hover and snaps). To avoid any
   flash/jump we FREEZE the whole row in its calm resting state for
   the entire life of the modal — from open, through close, until the
   user next moves the mouse — so the grid behind is always
   consistent and the zoom clone lands exactly on the resting card.
   Natural hover only re-engages on a real mouse move (smooth).
   ============================================================ */
(function cardZoomModal() {
  var SELECTOR = '.scard, .flow_step';
  var cards = document.querySelectorAll(SELECTOR);
  if (!cards.length) return;

  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var EASE = 'cubic-bezier(.16, 1, .3, 1)';
  var OPEN_MS = reduce ? 320 : 620;
  var CLOSE_MS = reduce ? 240 : 480;

  var style = document.createElement('style');
  style.textContent = [
    '.cardzoom{position:fixed;inset:0;z-index:1000;cursor:zoom-out;',
    'background:rgba(20,22,18,0);',
    '-webkit-backdrop-filter:blur(0px);backdrop-filter:blur(0px);',
    'transition:background .5s ' + EASE + ',backdrop-filter .5s ' + EASE + ';}',
    '.cardzoom.is-on{background:rgba(20,22,18,0.55);',
    '-webkit-backdrop-filter:blur(7px) saturate(.92);backdrop-filter:blur(7px) saturate(.92);}',
    '.cardzoom_card{transform-origin:top left;',
    'box-shadow:0 44px 90px -24px rgba(0,0,0,.5),0 18px 44px -20px rgba(0,0,0,.38);}',
    '.cardzoom-open{cursor:zoom-in;}',
    /* FROZEN row: force every card to its resting look (no hover magnify,
       no sibling dim) and kill transitions so it can't ramp/flash. */
    '.cz-frozen .scard,.cz-frozen .flow_step,.cz-frozen .scard_block{',
    'transition:none!important;}',
    '.cz-frozen .scard,.cz-frozen .flow_step{',
    'filter:none!important;opacity:1!important;transform:none!important;}',
    '.cz-frozen .scard_block{transform:none!important;box-shadow:none!important;',
    'border-color:var(--line)!important;}'
  ].join('');
  document.head.appendChild(style);

  var active = null;   /* { overlay, clone, card, row, finalTransform } */
  var busy = false;

  /* Lock page scroll WITHOUT the layout shifting: removing the scrollbar
     widens the page by its width, so we pad that width back on. */
  var prevBodyOverflow = '', prevBodyPadRight = '';
  function lockScroll() {
    var sbw = window.innerWidth - document.documentElement.clientWidth;
    prevBodyOverflow = document.body.style.overflow;
    prevBodyPadRight = document.body.style.paddingRight;
    document.body.style.overflow = 'hidden';
    if (sbw > 0) {
      var cur = parseFloat(getComputedStyle(document.body).paddingRight) || 0;
      document.body.style.paddingRight = (cur + sbw) + 'px';
    }
  }
  function unlockScroll() {
    document.body.style.overflow = prevBodyOverflow;
    document.body.style.paddingRight = prevBodyPadRight;
  }

  function rowOf(card) { return card.closest('.flow, .features-row') || card.parentElement; }

  /* The zoom shows a CLONE of the card; a fresh clone restarts every CSS
     animation from frame 0, which reads as a "reset" each time you open. Copy
     the live animation clock from the real card onto the clone so the looping
     card animations carry on seamlessly (and stay in phase for the close). */
  function syncAnimations(srcRoot, cloneRoot) {
    if (!srcRoot.getAnimations || !cloneRoot.getAnimations) return;
    var src, cln;
    try {
      src = srcRoot.getAnimations({ subtree: true });
      cln = cloneRoot.getAnimations({ subtree: true });
    } catch (e) { return; }
    for (var i = 0; i < cln.length && i < src.length; i++) {
      try {
        if (src[i].currentTime != null) cln[i].currentTime = src[i].currentTime;
      } catch (e) {}
    }
  }

  /* remove the freeze the next time the pointer actually moves, so hover
     re-engages smoothly under the cursor rather than snapping on reveal.
     Listeners attach directly (no rAF) so this still works if the tab was
     backgrounded during the close. done() is invoked from an animation
     callback, not a pointer event, so there's no spurious same-tick move. */
  function unfreezeOnMove(row) {
    var release = function () {
      row.classList.remove('cz-frozen');
      document.removeEventListener('mousemove', release);
      document.removeEventListener('wheel', release);
      document.removeEventListener('touchstart', release);
    };
    document.addEventListener('mousemove', release, { passive: true, once: true });
    document.addEventListener('wheel', release, { passive: true, once: true });
    document.addEventListener('touchstart', release, { passive: true, once: true });
  }

  function open(card) {
    if (active || busy) return;
    var row = rowOf(card);

    /* freeze the row to its resting state, THEN measure — so the rect is the
       card's true resting box even if it was hover-magnified at click time */
    row.classList.add('cz-frozen');
    var rect = card.getBoundingClientRect();

    var vw = window.innerWidth, vh = window.innerHeight;
    var margin = Math.max(40, Math.min(vw, vh) * 0.07);
    var availW = vw - margin * 2, availH = vh - margin * 2;
    var f = Math.min(availW / rect.width, availH / rect.height);
    f = Math.max(1, Math.min(f, 5));

    var scaledW = rect.width * f, scaledH = rect.height * f;
    var finalLeft = (vw - scaledW) / 2, finalTop = (vh - scaledH) / 2;
    var tx = finalLeft - rect.left, ty = finalTop - rect.top;
    var finalTransform = 'translate(' + tx + 'px,' + ty + 'px) scale(' + f + ')';

    var overlay = document.createElement('div');
    overlay.className = 'cardzoom';

    var clone = card.cloneNode(true);
    clone.classList.add('cardzoom_card');
    clone.style.position = 'fixed';
    clone.style.margin = '0';
    clone.style.left = rect.left + 'px';
    clone.style.top = rect.top + 'px';
    clone.style.width = rect.width + 'px';
    clone.style.height = rect.height + 'px';
    clone.style.pointerEvents = 'none';
    clone.style.transition = 'none';
    clone.style.transform = finalTransform;   /* rest on the enlarged state */

    var block = clone.querySelector('.scard_block');
    if (block) { block.style.transform = 'none'; block.style.transition = 'none'; block.style.boxShadow = 'none'; }

    overlay.appendChild(clone);
    document.body.appendChild(overlay);
    lockScroll();

    /* match the clone's animation phase to the live card so nothing resets */
    void clone.offsetWidth;   /* ensure the clone's CSS animations exist */
    syncAnimations(card, clone);

    requestAnimationFrame(function () { overlay.classList.add('is-on'); });

    if (clone.animate) {
      var oa = clone.animate(
        [{ transform: 'none' }, { transform: finalTransform }],
        { duration: OPEN_MS, easing: EASE, fill: 'none' }
      );
      var settle = function () { try { oa.cancel(); } catch (e) {} };
      var safety = setTimeout(settle, OPEN_MS + 300);
      oa.onfinish = function () { clearTimeout(safety); settle(); };
    }

    overlay.addEventListener('click', close);
    active = { overlay: overlay, clone: clone, card: card, row: row, finalTransform: finalTransform };
  }

  function close() {
    if (!active || busy) return;
    busy = true;
    var overlay = active.overlay, clone = active.clone,
        row = active.row, finalTransform = active.finalTransform;

    overlay.classList.remove('is-on');

    var done = function () {
      overlay.remove();
      unlockScroll();
      /* the row is still frozen (resting) — the revealed grid matches the
         clone's landing spot exactly, so there's no snap. Release the freeze
         on the next pointer move so hover resumes smoothly. */
      unfreezeOnMove(row);
      active = null;
      busy = false;
    };

    if (clone.animate) {
      var anim = clone.animate(
        [{ transform: finalTransform }, { transform: 'none' }],
        { duration: CLOSE_MS, easing: EASE, fill: 'forwards' }
      );
      clone.style.transform = 'none';
      anim.onfinish = done;
      anim.oncancel = done;
      setTimeout(done, CLOSE_MS + 150);
    } else {
      done();
    }
  }

  cards.forEach(function (card) {
    card.classList.add('cardzoom-open');
    card.addEventListener('click', function (e) {
      e.preventDefault();
      open(card);
    });
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') close();
  });
})();
