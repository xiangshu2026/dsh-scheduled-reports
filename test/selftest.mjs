// dsh-scheduled-reports · 插件入口契约自测
// 运行：node test/selftest.mjs
//
// 这一份测试是 2026-11-02 补的：此前 lib/index.js 把 tools.guard 当成
// 「按工具名注册」用，导致工具从未注册、且 guard 层每次调用都 TypeError。
// 下面五条断言就是那次事故的回归防线。
import assert from 'node:assert/strict';
import { apply, checkHealth } from '../lib/index.js';

let registered = null;
let disposed = false;

const fakeCtx = {
  get: (n) => (n === 'tools' ? { register: (t) => { registered = t; return () => { disposed = true; }; } } : null),
  effect: (fn) => fn(),
  logger: () => {},
};

apply(fakeCtx, {});

// 1. 真的注册了工具（不是往 guard 层塞字符串）
assert.ok(registered, 'apply() should call ctx.tools.register');
assert.equal(registered.name, 'report_health');
console.log('PASS register  report_health 已通过 ctx.tools.register 注册');

// 2. 定义完整：description / parameters / output.schema / execute
assert.equal(typeof registered.description, 'string');
assert.ok(registered.description.length > 20, 'description should be meaningful');
assert.equal(registered.parameters?.type, 'object');
assert.equal(registered.output?.schema?.type, 'object');
assert.equal(typeof registered.execute, 'function');
assert.equal(typeof registered.output.render, 'function');
console.log('PASS shape     description / parameters / output.schema / execute / render 齐全');

// 3. 真跑一次，返回值必须满足自己声明的 schema（required 全在、无多余字段）
const result = await registered.execute({});
const schema = registered.output.schema;
for (const key of schema.required) {
  assert.ok(key in result, 'missing required field: ' + key);
}
for (const key of Object.keys(result)) {
  assert.ok(key in schema.properties, 'unexpected field: ' + key);
}
assert.ok(['ok', 'warn', 'error'].includes(result.worst));
assert.equal(result.ok, result.worst === 'ok');
assert.ok(Array.isArray(result.items) && result.items.length > 0);
for (const item of result.items) {
  for (const key of ['item', 'level', 'ok', 'detail']) {
    assert.ok(key in item, 'item missing ' + key);
  }
  assert.ok(['ok', 'warn', 'error'].includes(item.level));
}
console.log('PASS schema    execute 返回值与 output.schema 严格一致（' + result.items.length + ' 项，worst=' + result.worst + '）');

// 4. render 产出可展示的文本，且不含 undefined
const rendered = registered.output.render({}, result);
assert.ok(Array.isArray(rendered) && rendered.length > 0);
assert.equal(rendered[0].type, 'text');
assert.ok(!rendered[0].text.includes('undefined'), 'render output should not contain undefined');
console.log('PASS render    输出 ' + rendered[0].text.split(String.fromCharCode(10)).length + ' 行文本');

// 5. 纯函数 checkHealth 可直接调用（不依赖 ctx）
const direct = checkHealth({});
assert.ok(direct.items.length > 0);
assert.ok(['ok', 'warn', 'error'].includes(direct.worst));
console.log('PASS pure      checkHealth() 可脱离 ctx 单独调用');

console.log(String.fromCharCode(10) + 'ALL SELFTESTS PASSED');
