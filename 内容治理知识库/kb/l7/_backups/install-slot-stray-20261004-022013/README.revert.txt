回滚说明 ｜ install-slot-stray-20261004-022013
================================================
动作：把装位里多出来的 doctor 巡检产物移出装载位（回滚基线 = 本目录）
执行时刻：2026-10-04 02:20:13 CST
执行者：kb-repair（会话内 agent）

背景
----
登记表 kb/l7/registry/skills.yaml 头部的 single_writer_rule 写明：
  装载位 ~/.dsh/skills/<id>/ 是【只读运行副本】，任何写入者都不得直接改装载位里的文件。
但 root-skills-doctor 的 skill-doctor.py:1136 把报告写死在 <target>/.doctor-backup/，
把 target 指向装载位时就会往只读副本里写文件（本次 target = ~/.dsh/skills/kb-check）。
同一形态 2026-10-04 00:23:39 出现过一次（已由上一次清理移到
kb/l7/_backups/install-slot-stray-20261004-013655/）；01:47:50 又跑了一次 doctor，
于是 02:20 复查时再次出现 —— 这是第 2 次复发。

为什么官方闸门看不见
--------------------
l7/scripts/skills_check.py:791 的 walk_files() 执行
  dirs[:] = [x for x in dirs if not x.startswith(".")]
即 `.` 开头的目录被整体剪掉。`.doctor-backup` 因此对第 3 类"副本不一致"不存在
—— 那不是"核过且一致"，是"没核"。

本次移动了哪些文件（1 个）
--------------------------
install-slot-kb-check/.doctor-backup/doctor-report-20261004-014750.md
  sha256（移动前后一致）= 329bae486af8a0e6d1009d3450c9dfd98cb8e3f3417aa8cd53bf3110aaff32df
  内容 = root-skills-doctor 的 DRY-RUN 报告（4 项"将要生成"，未真正落盘修复）

未做的事
--------
未改 kb/l0…l6 任何数据与台账；未改 kb/l7/registry/skills.yaml 以外的库内文件；
未改闸门判据（walk_files 是否该停止剪点目录，属判据改动，待裁）。

回滚（一行）
------------
mv "kb/l7/_backups/install-slot-stray-20261004-022013/install-slot-kb-check/.doctor-backup" "$HOME/.dsh/skills/kb-check/.doctor-backup"
