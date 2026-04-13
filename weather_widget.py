#!/usr/bin/env python3
# File: weather_widget.py
# Always-on-top weather banner (single row) at the top of the display.
# Uses Open-Meteo (free, no API key) for geocoding + forecasts.

import tkinter as tk
import threading
import urllib.request
import urllib.parse
import json
import logging
from datetime import datetime

import config

# ── WMO weather interpretation codes → (emoji, label) ──────────────────────
WEATHER_CODES = {
    0:  ('☀️',  'Clear'),
    1:  ('🌤️', 'Mainly Clear'),
    2:  ('⛅',  'Partly Cloudy'),
    3:  ('☁️',  'Overcast'),
    45: ('🌫️', 'Fog'),
    48: ('🌫️', 'Icy Fog'),
    51: ('🌦️', 'Light Drizzle'),
    53: ('🌦️', 'Drizzle'),
    55: ('🌧️', 'Heavy Drizzle'),
    61: ('🌧️', 'Light Rain'),
    63: ('🌧️', 'Rain'),
    65: ('🌧️', 'Heavy Rain'),
    71: ('❄️',  'Light Snow'),
    73: ('❄️',  'Snow'),
    75: ('❄️',  'Heavy Snow'),
    77: ('❄️',  'Snow Grains'),
    80: ('🌧️', 'Showers'),
    81: ('🌧️', 'Showers'),
    82: ('⛈️',  'Heavy Showers'),
    85: ('❄️',  'Snow Showers'),
    86: ('❄️',  'Heavy Snow Showers'),
    95: ('⛈️',  'Thunderstorm'),
    96: ('⛈️',  'Thunderstorm'),
    99: ('⛈️',  'Thunderstorm'),
}

def _wx_emoji(code):
    return WEATHER_CODES.get(code, ('❓', 'Unknown'))

def _c_to_f(c):
    return c * 9 / 5 + 32


