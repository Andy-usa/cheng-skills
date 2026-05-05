#!/usr/bin/env python3
"""
English Passage → Educational Video for primary school kids (v4)

Phases:
  refs    — generate character + location reference images (concurrent, with redundancy)
  images  — generate scene images via image2image / text2image (concurrent, N candidates)
  tts     — synthesize per-scene audio (concurrent)
  video   — burn subtitles + concat into final mp4 (no zoom/pan, static cuts)
  all     — refs → images → tts → video

Usage:
  python3 make_video.py <out_dir> --json <scenes.json> --phase <refs|images|tts|video|all>

Optional flags:
  --concurrency N      max parallel dreamina calls (default 6)
  --candidates N       candidates per scene image (default 3, redundancy)

Design notes:
  - Concurrent generation with N=3 candidates per scene gives natural redundancy:
    if one candidate fails (即梦 upload DNS, content filter, etc.), another wins.
  - Static images, NO Ken Burns. Zoom/pan crops the bottom subtitle. Hard cuts only.
  - TTS uses edge-tts Jenny voice at slow rate (-25%) for elementary learners.
    Sandbox TLS proxies that intercept speech.platform.bing.com are handled by a
    scoped ssl-no-verify monkey-patch around the edge-tts call.
  - Scenes are intended to be SHORT (~2 sec average). Plan more, smaller scenes;
    do not keep one scene per long sentence.
"""

import argparse
import asyncio
import contextlib
import json
import os
import random
import shutil
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request

from PIL import Image, ImageDraw, ImageFont

CANVAS_W, CANVAS_H = 1920, 1080
FPS = 25

# TTS settings — Aria voice for elementary English learners (clearer
# articulation than Jenny at slow rates; Microsoft tags Aria as
# informational/teaching).
#   Primary: edge-tts en-US-AriaNeural at -30% (free, best quality)
#            (Microsoft sometimes 403s from cloud sandbox IPs.)
#   Fallback: Bailian qwen3-tts-flash "Cherry" voice (works anywhere DashScope
#            does), slowed via ffmpeg atempo since Bailian's speed param is no-op.
# Override via env: EDGE_TTS_VOICE / EDGE_TTS_RATE (e.g. EDGE_TTS_VOICE=en-US-JennyNeural)
TTS_VOICE_EDGE     = os.environ.get("EDGE_TTS_VOICE", "en-US-AriaNeural")
TTS_RATE_EDGE      = os.environ.get("EDGE_TTS_RATE", "-30%")
TTS_VOICE_BAILIAN  = "Cherry"
TTS_TEMPO_BAILIAN  = 0.77    # 0.77x speed via ffmpeg atempo (≈ -30% rate, match Aria)

# 即梦 (Dreamina): generation model + resolution
DRM_MODEL = "5.0"
DRM_RES   = "2k"

# Default concurrency / redundancy
DEFAULT_CONCURRENCY = 6
DEFAULT_CANDIDATES  = 3

# Visual style: Eggy Party (蛋仔派对) — chibi, round, cute, kid-friendly
STYLE_SUFFIX = (
    "Eggy Party style chibi cartoon, round egg-shaped bodies, "
    "oversized cute big shiny eyes, large heads, soft pastel candy colors, "
    "bright cheerful kawaii aesthetic, smooth 3D-rendered look, "
    "adorable kid-friendly character art, vibrant and playful, "
    "clean clear composition with subject centered and upper-framed "
    "(leave bottom 25% of frame empty for subtitle)"
)


# ── ssl helper for edge-tts in sandboxed environments ────────────────────────

def _patch_edge_tts_ssl():
    """Replace edge-tts's hardcoded SSL_CTX with a permissive one.

    edge-tts builds its own SSL context with `ssl.create_default_context(
    cafile=certifi.where())` and passes it explicitly to ws_connect, so
    monkey-patching aiohttp's TCPConnector doesn't help. The fix is to
    overwrite `edge_tts.communicate._SSL_CTX` (and the same constant in
    `edge_tts.voices`) before any TTS call.

    Sandbox TLS proxies inject a self-signed root that certifi's bundle
    doesn't trust. We disable verification only for this module — other
    HTTPS calls in the process are unaffected.

    Idempotent: safe to call multiple times.
    """
    import ssl
    import edge_tts.communicate
    import edge_tts.voices

    permissive = ssl.create_default_context()
    permissive.check_hostname = False
    permissive.verify_mode = ssl.CERT_NONE
    edge_tts.communicate._SSL_CTX = permissive
    edge_tts.voices._SSL_CTX = permissive


