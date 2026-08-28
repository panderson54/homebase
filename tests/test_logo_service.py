from app import logo_service


class TestFaviconUrlFor:
    def test_builds_url_from_bare_domain(self):
        url = logo_service.favicon_url_for('acmehvac.com')
        assert url == 'https://www.google.com/s2/favicons?domain=acmehvac.com&sz=128'

    def test_builds_url_from_full_https_url(self):
        url = logo_service.favicon_url_for('https://www.acmehvac.com/contact')
        assert url == 'https://www.google.com/s2/favicons?domain=www.acmehvac.com&sz=128'

    def test_blank_returns_none(self):
        assert logo_service.favicon_url_for('') is None
        assert logo_service.favicon_url_for(None) is None

    def test_strips_path_and_query(self):
        url = logo_service.favicon_url_for('http://acmehvac.com/contact?ref=footer')
        assert url == 'https://www.google.com/s2/favicons?domain=acmehvac.com&sz=128'

    def test_whitespace_only_returns_none(self):
        assert logo_service.favicon_url_for('   ') is None
