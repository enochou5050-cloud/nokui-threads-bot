"""예약된 쓰레드 글을 메타 공식 Threads API로 올린다.
posts/*.json 중 시간이 지났고 아직 안 올린 글을 올리고 posted.json에 기록한다."""
import json, os, glob, time, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta

API = "https://graph.threads.net/v1.0"
TOKEN = os.environ["THREADS_TOKEN"]
REPO = os.environ["GITHUB_REPOSITORY"]
BRANCH = os.environ.get("GITHUB_REF_NAME", "main")
KST = timezone(timedelta(hours=9))
RAW = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/images/"

def call(path, params, method="POST"):
    params = {**params, "access_token": TOKEN}
    data = urllib.parse.urlencode(params).encode()
    url = f"{API}/{path}"
    req = urllib.request.Request(url, data=data, method="POST") if method == "POST" \
        else urllib.request.Request(url + "?" + data.decode())
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{path}: {e.code} {e.read().decode()[:500]}")

def wait_ready(cid):
    for _ in range(60):
        s = call(cid, {"fields": "status,error_message"}, "GET")
        if s.get("status") == "FINISHED":
            return
        if s.get("status") == "ERROR":
            raise RuntimeError(f"container {cid}: {s.get('error_message')}")
        time.sleep(5)
    raise RuntimeError(f"container {cid}: timeout")

CFG = json.load(open("config.json", encoding="utf-8")) if os.path.exists("config.json") else {}

def clean(t):
    """마크다운 기호(**, __, `, #) 제거"""
    import re
    t = t.replace("**", "").replace("__", "").replace("`", "")
    t = re.sub(r"(?m)^\s*#+\s*", "", t)
    return t.strip()

def with_link(reply):
    link = CFG.get("buy_link")
    if link and link not in reply:
        reply = reply.rstrip() + "\n\n" + CFG.get("buy_line", "구매 링크 👇") + "\n" + link
    return reply

def is_video(name):
    return name.lower().endswith((".mp4", ".mov"))

def media_params(name):
    url = RAW + urllib.parse.quote(name)
    return {"media_type": "VIDEO", "video_url": url} if is_video(name) else {"media_type": "IMAGE", "image_url": url}

def build(text, images, reply_to=None):
    """게시 전 컨테이너를 만들고 준비될 때까지 기다린다. 컨테이너 id 반환."""
    text = clean(text)
    base = {"reply_to_id": reply_to} if reply_to else {}
    if not images:
        cid = call("me/threads", {**base, "media_type": "TEXT", "text": text})["id"]
    elif len(images) == 1:
        cid = call("me/threads", {**base, **media_params(images[0]), "text": text})["id"]
    else:
        kids = []
        for n in images:
            k = call("me/threads", {**media_params(n), "is_carousel_item": "true"})["id"]
            wait_ready(k); kids.append(k)
        cid = call("me/threads", {**base, "media_type": "CAROUSEL", "children": ",".join(kids), "text": text})["id"]
    wait_ready(cid)
    return cid

def publish(text, images, reply_to=None):
    cid = build(text, images, reply_to)
    return call("me/threads_publish", {"creation_id": cid})["id"]

def main():
    check = os.environ.get("CHECK_ONLY", "").strip()
    if check:  # 게시하지 않고 사진·영상을 쓰레드가 받아가는지만 확인
        names = [n.strip() for n in check.split(",") if n.strip()]
        build("확인용", names)
        print("확인 완료(게시 안 함):", names)
        return
    done = json.load(open("posted.json")) if os.path.exists("posted.json") else {}
    now = datetime.now(KST)
    errors = []
    for f in sorted(glob.glob("posts/*.json")):
        key = os.path.basename(f)
        if key in done:
            continue
        p = json.load(open(f, encoding="utf-8"))
        when = datetime.fromisoformat(p["time"]).replace(tzinfo=KST)
        if when > now or now - when > timedelta(hours=12):
            continue  # 아직 시간이 안 됐거나 너무 지난 글은 건너뜀
        try:
            pid = publish(p["text"], p.get("images", []))
            rid = None
            reply = with_link(clean(p.get("reply", "")))
            if reply:
                time.sleep(10)
                rid = publish(reply, [], reply_to=pid)
            done[key] = {"post": pid, "reply": rid, "at": now.isoformat()}
            print("올림:", key, pid)
        except Exception as e:
            errors.append(f"{key}: {e}")
            print("실패:", key, e)
    json.dump(done, open("posted.json", "w"), ensure_ascii=False, indent=1)
    if errors:
        raise SystemExit("\n".join(errors))

if __name__ == "__main__":
    main()
