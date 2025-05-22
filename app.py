import webbrowser
from flask import Flask, request, send_from_directory, url_for, redirect, render_template_string, send_file
import yt_dlp
import os
import subprocess
import threading
import time
import uuid
import zipfile
from io import BytesIO
import json

app = Flask(__name__)
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

download_statuses = {}

def download_video(url, format_choice, job_id):
    status = {
        "progress": "Starting...",
        "files": []
    }
    download_statuses[job_id] = status

    def progress_hook(d):
        if d['status'] == 'downloading':
            percent = d.get('_percent_str', '').strip()
            eta = d.get('_eta_str', '').strip()
            status["progress"] = f"{percent} - ETA: {eta}" if eta else percent
        elif d['status'] == 'finished':
            status["progress"] = 'Processing finished...'
        elif d['status'] == 'error':
            status["progress"] = 'Error occurred'

    ydl_opts = {
        'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
        'progress_hooks': [progress_hook],
        'cookiefile': 'cookies.txt',
        'quiet': True,
        'ignoreerrors': True,
        'noplaylist': False
    }

    if format_choice == 'mp3':
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }]
        })
    else:
        ydl_opts.update({
            'format': 'bestvideo+bestaudio/best',
            'merge_output_format': 'mp4'
        })

    downloaded_files = []

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
        info_list = ydl.extract_info(url, download=False)

        entries = info_list['entries'] if 'entries' in info_list else [info_list]
        for info in entries:
            if info is None:
                continue
            filename = ydl.prepare_filename(info)
            ext = 'mp3' if format_choice == 'mp3' else 'mp4'
            base = os.path.splitext(filename)[0]
            filepath = base + f'.{ext}'
            if os.path.exists(filepath):
                downloaded_files.append(filepath)

    status["files"] = downloaded_files
    status["progress"] = "Download complete!"

    # Automatically open files in player
    player = 'C:\\Program Files\\Audacity\\audacity.exe' if format_choice == 'mp3' else 'C:\\Program Files\\VideoLAN\\VLC\\vlc.exe'
    try:
        for path in downloaded_files:
            subprocess.Popen([player, path])
    except Exception as e:
        print("Failed to open in player:", e)

@app.route('/')
def index():
    return '''
    <html>
        <head>
            <title>YouTube Downloader</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background-color: #f4f4f4;
                    padding: 30px;
                    text-align: center;
                }
                h1 {
                    color: #28a745;
                }
                input, select {
                    padding: 10px;
                    width: 400px;
                    margin: 10px 0;
                    font-size: 16px;
                }
                button {
                    padding: 10px 30px;
                    background-color: #007bff;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    cursor: pointer;
                    font-weight: bold;
                    font-size: 18px;
                }
                button:hover {
                    opacity: 0.8;
                }
            </style>
        </head>
        <body>
            <h1>YouTube to MP3/MP4 Downloader</h1>
            <form action="/start_download" method="post">
                <input type="text" name="url" placeholder="Paste YouTube playlist or video URL" required><br>
                <select name="format" required>
                    <option value="mp3">MP3 (Audio)</option>
                    <option value="mp4">MP4 (Video)</option>
                </select><br>
                <button type="submit">Start Download</button>
            </form>
        </body>
    </html>
    '''

@app.route('/start_download', methods=['POST'])
def start_download():
    url = request.form['url']
    format_choice = request.form['format']

    job_id = str(uuid.uuid4())
    threading.Thread(target=download_video, args=(url, format_choice, job_id), daemon=True).start()

    # Redirect user to progress page
    return redirect(url_for('progress', job_id=job_id))

@app.route('/progress/<job_id>')
def progress(job_id):
    status = download_statuses.get(job_id, None)
    if status is None:
        return "<h3>Invalid Job ID or download not started.</h3><a href='/'>Back to home</a>"

    # Auto-refresh every 2 seconds if not complete
    refresh = 2 if "complete" not in status["progress"].lower() else 0

    return f'''
    <html>
    <head>
        <title>Download Progress</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                background: #f7f9fc;
                text-align: center;
                padding: 40px;
            }}
            #progress {{
                font-size: 20px;
                color: #333;
                margin-bottom: 30px;
            }}
            a {{
                font-size: 18px;
                color: #2980b9;
                text-decoration: none;
                font-weight: bold;
            }}
            a:hover {{
                text-decoration: underline;
            }}
        </style>
        {'<meta http-equiv="refresh" content="2">' if refresh else ''}
    </head>
    <body>
        <h2>Download Progress</h2>
        <div id="progress">{status['progress']}</div>
        {'<a href="' + url_for("complete", job_id=job_id) + '">Go to Download Page</a>' if "complete" in status["progress"].lower() else ""}
        <br><br><a href="/">Cancel and go back</a>
    </body>
    </html>
    '''

