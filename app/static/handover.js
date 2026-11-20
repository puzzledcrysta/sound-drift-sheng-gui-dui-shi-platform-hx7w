import {query, readInput, encodeInput} from './api.js';
import {el, table} from './table.js';

const byId = id => document.getElementById(id);
const settings = JSON.parse(byId('settings').textContent);
const grid = byId('grid-data');
const notice = byId('notice');
const live = byId('state');
const phase = byId('phase');
const reviewForm = byId('review');
const reviewNote = byId('review-note');
const decision = byId('decision');
const runId = byId('run-id');
const topExport = byId('export');
const filter = byId('filter');
const uploaded = new Map();
let report = null;
let reviewVersion = 0;

const isHandover = () => (location.hash.slice(1) || 'domain') === 'handover';

function say(message, bad = false) {
  notice.value = message;
  notice.classList.toggle('problem', bad);
}

function flag(code) {
  return el('span', settings.reasons[code] || code, code === 'MATCH' ? 'state' : 'state problem');
}

function trackTag(value) {
  return el('span', value, value === '主轨' ? 'state' : 'state problem');
}

function renderHandover() {
  phase.textContent = settings.tabs.handover;
  byId('input-title').textContent = '交接输入';
  document.querySelector('#source button[type=submit]').textContent = '生成剪辑交接清单';
  if (!report) {
    grid.replaceChildren(el('p', '运行交接样例或上传主/备轨来源', 'empty'));
    reviewForm.hidden = true;
    return;
  }
  const id = report.manifest.run_id;
  runId.textContent = id.slice(0, 9);
  runId.title = id;
  topExport.hidden = false;
  topExport.href = `/api/handover/${id}/export`;
  live.textContent = `交接批次 ${id.slice(0, 9)} · 换声 ${report.stats.switches} 次 · ${report.gate.confirmable ? '可确认' : '差异未核清'}`;
  renderKpis();
  renderItems();
  renderReview();
}

function renderKpis() {
  const values = {
    accepted: report.counts.handover_items,
    rejected: report.counts.quarantine,
    delta: report.book.delta,
    mismatched: report.book.mismatched,
    input: report.stats.switches,
  };
  for (const cell of document.querySelectorAll('[data-count]')) {
    cell.textContent = values[cell.dataset.count] ?? '—';
  }
  const labels = {accepted: '取用片段', rejected: '隔离', delta: '对账净差(毫秒)', mismatched: '账差(条)', input: '换声次数'};
  for (const cell of document.querySelectorAll('[data-count]')) {
    const small = cell.parentElement.querySelector('small');
    if (small && labels[cell.dataset.count]) small.textContent = labels[cell.dataset.count];
  }
}

function renderItems() {
  const columns = [
    ['校准起(毫秒)', 'start', 'num'],
    ['校准止(毫秒)', 'end', 'num'],
    ['时长(毫秒)', 'duration', 'num'],
    ['类型', row => el('span', row.kind, row.kind === '空档' ? 'state problem' : 'state')],
    ['轨道', row => (row.track ? trackTag(row.track) : el('span', '—'))],
    ['声轨片段', 'key'],
    ['来源行', 'line', 'num'],
    ['重叠', row => el('span', row.overlap ? '重叠留一路' : '独有', row.overlap ? 'state problem' : 'state')],
  ];
  const rows = [...report.items].sort((a, b) => Number(a.start) - Number(b.start));
  const term = filter.value.trim().toLocaleLowerCase();
  const shown = term
    ? rows.filter(row => [row.key, row.track, row.kind].some(v => String(v ?? '').toLocaleLowerCase().includes(term)))
    : rows;
  byId('shown').textContent = `${shown.length} / ${rows.length}（含空档 ${report.gaps.length}）`;
  table(grid, columns, shown);
  appendBookTable();
}

