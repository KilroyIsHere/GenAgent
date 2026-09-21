#!/usr/bin/env python3
"""agatha cache helper — check/download page images for agatha.arch.be volumes.

Cache layout (see /workspace/agatha/cache/README.md):
    /workspace/agatha/cache/volumes/<bookpart_id>/
        index.json      per-page full_res_url (from IIIF manifest)
        manifest.json   raw IIIF manifest
        meta.json       volume metadata (date range, parish, type)
        pages/NNN.jpg   full-res page images (1-based, zero-padded 3)
        pages/NNN.ocr.txt  OCR transcription (kraken-ocr skill) — derived,
                          regenerable from NNN.jpg; safe to drop with clean --ocr
    /workspace/agatha/cache/crops/<bookpart_id>/NNN_<name>.png
    /workspace/agatha/cache/lookup/parishes.json, municipalities.json

USAGE (future invocations):
    # 0. Make sure the session is valid (auto-refresh: re-logins if stale).
    #    `get`/`init` already call this internally, so you can usually skip it.
    python3 agatha_cache.py ensure
    # 0b. (diagnostic) just report cookie validity: check / force re-login: login
    # 1. Find which volume covers a date: check meta.json of cached volumes,
    #    or search the site once (see SKILL.md runbook) and add the new volume.
    # 2. Get a page (cache-first, downloads only if missing; auto-refreshes):
    python3 agatha_cache.py get 6571 12
    # 3. List cached pages for a volume:
    python3 agatha_cache.py list 6571
    # 4. Add a brand-new volume (after finding manifest via the site):
    python3 agatha_cache.py init <bookpart_id> <manifest_url> <cookie> \
        --title "..." --range "01/01/1732 - 30/11/1774" --parish-id 13
    # 5. Save a crop (keeps it in cache):
    python3 agatha_cache.py crop 6571 12 <box:x,y,w,h> <name>
    # 6. Disk usage of the cache:
    python3 agatha_cache.py du
    # 7. Drop crops (all volumes, or one) — full-res pages are kept:
    python3 agatha_cache.py clean [bookpart_id]
    # 7b. Drop ONLY OCR outputs (.ocr.txt) — regenerable via kraken-ocr:
    python3 agatha_cache.py clean --ocr [bookpart_id]

SESSION / COOKIE:
  * The agatha PHPSESSID is a *session* cookie (no Expires/Max-Age) — it lives
    until the server drops the session; there is no fixed expiry time.
  * Nothing in the page workflow actually REQUIRES the cookie (verified):
    i3f.arch.be images, ajax.php lookups and the viewer page all return 200
    with a dead cookie + a Referer header. The cookie only controls the
    logged-in header (<AGATHA_USER> vs Login) and /en/profil/. So a stale cookie is a
    soft problem, but `ensure`/`check` keep it valid anyway.
  * Auto-refresh: `ensure` checks /en/profil/ (200 = valid); on stale it
    re-seeds a session and re-authenticates via library/login.php, saving the
    new PHPSESSID to session_cookie.txt. `get` and `init` call `ensure` first.

DOWNLOAD RULES (data is immutable — never re-download a cached page):
  * full-res image: GET <full_res_url from index.json> with headers
      Referer: <volume_url>   (from meta.json)
      Cookie:  <session cookie>
    No login needed for i3f.arch.be images if Referer+cookie are right;
    cookie from an agatha session (PHPSESSID; cookieconsent_status=dismiss).
  * IIIF manifest: GET <manifest_url> with Referer: <volume_url> + cookie.
  * On 403: session expired — re-login (runbook.md step 1) and retry once.
"""
import json
import os
import subprocess
import sys

CACHE = os.path.expanduser("/workspace/agatha/cache")


def vol_dir(bookpart_id: str) -> str:
    return os.path.join(CACHE, "volumes", str(bookpart_id))


def page_path(bookpart_id: str, page: int) -> str:
    return os.path.join(vol_dir(bookpart_id), "pages", f"{int(page):03d}.jpg")


def load_index(bookpart_id: str):
    p = os.path.join(vol_dir(bookpart_id), "index.json")
    if not os.path.exists(p):
        sys.exit(f"no index for {bookpart_id} — run 'init' first")
    return json.load(open(p))


def load_meta(bookpart_id: str):
    p = os.path.join(vol_dir(bookpart_id), "meta.json")
    if not os.path.exists(p):
        return {}
    return json.load(open(p))


