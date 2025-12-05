from flask import Flask, render_template, jsonify
import json, os

app = Flask(__name__, static_folder='static', template_folder='templates')

# serve dashboard (renders templates with Jinja)
@app.route('/')
@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/alert/<alert_id>')
def alert_review(alert_id):
    # you can send alert_id to template if needed
    return render_template('alert_review.html', alert_id=alert_id)

@app.route('/evidence')
def evidence():
    return render_template('evidence.html')

# mock API - reads mock/alerts.json and returns it
@app.route('/api/alerts')
def api_alerts():
    fp = os.path.join(app.root_path, 'mock', 'alerts.json')
    try:
        with open(fp, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        data = []
    return jsonify(data)

# serve mock evidence if you make one later
@app.route('/api/evidence')
def api_evidence():
    fp = os.path.join(app.root_path, 'mock', 'evidence.json')
    try:
        with open(fp, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        data = []
    return jsonify(data)

if __name__ == '__main__':
    # debug True for easier development; accessible on localhost:8000
    app.run(host='0.0.0.0', port=8000, debug=True)
