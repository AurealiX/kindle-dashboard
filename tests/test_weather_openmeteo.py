"""Open-Meteo provider: normalization to the QWeather cache shape + geocoding parse +
schema gating. All httpx calls are mocked — no network."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from server.sources import weather
from server.config import schema


class _FakeResp:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class _FakeClient:
    """Stands in for httpx.Client; returns canned payloads by URL."""
    payloads = {}

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def get(self, url, params=None, **k):
        for frag, data in self.payloads.items():
            if frag in url:
                self.captured_params = params
                _FakeClient.last_params = params
                return _FakeResp(data)
        raise AssertionError(f"unexpected url {url}")


_FORECAST = {
    "current": {"temperature_2m": 71.6, "relative_humidity_2m": 55,
                "apparent_temperature": 75.2, "weather_code": 2,
                "wind_speed_10m": 9.4, "wind_direction_10m": 300},
    "daily": {"time": ["2026-06-09", "2026-06-10"],
              "weather_code": [3, 61],
              "temperature_2m_max": [78.8, 71.1],
              "temperature_2m_min": [60.1, 55.9]},
}

_GEO = {"results": [
    {"name": "Chicago", "latitude": 41.85, "longitude": -87.65,
     "admin1": "Illinois", "admin2": "Cook", "country": "United States"},
    {"name": "Chicago Heights", "latitude": 41.5061, "longitude": -87.6356,
     "admin1": "Illinois", "country": "United States"},
]}


def _with_fake(monkeypatch, payloads):
    _FakeClient.payloads = payloads
    monkeypatch.setattr(weather.httpx, "Client", _FakeClient)


def test_collect_normalizes_to_qweather_shape(monkeypatch):
    _with_fake(monkeypatch, {"api.open-meteo.com": _FORECAST})
    cfg = {"server": {"language": "en"},
           "weather": {"provider": "open_meteo", "location": "41.85,-87.65",
                       "location_name": "Chicago", "units": "imperial"}}
    out = weather.collect(cfg)
    now = out["weather_now"]
    assert now["temp"] == "72" and now["feelsLike"] == "75"
    assert now["text"] == "Partly cloudy"
    assert now["humidity"] == "55"
    assert now["windDir"] == "WNW" and now["windScale"] == " 9 mph"
    d = out["weather_daily"]
    assert len(d) == 2
    assert d[0] == {"tempMin": "60", "tempMax": "79", "textDay": "Overcast"}
    assert d[1]["textDay"] == "Light rain"
    assert out["weather_city"] == "Chicago"
    # imperial units must reach the API params
    assert _FakeClient.last_params["temperature_unit"] == "fahrenheit"
    assert _FakeClient.last_params["wind_speed_unit"] == "mph"


def test_collect_zh_beaufort(monkeypatch):
    _with_fake(monkeypatch, {"api.open-meteo.com": _FORECAST})
    cfg = {"server": {"language": "zh"},
           "weather": {"provider": "open_meteo", "location": "41.85,-87.65"}}
    out = weather.collect(cfg)
    now = out["weather_now"]
    assert now["text"] == "多云"
    assert now["windDir"] == "西北风"
    # 9.4 km/h(metric)→ 蒲福 2 级;build_context 负责加「级」
    assert now["windScale"] == "2"


def test_collect_rejects_non_latlon_location(monkeypatch):
    _with_fake(monkeypatch, {"api.open-meteo.com": _FORECAST})
    cfg = {"weather": {"provider": "open_meteo", "location": "101010100"}}
    assert weather.collect(cfg) is None   # 残留 QWeather LocationID → 降级,不误调 API


def test_geocoding_parse(monkeypatch):
    _with_fake(monkeypatch, {"geocoding-api.open-meteo.com": _GEO})
    res = weather.search_city_open_meteo("chicago", "en")
    assert res[0]["id"] == "41.8500,-87.6500"
    assert res[0]["name"] == "Chicago"
    assert res[0]["adm2"] == "Cook" and res[0]["adm1"] == "Illinois"
    # second hit lacks admin2 → falls back to admin1 / country
    assert res[1]["adm2"] == "Illinois" and res[1]["adm1"] == "Illinois"


def test_schema_gating_open_meteo():
    c = schema.default_config()
    c["weather"]["provider"] = "open_meteo"
    # stale QWeather LocationID must NOT count as configured
    assert schema.enabled_modules(c)["weather"] is False
    c["weather"]["location"] = "41.85,-87.65"
    assert schema.enabled_modules(c)["weather"] is True
    assert schema.validate(c) == []      # no key needed for open_meteo


def test_wmo_fallback():
    assert weather._wmo_text(None, True) == "--"
    assert weather._wmo_text(42, True) == "--"   # unknown code degrades, never crashes
