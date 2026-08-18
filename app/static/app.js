/**
 * app.js - Campaign Rule Engine Frontend Logic
 * Minimalist Slate-900 Dashboard & Live Cart Evaluation Simulator
 */

let state = {
    rules: [],
    campaigns: [],
    gifts: [],
    coupons: [],
    currentTab: 'rules',
    lastSimulationResult: null
};

// Days of week constant
const DAYS_OF_WEEK = [
    { value: 'PAZARTESI', label: 'Pazartesi' },
    { value: 'SALI', label: 'Salı' },
    { value: 'CARSAMBA', label: 'Çarşamba' },
    { value: 'PERSEMBE', label: 'Perşembe' },
    { value: 'CUMA', label: 'Cuma' },
    { value: 'CUMARTESI', label: 'Cumartesi' },
    { value: 'PAZAR', label: 'Pazar' }
];

document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

async function initApp() {
    await refreshData();
    // Default condition row in create modal
    resetConditionRows();
}

// -------------------------------------------------------------
// Data Fetching & State
// -------------------------------------------------------------
async function refreshData() {
    try {
        const [rulesRes, campRes, giftsRes, couponsRes] = await Promise.all([
            fetch('/api/v1/kurallar'),
            fetch('/api/v1/kampanyalar'),
            fetch('/api/v1/referanslar/hediye-urunler'),
            fetch('/api/v1/referanslar/kuponlar')
        ]);

        if (rulesRes.ok) state.rules = await rulesRes.json();
        if (campRes.ok) state.campaigns = await campRes.json();
        if (giftsRes.ok) state.gifts = await giftsRes.json();
        if (couponsRes.ok) state.coupons = await couponsRes.json();

        updateMetrics();
        renderRulesTable();
        renderReferences();
        populateCampaignDropdown();
        populateReferenceDropdowns();
    } catch (err) {
        showToast('Veriler yüklenirken hata oluştu: ' + err.message, 'error');
    }
}

function updateMetrics() {
    const activeCount = state.rules.filter(r => r.durum === 'AKTIF').length;
    const totalCount = state.rules.length;
    const giftsCount = state.gifts.length;
    const couponsCount = state.coupons.length;

    document.getElementById('stat-active-rules').innerText = activeCount;
    document.getElementById('stat-total-rules').innerText = totalCount;
    document.getElementById('stat-active-gifts').innerText = giftsCount;
    document.getElementById('stat-active-coupons').innerText = couponsCount;
    document.getElementById('tab-badge-rules').innerText = totalCount;
}

// -------------------------------------------------------------
// Tab Switching
// -------------------------------------------------------------
function switchTab(tabId) {
    state.currentTab = tabId;
    const tabs = ['rules', 'simulator', 'references'];
    tabs.forEach(t => {
        const view = document.getElementById(`view-${t}`);
        const btn = document.getElementById(`tab-btn-${t}`);
        if (t === tabId) {
            view.classList.remove('hidden');
            btn.classList.add('border-slate-100', 'text-slate-100');
            btn.classList.remove('border-transparent', 'text-slate-400');
        } else {
            view.classList.add('hidden');
            btn.classList.remove('border-slate-100', 'text-slate-100');
            btn.classList.add('border-transparent', 'text-slate-400');
        }
    });
}

