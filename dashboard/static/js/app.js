/* =========================================================================
   SEA Automation Agency — Dashboard Frontend Logic
   ========================================================================= */

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let currentSort = 'score';
let currentOrder = 'desc';

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    updateClock();
    setInterval(updateClock, 1000);
    loadAll();
    setInterval(loadAll, 60000); // Auto-refresh every 60s
});

function loadAll() {
    loadStats();
    loadPipeline();
    loadLeads();
    loadOutreach();
    populatePreviewDropdown();
}

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------
function initTabs() {
    document.querySelectorAll('.nav-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const target = tab.dataset.tab;
            document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            tab.classList.add('active');
            document.getElementById(`tab-${target}`).classList.add('active');
        });
    });
}

// ---------------------------------------------------------------------------
// Clock
// ---------------------------------------------------------------------------
function updateClock() {
    const el = document.getElementById('headerTime');
    if (el) {
        const now = new Date();
        el.textContent = now.toLocaleString('vi-VN', {
            hour: '2-digit', minute: '2-digit', second: '2-digit',
            day: '2-digit', month: '2-digit', year: 'numeric'
        });
    }
}

// ---------------------------------------------------------------------------
// Stats / KPI Cards
// ---------------------------------------------------------------------------
async function loadStats() {
    try {
        const res = await fetch('/api/stats');
        const data = await res.json();
        setText('kpiTotal', data.total_leads);
        setText('kpiEmailsWeek', data.emails_sent_week);
        setText('kpiReplies', data.replies);
        setText('kpiReplyRate', `${data.reply_rate}% rate`);
        setText('kpiMeetings', data.meetings);
        setText('kpiMeetingRate', `${data.meeting_rate}% rate`);
        setText('kpiConversion', `${data.conversion_rate}%`);

        // Services
        const grid = document.getElementById('servicesGrid');
        if (data.services && data.services.length) {
            grid.innerHTML = data.services.map(s => `
                <div class="service-card">
                    <div class="service-name">${esc(s.name)}</div>
                    <div class="service-price">${formatVND(s.price)}</div>
                </div>
            `).join('');
        }
    } catch (e) {
        console.error('Stats load failed:', e);
    }
}

// ---------------------------------------------------------------------------
// Pipeline Funnel
// ---------------------------------------------------------------------------
async function loadPipeline() {
    const container = document.getElementById('funnelContainer');
    try {
        const res = await fetch('/api/pipeline');
        const data = await res.json();

        const stages = [
            { key: 'new', label: 'New', cls: 'f-new' },
            { key: 'contacted', label: 'Contacted', cls: 'f-contacted' },
            { key: 'replied', label: 'Replied', cls: 'f-replied' },
            { key: 'meeting', label: 'Meeting', cls: 'f-meeting' },
            { key: 'proposal_sent', label: 'Proposal Sent', cls: 'f-proposal' },
            { key: 'closed_won', label: 'Closed Won ✓', cls: 'f-won' },
            { key: 'closed_lost', label: 'Closed Lost ✗', cls: 'f-lost' },
        ];

        const maxVal = Math.max(data.total || 1, 1);

        container.innerHTML = stages.map(s => {
            const val = data[s.key] || 0;
            const pct = Math.max((val / maxVal) * 100, 0);
            return `
                <div class="funnel-bar-group">
                    <div class="funnel-label">${s.label}</div>
                    <div class="funnel-track">
                        <div class="funnel-fill ${s.cls}" style="width: ${pct}%"></div>
                    </div>
                    <div class="funnel-count">${val}</div>
                </div>
            `;
        }).join('');

        // Trigger animation after paint
        requestAnimationFrame(() => {
            container.querySelectorAll('.funnel-fill').forEach(el => {
                el.style.width = el.style.width; // Force reflow
            });
        });
    } catch (e) {
        container.innerHTML = '<div class="funnel-loading">Failed to load pipeline</div>';
    }
}

// ---------------------------------------------------------------------------
// Leads Table
// ---------------------------------------------------------------------------
async function loadLeads() {
    const body = document.getElementById('leadsBody');
    const search = document.getElementById('leadsSearch').value;
    const status = document.getElementById('leadsStatusFilter').value;
    const platform = document.getElementById('leadsPlatformFilter').value;

    const params = new URLSearchParams();
    if (search) params.set('q', search);
    if (status) params.set('status', status);
    if (platform) params.set('platform', platform);
    params.set('sort', currentSort);
    params.set('order', currentOrder);

    try {
        const res = await fetch(`/api/leads?${params}`);
        const data = await res.json();

        body.innerHTML = data.leads.map(l => `
            <tr>
                <td><span class="score-pill ${scoreClass(l.score)}">${l.score}</span></td>
                <td><strong>${esc(l.business_name)}</strong></td>
                <td><a href="mailto:${esc(l.email)}" style="color:var(--accent);text-decoration:none">${esc(l.email)}</a></td>
                <td>${esc(l.phone) || '—'}</td>
                <td>${esc(l.platform) || '—'}</td>
                <td>${esc(l.city) || '—'}</td>
                <td>${statusBadge(l.status)}</td>
                <td><button class="btn-inline" onclick="previewLeadEmail('${esc(l.email)}')">Preview</button></td>
            </tr>
        `).join('');

        setText('leadsCount', `${data.total} leads`);
    } catch (e) {
        body.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text-muted);padding:32px">Failed to load leads</td></tr>';
    }
}

