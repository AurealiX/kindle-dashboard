"""天气采集(和风天气 QWeather / Open-Meteo)。服务端直采。

两个 provider,产出同一套缓存键(weather_now/weather_daily/weather_city),
build_context 与全部风格零改动:
- qweather:host+key+LocationID;城市选择器走 GeoAPI。
- open_meteo:免 Key 免注册,location 存 "lat,lon";城市选择器走 open-meteo geocoding。

城市显示名优先用配置里的 location_name(用户选城市时写入);qweather 为空则 GeoAPI 反查并缓存。
"""
import httpx

# (host, location) -> 城市名,避免每轮采集重复反查(LocationID 对应的城市名不会变)
_city_name_cache = {}

# ---- Open-Meteo:WMO weather code → (en, zh) 文案 ----
_WMO = {
    0: ("Clear", "晴"), 1: ("Mostly clear", "晴间多云"), 2: ("Partly cloudy", "多云"),
    3: ("Overcast", "阴"), 45: ("Fog", "雾"), 48: ("Rime fog", "雾凇"),
    51: ("Light drizzle", "毛毛雨"), 53: ("Drizzle", "细雨"), 55: ("Heavy drizzle", "浓毛毛雨"),
    56: ("Freezing drizzle", "冻毛毛雨"), 57: ("Freezing drizzle", "冻毛毛雨"),
    61: ("Light rain", "小雨"), 63: ("Rain", "中雨"), 65: ("Heavy rain", "大雨"),
    66: ("Freezing rain", "冻雨"), 67: ("Freezing rain", "冻雨"),
    71: ("Light snow", "小雪"), 73: ("Snow", "中雪"), 75: ("Heavy snow", "大雪"),
    77: ("Snow grains", "米雪"), 80: ("Light showers", "小阵雨"), 81: ("Showers", "阵雨"),
    82: ("Heavy showers", "强阵雨"), 85: ("Snow showers", "阵雪"), 86: ("Snow showers", "阵雪"),
    95: ("Thunderstorm", "雷阵雨"), 96: ("Thunderstorm + hail", "雷阵雨伴冰雹"),
    99: ("Thunderstorm + hail", "雷阵雨伴冰雹"),
}

_DIRS_EN = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
_DIRS_ZH = ["北风", "东北风", "东北风", "东北风", "东风", "东南风", "东南风", "东南风",
            "南风", "西南风", "西南风", "西南风", "西风", "西北风", "西北风", "西北风"]

# 蒲福风级上限(km/h),索引即级数 —— zh 显示 "西北风3级" 用
_BEAUFORT_KMH = [1, 5, 11, 19, 28, 38, 49, 61, 74, 88, 102, 117]


def _wmo_text(code, en: bool) -> str:
    pair = _WMO.get(int(code) if code is not None else -1)
    if not pair:
        return "--"
    return pair[0] if en else pair[1]


