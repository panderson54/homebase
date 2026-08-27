class TestLogin:
    def test_dashboard_requires_login(self, client):
        resp = client.get('/dashboard')
        assert resp.status_code == 302
        assert '/login' in resp.headers['Location']

    def test_login_success_redirects_to_dashboard(self, client, user):
        resp = client.post('/login', data={'email': user.email, 'password': 'password123'})
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith('/dashboard')

    def test_login_wrong_password_returns_401(self, client, user):
        resp = client.post('/login', data={'email': user.email, 'password': 'wrong'})
        assert resp.status_code == 401

    def test_login_unknown_email_returns_401(self, client, db):
        resp = client.post('/login', data={'email': 'nobody@example.com', 'password': 'x'})
        assert resp.status_code == 401

    def test_logout_requires_login(self, client):
        resp = client.post('/logout')
        assert resp.status_code == 302

    def test_logout_then_dashboard_redirects_again(self, logged_in_client):
        logged_in_client.post('/logout')
        resp = logged_in_client.get('/dashboard')
        assert resp.status_code == 302