function sortLeads(field) {
    if (currentSort === field) {
        currentOrder = currentOrder === 'desc' ? 'asc' : 'desc';
    } else {
        currentSort = field;
        currentOrder = field === 'score' ? 'desc' : 'asc';
    }
    loadLeads();
}

function scoreClass(score) {
    const s = parseInt(score) || 0;
    if (s >= 70) return 'score-high';
    if (s >= 40) return 'score-mid';
    return 'score-low';
}

function statusBadge(status) {
    const s = (status || 'new').toLowerCase().trim();
    const map = {
        'new': ['badge-new', 'New'],
        'contacted': ['badge-contacted', 'Contacted'],
        'replied': ['badge-replied', 'Replied'],
        'meeting': ['badge-meeting', 'Meeting'],
        'proposal sent': ['badge-proposal', 'Proposal'],
        'closed won': ['badge-won', 'Won ✓'],
        'closed lost': ['badge-lost', 'Lost ✗'],
    };
    const [cls, label] = map[s] || ['badge-new', s];
    return `<span class="badge ${cls}">${label}</span>`;
}

// ---------------------------------------------------------------------------
// Outreach Monitor
// ---------------------------------------------------------------------------
async function loadOutreach() {
    const grid = document.getElementById('outreachGrid');
    try {
        const res = await fetch('/api/outreach');
        const data = await res.json();

        if (!data.outreach.length) {
            grid.innerHTML = '<div class="funnel-loading">No outreach data yet</div>';
            return;
        }

        grid.innerHTML = data.outreach.map(o => {
            const stepClass = (sent, isNext) => {
                if (o.reply_received) return 'replied';
                if (sent) return 'sent';
                if (isNext) return 'active';
                return '';
            };

            const nextEmail = o.email_3_sent ? 3 : o.email_2_sent ? 3 : o.email_1_sent ? 2 : 1;

            return `
                <div class="outreach-card">
                    <div class="outreach-card-header">
                        <div>
                            <div class="outreach-biz">${esc(o.business_name)}</div>
                            <div class="outreach-email">${esc(o.email)}</div>
                        </div>
                        <span class="score-pill ${scoreClass(o.score)}">${o.score}</span>
                    </div>
                    <div class="outreach-steps">
                        <div class="step-pill ${stepClass(o.email_1_sent, nextEmail === 1)}">
                            Email 1
                            <span class="step-date">${o.email_1_date || '—'}</span>
                        </div>
                        <div class="step-pill ${stepClass(o.email_2_sent, nextEmail === 2)}">
                            Email 2
                            <span class="step-date">${o.email_2_date || '—'}</span>
                        </div>
                        <div class="step-pill ${stepClass(o.email_3_sent, nextEmail === 3 && o.email_2_sent)}">
                            Email 3
                            <span class="step-date">${o.email_3_date || '—'}</span>
                        </div>
                    </div>
                    <div class="outreach-next">
                        <span class="next-label">Next:</span>
                        <span class="next-value">${esc(o.next_action)}${o.next_action_date ? ` (${o.next_action_date})` : ''}</span>
                    </div>
                </div>
            `;
        }).join('');
    } catch (e) {
        grid.innerHTML = '<div class="funnel-loading">Failed to load outreach data</div>';
    }
}

// ---------------------------------------------------------------------------
// Email Preview
// ---------------------------------------------------------------------------
async function populatePreviewDropdown() {
    try {
        const res = await fetch('/api/leads?sort=score&order=desc');
        const data = await res.json();
        const select = document.getElementById('previewLead');
        const currentVal = select.value;

        // Keep first option
        select.innerHTML = '<option value="">Select a lead…</option>';
        data.leads.forEach(l => {
            const opt = document.createElement('option');
            opt.value = l.email;
            opt.textContent = `${l.business_name} (${l.email})`;
            select.appendChild(opt);
        });

        if (currentVal) select.value = currentVal;
    } catch (e) {
        console.error('Failed to populate preview dropdown:', e);
    }
}

