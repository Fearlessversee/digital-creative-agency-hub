import http.server
import os
import json
import urllib.parse
import mimetypes
import functools
import posixpath
import sys

PORT = 5176
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("audio/mpeg", ".mp3")
mimetypes.add_type("audio/wav", ".wav")
mimetypes.add_type("application/json", ".json")
mimetypes.add_type("video/mp4", ".mp4")
mimetypes.add_type("application/octet-stream", ".riv")

def unflatten(val, arr, memo=None):
    if memo is None: memo = {}
    if isinstance(val, int):
        if val in memo: return memo[val]
        if val >= len(arr): return val
        raw = arr[val]
        if isinstance(raw, (int, float, str, bool)) or raw is None:
            return raw
        if isinstance(raw, list):
            if len(raw) >= 2 and isinstance(raw[0], str) and raw[0] in ('ShallowReactive', 'Reactive', 'Ref', 'Set'):
                return unflatten(raw[1], arr, memo)
            res = []
            memo[val] = res
            for item in raw:
                res.append(unflatten(item, arr, memo))
            return res
        if isinstance(raw, dict):
            res = {}
            memo[val] = res
            for k, v in raw.items():
                res[k] = unflatten(v, arr, memo)
            return res
        return raw
    elif isinstance(val, dict):
        return {k: unflatten(v, arr, memo) for k, v in val.items()}
    elif isinstance(val, list):
        return [unflatten(x, arr, memo) for x in val]
    return val

# Pre-index CMS data from payloads
CMS_CACHE = {}
for root, _, files in os.walk(DIRECTORY):
    if "_payload.json" in files:
        p = os.path.join(root, "_payload.json")
        try:
            with open(p, "r", encoding="utf-8") as f:
                arr = json.load(f)
            rel = os.path.relpath(root, DIRECTORY).replace("\\", "/").strip(".")
            key_name = rel.split("/")[-1] if rel else "home"
            for idx, item in enumerate(arr):
                if isinstance(item, dict) and "page" in item:
                    CMS_CACHE[key_name] = unflatten(idx, arr)
                    break
        except Exception:
            pass

print(f"Preloaded {len(CMS_CACHE)} CMS datasets for dynamic API fallback.")

class CleanAgencyHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        clean_path = parsed.path.rstrip('/')
        if clean_path in ('/api/cms', '/api', '/api/contact'):
            length = int(self.headers.get('Content-Length', 0))
            body_bytes = self.rfile.read(length) if length > 0 else b'{}'
            try:
                body = json.loads(body_bytes.decode('utf-8'))
            except Exception:
                body = {}

            variables = body.get('variables', {})
            slug = variables.get('slug', '')
            key = body.get('key', '')

            if slug and slug in CMS_CACHE:
                resp_data = CMS_CACHE[slug]
            elif key in CMS_CACHE:
                resp_data = CMS_CACHE[key]
            else:
                resp_data = {"page": {}, "success": True}

            resp_bytes = json.dumps(resp_data).encode('utf-8')
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp_bytes)))
            self.end_headers()
            self.wfile.write(resp_bytes)
            return

        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        clean_path = path.rstrip('/')

        # 1. DevTools & Meta probes
        if clean_path in ('/meta.json', '/.well-known/appspecific/com.chrome.devtools.json'):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")
            return

        # 2. Dynamic subpage routing
        rel_path = clean_path.lstrip('/')
        if rel_path:
            target_dir = os.path.join(DIRECTORY, rel_path.replace('/', os.sep))
            # If requesting subpage root without index.html
            if os.path.isdir(target_dir):
                target_index = os.path.join(target_dir, "index.html")
                if os.path.exists(target_index):
                    self.path = f"/{rel_path}/index.html"

        super().do_GET()

if __name__ == "__main__":
    os.chdir(DIRECTORY)
    handler = functools.partial(CleanAgencyHandler, directory=DIRECTORY)
    server = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), handler)
    print("=" * 60)
    print(f" Digital Agency Platform Live: http://localhost:{PORT}")
    print(f" Directory: {DIRECTORY}")
    print("=" * 60)
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
