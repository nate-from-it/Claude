"""
NIST 800-53 rev5 Control Translator - backend API.

Deliberately zero third-party dependencies (stdlib http.server only) so it
runs anywhere with just `python3 app.py` - no pip install required.
"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from tailoring import AUDIENCES, TECHNOLOGIES, tailor_control

DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "families")


def load_catalog():
    with open(os.path.join(DATA_DIR, "_meta.json")) as f:
        meta = json.load(f)

    controls = []
    for family in meta["families"]:
        with open(os.path.join(DATA_DIR, f"{family['id']}.json")) as f:
            controls.extend(json.load(f))

    return {"source": meta["source"], "families": meta["families"], "controls": controls}


CATALOG = load_catalog()
CONTROLS_BY_ID = {c["id"]: c for c in CATALOG["controls"]}
FAMILIES = CATALOG["families"]


def family_counts():
    counts = {}
    for c in CATALOG["controls"]:
        if c["withdrawn"]:
            continue
        counts[c["family"]] = counts.get(c["family"], 0) + 1
    return counts


def list_controls(params):
    family = (params.get("family", [""])[0] or "").upper()
    query = (params.get("q", [""])[0] or "").strip().lower()
    include_enhancements = (params.get("enhancements", ["true"])[0] or "true").lower() != "false"
    include_withdrawn = (params.get("withdrawn", ["false"])[0] or "false").lower() == "true"

    results = CATALOG["controls"]
    if family:
        results = [c for c in results if c["family"] == family]
    if not include_enhancements:
        results = [c for c in results if not c["is_enhancement"]]
    if not include_withdrawn:
        results = [c for c in results if not c["withdrawn"]]
    if query:
        results = [
            c
            for c in results
            if query in c["title"].lower()
            or query in c["number"].lower()
            or query in (c.get("statement") or "").lower()
        ]

    summary = [
        {
            "id": c["id"],
            "number": c["number"],
            "title": c["title"],
            "family": c["family"],
            "is_enhancement": c["is_enhancement"],
            "withdrawn": c["withdrawn"],
        }
        for c in results
    ]
    return 200, {"count": len(summary), "controls": summary}


def get_control(control_id):
    control = CONTROLS_BY_ID.get(control_id.lower())
    if not control:
        return 404, {"error": "control not found"}
    return 200, control


def tailor(control_id, body):
    control = CONTROLS_BY_ID.get(control_id.lower())
    if not control:
        return 404, {"error": "control not found"}

    technologies = body.get("technologies") or []
    audience = body.get("audience") or "sysadmin"

    if not isinstance(technologies, list) or not technologies:
        return 400, {"error": "technologies must be a non-empty list"}
    if audience not in AUDIENCES:
        return 400, {"error": f"audience must be one of {list(AUDIENCES)}"}

    result = tailor_control(control, technologies, audience)
    return 200, {
        "control": {"id": control["id"], "number": control["number"], "title": control["title"]},
        **result,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # keep stdout quiet; flip on for debugging

    def _send(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, {})

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/api/health":
            self._send(200, {"status": "ok", "controls": len(CATALOG["controls"])})
        elif path == "/api/families":
            counts = family_counts()
            self._send(200, [{**f, "control_count": counts.get(f["id"], 0)} for f in FAMILIES])
        elif path == "/api/technologies":
            self._send(200, [{"id": k, "name": v} for k, v in TECHNOLOGIES.items()])
        elif path == "/api/audiences":
            self._send(200, [{"id": k, "name": v} for k, v in AUDIENCES.items()])
        elif path == "/api/controls":
            status, payload = list_controls(params)
            self._send(status, payload)
        elif path.startswith("/api/controls/"):
            control_id = path[len("/api/controls/"):]
            status, payload = get_control(control_id)
            self._send(status, payload)
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/controls/") and path.endswith("/tailor"):
            control_id = path[len("/api/controls/"):-len("/tailor")]
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                self._send(400, {"error": "invalid JSON body"})
                return
            status, payload = tailor(control_id, body)
            self._send(status, payload)
        else:
            self._send(404, {"error": "not found"})


def main():
    port = int(os.environ.get("PORT", 5057))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"NIST 800-53 translator API listening on :{port} ({len(CATALOG['controls'])} controls loaded)")
    server.serve_forever()


if __name__ == "__main__":
    main()
