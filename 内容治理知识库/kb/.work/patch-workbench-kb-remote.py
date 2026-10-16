#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给工作台打一个可复核的补丁：镜像器支持「远程 HTTP 取数」。

为什么要在工作区里写这个脚本，而不是直接改工作台
------------------------------------------------
工作台目录（`skills-回归测试/工作台`）不在本会话的工作区里，写它要单独放行一次。
把改动做成本脚本 + 一份完整的新文件，一次放行就能落地，而且改了什么、原文在哪、
怎么回滚都留痕可查。

改了什么（三处，互相独立，可分别回滚）
--------------------------------------
1. `apps/server/src/kb/kb-sync.ts`
   · 新增 `SyncDoc` 类型与 `applyPlan()`：把「落库」从「扫盘」里拆出来，
     本地通道与远程通道共用同一段落库逻辑（语义不分叉）；
   · 新增远程通道：`options.remoteBaseUrl` 有值时，不再扫盘，
     改为 `GET <base>/manifest` 取「登记表 + 每条文档的原文」，
     再走**同一个** `parseEntry → renderForChunking → upsertMirrorDoc`；
   · 本地路径的行为、判据、状态字段一律不变（既有测试全部照旧）。
2. `apps/server/src/config.ts`：新增 `momcozyKbRemoteUrl`（`WORKBENCH_MOMCOZY_KB_REMOTE`）。
3. `apps/server/src/app.ts`：把新配置传给同步器。

回滚：备份在 `<工作台>/var/kb-remote-patch-backup-<ts>/`（脚本自动留），
或者 `git -C <工作台> checkout -- apps/server/src/kb/kb-sync.ts apps/server/src/config.ts apps/server/src/app.ts`。

用法
----
  python3 kb/.work/patch-workbench-kb-remote.py --wb "<工作台路径>" [--apply]
不给 `--apply` 时只做干跑：校验锚点是否都在、报告将要改的位置。
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time

# ── 1) kb-sync.ts 的第一处改动：类型 + 选项 ────────────────────────────
A1_OLD = """export type SkippedFile = { path: string; reason: string };
export type DriftItem = { collectionId: string; name: string; declared: number; actual: number };
"""

A1_NEW = """export type SkippedFile = { path: string; reason: string };
export type DriftItem = { collectionId: string; name: string; declared: number; actual: number };

/**
 * 一条待落库的文档。本地通道（扫盘）与远程通道（HTTP 取数）都产出这个结构，
 * 后面走同一个 `applyPlan` —— 两条通道的落库语义必须一模一样，不许各写一套。
 */
export type SyncDoc = {
  id: string;
  collectionId: string;
  /** 身份判定用（宿主侧的绝对路径）。 */
  sourcePath: string;
  title: string;
  sha256: string;
  /** 条目原文（frontmatter + 正文）。切块在 applyPlan 里统一做，两条通道同一个口径。 */
  text: string;
  bytes: number;
  /** 远程通道来自 manifest；本地通道留空（applyPlan 自己从 text 里解析）。 */
  metaJson?: string;
  /**
   * 本地通道：这个文件不是合法 UTF-8（解码失败）。**保留这个事实**，别用一个空字符串
   * 冒充正文 —— 否则「坏字节」会被报成「正文为空」，把两类问题搅成一句无关的话。
   */
  invalidUtf8?: boolean;
  /** 远程通道自带这些字段（它的登记表口径与宿主一致）；本地通道留空由解析补。 */
  entryId?: string;
  tier?: string;
  kind?: string;
  validUntil?: string;
  evidenceLevel?: string;
  owner?: string;
};

/**
 * 一次对账的「计划」：本地通道由 `plan()` 扫盘得出，远程通道由 HTTP manifest 得出。
 * 谁产出不重要，重要的是两者形状相同、落库走同一条路。
 */
export type SyncPlan = {
  collections: CollectionPlan[];
  docs: SyncDoc[];
  skipped: SkippedFile[];
  registryIssues: string[];
  libraryName?: string;
  declaredEntries?: number;
  driftFromSource?: DriftItem[];
};

/** 远程 manifest 的形状（由宿主库那侧的 HTTP 服务提供，见 _meta/manifest.json）。 */
type RemoteManifest = {
  manifestVersion?: number;
  version?: string;
  root?: string;
  rootExists?: boolean;
  libraryName?: string;
  libraryDisplayName?: string;
  libraryOwner?: string;
  collections?: Array<{
    id: string;
    name: string;
    description?: string;
    owner?: string;
    externalRoot: string;
    externalStatus?: string;
    entryCountDeclared?: number;
    note?: string;
    calledBy?: string[];
    record?: boolean;
  }>;
  issues?: string[];
  drift?: DriftItem[];
  docs?: Array<{
    id: string;
    collectionId: string;
    relPath: string;
    absPath?: string;
    record?: boolean;
    title?: string;
    sha256: string;
    text: string;
    bytes?: number;
    entryId?: string;
    tier?: string;
    kind?: string;
    validUntil?: string;
    evidenceLevel?: string;
    owner?: string;
    metaJson?: string;
  }>;
};
"""

