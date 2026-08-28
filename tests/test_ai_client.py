from app import ai_client


class _FakeBlock:
    def __init__(self, text):
        self.type = 'text'
        self.text = text


class _FakeMessages:
    def __init__(self, text, raise_error=False):
        self._text = text
        self._raise_error = raise_error

    def create(self, **kwargs):
        if self._raise_error:
            raise RuntimeError('boom')
        response = type('Response', (), {})()
        response.content = [_FakeBlock(self._text)]
        return response


class _FakeClient:
    def __init__(self, text, raise_error=False):
        self.messages = _FakeMessages(text, raise_error)


class TestAskJson:
    def test_returns_none_without_api_key(self, monkeypatch):
        monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
        assert ai_client.ask_json('system', user_text='hi') is None

    def test_parses_valid_json_response(self, monkeypatch):
        monkeypatch.setattr(ai_client, '_client', lambda: _FakeClient('{"make": "Whirlpool"}'))
        assert ai_client.ask_json('system', user_text='hi') == {'make': 'Whirlpool'}

    def test_strips_markdown_code_fence(self, monkeypatch):
        monkeypatch.setattr(ai_client, '_client', lambda: _FakeClient('```json\n{"make": "GE"}\n```'))
        assert ai_client.ask_json('system', user_text='hi') == {'make': 'GE'}

    def test_returns_none_for_invalid_json(self, monkeypatch):
        monkeypatch.setattr(ai_client, '_client', lambda: _FakeClient('not json'))
        assert ai_client.ask_json('system', user_text='hi') is None

    def test_returns_none_on_api_error(self, monkeypatch):
        monkeypatch.setattr(ai_client, '_client', lambda: _FakeClient('', raise_error=True))
        assert ai_client.ask_json('system', user_text='hi') is None
