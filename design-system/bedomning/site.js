/* Shared chrome injection — header + footer.
   Reads data-current="<key>" from <body> to mark active nav item. */
(function () {
  const current = document.body.dataset.current || '';
  const navItems = [
    { key: 'schema', label: 'Schema', href: 'schema.html' },
    { key: 'bibliotek', label: 'Bibliotek', href: 'bibliotek.html' },
    { key: 'samarbete', label: 'Samarbete', href: 'samarbete.html' },
    { key: 'bedomning', label: 'Bedömning', href: 'bedomning.html' },
    { key: 'ai', label: 'AI-stöd', href: 'ai.html' },
    { key: 'prov', label: 'Prov', href: 'prov.html' },
    { key: 'kontakt', label: 'Kontakt', href: 'kontakt.html' }
  ];

  const headerHTML = `
    <header class="header" id="Header">
      <div class="header_inner">
        <a href="../MinaLektioner.html" class="header_logo">
          <svg class="header_logo_mark" viewBox="0 0 32 32" aria-hidden="true">
            <rect x="6" y="4" width="20" height="24" rx="2" fill="none" stroke="currentColor" stroke-width="1.4"/>
            <line x1="11" y1="11" x2="21" y2="11" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
            <line x1="11" y1="16" x2="21" y2="16" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
            <line x1="11" y1="21" x2="17" y2="21" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
            <circle cx="22" cy="21" r="2" fill="var(--coral)"/>
          </svg>
          <span class="header_logo_text">mina<em>lektioner</em></span>
        </a>
        <div class="header_center">
          <ul class="header_list">
            ${navItems.map(i => `<li><a href="${i.href}" class="header_list_link${current === i.key ? ' is-current' : ''}">${i.label}</a></li>`).join('')}
          </ul>
        </div>
        <div class="header_right">
          <a href="logga-in.html" class="header_right_link">
            <span>Logga in</span>
            <span class="header_right_link_arrow" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
            </span>
          </a>
        </div>
      </div>
    </header>`;

  const footerHTML = `
    <footer class="footer-main">
      <div class="footer-main_inner container">
        <a href="../MinaLektioner.html" class="footer-main_logo">
          <svg class="footer-main_logo_mark" viewBox="0 0 32 32" aria-hidden="true">
            <rect x="6" y="4" width="20" height="24" rx="2" fill="none" stroke="currentColor" stroke-width="1.4"/>
            <line x1="11" y1="11" x2="21" y2="11" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
            <line x1="11" y1="16" x2="21" y2="16" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
            <line x1="11" y1="21" x2="17" y2="21" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
            <circle cx="22" cy="21" r="2" fill="var(--coral)"/>
          </svg>
          <span class="footer-main_logo_text">mina<em>lektioner</em></span>
        </a>
        <div class="footer-main_body">
          <div class="footer-main_body_top">
            <ul class="footer-main_list-global">
              ${navItems.map(i => `<li><a href="${i.href}" class="footer-main_list-global_text${current === i.key ? ' is-current' : ''}">${i.label}</a></li>`).join('')}
            </ul>
          </div>
          <div class="footer-main_body_bottom_inner">
            <ul class="footer-main_list-sub">
              <li><a href="integritet.html" class="footer-main_list-sub_text">Integritet</a></li>
              <li><a href="villkor.html" class="footer-main_list-sub_text">Villkor</a></li>
            </ul>
            <ul class="footer-main_list-lang">
              <li><a href="#" class="footer-main_list-lang_text is-current">SV</a></li>
              <li><a href="#" class="footer-main_list-lang_text">EN</a></li>
            </ul>
          </div>
          <p class="footer-main_copy">© 2026 MinaLektioner · Gjord i Sverige</p>
        </div>
      </div>
    </footer>`;

  const headerSlot = document.getElementById('site-header');
  const footerSlot = document.getElementById('site-footer');
  if (headerSlot) headerSlot.outerHTML = headerHTML;
  if (footerSlot) footerSlot.outerHTML = footerHTML;

  // Scroll state
  const onScroll = () => {
    const h = document.getElementById('Header');
    if (!h) return;
    if (window.scrollY > 20) h.classList.add('scrolled'); else h.classList.remove('scrolled');
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  // In-view observer
  const io = new IntersectionObserver((entries) => {
    entries.forEach(e => { if (e.isIntersecting) e.target.classList.add('is-in'); });
  }, { threshold: 0.15 });
  document.querySelectorAll('.in-view-mask, .in-view-fade').forEach(el => io.observe(el));
})();
