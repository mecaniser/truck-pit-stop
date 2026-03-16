from __future__ import annotations

import pytest

from app.services import website_logo_service as svc


def test_parse_website_logo_candidates_prefers_explicit_logo_sources():
    html = """
    <html>
      <head>
        <meta property="og:image" content="https://garage.example.com/social-card.png" />
        <link rel="icon" href="/favicon-32x32.png" sizes="32x32" />
        <script type="application/ld+json">
          {"@context": "https://schema.org", "@type": "Organization", "logo": "/brand-logo.svg"}
        </script>
      </head>
      <body>
        <img src="/header-logo.png" alt="Truck Pit Stop logo" />
      </body>
    </html>
    """

    result = svc.parse_website_logo_candidates(html, "https://garage.example.com/about")

    assert result.candidates[0].url == "https://garage.example.com/header-logo.png"
    assert result.candidates[0].source == "img.logo.src"
    assert any(candidate.url == "https://garage.example.com/brand-logo.svg" for candidate in result.candidates)
    assert any(candidate.url == "https://garage.example.com/favicon.ico" for candidate in result.candidates)


def test_parse_website_logo_candidates_collects_manifest_and_fallback():
    html = """
    <html>
      <head>
        <link rel="manifest" href="/site.webmanifest" />
      </head>
      <body></body>
    </html>
    """

    result = svc.parse_website_logo_candidates(html, "https://garage.example.com")

    assert result.manifest_urls == ["https://garage.example.com/site.webmanifest"]
    assert result.candidates[-1].url == "https://garage.example.com/favicon.ico"


def test_parse_website_logo_candidates_prefers_lazy_loaded_header_logo_over_generic_filename_logo():
    html = """
    <html>
      <body>
        <div class="elementor-widget-pxl_logo">
          <img
            class="logo-light attachment-full lazyload"
            data-src="https://truckpitstop.com/wp-content/uploads/2025/01/Trasp-white-1080x400-1.png"
            src="data:image/gif;base64,AAAA"
            width="1080"
            height="400"
            alt="Trasp white 1080x400"
          />
        </div>
        <section>
          <img
            src="https://truckpitstop.com/wp-content/uploads/2025/01/Freightliner-Logo.png"
            alt="Freightliner Logo"
            width="600"
            height="300"
          />
        </section>
      </body>
    </html>
    """

    result = svc.parse_website_logo_candidates(html, "https://truckpitstop.com/")

    assert result.candidates[0].url == "https://truckpitstop.com/wp-content/uploads/2025/01/Trasp-white-1080x400-1.png"
    assert result.candidates[0].source == "img.logo.data-src"
    assert any(
        candidate.url == "https://truckpitstop.com/wp-content/uploads/2025/01/Freightliner-Logo.png"
        for candidate in result.candidates
    )


@pytest.mark.asyncio
async def test_ensure_public_url_rejects_private_hosts():
    with pytest.raises(ValueError):
        await svc._ensure_public_url("http://127.0.0.1/logo.png")
