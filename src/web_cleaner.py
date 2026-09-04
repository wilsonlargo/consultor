from __future__ import annotations

from PySide6.QtWebEngineCore import QWebEngineUrlRequestInterceptor


class AdTrackerInterceptor(QWebEngineUrlRequestInterceptor):
    BLOCKED_HOST_PARTS = (
        "doubleclick.net",
        "googlesyndication.com",
        "googleadservices.com",
        "amazon-adsystem.com",
        "adnxs.com",
        "adsrvr.org",
        "criteo.com",
        "criteo.net",
        "outbrain.com",
        "taboola.com",
        "pubmatic.com",
        "rubiconproject.com",
        "openx.net",
        "casalemedia.com",
        "quantserve.com",
        "scorecardresearch.com",
    )

    def interceptRequest(self, info):
        host = info.requestUrl().host().lower()
        if any(part in host for part in self.BLOCKED_HOST_PARTS):
            info.block(True)


def cleanup_javascript(host: str) -> str:
    """
    Modo limpio permanente.

    No extrae ni modifica el texto bíblico. Solo:
    - oculta publicidad/promociones;
    - reduce cabeceras y navegación del sitio;
    - desplaza la vista hacia el pasaje.
    """
    host = (host or "").lower()

    common = r"""
    (() => {
      const hide = (selector) => {
        document.querySelectorAll(selector).forEach(el => {
          el.style.setProperty('display', 'none', 'important');
        });
      };

      [
        '[id^="ad-"]',
        '[id*="-ad-"]',
        '[id*="advert"]',
        '[class^="ad-"]',
        '[class*=" ad-"]',
        '[class*="advert"]',
        '[class*="Advertisement"]',
        '[data-ad]',
        '[data-ad-slot]',
        '[aria-label="advertisement"]',
        '[aria-label="Advertisement"]'
      ].forEach(hide);

      document.querySelectorAll('iframe').forEach(frame => {
        const src = (frame.src || '').toLowerCase();
        const blocked = [
          'doubleclick.net',
          'googlesyndication.com',
          'amazon-adsystem.com',
          'criteo',
          'taboola',
          'outbrain'
        ];
        if (blocked.some(x => src.includes(x))) {
          frame.style.setProperty('display', 'none', 'important');
        }
      });

      // Oculta banners promocionales por texto, aunque cambien de clase.
      const promoPhrases = [
        'daily inspiration from',
        'sign up for',
        'get the app',
        'download the app'
      ];
      document.querySelectorAll('body *').forEach(el => {
        const txt = (el.innerText || '').trim().toLowerCase();
        if (!txt || txt.length > 180) return;
        if (promoPhrases.some(p => txt.includes(p))) {
          const target =
            el.closest('aside,section,div,header,nav') || el;
          target.style.setProperty('display', 'none', 'important');
        }
      });
    })();
    """

    if "biblegateway.com" in host:
        return common + r"""
        (() => {
          const hide = (selector) => {
            document.querySelectorAll(selector).forEach(el => {
              el.style.setProperty('display', 'none', 'important');
            });
          };

          // Elementos de navegación del sitio que ocupan espacio en el panel.
          [
            'body > header',
            'header[role="banner"]',
            'nav',
            'footer',
            '.navbar',
            '.site-header',
            '.site-footer',
            '.advertisement',
            '.advertisement-container',
            '.ad-container',
            '.ad-wrapper',
            '.ad-unit',
            '[class*="adContainer"]',
            '[class*="AdContainer"]',
            '[data-testid*="advert"]'
          ].forEach(hide);

          // Reduce márgenes superiores residuales.
          document.documentElement.style.setProperty('scroll-padding-top', '0px');
          document.body.style.setProperty('margin-top', '0px');

          const candidates = [
            '.passage-content',
            '.passage-text',
            '[class*="passage-content"]',
            '[class*="passageContent"]',
            'main article',
            'main'
          ];

          let target = null;
          for (const selector of candidates) {
            target = document.querySelector(selector);
            if (target) break;
          }

          if (target) {
            const y = Math.max(
              0,
              target.getBoundingClientRect().top + window.scrollY - 8
            );
            window.scrollTo(0, y);
          }
        })();
        """

    if "stepbible.org" in host:
        return common + r"""
        (() => {
          document.querySelectorAll(
            '[class*="advert"], [id*="advert"]'
          ).forEach(el => {
            el.style.setProperty('display', 'none', 'important');
          });

          const target =
            document.querySelector('#passage') ||
            document.querySelector('[class*="passage"]') ||
            document.querySelector('main');

          if (target) {
            const y = Math.max(
              0,
              target.getBoundingClientRect().top + window.scrollY - 8
            );
            window.scrollTo(0, y);
          }
        })();
        """

    return common
