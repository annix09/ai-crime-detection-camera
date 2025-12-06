import os, sqlite3, uuid, time
from flask import Flask, request, jsonify, render_template, send_file
from cryptography.fernet import Fernet
from pathlib import Path

app = Flask(__name__, template_folder="templates")
DB = "app.db"
EVIDENCE_DIR = Path("evidence")
EVIDENCE_DIR.mkdir(exist_ok=True)


from cryptography.fernet import Fernet
from pathlib import Path


KEY_FILE = Path("fernet.key")
if not KEY_FILE.exists():

    key = Fernet.generate_key()
    KEY_FILE.write_bytes(key)
    print("No key found, generated new key in fernet.key")
else:
    key = KEY_FILE.read_bytes()

fernet = Fernet(key)
print("Fernet key loaded:", key.decode())


def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY,
                    device_id TEXT,
                    location TEXT,
                    cls TEXT,
                    confidence REAL,
                    status TEXT,
                    timestamp REAL,
                    frame_b64 TEXT
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS evidence (
                    id TEXT PRIMARY KEY,
                    alert_id TEXT,
                    filename TEXT,
                    timestamp REAL
                )''')
    conn.commit(); conn.close()
init_db()

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/alerts", methods=["POST"])
def create_alert():
    data = request.json
    aid = str(uuid.uuid4())
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("INSERT INTO alerts VALUES (?,?,?,?,?,?,?,?)",
              (aid, data.get("device_id"), data.get("location"), data.get("cls"),
               data.get("confidence"), "pending", data.get("timestamp"), data.get("frame_b64")))
    conn.commit(); conn.close()
    return jsonify({"id": aid}), 201

@app.route("/api/alerts", methods=["GET"])
def list_alerts():
    status = request.args.get("status")
    conn = sqlite3.connect(DB); c = conn.cursor()
    if status:
        rows = c.execute("SELECT id, device_id, location, cls, confidence, status, timestamp FROM alerts WHERE status=?", (status,)).fetchall()
    else:
        rows = c.execute("SELECT id, device_id, location, cls, confidence, status, timestamp FROM alerts").fetchall()
    conn.close()
    out = [{"id": r[0], "device_id": r[1], "location": r[2], "cls": r[3], "confidence": r[4], "status": r[5], "timestamp": r[6]} for r in rows]
    return jsonify(out)

@app.route("/api/alerts/<aid>/status", methods=["GET"])
def alert_status(aid):
    conn = sqlite3.connect(DB); c = conn.cursor()
    r = c.execute("SELECT status FROM alerts WHERE id=?", (aid,)).fetchone()
    conn.close()
    if not r:
        return jsonify({"error":"not found"}), 404
    return jsonify({"status": r[0]})

@app.route("/api/alerts/<aid>/action", methods=["POST"])
def alert_action(aid):
    data = request.json
    action = data.get("action")
    reviewer = data.get("reviewer", "anonymous")
    conn = sqlite3.connect(DB); c = conn.cursor()
    if action not in ["confirm", "reject"]:
        return jsonify({"error":"invalid action"}), 400
    c.execute("UPDATE alerts SET status=? WHERE id=?", (action, aid))
    conn.commit(); conn.close()
    return jsonify({"ok": True})


@app.route("/api/upload_evidence", methods=["POST"])
def upload_evidence():
    alert_id = request.form.get("alert_id")
    file = request.files.get("file")
    if not alert_id or not file:
        return jsonify({"error":"missing"}), 400
    filename = f"{int(time.time())}_{file.filename}"
    raw_path = EVIDENCE_DIR / filename
    file.save(raw_path)
    data = raw_path.read_bytes()
    enc_path = EVIDENCE_DIR / (filename + ".enc")
    enc_path.write_bytes(fernet.encrypt(data))
    raw_path.unlink(missing_ok=True)
    eid = str(uuid.uuid4())
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("INSERT INTO evidence VALUES (?,?,?,?)", (eid, alert_id, str(enc_path), time.time()))
    conn.commit(); conn.close()
    return jsonify({"ok": True, "evidence_id": eid})

@app.route("/api/evidence", methods=["GET"])
def list_evidence():
    conn = sqlite3.connect(DB); c = conn.cursor()
    rows = c.execute("SELECT id, alert_id, filename, timestamp FROM evidence").fetchall()
    conn.close()
    out = [{"id": r[0], "alert_id": r[1], "path": r[2], "timestamp": r[3]} for r in rows]
    return jsonify(out)

@app.route("/api/download/<evidence_id>", methods=["GET"])
def download_evidence(evidence_id):
    conn = sqlite3.connect(DB); c = conn.cursor()
    row = c.execute("SELECT filename FROM evidence WHERE id=?", (evidence_id,)).fetchone()
    conn.close()
    if not row:
        return "Not found", 404
    return send_file(row[0], as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