# ── 即梦 helpers (subprocess-based, called from a thread pool) ───────────────

def _drm_generate(args, timeout=180):
    """Run dreamina CLI; return parsed JSON or raise."""
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"dreamina exit {r.returncode}: {r.stderr[-300:]}")
    out = r.stdout.strip()
    try:
        data = json.loads(out)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"dreamina json parse: {e}; stdout head: {out[:300]}")
    return data


def _drm_extract_url(data):
    if data.get("gen_status") not in ("success", "succeed"):
        raise RuntimeError(f"gen_status={data.get('gen_status')!r} fail_reason={data.get('fail_reason','')[-200:]}")
    return data["result_json"]["images"][0]["image_url"]


def run_t2i_sync(prompt, out_path, ratio="16:9"):
    if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        return out_path
    data = _drm_generate([
        "dreamina", "text2image",
        f"--prompt={prompt}", f"--ratio={ratio}",
        f"--model_version={DRM_MODEL}", f"--resolution_type={DRM_RES}",
        "--poll=90",
    ])
    url = _drm_extract_url(data)
    urllib.request.urlretrieve(url, out_path)
    return out_path


def run_i2i_sync(ref, prompt, out_path, ratio="16:9"):
    """image2image; on upload failure (sandbox DNS quirk), fall back to text2image."""
    if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        return out_path
    try:
        data = _drm_generate([
            "dreamina", "image2image",
            f"--images={ref}", f"--prompt={prompt}", f"--ratio={ratio}",
            f"--model_version={DRM_MODEL}", f"--resolution_type={DRM_RES}",
            "--poll=90",
        ])
        url = _drm_extract_url(data)
    except RuntimeError as e:
        msg = str(e)
        # Upload phase commonly fails on sandbox DNS — fall back to t2i
        if "upload resource" in msg or "ApplyImageUpload" in msg or "resolve_no_records" in msg:
            return run_t2i_sync(prompt, out_path, ratio)
        raise
    urllib.request.urlretrieve(url, out_path)
    return out_path


# ── concurrent generation with N candidates per scene ────────────────────────

async def _gen_with_retry(sem, fn, *args, retries=3):
    """Async wrapper with bounded concurrency + exponential backoff retry."""
    async with sem:
        for attempt in range(retries):
            try:
                return await asyncio.to_thread(fn, *args)
            except Exception as e:
                if attempt == retries - 1:
                    raise
                await asyncio.sleep((2 ** attempt) + random.random())
        return None


async def gen_scene_image(i, scene, char_refs, loc_refs, img_dir, sem, n_candidates):
    """Generate N candidate images for scene i in parallel; return first success.

    Already-existing `s{i:02d}.jpg` is preserved (idempotent).
    Candidate files (`s{i:02d}_c{k}.jpg`) are kept on disk for QC inspection.
    """
    out_path = os.path.join(img_dir, f"s{i:02d}.jpg")
    if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        return out_path

    full_prompt = f"{scene['prompt']}, {STYLE_SUFFIX}"
    ref_name = scene.get("char_ref") or scene.get("loc_ref")
    ref_path = char_refs.get(ref_name) or loc_refs.get(ref_name)
    use_i2i = bool(ref_path and os.path.exists(ref_path))

    candidate_paths = [os.path.join(img_dir, f"s{i:02d}_c{k}.jpg") for k in range(n_candidates)]

    async def gen_one(c_path):
        if use_i2i:
            return await _gen_with_retry(sem, run_i2i_sync, ref_path, full_prompt, c_path)
        return await _gen_with_retry(sem, run_t2i_sync, full_prompt, c_path)

    tasks = [gen_one(p) for p in candidate_paths]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Pick first successful candidate as the canonical scene image
    winner = None
    for r, p in zip(results, candidate_paths):
        if not isinstance(r, Exception) and os.path.exists(p) and os.path.getsize(p) > 0:
            winner = p
            break

    if winner:
        shutil.copy(winner, out_path)
        return out_path

    errs = [str(r)[:120] for r in results if isinstance(r, Exception)]
    print(f"  [s{i:02d} ALL CANDIDATES FAILED] {errs}", file=sys.stderr)
    return None


