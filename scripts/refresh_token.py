"""60일짜리 토큰을 연장해서 출력한다 (워크플로가 GitHub 비밀값을 갱신)."""
import json, os, urllib.request, urllib.parse
q = urllib.parse.urlencode({"grant_type": "th_refresh_token", "access_token": os.environ["THREADS_TOKEN"]})
with urllib.request.urlopen("https://graph.threads.net/refresh_access_token?" + q, timeout=60) as r:
    print(json.load(r)["access_token"])
