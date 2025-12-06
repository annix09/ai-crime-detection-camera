"""
Multi-camera YOLO alert sender.
- Each camera runs in its own thread.
- Uses snapshot (/shot.jpg) method for reliability.
- One alert per EVENT_WINDOW_SECONDS per (device|location|class).
"""
import time, os, base64, requests, cv2, uuid, threading
import numpy as np
from collections import deque
from ultralytics import YOLO

# --------- GLOBAL CONFIG ----------
BACKEND = "http://10.232.133.20:8000"  

# Default model path
DEFAULT_MODEL_PATH = "best.pt"  

# Cameras: add/modify entries here
# stream: full '/video' URL from IP Webcam
# device_id / location: label strings used for dedupe/storage
# optionally override model_path per camera
CAMERAS = [
    {"stream": "http://10.232.133.189:8080", "device_id": "phone_cam_1", "location": "Main Gate"},
    {"stream": "http://10.232.133.99:8080", "device_id": "phone_cam_2", "location": "Parking Lot", "model_path": "best.pt"}
]

# Detection tuning (common)
CONF_THRESHOLD = 0.35
CONSECUTIVE_REQUIRED = 2
FPS = 5  # used to size ring buffer and approximate timing

# Event window: send only 1 alert per device|location|class per this interval
EVENT_WINDOW_SECONDS = 30

# How many seconds to keep as post-trigger (we default 0 because ring already stores pre-30s)
POST_SECONDS = 0

# Max retries to post alert if first attempt fails
ALERT_POST_RETRIES = 3
ALERT_POST_RETRY_DELAY = 2.0

# Target classes 
TARGET_CLASSES = set(["guns", "knife"])
# ------------------------------------------------

# Utility: create shot URL from /video
def to_shot_url(video_url):
    if "/video" in video_url:
        return video_url.replace("/video", "/shot.jpg")
    return video_url.rstrip("/") + "/shot.jpg"

# Helper: save ring to mp4
def save_ring_to_mp4(outpath=None, ring_frames=None, fps=FPS):
    if ring_frames is None or len(ring_frames) == 0:
        return None
    if outpath is None:
        outpath = f"clip_{int(time.time())}_{uuid.uuid4().hex[:8]}.mp4"
    h, w = ring_frames[0].shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    try:
        out = cv2.VideoWriter(outpath, fourcc, fps, (w, h))
        for f in ring_frames:
            out.write(f)
        out.release()
        return outpath
    except Exception as e:
        print("save_ring_to_mp4 exception:", e)
        try: out.release()
        except: pass
        return None

# Upload clip helper (shared)
def upload_clip_to_backend(alert_id, filepath, backend_base=BACKEND):
    if not os.path.exists(filepath):
        print("upload: file not found", filepath)
        return False
    files = {"file": open(filepath, "rb")}
    data = {"alert_id": alert_id}
    try:
        r = requests.post(f"{backend_base}/api/upload_evidence", files=files, data=data, timeout=60)
        print("Upload response:", r.status_code, r.text)
        files["file"].close()
        return r.status_code == 200 or r.status_code == 201
    except Exception as e:
        print("Upload exception:", e)
        try: files["file"].close()
        except: pass
        return False

