#!/usr/bin/env python3
# File: web/upload.py
# Upload handler for P4Frame web server.
# Accepts multipart/form-data POSTs (one file per request).
# Converts HEIC/HEIF to JPEG if pillow-heif is installed.

import io
import json
import logging
import os

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    _HEIC_SUPPORT = True
except ImportError:
    _HEIC_SUPPORT = False

_HEIC_EXTS = {'.heic', '.heif'}


def handle_get(handler):
    """Serve the upload page."""
    body = _render_page().encode()
    handler.send_response(200)
    handler.send_header('Content-Type', 'text/html; charset=utf-8')
    handler.send_header('Content-Length', len(body))
    handler.end_headers()
    handler.wfile.write(body)


def handle_post(handler, media_dir):
    """Handle a single-file upload POST. Responds with JSON."""
    filename, data = _parse_multipart(handler)

    if not filename or data is None:
        _json(handler, 400, {'ok': False, 'error': 'No file received'})
        return

    filename = os.path.basename(filename)
    if not filename:
        _json(handler, 400, {'ok': False, 'error': 'Invalid filename'})
        return

    ok, result = _save_file(filename, data, media_dir)
    if ok:
        _json(handler, 200, {'ok': True, 'saved_as': result})
    else:
        _json(handler, 500, {'ok': False, 'error': result})


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _parse_multipart(handler):
    """Parse multipart/form-data body. Returns (filename, bytes) or (None, None)."""
    content_type = handler.headers.get('Content-Type', '')
    content_length = int(handler.headers.get('Content-Length', 0))

    if 'boundary=' not in content_type:
        return None, None

    boundary = content_type.split('boundary=', 1)[1].strip().strip('"').encode()
    body = handler.rfile.read(content_length)
    delimiter = b'--' + boundary

    for part in body.split(delimiter)[1:]:
        if part.startswith(b'--'):   # epilogue marker
            break
        if part.startswith(b'\r\n'):
            part = part[2:]

        sep = part.find(b'\r\n\r\n')
        if sep == -1:
            continue

        headers_raw = part[:sep].decode('utf-8', errors='replace')
        payload = part[sep + 4:]
        if payload.endswith(b'\r\n'):
            payload = payload[:-2]

        filename = _extract_filename(headers_raw)
        if filename:
            return filename, payload

    return None, None


def _extract_filename(headers_raw):
    """Extract filename from Content-Disposition header text."""
    for line in headers_raw.split('\r\n'):
        if line.lower().startswith('content-disposition:'):
            for segment in line.split(';'):
                segment = segment.strip()
                if segment.lower().startswith('filename='):
                    return segment[9:].strip().strip('"')
    return None


def _save_file(filename, data, media_dir):
    """Save file to media_dir, converting HEIC→JPEG if needed.
    Returns (ok: bool, saved_as_or_error: str).
    """
    name, ext = os.path.splitext(filename)

    if ext.lower() in _HEIC_EXTS:
        if not _HEIC_SUPPORT:
            return False, 'HEIC not supported: run "pip install pillow-heif"'
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(data))
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=90)
            data = buf.getvalue()
            filename = name + '.jpg'
        except Exception as e:
            return False, f'HEIC conversion failed: {e}'

    dest = os.path.join(media_dir, filename)
    try:
        with open(dest, 'wb') as f:
            f.write(data)
    except OSError as e:
        return False, f'Write failed: {e}'

    logging.info(f"Uploaded {len(data)} bytes → {dest}")
    return True, filename


def _json(handler, code, payload):
    body = json.dumps(payload).encode()
    handler.send_response(code)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Content-Length', len(body))
    handler.end_headers()
    handler.wfile.write(body)


