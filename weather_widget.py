#!/usr/bin/env python3
# File: weather_widget.py
# Always-on-top weather banner (single row) at the top of the display.
# Uses Open-Meteo (free, no API key) for geocoding + forecasts.

import os
import difflib
import tkinter as tk
import threading
import urllib.request
import urllib.parse
import json
import logging
from datetime import datetime

try:
    from PIL import Image, ImageTk
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False
    logging.warning('WeatherWidget: Pillow not installed — falling back to text icons')

import config

# ── WMO weather interpretation codes → (icon filename, label) ──────────────
# Icons are loaded from icons/weather/<name>.png (Meteocons fill set).
# Text fallbacks are used when PIL is unavailable or the file is missing.
WEATHER_CODE_ICONS = {
    0:  ('clear-day',            'Clear'),
    1:  ('clear-day',            'Mainly Clear'),
    2:  ('partly-cloudy-day',    'Partly Cloudy'),
    3:  ('overcast',             'Overcast'),
    45: ('fog',                  'Fog'),
    48: ('fog',                  'Icy Fog'),
    51: ('drizzle',              'Light Drizzle'),
    53: ('drizzle',              'Drizzle'),
    55: ('drizzle',              'Heavy Drizzle'),
    61: ('rain',                 'Light Rain'),
    63: ('rain',                 'Rain'),
    65: ('rain',                 'Heavy Rain'),
    71: ('snow',                 'Light Snow'),
    73: ('snow',                 'Snow'),
    75: ('snow',                 'Heavy Snow'),
    77: ('snow',                 'Snow Grains'),
    80: ('rain',                 'Showers'),
    81: ('rain',                 'Showers'),
    82: ('thunderstorms-rain',   'Heavy Showers'),
    85: ('snow',                 'Snow Showers'),
    86: ('snow',                 'Heavy Snow Showers'),
    95: ('thunderstorms',        'Thunderstorm'),
    96: ('thunderstorms-rain',   'Thunderstorm'),
    99: ('thunderstorms-rain',   'Thunderstorm'),
}

WEATHER_CODE_TEXT = {
    0:  'Sun',   1:  'Sun',   2:  '~Sun',  3:  'Cld',
    45: 'Fog',   48: 'Fog',
    51: 'Drzl',  53: 'Drzl',  55: 'Drzl',
    61: 'Rain',  63: 'Rain',  65: 'Rain',
    71: 'Snow',  73: 'Snow',  75: 'Snow',  77: 'Snow',
    80: 'Shwr',  81: 'Shwr',  82: 'Shwr',
    85: 'Snow',  86: 'Snow',
    95: 'Thdr',  96: 'Thdr',  99: 'Thdr',
}

_ICONS_DIR = os.path.join(os.path.dirname(__file__), 'icons', 'weather')

def _wx_icon_name(code):
    """Return (icon_filename_stem, label) for a WMO code."""
    return WEATHER_CODE_ICONS.get(code, ('unknown', 'Unknown'))

def _wx_text(code):
    """Short text fallback for a WMO code."""
    return WEATHER_CODE_TEXT.get(code, '?')

def _c_to_f(c):
    return c * 9 / 5 + 32


