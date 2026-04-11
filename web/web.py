#!/usr/bin/env python3
# File: web/web.py
# Minimal web server to view and edit P4Frame configuration.
# Writes changes to p4frame.conf (auto-loaded by config.py) and restarts media_frame.py.

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import re
import signal
import subprocess
import argparse
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

import config as cfg

DEFAULT_PORT = 8080

# Sections to expose, in display order. Tuple/list fields are skipped automatically.
SECTIONS = [
    'MEDIA', 'DISPLAY', 'SLIDESHOW', 'VIDEO_PLAYER',
    'VIDEO_CONVERSION', 'LOGGING', 'SYSTEM', 'DEBUG', 'MEMORY_MANAGEMENT',
]

# Fields to hide from the UI (internal implementation details)
HIDDEN_FIELDS = {
    'supported_image_formats', 'supported_video_formats',
    'converted_subfolder', 'tmp_extension', 'virtual_display',
    'user', 'group', 'working_directory',
}


def parse_config_comments():
    """Parse inline # comments from config.py, returns {section: {key: comment}}."""
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.py')
    comments = {}
    current_section = None
    section_re = re.compile(r'^([A-Z_]+)\s*=\s*\{')
    field_re = re.compile(r"""['"](\w+)['"]\s*:.*?#\s*(.+)$""")
    try:
        with open(config_path) as f:
            for line in f:
                m = section_re.match(line)
                if m:
                    current_section = m.group(1)
                    comments.setdefault(current_section, {})
                    continue
                if current_section:
                    m = field_re.search(line)
                    if m:
                        comments[current_section][m.group(1)] = m.group(2).strip()
    except OSError:
        pass
    return comments

CONFIG_COMMENTS = parse_config_comments()


def get_current_config():
    """Return editable config as a flat dict: {section: {key: value}}."""
    result = {}
    for section in SECTIONS:
        raw = getattr(cfg, section, None)
        if not isinstance(raw, dict):
            continue
        fields = {}
        for k, v in raw.items():
            if k in HIDDEN_FIELDS:
                continue
            if isinstance(v, (bool, int, float, str)):
                fields[k] = v
        if fields:
            result[section] = fields
    return result


def load_conf_file(path):
    """Load existing overrides from the conf file."""
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_conf_file(path, data):
    """Save overrides to the conf file."""
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def find_media_frame_pid():
    """Find running media_frame.py PID."""
    try:
        out = subprocess.check_output(['pgrep', '-f', 'media_frame.py'], text=True)
        pids = [int(p) for p in out.strip().split() if p.strip().isdigit()]
        return pids[0] if pids else None
    except subprocess.CalledProcessError:
        return None


def restart_media_frame(conf_path):
    """Restart media_frame.py if it is currently running."""
    pid = find_media_frame_pid()
    if not pid:
        logging.info("media_frame.py is not running, skipping restart")
        return

    try:
        os.kill(pid, signal.SIGTERM)
        logging.info(f"Sent SIGTERM to media_frame.py (PID {pid})")
    except ProcessLookupError:
        pass

    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = os.environ.copy()
    if 'DISPLAY' not in env:
        env['DISPLAY'] = ':0.0'

    cmd = [sys.executable, os.path.join(script_dir, 'media_frame.py'),
           '--config', conf_path]
    proc = subprocess.Popen(cmd, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)
    logging.info(f"Started media_frame.py (PID {proc.pid}): {' '.join(cmd)}")


def render_field(section, key, value):
    """Render a single form field with optional comment hint from config.py."""
    name = f"{section}.{key}"
    label = key.replace('_', ' ').title()
    comment = CONFIG_COMMENTS.get(section, {}).get(key, '')
    hint = f'<span class="hint">{_esc(comment)}</span>' if comment else ''

    if isinstance(value, bool):
        checked = 'checked' if value else ''
        return (
            f'<div class="field">'
            f'<label><input type="checkbox" name="{name}" {checked}> {label}</label>'
            f'{hint}</div>'
        )
    elif isinstance(value, int):
        return (
            f'<div class="field">'
            f'<label>{label}<input type="number" name="{name}" value="{value}"></label>'
            f'{hint}</div>'
        )
    elif isinstance(value, float):
        return (
            f'<div class="field">'
            f'<label>{label}<input type="number" step="any" name="{name}" value="{value}"></label>'
            f'{hint}</div>'
        )
    else:  # str
        wide = 'wide' if len(value) > 40 else ''
        return (
            f'<div class="field">'
            f'<label>{label}<input type="text" name="{name}" value="{_esc(value)}" class="{wide}"></label>'
            f'{hint}</div>'
        )