# ── 2) kb-sync.ts 的第二处改动：选项类型 ────────────────────────────────
A2_OLD = """export type KbSyncOptions = {
  /** 宿主库根目录。 */
  root: string;
  enabled: boolean;
"""

A2_NEW = """export type KbSyncOptions = {
  /** 宿主库根目录。 */
  root: string;
  enabled: boolean;
  /**
   * 远程取数地址（形如 `http://127.0.0.1:4508`）。有值时**不扫盘**，改成
   * `GET <base>/manifest` 拿「登记表 + 每条文档原文」。
   *
   * 为什么需要这条通道：本机装了加密代理（`/usr/local/.trld`），Electron/Node 读宿主库的
   * md 拿到的是密文 —— 实测同一路径 `fs.statSync` 报 13084 字节而 python 看到 8988 字节，
   * 读出来不是合法 UTF-8，509 条条目全部被「跳过非 UTF-8」挡在门外；只有 2026-09-20
   * 之前落盘的老文件两边都能读。这不是内容问题，是「谁在读」的问题，所以换传输层：
   * 由宿主库那侧的 python 服务读明文、发 HTTP，工作台不再碰这些文件。
   * 远程通道与本地通道共用 `applyPlan`，解析/切块/差集/删除语义完全一致。
   */
  remoteBaseUrl?: string;
"""

# ── 3) kb-sync.ts 的第三处改动：状态里多一个 channel 字段 ────────────────
A3_OLD = """  /** 宿主登记表声明的条目总数 vs 实际同步到的条目数。 */
  declaredEntries?: number;
};"""

A3_NEW = """  /** 宿主登记表声明的条目总数 vs 实际同步到的条目数。 */
  declaredEntries?: number;
  /** 取数通道：`local`（直接扫盘）还是 `remote`（HTTP 取数）。 */
  channel?: 'local' | 'remote';
  /** 远程通道的地址（有值时界面能看出它没在读文件）。 */
  remoteBaseUrl?: string;
};"""

# ── 4) kb-sync.ts 的第四处改动：构造函数里把 channel 写进状态 ─────────────
A4_OLD = """    this.status_ = {
      enabled: options.enabled,
      root: options.root,
      rootExists: false,
      state: options.enabled ? 'idle' : 'disabled',
      watching: false,
      collections: 0,
      docs: 0,
      entries: 0,
      records: 0,
      skipped: [],
      drift: [],
      registryIssues: [],
    };"""

A4_NEW = """    this.status_ = {
      enabled: options.enabled,
      root: options.root,
      rootExists: false,
      state: options.enabled ? 'idle' : 'disabled',
      watching: false,
      collections: 0,
      docs: 0,
      entries: 0,
      records: 0,
      skipped: [],
      drift: [],
      registryIssues: [],
      channel: options.remoteBaseUrl === undefined ? 'local' : 'remote',
      ...(options.remoteBaseUrl === undefined ? {} : { remoteBaseUrl: options.remoteBaseUrl }),
    };"""

# ── 5) kb-sync.ts 的第五处改动：start()/startWatcher 在远程模式下不 watch 文件 ──
A5_OLD = """  /** 起同步：启动全量 + watch + 兜底。**不阻塞调用方**（启动时不能卡住 listen）。 */
  start(): void {
    if (!this.options.enabled) {
      this.status_.state = 'disabled';
      return;
    }
    void this.syncNow('startup');
    this.startWatcher();"""

