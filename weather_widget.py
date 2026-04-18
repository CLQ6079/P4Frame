#!/usr/bin/env python3
# File: weather_widget.py
# Always-on-top weather banner (single row) at the top of the display.
# Uses Open-Meteo (free, no API key) for geocoding + forecasts.

import os
import difflib
import tkinter as tk
import tkinter.font as tkfont
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
        # tkfont.Font objects serve dual purpose: canvas rendering + text measurement
        self.f_loc   = tkfont.Font(family='DejaVu Sans', size=_fs(12), weight='bold')
        self.f_main  = tkfont.Font(family='DejaVu Sans', size=_fs(11))
        self.f_small = tkfont.Font(family='DejaVu Sans', size=_fs(10))
        self.f_tiny  = tkfont.Font(family='DejaVu Sans', size=_fs(9))
        self._banner_h = self.f_tiny.metrics('linespace') + self.f_main.metrics('linespace') + 16

        # ── Icons ────────────────────────────────────────────────────────────
        self._icon_size   = self.cfg.get('icon_size', 24)
        self._pil_cache   = {}     # name → PIL Image (background-loaded)
        self._icon_cache  = {}     # name → ImageTk.PhotoImage (main-thread, GC anchor)
        self._icons_ready = False
        if _PIL_AVAILABLE:
            threading.Thread(target=self._preload_icons, daemon=True).start()

        # ── Canvas — single widget replaces all child Labels/Frames ─────────
        # One canvas repaint = one XWayland call; avoids progressive rendering
        # on every lift() after a photo change.
        self._canvas = tk.Canvas(self, bg=self.BG, highlightthickness=0,
                                 width=self.screen_width, height=self._banner_h)
        self._canvas.pack(fill='both', expand=True)

        self._show_loading()
        self._fetch_all()
        self._schedule_refresh()

    # ── Icon loading ────────────────────────────────────────────────────────

    def _preload_icons(self):
        """Background thread: open + resize every needed icon into _pil_cache.

        Fuzzy matching is done here so the main thread never touches the disk.
        """
        if not os.path.isdir(_ICONS_DIR):
            logging.warning(f'WeatherWidget: icons directory not found: {_ICONS_DIR}')
            self._icons_ready = True
            return

        available = {f[:-4]: f for f in os.listdir(_ICONS_DIR) if f.endswith('.png')}
        wanted    = {stem for stem, _ in WEATHER_CODE_ICONS.values()}

        for name in wanted:
            if name in available:
                resolved = name
            else:
                matches = difflib.get_close_matches(name, available, n=1, cutoff=0.4)
                if not matches:
                    logging.warning(f'WeatherWidget: no icon found for "{name}"')
                    self._pil_cache[name] = None
                    continue
                resolved = matches[0]
                logging.info(f'WeatherWidget: icon "{name}" → "{resolved}" (fuzzy)')

            try:
                path = os.path.join(_ICONS_DIR, available[resolved])
                img  = Image.open(path).convert('RGBA').resize(
                    (self._icon_size, self._icon_size), Image.LANCZOS)
                self._pil_cache[name]     = img
                self._pil_cache[resolved] = img   # alias so both keys hit
            except Exception as exc:
                logging.warning(f'WeatherWidget: failed to load icon "{name}": {exc}')
                self._pil_cache[name] = None

        self._icons_ready = True
        logging.info(f'WeatherWidget: preloaded {sum(v is not None for v in self._pil_cache.values())} icons')

    def _load_icon(self, name):
        """Return an ImageTk.PhotoImage for *name*, converting from _pil_cache.

        PIL work is already done off-thread; this only does the fast Tk conversion.
        Falls back to None (text label) if icons aren't ready yet or file was missing.
        """
        if name in self._icon_cache:
            return self._icon_cache[name]
        if not self._icons_ready:
            return None   # preload still running — text fallback until next rebuild

        pil_img = self._pil_cache.get(name)
        if pil_img is None:
            self._icon_cache[name] = None
            return None

        photo = ImageTk.PhotoImage(pil_img)
        self._icon_cache[name] = photo
        return photo

    def _draw_icon(self, x, y, code):
        """Draw icon (or text fallback) at canvas (x, y) anchor=nw. Returns x + icon_size."""
        icon_name, _ = _wx_icon_name(code)
        photo = self._load_icon(icon_name)
        if photo:
            self._canvas.create_image(x, y, image=photo, anchor='nw')
        else:
            s = self._icon_size
            self._canvas.create_text(x + s//2, y + s//2,
                                     text=_wx_text(code),
                                     fill=self.FG, font=self.f_tiny, anchor='center')
        return x + self._icon_size

    # ── Loading placeholder ─────────────────────────────────────────────────

    def _show_loading(self):
        self._canvas.create_text(8, self._banner_h // 2,
                                 text='Loading weather…',
                                 fill=self.FG_DIM, font=self.f_small, anchor='w')

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
        self._canvas.delete('all')

        x     = 0
        first = True
        for loc_name, coords, weather in self._results:
            if not first:
                x += 6
                self._canvas.create_rectangle(x, 4, x+1, self._banner_h-4,
                                              fill=self.SEP_CLR, outline='')
                x += 7
            first = False
            display_name = coords.get('name', loc_name) if coords else loc_name
            if weather:
                x = self._draw_location(x, display_name, weather)
            else:
                self._canvas.create_text(x+8, self._banner_h//2,
                                         text=f'{display_name}: unavailable',
                                         fill=self.FG_DIM, font=self.f_small, anchor='w')

        self.lift()

    def _sep(self, x):
        """Draw a vertical separator at x and return x advanced past it."""
        self._canvas.create_rectangle(x+4, 4, x+5, self._banner_h-4,
                                      fill=self.SEP_CLR, outline='')
        return x + 9

    def _draw_location(self, x, display_name, weather):
        """Draw one location block onto the canvas starting at x. Returns new x."""
        cv  = self._canvas
        cy  = self._banner_h // 2
        daily  = weather.get('daily', {})
        hourly = weather.get('hourly', {})

        units          = self.cfg.get('units', 'fahrenheit')
        forecast_units = self.cfg.get('forecast_units', units)

        today_str  = daily['time'][0]
        today_dt   = datetime.strptime(today_str, '%Y-%m-%d')
        today_code = daily['weather_code'][0]
        today_high = daily['temperature_2m_max'][0]
        today_low  = daily['temperature_2m_min'][0]

        # ── Location name ──────────────────────────────────────────────────
        x += 8
        cv.create_text(x, cy, text=display_name,
                       fill=self.FG_LOC, font=self.f_loc, anchor='w')
        x += self.f_loc.measure(display_name) + 4
        x  = self._sep(x)

        # ── Today: icon + date + H/L ───────────────────────────────────────
        x += 4
        x  = self._draw_icon(x, cy - self._icon_size//2, today_code)
        x += 2

        date_str = today_dt.strftime('%a %-d')
        cv.create_text(x, cy, text=date_str, fill=self.FG, font=self.f_main, anchor='w')
        x += self.f_main.measure(date_str) + 8

        hl = f"H:{self._fmt_temp(today_high, units)}  L:{self._fmt_temp(today_low, units)}"
        cv.create_text(x, cy, text=hl, fill=self.FG_DIM, font=self.f_small, anchor='w')
        x += self.f_small.measure(hl) + 8
        x  = self._sep(x)

        # ── Hourly cells ───────────────────────────────────────────────────
        lbl_h  = self.f_tiny.metrics('linespace')
        cell_h = lbl_h + 2 + self._icon_size
        top_y  = cy - cell_h // 2

        h_times = hourly.get('time', [])
        h_codes = hourly.get('weather_code', [])

        for hour, lbl in zip(self.TODAY_HOURS, self.TODAY_LBLS):
            target = f'{today_str}T{hour:02d}:00'
            try:
                idx       = h_times.index(target)
                hour_code = h_codes[idx]
            except (ValueError, IndexError):
                hour_code = None

            x      += 3
            lbl_w   = self.f_tiny.measure(lbl)
            cell_w  = max(self._icon_size, lbl_w)

            cv.create_text(x + (cell_w - lbl_w)//2, top_y,
                           text=lbl, fill=self.FG_DIM, font=self.f_tiny, anchor='nw')

            icon_x = x + (cell_w - self._icon_size)//2
            icon_y = top_y + lbl_h + 2
            if hour_code is not None:
                self._draw_icon(icon_x, icon_y, hour_code)
            else:
                cv.create_text(icon_x + self._icon_size//2, icon_y + self._icon_size//2,
                               text='–', fill=self.FG_DIM, font=self.f_main, anchor='center')
            x += cell_w + 3

        # ── 7-day forecast ─────────────────────────────────────────────────
        tiny_lh = self.f_tiny.metrics('linespace')
        row1_h  = max(self._icon_size, tiny_lh)
        fc_top  = cy - (row1_h + 2 + tiny_lh) // 2

        for i in range(1, 8):
            if i >= len(daily.get('time', [])) or x >= self.screen_width:
                break
            d_str     = daily['time'][i]
            d_dt      = datetime.strptime(d_str, '%Y-%m-%d')
            d_code    = daily['weather_code'][i]
            d_high    = daily['temperature_2m_max'][i]
            d_low     = daily['temperature_2m_min'][i]
            day_str   = d_dt.strftime('%a %-d')
            range_str = self._fmt_temp_range(d_low, d_high, forecast_units)

            row1_w = self._icon_size + 3 + self.f_tiny.measure(day_str)
            cell_w = max(row1_w, self.f_tiny.measure(range_str))

            x = self._sep(x)

            # Row 1: icon + day name side by side
            icon_top = fc_top + (row1_h - self._icon_size)//2
            self._draw_icon(x, icon_top, d_code)
            text_top = fc_top + (row1_h - tiny_lh)//2
            cv.create_text(x + self._icon_size + 3, text_top,
                           text=day_str, fill=self.FG, font=self.f_tiny, anchor='nw')

            # Row 2: temp range
            cv.create_text(x, fc_top + row1_h + 2,
                           text=range_str, fill=self.FG_DIM, font=self.f_tiny, anchor='nw')

            x += cell_w + 3

        return x

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
