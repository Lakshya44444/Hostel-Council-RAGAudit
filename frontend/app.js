/**
 * app.js — DataForge Retrieval Integrity Auditor
 * Features: audit pipeline, animated gauge, heatmap, evidence filter+search,
 *           cell drawer, audit history, keyboard shortcuts, share link, provider detection
 */

'use strict';

// ── State ─────────────────────────────────────────────────────────────────────
const API = '';
let _result   = null;
let _files    = [];
let _kbLoaded = false;
let _pipeInterval = null;
let _allChunks = [];  // cache for evidence filter

// ── DOM shortcuts ─────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const qs = sel => document.querySelector(sel);

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  detectProvider();
  loadHistoryBadge();
  liveChunkCounter();
  setupDropZone();

  // Keyboard shortcuts
  document.addEventListener('keydown', e => {
    const mod = e.ctrlKey || e.metaKey;
    if (mod && e.key === 'Enter') { e.preventDefault(); runAudit(); }
    if (mod && e.key === 'd')    { e.preventDefault(); loadDemo(); }
    if (e.key === 'Escape')      { closeDrawer(); closeHistory(); }
  });

  // Restore from URL hash if present
  if (location.hash.startsWith('#result=')) restoreFromHash();
});

// ── Provider detection ────────────────────────────────────────────────────────
async function detectProvider() {
  try {
    const r = await fetch(`${API}/health`);
    if (r.ok) {
      const d = await r.json();
      if (d.kb_loaded) { setKbStatus(true, `${d.kb_chunks} chunks`); _kbLoaded = true; }
    }
  } catch (_) {}

  // Read from env hint (if backend exposes it) — fall back to env var name
  const providerEl = $('provider-label');
  const envProvider = 'fallback'; // default shown; backend could expose via /health
  providerEl.textContent = envProvider;
}

function setKbStatus(online, label) {
  const pill = $('kb-status-pill');
  const lbl  = $('kb-status-label');
  pill.classList.toggle('online', online);
  pill.classList.toggle('offline', !online);
  lbl.textContent = online ? `KB: ${label}` : 'No KB loaded';
}

// ── Drop zone ─────────────────────────────────────────────────────────────────
function setupDropZone() {
  const zone = $('drop-zone');
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('over');
    _files = Array.from(e.dataTransfer.files).filter(f => /\.(pdf|txt)$/i.test(f.name));
    renderFileChips();
    $('upload-btn').disabled = !_files.length;
  });
}

function handleFileSelect(e) {
  _files = Array.from(e.target.files);
  renderFileChips();
  $('upload-btn').disabled = !_files.length;
}

function renderFileChips() {
  const el = $('file-chips');
  el.innerHTML = _files.map(f => `
    <div class="file-chip-item">
      <svg width="11" height="11" viewBox="0 0 11 11" fill="none"><path d="M2 1h5.5L9 2.5V10H2V1z" stroke="currentColor" stroke-width="1.1" stroke-linejoin="round"/></svg>
      ${esc(f.name)} <span style="color:var(--text-4)">${fmtBytes(f.size)}</span>
    </div>`).join('');
}

// ── KB Upload ─────────────────────────────────────────────────────────────────
async function uploadKnowledgeBase() {
  if (!_files.length) { toast('Select at least one file.', 'error'); return; }
  const btn = $('upload-btn');
  btn.disabled = true; btn.textContent = 'Uploading…';

  const fd = new FormData();
  _files.forEach(f => fd.append('files', f));

  try {
    const r = await fetch(`${API}/upload-kb`, { method: 'POST', body: fd });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Upload failed');

    _kbLoaded = true;
    setKbStatus(true, `${d.num_chunks} chunks`);
    $('kb-chunk-count').textContent = `${d.num_chunks} chunks`;
    $('kb-chunk-count').style.display = 'inline';
    $('provider-label').textContent = 'ready';
    toast(`KB indexed — ${d.num_chunks} chunks from ${d.doc_ids.join(', ')}`, 'success');
  } catch(e) {
    toast(`Upload failed: ${e.message}`, 'error');
  } finally {
    btn.disabled = false; btn.textContent = 'Upload to index';
  }
}

// ── Live chunk counter ────────────────────────────────────────────────────────
function liveChunkCounter() {
  const ta = $('chunks-input');
  const el = $('chunk-counter');
  const update = () => {
    try {
      const v = ta.value.trim();
      if (!v) { el.textContent = ''; return; }
      const arr = JSON.parse(v);
      if (Array.isArray(arr)) el.textContent = `${arr.length} chunk${arr.length !== 1 ? 's' : ''}`;
      else el.textContent = '';
    } catch { el.textContent = '⚠ invalid JSON'; }
  };
  ta.addEventListener('input', update);
  update();
}

// ── Copy / Format chunks ──────────────────────────────────────────────────────
function copyChunks() {
  const val = $('chunks-input').value;
  if (!val) { toast('Nothing to copy.', 'info'); return; }
  navigator.clipboard.writeText(val).then(() => toast('Copied!', 'success'));
}

function formatChunks() {
  try {
    const v = $('chunks-input').value.trim();
    $('chunks-input').value = JSON.stringify(JSON.parse(v), null, 2);
    liveChunkCounter();
    toast('Formatted!', 'success');
  } catch { toast('Invalid JSON — cannot format.', 'error'); }
}