class WeatherWidget(tk.Toplevel):
    """
    Horizontal banner pinned to the top of the display.

    Single-row layout per location:
      📍 Location  |  ☀️ Today Mon 13  H:72°F L:58°F  |  8a ☀️  10a ⛅  12p ⛅ …

    Multiple locations are placed side-by-side separated by a divider.
    Font size is controlled by the 'scale' config key (default 1.0).
    """

    # ── Palette ────────────────────────────────────────────────────────────
    BG      = '#0d1117'   # near-black background
    FG      = '#e6edf3'   # primary text
    FG_DIM  = '#8b949e'   # secondary / muted text
    FG_LOC  = '#79c0ff'   # location header blue
    SEP_CLR = '#30363d'   # vertical separator

    # ── Hours shown for today's hourly forecast ─────────────────────────────
    TODAY_HOURS = [8, 10, 12, 14, 16, 18, 20]
    TODAY_LBLS  = ['8a', '10a', '12p', '2p', '4p', '6p', '8p']

    def __init__(self, root, screen_width, screen_height):
        super().__init__(root)
        self.screen_width  = screen_width
        self.screen_height = screen_height
        self.cfg = getattr(config, 'WEATHER', {})

        self.MARGIN = int(screen_width * self.cfg.get('margin_pct', 0.5) / 100)
        self._results = []   # [(loc_name, coords_dict, weather_dict), …]

        # ── Scale ───────────────────────────────────────────────────────────
        scale = self.cfg.get('scale', 1.0)
        def _fs(base): return max(1, round(base * scale))
        self.f_loc   = ('DejaVu Sans', _fs(12), 'bold')
        self.f_main  = ('DejaVu Sans', _fs(11))
        self.f_small = ('DejaVu Sans', _fs(10))
        self.f_tiny  = ('DejaVu Sans', _fs(9))
        # Banner height: two stacked labels (f_tiny + f_main) + padding
        # Use point-to-pixel ratio ~1.33 as a safe approximation
        self._banner_h = round((_fs(9) + _fs(11)) * 1.33) + 16

        # ── Window chrome ───────────────────────────────────────────────────
        self.overrideredirect(True)
        self.configure(bg=self.BG)
        self.attributes('-topmost', True)
        try:
            self.attributes('-alpha', 0.88)
        except Exception:
            pass

        # ── Single row frame ────────────────────────────────────────────────
        self._row = tk.Frame(self, bg=self.BG)
        self._row.pack(fill='both', expand=True, padx=4, pady=4)

        self._show_loading()
        self._position()
        self._fetch_all()
        self._schedule_refresh()

    # ── Positioning ─────────────────────────────────────────────────────────

    def _position(self):
        self.geometry(f'{self.screen_width}x{self._banner_h}+0+{self.MARGIN}')

    # ── Loading placeholder ─────────────────────────────────────────────────

    def _show_loading(self):
        tk.Label(
            self._row, text='  Loading weather…',
            bg=self.BG, fg=self.FG_DIM, font=self.f_small,
        ).pack(side='left', padx=8)

    # ── Data fetching (background thread) ───────────────────────────────────

    def _fetch_all(self):
        def worker():
            locations = self.cfg.get('locations', [])
            results = []
            for loc in locations:
                try:
                    coords  = self._geocode(loc)
                    weather = self._fetch_weather(coords) if coords else None
                    results.append((loc, coords, weather))
                except Exception as exc:
                    logging.error(f'WeatherWidget: error fetching "{loc}": {exc}')
                    results.append((loc, None, None))
            self.after(0, lambda: self._on_data(results))

        threading.Thread(target=worker, daemon=True).start()

    def _geocode(self, name):
        city = name.split(',')[0].strip()
        url = (
            'https://geocoding-api.open-meteo.com/v1/search'
            f'?name={urllib.parse.quote(city)}&count=1&language=en&format=json'
        )
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        res = data.get('results', [])
        if not res:
            logging.warning(f'WeatherWidget: could not geocode "{name}"')
            return None
        return {
            'lat':  res[0]['latitude'],
            'lon':  res[0]['longitude'],
            'name': name,
        }

    def _fetch_weather(self, coords):
        units_cfg = self.cfg.get('units', 'fahrenheit').lower()
        show_both = 'both' in units_cfg
        temp_unit = 'celsius' if (show_both or 'c' in units_cfg) else 'fahrenheit'
        params = urllib.parse.urlencode({
            'latitude':         coords['lat'],
            'longitude':        coords['lon'],
            'hourly':           'weather_code,temperature_2m',
            'daily':            'weather_code,temperature_2m_max,temperature_2m_min',
            'timezone':         'auto',
            'forecast_days':    8,
            'temperature_unit': temp_unit,
        })
        url = f'https://api.open-meteo.com/v1/forecast?{params}'
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        data['_show_both'] = show_both
        data['_unit']      = '°C' if temp_unit == 'celsius' else '°F'
        return data

    def _fmt_temp(self, val, weather):
        if weather.get('_show_both'):
            return f'{round(_c_to_f(val))}°F/{round(val)}°C'
        return f'{round(val)}{weather.get("_unit", "°F")}'

    # ── Display update (main thread) ─────────────────────────────────────────

    def _on_data(self, results):
        self._results = results
        self._rebuild()

    def _rebuild(self):
        for w in self._row.winfo_children():
            w.destroy()

        first = True
        for loc_name, coords, weather in self._results:
            if not first:
                tk.Frame(self._row, bg=self.SEP_CLR, width=1).pack(
                    side='left', fill='y', padx=6, pady=4
                )
            first = False
            if weather:
                self._build_location(coords.get('name', loc_name) if coords else loc_name, weather)
            else:
                tk.Label(
                    self._row, text=f'{loc_name}: unavailable',
                    bg=self.BG, fg=self.FG_DIM, font=self.f_small,
                ).pack(side='left', padx=8)

        self._position()
        self.attributes('-topmost', True)

    def _build_location(self, display_name, weather):
        daily  = weather.get('daily', {})
        hourly = weather.get('hourly', {})

        today_str  = daily['time'][0]
        today_dt   = datetime.strptime(today_str, '%Y-%m-%d')
        today_icon, _ = _wx_emoji(daily['weather_code'][0])
        today_high = daily['temperature_2m_max'][0]
        today_low  = daily['temperature_2m_min'][0]

        # Location name
        tk.Label(
            self._row, text=display_name,
            bg=self.BG, fg=self.FG_LOC, font=self.f_loc,
        ).pack(side='left', padx=(8, 4))

        # Thin separator
        tk.Frame(self._row, bg=self.SEP_CLR, width=1).pack(
            side='left', fill='y', padx=4, pady=4
        )

        # Today icon + date + H/L
        tk.Label(
            self._row,
            text=f"{today_icon} {today_dt.strftime('%a %-d')}",
            bg=self.BG, fg=self.FG, font=self.f_main,
        ).pack(side='left', padx=(4, 2))

        tk.Label(
            self._row,
            text=f"H:{self._fmt_temp(today_high, weather)}  L:{self._fmt_temp(today_low, weather)}",
            bg=self.BG, fg=self.FG_DIM, font=self.f_small,
        ).pack(side='left', padx=(2, 8))

        # Thin separator before hourly
        tk.Frame(self._row, bg=self.SEP_CLR, width=1).pack(
            side='left', fill='y', padx=4, pady=4
        )

        # Hourly forecast cells
        h_times = hourly.get('time', [])
        h_codes = hourly.get('weather_code', [])

        for hour, lbl in zip(self.TODAY_HOURS, self.TODAY_LBLS):
            target = f'{today_str}T{hour:02d}:00'
            try:
                idx = h_times.index(target)
                icon, _ = _wx_emoji(h_codes[idx])
            except (ValueError, IndexError):
                icon = '–'

            cell = tk.Frame(self._row, bg=self.BG)
            cell.pack(side='left', padx=3)
            tk.Label(cell, text=lbl,  bg=self.BG, fg=self.FG_DIM, font=self.f_tiny).pack()
            tk.Label(cell, text=icon, bg=self.BG, fg=self.FG,      font=self.f_main).pack()

        # Next 7 days — pack as many as fit; the banner clips anything beyond the edge
        for i in range(1, 8):
            if i >= len(daily.get('time', [])):
                break
            d_str  = daily['time'][i]
            d_dt   = datetime.strptime(d_str, '%Y-%m-%d')
            d_icon, _ = _wx_emoji(daily['weather_code'][i])
            d_high = daily['temperature_2m_max'][i]
            d_low  = daily['temperature_2m_min'][i]

            tk.Frame(self._row, bg=self.SEP_CLR, width=1).pack(
                side='left', fill='y', padx=4, pady=4
            )
            cell = tk.Frame(self._row, bg=self.BG)
            cell.pack(side='left', padx=3)
            tk.Label(cell,
                     text=f"{d_icon} {d_dt.strftime('%a %-d')}",
                     bg=self.BG, fg=self.FG, font=self.f_tiny).pack()
            tk.Label(cell,
                     text=f"H:{self._fmt_temp(d_high, weather)}  L:{self._fmt_temp(d_low, weather)}",
                     bg=self.BG, fg=self.FG_DIM, font=self.f_tiny).pack()

    # ── Periodic refresh ────────────────────────────────────────────────────

    def _schedule_refresh(self):
        interval_ms = self.cfg.get('update_interval_minutes', 30) * 60 * 1000
        self.after(interval_ms, self._do_refresh)

    def _do_refresh(self):
        self._fetch_all()
        self._schedule_refresh()

    # ── Public ──────────────────────────────────────────────────────────────

    def bring_to_front(self):
        self.lift()
        self.attributes('-topmost', True)