function appendBookTable() {
  document.querySelectorAll('.handover-extra').forEach(node => node.remove());
  const head = el('h2', '外部账对账（实际取用时长）');
  head.style.margin = '14px 11px 4px';
  const columns = [
    ['声轨片段', 'key'],
    ['轨道', row => trackTag(row.track)],
    ['实际取用', 'amount', 'num'],
    ['外部账', 'reference', 'num'],
    ['差值', 'delta', 'num'],
    ['外部行', 'book_line', 'num'],
    ['结论', row => flag(row.code)],
  ];
  const target = el('div');
  target.className = 'scroll';
  table(target, columns, report.book.rows);
  const gate = el('p', report.gate.confirmable
    ? `对账闭合，可确认交接；空档 ${report.gate.gap_count} 段共 ${report.gate.gap_total} 毫秒已标出。`
    : `差异未核清（${report.gate.blockers.map(c => settings.reasons[c] || c).join('、')}），不能确认交接。`,
    report.gate.confirmable ? 'state' : 'state problem');
  gate.style.margin = '8px 11px';
  for (const node of [head, target, gate]) node.classList.add('handover-extra');
  grid.after(head, target, gate);
}

async function renderReview() {
  const timeline = await query(`/api/handover/${report.manifest.run_id}/reviews`);
  reviewVersion = timeline[0]?.version || 0;
  reviewForm.hidden = false;
  const existing = document.querySelector('.handover-reviews');
  if (existing) existing.remove();
  if (timeline.length) {
    const box = el('div');
    box.className = 'handover-reviews';
    table(box, [['版本', 'version', 'num'], ['结论', 'decision'], ['意见', 'note'], ['登记 UTC', 'changed']], timeline);
    reviewForm.after(box);
  }
}

async function submit() {
  const payload = {};
  for (const [control, name] of [['source', 'data'], ['book', 'book']]) {
    const text = byId(`${control}-csv`).value;
    const original = uploaded.get(control);
    if (original && text === original.text) payload[`${name}_base64`] = encodeInput(original.bytes);
    else if (text.length || original) payload[name] = text;
  }
  report = await query('/api/handover', payload);
  document.querySelectorAll('.handover-extra').forEach(node => node.remove());
  say('交接清单已生成');
  renderHandover();
}

function wire() {
  document.querySelector('#source').addEventListener('submit', event => {
    if (!isHandover()) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    submit().catch(error => say(error.message, true));
  }, true);

  reviewForm.addEventListener('submit', event => {
    if (!isHandover()) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    query(`/api/handover/${report.manifest.run_id}/reviews`,
      {version: reviewVersion, decision: decision.value, note: reviewNote.value})
      .then(() => { say('复核已登记'); reviewNote.value = ''; renderReview(); })
      .catch(error => { say(error.message, true); if (error.status === 409) renderReview(); });
  }, true);

  byId('sample').addEventListener('click', event => {
    if (!isHandover()) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    Promise.all(['handover', 'handover_external'].map(name => fetch(`/api/samples/${name}`)))
      .then(async responses => {
        const files = await Promise.all(responses.map(r => r.arrayBuffer()));
        for (const [index, name] of ['source', 'book'].entries()) {
          const text = new TextDecoder('utf-8').decode(files[index]);
          byId(`${name}-csv`).value = text;
          uploaded.set(name, {text, bytes: files[index]});
        }
        document.querySelector('#source details').open = true;
        say('交接样例已载入');
      })
      .catch(error => say(error.message, true));
  }, true);

  for (const name of ['source', 'book']) {
    byId(`${name}-file`).addEventListener('change', async event => {
      if (!isHandover()) return;
      const file = event.target.files[0];
      if (!file) return;
      try {
        const [text, bytes] = await readInput(file);
        byId(`${name}-csv`).value = text;
        uploaded.set(name, {text, bytes});
        say(`已读取 ${file.name}`);
      } catch (error) {
        event.target.value = '';
        say(error.message, true);
      }
    });
  }

  filter.addEventListener('input', () => { if (isHandover() && report) renderItems(); });
}

function onHash() {
  document.querySelectorAll('.handover-extra,.handover-reviews').forEach(node => node.remove());
  if (isHandover()) {
    document.querySelectorAll('.rail nav a').forEach(a =>
      a.toggleAttribute('aria-current', a.dataset.module === 'handover'));
    renderHandover();
  } else if (report) {
    // 切回其它标签时还原 KPI 标签，交给主脚本重渲染。
    report = null;
    topExport.hidden = true;
  }
}

wire();
window.addEventListener('hashchange', onHash);
if (isHandover()) onHash();