# ── TTS: edge-tts Jenny, slow rate ───────────────────────────────────────────

async def _tts_edge(text, mp3_path):
    import edge_tts
    _patch_edge_tts_ssl()
    await edge_tts.Communicate(
        text, voice=TTS_VOICE_EDGE, rate=TTS_RATE_EDGE
    ).save(mp3_path)


def _tts_bailian_slow(text, mp3_path):
    """Bailian Cherry → ffmpeg atempo slowdown → mp3. Sync; call via thread."""
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY not set; Bailian fallback unavailable")
    payload = {
        "model": "qwen3-tts-flash",
        "input": {"text": text, "voice": TTS_VOICE_BAILIAN},
        "parameters": {"language_type": "English"},
    }
    req = urllib.request.Request(
        "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
        method="POST",
    )
    last_err = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read().decode("utf-8"))
            url = data["output"]["audio"]["url"]
            tmp_wav = mp3_path + ".wav.tmp"
            urllib.request.urlretrieve(url, tmp_wav)
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error",
                 "-i", tmp_wav,
                 "-filter:a", f"atempo={TTS_TEMPO_BAILIAN}",
                 "-codec:a", "libmp3lame", "-qscale:a", "2",
                 mp3_path],
                check=True,
            )
            os.remove(tmp_wav)
            return
        except (urllib.error.HTTPError, urllib.error.URLError,
                KeyError, subprocess.CalledProcessError) as e:
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Bailian TTS failed after retries: {last_err}")


async def tts_one(text, mp3_path):
    if os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 0:
        return
    try:
        await _tts_edge(text, mp3_path)
        return
    except Exception as e:
        # Microsoft sometimes 403s cloud sandbox IPs, or SSL is intercepted.
        # Bailian Cherry is the documented fallback.
        print(f"  [tts] edge-tts failed ({type(e).__name__}); falling back to Bailian Cherry",
              file=sys.stderr)
        # Clean up any zero-byte file edge-tts left behind
        if os.path.exists(mp3_path) and os.path.getsize(mp3_path) == 0:
            os.remove(mp3_path)
        await asyncio.to_thread(_tts_bailian_slow, text, mp3_path)


def get_duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", path],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(r.stdout)["format"]["duration"])


# ── subtitle burn ────────────────────────────────────────────────────────────

def _find_font(size=48):
    for fp in [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                pass
    return ImageFont.load_default()


def burn_subtitle(img_path, text, out_path):
    """Burn a centered subtitle into the bottom of the canvas. Static — no zoom."""
    img = Image.open(img_path).convert("RGB").resize((CANVAS_W, CANVAS_H), Image.LANCZOS)
    font = _find_font(48)

    lines = textwrap.wrap(text, width=48)
    line_h = 60
    block_h = line_h * len(lines) + 24
    y0 = CANVAS_H - block_h - 60

    rgba = img.convert("RGBA")
    bg = Image.new("RGBA", (CANVAS_W, block_h + 16), (0, 0, 0, 175))
    rgba.alpha_composite(bg, (0, y0 - 8))
    img = rgba.convert("RGB")

    draw = ImageDraw.Draw(img)
    for k, line in enumerate(lines):
        y = y0 + k * line_h
        bb = draw.textbbox((0, 0), line, font=font)
        x = (CANVAS_W - (bb[2] - bb[0])) // 2
        for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (2, 2)]:
            draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=(255, 255, 255))
    img.save(out_path, "JPEG", quality=95)


