import pytest
from starlette.testclient import TestClient

from app import create_app, mcp_token_service
from app.mcp_http import create_asgi_app

TOKEN = 'hbmcp_test-token'
MCP_HEADERS = {
    'Authorization': f'Bearer {TOKEN}',
    'Accept': 'application/json, text/event-stream',
    'MCP-Protocol-Version': '2025-06-18',
}


def _rpc(method, params=None):
    return {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}}


@pytest.fixture
def asgi_client(app):
    app.config['MCP_TOKENS'] = {'muse': mcp_token_service.hash_token(TOKEN)}
    with TestClient(create_asgi_app(app), follow_redirects=False) as client:
        yield client


class TestTokenConfig:
    def test_parse_normalizes_and_skips_blanks(self):
        digest = 'A' * 64
        assert mcp_token_service.parse_tokens(f' Muse:{digest} , ,') == {'muse': 'a' * 64}

    def test_parse_empty(self):
        assert mcp_token_service.parse_tokens(None) == {}

    @pytest.mark.parametrize('raw', [
        'muse',                                # no hash
        'muse:abc123',                         # not a sha256
        f'muse:{TOKEN}',                       # raw token pasted instead of its hash
        f'bad name:{"a" * 64}',
        f'muse:{"a" * 64},muse:{"b" * 64}',    # duplicate
    ])
    def test_parse_rejects_malformed(self, raw):
        with pytest.raises(mcp_token_service.McpTokenConfigError):
            mcp_token_service.parse_tokens(raw)

    def test_error_never_echoes_the_value(self):
        with pytest.raises(mcp_token_service.McpTokenConfigError) as e:
            mcp_token_service.parse_tokens(f'muse:{TOKEN}')
        assert TOKEN not in str(e.value)

    def test_find_client(self):
        tokens = {'muse': mcp_token_service.hash_token(TOKEN), 'other': 'f' * 64}
        assert mcp_token_service.find_client(TOKEN, tokens) == 'muse'
        assert mcp_token_service.find_client('wrong', tokens) is None
        assert mcp_token_service.find_client(None, tokens) is None
        assert mcp_token_service.find_client(TOKEN, {}) is None

    def test_malformed_env_stops_startup(self, monkeypatch):
        monkeypatch.setenv('HOMEBASE_MCP_TOKENS', 'muse:not-a-hash')
        with pytest.raises(mcp_token_service.McpTokenConfigError):
            create_app()

    def test_cli_output_round_trips_into_config(self, app):
        result = app.test_cli_runner().invoke(args=['mcp-token', 'Muse'])
        assert result.exit_code == 0
        lines = [line.strip() for line in result.output.splitlines()]
        token = next(line for line in lines if line.startswith(mcp_token_service.TOKEN_PREFIX))
        entry = next(line for line in lines if line.startswith('muse:'))
        assert mcp_token_service.find_client(token, mcp_token_service.parse_tokens(entry)) == 'muse'

    def test_cli_rejects_bad_name(self, app):
        result = app.test_cli_runner().invoke(args=['mcp-token', 'not ok'])
        assert result.exit_code != 0


class TestMcpEndpointAuth:
    @pytest.mark.parametrize('headers', [
        {},
        {'Authorization': 'Bearer wrong'},
        {'Authorization': f'Basic {TOKEN}'},
    ])
    def test_rejected_without_valid_bearer_token(self, asgi_client, headers):
        resp = asgi_client.post('/mcp', headers=headers, json=_rpc('tools/list'))
        assert resp.status_code == 401
        assert resp.headers['WWW-Authenticate'].startswith('Bearer')

    def test_revoked_token_rejected(self, app, asgi_client):
        app.config['MCP_TOKENS'] = {}
        assert asgi_client.post('/mcp', headers=MCP_HEADERS, json=_rpc('tools/list')).status_code == 401

    def test_token_does_not_unlock_the_website(self, asgi_client):
        resp = asgi_client.get('/dashboard', headers=MCP_HEADERS)
        assert resp.status_code == 302
        assert '/login' in resp.headers['Location']


class TestMcpEndpoint:
    def test_lists_tools_without_any_review_tool(self, asgi_client):
        resp = asgi_client.post('/mcp', headers=MCP_HEADERS, json=_rpc('tools/list'))
        assert resp.status_code == 200
        tools = {tool['name']: tool for tool in resp.json()['result']['tools']}
        assert 'list_vendors' in tools and 'submit_feature_request' in tools
        assert not any('review' in name or 'approve' in name for name in tools)
        # The app-context wrapper must keep each tool's real signature for its schema.
        assert {'service_date', 'appliance_id', 'vendor_name'} <= set(tools['create_service']['inputSchema']['properties'])

    def test_tool_call_reads_household_data(self, asgi_client, vendor):
        resp = asgi_client.post('/mcp', headers=MCP_HEADERS, json=_rpc(
            'tools/call', {'name': 'list_vendors', 'arguments': {}},
        ))
        assert resp.status_code == 200
        assert resp.json()['result']['structuredContent']['result'] == [
            {'id': vendor.id, 'name': 'ACME HVAC', 'vendor_type': 'HVAC'},
        ]

    def test_validation_errors_reach_the_agent(self, asgi_client, household):
        resp = asgi_client.post('/mcp', headers=MCP_HEADERS, json=_rpc(
            'tools/call', {'name': 'create_service', 'arguments': {'service_date': '2026-10-01'}},
        ))
        result = resp.json()['result']
        assert result['isError'] is True
        assert 'Pass exactly one of appliance_id or zone_id' in result['content'][0]['text']


class TestSiteThroughAsgi:
    def test_public_login_page_served(self, asgi_client):
        assert asgi_client.get('/login').status_code == 200
