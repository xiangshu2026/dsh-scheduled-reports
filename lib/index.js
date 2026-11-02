// DSH 定时报告 · 无人值守报告生成与归档
// https://github.com/xiangshu2026/dsh-scheduled-reports
/**
 * DSH 插件入口：把 sentinel 的「副作用检查」能力注册成工具。
 *
 * 设计原则（来自 sentinel.mjs）：
 *   不看任务返回值，看副作用——文件真的生成了、时间戳真的新了，才算干了活。
 *   退出码 0 但什么都没产出，是最难发现的失败。
 *
 * 注册的工具：
 *   report_health   检查报告新鲜度 / 审计账本 / 日志增长，返回结构化结果
 */
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

export const name = 'scheduled-reports';
export const inject = ['tools'];

const HOUR = 3600 * 1000;
const DAY = 24 * HOUR;

function homeOf(config) {
  return config?.home || os.homedir();
}

function reportsDirOf(config) {
  return config?.reportsDir || process.env.SENT_REPORTS || path.join(homeOf(config), 'Desktop', 'DSH-Reports');
}

function guardDirOf(config) {
  return config?.guardDir || process.env.SENT_GUARD || path.join(homeOf(config), '.dsh', 'alpha-guard');
}

function logsDirOf(config) {
  return config?.logsDir || process.env.SENT_LOGS || path.join(homeOf(config), '.dsh', 'scheduled', 'logs');
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

/**
 * 跑一次完整健康检查。
 * @returns {{ items: Array, worst: 'ok'|'warn'|'error' }}
 */
export function checkHealth(config = {}) {
  const REPORTS = reportsDirOf(config);
  const GUARD_DIR = guardDirOf(config);
  const LOGS = logsDirOf(config);
  const MAX_DAYS = Number(config.maxReportDays ?? process.env.SENT_REPORT_MAX_DAYS ?? 7);
  const EXPECT_PER_RUN = Number(config.expectPerRun ?? process.env.SENT_REPORT_EXPECT ?? 4);

  const items = [];
  const push = (item, level, ok, detail) => items.push({ item, level, ok, detail });

  // 1. 每日报告新鲜度 + 完整性
  let latest = null;
  try {
    const dirs = fs.readdirSync(REPORTS, { withFileTypes: true })
      .filter((d) => d.isDirectory() && /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(d.name))
      .map((d) => d.name)
      .sort();
    if (dirs.length) latest = dirs[dirs.length - 1];
  } catch { /* 目录不存在 */ }

  if (!latest) {
    push('每日报告', 'warn', false, '找不到任何报告目录：' + REPORTS);
  } else {
    const dir = path.join(REPORTS, latest);
    let files = [];
    try { files = fs.readdirSync(dir).filter((f) => f.endsWith('.docx')); } catch {}
    const age = ageMs(dir);
    const days = age === null ? 999 : age / DAY;
    const fresh = days <= MAX_DAYS;
    const enough = files.length >= EXPECT_PER_RUN;
    const kinds = new Set(files.map((f) => f.replace(/-[0-9]{4}-[0-9]{2}-[0-9]{2}.*$/, '')));
    const varied = kinds.size >= 2;
    const ok = fresh && enough && varied;
    const lvl = !fresh && days > MAX_DAYS * 2 ? 'error' : 'warn';
    const issues = [];
    if (!fresh) issues.push('超过 ' + MAX_DAYS + ' 天阈值');
    if (!enough) issues.push('只有 ' + files.length + '/' + EXPECT_PER_RUN + ' 份');
    if (!varied) issues.push('类别单一(' + [...kinds].join(',') + ')');
    push('每日报告', ok ? 'ok' : lvl, ok,
      '最新 ' + latest + ' · ' + files.length + ' 份 · ' + fmtAge(age) +
      (ok ? '' : '（' + issues.join('；') + '）'));
  }

  // 2. 审计账本
  {
    const led = path.join(GUARD_DIR, 'audit-ledger.json');
    if (!fs.existsSync(led)) {
      push('审计账本', 'warn', false, '账本不存在（alpha-guard 未启用则忽略此项）');
    } else {
      let data = null;
      try { data = JSON.parse(fs.readFileSync(led, 'utf8')); } catch {}
      if (!data) {
        push('审计账本', 'error', false, '账本文件损坏');
      } else {
        const lastSync = data.lastSync ? new Date(data.lastSync).getTime() : null;
        const syncAge = lastSync ? Date.now() - lastSync : null;
        const stale = syncAge === null || syncAge > 7 * DAY;
        push('审计账本', stale ? 'warn' : 'ok', !stale,
          '登记 ' + (data.count ?? 0) + ' 行 · 最后同步 ' + (lastSync ? fmtAge(syncAge) : '从未') +
          (stale ? '（建议跑 audit-ledger --sync）' : ''));
      }
    }
  }

  // 3. 审计日志在增长
  {
    const audit = path.join(GUARD_DIR, 'audit.jsonl');
    const age = ageMs(audit);
    if (age === null) {
      push('审计日志', 'warn', false, 'audit.jsonl 不存在（alpha-guard 未启用则忽略此项）');
    } else {
      const ok = age < 7 * DAY;
      push('审计日志', ok ? 'ok' : 'warn', ok, '最后写入 ' + fmtAge(age));
    }
  }

  // 4. 定时日志新鲜度
  {
    let latestLog = null;
    try {
      const files = fs.readdirSync(LOGS)
        .filter((f) => f.endsWith('.log'))
        .map((f) => ({ name: f, mtime: fs.statSync(path.join(LOGS, f)).mtimeMs }))
        .sort((a, b) => b.mtime - a.mtime);
      if (files.length) latestLog = files[0];
    } catch { /* 目录不存在 */ }

    if (!latestLog) {
      push('定时日志', 'warn', false, '找不到任何日志：' + LOGS);
    } else {
      const age = Date.now() - latestLog.mtime;
      const ok = age < 8 * DAY;
      push('定时日志', ok ? 'ok' : 'warn', ok, latestLog.name + ' · ' + fmtAge(age));
    }
  }

  const worst = items.some((i) => i.level === 'error') ? 'error'
    : items.some((i) => !i.ok) ? 'warn' : 'ok';
  return { items, worst };
}


// ─────────────────────────────────────────────────────────────
// 工具注册（2026-11-02 修：原先误用 ctx.tools.guard 注册，guard 只接受
// ToolGuard 函数 (execution) => string | undefined，传字符串会被 append 进 guard 层，
// 每次工具调用执行 guard(exec) 时 TypeError；且工具本身从未真正注册，模型看不见。
// 正确做法：ctx.tools.register({ name, description, parameters, output, execute })。
// ─────────────────────────────────────────────────────────────

/** report_health 的入参：全部可选，用于覆盖 config 里的默认路径与阈值。 */
const REPORT_HEALTH_PARAMETERS = {
  type: 'object',
  additionalProperties: false,
  properties: {
    home: { type: 'string', description: '用户主目录覆盖（缺省 os.homedir()）' },
    reportsDir: { type: 'string', description: '报告根目录（缺省 ~/Desktop/DSH-Reports，可用环境变量 SENT_REPORTS 覆盖）' },
    guardDir: { type: 'string', description: 'alpha-guard 目录（缺省 ~/.dsh/alpha-guard，可用 SENT_GUARD 覆盖）' },
    logsDir: { type: 'string', description: '定时任务日志目录（缺省 ~/.dsh/scheduled/logs，可用 SENT_LOGS 覆盖）' },
    maxReportDays: { type: 'number', description: '报告过期阈值（天，缺省 7）' },
    expectPerRun: { type: 'number', description: '每轮期望生成的报告份数（缺省 4）' },
  },
  required: [],
};

/** report_health 的返回结构，与 execute 返回值严格一致。 */
const REPORT_HEALTH_OUTPUT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    worst: { type: 'string', enum: ['ok', 'warn', 'error'], description: '总体结论：ok=全绿，warn=有告警，error=有严重项' },
    ok: { type: 'boolean', description: 'worst === ok 的便捷布尔值' },
    items: {
      type: 'array',
      description: '逐项检查结果',
      items: {
        type: 'object',
        additionalProperties: false,
        properties: {
          item: { type: 'string', description: '检查项名称' },
          level: { type: 'string', enum: ['ok', 'warn', 'error'], description: '该项等级' },
          ok: { type: 'boolean', description: '该项是否通过' },
          detail: { type: 'string', description: '给人看的说明' },
        },
        required: ['item', 'level', 'ok', 'detail'],
      },
    },
  },
  required: ['worst', 'ok', 'items'],
};