def _esc(s):
    return s.replace('&', '&amp;').replace('"', '&quot;').replace('<', '&lt;')


def render_page(current, message=''):
    sections_html = ''
    for section, fields in current.items():
        rows = ''.join(render_field(section, k, v) for k, v in fields.items())
        sections_html += f'<section><h2>{section}</h2>{rows}</section>\n'

    msg_html = f'<div class="msg">{message}</div>' if message else ''

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>P4Frame Config</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font: 15px/1.5 system-ui, sans-serif; background: #111; color: #eee; padding: 20px; }}
  h1 {{ margin-bottom: 20px; color: #fff; }}
  h2 {{ font-size: 13px; text-transform: uppercase; letter-spacing: .1em;
        color: #888; margin: 24px 0 10px; border-bottom: 1px solid #333; padding-bottom: 4px; }}
  section {{ margin-bottom: 8px; }}
  .field {{ margin: 6px 0; }}
  label {{ display: flex; align-items: center; gap: 10px; }}
  label:has(input[type=checkbox]) {{ cursor: pointer; }}
  input[type=text], input[type=number] {{
    background: #222; border: 1px solid #444; color: #eee;
    padding: 4px 8px; border-radius: 4px; width: 220px; font-size: 14px;
  }}
  input.wide {{ width: 420px; }}
  input[type=checkbox] {{ width: 16px; height: 16px; cursor: pointer; }}
  .hint {{ display: block; font-size: 12px; color: #666; margin: 2px 0 0 0; }}
  .actions {{ margin-top: 28px; }}
  button {{ background: #1a7a3c; color: #fff; border: none; padding: 10px 28px;
            border-radius: 5px; font-size: 15px; cursor: pointer; }}
  button:hover {{ background: #239952; }}
  .msg {{ margin: 12px 0; padding: 10px 16px; background: #1a3a1a; border-left: 3px solid #3c3; border-radius: 4px; color: #7f7; }}
</style>
</head>
<body>
<h1>P4Frame Configuration</h1>
{msg_html}
<form method="POST" action="/save">
{sections_html}
<div class="actions">
  <button type="submit">Save &amp; Restart</button>
</div>
</form>
</body>
</html>"""


class ConfigHandler(BaseHTTPRequestHandler):
    conf_path = None  # Set before server starts

    def log_message(self, fmt, *args):
        logging.debug(fmt % args)

    def do_GET(self):
        if self.path not in ('/', '/?saved=1'):
            self._respond(404, 'text/plain', b'Not found')
            return
        current = get_current_config()
        message = 'Configuration saved. media_frame.py restarted.' if self.path == '/?saved=1' else ''
        body = render_page(current, message=message).encode()
        self._respond(200, 'text/html; charset=utf-8', body)

    def do_POST(self):
        if self.path != '/save':
            self._respond(404, 'text/plain', b'Not found')
            return

        length = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(length).decode()
        params = parse_qs(raw, keep_blank_values=True)

        current = get_current_config()
        overrides = load_conf_file(self.conf_path)

        for section, fields in current.items():
            if section not in overrides:
                overrides[section] = {}
            for key, original in fields.items():
                form_key = f"{section}.{key}"
                if isinstance(original, bool):
                    # Checkboxes are absent from POST when unchecked
                    overrides[section][key] = form_key in params
                elif form_key in params:
                    raw_val = params[form_key][0]
                    overrides[section][key] = self._coerce(raw_val, original)

        save_conf_file(self.conf_path, overrides)
        logging.info(f"Config saved to {self.conf_path}")
        cfg.load_custom_config(self.conf_path)

        restart_media_frame(self.conf_path)

        # Post/Redirect/Get: redirect so a page refresh won't re-submit the form
        self.send_response(303)
        self.send_header('Location', '/?saved=1')
        self.end_headers()

    def _coerce(self, raw, original):
        """Cast form string value to match the original type."""
        try:
            if isinstance(original, int):
                return int(raw)
            if isinstance(original, float):
                return float(raw)
        except ValueError:
            pass
        return raw

    def _respond(self, code, content_type, body):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser(description='P4Frame web configuration server')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help='HTTP port (default: 8080)')
    parser.add_argument('--conf', required=True,
                        help='Config override file path (e.g. p4frame_linux.conf)')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s')

    ConfigHandler.conf_path = os.path.abspath(args.conf)
    cfg.load_custom_config(ConfigHandler.conf_path)
    server = HTTPServer(('0.0.0.0', args.port), ConfigHandler)
    logging.info(f"Config server running at http://0.0.0.0:{args.port}")
    logging.info(f"Config file: {ConfigHandler.conf_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Config server stopped")


if __name__ == '__main__':
    main()