// ── Demo Scenarios ────────────────────────────────────────────────────────────
const DEMOS = [
  {
    label: 'HR: Leave Policy',
    kbFile: 'knowledge_base.txt',
    query: 'How many days of annual leave do employees get and what is the process to apply for leave?',
    gt: ['hr_c1'],
    chunks: [
      { chunk_id:'hr_c1', text:'Employees are entitled to 25 days of paid annual leave per calendar year. Leave accrues at a rate of 2.08 days per month for full-time employees. Part-time employees receive pro-rated leave based on their contracted hours.', rank:1, similarity_score:0.91, doc_id:'knowledge_base.txt' },
      { chunk_id:'hr_c2', text:'The company offers competitive benefits including health insurance, dental coverage, vision care, and pension contributions matched up to 6% of salary. Employees are encouraged to review their benefits package annually during open enrollment.', rank:2, similarity_score:0.44, doc_id:'knowledge_base.txt' },
      { chunk_id:'hr_c3', text:'Performance reviews are conducted annually every December. Employees must prepare a self-assessment using the Performance Review Template available on the HR Portal before meeting with their line manager.', rank:3, similarity_score:0.37, doc_id:'knowledge_base.txt' }
    ]
  },
  {
    label: 'E-Commerce: Product FAQ',
    kbFile: null,
    query: 'What is the return policy, how long does shipping take, and do you offer international delivery?',
    gt: ['ec_c1', 'ec_c2'],
    chunks: [
      { chunk_id:'ec_c1', text:'Our standard return policy allows customers to return any unused product within 30 days of purchase for a full refund. Items must be in original packaging with all tags attached. Digital downloads and personalized items are non-refundable.', rank:1, similarity_score:0.88, doc_id:'ecommerce_faq.txt' },
      { chunk_id:'ec_c2', text:'Standard domestic shipping takes 3–5 business days. Express shipping is available for an additional fee and delivers within 1–2 business days. Free shipping is offered on all orders over $50 within the continental United States.', rank:2, similarity_score:0.82, doc_id:'ecommerce_faq.txt' },
      { chunk_id:'ec_c3', text:'Our loyalty rewards program gives customers 1 point per dollar spent. Points can be redeemed for discounts at a rate of 100 points equals $1 off. Gold members who spend over $500 annually receive double points on every purchase.', rank:3, similarity_score:0.31, doc_id:'ecommerce_faq.txt' },
      { chunk_id:'ec_c4', text:'We offer seasonal sales every quarter including our biggest Black Friday event. Sign up to our newsletter to get early access to all promotions and an exclusive 10% welcome discount on your first order.', rank:4, similarity_score:0.22, doc_id:'ecommerce_faq.txt' }
    ]
  },
  {
    label: 'Healthcare: Drug Info',
    kbFile: null,
    query: 'What are the side effects, recommended dosage, and contraindications of Metformin for type 2 diabetes?',
    gt: ['med_c1', 'med_c2'],
    chunks: [
      { chunk_id:'med_c1', text:'Metformin is the first-line pharmacological treatment for type 2 diabetes. The standard starting dosage is 500mg twice daily with meals, increasing to a maximum of 2000–2500mg per day based on patient tolerance and kidney function.', rank:1, similarity_score:0.93, doc_id:'drug_reference.txt' },
      { chunk_id:'med_c2', text:'Common side effects of Metformin include gastrointestinal symptoms such as nausea, vomiting, diarrhea, and abdominal discomfort, especially when first starting treatment. Taking Metformin with food significantly reduces these side effects.', rank:2, similarity_score:0.89, doc_id:'drug_reference.txt' },
      { chunk_id:'med_c3', text:'Type 2 diabetes management includes lifestyle modifications such as regular aerobic exercise for at least 150 minutes per week, a balanced low-glycaemic diet, weight management, and regular blood glucose monitoring using a home glucometer.', rank:3, similarity_score:0.41, doc_id:'drug_reference.txt' },
      { chunk_id:'med_c4', text:'Insulin pump therapy and continuous glucose monitoring (CGM) are advanced management tools for patients with difficult-to-control diabetes. CGM devices provide real-time blood glucose readings every 5 minutes throughout the day and night.', rank:4, similarity_score:0.19, doc_id:'drug_reference.txt' }
    ]
  },
  {
    label: 'Education: Course Policy',
    kbFile: null,
    query: 'What is the attendance requirement, how are assignments graded, and what happens if I miss an exam?',
    gt: ['edu_c1', 'edu_c3'],
    chunks: [
      { chunk_id:'edu_c1', text:'Students must maintain a minimum attendance of 75% in all registered courses. Attendance is recorded at the start of each class session. Students who fall below the 75% threshold may be barred from sitting the final examination at the discretion of the course coordinator.', rank:1, similarity_score:0.90, doc_id:'course_handbook.txt' },
      { chunk_id:'edu_c2', text:'The university library provides access to over 2 million physical books, 500,000 e-books, and 80 academic journal databases including JSTOR, Scopus, and Web of Science. Students receive a library card upon enrollment which also grants 24-hour access to study rooms.', rank:2, similarity_score:0.28, doc_id:'course_handbook.txt' },
      { chunk_id:'edu_c3', text:'Course assessment comprises 40% continuous assessment (assignments, quizzes, and participation) and 60% final examination. All assignments must be submitted through the online portal by 11:59 PM on the due date. Late submissions incur a 10% penalty per day.', rank:3, similarity_score:0.86, doc_id:'course_handbook.txt' },
      { chunk_id:'edu_c4', text:'Student clubs and societies provide excellent networking and personal development opportunities. The Students Union runs over 120 active clubs covering sports, culture, arts, technology, and entrepreneurship. All enrolled students can join any club for a nominal annual fee.', rank:4, similarity_score:0.15, doc_id:'course_handbook.txt' }
    ]
  }
];

