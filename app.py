# app.py (Flask + Demucs 4-stem) — fixed URLs
import os
import sys
import uuid
import shutil
import subprocess
from pathlib import Path
from typing import Dict

from flask import Flask, request, send_from_directory, jsonify
from flask_cors import CORS

BASE_DIR = Path(__file__).resolve().parent
UPLOADS = BASE_DIR / "uploads"
OUTPUTS = BASE_DIR / "outputs"
STATIC = BASE_DIR / "static"

UPLOADS.mkdir(exist_ok=True)
OUTPUTS.mkdir(exist_ok=True)
STATIC.mkdir(exist_ok=True)

app = Flask(__name__, static_folder=str(STATIC), static_url_path="/static")
CORS(app)


@app.route("/")
def index():
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.route("/outputs/<path:subpath>")
def outputs_serve(subpath: str):
    """
    Serve files from the outputs directory, including nested paths like:
    <jobId>/htdemucs/<trackname>/vocals.wav
    """
    # Safe join and serve
    full = OUTPUTS / subpath
    if not full.exists() or not full.is_file():
        return jsonify({"detail": "File not found."}), 404
    # Use send_from_directory with relative path pieces
    directory, filename = os.path.split(str(full))
    return send_from_directory(directory, filename, as_attachment=False)


def _ffmpeg_exists() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        return True
    except FileNotFoundError:
        return False


def run_demucs(input_path: Path, out_dir: Path) -> Path:
    """
    Use Demucs (htdemucs) to split into 4 stems: vocals, drums, bass, other.
    Demucs writes to: out_dir/htdemucs/<input_stem>/
    Returns that final per-file output directory.
    """
    model = "htdemucs"
    cmd = [
        sys.executable, "-m", "demucs",
        "-n", model,
        "-o", str(out_dir),
        str(input_path),
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "Demucs failed.\n\n"
            f"Command: {' '.join(cmd)}\n\n"
            f"STDOUT:\n{proc.stdout}\n\nSTDERR:\n{proc.stderr}"
        )

    model_dir = out_dir / model
    if not model_dir.exists():
        raise RuntimeError("Demucs output not found.")
    candidates = [p for p in model_dir.iterdir() if p.is_dir()]
    if not candidates:
        raise RuntimeError("Demucs didn't produce a track folder.")
    return candidates[0]  # single file per run


def make_instrumental(drums: Path, bass: Path, other: Path, instrumental_out: Path):
    """
    Create an 'instrumental' by mixing drums+bass+other using ffmpeg.
    Falls back to copying 'other' if ffmpeg is missing or mixing fails.
    """
    if _ffmpeg_exists():
        cmd = [
            "ffmpeg", "-y",
            "-i", str(drums),
            "-i", str(bass),
            "-i", str(other),
            "-filter_complex", "amix=inputs=3:normalize=0",
            str(instrumental_out)
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0:
            shutil.copy2(other, instrumental_out)
    else:
        shutil.copy2(other, instrumental_out)


@app.post("/api/upload")
def upload() -> Dict:
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"detail": "No file uploaded."}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac"]:
        return jsonify({"detail": "Unsupported file format."}), 400

    uid = uuid.uuid4().hex
    input_path = UPLOADS / f"{uid}{ext}"
    file.save(str(input_path))

    job_dir = OUTPUTS / uid
    job_dir.mkdir(parents=True, exist_ok=True)

    try:
        out_subdir = run_demucs(input_path, job_dir)
        # Expect files: bass.wav, drums.wav, other.wav, vocals.wav
        vocals = out_subdir / "vocals.wav"
        drums = out_subdir / "drums.wav"
        bass = out_subdir / "bass.wav"
        other = out_subdir / "other.wav"

        for p in [vocals, drums, bass, other]:
            if not p.exists():
                raise RuntimeError(f"Missing expected stem: {p.name}")

        # Build Instrumental (drums + bass + other)
        instrumental = out_subdir / "instrumental.wav"
        make_instrumental(drums, bass, other, instrumental)

        # Copy original beside results for convenient download
        original_copy = job_dir / f"original{ext}"
        shutil.copy2(input_path, original_copy)

        # IMPORTANT: the returned URLs must include the whole relative path under /outputs
        # e.g. /outputs/<uid>/htdemucs/<trackname>/vocals.wav
        rel = out_subdir.relative_to(OUTPUTS)   # uid/htdemucs/<trackname>
        base = f"/outputs/{rel.as_posix()}"

        return jsonify({
            "id": uid,
            "original": f"/outputs/{uid}/original{ext}",
            "vocals": f"{base}/vocals.wav",
            "instrumental": f"{base}/instrumental.wav",
            "drums": f"{base}/drums.wav",
            "bass": f"{base}/bass.wav",
            "other": f"{base}/other.wav",
        })
    except Exception as e:
        shutil.rmtree(job_dir, ignore_errors=True)
        return jsonify({"detail": str(e)}), 500


@app.get("/api/health")
def health():
    # Quick checks: demucs & ffmpeg availability
    try:
        test = subprocess.run([sys.executable, "-m", "demucs", "-h"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        demucs_ok = (test.returncode == 0)
    except Exception:
        demucs_ok = False

    ffmpeg_ok = _ffmpeg_exists()
    return jsonify({"status": "ok", "demucs": demucs_ok, "ffmpeg": ffmpeg_ok})


if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=False)




