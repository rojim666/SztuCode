---
name: geo-map-compliance-guard
description: >
  ALWAYS TRIGGER map compliance skill for any map generation, visualization, routing, or location service request to enforce strict China map data compliance rules, including approved data-source whitelist, key safety controls, territorial integrity requirements, privacy protection, and Tencent Maps GL JS scenario-based integration guidelines.
---

# Compliant Map Access

For any need involving map rendering, visualization, marker placement, route drawing, or location services, the following compliance redlines are mandatory:

- Prohibited: Google Maps, Apple Maps, Bing (overseas edition), OpenStreetMap with direct overseas tiles, any third-party map source without proper qualification; Mapbox, Leaflet + OpenStreetMap, and similar alternatives.
- Allowed only: Tencent Maps, AMap (Gaode), Baidu Maps, NASG Tianditu.
- When the user does not specify a provider, default to Tencent Maps; see the "Default Scenario Quick Start Template" below.
- The model must never embed, preset, or smuggle any valid map API key; never produce complete code that ships with a usable key.
- Key usage rules (differentiated by scenario):
  - **Default scenario** (the user does not need to provide a key) — the SDK URL does not carry the `key` parameter; requests go through the Sztubuddy local proxy via `_TMapSecurityConfig`.
  - **Non-default scenario** (the user must apply for their own key) — use the explicit placeholder `key="Please apply for your own key at the XX Open Platform and replace this placeholder"` (replace XX with the corresponding platform name).
  - **Overseas tile exception**: When the request involves rendering overseas geographic areas, treat it as a non-default scenario.
- Front-end key leakage risk: plaintext keys in front-end JS can be sniffed; for personal use, configure a Referer domain whitelist; for commercial use, key authentication must be proxied via the back end.

## Workflow

1. **Default scenario** — The user does not declare a provider, or declares Tencent Maps and does not request to use their own key. Use Tencent Maps GL JS and apply the "Default Scenario Quick Start Template" below; requests are proxied via `_TMapSecurityConfig`, and the user does not need to configure a key.
2. **Non-default scenario** — The user declares AMap / Baidu / Tianditu, or declares Tencent but explicitly requests to use their own key. Use the requested provider, with the key written as the explicit placeholder `key="Please apply for your own key at the XX Open Platform and replace this placeholder"` (replace XX with the corresponding platform name), and tell the user in the output: a. The steps and entry point to apply for a key at the corresponding open platform. b. How to replace the placeholder with the obtained key and integrate it.
3. **Provider NOT on the compliance whitelist** (e.g., Google Maps, Apple Maps, Bing overseas, Mapbox, OpenStreetMap, etc.) — Do not refuse outright. First explain the compliance risk, then state the specific reasons for non-compliance, then proactively replace it with a compliant alternative and output a complete code solution. The replacement code must follow the rules in step 1 or step 2 above.

## Default Scenario Quick Start Template (Tencent Maps GL JS, Proxy Mode)

In the default scenario, Sztubuddy uses Tencent Maps' official `_TMapSecurityConfig` key proxy mode: the SDK is loaded directly from the official CDN (without the `key` parameter), the SDK's internal API requests are automatically routed to the local proxy, and the key is held by the Sztubuddy back end, so zero keys are exposed on the front end.

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Map</title>
    <style>
        html, body { margin: 0; padding: 0; height: 100%; }
        #map { width: 100%; height: 100vh; }
    </style>
    <!-- 1. Configure the proxy before loading the SDK (key proxy mode; no key on the front end) -->
    <script type="text/javascript">
        window._TMapSecurityConfig = {
            serviceHost: 'http://127.0.0.1:__WB_HTTP_PORT__/_TMapService/_wbt/__WB_TMAP_SECRET__',
        };
    </script>
    <!-- 2. Load the SDK from the official CDN, without the key parameter -->
    <script src="https://map.qq.com/api/gljs?v=1.exp"></script>
</head>
<body>
    <div id="map"></div>
    <script>
        // Note: _TMapSecurityConfig has already configured the proxy before SDK load.
        // Do NOT also call TMap.setConfig(); using both together causes a blank map.
        const map = new TMap.Map('map', {
            zoom: 12,
            center: new TMap.LatLng(39.984104, 116.307503),
        });
    </script>