// -------------------------------------------------------------
// Rules Table Rendering & Priority Shift
// -------------------------------------------------------------
function renderRulesTable() {
    const tbody = document.getElementById('rules-table-body');
    if (!state.rules.length) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="text-center py-10 text-slate-500">
                    Henüz tanımlanmış bir kural bulunmuyor. Yeni bir kural oluşturun.
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = state.rules.map((rule, idx) => {
        const isFirst = idx === 0;
        const isLast = idx === state.rules.length - 1;
        const isAktif = rule.durum === 'AKTIF';

        // Action badge rendering
        let actionBadge = `<span class="px-2 py-0.5 rounded font-mono text-[11px] bg-slate-800 text-slate-300">${rule.aksiyon?.aksiyon_tipi || '-'}</span>`;
        if (rule.aksiyon) {
            const tip = rule.aksiyon.aksiyon_tipi;
            const val = rule.aksiyon.aksiyon_degeri;
            if (tip === 'YUZDE_INDIRIM') {
                actionBadge = `<span class="px-2 py-0.5 rounded font-mono text-[11px] bg-emerald-950/80 border border-emerald-800 text-emerald-300 font-semibold">%${val} İndirim</span>`;
            } else if (tip === 'SABIT_INDIRIM') {
                actionBadge = `<span class="px-2 py-0.5 rounded font-mono text-[11px] bg-emerald-950/80 border border-emerald-800 text-emerald-300 font-semibold">₺${val} İndirim</span>`;
            } else if (tip === 'UCRETSIZ_KARGO') {
                actionBadge = `<span class="px-2 py-0.5 rounded font-mono text-[11px] bg-blue-950/80 border border-blue-800 text-blue-300">📦 Ücretsiz Kargo</span>`;
            } else if (tip === 'HEDIYE_URUN_EKLE') {
                actionBadge = `<span class="px-2 py-0.5 rounded font-mono text-[11px] bg-purple-950/80 border border-purple-800 text-purple-300">🎁 Hediye Ürün</span>`;
            } else if (tip === 'KUPON_TANIMLA') {
                actionBadge = `<span class="px-2 py-0.5 rounded font-mono text-[11px] bg-amber-950/80 border border-amber-800 text-amber-300">🎟️ Kupon</span>`;
            }
        }

        // Conditions badges
        const conditionsHtml = (rule.kosullar || []).map(c => {
            let label = c.parametre;
            let displayVal = c.deger;
            if (c.parametre === 'sepet_tutari') {
                label = 'Sepet';
                displayVal = `₺${c.deger}`;
            } else if (c.parametre === 'kullanici_tipi') {
                label = 'Segment';
            } else if (c.parametre === 'islem_saati') {
                label = 'Saat';
            } else if (c.parametre === 'haftanin_gunu') {
                label = 'Gün';
            } else if (c.parametre === 'odeme_yontemi') {
                label = 'Ödeme';
            }
            return `<span class="inline-flex items-center px-2 py-0.5 rounded text-[11px] bg-slate-800/90 border border-slate-700 text-slate-300 space-x-1 mr-1 mb-1">
                <span class="text-slate-400 font-medium">${label}</span>
                <span class="text-slate-400 font-mono">${c.operator}</span>
                <span class="text-slate-200 font-semibold">${displayVal}</span>
            </span>`;
        }).join('');

        return `
            <tr class="hover:bg-slate-850/60 transition-colors ${!isAktif ? 'opacity-60' : ''}">
                <!-- Priority Column -->
                <td class="py-3 px-4 text-center">
                    <div class="inline-flex items-center justify-center w-7 h-7 rounded-full font-mono text-xs font-bold ${isAktif ? 'bg-slate-800 text-slate-100 border border-slate-700' : 'bg-slate-900 text-slate-500 border border-slate-800'}">
                        #${rule.oncelik_sirasi}
                    </div>
                </td>

                <!-- Rule & Campaign Name -->
                <td class="py-3 px-4">
                    <div class="font-semibold text-slate-100 text-sm">${escapeHtml(rule.ad)}</div>
                    <div class="text-[11px] text-slate-400">${rule.kampanya ? escapeHtml(rule.kampanya.ad) : 'Bağımsız Kural'}</div>
                </td>

                <!-- Conditions -->
                <td class="py-3 px-4">
                    <div class="flex flex-wrap items-center">
                        ${conditionsHtml || '<span class="text-slate-500 italic">Koşulsuz (Her sepete uyar)</span>'}
                    </div>
                </td>

                <!-- Action -->
                <td class="py-3 px-4">
                    ${actionBadge}
                </td>

                <!-- Status Toggle -->
                <td class="py-3 px-4 text-center">
                    <button onclick="toggleRuleStatus(${rule.id}, '${isAktif ? 'PASIF' : 'AKTIF'}')" class="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full text-xs font-medium border transition-colors ${
                        isAktif 
                        ? 'bg-emerald-950/60 border-emerald-800 text-emerald-400 hover:bg-emerald-900/60' 
                        : 'bg-slate-800 border-slate-700 text-slate-400 hover:bg-slate-750'
                    }">
                        <span class="w-1.5 h-1.5 rounded-full ${isAktif ? 'bg-emerald-400' : 'bg-slate-500'}"></span>
                        <span>${rule.durum}</span>
                    </button>
                </td>

                <!-- Actions: Up/Down Shift & Delete -->
                <td class="py-3 px-4 text-right">
                    <div class="inline-flex items-center space-x-1">
                        <button onclick="shiftRulePriority(${rule.id}, ${rule.oncelik_sirasi - 1})" ${isFirst ? 'disabled' : ''} title="Önceliği Artır (Yukarı Al)" class="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200 disabled:opacity-20 disabled:hover:bg-transparent">
                            ▲
                        </button>
                        <button onclick="shiftRulePriority(${rule.id}, ${rule.oncelik_sirasi + 1})" ${isLast ? 'disabled' : ''} title="Önceliği Azalt (Aşağı Al)" class="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200 disabled:opacity-20 disabled:hover:bg-transparent">
                            ▼
                        </button>
                        <button onclick="deleteRule(${rule.id})" title="Kuralı Sil" class="p-1.5 rounded hover:bg-red-950/60 text-slate-400 hover:text-red-400 transition-colors">
                            🗑️
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

// -------------------------------------------------------------
// References Inventory Rendering
// -------------------------------------------------------------
function renderReferences() {
    // Gifts
    const giftsBody = document.getElementById('gifts-table-body');
    giftsBody.innerHTML = state.gifts.map(g => `
        <tr class="hover:bg-slate-850/50">
            <td class="py-2.5 font-mono text-slate-400">${escapeHtml(g.stok_kodu)}</td>
            <td class="py-2.5 font-medium text-slate-200">${escapeHtml(g.urun_adi)}</td>
            <td class="py-2.5 text-center font-mono font-bold ${g.stok_adedi > 0 ? 'text-emerald-400' : 'text-red-400'}">${g.stok_adedi} adet</td>
            <td class="py-2.5 text-right">
                <span class="px-2 py-0.5 rounded text-[11px] ${g.durum === 'AKTIF' ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' : 'bg-slate-800 text-slate-400'}">${g.durum}</span>
            </td>
        </tr>
    `).join('');

    // Coupons
    const couponsBody = document.getElementById('coupons-table-body');
    couponsBody.innerHTML = state.coupons.map(c => `
        <tr class="hover:bg-slate-850/50">
            <td class="py-2.5 font-mono font-semibold text-amber-300">${escapeHtml(c.kupon_kodu)}</td>
            <td class="py-2.5 font-mono text-slate-200">₺${c.indirim_tutari}</td>
            <td class="py-2.5 text-center font-mono ${c.kullanim_limiti > 0 ? 'text-emerald-400' : 'text-red-400'}">${c.kullanim_limiti}</td>
            <td class="py-2.5 text-right">
                <span class="px-2 py-0.5 rounded text-[11px] ${c.durum === 'AKTIF' ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' : 'bg-slate-800 text-slate-400'}">${c.durum}</span>
            </td>
        </tr>
    `).join('');
}

// -------------------------------------------------------------
// Dropdowns Population
// -------------------------------------------------------------
function populateCampaignDropdown() {
    const select = document.getElementById('form-campaign-id');
    select.innerHTML = '<option value="">-- Kampanyasız / Bağımsız --</option>' +
        state.campaigns.map(c => `<option value="${c.id}">${escapeHtml(c.ad)}</option>`).join('');
}

function populateReferenceDropdowns() {
    const giftSelect = document.getElementById('form-gift-id');
    const couponSelect = document.getElementById('form-coupon-id');

    giftSelect.innerHTML = '<option value="">-- Stoklu Hediye Seçin --</option>' +
        state.gifts.filter(g => g.durum === 'AKTIF' && g.stok_adedi > 0)
                   .map(g => `<option value="${g.id}">${escapeHtml(g.urun_adi)} (${g.stok_adedi} Stok)</option>`).join('');

    couponSelect.innerHTML = '<option value="">-- Geçerli Kupon Seçin --</option>' +
        state.coupons.filter(c => c.durum === 'AKTIF' && c.kullanim_limiti > 0)
                     .map(c => `<option value="${c.id}">${escapeHtml(c.kupon_kodu)} (₺${c.indirim_tutari} İndirim - ${c.kullanim_limiti} Limit)</option>`).join('');
}

// -------------------------------------------------------------
// Rule Creation / Modal Form Strict Constraints
// -------------------------------------------------------------
function openCreateRuleModal() {
    document.getElementById('modal-title').innerText = 'Yeni Kampanya Kuralı Tanımla';
    document.getElementById('form-rule-id').value = '';
    document.getElementById('form-rule-name').value = '';
    document.getElementById('form-campaign-id').value = '';
    document.getElementById('form-priority').value = '';
    document.getElementById('form-status').value = 'PASIF';
    document.getElementById('form-action-type').value = 'YUZDE_INDIRIM';
    document.getElementById('form-action-value').value = '';
    document.getElementById('modal-error').classList.add('hidden');

    handleActionTypeChange();
    resetConditionRows();
    document.getElementById('rule-modal').classList.remove('hidden');
}

function closeRuleModal() {
    document.getElementById('rule-modal').classList.add('hidden');
}

function resetConditionRows() {
    const container = document.getElementById('conditions-container');
    container.innerHTML = '';
    addConditionRow('sepet_tutari', '>=', '500');
}

function addConditionRow(defaultParam = 'sepet_tutari', defaultOp = '>=', defaultVal = '') {
    const container = document.getElementById('conditions-container');
    const rowIndex = Date.now() + Math.random().toString(36).substr(2, 5);

    const row = document.createElement('div');
    row.id = `cond-row-${rowIndex}`;
    row.className = 'grid grid-cols-12 gap-2 items-center bg-slate-900 border border-slate-800 p-2.5 rounded';

    row.innerHTML = `
        <div class="col-span-4">
            <select class="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-slate-200 text-xs focus:outline-none focus:border-slate-500 param-select" onchange="handleParamChange('${rowIndex}')">
                <option value="sepet_tutari" ${defaultParam === 'sepet_tutari' ? 'selected' : ''}>sepet_tutari</option>
                <option value="kullanici_tipi" ${defaultParam === 'kullanici_tipi' ? 'selected' : ''}>kullanici_tipi</option>
                <option value="odeme_yontemi" ${defaultParam === 'odeme_yontemi' ? 'selected' : ''}>odeme_yontemi</option>
                <option value="haftanin_gunu" ${defaultParam === 'haftanin_gunu' ? 'selected' : ''}>haftanin_gunu</option>
                <option value="islem_saati" ${defaultParam === 'islem_saati' ? 'selected' : ''}>islem_saati</option>
            </select>
        </div>
        <div class="col-span-3">
            <select class="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-slate-200 text-xs font-mono focus:outline-none focus:border-slate-500 op-select" onchange="handleOperatorChange('${rowIndex}')">
            </select>
        </div>
        <div class="col-span-4 val-container">
        </div>
        <div class="col-span-1 text-right">
            <button type="button" onclick="removeConditionRow('${rowIndex}')" class="text-slate-500 hover:text-red-400 text-sm font-bold">&times;</button>
        </div>
    `;

    container.appendChild(row);
    renderOperatorAndValueInput(rowIndex, defaultParam, defaultOp, defaultVal);
}

function removeConditionRow(rowIndex) {
    const row = document.getElementById(`cond-row-${rowIndex}`);
    if (row) row.remove();
}

function handleParamChange(rowIndex) {
    const row = document.getElementById(`cond-row-${rowIndex}`);
    const param = row.querySelector('.param-select').value;
    renderOperatorAndValueInput(rowIndex, param);
}

function handleOperatorChange(rowIndex) {
    const row = document.getElementById(`cond-row-${rowIndex}`);
    const param = row.querySelector('.param-select').value;
    const op = row.querySelector('.op-select').value;
    renderValueInput(rowIndex, param, op);
}

function renderOperatorAndValueInput(rowIndex, param, selectedOp = null, selectedVal = '') {
    const row = document.getElementById(`cond-row-${rowIndex}`);
    const opSelect = row.querySelector('.op-select');

    // Strict Operator mappings
    let ops = [];
    if (param === 'sepet_tutari') {
        ops = [
            { val: '>=', label: '>=' },
            { val: '<=', label: '<=' },
            { val: '>', label: '>' },
            { val: '<', label: '<' },
            { val: '==', label: '==' }
        ];
    } else if (param === 'kullanici_tipi' || param === 'odeme_yontemi') {
        ops = [{ val: '==', label: '==' }];
    } else if (param === 'haftanin_gunu') {
        ops = [
            { val: '==', label: '==' },
            { val: 'ICINDEDIR', label: 'ICINDEDIR' }
        ];
    } else if (param === 'islem_saati') {
        ops = [
            { val: '>=', label: '>=' },
            { val: '<=', label: '<=' },
            { val: '==', label: '==' }
        ];
    }

    opSelect.innerHTML = ops.map(o => `<option value="${o.val}" ${selectedOp === o.val ? 'selected' : ''}>${o.label}</option>`).join('');
    renderValueInput(rowIndex, param, opSelect.value, selectedVal);
}

function renderValueInput(rowIndex, param, op, selectedVal = '') {
    const row = document.getElementById(`cond-row-${rowIndex}`);
    const valContainer = row.querySelector('.val-container');

    if (param === 'sepet_tutari') {
        valContainer.innerHTML = `
            <input type="number" step="0.01" min="0" required class="val-input w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-slate-100 text-xs font-mono focus:outline-none focus:border-slate-500" placeholder="Tutar" value="${selectedVal || '500'}">
        `;
    } else if (param === 'kullanici_tipi') {
        valContainer.innerHTML = `
            <select required class="val-input w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-slate-100 text-xs focus:outline-none focus:border-slate-500">
                <option value="VIP" ${selectedVal === 'VIP' ? 'selected' : ''}>VIP</option>
                <option value="STANDART" ${selectedVal === 'STANDART' || !selectedVal ? 'selected' : ''}>STANDART</option>
                <option value="YENI" ${selectedVal === 'YENI' ? 'selected' : ''}>YENI</option>
            </select>
        `;
    } else if (param === 'odeme_yontemi') {
        valContainer.innerHTML = `
            <select required class="val-input w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-slate-100 text-xs focus:outline-none focus:border-slate-500">
                <option value="KREDI_KARTI" ${selectedVal === 'KREDI_KARTI' || !selectedVal ? 'selected' : ''}>KREDI_KARTI</option>
                <option value="HAVALE" ${selectedVal === 'HAVALE' ? 'selected' : ''}>HAVALE</option>
                <option value="KAPIDA_ODEME" ${selectedVal === 'KAPIDA_ODEME' ? 'selected' : ''}>KAPIDA_ODEME</option>
            </select>
        `;
    } else if (param === 'haftanin_gunu') {
        if (op === '==') {
            valContainer.innerHTML = `
                <select required class="val-input w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-slate-100 text-xs focus:outline-none focus:border-slate-500">
                    ${DAYS_OF_WEEK.map(d => `<option value="${d.value}" ${selectedVal === d.value ? 'selected' : ''}>${d.value}</option>`).join('')}
                </select>
            `;
        } else {
            // ICINDEDIR - dropdown with quick weekend or custom string
            valContainer.innerHTML = `
                <select required class="val-input w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-slate-100 text-xs focus:outline-none focus:border-slate-500">
                    <option value="CUMARTESI,PAZAR" ${selectedVal === 'CUMARTESI,PAZAR' || !selectedVal ? 'selected' : ''}>Hafta Sonu (Cmt, Paz)</option>
                    <option value="PAZARTESI,SALI,CARSAMBA,PERSEMBE,CUMA" ${selectedVal === 'PAZARTESI,SALI,CARSAMBA,PERSEMBE,CUMA' ? 'selected' : ''}>Hafta İçi (Pzt-Cum)</option>
                    <option value="CUMA,CUMARTESI,PAZAR" ${selectedVal === 'CUMA,CUMARTESI,PAZAR' ? 'selected' : ''}>Cuma + Hafta Sonu</option>
                </select>
            `;
        }
    } else if (param === 'islem_saati') {
        valContainer.innerHTML = `
            <input type="time" required class="val-input w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-slate-100 text-xs font-mono focus:outline-none focus:border-slate-500" value="${selectedVal || '22:00'}">
        `;
    }
}

function handleActionTypeChange() {
    const actionType = document.getElementById('form-action-type').value;
    const valueWrapper = document.getElementById('action-value-wrapper');
    const giftWrapper = document.getElementById('action-gift-wrapper');
    const couponWrapper = document.getElementById('action-coupon-wrapper');
    const valueLabel = document.getElementById('action-value-label');
    const valueInput = document.getElementById('form-action-value');

    valueWrapper.classList.add('hidden');
    giftWrapper.classList.add('hidden');
    couponWrapper.classList.add('hidden');

    if (actionType === 'YUZDE_INDIRIM') {
        valueWrapper.classList.remove('hidden');
        valueLabel.innerText = 'İndirim Yüzdesi (% 1-100)';
        valueInput.placeholder = 'Örn: 10';
        valueInput.min = '1';
        valueInput.max = '100';
    } else if (actionType === 'SABIT_INDIRIM') {
        valueWrapper.classList.remove('hidden');
        valueLabel.innerText = 'Sabit İndirim Tutarı (TL)';
        valueInput.placeholder = 'Örn: 150';
        valueInput.removeAttribute('max');
    } else if (actionType === 'HEDIYE_URUN_EKLE') {
        giftWrapper.classList.remove('hidden');
    } else if (actionType === 'KUPON_TANIMLA') {
        couponWrapper.classList.remove('hidden');
    }
}

// -------------------------------------------------------------
// Save Rule API Call
// -------------------------------------------------------------
async function saveRule() {
    const errorDiv = document.getElementById('modal-error');
    errorDiv.classList.add('hidden');

    const name = document.getElementById('form-rule-name').value.trim();
    const campaignId = document.getElementById('form-campaign-id').value;
    const priorityVal = document.getElementById('form-priority').value;
    const status = document.getElementById('form-status').value;
    const actionType = document.getElementById('form-action-type').value;

    if (!name) {
        showModalError('Lütfen bir kural adı girin.');
        return;
    }

    // Collect conditions
    const conditionRows = document.querySelectorAll('#conditions-container > div');
    if (!conditionRows.length) {
        showModalError('En az 1 adet koşul eklenmelidir.');
        return;
    }

    const kosullar = [];
    for (const row of conditionRows) {
        const param = row.querySelector('.param-select').value;
        const op = row.querySelector('.op-select').value;
        const valInput = row.querySelector('.val-input');
        const val = valInput ? valInput.value.trim() : '';

        if (!val) {
            showModalError(`'${param}' koşulu için bir değer belirtilmelidir.`);
            return;
        }
        kosullar.push({ parametre: param, operator: op, deger: val });
    }

    // Collect action
    const aksiyon = { aksiyon_tipi: actionType };
    if (actionType === 'YUZDE_INDIRIM' || actionType === 'SABIT_INDIRIM') {
        const val = parseFloat(document.getElementById('form-action-value').value);
        if (isNaN(val) || val <= 0) {
            showModalError('Geçerli bir indirim tutarı / yüzdesi girin.');
            return;
        }
        aksiyon.aksiyon_degeri = val;
    } else if (actionType === 'HEDIYE_URUN_EKLE') {
        const giftId = parseInt(document.getElementById('form-gift-id').value);
        if (!giftId) {
            showModalError('Lütfen listeden aktif bir hediye ürün seçin.');
            return;
        }
        aksiyon.hediye_urun_id = giftId;
    } else if (actionType === 'KUPON_TANIMLA') {
        const couponId = parseInt(document.getElementById('form-coupon-id').value);
        if (!couponId) {
            showModalError('Lütfen listeden geçerli bir kupon şablonu seçin.');
            return;
        }
        aksiyon.kupon_sablon_id = couponId;
    }

    const payload = {
        ad: name,
        kampanya_id: campaignId ? parseInt(campaignId) : null,
        oncelik_sirasi: priorityVal ? parseInt(priorityVal) : null,
        durum: status,
        kosullar: kosullar,
        aksiyon: aksiyon
    };

    try {
        const res = await fetch('/api/v1/kurallar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await res.json();
        if (!res.ok) {
            const errorMsg = data.message || data.detail || 'Kural kaydedilemedi.';
            showModalError(errorMsg);
            return;
        }

        closeRuleModal();
        await refreshData();
        showToast(`Kural başarıyla oluşturuldu (${data.durum})`, 'success');
    } catch (err) {
        showModalError('Ağ hatası: ' + err.message);
    }
}

function showModalError(msg) {
    const errorDiv = document.getElementById('modal-error');
    errorDiv.innerText = msg;
    errorDiv.classList.remove('hidden');
}

// -------------------------------------------------------------
// Quick Actions (Toggle Status, Priority Shift, Delete)
// -------------------------------------------------------------
async function toggleRuleStatus(ruleId, newStatus) {
    try {
        const res = await fetch(`/api/v1/kurallar/${ruleId}/durum`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ durum: newStatus })
        });
        if (res.ok) {
            await refreshData();
            showToast(`Kural durumu '${newStatus}' olarak güncellendi.`, 'info');
        } else {
            const err = await res.json();
            showToast(err.detail || 'Durum değiştirilemedi.', 'error');
        }
    } catch (err) {
        showToast('Hata: ' + err.message, 'error');
    }
}

async function shiftRulePriority(ruleId, newPriority) {
    if (newPriority < 1) return;
    try {
        const res = await fetch(`/api/v1/kurallar/${ruleId}/oncelik`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ yeni_oncelik: newPriority })
        });
        if (res.ok) {
            await refreshData();
            showToast(`Öncelik sırası #${newPriority} olarak güncellendi.`, 'info');
        } else {
            const err = await res.json();
            showToast(err.detail || 'Sıra güncellenemedi.', 'error');
        }
    } catch (err) {
        showToast('Hata: ' + err.message, 'error');
    }
}