async function previewEmail() {
    const leadEmail = document.getElementById('previewLead').value;
    const seqNum = document.getElementById('previewSeq').value;
    const lang = document.getElementById('previewLang').value;
    const container = document.getElementById('emailPreview');

    if (!leadEmail) {
        container.innerHTML = '<div class="preview-placeholder">Select a lead to preview email</div>';
        return;
    }

    try {
        const res = await fetch('/api/email-preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lead_email: leadEmail, sequence_num: seqNum, lang }),
        });

        if (!res.ok) {
            const err = await res.json();
            container.innerHTML = `<div class="preview-placeholder" style="color:var(--danger)">${esc(err.error || 'Error')}</div>`;
            return;
        }

        const data = await res.json();
        container.innerHTML = `
            <div class="preview-to">To: ${esc(data.to)}</div>
            <div class="preview-subject">${esc(data.subject)}</div>
            <div class="preview-body">${esc(data.body)}</div>
        `;
    } catch (e) {
        container.innerHTML = '<div class="preview-placeholder" style="color:var(--danger)">Failed to load preview</div>';
    }
}

function previewLeadEmail(email) {
    // Switch to Actions tab and select the lead
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.querySelector('[data-tab="actions"]').classList.add('active');
    document.getElementById('tab-actions').classList.add('active');

    document.getElementById('previewLead').value = email;
    previewEmail();
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------
async function runAction(action, btn) {
    if (btn) {
        btn.classList.add('loading');
        btn.querySelector('.action-label').textContent = 'Running…';
    }

    appendLog(`[${timestamp()}] Running: ${action}…`);

    try {
        const res = await fetch(`/api/actions/${action}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
        });
        const data = await res.json();

        if (data.success) {
            showToast(`${action} completed successfully!`, 'success');
            appendLog(`[${timestamp()}] ✓ ${action} succeeded`);
            if (data.output) appendLog(data.output);
            if (data.synced) appendLog(`  Synced ${data.synced} leads to CRM`);
        } else {
            showToast(`${action} failed: ${data.error}`, 'error');
            appendLog(`[${timestamp()}] ✗ ${action} failed: ${data.error}`);
            if (data.output) appendLog(data.output);
        }

        // Reload data after action
        loadAll();
    } catch (e) {
        showToast(`${action} error: ${e.message}`, 'error');
        appendLog(`[${timestamp()}] ✗ Error: ${e.message}`);
    } finally {
        if (btn) {
            btn.classList.remove('loading');
            resetActionLabel(btn, action);
        }
    }
}

async function sendLive(btn) {
    if (!confirm('⚠️ This will send REAL emails to all qualified leads. Continue?')) return;
    if (btn) {
        btn.classList.add('loading');
        btn.querySelector('.action-label').textContent = 'Sending…';
    }
    appendLog(`[${timestamp()}] 🚀 Sending LIVE emails…`);

    try {
        const res = await fetch('/api/actions/send-batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dry_run: false }),
        });
        const data = await res.json();

        if (data.success) {
            showToast('Emails sent successfully!', 'success');
            appendLog(`[${timestamp()}] ✓ Live send complete`);
            if (data.output) appendLog(data.output);
        } else {
            showToast(`Send failed: ${data.error}`, 'error');
            appendLog(`[${timestamp()}] ✗ Send failed: ${data.error}`);
        }
        loadAll();
    } catch (e) {
        showToast(`Send error: ${e.message}`, 'error');
        appendLog(`[${timestamp()}] ✗ Error: ${e.message}`);
    } finally {
        if (btn) {
            btn.classList.remove('loading');
            btn.querySelector('.action-label').textContent = 'Send Live';
        }
    }
}

function resetActionLabel(btn, action) {
    const labels = {
        'scrape': 'Run Scraper',
        'qualify': 'Qualify Leads',
        'send-batch': 'Send Batch (Dry Run)',
        'sync-crm': 'Sync to CRM',
    };
    const labelEl = btn.querySelector('.action-label');
    if (labelEl) labelEl.textContent = labels[action] || action;
}

// ---------------------------------------------------------------------------
// Toast
// ---------------------------------------------------------------------------
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

// ---------------------------------------------------------------------------
// Log
// ---------------------------------------------------------------------------
function appendLog(text) {
    const log = document.getElementById('actionLog');
    log.textContent += text + '\n';
    log.scrollTop = log.scrollHeight;
}

function clearLog() {
    document.getElementById('actionLog').textContent = 'Ready.\n';
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function esc(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function formatVND(amount) {
    if (!amount) return '—';
    return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(amount);
}

function timestamp() {
    return new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