@app.route('/complete/<job_id>')
def complete(job_id):
    status = download_statuses.get(job_id)
    if not status or not status.get("files"):
        return "<h2>No files found or download failed.</h2><br><a href='/'>Back to Home</a>"

    files = status["files"]

    file_items = ""
    for f in files:
        filename = os.path.basename(f)
        file_url = url_for('download_file', filename=filename)
        file_items += f'''
        <div style="margin-bottom:10px;">
            <input type="checkbox" class="file-checkbox" id="chk_{filename}" name="selected_files" value="{filename}" checked>
            <label for="chk_{filename}">{filename}</label>
            &nbsp;&nbsp;
            <a href="{file_url}" download style="text-decoration:none; color:#2980b9;">[Download]</a>
        </div>
        '''

    return render_template_string(f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Download Complete</title>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: #f7f9fc;
                padding: 40px;
                text-align: center;
            }}
            h2 {{
                color: #27ae60;
                margin-bottom: 30px;
            }}
            button {{
                background-color: #2980b9;
                color: white;
                padding: 12px 30px;
                border: none;
                border-radius: 8px;
                cursor: pointer;
                font-size: 18px;
                font-weight: 600;
                margin: 10px 15px;
                transition: background-color 0.3s ease;
            }}
            button:hover {{
                background-color: #3498db;
            }}
            #file-list {{
                text-align: left;
                max-width: 600px;
                margin: 0 auto 30px;
                background: white;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            }}
            #select-all-container {{
                margin-bottom: 15px;
            }}
        </style>
    </head>
    <body>
        <h2>Download Complete</h2>

        <div id="file-list">
            <div id="select-all-container">
                <input type="checkbox" id="select_all" checked>
                <label for="select_all" style="font-weight:bold; cursor:pointer;">Select All</label>
            </div>
            <form id="selectedDownloadForm">
                {file_items}
            </form>
        </div>

        <button onclick="downloadSelected()">Download Selected Files</button>
        <button onclick="downloadSelectedZip()">Download Selected as ZIP</button>
        <button onclick="window.location.href='/download_all_mp3/{job_id}'">Download All in MP3</button>
        <button onclick="window.location.href='/download_all_zip/{job_id}'">Download All in ZIP</button><br><br>

        <button onclick="window.location.href='/'">Back to Main</button>

        <script>
        // Toggle all checkboxes
        document.getElementById('select_all').addEventListener('change', function() {{
            const checked = this.checked;
            document.querySelectorAll('input.file-checkbox').forEach(chk => {{
                chk.checked = checked;
            }});
        }});

        // Download individual selected files
        function downloadSelected() {{
            const checkedBoxes = document.querySelectorAll('input.file-checkbox:checked');
            if(checkedBoxes.length === 0) {{
                alert('Please select at least one file to download.');
                return;
            }}

            checkedBoxes.forEach(chk => {{
                const filename = chk.value;
                const url = '/downloads/' + encodeURIComponent(filename);
                const a = document.createElement('a');
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
            }});
        }}

        // Download selected files as zip
        function downloadSelectedZip() {{
            const checkedBoxes = document.querySelectorAll('input.file-checkbox:checked');
            if(checkedBoxes.length === 0) {{
                alert('Please select at least one file to download as ZIP.');
                return;
            }}

            // Collect filenames
            const selectedFiles = Array.from(checkedBoxes).map(chk => chk.value);

            // POST selected files to server to get zip
            fetch('/download_selected_zip', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json'
                }},
                body: JSON.stringify({{files: selectedFiles}})
            }})
            .then(response => {{
                if(!response.ok) throw new Error('Network response was not ok.');
                return response.blob();
            }})
            .then(blob => {{
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'selected_files.zip';
                document.body.appendChild(a);
                a.click();
                a.remove();
                window.URL.revokeObjectURL(url);
            }})
            .catch(() => alert('Failed to download ZIP.'));
        }}
        </script>
    </body>
    </html>
    ''')

@app.route('/download_selected_zip', methods=['POST'])
def download_selected_zip():
    data = request.get_json()
    selected_files = data.get("files", [])
    if not selected_files:
        return "No files selected", 400

    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, 'w') as zf:
        for filename in selected_files:
            safe_filename = os.path.basename(filename)
            file_path = os.path.join(DOWNLOAD_DIR, safe_filename)
            if os.path.exists(file_path):
                zf.write(file_path, arcname=safe_filename)
    memory_file.seek(0)

    return send_file(memory_file,
                     mimetype='application/zip',
                     as_attachment=True,
                     download_name='selected_files.zip')

@app.route('/download_all_mp3/<job_id>')
def download_all_mp3(job_id):
    status = download_statuses.get(job_id)
    if not status or not status.get("files"):
        return "<h3>No files found.</h3><br><a href='/'>Back to home</a>"
    # Assuming the files are already mp3 or convert logic if needed
    # For simplicity, serve as is
    # We zip and send all mp3 files
    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, 'w') as zf:
        for filepath in status["files"]:
            if filepath.endswith('.mp3'):
                zf.write(filepath, arcname=os.path.basename(filepath))
    memory_file.seek(0)
    return send_file(memory_file,
                     mimetype='application/zip',
                     as_attachment=True,
                     download_name='all_mp3_files.zip')

@app.route('/download_all_zip/<job_id>')
def download_all_zip(job_id):
    status = download_statuses.get(job_id)
    if not status or not status.get("files"):
        return "<h3>No files found.</h3><br><a href='/'>Back to home</a>"
    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, 'w') as zf:
        for filepath in status["files"]:
            zf.write(filepath, arcname=os.path.basename(filepath))
    memory_file.seek(0)
    return send_file(memory_file,
                     mimetype='application/zip',
                     as_attachment=True,
                     download_name='all_files.zip')

@app.route('/downloads/<filename>')
def download_file(filename):
    # Secure filename
    safe_filename = os.path.basename(filename)
    return send_from_directory(DOWNLOAD_DIR, safe_filename, as_attachment=True)


# Open browser only once when Flask is ready
def open_browser():
    time.sleep(1)
    webbrowser.open("http://localhost:5000")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