def _compass(deg, en: bool) -> str:
    try:
        i = int((float(deg) + 11.25) // 22.5) % 16
    except (TypeError, ValueError):
        return ""
    return _DIRS_EN[i] if en else _DIRS_ZH[i]


def _beaufort(speed: float, imperial: bool) -> int:
    kmh = speed * 1.609344 if imperial else speed
    for lvl, top in enumerate(_BEAUFORT_KMH):
        if kmh <= top:
            return lvl
    return 12


def search_city(host: str, key: str, q: str) -> list:
    """按城市名/拼音搜索,返回候选 [{id, name, adm2, adm1}]。供设置网页城市选择器用。
    重名(如"朝阳")会返回多条,带 adm2(市)/adm1(省)供消歧。"""
    host = (host or "").strip()
    key = (key or "").strip()
    q = (q or "").strip()
    if not (host and key and q):
        return []
    url = f"https://{host}/geo/v2/city/lookup"
    with httpx.Client(timeout=10) as c:
        r = c.get(url, params={"location": q, "key": key, "number": 10},
                  headers={"Accept-Encoding": "gzip"}).json()
    if r.get("code") != "200":
        return []
    return [{"id": x.get("id"), "name": x.get("name"),
             "adm2": x.get("adm2"), "adm1": x.get("adm1")}
            for x in (r.get("location") or [])]


def lookup_city_name(host: str, key: str, location: str) -> str:
    """反查 LocationID 对应的城市名,结果缓存。查不到返回空串。"""
    host = (host or "").strip()
    key = (key or "").strip()
    location = (location or "").strip()
    if not (host and key and location):
        return ""
    ck = (host, location)
    if ck in _city_name_cache:
        return _city_name_cache[ck]
    name = ""
    try:
        hits = search_city(host, key, location)   # GeoAPI lookup 也吃 LocationID
        if hits:
            name = hits[0].get("name") or ""
    except Exception as e:
        print(f"[weather] city lookup: {e}")
    if name:
        _city_name_cache[ck] = name
    return name


def search_city_open_meteo(q: str, lang: str = "en") -> list:
    """Open-Meteo geocoding 城市搜索(免 Key)。返回与 search_city 同形:
    [{id, name, adm2, adm1}],其中 id 为 "lat,lon"(采集端按它定位)。"""
    q = (q or "").strip()
    if not q:
        return []
    url = "https://geocoding-api.open-meteo.com/v1/search"
    with httpx.Client(timeout=10) as c:
        r = c.get(url, params={"name": q, "count": 10, "language": lang,
                               "format": "json"}).json()
    out = []
    for x in (r.get("results") or []):
        lat, lon = x.get("latitude"), x.get("longitude")
        if lat is None or lon is None:
            continue
        out.append({
            "id": f"{lat:.4f},{lon:.4f}",
            "name": x.get("name") or "",
            "adm2": x.get("admin2") or x.get("admin1") or "",
            "adm1": x.get("admin1") or x.get("country") or "",
        })
    return out


def _collect_open_meteo(w: dict, lang: str):
    """Open-Meteo 采集:location="lat,lon" → 当前 + 今明两天,归一成 QWeather 形状。"""
    loc = (w.get("location") or "").strip()
    if "," not in loc:
        return None         # 还没用城市选择器选过(或填的是 QWeather LocationID)→ 降级
    try:
        lat, lon = (float(p) for p in loc.split(",", 1))
    except ValueError:
        return None
    en = lang == "en"
    imperial = (w.get("units") or "metric") == "imperial"
    params = {
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,"
                   "weather_code,wind_speed_10m,wind_direction_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min",
        "forecast_days": 2, "timezone": "auto",
    }
    if imperial:
        params["temperature_unit"] = "fahrenheit"
        params["wind_speed_unit"] = "mph"
    try:
        with httpx.Client(timeout=10) as c:
            r = c.get("https://api.open-meteo.com/v1/forecast", params=params).json()
    except Exception as e:
        print(f"[weather] open-meteo: {e}")
        return None
    cur = r.get("current") or {}
    daily = r.get("daily") or {}
    if not cur:
        print(f"[weather] open-meteo api: {r.get('reason') or 'no current data'}")
        return None
    spd = cur.get("wind_speed_10m") or 0
    if en:
        wind_scale = f" {round(spd)} {'mph' if imperial else 'km/h'}"
    else:
        wind_scale = str(_beaufort(spd, imperial))   # build_context 会补「级」
    now = {
        "temp": str(round(cur.get("temperature_2m", 0))),
        "text": _wmo_text(cur.get("weather_code"), en),
        "feelsLike": str(round(cur.get("apparent_temperature", 0))),
        "humidity": str(round(cur.get("relative_humidity_2m", 0))),
        "windDir": _compass(cur.get("wind_direction_10m"), en),
        "windScale": wind_scale,
    }
    out_daily = []
    for i in range(len(daily.get("time") or [])):
        out_daily.append({
            "tempMin": str(round(daily["temperature_2m_min"][i])),
            "tempMax": str(round(daily["temperature_2m_max"][i])),
            "textDay": _wmo_text(daily["weather_code"][i], en),
        })
    city = (w.get("location_name") or "").strip()
    return {"weather_now": now, "weather_daily": out_daily, "weather_city": city}


def collect(cfg: dict):
    w = (cfg or {}).get("weather", {})
    lang = ((cfg or {}).get("server", {}) or {}).get("language") or "zh"
    if (w.get("provider") or "qweather") == "open_meteo":
        return _collect_open_meteo(w, lang)
    key = (w.get("key") or "").strip()
    host = (w.get("host") or "").strip()
    loc = (w.get("location") or "").strip()
    if not (key and host and loc):
        return None
    base = f"https://{host}/v7"
    params = {"location": loc, "key": key}
    headers = {"Accept-Encoding": "gzip"}
    try:
        with httpx.Client(timeout=10) as c:
            nd = c.get(f"{base}/weather/now", params=params, headers=headers).json()
            dd = c.get(f"{base}/weather/3d", params=params, headers=headers).json()
    except Exception as e:
        print(f"[weather] {e}")
        return None
    if nd.get("code") == "200" and dd.get("code") == "200":
        city = (w.get("location_name") or "").strip() or lookup_city_name(host, key, loc)
        return {"weather_now": nd["now"], "weather_daily": dd["daily"], "weather_city": city}
    print(f"[weather] api code now={nd.get('code')} 3d={dd.get('code')}")
    return None
