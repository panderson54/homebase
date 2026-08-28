from app import ai_client, appliance_lookup_service


class TestLookupAppliance:
    def test_no_input_returns_empty_dict(self):
        assert appliance_lookup_service.lookup_appliance() == {}

    def test_returns_fields_from_ai_client(self, monkeypatch):
        monkeypatch.setattr(ai_client, 'ask_json', lambda *a, **k: {
            'make': 'Whirlpool', 'category': 'dishwasher', 'pro_service_interval_unit': 'years',
        })
        result = appliance_lookup_service.lookup_appliance(model_number='WDT730PAHZ0')
        assert result['make'] == 'Whirlpool'
        assert result['category'] == 'dishwasher'
        assert result['pro_service_interval_unit'] == 'years'

    def test_invalid_category_is_nulled(self, monkeypatch):
        monkeypatch.setattr(ai_client, 'ask_json', lambda *a, **k: {'category': 'not-a-real-category'})
        result = appliance_lookup_service.lookup_appliance(model_number='X123')
        assert result['category'] is None

    def test_invalid_interval_unit_is_nulled(self, monkeypatch):
        monkeypatch.setattr(ai_client, 'ask_json', lambda *a, **k: {'pro_service_interval_unit': 'fortnights'})
        result = appliance_lookup_service.lookup_appliance(model_number='X123')
        assert result['pro_service_interval_unit'] is None

    def test_ai_client_failure_returns_empty_dict(self, monkeypatch):
        monkeypatch.setattr(ai_client, 'ask_json', lambda *a, **k: None)
        assert appliance_lookup_service.lookup_appliance(model_number='X123') == {}

    def test_photo_only_still_calls_ai_client(self, monkeypatch):
        called = {}
        def fake_ask_json(system_prompt, user_text=None, image_bytes=None, image_media_type=None):
            called['image_bytes'] = image_bytes
            return {'make': 'GE'}
        monkeypatch.setattr(ai_client, 'ask_json', fake_ask_json)
        result = appliance_lookup_service.lookup_appliance(image_bytes=b'fake-image-bytes')
        assert result['make'] == 'GE'
        assert called['image_bytes'] == b'fake-image-bytes'