// ── Load Demo ─────────────────────────────────────────────────────────────────
// Loads the selected demo scenario and auto-uploads KB if available.
async function loadDemo() {
  const btn = $('demo-btn');
  const idx = parseInt($('demo-select')?.value ?? '0', 10);
  const demo = DEMOS[idx] ?? DEMOS[0];

  btn.disabled = true;
  btn.textContent = '⏳ Setting up…';

  try {
    // Step 1 — upload KB if a real file exists for this demo
    if (demo.kbFile) {
      btn.textContent = '⏳ Uploading KB…';
      toast(`Uploading demo knowledge base…`, 'info');
      const kbRes = await fetch(`/demo/${demo.kbFile}`);
      if (!kbRes.ok) throw new Error(`Could not fetch /demo/${demo.kbFile}`);
      const kbBlob = await kbRes.blob();
      const kbFile = new File([kbBlob], demo.kbFile, { type: 'text/plain' });
      const fd = new FormData();
      fd.append('files', kbFile);
      const upRes  = await fetch(`${API}/upload-kb`, { method: 'POST', body: fd });
      const upData = await upRes.json();
      if (!upRes.ok) throw new Error(upData.detail || 'KB upload failed');

      _kbLoaded = true;
      setKbStatus(true, `${upData.num_chunks} chunks`);
      $('kb-chunk-count').textContent = `${upData.num_chunks} chunks`;
      $('kb-chunk-count').style.display = 'inline';
      $('drop-zone').style.borderColor = 'var(--emerald)';
      $('drop-zone').querySelector('.drop-primary').innerHTML =
        `<strong style="color:var(--emerald)">✓ ${demo.kbFile} indexed</strong>`;
      $('drop-zone').querySelector('.drop-hint').textContent = `${upData.num_chunks} chunks ready`;
      hideKbWarning();
    } else {
      // For demos without a real KB file, generate a synthetic KB from the chunks
      btn.textContent = '⏳ Indexing KB…';
      const syntheticKB = demo.chunks.map(c => c.text).join('\n\n');
      const kbBlob = new Blob([syntheticKB], { type: 'text/plain' });
      const kbFile = new File([kbBlob], demo.chunks[0]?.doc_id || 'demo_kb.txt', { type: 'text/plain' });
      const fd = new FormData();
      fd.append('files', kbFile);
      const upRes  = await fetch(`${API}/upload-kb`, { method: 'POST', body: fd });
      const upData = await upRes.json();
      if (!upRes.ok) throw new Error(upData.detail || 'KB upload failed');

      _kbLoaded = true;
      setKbStatus(true, `${upData.num_chunks} chunks`);
      $('kb-chunk-count').textContent = `${upData.num_chunks} chunks`;
      $('kb-chunk-count').style.display = 'inline';
      $('drop-zone').style.borderColor = 'var(--emerald)';
      $('drop-zone').querySelector('.drop-primary').innerHTML =
        `<strong style="color:var(--emerald)">✓ ${demo.label} KB indexed</strong>`;
      $('drop-zone').querySelector('.drop-hint').textContent = `${upData.num_chunks} chunks ready`;
      hideKbWarning();
    }

    // Step 2 — fill query + chunks
    btn.textContent = '⏳ Loading query…';
    $('query-input').value  = demo.query;
    $('chunks-input').value = JSON.stringify(demo.chunks, null, 2);
    if ($('gt-input')) $('gt-input').value = (demo.gt || []).join(', ');

    liveChunkCounter();
    toast(`✅ "${demo.label}" demo ready! Hit Run Audit.`, 'success');

  } catch (err) {
    toast(`Demo setup failed: ${err.message}`, 'error');
  } finally {
    btn.disabled = false; btn.textContent = 'Load demo';
  }
}

function clearAll() {
  $('query-input').value = '';
  $('chunks-input').value = '';
  if ($('gt-input')) $('gt-input').value = '';
  $('file-chips').innerHTML = '';
  $('chunk-counter').textContent = '';
  _files = []; _result = null;
  showEmptyCanvas();
  toast('Cleared.', 'info');
}

// ── Audit ─────────────────────────────────────────────────────────────────────
const STEPS = [
  { label: 'Decomposing query into sub-aspects', icon: '◆' },
  { label: 'Computing coverage matrix (N × K)', icon: '▦' },
  { label: 'Classifying chunks (SUPPORTING / PARTIAL / NOISE)', icon: '◈' },
  { label: 'Searching KB for missing evidence', icon: '⊕' },
  { label: 'Computing Retrieval Integrity Score', icon: '◉' },
  { label: 'Generating explanation & recommendations', icon: '◎' },
  { label: 'Building audit report', icon: '✓' },
];

// ── KB warning banner ─────────────────────────────────────────────────────────
function showKbWarning() {
  let warn = $('kb-warning');
  if (!warn) {
    warn = document.createElement('div');
    warn.id = 'kb-warning';
    warn.style.cssText = 'display:flex;align-items:center;gap:10px;padding:10px 14px;background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.3);border-radius:8px;font-size:13px;color:#f59e0b;margin-bottom:4px;animation:fadeSlideUp .3s ease';
    warn.innerHTML = `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M8 1L1 14h14L8 1z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M8 6v4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><circle cx="8" cy="12" r=".8" fill="currentColor"/></svg>
      <span><strong>Knowledge Base not loaded.</strong> Click <strong>Load demo</strong> (sets up everything automatically) or upload your own files above.</span>
      <button onclick="hideKbWarning()" style="margin-left:auto;background:none;border:none;color:#f59e0b;cursor:pointer;font-size:16px;line-height:1">×</button>`;
    $('run-btn').insertAdjacentElement('beforebegin', warn);
  }
  warn.style.display = 'flex';
}
function hideKbWarning() {
  const w = $('kb-warning'); if (w) w.style.display = 'none';
}

