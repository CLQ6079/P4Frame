#!/usr/bin/env python3
# File: weather_widget.py
# Always-on-top weather overlay for P4Frame.
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
    Floating weather overlay positioned at the top-right corner of the display.

    Implemented as a Toplevel window (not a child widget) so it remains visible
    above VLC's X11-embedded video surface.  overrideredirect removes the title
    bar; -topmost keeps it above all other windows.

    Per-location layout
    ─────────────────────────────────
      Location Name
      Today · Mon 12        H:82°F L:65°F
      8a  10a  12p  2p  4p  6p  8p
      ☀️   ☀️   ⛅   ⛅   🌦️  🌧️  🌧️

      ☀️ Tue 13              H:79° L:62°
      ⛅ Wed 14              H:75° L:60°
      … (7 more days)
    ─────────────────────────────────
    """

    # ── Palette ────────────────────────────────────────────────────────────
    BG      = '#0d1117'   # near-black background
    FG      = '#e6edf3'   # primary text
    FG_DIM  = '#8b949e'   # secondary / muted text
    FG_LOC  = '#79c0ff'   # location header blue
    SEP_CLR = '#30363d'   # separator line

    # ── Hours shown for today's hourly forecast ─────────────────────────────
    TODAY_HOURS = [8, 10, 12, 14, 16, 18, 20]
    TODAY_LBLS  = ['8a', '10a', '12p', '2p', '4p', '6p', '8p']

    def __init__(self, root, screen_width, screen_height):
        super().__init__(root)
        self.screen_width  = screen_width
        self.screen_height = screen_height
        self.cfg = getattr(config, 'WEATHER', {})

        # Derive pixel dimensions from screen size + config percentages
        self.WIDGET_W = int(screen_width * self.cfg.get('widget_width_pct', 12.5) / 100)
        self.MARGIN   = int(screen_width * self.cfg.get('margin_pct', 0.5)        / 100)
        self._results = []   # [(loc_name, coords_dict, weather_dict), …]

        # ── Window chrome ───────────────────────────────────────────────────
        self.overrideredirect(True)           # no title bar / decorations
        self.configure(bg=self.BG)
        self.attributes('-topmost', True)
        try:
            self.attributes('-alpha', 0.88)   # slight transparency (compositor required)
        except Exception:
            pass

        # ── Fonts ───────────────────────────────────────────────────────────
        self.f_loc   = ('DejaVu Sans', 10, 'bold')
        self.f_main  = ('DejaVu Sans', 9)
        self.f_small = ('DejaVu Sans', 8)
        self.f_tiny  = ('DejaVu Sans', 7)

        # ── Scrollable inner frame ──────────────────────────────────────────
        self._canvas = tk.Canvas(self, bg=self.BG, highlightthickness=0,
                                 width=self.WIDGET_W)
        self._canvas.pack(fill='both', expand=True)
        self._inner = tk.Frame(self._canvas, bg=self.BG)
        self._win_id = self._canvas.create_window(
            (0, 0), window=self._inner, anchor='nw', width=self.WIDGET_W
        )
        self._canvas.bind('<MouseWheel>', self._on_scroll)
        self._canvas.bind('<Button-4>',   lambda e: self._canvas.yview_scroll(-1, 'units'))
        self._canvas.bind('<Button-5>',   lambda e: self._canvas.yview_scroll( 1, 'units'))

        self._show_loading()
        self._position()
        self._fetch_all()
        self._schedule_refresh()

    # ── Positioning ─────────────────────────────────────────────────────────

    def _position(self):
        x = self.screen_width - self.WIDGET_W - self.MARGIN
        y = self.MARGIN
        self.geometry(f'+{x}+{y}')

    def _resize_to_content(self):
        """Resize canvas height to fit inner content (capped at screen height)."""
        self.update_idletasks()
        content_h = self._inner.winfo_reqheight()
        display_h = min(content_h, self.screen_height - self.MARGIN * 2)
        self._canvas.configure(height=display_h)
        self._canvas.configure(scrollregion=(0, 0, self.WIDGET_W, content_h))
        self._position()

    def _on_scroll(self, event):
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')

    # ── Loading placeholder ─────────────────────────────────────────────────

    def _show_loading(self):
        tk.Label(
            self._inner, text='  Loading weather…',
            bg=self.BG, fg=self.FG_DIM, font=self.f_small,
            anchor='w', width=30,
        ).pack(fill='x', pady=6)
        self._resize_to_content()

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
        # Open-Meteo geocoding only accepts a plain city name.
        # Strip ", State" / ", Country" suffix before querying.
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
            # Use the full configured name for display (e.g. "Mountlake Terrace, WA")
            'name': name,
        }

    def _fetch_weather(self, coords):
        units_cfg = self.cfg.get('units', 'fahrenheit').lower()
        # For "both", fetch Celsius and convert to F ourselves
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
        # Tag with display mode so _build_location knows how to format
        data['_show_both'] = show_both
        data['_unit']      = '°C' if temp_unit == 'celsius' else '°F'
        return data

    def _fmt_temp(self, val, weather):
        """Format a temperature value for display based on units mode."""
        if weather.get('_show_both'):
            f = round(_c_to_f(val))
            c = round(val)
            return f'{f}°F/{c}°C'
        unit = weather.get('_unit', '°F')
        return f'{round(val)}{unit}'

    def _fmt_temp_hl(self, high, low, weather):
        """Format high/low pair, e.g. 'H:72°F/22°C  L:58°F/14°C'"""
        return f'H:{self._fmt_temp(high, weather)}  L:{self._fmt_temp(low, weather)}'

    # ── Display update (main thread) ─────────────────────────────────────────

    def _on_data(self, results):
        self._results = results
        self._rebuild()

    def _rebuild(self):
        for w in self._inner.winfo_children():
            w.destroy()

        first = True
        for loc_name, coords, weather in self._results:
            if not first:
                tk.Frame(self._inner, bg=self.SEP_CLR, height=1).pack(
                    fill='x', padx=8, pady=3
                )
            first = False
            if weather:
                self._build_location(loc_name, coords, weather)
            else:
                tk.Label(
                    self._inner,
                    text=f'  {loc_name}: unavailable',
                    bg=self.BG, fg=self.FG_DIM, font=self.f_small, anchor='w',
                ).pack(fill='x', padx=8, pady=4)

        self._resize_to_content()
        self.attributes('-topmost', True)  # re-assert after rebuild

    def _build_location(self, loc_name, coords, weather):
        daily  = weather.get('daily', {})
        hourly = weather.get('hourly', {})

        display_name = coords.get('name', loc_name) if coords else loc_name

        # ── Location header ─────────────────────────────────────────────────
        tk.Label(
            self._inner, text=f'  {display_name}',
            bg=self.BG, fg=self.FG_LOC, font=self.f_loc,
            anchor='w',
        ).pack(fill='x', pady=(5, 0))

        # ── Today ───────────────────────────────────────────────────────────
        today_str  = daily['time'][0]
        today_dt   = datetime.strptime(today_str, '%Y-%m-%d')
        today_high = daily['temperature_2m_max'][0]
        today_low  = daily['temperature_2m_min'][0]

        row = tk.Frame(self._inner, bg=self.BG)
        row.pack(fill='x', padx=8)
        tk.Label(row, text=f"Today · {today_dt.strftime('%a %-d')}",
                 bg=self.BG, fg=self.FG, font=self.f_main,
                 anchor='w').pack(side='left')
        tk.Label(row, text=self._fmt_temp_hl(today_high, today_low, weather),
                 bg=self.BG, fg=self.FG_DIM, font=self.f_small,
                 anchor='e').pack(side='right')

        # ── Today hourly 8 am – 8 pm ────────────────────────────────────────
        h_times = hourly.get('time', [])
        h_codes = hourly.get('weather_code', [])

        hrly = tk.Frame(self._inner, bg=self.BG)
        hrly.pack(fill='x', padx=8, pady=(1, 5))

        for hour, lbl in zip(self.TODAY_HOURS, self.TODAY_LBLS):
            target = f'{today_str}T{hour:02d}:00'
            try:
                idx  = h_times.index(target)
                icon, _ = _wx_emoji(h_codes[idx])
            except (ValueError, IndexError):
                icon = '–'
            cell = tk.Frame(hrly, bg=self.BG)
            cell.pack(side='left', padx=1)
            tk.Label(cell, text=lbl, bg=self.BG, fg=self.FG_DIM,
                     font=self.f_tiny, anchor='center').pack()
            tk.Label(cell, text=icon, bg=self.BG, fg=self.FG,
                     font=self.f_main, anchor='center').pack()

        # ── Next 7 days ─────────────────────────────────────────────────────
        for i in range(1, 8):
            if i >= len(daily.get('time', [])):
                break
            d_str  = daily['time'][i]
            d_dt   = datetime.strptime(d_str, '%Y-%m-%d')
            d_icon, _ = _wx_emoji(daily['weather_code'][i])
            d_high = daily['temperature_2m_max'][i]
            d_low  = daily['temperature_2m_min'][i]

            row = tk.Frame(self._inner, bg=self.BG)
            row.pack(fill='x', padx=8)
            tk.Label(row,
                     text=f"{d_icon} {d_dt.strftime('%a %-d')}",
                     bg=self.BG, fg=self.FG, font=self.f_small,
                     anchor='w', width=9).pack(side='left')
            tk.Label(row,
                     text=self._fmt_temp_hl(d_high, d_low, weather),
                     bg=self.BG, fg=self.FG_DIM, font=self.f_small,
                     anchor='e').pack(side='right')

        # Small bottom padding after last day row
        tk.Frame(self._inner, bg=self.BG, height=4).pack()

    # ── Periodic refresh ────────────────────────────────────────────────────

    def _schedule_refresh(self):
        interval_ms = self.cfg.get('update_interval_minutes', 30) * 60 * 1000
        self.after(interval_ms, self._do_refresh)

    def _do_refresh(self):
        self._fetch_all()
        self._schedule_refresh()

    # ── Public ──────────────────────────────────────────────────────────────

    def bring_to_front(self):
        """Call this whenever the main display transitions to keep widget on top."""
        self.lift()
        self.attributes('-topmost', True)
