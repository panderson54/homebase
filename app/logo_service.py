"""Looks up a vendor's logo/favicon from its website, via Google's public
favicon service — no API key, no scraping, no server-side HTTP call: the
browser fetches the image directly when it renders the <img> tag, so this
module only builds the URL.
"""
from urllib.parse import urlparse

FAVICON_SIZE = 128


def favicon_url_for(website):
    """Returns a URL for the given website's favicon, or None if `website`
    isn't a usable http(s) URL with a hostname."""
    website = (website or '').strip()
    if not website:
        return None
    if '//' not in website:
        website = f'//{website}'

    host = urlparse(website, scheme='https').hostname
    if not host:
        return None

    return f'https://www.google.com/s2/favicons?domain={host}&sz={FAVICON_SIZE}'