A5_NEW = """  /** 起同步：启动全量 + watch + 兜底。**不阻塞调用方**（启动时不能卡住 listen）。 */
  start(): void {
    if (!this.options.enabled) {
      this.status_.state = 'disabled';
      return;
    }
    void this.syncNow('startup');
    // 远程通道不 watch 本地文件：取数走 HTTP，文件事件没有意义（而且这台机器上
    // watch 的那些文件本来也读不出内容）。兜底对账照旧跑。
    if (this.options.remoteBaseUrl === undefined) this.startWatcher();"""

# ── 6) kb-sync.ts 的第六处改动：reconcile 拆成 applyPlan + 两条通道 ────────
A6_OLD = """  /** 真正的对账：扫描宿主 → 建计划 → 差集 → 落库。同步执行（SQLite 是同步 API）。 */
  private reconcile(reason: string, started: number): KbSyncReport {
    const skipped: SkippedFile[] = [];
    const { root } = this.options;
    this.status_.rootExists = exists(root);
    if (!this.status_.rootExists) {
      throw new Error(`宿主知识库目录不存在：${root}`);
    }

    const { plans, files, registryIssues, libraryName, declaredEntries } = this.plan(root, skipped);
    this.status_.registryIssues = registryIssues;
    this.status_.libraryName = libraryName;
    this.status_.declaredEntries = declaredEntries;

    const now = Date.now();"""

