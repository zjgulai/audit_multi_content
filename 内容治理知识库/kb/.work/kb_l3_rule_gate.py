#!/usr/bin/env python3
"""L3 写入幂等闸（件0）。规则类产出按 rule_id **覆盖**，不追加；同 run 内重复 rule_id 报错。"""
import json, os

class RuleIdempotencyGate:
    def __init__(self, path, run_id):
        self.path, self.run = path, run_id
        self.seen = {}
        self.rows = {}
        if os.path.exists(path):
            for line in open(path, encoding="utf-8"):
                if line.strip():
                    r = json.loads(line)
                    self.rows[r["rule_id"]] = r

    def put(self, row):
        k = row["rule_id"]
        if k in self.seen:
            raise ValueError(
                f"[E-DUP-RULE] run {self.run} 内 rule_id {k} 出现两次："
                f"第一次 {self.seen[k].get('form')} / 第二次 {row.get('form')}。"
                f"拒绝静默写两行（件0 幂等闸）。")
        self.seen[k] = row
        self.rows[k] = row          # 覆盖语义

    def flush(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            for k in sorted(self.rows):
                fh.write(json.dumps(self.rows[k], ensure_ascii=False, sort_keys=True) + "\n")
        return len(self.rows)
