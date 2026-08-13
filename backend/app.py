"""
NIST 800-53 rev5 Control Translator - backend API.

Deliberately zero third-party dependencies (stdlib http.server only) so it
runs anywhere with just `python3 app.py` - no pip install required.
"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from tailoring import AUDIENCES, TECHNOLOGIES, tailor_control, technologies_for_audience
from stigs import STIG_META, rules_for_control, search_rules, stig_technologies
from narrative import generate_narrative

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
# STIG rules carry base NIST control numbers (e.g. "AC-4"), which is also
# the number of that control's own (non-enhancement) catalog entry - so
# this maps a base number straight to its control id for deep-linking.
CONTROL_ID_BY_NUMBER = {c["number"]: c["id"] for c in CATALOG["controls"] if not c["is_enhancement"]}


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

    if not isinstance(technologies, list):
        return 400, {"error": "technologies must be a list (may be empty for narrative-only)"}
    if audience not in AUDIENCES:
        return 400, {"error": f"audience must be one of {list(AUDIENCES)}"}

    result = tailor_control(control, technologies, audience)
    return 200, {
        "control": {"id": control["id"], "number": control["number"], "title": control["title"]},
        **result,
    }


def stig_for_control(control_id, params):
    control = CONTROLS_BY_ID.get(control_id.lower())
    if not control:
        return 404, {"error": "control not found"}

    technology = (params.get("technology", [""])[0] or "").strip()
    if not technology:
        return 400, {"error": "technology query param is required"}

    if technology not in stig_technologies():
        return 200, {
            "control": {"id": control["id"], "number": control["number"], "title": control["title"]},
            "technology": technology,
            "technology_name": TECHNOLOGIES.get(technology, technology),
            "available": False,
            "rules": [],
        }

    rules = rules_for_control(control["number"], technology)
    return 200, {
        "control": {"id": control["id"], "number": control["number"], "title": control["title"]},
        "technology": technology,
        "technology_name": TECHNOLOGIES.get(technology, technology),
        "available": True,
        "source": STIG_META[technology],
        "rules": rules,
    }


def narrative_for_control(control_id, body):
    control = CONTROLS_BY_ID.get(control_id.lower())
    if not control:
        return 404, {"error": "control not found"}

    technologies = body.get("technologies") or []
    status = body.get("status")

    if not isinstance(technologies, list) or not technologies:
        return 400, {"error": "technologies must be a non-empty list"}
    if status not in ("met", "not_met"):
        return 400, {"error": 'status must be "met" or "not_met"'}

    technologies = [t for t in technologies if t in TECHNOLOGIES]
    if not technologies:
        return 400, {"error": "no valid technologies given"}

    stig_rule_ids_by_tech = {}
    for tech in technologies:
        if tech in stig_technologies():
            stig_rule_ids_by_tech[tech] = [r["id"] for r in rules_for_control(control["number"], tech)]

    narrative = generate_narrative(control, technologies, status, stig_rule_ids_by_tech)
    return 200, {
        "control": {"id": control["id"], "number": control["number"], "title": control["title"]},
        "status": status,
        "narrative": narrative,
    }


def stig_search(params):
    query = (params.get("q", [""])[0] or "").strip()
    technologies = params.get("technology") or None

    total, truncated, rules = search_rules(query, technologies)
    results = []
    for r in rules:
        controls = []
        for number in r["nist_controls"]:
            control_id = CONTROL_ID_BY_NUMBER.get(number)
            if control_id:
                controls.append({"id": control_id, "number": number, "title": CONTROLS_BY_ID[control_id]["title"]})
            else:
                controls.append({"id": None, "number": number, "title": None})
        results.append({
            "technology": r["technology"],
            "technology_name": TECHNOLOGIES.get(r["technology"], r["technology"]),
            "id": r["id"],
            "severity": r["severity"],
            "title": r["title"],
            "cci": r["cci"],
            "nist_controls": controls,
        })

    return 200, {"query": query, "count": total, "truncated": truncated, "results": results}


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
            audience = (params.get("audience", [""])[0] or "").strip()
            keys = technologies_for_audience(audience) if audience in AUDIENCES else list(TECHNOLOGIES)
            self._send(200, [{"id": k, "name": TECHNOLOGIES[k]} for k in keys])
        elif path == "/api/audiences":
            self._send(200, [{"id": k, "name": v} for k, v in AUDIENCES.items()])
        elif path == "/api/stig-technologies":
            self._send(200, [{"id": k, **v} for k, v in STIG_META.items()])
        elif path == "/api/stig/search":
            status, payload = stig_search(params)
            self._send(status, payload)
        elif path == "/api/controls":
            status, payload = list_controls(params)
            self._send(status, payload)
        elif path.startswith("/api/controls/") and path.endswith("/stig"):
            control_id = path[len("/api/controls/"):-len("/stig")]
            status, payload = stig_for_control(control_id, params)
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
        elif path.startswith("/api/controls/") and path.endswith("/narrative"):
            control_id = path[len("/api/controls/"):-len("/narrative")]
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                self._send(400, {"error": "invalid JSON body"})
                return
            status, payload = narrative_for_control(control_id, body)
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