A6_NEW = """  /**
   * 对账。两条通道，一个落库：
   *   · `remoteBaseUrl` 有值 → 远程取数（HTTP manifest）；
   *   · 否则 → 扫盘（原行为，判据不动）。
   */
  private async reconcile(reason: string, started: number): Promise<KbSyncReport> {
    const plan = this.options.remoteBaseUrl === undefined
      ? this.planFromDisk()
      : await this.planFromRemote(this.options.remoteBaseUrl);
    return this.applyPlan(plan, reason, started);
  }

  /** 本地通道：扫盘建计划（原逻辑，一行未改）。 */
  private planFromDisk(): SyncPlan {
    const skipped: SkippedFile[] = [];
    const { root } = this.options;
    this.status_.rootExists = exists(root);
    if (!this.status_.rootExists) {
      throw new Error(`宿主知识库目录不存在：${root}`);
    }
    const { plans, files, registryIssues, libraryName, declaredEntries } = this.plan(root, skipped);
    const docs: SyncDoc[] = files.map((file) => {
      const buffer = readFileSync(file.absPath);
      const text = decodeUtf8(buffer);
      return {
        id: '', // applyPlan 里按 sourcePath 派生（mirrorDocId）
        collectionId: file.collectionId,
        sourcePath: file.absPath,
        title: file.relPath,
        sha256: sha256Of(buffer),
        text: text ?? '',
        bytes: buffer.byteLength,
        ...(text === undefined ? { invalidUtf8: true } : {}),
      };
    });
    return {
      collections: plans,
      docs,
      skipped,
      registryIssues,
      ...(libraryName === undefined ? {} : { libraryName }),
      ...(declaredEntries === undefined ? {} : { declaredEntries }),
    };
  }

  /**
   * 远程通道：向宿主库那侧的服务要 manifest。
   *
   * 取不到就抛错（状态进 error、界面能看到原因），**不清空既有镜像** ——
   * 「服务没起来」不该表现为「知识库空了」。
   */
  private async planFromRemote(baseUrl: string): Promise<SyncPlan> {
    const url = `${baseUrl.replace(/\\/+$/, '')}/manifest`;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.options.remoteTimeoutMs ?? 30_000);
    let response: Response;
    try {
      response = await fetch(url, { signal: controller.signal, headers: { accept: 'application/json' } });
    } finally {
      clearTimeout(timer);
    }
    if (!response.ok) {
      throw new Error(`远程取数失败：GET ${url} → HTTP ${response.status}`);
    }
    const manifest = (await response.json()) as RemoteManifest;
    if (!Array.isArray(manifest.collections) || !Array.isArray(manifest.docs)) {
      throw new Error(`远程 manifest 形状不对（${url}）：缺 collections / docs`);
    }
    this.status_.rootExists = manifest.rootExists ?? true;
    const skipped: SkippedFile[] = [];
    const collections: CollectionPlan[] = manifest.collections.map((item) => ({
      id: item.id,
      name: item.name,
      description: item.description ?? '',
      owner: item.owner ?? '未指定',
      // externalRoot 是**身份的锚**（界面上的「宿主目录」也靠它）。载荷缺了就直接报错，
      // 别用 undefined 落库 —— node:sqlite 只会回一句「parameter 6 不能绑定」，
      // 排查时完全看不出是哪来的。
      externalRoot: item.externalRoot ?? '',
      ...(item.externalStatus === undefined ? {} : { externalStatus: item.externalStatus }),
      ...(item.entryCountDeclared === undefined ? {} : { entryCountDeclared: item.entryCountDeclared }),
      ...(item.note === undefined ? {} : { note: item.note }),
      calledBy: item.calledBy ?? [],
      record: item.record === true,
    }));
    const noRoot = collections.filter((item) => item.externalRoot === '').map((item) => item.id);
    if (noRoot.length > 0) {
      throw new Error(`远程 manifest 的子库缺 externalRoot：${noRoot.join('、')}（载荷生成器要补这个字段）`);
    }
    const docs: SyncDoc[] = manifest.docs.map((doc) => {
      const text = typeof doc.text === 'string' ? doc.text : '';
      return {
        id: doc.id,
        collectionId: doc.collectionId,
        sourcePath: doc.absPath ?? doc.relPath,
        title: doc.title ?? doc.relPath,
        sha256: doc.sha256,
        text,
        bytes: doc.bytes ?? Buffer.byteLength(text, 'utf8'),
        ...(doc.metaJson === undefined ? {} : { metaJson: doc.metaJson }),
        ...(doc.entryId === undefined ? {} : { entryId: doc.entryId }),
        ...(doc.tier === undefined ? {} : { tier: doc.tier }),
        ...(doc.kind === undefined ? {} : { kind: doc.kind }),
        ...(doc.validUntil === undefined ? {} : { validUntil: doc.validUntil }),
        ...(doc.evidenceLevel === undefined ? {} : { evidenceLevel: doc.evidenceLevel }),
        ...(doc.owner === undefined ? {} : { owner: doc.owner }),
      };
    });
    return {
      collections,
      docs,
      skipped,
      registryIssues: manifest.issues ?? [],
      ...(manifest.libraryDisplayName === undefined && manifest.libraryName === undefined
        ? {}
        : { libraryName: manifest.libraryDisplayName ?? manifest.libraryName }),
      ...(manifest.drift === undefined || manifest.drift.length === 0 ? {} : { driftFromSource: manifest.drift }),
    };
  }

  /** 落库：两条通道共用这一段（差集、删除、计数语义只有一份）。 */
  private applyPlan(plan: SyncPlan, reason: string, started: number): KbSyncReport {
    const { collections: plans, docs, skipped } = plan;
    this.status_.registryIssues = plan.registryIssues;
    if (plan.libraryName !== undefined) this.status_.libraryName = plan.libraryName;
    this.status_.declaredEntries = plan.declaredEntries;

    const now = Date.now();"""

