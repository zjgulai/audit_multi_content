---
source_url: https://momcozy-in.feishu.cn/wiki/Acl7w1Ax3iAY6GkW8rmcF5Bknkg
kind: wiki
title: 
fetched_at: 2026-10-10 16:46:21
sha256: eed44de4b0b142fd8678d5002f46012518398183a294c6824549002ae9f79ef4
bytes: 1088
run: spec-fix-20261010-1655
---

{
  "ok": false,
  "identity": "bot",
  "error": {
    "type": "authorization",
    "subtype": "permission_denied",
    "code": 131006,
    "message": "bot lacks permission for the requested resource",
    "hint": "check the resource owner has granted access to this bot\nThe current user or app/bot identity lacks access to the target wiki space or node. This is resource access, not app scope authorization. Do not retry the same request, reauthorize, or switch identity as trial and error; ask the resource owner or wiki administrator to grant read access, or use an accessible resource.",
    "log_id": "202610101646206977FF1C34DC985FF9E0",
    "troubleshooter": "排查建议查看(Troubleshooting suggestions): https://open.feishu.cn/search?from=openapi&log_id=202610101646206977FF1C34DC985FF9E0&code=131006&method_id=7673757597802990565",
    "identity": "bot"
  },
  "_notice": {
    "update": {
      "command": "lark-cli update",
      "current": "1.0.95",
      "latest": "1.0.97",
      "message": "lark-cli 1.0.97 available, current 1.0.95, run: lark-cli update"
    }
  }
}