/** 把 checkHealth 的结果渲染成给人看的多行文本。 */
function renderReportHealth(value) {
  const mark = { ok: 'OK  ', warn: 'WARN', error: 'ERR ' };
  const body = (value.items || []).map((i) => (mark[i.level] || 'WARN') + ' ' + i.item + '：' + i.detail);
  const head = '【报告健康检查】总体：' + String(value.worst || 'unknown').toUpperCase();
  return [{ type: 'text', text: [head].concat(body).join(String.fromCharCode(10)) }];
}

export function apply(ctx, config = {}) {
  const tools = ctx.get('tools');
  if (!tools) return;

  const tool = {
    name: 'report_health',
    description: '检查定时报告任务是否真的跑了：不看待退出码，看副作用——最新报告目录有多旧、里面有几份 docx、是否不止一个类别、alpha-guard 审计账本上次同步多久前、audit.jsonl 最后写入时间、定时任务日志是否新鲜。返回逐项结果与总体结论（ok/warn/error）。只读本地路径，不联网、不调模型、不产生副作用；路径与阈值可用参数覆盖。',
    parameters: REPORT_HEALTH_PARAMETERS,
    output: {
      schema: REPORT_HEALTH_OUTPUT_SCHEMA,
      render(_args, value) {
        return renderReportHealth(value);
      },
    },
    // 入参优先于 config：显式传的覆盖配置，没传的沿用 config 默认。
    execute: async (args) => {
      const { items, worst } = checkHealth({ ...config, ...(args || {}) });
      return { worst, ok: worst === 'ok', items };
    },
  };

  // register 返回 dispose；挂到 ctx.effect 上，插件卸载时自动注销。
  const dispose = ctx.effect(function () {
    return tools.register(tool);
  }, 'scheduled-reports: report_health tool');

  try {
    ctx.logger?.('scheduled-reports: report_health 已注册');
  } catch (e) { /* logger 可选 */ }
  return dispose;
}