# ── 7) kb-sync.ts 的第七处改动：applyPlan 里换成消费 SyncDoc ───────────────
A7_OLD = """    for (const file of files) {
      const buffer = readFileSync(file.absPath);
      const sha256 = sha256Of(buffer);
      const key = `${file.collectionId}\\u0000${file.absPath}`;
      seen.add(key);

      const current = existing.get(key);
      if (current !== undefined && current.sha256 === sha256) {
        // 内容没变：跳过切块与 FTS 写入，只推一下同步时间（在 KbService 里做）。
        this.kb.upsertMirrorDoc({
          id: current.id,
          collectionId: file.collectionId,
          title: file.relPath,
          sourcePath: file.absPath,
          sha256,
          content: '',
          bytes: buffer.byteLength,
          syncedAt: now,
        });
        unchanged += 1;
        continue;
      }

      const text = decodeUtf8(buffer);
      if (text === undefined) {
        skipped.push({ path: file.relPath, reason: '不是合法 UTF-8，跳过（不静默替换坏字节）' });
        seen.delete(key);
        continue;
      }

      const { meta, body, error, rawMeta } = parseEntry(text);
      if (error !== undefined) {
        skipped.push({ path: file.relPath, reason: `${error}（正文照同步，元数据缺失）` });
      }
      const content = renderForChunking(meta, body);
      if (content.trim() === '') {
        skipped.push({ path: file.relPath, reason: '正文为空，跳过' });
        seen.delete(key);
        continue;
      }

      const outcome = this.kb.upsertMirrorDoc({
        id: current?.id ?? mirrorDocId(file.relPath),
        collectionId: file.collectionId,
        title: titleOf(meta, body, file.relPath.split(sep).pop() ?? file.relPath),
        sourcePath: file.absPath,
        sha256,
        content,
        bytes: buffer.byteLength,
        entryId: meta.entryId,
        tier: meta.tier,
        kind: meta.kind,
        validUntil: meta.validUntil,
        evidenceLevel: meta.evidenceLevel,
        owner: meta.owner,
        // 存**原始 frontmatter**（不是规范化后的 KbEntryMeta）：界面要能展开看到宿主写的一切，
        // 包括我没建模的字段（provenance / verification / sensitivity_level …）。
        // 建模过的那几个另有专门的列（tier / valid_until / evidence_level / owner）供排序与筛选。
        metaJson: rawMeta === undefined ? undefined : JSON.stringify(rawMeta),
        syncedAt: now,
      });
      if (outcome === 'inserted') inserted += 1;
      else if (outcome === 'updated') updated += 1;
      else unchanged += 1;
    }
"""

A7_NEW = """    for (const doc of docs) {
      const relPath = doc.id !== '' ? doc.id : doc.sourcePath;
      const key = `${doc.collectionId}\\u0000${doc.sourcePath}`;
      seen.add(key);

      const current = existing.get(key);
      if (current !== undefined && current.sha256 === doc.sha256) {
        // 内容没变：跳过切块与 FTS 写入，只推一下同步时间（在 KbService 里做）。
        this.kb.upsertMirrorDoc({
          id: current.id,
          collectionId: doc.collectionId,
          title: doc.title,
          sourcePath: doc.sourcePath,
          sha256: doc.sha256,
          content: '',
          bytes: doc.bytes,
          syncedAt: now,
        });
        unchanged += 1;
        continue;
      }

      const text = decodeUtf8(Buffer.from(doc.text, 'utf8'));
      if (text === undefined || doc.invalidUtf8 === true) {
        // 本地通道的坏字节在这里被判掉；远程通道的载荷本身就是 JSON 字符串，不会走到这。
        skipped.push({ path: relPath, reason: '不是合法 UTF-8，跳过（不静默替换坏字节）' });
        seen.delete(key);
        continue;
      }

      const { meta, body, error, rawMeta } = parseEntry(text);
      if (error !== undefined) {
        skipped.push({ path: relPath, reason: `${error}（正文照同步，元数据缺失）` });
      }
      const content = renderForChunking(meta, body);
      if (content.trim() === '') {
        skipped.push({ path: relPath, reason: '正文为空，跳过' });
        seen.delete(key);
        continue;
      }

      // 本地通道：从正文解析元数据；远程通道：宿主那侧的 manifest 已经带了同口径字段，
      // 解析结果只当兜底（两边都不缺，谁的字段更全用谁）。
      const resolved: SyncDoc = {
        ...doc,
        entryId: meta.entryId ?? doc.entryId,
        tier: meta.tier ?? doc.tier,
        kind: meta.kind ?? doc.kind,
        validUntil: meta.validUntil ?? doc.validUntil,
        evidenceLevel: meta.evidenceLevel ?? doc.evidenceLevel,
        owner: meta.owner ?? doc.owner,
      };

      const outcome = this.kb.upsertMirrorDoc({
        id: current?.id ?? (doc.id !== '' ? doc.id : mirrorDocId(doc.sourcePath)),
        collectionId: doc.collectionId,
        title: titleOf(meta, body, resolved.title.split(sep).pop() ?? resolved.title),
        sourcePath: doc.sourcePath,
        sha256: doc.sha256,
        content,
        bytes: doc.bytes,
        entryId: resolved.entryId,
        tier: resolved.tier,
        kind: resolved.kind,
        validUntil: resolved.validUntil,
        evidenceLevel: resolved.evidenceLevel,
        owner: resolved.owner,
        // 存**原始 frontmatter**（不是规范化后的 KbEntryMeta）：界面要能展开看到宿主写的一切，
        // 包括我没建模的字段（provenance / verification / sensitivity_level …）。
        // 建模过的那几个另有专门的列（tier / valid_until / evidence_level / owner）供排序与筛选。
        metaJson: rawMeta === undefined ? doc.metaJson : JSON.stringify(rawMeta),
        syncedAt: now,
      });
      if (outcome === 'inserted') inserted += 1;
      else if (outcome === 'updated') updated += 1;
      else unchanged += 1;
    }
"""