class WeatherWidget(tk.Frame):
    """
    Horizontal banner pinned to the top of the display.

    Implemented as a plain Frame (not Toplevel) so it works under Wayland/labwc
    where a Toplevel cannot appear above a fullscreen override-redirect window.
    The parent (media_frame) positions it via place() and calls lift() after
    each media transition.

    Single-row layout per location:
      Location  |  [icon] Mon 13  H:72°F L:58°F  |  8a [icon]  10a [icon]  12p [icon] …

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
        self.cfg = getattr(config, 'WEATHER', {})
        super().__init__(root, bg=self.BG)

        self.screen_width  = screen_width
        self.screen_height = screen_height
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

        # ── Icons ────────────────────────────────────────────────────────────
        self._icon_size  = self.cfg.get('icon_size', 24)
        self._icon_cache = {}   # name → ImageTk.PhotoImage (kept to prevent GC)

        # ── Single row frame ────────────────────────────────────────────────
        self._row = tk.Frame(self, bg=self.BG,
                             width=self.screen_width, height=self._banner_h)
        self._row.pack_propagate(False)
        self._row.pack(fill='both', expand=True)

        self._show_loading()
        self._fetch_all()
        self._schedule_refresh()

    # ── Icon loading ────────────────────────────────────────────────────────

    def _load_icon(self, name):
        """Return a cached ImageTk.PhotoImage for *name*, or None on failure.

        If the exact file is missing, tries a fuzzy match against whatever
        PNGs are present in the icons directory before giving up.
        """
        if name in self._icon_cache:
            return self._icon_cache[name]
        if not _PIL_AVAILABLE:
            return None

        path = os.path.join(_ICONS_DIR, f'{name}.png')

        if not os.path.isfile(path):
            # Fuzzy-match against available PNGs
            resolved = self._fuzzy_resolve_icon(name)
            if resolved:
                path = os.path.join(_ICONS_DIR, f'{resolved}.png')
                logging.info(f'WeatherWidget: icon "{name}" → using "{resolved}" (fuzzy match)')
            else:
                logging.warning(f'WeatherWidget: icon "{name}" not found and no close match')
                self._icon_cache[name] = None
                return None

        try:
            img = Image.open(path).convert('RGBA')
            img = img.resize((self._icon_size, self._icon_size), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._icon_cache[name] = photo
            return photo
        except Exception as exc:
            logging.warning(f'WeatherWidget: could not load icon "{name}": {exc}')
            self._icon_cache[name] = None
            return None

    def _fuzzy_resolve_icon(self, name):
        """Return the closest available icon stem for *name*, or None."""
        if not os.path.isdir(_ICONS_DIR):
            return None
        available = [f[:-4] for f in os.listdir(_ICONS_DIR) if f.endswith('.png')]
        if not available:
            return None
        matches = difflib.get_close_matches(name, available, n=1, cutoff=0.4)
        return matches[0] if matches else None

    def _icon_label(self, parent, code, font):
        """Return a Label showing the icon image, or a text fallback."""
        icon_name, _ = _wx_icon_name(code)
        photo = self._load_icon(icon_name)
        if photo:
            return tk.Label(parent, image=photo, bg=self.BG)
        # Fallback: short text in muted colour
        return tk.Label(parent, text=_wx_text(code),
                        bg=self.BG, fg=self.FG, font=font)

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
        # Always fetch in Celsius; display conversion is done client-side
        # so that 'units' and 'forecast_units' can differ independently.
        params = urllib.parse.urlencode({
            'latitude':         coords['lat'],
            'longitude':        coords['lon'],
            'hourly':           'weather_code,temperature_2m',
            'daily':            'weather_code,temperature_2m_max,temperature_2m_min',
            'timezone':         'auto',
            'forecast_days':    8,
            'temperature_unit': 'celsius',
        })
        url = f'https://api.open-meteo.com/v1/forecast?{params}'
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read())

    def _fmt_temp(self, val_c, units_cfg):
        """Format a single Celsius value per units config ('fahrenheit'/'celsius'/'both')."""
        u = units_cfg.lower()
        if 'both' in u:
            return f'{round(_c_to_f(val_c))}°F/{round(val_c)}°C'
        if 'c' in u:
            return f'{round(val_c)}°C'
        return f'{round(_c_to_f(val_c))}°F'

    def _fmt_temp_range(self, low_c, high_c, units_cfg):
        """Format a low–high range compactly, e.g. '58–72°C'."""
        u = units_cfg.lower()
        if 'both' in u:
            return (f'{round(low_c)}–{round(high_c)}°C'
                    f' / {round(_c_to_f(low_c))}–{round(_c_to_f(high_c))}°F')
        if 'c' in u:
            return f'{round(low_c)}–{round(high_c)}°C'
        return f'{round(_c_to_f(low_c))}–{round(_c_to_f(high_c))}°F'

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

        self.lift()

    def _build_location(self, display_name, weather):
        daily  = weather.get('daily', {})
        hourly = weather.get('hourly', {})

        units          = self.cfg.get('units', 'fahrenheit')
        forecast_units = self.cfg.get('forecast_units', units)  # falls back to units if unset

        today_str  = daily['time'][0]
        today_dt   = datetime.strptime(today_str, '%Y-%m-%d')
        today_code = daily['weather_code'][0]
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
        self._icon_label(self._row, today_code, self.f_main).pack(
            side='left', padx=(4, 2))
        tk.Label(
            self._row,
            text=today_dt.strftime('%a %-d'),
            bg=self.BG, fg=self.FG, font=self.f_main,
        ).pack(side='left', padx=(0, 2))

        tk.Label(
            self._row,
            text=f"H:{self._fmt_temp(today_high, units)}  L:{self._fmt_temp(today_low, units)}",
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
                idx       = h_times.index(target)
                hour_code = h_codes[idx]
            except (ValueError, IndexError):
                hour_code = None

            cell = tk.Frame(self._row, bg=self.BG)
            cell.pack(side='left', padx=3)
            tk.Label(cell, text=lbl, bg=self.BG, fg=self.FG_DIM, font=self.f_tiny).pack()
            if hour_code is not None:
                self._icon_label(cell, hour_code, self.f_main).pack()
            else:
                tk.Label(cell, text='–', bg=self.BG, fg=self.FG_DIM, font=self.f_main).pack()

        # Next 7 days — pack as many as fit; the banner clips anything beyond the edge
        for i in range(1, 8):
            if i >= len(daily.get('time', [])):
                break
            d_str  = daily['time'][i]
            d_dt   = datetime.strptime(d_str, '%Y-%m-%d')
            d_code = daily['weather_code'][i]
            d_high = daily['temperature_2m_max'][i]
            d_low  = daily['temperature_2m_min'][i]

            tk.Frame(self._row, bg=self.SEP_CLR, width=1).pack(
                side='left', fill='y', padx=4, pady=4
            )
            cell = tk.Frame(self._row, bg=self.BG)
            cell.pack(side='left', padx=3)
            top = tk.Frame(cell, bg=self.BG)
            top.pack()
            self._icon_label(top, d_code, self.f_tiny).pack(side='left')
            tk.Label(top,
                     text=f" {d_dt.strftime('%a %-d')}",
                     bg=self.BG, fg=self.FG, font=self.f_tiny).pack(side='left')
            tk.Label(cell,
                     text=self._fmt_temp_range(d_low, d_high, forecast_units),
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