# Worker class for each camera
class CameraWorker(threading.Thread):
    def __init__(self, cam_cfg):
        super().__init__(daemon=True)
        self.stream = cam_cfg["stream"]
        self.shot_url = to_shot_url(self.stream)
        self.device_id = cam_cfg.get("device_id", "device")
        self.location = cam_cfg.get("location", "location")
        self.model_path = cam_cfg.get("model_path", DEFAULT_MODEL_PATH)
        self.fps = cam_cfg.get("fps", FPS)
        self.conf_threshold = cam_cfg.get("conf_threshold", CONF_THRESHOLD)
        self.consecutive_required = cam_cfg.get("consecutive_required", CONSECUTIVE_REQUIRED)
        self.target_classes = cam_cfg.get("target_classes", TARGET_CLASSES)
        # per-camera runtime state
        self.ring = deque(maxlen=self.fps * 30)
        self.consec = {}
        self.active_events = {}   # key -> event dict
        self.last_event_end = {}
        self.alert_map = {}       # alert_id -> timestamp
        self.model = None
        self.shutdown_flag = threading.Event()
        # startup banner identity
        self.name = f"{self.device_id}-{self.location}"

    def load_model(self):
        print(f"[{self.name}] Loading model: {self.model_path}")
        self.model = YOLO(self.model_path)
        print(f"[{self.name}] Loaded model. class names:", self.model.names)
        
        # If desired, auto-check and warn:
        model_names = set([v for k,v in self.model.names.items()]) if isinstance(self.model.names, dict) else set(self.model.names)
        missing = [c for c in self.target_classes if c not in model_names]
        if missing:
            print(f"[{self.name}] WARNING: target_classes {self.target_classes} contains items not in model.names {model_names}. Update camera config if needed.")

    def send_alert(self, frame, cls, conf):
        """Post to backend. returns alert_id or None."""
        _, buf = cv2.imencode('.jpg', frame)
        b64 = base64.b64encode(buf.tobytes()).decode('utf-8')
        payload = {
            "device_id": self.device_id,
            "location": self.location,
            "cls": cls,
            "confidence": float(conf),
            "timestamp": time.time(),
            "frame_b64": b64
        }
        try:
            r = requests.post(BACKEND + "/api/alerts", json=payload, timeout=5)
            if r.status_code == 201:
                res = r.json(); aid = res.get("id")
                print(f"[{self.name}] Sent alert id={aid} for {cls}")
                self.alert_map[aid] = time.time()
                return aid
            else:
                print(f"[{self.name}] Alert POST failed:", r.status_code, r.text)
                return None
        except Exception as e:
            print(f"[{self.name}] Alert POST exception:", e)
            return None

    def check_for_confirmed_alerts_and_upload(self):
        # poll own alert_map only
        to_upload = []
        for aid in list(self.alert_map.keys()):
            try:
                r = requests.get(f"{BACKEND}/api/alerts/{aid}/status", timeout=3)
                if r.status_code == 200:
                    st = r.json().get("status")
                    if st in ("confirm","confirmed"):
                        to_upload.append(aid)
                    elif st in ("reject","rejected"):
                        self.alert_map.pop(aid, None)
            except Exception:
                pass
        for aid in to_upload:
            print(f"[{self.name}] Confirmed alert detected: {aid}, saving clip...")
            tmp = save_ring_to_mp4(outpath=None, ring_frames=list(self.ring), fps=self.fps)
            if tmp:
                ok = upload_clip_to_backend(aid, tmp)
                if ok:
                    print(f"[{self.name}] Uploaded evidence for {aid}")
                    try: os.remove(tmp)
                    except: pass
                    self.alert_map.pop(aid, None)
                else:
                    print(f"[{self.name}] Upload failed for {aid}")
            else:
                print(f"[{self.name}] Failed to save clip for {aid}")

    def run(self):

        # load model
        try:
            self.load_model()
        except Exception as e:
            print(f"[{self.name}] model load failed:", e)
            return

        # main loop
        while not self.shutdown_flag.is_set():
            # fetch single shot frame
            try:
                r = requests.get(self.shot_url, timeout=6)
                if r.status_code != 200:
                    # print(f"[{self.name}] Shot request failed:", r.status_code)
                    time.sleep(0.2)
                    continue
                arr = np.frombuffer(r.content, np.uint8)
                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if frame is None:
                    # print(f"[{self.name}] Warning: decoded frame is None")
                    time.sleep(0.2)
                    continue
            except Exception as e:
                # print(f"[{self.name}] Shot request exception:", e)
                time.sleep(0.2)
                continue

            # resize & add to ring
            frame = cv2.resize(frame, (640, 480))
            self.ring.append(frame.copy())

            # inference and detection processing
            try:
                results = self.model.predict(source=frame, verbose=False)
            except Exception as e:
                print(f"[{self.name}] Model predict exception:", e)
                time.sleep(0.2)
                continue

            boxes = results[0].boxes
            # per-frame dedupe set
            seen_this_frame = set()
            for box in boxes:
                cls_idx = int(box.cls[0])
                cls_name = self.model.names[cls_idx]
                if cls_name in seen_this_frame:
                    continue
                seen_this_frame.add(cls_name)
                conf = float(box.conf[0])
                # debug
                # print(f"[{self.name}] Detected class='{cls_name}' conf={conf:.3f}")

                # gating
                if cls_name not in self.target_classes or conf < self.conf_threshold:
                    self.consec[cls_name] = 0
                    continue
                self.consec[cls_name] = self.consec.get(cls_name, 0) + 1
                if self.consec[cls_name] < self.consecutive_required:
                    continue

                # create event key
                key = f"{self.device_id}|{self.location}|{cls_name}"
                now = time.time()
                ev = self.active_events.get(key)

                # if an active event exists and is within window skip
                if ev and (now - ev["start_ts"] <= EVENT_WINDOW_SECONDS):
                    pass
                    self.consec[cls_name] = 0
                    continue

                # if last event just ended very recently, skip to avoid immediate re-creation
                last_end = self.last_event_end.get(key)
                if last_end and (now - last_end) < 2.0:
                    pass
                    self.consec[cls_name] = 0
                    continue

                # create event
                ev = {"start_ts": now, "alert_id": None, "posted": False, "post_attempts": 0, "last_post_attempt_ts": 0.0}
                self.active_events[key] = ev
                print(f"[{self.name}] created event for {key} at {now}")

                # try to post alert bounded times
                while ev["post_attempts"] < ALERT_POST_RETRIES and not ev["posted"]:
                    if ev["post_attempts"] > 0:
                        # throttle
                        sleep_needed = ALERT_POST_RETRY_DELAY - (time.time() - ev["last_post_attempt_ts"])
                        if sleep_needed > 0:
                            time.sleep(sleep_needed)
                    ev["post_attempts"] += 1
                    ev["last_post_attempt_ts"] = time.time()
                    print(f"[{self.name}] attempt POST {ev['post_attempts']} for {key}")
                    aid = self.send_alert(frame, cls_name, conf)
                    if aid:
                        ev["alert_id"] = aid
                        ev["posted"] = True
                        print(f"[{self.name}] POST succeeded for {key} -> {aid}")
                        break
                    else:
                        print(f"[{self.name}] POST failed attempt {ev['post_attempts']} for {key}")

                if not ev["posted"]:
                    print(f"[{self.name}] POST unsuccessful after retries for {key}. Event will still suppress further alerts for window.")

                # reset consec for class so it doesn't immediately re-trigger
                self.consec[cls_name] = 0

            # cleanup expired events
            now = time.time()
            expired = []
            for key, ev in list(self.active_events.items()):
                if now - ev["start_ts"] > EVENT_WINDOW_SECONDS:
                    print(f"[{self.name}] event window ended for {key}")
                    self.last_event_end[key] = now
                    expired.append(key)
            for k in expired:
                self.active_events.pop(k, None)

            # every few seconds, check for confirmed alerts and upload (per-camera)
            if int(time.time()) % 5 == 0:
                self.check_for_confirmed_alerts_and_upload()

            # sleep to roughly match FPS
            time.sleep(1.0 / max(1, self.fps))

        # shutdown cleanup
        print(f"[{self.name}] shutting down worker.")

# ---------- MAIN ----------
def main():
    # create and start workers
    workers = []
    for cam in CAMERAS:
        w = CameraWorker(cam)
        workers.append(w)
        w.start()
        # small stagger to avoid simultaneous heavy startup
        time.sleep(0.5)

    print("Started all camera workers. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutdown requested. Stopping workers...")
        for w in workers:
            w.shutdown_flag.set()
        # allow workers to exit
        for w in workers:
            w.join(timeout=5)
        print("All workers stopped. Exiting.")

if __name__ == "__main__":
    main()