# ── video: per-scene clip + concat (no Ken Burns) ────────────────────────────

def make_scene_clip(img_path, audio_path, out_path, duration):
    """Static image + audio. Uniform encoding for concat compatibility."""
    r = subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-loop", "1", "-t", f"{duration:.3f}", "-i", img_path,
        "-i", audio_path,
        "-vf", (f"scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=decrease,"
                f"pad={CANVAS_W}:{CANVAS_H}:(ow-iw)/2:(oh-ih)/2,setsar=1"),
        "-r", str(FPS),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-shortest",
        out_path,
    ], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  [CLIP ERR] {r.stderr[-300:]}", file=sys.stderr)
        return False
    return True


def concat_clips(clip_paths, out_path):
    """Concatenate using absolute paths (avoids relative-path resolution bugs)."""
    list_file = out_path.replace(".mp4", "_list.txt")
    with open(list_file, "w") as f:
        for p in clip_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")
    r = subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-c", "copy", out_path,
    ], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  [CONCAT ERR] {r.stderr[-300:]}", file=sys.stderr)
        return False
    os.remove(list_file)
    return True


# ── phases ───────────────────────────────────────────────────────────────────

async def phase_refs(plan, ref_dir, char_refs, loc_refs, sem, n_candidates):
    characters = plan.get("characters", [])
    locations = plan.get("locations", [])
    print(f"\n=== [Phase: refs] {len(characters)} characters + {len(locations)} locations ===")

    async def gen_char(c):
        path = os.path.join(ref_dir, f"char_{c['name'].lower().replace(' ', '_')}.jpg")
        if os.path.exists(path) and os.path.getsize(path) > 0:
            char_refs[c["name"]] = path
            return c["name"]
        prompt = f"{c['ref_prompt']}, {STYLE_SUFFIX}"
        candidates = [os.path.join(ref_dir, f"char_{c['name'].lower().replace(' ', '_')}_c{k}.jpg") for k in range(n_candidates)]
        results = await asyncio.gather(
            *[_gen_with_retry(sem, run_t2i_sync, prompt, p, "3:2") for p in candidates],
            return_exceptions=True,
        )
        for r, p in zip(results, candidates):
            if not isinstance(r, Exception) and os.path.exists(p):
                shutil.copy(p, path)
                char_refs[c["name"]] = path
                return c["name"]
        return None

    async def gen_loc(l):
        path = os.path.join(ref_dir, f"loc_{l['name'].lower().replace(' ', '_')}.jpg")
        if os.path.exists(path) and os.path.getsize(path) > 0:
            loc_refs[l["name"]] = path
            return l["name"]
        prompt = f"{l['ref_prompt']}, {STYLE_SUFFIX}"
        candidates = [os.path.join(ref_dir, f"loc_{l['name'].lower().replace(' ', '_')}_c{k}.jpg") for k in range(n_candidates)]
        results = await asyncio.gather(
            *[_gen_with_retry(sem, run_t2i_sync, prompt, p, "16:9") for p in candidates],
            return_exceptions=True,
        )
        for r, p in zip(results, candidates):
            if not isinstance(r, Exception) and os.path.exists(p):
                shutil.copy(p, path)
                loc_refs[l["name"]] = path
                return l["name"]
        return None

    tasks = [gen_char(c) for c in characters] + [gen_loc(l) for l in locations]
    done = await asyncio.gather(*tasks, return_exceptions=True)
    for d in done:
        if isinstance(d, Exception):
            print(f"  ref ERR: {d}", file=sys.stderr)
        else:
            print(f"  ref ok: {d}")


