# Python V1.12
import cv2
import numpy as np
import requests
from flask import (
    Flask,
    Response,
    jsonify,
    render_template_string,
    request,
    stream_with_context,
)
from ultralytics import YOLO

app = Flask(__name__)

model = YOLO("best.pt")

# IP Address ESP32-CAM
#ESP32_IP = "192.168.18.232"
ESP32_IP = "192.168.11.183"
STREAM_URL = f"http://{ESP32_IP}:82/stream"
SETTINGS_URL = f"http://{ESP32_IP}/settings"

recognize_active = False
current_angle = 0

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset='UTF-8'>
    <title>Pre-Test YOLO - AI Dashboard</title>
    <style>
        *{box-sizing:border-box}
        body{margin:0;background:#1a1a1a;color:#e5e7eb;font-family:Inter,Arial,sans-serif;display:grid;grid-template-columns:300px minmax(0,1fr);min-height:100vh}
        .sidebar{padding:24px;background:#20242b;border-right:1px solid #2f3542;overflow-y:auto}
        .brand{font-size:18px;font-weight:700;color:#fff;margin-bottom:4px}
        .subtitle{font-size:12px;color:#9ca3af;margin-bottom:24px}
        .section-title{font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#9ca3af;margin:20px 0 12px}
        .setting-row{margin-bottom:16px}
        .setting-row label{display:flex;justify-content:space-between;font-size:13px;font-weight:600;margin-bottom:6px;color:#d1d5db}
        .note{font-size:10px;color:#9ca3af;font-weight:normal;}
        select{width:100%;padding:10px;border:1px solid #4b5563;border-radius:6px;background:#2d3748;color:#fff;font-size:13px}
        input[type=range]{width:100%;accent-color:#4ade80;cursor:pointer}
        .actions{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}
        button{padding:10px;border:1px solid #4b5563;border-radius:6px;background:#2d3748;color:#fff;font-size:12px;font-weight:600;cursor:pointer}
        button:hover{background:#374151}
        #status{font-size:12px;color:#4ade80;background:#111827;border-radius:6px;padding:10px;margin-top:16px;border:1px solid #374151;line-height:1.4}
        
        .main{padding:24px;display:flex;flex-direction:column;align-items:center;justify-content:flex-start;width:100%;overflow-y:auto}
        .header-bar{width:100%;max-width:1100px;display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}
        h1{font-size:20px;margin:0;color:#4ade80}
        
        /* Widget Wi-Fi & RSSI di Pojok Kanan Atas */
        .wifi-widget{display:flex;align-items:center;gap:8px;background:#20242b;border:1px solid #374151;padding:6px 12px;border-radius:20px;font-size:12px;color:#4ade80;font-weight:600}
        
        .camera-card{background:#111827;border:1px solid #374151;border-radius:12px;padding:16px;box-shadow:0 4px 6px -1px rgba(0,0,0,0.5);width:100%;max-width:1100px;display:flex;justify-content:center;align-items:center}
        
        /* Streaming Adaptif Jernih tanpa gepeng / terpotong */
        img{display:block;width:100%;max-height:80vh;height:auto;border-radius:8px;object-fit:contain;}
        
        .switch-container{background:#2d3748;padding:12px;border-radius:8px;border:1px solid #4b5563;margin-bottom:15px}
        .switch-label{display:flex;align-items:center;gap:10px;font-weight:bold;cursor:pointer;color:#4ade80}
        input[type=checkbox]{width:18px;height:18px;accent-color:#4ade80;cursor:pointer}
    </style>
</head>
<body>
    <aside class='sidebar'>
        <div class='brand'>AI Dashboard</div>
        <div class='subtitle'>ESP32-CAM Universal & YOLO</div>
        
        <div class='section-title' style='color:#4ade80;'>AI Testing Panel</div>
        <div class='switch-container'>
            <label class='switch-label'>
                <input type='checkbox' id='recognizeToggle' onchange='toggleRecognize(this)'>
                Object Recognize (BETA)
            </label>
        </div>

        <div class='section-title'>Flash Lighting</div>
        <div class='setting-row'>
            <label for='flashBrightness'>Flash Level <strong id='flashValue'>0</strong>%</label>
            <input id='flashBrightness' type='range' min='0' max='100' value='0' step='1' oninput='updateFlashText(this.value)' onchange='applySettings()'>
        </div>

        <div class='section-title'>Image Settings</div>
        <div class='setting-row'>
            <label for='resolution'>Resolution</label>
            <select id='resolution' onchange='applySettings()'>
                <option value='HD'>HD - 1280 x 720</option>
                <option value='SVGA' selected>SVGA - 800 x 600</option>
                <option value='VGA'>VGA - 640 x 480</option>
                <option value='QVGA'>QVGA - 320 x 240</option>
            </select>
        </div>
        <div class='setting-row'>
            <label for='quality'>JPEG Quality <strong id='qualityValue'>14</strong></label>
            <input id='quality' type='range' min='4' max='63' value='14' step='1' oninput='updateQualityText(this.value)' onchange='applySettings()'>
        </div>
        <div class='setting-row'>
            <label for='gainCeiling'>Gain Ceiling <span class='note'>(OV2640 Only)</span></label>
            <select id='gainCeiling' onchange='applySettings()'>
                <option value='2' selected>2x</option>
                <option value='4'>4x</option>
                <option value='8'>8x</option>
                <option value='16'>16x</option>
                <option value='32'>32x</option>
                <option value='64'>64x</option>
                <option value='128'>128x</option>
            </select>
        </div>

        <div class='section-title'>Orientation & Flip</div>
        <div class='switch-container' style='margin-bottom:8px;'>
            <label class='switch-label' style='color:#e5e7eb;'>
                <input type='checkbox' id='mirrorToggle' onchange='applySettings()'>
                Mirror Mode (H-Flip)
            </label>
        </div>
        <div class='switch-container' style='margin-bottom:12px;'>
            <label class='switch-label' style='color:#e5e7eb;'>
                <input type='checkbox' id='vflipToggle' onchange='applySettings()'>
                Vertical Flip (V-Flip)
            </label>
        </div>
        <div class='actions'>
            <button type='button' onclick='rotateCamera("left")'>ROTATE LEFT</button>
            <button type='button' onclick='rotateCamera("right")'>ROTATE RIGHT</button>
        </div>

        <div id='status'>System Ready</div>
    </aside>

    <main class='main'>
        <div class='header-bar'>
            <h1>Pre-Test YOLO Algorithm</h1>
            <div class='wifi-widget'>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.55a11 11 0 0 1 14.08 0"></path><path d="M1.42 9a16 16 0 0 1 21.16 0"></path><path d="M8.53 16.11a6 6 0 0 1 6.94 0"></path><line x1="12" y1="20" x2="12.01" y2="20"></line></svg>
                <span id='wifiText'>RSSI: -- dBm</span>
            </div>
        </div>
        <div class='camera-card'>
            <img id='streamImage' src='/video_feed' alt='Live Stream'>
        </div>
    </main>

    <script>
        const statusDiv = document.getElementById('status');
        const wifiText = document.getElementById('wifiText');
        let isInitializing = true;

        function updateQualityText(val) {
            document.getElementById('qualityValue').textContent = val;
        }

        function updateFlashText(val) {
            document.getElementById('flashValue').textContent = val;
        }

        function toggleRecognize(box) {
            fetch('/toggle_recognize?status=' + box.checked)
                .then(res => res.text())
                .then(data => console.log(data));
        }

        async function loadActiveSettings() {
            try {
                const res = await fetch('/get_settings');
                const data = await res.json();
                if(data.ok) {
                    document.getElementById('resolution').value = data.resolution || 'SVGA';
                    document.getElementById('quality').value = data.quality || 14;
                    document.getElementById('qualityValue').textContent = data.quality || 14;
                    document.getElementById('gainCeiling').value = data.gain_ceiling || 2;
                    document.getElementById('flashBrightness').value = data.flash || 0;
                    document.getElementById('flashValue').textContent = data.flash || 0;
                    document.getElementById('mirrorToggle').checked = (data.mirror == 1);
                    document.getElementById('vflipToggle').checked = (data.vflip == 1);
                    
                    if(data.rssi !== undefined) {
                        wifiText.textContent = `RSSI: ${data.rssi} dBm`;
                    }
                    
                    statusDiv.textContent = `Active | ${data.resolution} | Quality ${data.quality} | Flash ${data.flash || 0}%`;
                }
            } catch(e) {
                console.error("Gagal memuat setting aktif", e);
            } finally {
                isInitializing = false;
            }
        }

        function applySettings() {
            if (isInitializing) return;

            const res = document.getElementById('resolution').value;
            const q = document.getElementById('quality').value;
            const gc = document.getElementById('gainCeiling').value;
            const flash = document.getElementById('flashBrightness').value;
            const mirror = document.getElementById('mirrorToggle').checked ? 1 : 0;
            const vflip = document.getElementById('vflipToggle').checked ? 1 : 0;
            
            statusDiv.textContent = 'Applying settings...';

            fetch(`/update_settings?res=${res}&q=${q}&gc=${gc}&flash=${flash}&mirror=${mirror}&vflip=${vflip}`)
                .then(res => res.json())
                .then(data => {
                    if(data.ok) {
                        statusDiv.textContent = `Active | ${res} | Flash ${flash}% | Quality ${q} | H-Flip ${mirror} | V-Flip ${vflip}`;
                        if(data.rssi !== undefined) {
                            wifiText.textContent = `RSSI: ${data.rssi} dBm`;
                        }
                    } else {
                        statusDiv.textContent = 'Failed to apply settings';
                    }
                })
                .catch(err => {
                    statusDiv.textContent = 'Error connecting to camera settings';
                });
        }

        function rotateCamera(dir) {
            fetch('/rotate?dir=' + dir)
                .then(res => res.json())
                .then(data => {
                    statusDiv.textContent = 'Rotated ' + dir.toUpperCase() + ' (' + data.angle + '°)';
                });
        }

        loadActiveSettings();
    </script>
</body>
</html>
"""


@app.route("/")
def index():
  return render_template_string(HTML_TEMPLATE)


@app.route("/toggle_recognize")
def toggle_recognize():
  global recognize_active
  status = request.args.get("status", "false")
  recognize_active = True if status == "true" else False
  return f"Recognize status: {recognize_active}"


@app.route("/get_settings")
def get_settings():
  try:
    r = requests.get(SETTINGS_URL, timeout=2)
    if r.status_code == 200:
      return r.json()
    return jsonify({"ok": False}), 500
  except Exception as e:
    return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/update_settings")
def update_settings():
  res = request.args.get("res", "SVGA")
  q = request.args.get("q", "14")
  gc = request.args.get("gc", "2")
  flash = request.args.get("flash", "0")
  mirror = request.args.get("mirror", "0")
  vflip = request.args.get("vflip", "1")
  try:
    r = requests.get(
        f"{SETTINGS_URL}?res={res}&q={q}&gc={gc}&flash={flash}&mirror={mirror}&vflip={vflip}", timeout=3
    )
    if r.status_code == 200:
      return r.json()
    return jsonify({"ok": False}), 500
  except Exception as e:
    return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/rotate")
def rotate_cam():
  global current_angle
  direction = request.args.get("dir", "right")
  if direction == "right":
    current_angle = (current_angle + 90) % 360
  else:
    current_angle = (current_angle - 90) % 360
  return jsonify({"angle": current_angle})


def generate_frames():
  global current_angle
  frame_skip_counter = 0
  cached_boxes = []

  while True:
    try:
      stream = requests.get(STREAM_URL, stream=True, timeout=5)
      bytes_data = bytes()

      for chunk in stream.iter_content(chunk_size=1024):
        bytes_data += chunk
        a = bytes_data.find(b"\xff\xd8")
        b = bytes_data.find(b"\xff\xd9")
        if a != -1 and b != -1:
          jpg = bytes_data[a : b + 2]
          bytes_data = bytes_data[b + 2 :]

          if len(jpg) > 0:
            try:
              frame = cv2.imdecode(
                  np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR
              )
              if frame is not None:
                if current_angle == 90:
                  frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                elif current_angle == 180:
                  frame = cv2.rotate(frame, cv2.ROTATE_180)
                elif current_angle == 270:
                  frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

                if recognize_active:
                  frame_skip_counter += 1
                  if frame_skip_counter % 4 == 0:
                    cached_boxes = []
                    
                    # YOLOv8 inferensi dengan imgsz=320 yang stabil dan kilat
                    results = model(frame, imgsz=320, conf=0.5, verbose=False)
                    
                    for r in results:
                      for box in r.boxes:
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        conf = float(box.conf[0])
                        cls = int(box.cls[0])
                        class_name = model.names[cls]

                        cached_boxes.append(
                            (int(x1), int(y1), int(x2), int(y2), class_name, conf)
                        )

                  for box_info in cached_boxes:
                    x1, y1, x2, y2, class_name, conf = box_info
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    label = f"{class_name} ({conf:.2f})"
                    cv2.putText(
                        frame,
                        label,
                        (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (0, 255, 0),
                        2,
                    )

                _, buffer = cv2.imencode(
                    ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90]
                )
                frame_bytes = buffer.tobytes()
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
                )
            except Exception:
              continue
    except Exception as e:
      cv2.waitKey(1000)


@app.route("/video_feed")
def video_feed():
  return Response(
      stream_with_context(generate_frames()),
      mimetype="multipart/x-mixed-replace; boundary=frame",
  )


if __name__ == "__main__":
  print("Server Python berjalan di http://localhost:5000")
  app.run(host="0.0.0.0", port=5000, debug=False)