async function runAudit() {
  const query     = $('query-input').value.trim();
  const rawChunks = $('chunks-input').value.trim();

  if (!query)     { toast('Enter a query first.', 'error'); return; }
  if (!rawChunks) { toast('Paste retrieved chunks JSON.', 'error'); return; }

  // Check KB loaded — guard before hitting the network
  if (!_kbLoaded) {
    showKbWarning();
    toast('Upload a Knowledge Base first — or click "Load demo" to auto-setup!', 'error');
    $('demo-btn').style.boxShadow = '0 0 0 3px rgba(99,102,241,.5)';
    setTimeout(() => { $('demo-btn').style.boxShadow = ''; }, 2000);
    return;
  }

  let retrieved_chunks;
  try {
    retrieved_chunks = JSON.parse(rawChunks);
    if (!Array.isArray(retrieved_chunks)) throw new Error('Must be an array');
  } catch(e) { toast(`Invalid JSON: ${e.message}`, 'error'); return; }

  const required = ['chunk_id','text','rank','similarity_score','doc_id'];
  for (const [i,c] of retrieved_chunks.entries()) {
    const miss = required.filter(k => !(k in c));
    if (miss.length) { toast(`Chunk [${i}] missing: ${miss.join(', ')}`, 'error'); return; }
  }

  // Optional ground truth — comma/space/JSON list of relevant chunk IDs
  let ground_truth = null;
  const gtRaw = $('gt-input')?.value.trim();
  if (gtRaw) {
    let ids;
    try {
      ids = gtRaw.startsWith('[') ? JSON.parse(gtRaw)
                                  : gtRaw.split(/[,\s]+/).filter(Boolean);
    } catch { ids = gtRaw.split(/[,\s]+/).filter(Boolean); }
    if (ids.length) ground_truth = { relevant_chunk_ids: ids, relevant_doc_ids: [] };
  }

  // Show pipeline
  const btn = $('run-btn');
  btn.disabled = true;
  $('run-btn-text').textContent = 'Running…';
  $('run-arrow').style.display = 'none';
  $('run-spinner').style.display = 'block';

  showPipeline(query);

  try {
    const res = await fetch(`${API}/audit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(ground_truth ? { query, retrieved_chunks, ground_truth }
                                        : { query, retrieved_chunks })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Audit failed');

    _result = data;
    saveHistory(data);
    renderResults(data);
    toast('Audit complete!', 'success');
  } catch(e) {
    toast(`Error: ${e.message}`, 'error');
    showEmptyCanvas();
  } finally {
    btn.disabled = false;
    $('run-btn-text').textContent = 'Run Audit';
    $('run-arrow').style.display = '';
    $('run-spinner').style.display = 'none';
    clearInterval(_pipeInterval);
  }
}

function showPipeline(query) {
  $('empty-canvas').style.display  = 'none';
  $('results-view').style.display  = 'none';
  $('pipeline-view').style.display = 'flex';
  $('pipeline-query-text').textContent = query.slice(0, 100);

  const container = $('pipeline-steps');
  container.innerHTML = STEPS.map((s, i) => `
    <div class="pipe-step" id="pstep-${i}">
      <div class="pipe-step-icon" id="picon-${i}">${i + 1}</div>
      <span>${s.label}</span>
    </div>`).join('');

  let cur = 0;
  activatePipeStep(cur);
  _pipeInterval = setInterval(() => {
    markPipeStepDone(cur);
    cur++;
    if (cur < STEPS.length) activatePipeStep(cur);
  }, 2600);
}

function activatePipeStep(i) {
  $(`pstep-${i}`)?.classList.add('active');
  const icon = $(`picon-${i}`);
  if (icon) icon.innerHTML = '<div class="run-spinner" style="width:10px;height:10px;border-width:1.5px"></div>';
}

function markPipeStepDone(i) {
  const step = $(`pstep-${i}`);
  if (!step) return;
  step.classList.remove('active');
  step.classList.add('done');
  const icon = $(`picon-${i}`);
  if (icon) icon.innerHTML = '<svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M1.5 5l2.5 2.5 4.5-4.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
}

function showEmptyCanvas() {
  $('empty-canvas').style.display  = 'flex';
  $('results-view').style.display  = 'none';
  $('pipeline-view').style.display = 'none';
}

// ── Render Results ────────────────────────────────────────────────────────────
function renderResults(data) {
  $('pipeline-view').style.display = 'none';
  $('empty-canvas').style.display  = 'none';
  $('results-view').style.display  = 'flex';

  // Header
  $('result-query-label').textContent = data.query;
  $('result-timestamp').textContent   = new Date().toLocaleTimeString();

  renderScore(data.summary, data.explanation);
  renderGroundTruth(data.ground_truth_eval);
  renderHeatmap(data.aspects, data.chunk_classifications, data.coverage_matrix);
  renderEvidence(data.chunk_classifications);
  renderMissing(data.missing_evidence);
  renderRecs(data.recommendations);

  // Tab counts
  $('tc-heat').textContent = data.aspects.length;
  $('tc-evid').textContent = data.chunk_classifications.length;
  $('tc-miss').textContent = data.missing_evidence.length;
  $('tc-recs').textContent = data.recommendations.length;

  // Switch to first tab
  switchTab('heat');
}

// ── Score ─────────────────────────────────────────────────────────────────────
function renderScore(s, explanation) {
  const score = s.integrity_score;

  // Gauge animation (count-up)
  let current = 0;
  const el = $('score-num');
  const arc = $('gauge-arc');
  const circ = 314.16;

  const color = score >= 71 ? '#10b981' : score >= 41 ? '#f59e0b' : '#ef4444';
  arc.style.stroke = color;

  const interval = setInterval(() => {
    current = Math.min(current + Math.ceil((score - current) / 5 + 1), score);
    el.textContent = current;
    const offset = circ - (current / 100) * circ;
    arc.style.strokeDashoffset = offset;
    if (current >= score) clearInterval(interval);
  }, 30);

  // Grade badge
  const badge = $('score-grade-badge');
  if (score >= 71) { badge.textContent = '✓ High Integrity'; badge.className = 'score-grade-badge grade-high'; }
  else if (score >= 41) { badge.textContent = '⚠ Medium Integrity'; badge.className = 'score-grade-badge grade-mid'; }
  else { badge.textContent = '✕ Low Integrity'; badge.className = 'score-grade-badge grade-low'; }

  // Formula hint
  const noiseP = (s.noise_ratio * 20).toFixed(1);
  $('score-formula').textContent = `base − ${noiseP} noise penalty`;
  $('score-formula').title = `base = (${s.covered_aspects}/${s.total_aspects}) × 100 = ${(s.covered_aspects/s.total_aspects*100).toFixed(1)}, noise_penalty = ${s.noise_ratio.toFixed(2)} × 20 = ${noiseP}`;

  // Metrics
  $('score-metrics').innerHTML = `
    <div class="metric"><span class="metric-val indigo">${s.total_aspects}</span><span class="metric-lbl">Aspects</span></div>
    <div class="metric"><span class="metric-val green">${s.covered_aspects}</span><span class="metric-lbl">Covered</span></div>
    <div class="metric"><span class="metric-val red">${s.missing_aspects}</span><span class="metric-lbl">Missing</span></div>
    <div class="metric"><span class="metric-val green">${s.supporting_chunks}</span><span class="metric-lbl">Supporting</span></div>
    <div class="metric"><span class="metric-val ${s.noise_chunks > 0 ? 'red':'green'}">${s.noise_chunks}</span><span class="metric-lbl">Noise</span></div>
  `;

  // Coverage bars
  const covPct = s.total_aspects > 0 ? Math.round(s.covered_aspects / s.total_aspects * 100) : 0;
  const noisePct = Math.round(s.noise_ratio * 100);
  $('coverage-bars').innerHTML = `
    <div class="cbar-row">
      <span class="cbar-label">Coverage</span>
      <div class="cbar-track"><div class="cbar-fill" style="width:0%;background:var(--emerald)" data-target="${covPct}"></div></div>
      <span class="cbar-val">${covPct}%</span>
    </div>
    <div class="cbar-row">
      <span class="cbar-label">Noise ratio</span>
      <div class="cbar-track"><div class="cbar-fill" style="width:0%;background:var(--red)" data-target="${noisePct}"></div></div>
      <span class="cbar-val">${noisePct}%</span>
    </div>
  `;
  // Animate bars
  setTimeout(() => {
    document.querySelectorAll('.cbar-fill').forEach(el => {
      el.style.width = el.dataset.target + '%';
    });
  }, 80);

  $('score-explanation').textContent = explanation || '—';
}

// ── Ground-Truth Evaluation ───────────────────────────────────────────────────
function renderGroundTruth(gt) {
  const el = $('gt-eval');
  if (!el) return;
  if (!gt) { el.style.display = 'none'; el.innerHTML = ''; return; }

  const pct = v => Math.round(v * 100);
  const f1Color = gt.f1 >= 0.7 ? 'var(--emerald)' : gt.f1 >= 0.4 ? 'var(--amber)' : 'var(--red)';
  const missed = gt.missed_relevant_ids.length
    ? gt.missed_relevant_ids.map(id => `<span class="gt-chip miss">${esc(id)}</span>`).join('')
    : '<span class="gt-chip ok">none — full recall</span>';

  el.style.display = 'block';
  el.innerHTML = `
    <div class="gt-head">
      <span class="gt-title">Ground-Truth Evaluation</span>
      <span class="gt-sub">vs. labeled relevant chunks</span>
    </div>
    <div class="gt-metrics">
      <div class="gt-metric"><span class="gt-val">${pct(gt.precision)}%</span><span class="gt-lbl">Precision</span></div>
      <div class="gt-metric"><span class="gt-val">${pct(gt.recall)}%</span><span class="gt-lbl">Recall</span></div>
      <div class="gt-metric"><span class="gt-val" style="color:${f1Color}">${gt.f1.toFixed(2)}</span><span class="gt-lbl">F1 Score</span></div>
      <div class="gt-metric"><span class="gt-val green">${gt.true_positives}</span><span class="gt-lbl">Hits (TP)</span></div>
      <div class="gt-metric"><span class="gt-val ${gt.false_positives?'red':'green'}">${gt.false_positives}</span><span class="gt-lbl">Noise (FP)</span></div>
      <div class="gt-metric"><span class="gt-val ${gt.false_negatives?'red':'green'}">${gt.false_negatives}</span><span class="gt-lbl">Missed (FN)</span></div>
    </div>
    <div class="gt-missed"><span class="gt-missed-lbl">Missed relevant:</span> ${missed}</div>
  `;
}

// ── Heatmap ───────────────────────────────────────────────────────────────────
function scoreColor(s) {
  if (s < 0.01) return '#f1f5f9';  // near-zero: light gray
  if (s < 0.25) return `hsl(120,${Math.round(20+s*60)}%,${Math.round(82-s*20)}%)`;  // light green
  if (s < 0.50) return `hsl(120,${Math.round(40+s*40)}%,${Math.round(72-s*18)}%)`;  // mid green
  return `hsl(120,${Math.round(50+s*30)}%,${Math.round(62-s*22)}%)`;  // strong green
}

function renderHeatmap(aspects, chunks, matrix) {
  const wrap = $('heatmap-wrap');
  const chunkIds = chunks.map(c => c.chunk_id);
  const chunkMap = Object.fromEntries(chunks.map(c => [c.chunk_id, c]));

  const headCols = chunkIds.map(id =>
    `<th title="${esc(chunkMap[id]?.text?.slice(0,120)||id)}">${esc(id)}</th>`
  ).join('');

  const rows = aspects.map(ac => {
    const miss = ac.status === 'MISSING';
    const cells = chunkIds.map(cid => {
      const sc = (matrix[ac.aspect]||{})[cid] ?? 0;
      const bg = scoreColor(sc);
      return `<td>
        <div class="hmap-cell" tabindex="0" role="button"
          style="background:${bg}"
          title="${esc(ac.aspect)} × ${esc(cid)}: ${sc.toFixed(4)}"
          onclick="openCellDrawer(${JSON.stringify(ac)},${JSON.stringify(chunkMap[cid])},${sc})"
          onkeydown="if(event.key==='Enter'||event.key===' ')openCellDrawer(${JSON.stringify(ac)},${JSON.stringify(chunkMap[cid])},${sc})"
        >${sc.toFixed(2)}</div>
      </td>`;
    }).join('');

    return `<tr onmouseenter="heatRowHL(this,true)" onmouseleave="heatRowHL(this,false)">
      <td class="${miss?'miss-row':''}" title="${esc(ac.aspect)}">
        ${esc(ac.aspect)}${miss?'<span class="miss-tag">MISSING</span>':''}
      </td>
      ${cells}
    </tr>`;
  }).join('');

  wrap.innerHTML = `
    <table class="hmap">
      <thead><tr><th>Aspect / Sub-topic</th>${headCols}</tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

let _heatHighlight = false;
function toggleHeatHighlight() { _heatHighlight = $('heat-highlight-toggle').checked; }
function heatRowHL(tr, on) {
  if (!_heatHighlight) return;
  tr.classList.toggle('row-hl', on);
}

// ── Evidence ──────────────────────────────────────────────────────────────────
function renderEvidence(chunks) {
  _allChunks = chunks;
  const list = $('evid-list');

  if (!chunks.length) {
    list.innerHTML = emptyState('🔍', 'No chunks to display.');
    return;
  }

  list.innerHTML = chunks.map((c, i) => {
    const cls = c.classification.toLowerCase();
    const aspectPills = c.covers_aspects.map(a =>
      `<span class="aspect-tag">${esc(a)}</span>`
    ).join('');
    const noiseNote = c.noise_reason
      ? `<div class="noise-note">⚠ ${esc(c.noise_reason)}</div>` : '';
    const short = c.text.slice(0, 200);
    const hasMore = c.text.length > 200;

    return `<div class="evid-card ${cls}" data-cls="${c.classification}" data-text="${esc(c.text.toLowerCase())}" style="animation-delay:${i*40}ms">
      <div class="evid-card-head">
        <div class="evid-left">
          <span class="rank-badge">#${c.rank ?? i+1}</span>
          <span class="chunk-id-tag">${esc(c.chunk_id)}</span>
          <span class="sim-badge">sim ${c.similarity_score?.toFixed(3) ?? '—'}</span>
        </div>
        <span class="cls-badge cls-${cls}">${clsIcon(c.classification)} ${c.classification}</span>
      </div>
      <div class="evid-text evid-text-collapsed" id="etxt-${i}">${esc(short)}${hasMore?'…':''}</div>
      ${hasMore ? `<button class="expand-btn" onclick="toggleExpand(${i},this)"  data-full="${esc(c.text)}" data-short="${esc(short)}">Show more</button>` : ''}
      ${aspectPills ? `<div class="aspect-tags">${aspectPills}</div>` : ''}
      ${noiseNote}
    </div>`;
  }).join('');
}

function toggleExpand(i, btn) {
  const el = $(`etxt-${i}`);
  if (el.classList.contains('evid-text-collapsed')) {
    el.textContent = btn.dataset.full;
    el.classList.remove('evid-text-collapsed');
    btn.textContent = 'Show less';
  } else {
    el.textContent = btn.dataset.short + '…';
    el.classList.add('evid-text-collapsed');
    btn.textContent = 'Show more';
  }
}

function clsIcon(cls) {
  return cls === 'SUPPORTING' ? '✓' : cls === 'PARTIAL' ? '~' : '✗';
}

function filterEvidence(btn) {
  document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
  btn.classList.add('active');
  const f = btn.dataset.filter;
  applyEvidenceFilter(f, $('evid-search').value);
}

function searchEvidence(q) {
  const activeChip = qs('.filter-chip.active');
  const f = activeChip ? activeChip.dataset.filter : 'ALL';
  applyEvidenceFilter(f, q);
}

function applyEvidenceFilter(cls, q) {
  const lq = q.toLowerCase();
  document.querySelectorAll('.evid-card').forEach(card => {
    const matchCls  = cls === 'ALL' || card.dataset.cls === cls;
    const matchText = !lq || card.dataset.text.includes(lq) || card.querySelector('.chunk-id-tag')?.textContent.toLowerCase().includes(lq);
    card.dataset.hidden = !(matchCls && matchText);
    card.style.display = matchCls && matchText ? '' : 'none';
  });
}

// ── Missing Evidence ──────────────────────────────────────────────────────────
function renderMissing(items) {
  const el = $('missing-list');
  if (!items.length) {
    el.innerHTML = emptyState('✅', 'No missing evidence — all aspects were covered by retrieved chunks!');
    return;
  }
  el.innerHTML = items.map(m => `
    <div class="miss-card">
      <div class="miss-aspect">
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 1L1 13h12L7 1z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M7 6v3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><circle cx="7" cy="11" r=".8" fill="currentColor"/></svg>
        ${esc(m.aspect)}
      </div>
      <div class="miss-candidate">
        <div class="miss-meta">
          <span class="meta-pill">${esc(m.candidate_chunk_id)}</span>
          <span class="meta-pill">📄 ${esc(m.candidate_doc_id)}</span>
          <span class="meta-sim">sim ${m.similarity_score.toFixed(4)}</span>
        </div>
        <div class="miss-text">"${esc(m.candidate_text)}${m.candidate_text.length >= 400 ? '…' : ''}"</div>
      </div>
      <div class="miss-reason">💡 ${esc(m.reason_missed)}</div>
    </div>`).join('');
}

// ── Recommendations ───────────────────────────────────────────────────────────
const REC_ICONS = {
  QUERY_REWRITE: '✏', CHUNKING: '✂', HYBRID_SEARCH: '⊕', THRESHOLD: '◎', RERANKING: '⇅'
};

function renderRecs(recs) {
  const el = $('recs-grid');
  if (!recs.length) {
    el.innerHTML = emptyState('💡', 'No recommendations generated.');
    return;
  }
  el.innerHTML = recs.map(r => `
    <div class="rec-card">
      <div class="rec-type rt-${r.type}">
        ${REC_ICONS[r.type] || '●'} ${r.type.replace(/_/g,' ')}
      </div>
      <div class="rec-desc">${esc(r.description)}</div>
      <div class="rec-example">${esc(r.example)}</div>
    </div>`).join('');
}

// ── Tabs ──────────────────────────────────────────────────────────────────────
function switchTab(name) {
  ['heat','evid','miss','recs'].forEach(t => {
    $(`tab-${t}`)?.classList.toggle('active', t === name);
    $(`tab-${t}`)?.setAttribute('aria-selected', t === name);
    $(`panel-${t}`)?.classList.toggle('active', t === name);
    if ($(`panel-${t}`)) $(`panel-${t}`).style.display = t === name ? 'block' : 'none';
  });
}

// ── Cell Drawer ───────────────────────────────────────────────────────────────
function openCellDrawer(aspect, chunk, score) {
  const color = scoreColor(score);
  const statusColor = aspect.status === 'COVERED' ? 'var(--emerald)' : aspect.status === 'PARTIAL' ? 'var(--amber)' : 'var(--red)';

  $('drawer-body').innerHTML = `
    <div class="drawer-field">
      <div class="drawer-lbl">Aspect</div>
      <div class="drawer-val">${esc(aspect.aspect)}</div>
    </div>
    <div class="drawer-field">
      <div class="drawer-lbl">Status</div>
      <div class="drawer-val" style="color:${statusColor};font-weight:600">${aspect.status}</div>
    </div>
    <div class="drawer-field">
      <div class="drawer-lbl">Chunk</div>
      <div class="drawer-val mono">${esc(chunk?.chunk_id || '—')}</div>
    </div>
    <div class="drawer-field">
      <div class="drawer-lbl">Similarity Score</div>
      <div class="dbar-wrap" style="margin-top:6px">
        <div class="dbar-track"><div class="dbar-fill" style="width:${(score*100).toFixed(1)}%;background:${color}"></div></div>
        <span class="dbar-num" style="color:${color}">${score.toFixed(4)}</span>
      </div>
    </div>
    <div class="drawer-field">
      <div class="drawer-lbl">Classification</div>
      <div class="drawer-val">
        <span class="cls-badge cls-${(chunk?.classification||'noise').toLowerCase()}">${chunk?.classification||'—'}</span>
      </div>
    </div>
    <div class="drawer-field">
      <div class="drawer-lbl">Full Chunk Text</div>
      <div class="drawer-val" style="max-height:200px;overflow-y:auto">${esc(chunk?.text||'—')}</div>
    </div>
    ${chunk?.covers_aspects?.length ? `
    <div class="drawer-field">
      <div class="drawer-lbl">Aspects Covered</div>
      <div style="display:flex;flex-wrap:wrap;gap:5px;margin-top:6px">
        ${chunk.covers_aspects.map(a => `<span class="aspect-tag">${esc(a)}</span>`).join('')}
      </div>
    </div>` : ''}
    ${chunk?.noise_reason ? `
    <div class="drawer-field">
      <div class="drawer-lbl">Noise Reason</div>
      <div class="drawer-val" style="color:var(--red)">${esc(chunk.noise_reason)}</div>
    </div>` : ''}
    <div class="drawer-field">
      <div class="drawer-lbl">Source</div>
      <div class="drawer-val mono">${esc(chunk?.doc_id||'—')}</div>
    </div>
  `;

  $('cell-drawer').classList.add('open');
  $('drawer-backdrop').classList.add('open');
}

function closeDrawer() {
  $('cell-drawer').classList.remove('open');
  $('drawer-backdrop').classList.remove('open');
}

// ── History ───────────────────────────────────────────────────────────────────
function saveHistory(data) {
  try {
    const hist = JSON.parse(localStorage.getItem('ria_history') || '[]');
    hist.unshift({
      query: data.query,
      score: data.summary.integrity_score,
      ts: Date.now(),
      data
    });
    localStorage.setItem('ria_history', JSON.stringify(hist.slice(0, 10)));
    loadHistoryBadge();
  } catch(_) {}
}

function loadHistoryBadge() {
  try {
    const hist = JSON.parse(localStorage.getItem('ria_history') || '[]');
    const btn = $('history-btn');
    if (btn && hist.length) btn.innerHTML = `<svg width="15" height="15" viewBox="0 0 15 15" fill="none"><path d="M7.5 1a6.5 6.5 0 100 13A6.5 6.5 0 007.5 1zM7.5 4v4l2.5 1.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg> History <span style="background:var(--indigo);color:#fff;border-radius:99px;padding:0 6px;font-size:11px">${hist.length}</span>`;
  } catch(_) {}
}

function openHistory() {
  try {
    const hist = JSON.parse(localStorage.getItem('ria_history') || '[]');
    const list = $('history-list');
    if (!hist.length) {
      list.innerHTML = '<div class="history-empty">No audits yet. Run one!</div>';
    } else {
      list.innerHTML = hist.map((item, i) => {
        const cls = item.score >= 71 ? 'high' : item.score >= 41 ? 'mid' : 'low';
        const ts = new Date(item.ts).toLocaleString();
        return `<div class="history-item" onclick="restoreHistory(${i})">
          <div class="history-item-query">${esc(item.query)}</div>
          <div class="history-item-meta">
            <span class="history-score ${cls}">${item.score}/100</span>
            <span class="history-ts">${ts}</span>
          </div>
        </div>`;
      }).join('');
    }
  } catch(_) {
    $('history-list').innerHTML = '<div class="history-empty">Could not load history.</div>';
  }
  $('history-panel').classList.add('open');
  $('history-backdrop').classList.add('open');
}

function closeHistory() {
  $('history-panel').classList.remove('open');
  $('history-backdrop').classList.remove('open');
}

function restoreHistory(i) {
  try {
    const hist = JSON.parse(localStorage.getItem('ria_history') || '[]');
    const item = hist[i];
    if (!item) return;
    _result = item.data;
    $('query-input').value = item.data.query;
    renderResults(item.data);
    closeHistory();
    toast('Restored audit from history.', 'info');
  } catch(e) { toast('Could not restore.', 'error'); }
}

function clearHistory() {
  localStorage.removeItem('ria_history');
  $('history-list').innerHTML = '<div class="history-empty">History cleared.</div>';
  loadHistoryBadge();
  toast('History cleared.', 'info');
}

// ── Download / Share ──────────────────────────────────────────────────────────
function downloadReport() {
  if (!_result) { toast('Run an audit first.', 'error'); return; }
  const blob = new Blob([JSON.stringify(_result, null, 2)], { type: 'application/json' });
  const a = Object.assign(document.createElement('a'), {
    href: URL.createObjectURL(blob),
    download: `ria-audit-${Date.now()}.json`
  });
  a.click(); URL.revokeObjectURL(a.href);
  toast('Report downloaded!', 'success');
}

function copyShareLink() {
  if (!_result) { toast('Run an audit first.', 'error'); return; }
  const compact = { q: _result.query, s: _result.summary.integrity_score };
  const hash = btoa(JSON.stringify(compact)).replace(/=/g,'');
  const url = `${location.origin}${location.pathname}#result=${hash}`;
  navigator.clipboard.writeText(url).then(() => toast('Link copied to clipboard!', 'success'));
}

function restoreFromHash() {
  try {
    const hash = location.hash.replace('#result=','');
    const data = JSON.parse(atob(hash + '=='));
    toast(`Shared audit: "${data.q.slice(0,60)}" — Score: ${data.s}/100`, 'info');
  } catch(_) {}
}

function openDocs() {
  toast('Documentation: see README.md in the project root.', 'info');
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function esc(s) {
  if (typeof s !== 'string') return String(s ?? '');
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

function fmtBytes(b) {
  if (b < 1024) return `${b}B`;
  if (b < 1048576) return `${(b/1024).toFixed(1)}KB`;
  return `${(b/1048576).toFixed(1)}MB`;
}

function emptyState(icon, text) {
  return `<div class="list-empty"><div class="list-empty-icon">${icon}</div><div class="list-empty-txt">${text}</div></div>`;
}

function toast(msg, type = 'info') {
  const icons = { success:'✓', error:'✕', info:'i' };
  const el = document.createElement('div');
  el.className = `toast-item ${type}`;
  el.innerHTML = `<span class="toast-icon">${icons[type]||'i'}</span><span class="toast-msg">${esc(msg)}</span>`;
  $('toast-rack').appendChild(el);
  setTimeout(() => {
    el.style.animation = 'slideDown .25s ease forwards';
    setTimeout(() => el.remove(), 250);
  }, 3800);
}