COOKIE_FILE = os.path.join(CACHE, "session_cookie.txt")
BASE = "https://agatha.arch.be"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
LOGIN_URL = f"{BASE}/library/login.php"
GEN_URL = f"{BASE}/en/search/genealogie/"
# Session-gated page: /en/profil/ only renders (200, no redirect) for a
# valid PHPSESSID. Used as the login capability check.
PROFIL_URL = f"{BASE}/en/profil/"


def get_cookie() -> str:
    """Read a saved session cookie (updated by `login`/`ensure`)."""
    if os.path.exists(COOKIE_FILE):
        c = open(COOKIE_FILE).read().strip()
        if c:
            return c
    sys.exit(
        "no session cookie saved — run: python3 agatha_cache.py login"
    )


def _curl_http(url: str, cookie: str, referer: str, data: str = None,
               follow: bool = False) -> tuple:
    """Return (http_code, body). Minimal, for the login/check helpers."""
    cmd = ["curl", "-sS", "-w", "\n%{http_code}"]
    if cookie:
        cmd += ["--cookie", cookie]
    if follow:
        cmd += ["-L"]
    cmd += ["-A", UA, "-H", f"Referer: {referer}"]
    if data is not None:
        cmd += ["-X", "POST", "-H",
                "Content-Type: application/x-www-form-urlencoded",
                "--data", data]
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, text=True)
    body, _, code = r.stdout.rpartition("\n")
    return (code.strip(), body)


def _seed_session() -> str:
    """GET the search page to obtain a fresh PHPSESSID; return it."""
    # -c jar then read it; reuse a temp cookie jar
    jar = os.path.join(CACHE, ".seed_jar")
    r = subprocess.run(
        ["curl", "-sS", "-c", jar, "-o", os.devnull, "-A", UA,
         "-H", "Referer: https://agatha.arch.be/", GEN_URL],
        capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"failed to seed session: {r.stderr}")
    for line in open(jar):
        if line.startswith("#") or "\t" not in line:
            continue
        parts = line.split("\t")
        if len(parts) == 7 and parts[5] == "PHPSESSID":
            return f"PHPSESSID={parts[6].strip()}"
    sys.exit("no PHPSESSID returned when seeding session")


def do_login() -> str:
    """Perform a fresh login (seed + POST login.php) and save the cookie.

    Returns the new cookie string. Exits non-zero if credentials fail.
    """
    cookie = _seed_session()
    data = (
        "username=<AGATHA_USER>&password=<AGATHA_PASSWORD>"
        "&app=/en/search/genealogie"
    )
    code, body = _curl_http(LOGIN_URL, cookie, GEN_URL, data=data)
    ok = body.strip().endswith("1") or body.strip() == "1"
    if code != "200" or not ok:
        sys.exit(f"login failed (HTTP {code}, body={body.strip()[:80]!r}) "
                 f"— check credentials")
    with open(COOKIE_FILE, "w") as f:
        f.write(cookie + "\n")
    print(f"LOGIN OK — saved fresh cookie {cookie}")
    return cookie


def check_cookie(cookie: str) -> bool:
    """True if `cookie` is still a valid agatha session.

    Capability check: /en/profil/ renders (200) only for a valid session.
    """
    code, _body = _curl_http(PROFIL_URL, cookie, GEN_URL)
    # A valid session serves the profile page (200); a dead one redirects
    # (302 -> login) or errors. -L is off so we see the raw status.
    return code == "200"


def cmd_check() -> None:
    cookie = get_cookie()
    ok = check_cookie(cookie)
    if ok:
        print("COOKIE OK  (valid session)")
    else:
        print("COOKIE STALE (session expired — run 'login' or 'ensure')")
        sys.exit(2)


def cmd_ensure() -> str:
    """Return a guaranteed-valid cookie: reuse if fresh, re-login if stale.

    This is the auto-refresh: call it at the start of any agatha run.
    """
    cookie = get_cookie() if os.path.exists(COOKIE_FILE) else ""
    if cookie and check_cookie(cookie):
        print(f"COOKIE OK  (reusing {cookie})")
        return cookie
    print("cookie stale/missing — re-authenticating…")
    return do_login()