async function deleteRule(ruleId) {
    if (!confirm('Bu kuralı silmek istediğinize emin misiniz?')) return;
    try {
        const res = await fetch(`/api/v1/kurallar/${ruleId}`, {
            method: 'DELETE'
        });
        if (res.ok) {
            await refreshData();
            showToast('Kural başarıyla silindi.', 'info');
        } else {
            showToast('Kural silinemedi.', 'error');
        }
    } catch (err) {
        showToast('Hata: ' + err.message, 'error');
    }
}

// -------------------------------------------------------------
// Cart Simulation Engine Call
// -------------------------------------------------------------
async function runSimulation() {
    const sepetTutari = parseFloat(document.getElementById('sim_sepet_tutari').value);
    const kullaniciTipi = document.getElementById('sim_kullanici_tipi').value;
    const odemeYontemi = document.getElementById('sim_odeme_yontemi').value;
    const haftaninGunu = document.getElementById('sim_haftanin_gunu').value;
    const islemSaati = document.getElementById('sim_islem_saati').value;

    const payload = {
        sepet_tutari: isNaN(sepetTutari) ? 0 : sepetTutari,
        kullanici_tipi: kullaniciTipi,
        odeme_yontemi: odemeYontemi,
        haftanin_gunu: haftaninGunu,
        islem_saati: islemSaati
    };

    const startTime = performance.now();

    try {
        const res = await fetch('/api/v1/kampanya/degerlendir', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const execTime = (performance.now() - startTime).toFixed(1);
        const data = await res.json();
        state.lastSimulationResult = data;

        document.getElementById('sim-exec-time').innerText = `${execTime} ms`;
        document.getElementById('json-viewer').innerText = JSON.stringify(data, null, 2);

        // Update presentation card
        const origEl = document.getElementById('res-orig-price');
        const discEl = document.getElementById('res-discount');
        const finalEl = document.getElementById('res-final-price');
        const statusBadge = document.getElementById('sim-status-badge');
        const hitBadge = document.getElementById('sim-hit-badge');
        const benefitBox = document.getElementById('sim-benefit-box');
        const msgBox = document.getElementById('sim-message-box');
        const extraRow = document.getElementById('res-extra-benefit-row');
        const extraVal = document.getElementById('res-extra-benefit-val');

        if (!res.ok) {
            statusBadge.innerText = `Hata (${res.status})`;
            statusBadge.className = 'px-2.5 py-0.5 rounded text-xs font-mono font-medium bg-red-950 border border-red-800 text-red-400';
            hitBadge.classList.add('hidden');
            benefitBox.classList.add('hidden');
            msgBox.innerText = data.message || 'Geçersiz parametre girişi.';
            return;
        }

        origEl.innerText = `₺${(data.orijinal_tutar || 0).toFixed(2)}`;
        discEl.innerText = `₺${(data.indirim_tutari || 0).toFixed(2)}`;
        finalEl.innerText = `₺${(data.odenecek_tutar || 0).toFixed(2)}`;

        if (data.fallback_applied) {
            statusBadge.innerText = 'Fallback (0 TL İndirim)';
            statusBadge.className = 'px-2.5 py-0.5 rounded text-xs font-mono font-medium bg-amber-950 border border-amber-800 text-amber-400';
            hitBadge.classList.add('hidden');
            benefitBox.classList.add('hidden');
            msgBox.innerText = data.mesaj || 'Sunucu koruması devreye girdi.';
            return;
        }

        if (data.uygulanan_kural_id) {
            statusBadge.innerText = '200 OK - İndirim Uygulandı';
            statusBadge.className = 'px-2.5 py-0.5 rounded text-xs font-mono font-medium bg-emerald-950 border border-emerald-800 text-emerald-400';
            hitBadge.classList.remove('hidden');
            hitBadge.innerText = `Kural #${data.uygulanan_kural_id} Kazandı`;
            benefitBox.classList.remove('hidden');

            document.getElementById('res-rule-name').innerText = data.kampanya_adi || `Kural #${data.uygulanan_kural_id}`;
            document.getElementById('res-action-type').innerText = data.aksiyon_tipi;

            if (data.ek_fayda) {
                extraRow.classList.remove('hidden');
                extraVal.innerText = data.ek_fayda.aciklama || data.ek_fayda.urun_adi || data.ek_fayda.kupon_kodu || JSON.stringify(data.ek_fayda);
            } else {
                extraRow.classList.add('hidden');
            }

            msgBox.innerText = data.mesaj || 'Kampanya başarıyla sepete uygulandı.';
        } else {
            statusBadge.innerText = '200 OK - 0 TL İndirim';
            statusBadge.className = 'px-2.5 py-0.5 rounded text-xs font-mono font-medium bg-slate-800 text-slate-300';
            hitBadge.classList.add('hidden');
            benefitBox.classList.add('hidden');
            msgBox.innerText = data.mesaj || 'Hiçbir kampanya kuralı eşleşmedi.';
        }

    } catch (err) {
        document.getElementById('sim-status-badge').innerText = 'Bağlantı Hatası';
        document.getElementById('sim-message-box').innerText = 'Servise ulaşılamadı: ' + err.message;
    }
}

function loadScenario(type) {
    if (type === 'weekend_discount') {
        document.getElementById('sim_sepet_tutari').value = '600.00';
        document.getElementById('sim_kullanici_tipi').value = 'STANDART';
        document.getElementById('sim_odeme_yontemi').value = 'KREDI_KARTI';
        document.getElementById('sim_haftanin_gunu').value = 'PAZAR';
        document.getElementById('sim_islem_saati').value = '14:30';
    } else if (type === 'vip_order') {
        document.getElementById('sim_sepet_tutari').value = '1200.00';
        document.getElementById('sim_kullanici_tipi').value = 'VIP';
        document.getElementById('sim_odeme_yontemi').value = 'KREDI_KARTI';
        document.getElementById('sim_haftanin_gunu').value = 'CARSAMBA';
        document.getElementById('sim_islem_saati').value = '15:00';
    } else if (type === 'night_order') {
        document.getElementById('sim_sepet_tutari').value = '400.00';
        document.getElementById('sim_kullanici_tipi').value = 'STANDART';
        document.getElementById('sim_odeme_yontemi').value = 'HAVALE';
        document.getElementById('sim_haftanin_gunu').value = 'PERSEMBE';
        document.getElementById('sim_islem_saati').value = '23:30';
    } else if (type === 'gift_cart') {
        document.getElementById('sim_sepet_tutari').value = '800.00';
        document.getElementById('sim_kullanici_tipi').value = 'STANDART';
        document.getElementById('sim_odeme_yontemi').value = 'KREDI_KARTI';
        document.getElementById('sim_haftanin_gunu').value = 'SALI';
        document.getElementById('sim_islem_saati').value = '16:00';
    }
    runSimulation();
}

function copyJsonResponse() {
    if (!state.lastSimulationResult) return;
    navigator.clipboard.writeText(JSON.stringify(state.lastSimulationResult, null, 2));
    showToast('JSON yanıtı panoya kopyalandı.', 'info');
}

// -------------------------------------------------------------
// Toast & Utility Helpers
// -------------------------------------------------------------
let toastTimer = null;
function showToast(message, type = 'info') {
    const toast = document.getElementById('toast');
    const toastMsg = document.getElementById('toast-msg');
    const toastIcon = document.getElementById('toast-icon');

    toastMsg.innerText = message;
    toast.className = 'fixed bottom-5 right-5 z-50 max-w-sm px-4 py-3 rounded-lg border shadow-xl text-xs font-medium transition-all duration-300 transform translate-y-0 ';

    if (type === 'success') {
        toast.classList.add('bg-slate-900', 'border-emerald-700', 'text-emerald-300');
        toastIcon.innerText = '✓';
    } else if (type === 'error') {
        toast.classList.add('bg-slate-900', 'border-red-800', 'text-red-300');
        toastIcon.innerText = '⚠️';
    } else {
        toast.classList.add('bg-slate-900', 'border-slate-700', 'text-slate-200');
        toastIcon.innerText = 'ℹ️';
    }

    toast.classList.remove('hidden');

    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
        toast.classList.add('hidden');
    }, 4000);
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}