async def phase_images(plan, img_dir, char_refs, loc_refs, sem, n_candidates):
    scenes = plan["scenes"]
    print(f"\n=== [Phase: images] {len(scenes)} scenes × {n_candidates} candidates ===")
    tasks = [
        gen_scene_image(i, s, char_refs, loc_refs, img_dir, sem, n_candidates)
        for i, s in enumerate(scenes, 1)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    ok = sum(1 for r in results if isinstance(r, str))
    print(f"  → {ok}/{len(scenes)} scenes have a winning image")


async def phase_tts(plan, audio_dir):
    scenes = plan["scenes"]
    print(f"\n=== [Phase: tts] {len(scenes)} scenes ===")
    tasks = []
    for i, s in enumerate(scenes, 1):
        p = os.path.join(audio_dir, f"s{i:02d}.mp3")
        tasks.append(tts_one(s["text"], p))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    ok = sum(1 for r in results if not isinstance(r, Exception))
    print(f"  → {ok}/{len(scenes)} audio files written")


def phase_video(plan, audio_dir, img_dir, sub_dir, clips_dir, final_dir):
    scenes = plan["scenes"]
    print(f"\n=== [Phase: video] burn subs + build clips ({len(scenes)}) ===")
    clip_paths = []
    for i, s in enumerate(scenes, 1):
        img_p = os.path.join(img_dir, f"s{i:02d}.jpg")
        if not os.path.exists(img_p):
            print(f"  [s{i:02d}] missing image, skip"); continue
        sub_p = os.path.join(sub_dir, f"s{i:02d}.jpg")
        burn_subtitle(img_p, s["text"], sub_p)

        audio_p = os.path.join(audio_dir, f"s{i:02d}.mp3")
        if not os.path.exists(audio_p):
            print(f"  [s{i:02d}] missing audio, skip"); continue
        dur = get_duration(audio_p)

        clip_p = os.path.join(clips_dir, f"clip_{i:02d}.mp4")
        ok = make_scene_clip(sub_p, audio_p, clip_p, dur)
        print(f"  [s{i:02d}] {dur:.1f}s → {'ok' if ok else 'FAIL'}")
        if ok:
            clip_paths.append(clip_p)

    if not clip_paths:
        print("❌ no clips to concat"); return

    final = os.path.join(final_dir, "english_lesson.mp4")
    if concat_clips(clip_paths, final):
        print(f"\n✅  {final}")
        try:
            subprocess.run(["open", final], check=False)
        except FileNotFoundError:
            pass


# ── main ─────────────────────────────────────────────────────────────────────

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--json", required=True, dest="plan_file")
    ap.add_argument("--phase", default="all",
                    choices=["refs", "images", "tts", "video", "all"])
    ap.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    ap.add_argument("--candidates", type=int, default=DEFAULT_CANDIDATES)
    return ap.parse_args()


async def main():
    args = parse_args()
    with open(args.plan_file) as f:
        plan = json.load(f)

    out = args.out_dir
    ref_dir   = os.path.join(out, "references")
    audio_dir = os.path.join(out, "audio")
    img_dir   = os.path.join(out, "images")
    sub_dir   = os.path.join(out, "images_sub")
    clips_dir = os.path.join(out, "clips")
    final_dir = os.path.join(out, "final")
    for d in (ref_dir, audio_dir, img_dir, sub_dir, clips_dir, final_dir):
        os.makedirs(d, exist_ok=True)

    sem = asyncio.Semaphore(args.concurrency)

    char_refs, loc_refs = {}, {}
    for c in plan.get("characters", []):
        p = os.path.join(ref_dir, f"char_{c['name'].lower().replace(' ', '_')}.jpg")
        if os.path.exists(p) and os.path.getsize(p) > 0:
            char_refs[c["name"]] = p
    for l in plan.get("locations", []):
        p = os.path.join(ref_dir, f"loc_{l['name'].lower().replace(' ', '_')}.jpg")
        if os.path.exists(p) and os.path.getsize(p) > 0:
            loc_refs[l["name"]] = p

    if args.phase in ("refs", "all"):
        await phase_refs(plan, ref_dir, char_refs, loc_refs, sem, args.candidates)

    if args.phase in ("images", "all"):
        await phase_images(plan, img_dir, char_refs, loc_refs, sem, args.candidates)

    if args.phase in ("tts", "all"):
        await phase_tts(plan, audio_dir)

    if args.phase in ("video", "all"):
        phase_video(plan, audio_dir, img_dir, sub_dir, clips_dir, final_dir)


if __name__ == "__main__":
    asyncio.run(main())