def _render_page():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>P4Frame Upload</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font: 15px/1.5 system-ui, sans-serif; background: #111; color: #eee; padding: 20px; }
  h1 { margin-bottom: 16px; color: #fff; }
  .tabs { display: flex; gap: 2px; margin-bottom: 24px; border-bottom: 1px solid #333; }
  .tab { padding: 8px 22px; text-decoration: none; color: #888;
         border-radius: 4px 4px 0 0; font-size: 14px; }
  .tab.active { background: #222; color: #fff; border: 1px solid #333; border-bottom: 1px solid #222; }
  .tab:hover:not(.active) { color: #ccc; }
  .drop-zone { border: 2px dashed #444; border-radius: 8px; padding: 48px 20px;
               text-align: center; color: #888; cursor: pointer;
               transition: border-color .2s, background .2s; }
  .drop-zone.dragover { border-color: #1a7a3c; background: #0e1e0e; color: #eee; }
  .drop-zone p { pointer-events: none; }
  .drop-zone .sub { font-size: 13px; margin-top: 6px; color: #555; }
  input[type=file] { display: none; }
  .file-count { color: #888; font-size: 13px; margin: 10px 0 4px; min-height: 20px; }
  .btn { display: block; width: 100%; background: #1a7a3c; color: #fff; border: none;
         padding: 14px; border-radius: 6px; font-size: 16px; cursor: pointer;
         margin-top: 10px; }
  .btn:hover:not(:disabled) { background: #239952; }
  .btn:disabled { background: #333; color: #666; cursor: default; }
  .progress-wrap { margin: 18px 0 0; display: none; }
  .progress-label { font-size: 13px; color: #aaa; margin-bottom: 6px; }
  .progress-bg { background: #222; border-radius: 6px; height: 14px; border: 1px solid #333; overflow: hidden; }
  .progress-fill { background: #1a7a3c; height: 100%; width: 0%;
                   transition: width .25s ease; border-radius: 6px; }
  .results { margin-top: 16px; }
  .result { padding: 7px 12px; margin: 4px 0; border-radius: 4px; font-size: 13px; word-break: break-all; }
  .result.ok  { background: #0e2a0e; color: #7f7; border-left: 3px solid #3c3; }
  .result.err { background: #2a0e0e; color: #f77; border-left: 3px solid #c33; }
</style>
</head>
<body>
<h1>P4Frame</h1>
<nav class="tabs">
  <a href="/" class="tab">Config</a>
  <a href="/upload" class="tab active">Upload</a>
</nav>

<div class="drop-zone" id="dropZone">
  <p>Tap to select photos &amp; videos</p>
  <p class="sub">or drag and drop here</p>
</div>
<input type="file" id="fileInput" multiple accept="image/*,video/*">

<div class="file-count" id="fileCount"></div>
<button class="btn" id="uploadBtn" disabled>Upload</button>

<div class="progress-wrap" id="progressWrap">
  <div class="progress-label" id="progressLabel">0 / 0 uploaded</div>
  <div class="progress-bg"><div class="progress-fill" id="progressFill"></div></div>
</div>

<div class="results" id="results"></div>

<script>
const dropZone    = document.getElementById('dropZone');
const fileInput   = document.getElementById('fileInput');
const fileCount   = document.getElementById('fileCount');
const uploadBtn   = document.getElementById('uploadBtn');
const progressWrap = document.getElementById('progressWrap');
const progressLabel = document.getElementById('progressLabel');
const progressFill  = document.getElementById('progressFill');
const results     = document.getElementById('results');

let selectedFiles = [];

dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('dragover');
  setFiles(e.dataTransfer.files);
});
fileInput.addEventListener('change', () => setFiles(fileInput.files));

function setFiles(files) {
  selectedFiles = Array.from(files);
  const n = selectedFiles.length;
  fileCount.textContent = n > 0 ? `${n} file${n > 1 ? 's' : ''} selected` : '';
  uploadBtn.disabled = n === 0;
  results.innerHTML = '';
  progressWrap.style.display = 'none';
}

uploadBtn.addEventListener('click', async () => {
  if (!selectedFiles.length) return;

  uploadBtn.disabled = true;
  results.innerHTML = '';
  progressWrap.style.display = 'block';

  const total = selectedFiles.length;
  let done = 0;
  setProgress(0, total);

  for (const file of selectedFiles) {
    const fd = new FormData();
    fd.append('file', file);
    try {
      const resp = await fetch('/upload', { method: 'POST', body: fd });
      const data = await resp.json();
      done++;
      setProgress(done, total);
      if (data.ok) {
        addResult('ok', '\u2713 ' + file.name + (data.saved_as !== file.name ? ' \u2192 ' + data.saved_as : ''));
      } else {
        addResult('err', '\u2717 ' + file.name + ': ' + data.error);
      }
    } catch (err) {
      done++;
      setProgress(done, total);
      addResult('err', '\u2717 ' + file.name + ': network error');
    }
  }

  uploadBtn.disabled = false;
  fileInput.value = '';
  selectedFiles = [];
  fileCount.textContent = '';
});

function setProgress(done, total) {
  progressLabel.textContent = done + ' / ' + total + ' uploaded';
  progressFill.style.width = (total > 0 ? (done / total * 100) : 0) + '%';
}

function addResult(cls, msg) {
  const div = document.createElement('div');
  div.className = 'result ' + cls;
  div.textContent = msg;
  results.appendChild(div);
}
</script>
</body>
</html>"""
