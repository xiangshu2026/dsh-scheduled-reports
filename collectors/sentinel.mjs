#!/usr/bin/env node
// DSH 定时报告 · 无人值守报告生成与归档
// https://github.com/xiangshu2026/dsh-scheduled-reports
/**
 * sentinel.mjs —— 「退出码 0 但没干活」哨兵
 *
 * 来源：2026-10-31 从「大肥鱼记忆系统」修复记录学到的守卫模式。
 * 核心原则：不看任务返回值，看**副作用**。
 *   任务返回 0 不代表干了活；文件真的生成了、时间戳真的新了，才算干了活。
 *
 * 检查项：
 *   1. DSH 每日报告：最新报告目录距今是否超过阈值
 *   2. 审计账本：audit-ledger 是否 OK
 *   3. 审计日志：audit.jsonl 是否还在增长
 *   4. 关键日志：scheduled/logs 下最新日志距今多久
 *
 * 用法：
 *   node sentinel.mjs                 人读格式
 *   node sentinel.mjs --line          单行输出（给日志用）
 *   node sentinel.mjs --json          机器读
 * 退出码：0 = 全绿；1 = 有告警；2 = 有严重问题
 */
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

const HOME = os.homedir();
const REPORTS = process.env.SENT_REPORTS || path.join(HOME, 'Desktop', 'DSH-Reports');
const GUARD_DIR = process.env.SENT_GUARD || path.join(HOME, '.dsh', 'alpha-guard');
const LOGS = process.env.SENT_LOGS || path.join(HOME, '.dsh', 'scheduled', 'logs');

const HOUR = 3600 * 1000;
const DAY = 24 * HOUR;

const results = [];
function check(name, level, ok, detail) {
  results.push({ name, level, ok, detail });
}

function ageMs(p) {
  try { return Date.now() - fs.statSync(p).mtimeMs; } catch { return null; }
}

function fmtAge(ms) {
  if (ms === null) return '不存在';
  const h = ms / HOUR;
  if (h < 1) return Math.round(ms / 60000) + ' 分钟前';
  if (h < 48) return h.toFixed(1) + ' 小时前';
  return (ms / DAY).toFixed(1) + ' 天前';
}

// ── 1. DSH 每日报告 ───────────────────────────────────────────
// 计划任务每周一 09:00 跑。给 9 天余量（跨一个周末 + 1 天容错）。
const REPORT_MAX_DAYS = Number(process.env.SENT_REPORT_MAX_DAYS || 9);
{
  let latest = null;
  try {
    const dirs = fs.readdirSync(REPORTS, { withFileTypes: true })
      .filter((d) => d.isDirectory() && /^\d{4}-\d{2}-\d{2}$/.test(d.name))
      .map((d) => d.name).sort();
    if (dirs.length) latest = dirs[dirs.length - 1];
  } catch { /* 目录不存在 */ }

  // 一次完整运行应产出 4 份：电脑状况 / AI动态 / 时政 / token消耗
  const EXPECT_PER_RUN = Number(process.env.SENT_REPORT_EXPECT || 4);
  if (!latest) {
    check('每日报告', 'warn', false, '找不到任何报告目录：' + REPORTS);
  } else {
    const dir = path.join(REPORTS, latest);
    let files = [];
    try { files = fs.readdirSync(dir).filter((f) => f.endsWith('.docx')); } catch {}
    const age = ageMs(dir);
    const days = age === null ? 999 : age / DAY;

    // 三个条件都满足才算 OK：日期新鲜 + 份数够 + 不是只有「插件周报」这一类
    const fresh = days <= REPORT_MAX_DAYS;
    const enough = files.length >= EXPECT_PER_RUN;
    // 残缺检测：目录里只有单一类别（如全是「DSH插件周报」）说明只跑了部分任务
    const kinds = new Set(files.map((f) => f.replace(/-\d{4}-\d{2}-\d{2}.*$/, '')));
    const varied = kinds.size >= 2;

    const ok = fresh && enough && varied;
    const lvl = !fresh && days > REPORT_MAX_DAYS * 2 ? 'error' : 'warn';
    const issues = [];
    if (!fresh) issues.push('超过 ' + REPORT_MAX_DAYS + ' 天阈值');
    if (!enough) issues.push('只有 ' + files.length + '/' + EXPECT_PER_RUN + ' 份');
    if (!varied) issues.push('类别单一(' + [...kinds].join(',') + ')');
    // 只报事实，不猜原因。可能原因：任务没跑 / 被误删 / 部分任务失败 / 手动清理。
    check('每日报告', ok ? 'ok' : lvl, ok,
      '最新 ' + latest + ' · ' + files.length + ' 份 · ' + fmtAge(age) +
      (ok ? '' : '（' + issues.join('；') + '）'));
  }
}

