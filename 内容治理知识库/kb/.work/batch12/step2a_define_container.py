#!/usr/bin/env python3
"""§6.3-2「先定义后执行」：把「容器」判据写进配置。本步只改 registry，不碰任何数据。"""
import json, os, time
REG="kb/l0/registry/kb.json"
reg=json.load(open(REG,encoding="utf-8"))
assert "container_policy" not in reg, "container_policy 已存在，勿重复定义"
reg["container_policy"]={
 "defined_at":"20260924-1512",
 "defined_before_run":True,
 "purpose":("把「归哪个库」(kb_type) 与「要不要发射单元」(container) 解耦。"
            "此前发射器拿 kb_type 当发射开关用：unknown → R5 → 一个不产单元的 splitter。"
            "结果是分类一旦修真（走 rule_for 真求值），立刻会放出 101 个元数据角色的噪声单元。"),
 "criteria":[
   {"id":"C1","statement":"该资源在 L1 抽出的**全部** segment 都是元数据（每段的字段角色 role != 'content'）",
    "check":"读 kb/l1/<kb_type>/<resource_id>.json 的 segments[]，对每段取 field_name，"
            "按 field_role_resolution 解析角色，断言集合内无 'content'",
    "why":"只要有任意一段是可引用正文，它就不是纯容器"},
   {"id":"C2","statement":"该资源在 L0 链接图里**有子资源**（存在 from_id 指向它的 depth+1 边）",
    "check":"读 kb/l0/links/graph.jsonl，存在 from_id ∈ {record:<record_id>, <resource_key>} 的边",
    "why":"「容器」的语义是「它的内容归属落在子资源上」；没有子资源就没有归属对象，不构成容器"},
   {"id":"C3","statement":"候选容器**当前不发射任何 L2 单元**（否则打标会误删既有单元）",
    "check":"该 resource_id 在 kb/l2/index/l2.jsonl 中的单元数 == 0",
    "why":"这是**安全阀**：容器标记只能「不新增」，绝不能「删既有」。若某资源已有单元却被判为容器，"
          "说明 C1/C2 的口径有问题，闸门必须拦下（计入 deletions_risk）"}
 ],
 "resolution_order":"全部 C1 ∧ C2 ∧ C3 同时成立才判 container=true；任一不成立即 non-container",
 "effect":("container=true → **不发射 L2 单元**（发射层跳过），但 kb_type **仍按 rules 真求值**落到对应库目录。"
           "即：归属与发射彻底分开。"),
 "not_used":["表名 == 材料收集（禁止硬编码表名）","kb_type == unknown（禁止再用 kb_type 当发射开关）"],
 "forbidden":["不得用中文目录名做判断，一律查 dir_map / dir_map_reverse",
              "不得用 kb_type 决定是否发射单元"],
 "evaluated_by":"kb/.work/batch12/step2b_container_shadow.py",
 "gate":"完整修法（真求值 + 容器不发射）重跑影子，预期新增 L2 单元 == 0，且 deletions_risk == 0"}
reg["changes"].append({"run_id":"20260924-1512","change":"append","keys":["container_policy"],
  "note":"§6.3-2 先定义后执行：容器判据 C1/C2/C3 先落配置，再跑影子与改判。"})
t=REG+".tmp"
with open(t,"w",encoding="utf-8") as fh: json.dump(reg,fh,ensure_ascii=False,indent=1)
json.load(open(t,encoding="utf-8")); os.replace(t,REG)
d=json.load(open(REG,encoding="utf-8"))
print("container_policy 已写入（顶层键 %d → %d）"%(len(reg)-1,len(d)))
print(json.dumps(d["container_policy"]["criteria"],ensure_ascii=False,indent=1))