def curl(url: str, out: str, referer: str, cookie: str) -> None:
    r = subprocess.run(
        [
            "curl", "-sS", "-f", "-o", out,
            "-H", f"Referer: {referer}",
            "-H", f"Cookie: {cookie}",
            "-w", "%{http_code}",
            url,
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        os.unlink(out) if os.path.exists(out) else None
        sys.exit(f"download failed: {url}\n{r.stderr}")
    if r.stdout.strip() != "200":
        os.unlink(out)
        sys.exit(f"HTTP {r.stdout} for {url} — re-login and retry once")


def cmd_get(bookpart_id: str, page: int) -> None:
    dst = page_path(bookpart_id, page)
    if os.path.exists(dst) and os.path.getsize(dst) > 10_000:
        print(f"CACHE HIT  {dst}")
        return
    idx = load_index(bookpart_id)
    if page < 1 or page > len(idx):
        sys.exit(f"page {page} out of range 1..{len(idx)}")
    meta = load_meta(bookpart_id)
    url = idx[page - 1]["full_res_url"]
    referer = meta.get("volume_url", "https://agatha.arch.be/")
    tmp = dst + ".part"
    # Auto-refresh: reuse a valid cookie, re-login if the session is stale.
    curl(url, tmp, referer, cmd_ensure())
    os.rename(tmp, dst)
    print(f"DOWNLOADED {dst} ({os.path.getsize(dst)} bytes)")


def cmd_list(bookpart_id: str) -> None:
    meta = load_meta(bookpart_id)
    print(f"volume {bookpart_id}: {meta.get('title', '?')}  [{meta.get('date_range', '?')}]")
    idx = load_index(bookpart_id)
    cached = set()
    pdir = os.path.join(vol_dir(bookpart_id), "pages")
    if os.path.isdir(pdir):
        cached = {int(f[:3]) for f in os.listdir(pdir) if f[:3].isdigit()}
    print(f"{len(idx)} pages in index; {len(cached)} cached: {sorted(cached)}")


def cmd_init(bookpart_id: str, manifest_url: str, cookie: str, title: str,
             date_range: str, parish_id: str) -> None:
    vdir = vol_dir(bookpart_id)
    os.makedirs(os.path.join(vdir, "pages"), exist_ok=True)
    referer = f"https://agatha.arch.be/en/search/genealogie/{bookpart_id}"
    mpath = os.path.join(vdir, "manifest.json")
    curl(manifest_url, mpath, referer, cookie)
    d = json.load(open(mpath))
    canv = d["sequences"][0]["canvases"]
    idx = []
    for i, c in enumerate(canv, 1):
        res = c["images"][0]["resource"]
        idx.append({
            "page": i,
            "label": c["label"].get("@value") if isinstance(c.get("label"), dict) else c.get("label"),
            "full_res_url": res["@id"],
            "jp2_service": res["service"]["@id"],
        })
    json.dump(idx, open(os.path.join(vdir, "index.json"), "w"), indent=1)
    meta = {
        "bookpart_id": bookpart_id,
        "parish_id": parish_id,
        "title": title,
        "date_range": date_range,
        "volume_url": referer,
        "manifest_url": manifest_url,
        "n_pages": len(idx),
        "seeded": "see git/file mtime",
    }
    json.dump(meta, open(os.path.join(vdir, "meta.json"), "w"), indent=1)
    print(f"initialized volume {bookpart_id}: {len(idx)} pages")


def cmd_crop(bookpart_id: str, page: int, box: str, name: str) -> None:
    from PIL import Image
    src = page_path(bookpart_id, page)
    if not os.path.exists(src):
        sys.exit(f"source page missing — 'get {bookpart_id} {page}' first")
    x, y, w, h = [int(v) for v in box.split(",")]
    im = Image.open(src).crop((x, y, x + w, y + h))
    dst = os.path.join(CACHE, "crops", str(bookpart_id), f"{int(page):03d}_{name}.png")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    im.save(dst)
    print(f"CROP {dst} ({im.size[0]}x{im.size[1]})")


def _dir_size(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            if os.path.isfile(fp):
                total += os.path.getsize(fp)
    return total


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024


def cmd_du() -> None:
    vol = os.path.join(CACHE, "volumes")
    pages = 0
    ocr = 0
    for v in os.listdir(vol):
        if not os.path.isdir(os.path.join(vol, v)):
            continue
        for f in os.listdir(os.path.join(vol, v, "pages")):
            fp = os.path.join(vol, v, "pages", f)
            if os.path.isfile(fp):
                if f.endswith(".ocr.txt"):
                    ocr += os.path.getsize(fp)
                else:
                    pages += os.path.getsize(fp)
    meta = _dir_size(vol) - pages - ocr  # manifest/index/meta json
    crops = _dir_size(os.path.join(CACHE, "crops"))
    lookup = _dir_size(os.path.join(CACHE, "lookup"))
    print(f"full-res pages : {_human(pages)}")
    print(f"ocr outputs    : {_human(ocr)}  (derived, regenerable — clean --ocr)")
    print(f"volume metadata: {_human(meta)}")
    print(f"crops          : {_human(crops)}")
    print(f"lookup         : {_human(lookup)}")
    total = _dir_size(CACHE)
    print(f"TOTAL          : {_human(total)}")


def cmd_clean(volume: str, ocr_only: bool = False) -> None:
    """Drop crops (default: all; or one volume), or — with ocr_only — only
    OCR outputs (.ocr.txt). Full-res pages are always kept: crops can be
    re-cropped, OCR regenerated via the kraken-ocr skill.
    Never touches pages/*.jpg, index or meta."""
    if ocr_only:
        # Walk volume pages/ dirs and drop .ocr.txt only.
        base = os.path.join(CACHE, "volumes")
        if volume:
            targets = [os.path.join(base, volume, "pages")]
        else:
            targets = [os.path.join(base, d, "pages")
                       for d in sorted(os.listdir(base))
                       if os.path.isdir(os.path.join(base, d))]
        freed, nfiles = 0, 0
        for t in targets:
            if not os.path.isdir(t):
                continue
            for f in sorted(os.listdir(t)):
                if not f.endswith(".ocr.txt"):
                    continue
                fp = os.path.join(t, f)
                freed += os.path.getsize(fp)
                os.unlink(fp)
                nfiles += 1
        print(f"removed {nfiles} OCR files, freed {_human(freed)} "
              f"— full-res pages kept (regenerate via kraken-ocr)")
        return
    # Crop mode (original behaviour)
    base = os.path.join(CACHE, "crops")
    if volume:
        targets = [os.path.join(base, volume)]
    else:
        targets = [os.path.join(base, d) for d in sorted(os.listdir(base))] \
            if os.path.isdir(base) else []
    freed, nfiles = 0, 0
    for t in targets:
        if not os.path.isdir(t):
            continue
        for root, _dirs, files in os.walk(t):
            for f in files:
                fp = os.path.join(root, f)
                freed += os.path.getsize(fp)
                os.unlink(fp)
                nfiles += 1
    if os.path.isdir(base):
        for d in os.listdir(base):
            p = os.path.join(base, d)
            if os.path.isdir(p) and not os.listdir(p):
                os.rmdir(p)
    print(f"removed {nfiles} crop files, freed {_human(freed)} — full-res pages kept")


if __name__ == "__main__":
    # crop needs PIL: re-exec under the workspace venv if the current
    # interpreter lacks it (uv-managed venv at /workspace/.venv)
    if sys.argv[1:2] == ["crop"]:
        try:
            import PIL  # noqa: F401
        except ImportError:
            venv_py = "/workspace/.venv/bin/python"
            if os.path.exists(venv_py):
                os.execv(venv_py, [venv_py] + sys.argv)
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "get" and len(sys.argv) == 4:
        cmd_get(sys.argv[2], int(sys.argv[3]))
    elif cmd == "list" and len(sys.argv) == 3:
        cmd_list(sys.argv[2])
    elif cmd == "init" and len(sys.argv) == 8:
        cmd_init(sys.argv[2], sys.argv[3], sys.argv[4],
                 sys.argv[5], sys.argv[6], sys.argv[7])
    elif cmd == "crop" and len(sys.argv) == 6:
        cmd_crop(sys.argv[2], int(sys.argv[3]), sys.argv[4], sys.argv[5])
    elif cmd == "du" and len(sys.argv) == 2:
        cmd_du()
    elif cmd == "clean" and len(sys.argv) in (2, 3, 4):
        # clean [--ocr] [bookpart_id]
        ocr_only = "--ocr" in sys.argv[2:]
        vol_arg = [a for a in sys.argv[2:] if a != "--ocr"]
        cmd_clean(vol_arg[0] if vol_arg else "", ocr_only=ocr_only)
    elif cmd == "check" and len(sys.argv) == 2:
        cmd_check()
    elif cmd == "login" and len(sys.argv) == 2:
        do_login()
    elif cmd == "ensure" and len(sys.argv) == 2:
        cmd_ensure()
    else:
        print(__doc__)
        sys.exit(1)