// ── 2. 审计账本 ───────────────────────────────────────────────
{
  const led = path.join(GUARD_DIR, 'audit-ledger.json');
  if (!fs.existsSync(led)) {
    check('审计账本', 'warn', false, '账本不存在，先跑 audit-ledger.mjs --init');
  } else {
    let data = null;
    try { data = JSON.parse(fs.readFileSync(led, 'utf8')); } catch {}
    if (!data) {
      check('审计账本', 'error', false, '账本文件损坏');
    } else {
      const lastSync = data.lastSync ? new Date(data.lastSync).getTime() : null;
      const syncAge = lastSync ? Date.now() - lastSync : null;
      const stale = syncAge === null || syncAge > 7 * DAY;
      check('审计账本', stale ? 'warn' : 'ok', !stale,
        '登记 ' + data.count + ' 行 · 最后同步 ' + (lastSync ? fmtAge(syncAge) : '从未') +
        (stale ? '（建议跑 --sync）' : ''));
    }
  }
}

// ── 3. 审计日志在增长 ─────────────────────────────────────────
{
  const audit = path.join(GUARD_DIR, 'audit.jsonl');
  const age = ageMs(audit);
  if (age === null) {
    check('审计日志', 'error', false, 'audit.jsonl 不存在');
  } else {
    const ok = age < 7 * DAY;
    check('审计日志', ok ? 'ok' : 'warn', ok, '最后写入 ' + fmtAge(age));
  }
}

// ── 4. 定时日志新鲜度 ─────────────────────────────────────────
{
  let latest = null, latestName = '';
  try {
    const files = fs.readdirSync(LOGS).filter((f) => f.endsWith('.log'));
    for (const f of files) {
      const t = fs.statSync(path.join(LOGS, f)).mtimeMs;
      if (!latest || t > latest) { latest = t; latestName = f; }
    }
  } catch {}
  if (latest === null) {
    check('定时日志', 'warn', false, '找不到任何日志：' + LOGS);
  } else {
    const age = Date.now() - latest;
    const ok = age < 9 * DAY;
    check('定时日志', ok ? 'ok' : 'warn', ok, latestName + ' · ' + fmtAge(age));
  }
}

// ── 输出 ─────────────────────────────────────────────────────
const bad = results.filter((r) => !r.ok);
const errors = results.filter((r) => r.level === 'error');
const code = errors.length ? 2 : bad.length ? 1 : 0;

if (process.argv.includes('--json')) {
  console.log(JSON.stringify({ ts: new Date().toISOString(), code, results }, null, 1));
} else if (process.argv.includes('--line')) {
  const tag = (r) => (r.ok ? 'OK' : r.level === 'error' ? 'ERR' : 'WARN');
  console.log('[sentinel] ' + new Date().toISOString().slice(0, 10) + ' ' +
    results.map((r) => r.name + '=' + tag(r)).join(' ') +
    ' → ' + (code === 0 ? 'ALL_OK' : code === 1 ? 'WARN' : 'ERROR'));
} else {
  console.log('══════════════════════════════════════');
  console.log('哨兵体检  ' + new Date().toLocaleString('zh-CN'));
  console.log('══════════════════════════════════════');
  for (const r of results) {
    const mark = r.ok ? '✅' : r.level === 'error' ? '❌' : '⚠️ ';
    console.log(mark + ' ' + r.name.padEnd(8, '　') + ' ' + r.detail);
  }
  console.log('──────────────────────────────────────');
  console.log('结论  ' + (code === 0 ? '全绿' : code === 1 ? '有 ' + bad.length + ' 项告警' : '有 ' + errors.length + ' 项严重问题'));
  if (bad.length) {
    console.log('──────────────────────────────────────');
    console.log('常见原因（仅供排查，不是结论）：');
    console.log('  · 任务确实没跑起来 / 计划任务被禁用');
    console.log('  · 目录被误删或手动清理（历史上有过）');
    console.log('  · 部分子任务失败，只生成了部分报告');
    console.log('  · 机器当天没开机');
  }
  console.log('══════════════════════════════════════');
}

process.exit(code);