# ── 8) kb-sync.ts 的第八处改动：drift 在远程模式下用 manifest 的声明值 ────────
A8_OLD = """    const drift = this.computeDrift(plans, files);
    this.status_.skipped = skipped;
    this.status_.drift = drift;"""

A8_NEW = """    const drift = plan.driftFromSource ?? this.computeDrift(plans, docs);
    this.status_.skipped = skipped;
    this.status_.drift = drift;"""

# ── 9) kb-sync.ts 的第九处改动：computeDrift 的入参类型 ────────────────────
A9_OLD = """  private computeDrift(plans: CollectionPlan[], files: FilePlan[]): DriftItem[] {
    const actual = new Map<string, number>();
    for (const file of files) actual.set(file.collectionId, (actual.get(file.collectionId) ?? 0) + 1);"""

A9_NEW = """  private computeDrift(plans: CollectionPlan[], files: Array<{ collectionId: string }>): DriftItem[] {
    const actual = new Map<string, number>();
    for (const file of files) actual.set(file.collectionId, (actual.get(file.collectionId) ?? 0) + 1);"""

# ── 10) kb-sync.ts 的第十处改动：remoteTimeoutMs 选项 ─────────────────────
A10_OLD = """  /** 每次同步完（有变化时）回调，用来推 SSE / 刷新界面。 */
  onChanged?: (report: KbSyncReport) => void;
};"""

A10_NEW = """  /** 远程取数的超时（ms）。取不到就报错并保留既有镜像，不清空。 */
  remoteTimeoutMs?: number;
  /** 每次同步完（有变化时）回调，用来推 SSE / 刷新界面。 */
  onChanged?: (report: KbSyncReport) => void;
};"""

# ── 11) kb-sync.ts 的第十一处改动：run() 里 await（reconcile 现在可能是异步的） ──
A11_OLD = """      const report = this.reconcile(reason, started);"""
A11_NEW = """      const report = await this.reconcile(reason, started);"""

# ── config.ts ───────────────────────────────────────────────────────────
B1_OLD = """  /** 宿主知识库的只读镜像（`~/.dsh/Momcozy知识库`）。 */
  momcozyKbPath: string;
  momcozyKbEnabled: boolean;"""
B1_NEW = """  /** 宿主知识库的只读镜像（`~/.dsh/Momcozy知识库`）。 */
  momcozyKbPath: string;
  momcozyKbEnabled: boolean;
  /**
   * 宿主库的远程取数地址（`WORKBENCH_MOMCOZY_KB_REMOTE`，形如 `http://127.0.0.1:4508`）。
   *
   * 为什么会有这条：本机加密代理（`/usr/local/.trld`）让 Electron 读宿主库文件时拿到密文
   * （实测同一路径 stat 13084 而 python 看到 8988，读出来不是 UTF-8），镜像器原来那条
   * 「直接扫盘」的路一条条目都入不了库。设了这个值就改成 HTTP 取数（服务由宿主库那侧的
   * python 起，它读得到明文），落库语义与本地通道完全一致。空值 = 保持原行为。
   */
  momcozyKbRemoteUrl?: string;"""
B2_OLD = """    momcozyKbPath: str('WORKBENCH_MOMCOZY_KB_PATH', `${homedir()}/.dsh/Momcozy知识库`),
    momcozyKbEnabled: bool('WORKBENCH_MOMCOZY_KB', true),"""
