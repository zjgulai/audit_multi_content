# Feishu adapter contract

## Inbound

```json
{
  "event_id": "evt-1",
  "source": "feishu-group|feishu-bitable|url|file",
  "sender_id": "user-1",
  "message_id": "msg-1",
  "attachments": [],
  "fields": {
    "content_id": "AD-001",
    "content_version": "v1",
    "product_line": "吸奶器",
    "sku": "PUMP-001",
    "channel": "TikTok"
  }
}
```

## Outbound

Return the engine result, `chat_message`, `report_url`, `table_patch`, and `mentions`. Apply writes idempotently by `review_id` and content version. The local implementation is `../../core/feishu_adapter.py`; it emits role placeholders such as `{{role:legal}}` until Feishu member IDs and app credentials are configured.
