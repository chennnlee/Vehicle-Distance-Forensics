from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

AUTH_URL = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
CCTV_URL_TEMPLATE = "https://tdx.transportdata.tw/api/basic/v2/Road/Traffic/CCTV/City/{city}"


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def get_access_token(client_id: str, client_secret: str) -> str:
    resp = requests.post(
        AUTH_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        headers={"content-type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    resp.raise_for_status()
    token = resp.json().get("access_token")
    if not token:
        raise RuntimeError(f"No access_token in TDX auth response: {resp.text[:300]}")
    return token


def fetch_cctv_list(token: str, city: str) -> list[dict]:
    resp = requests.get(
        CCTV_URL_TEMPLATE.format(city=city),
        headers={"authorization": f"Bearer {token}"},
        params={"$format": "JSON"},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and "CCTVs" in data:
        return data["CCTVs"]
    if isinstance(data, list):
        return data
    raise RuntimeError(f"Unexpected CCTV response shape for city={city}: {str(data)[:300]}")


def try_direct_download(video_url: str, out_path: Path, timeout: int) -> bool:
    try:
        resp = requests.get(video_url, timeout=timeout, stream=True)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "image" not in content_type and not video_url.lower().endswith((".jpg", ".jpeg", ".png")):
            # Most TDX entries are MJPEG/HLS live streams or HTML viewer
            # pages, not single-shot snapshots -- grabbing an arbitrary byte
            # range from those would produce a corrupt, unusable file, so
            # bail out here and let the ffmpeg fallback handle streams.
            return False
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        return True
    except requests.RequestException:
        return False


def try_ffmpeg_grab(video_url: str, out_path: Path, timeout: int) -> bool:
    # Handles MJPEG (multipart/x-mixed-replace) and HLS (.m3u8) live streams
    # by decoding just the first frame, which a plain HTTP GET cannot do
    # since those are continuous streams rather than a single response body.
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-timeout", str(timeout * 1_000_000),
                "-i", video_url,
                "-frames:v", "1",
                "-update", "1",
                str(out_path),
            ],
            capture_output=True,
            timeout=timeout + 5,
        )
        return result.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def download_snapshot(video_url: str, out_path: Path, timeout: int = 10) -> bool:
    if try_direct_download(video_url, out_path, timeout):
        return True
    return try_ffmpeg_grab(video_url, out_path, timeout)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch static CCTV snapshots from Taiwan's TDX open data platform.")
    parser.add_argument("--cities", required=True, help="Comma-separated TDX city codes, e.g. Taipei,Kaohsiung,Hsinchu.")
    parser.add_argument("--out-dir", default="data/input/tdx_cctv", help="Output directory for downloaded snapshots and metadata.")
    parser.add_argument("--max-per-city", type=int, default=20, help="Maximum number of cameras to attempt per city.")
    parser.add_argument("--env-file", default=".env", help="Path to a .env file with TDX_CLIENT_ID / TDX_CLIENT_SECRET.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    env = {**load_env_file(PROJECT_ROOT / args.env_file), **{k: v for k, v in __import__("os").environ.items()}}
    client_id = env.get("TDX_CLIENT_ID")
    client_secret = env.get("TDX_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError(f"TDX_CLIENT_ID / TDX_CLIENT_SECRET not found in {args.env_file} or environment.")

    print("正在取得 TDX access token...")
    token = get_access_token(client_id, client_secret)

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = PROJECT_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest: list[dict] = []
    for city in [c.strip() for c in args.cities.split(",") if c.strip()]:
        print(f"=== {city} ===")
        try:
            cctvs = fetch_cctv_list(token, city)
        except Exception as exc:  # noqa: BLE001 - report and continue with other cities
            print(f"  查詢失敗: {exc}")
            continue
        print(f"  取得 {len(cctvs)} 支攝影機資訊")

        saved = 0
        for cam in cctvs:
            if saved >= args.max_per_city:
                break
            cam_id = cam.get("CCTVID", "unknown")
            video_url = cam.get("VideoStreamURL") or cam.get("VideoImageURL") or ""
            if not video_url:
                continue
            # Always save as .jpg: both the direct-download and ffmpeg-grab
            # paths produce a JPEG regardless of what the source URL's own
            # path/extension looks like (many are extension-less viewer
            # pages or stream endpoints, not real image file paths).
            out_path = out_dir / city / f"{cam_id}.jpg"
            ok = download_snapshot(video_url, out_path)
            manifest.append(
                {
                    "city": city,
                    "cctv_id": cam_id,
                    "road_name": cam.get("RoadName"),
                    "position_lon": cam.get("PositionLon"),
                    "position_lat": cam.get("PositionLat"),
                    "video_url": video_url,
                    "saved_path": str(out_path) if ok else None,
                    "status": "ok" if ok else "not_a_static_image_or_failed",
                }
            )
            if ok:
                saved += 1
            time.sleep(0.1)
        print(f"  成功下載 {saved} 張靜態影像")

    manifest_path = out_dir / "tdx_fetch_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"清單存於: {manifest_path}")


if __name__ == "__main__":
    main()