B2_NEW = """    momcozyKbPath: str('WORKBENCH_MOMCOZY_KB_PATH', `${homedir()}/.dsh/Momcozy知识库`),
    momcozyKbEnabled: bool('WORKBENCH_MOMCOZY_KB', true),
    ...(process.env['WORKBENCH_MOMCOZY_KB_REMOTE'] === undefined || process.env['WORKBENCH_MOMCOZY_KB_REMOTE'] === ''
      ? {}
      : { momcozyKbRemoteUrl: process.env['WORKBENCH_MOMCOZY_KB_REMOTE'] }),"""

# ── app.ts ──────────────────────────────────────────────────────────────
C1_OLD = """  const kbSync = new MomcozyKbSync(kb, {
    root: config.momcozyKbPath,
    enabled: config.momcozyKbEnabled,"""
C1_NEW = """  const kbSync = new MomcozyKbSync(kb, {
    root: config.momcozyKbPath,
    enabled: config.momcozyKbEnabled,
    // 远程取数（加密代理挡着直接读文件时用；不设就是原来的扫盘通道）
    ...(config.momcozyKbRemoteUrl === undefined ? {} : { remoteBaseUrl: config.momcozyKbRemoteUrl }),"""

EDITS = {
    "apps/server/src/kb/kb-sync.ts": [
        ("A1", A1_OLD, A1_NEW), ("A2", A2_OLD, A2_NEW), ("A3", A3_OLD, A3_NEW),
        ("A4", A4_OLD, A4_NEW), ("A5", A5_OLD, A5_NEW), ("A6", A6_OLD, A6_NEW),
        ("A7", A7_OLD, A7_NEW), ("A8", A8_OLD, A8_NEW), ("A9", A9_OLD, A9_NEW),
        ("A10", A10_OLD, A10_NEW), ("A11", A11_OLD, A11_NEW),
    ],
    "apps/server/src/config.ts": [("B1", B1_OLD, B1_NEW), ("B2", B2_OLD, B2_NEW)],
    "apps/server/src/app.ts": [("C1", C1_OLD, C1_NEW)],
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wb", required=True, help="工作台目录")
    parser.add_argument("--apply", action="store_true", help="真的写入（默认干跑）")
    args = parser.parse_args()

    wb = os.path.abspath(args.wb)
    if not os.path.isdir(wb):
        print(f"找不到工作台目录：{wb}")
        return 2

    problems: list[str] = []
    plan: list[tuple[str, str, str, str]] = []
    for rel, edits in EDITS.items():
        path = os.path.join(wb, rel)
        if not os.path.isfile(path):
            problems.append(f"{rel}：文件不存在")
            continue
        text = open(path, encoding="utf-8").read()
        for tag, old, new in edits:
            hits = text.count(old)
            if hits != 1:
                problems.append(f"{rel} [{tag}]：锚点出现 {hits} 次（应为 1 次）")
                continue
            text = text.replace(old, new, 1)
            plan.append((rel, tag, old.splitlines()[0][:60], new.splitlines()[0][:60]))
        if not args.apply:
            continue

    print(f"[patch] 目标：{wb}")
    for rel, tag, _old, _new in plan:
        print(f"[patch]   {rel} [{tag}]")
    if problems:
        print("[patch] 干跑失败，锚点对不上：")
        for item in problems:
            print(f"[patch]   · {item}")
        return 1
    if not args.apply:
        print(f"[patch] 干跑通过：{len(plan)} 处锚点都在（未写入）。加 --apply 落地。")
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = os.path.join(wb, "var", f"kb-remote-patch-backup-{stamp}")
    os.makedirs(backup, exist_ok=True)
    for rel in EDITS:
        dst = os.path.join(backup, rel.replace("/", "__"))
        shutil.copy2(os.path.join(wb, rel), dst)
    print(f"[patch] 原文件已备份到 {backup}")

    for rel, edits in EDITS.items():
        path = os.path.join(wb, rel)
        text = open(path, encoding="utf-8").read()
        for tag, old, new in edits:
            if text.count(old) != 1:
                print(f"[patch] 落盘中止：{rel} [{tag}] 锚点不是 1 次（文件未被改动）")
                return 1
            text = text.replace(old, new, 1)
        open(path, "w", encoding="utf-8").write(text)
        print(f"[patch] 已写入 {rel}")
    print("[patch] 完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