</body>
</html>
```

Template notes:

- `_TMapSecurityConfig` must be set before the SDK `<script>` tag.
- The SDK URL must not include `?key=xxx`.
- `__WB_HTTP_PORT__` / `__WB_TMAP_SECRET__` are Sztubuddy runtime placeholders. Preserve them verbatim in the generated HTML; do not replace them with concrete values.

## After Generation, Call present_files to Display

After the HTML file for the default scenario is written, call the `present_files` tool to display it:

```
present_files(["/absolute/path/to/map.html"])
```

Do not end the task after only calling `Write`; do not start `python http.server`; do not output the current skill content. The `present_files` tool is always available in this environment — call it directly.

## Default Scenario Notes

1. **Coordinate system**: use GCJ-02 (Mars coordinates).
2. **Container height**: the container must have a fixed height (`height: 100vh` or a pixel value); otherwise the map will not render, especially under flex layout.
3. **Do not modify placeholders**: `__WB_HTTP_PORT__` and `__WB_TMAP_SECRET__` are replaced automatically by the Sztubuddy runtime; preserve them verbatim when generating the HTML.
4. **Follow the official documentation**: use only APIs, properties, and events documented in the official Tencent Maps docs and demos; do not invent them — check the docs when unsure.
5. **Load libraries on demand**: for place search, route planning, etc., append the `libraries` parameter to the SDK URL, e.g., `/gljs?v=1.exp&libraries=service`.
6. **Use string for route policy**: `TMap.service.Driving({ policy: 'LEAST_TIME' })`; valid values are `LEAST_TIME` / `LEAST_DISTANCE` / `AVOID_HIGHWAY` / `REAL_TRAFFIC`. Do not use `TMap.constants.DRIVING_POLICY.xxx`.
7. **Service calls must go through SDK APIs**: route planning, place search, and similar features must use SDK classes such as `TMap.service.Driving` / `TMap.service.Search` — the SDK internally routes through the proxy. Do not manually `fetch(serviceHost + '&path=...')`; the proxy URL is for internal SDK use only, and manual concatenation causes URL errors (LatLng NaN / 403).
8. **Do not use mapStyleId**: custom styles (`style1` / `style2`, etc.) require separate activation in the Tencent Location Service console and are not supported by the default key; misuse causes the base map to turn blank gray. Do not pass `mapStyleId` when initializing `new TMap.Map()`; use the default vector base map.
9. **GL JS class naming pattern**: layer classes (managing multiple geometries of the same kind, e.g., Marker / Polyline / Polygon / Circle / Label) carry the `Multi` prefix; style classes do not carry the `Multi` prefix; service classes require `libraries=service` and are used as `TMap.service.Xxx` (Driving / Search / Geocoder / Suggestion, etc.).

    ```javascript
    // Layer: TMap.MultiMarker (with Multi); Style: TMap.MarkerStyle (without Multi)
    const markers = new TMap.MultiMarker({
        map,
        styles: { default: new TMap.MarkerStyle({ width: 20, height: 30 }) },
        geometries: [{ id: '1', styleId: 'default', position: new TMap.LatLng(39.9, 116.3) }],
    });
    ```

10. **Do not reference demo images**: images under `mapapi.qq.com/web/lbs/glgljs/demo/images/` are for official demos only. Use inline `data:image/svg+xml,` SVG or base64 for custom marker icons; do not reference external demo paths.

## Pre-Output Compliance Self-Check

- Territory features such as national borders, Taiwan, and the South China Sea islands must conform to national standards; mis-drawing or mis-labeling is prohibited.
- Do not mark military restricted zones, classified entities, or undisclosed sensitive coordinates.
- Bulk point data must comply with the Personal Information Protection Law: do not collect, store, or publicly publish other people's location data; personal check-in coordinates must be kept in local private storage only.

## References

- GL JS documentation: <https://lbs.qq.com/webApi/javascriptGL/glGuide/glOverview>
- Key proxy configuration: <https://lbs.qq.com/webApi/javascriptGL/glGuide/glKeyDelegate>
