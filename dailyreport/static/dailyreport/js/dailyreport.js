/* -------------------------------------------------------
 * Driver Daily Report (stable) 
 * - 保留既有功能
 * - 新增行级ETC三字段(乘車/空車/負担)的小计聚合与开关
 * -----------------------------------------------------*/

// ===== 页面闸门：只在“司机日報编辑页”生效 =====
(function () {
  const root =
    document.querySelector("table.report-table") ||
    document.querySelector("#smart-hint-panel")?.closest("form");
  if (!root) {
    console.debug("dailyreport.js: not driver dailyreport page, abort.");
    return;
  }
  window.__DR_ROOT__ = root;
})();

// ====== 工具函数 ======
const ENABLE_LIVE_SORT = false;  // 是否启用“同一时间点自动排序”（默认关闭）
function $(sel, root) { return (root || document).querySelector(sel); }
function $all(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }
function getRow(el) { return el?.closest("tr.report-item-row") || el?.closest("tr"); }
function toInt(v, fallback = 0) { const n = parseInt(String(v ?? "").replace(/[^\d-]/g, ""), 10); return Number.isFinite(n) ? n : fallback; }
function _yen(v) { if (v == null) return 0; const n = Number(String(v).replace(/[,，\s]/g, "")); return isFinite(n) ? n : 0; }
function idText(id, n) { const el = document.getElementById(id); if (el) el.textContent = Number(n || 0).toLocaleString(); }

// ====== flatpickr 初始化（仅一次） ======
function initFlatpickr(root) {
  if (typeof flatpickr === 'function') {
    flatpickr($all(".time-input", root), {
      enableTime: true, noCalendar: true, dateFormat: "H:i",
      time_24hr: true, locale: "ja"
    });
  }
}

// ====== 保底：时间控件初始化（确保 .time-input 都挂上 flatpickr） ======
function initFlatpickr(root) {
  try {
    if (typeof flatpickr === 'function') {
      flatpickr((root || document).querySelectorAll(".time-input"), {
        enableTime: true,
        noCalendar: true,
        dateFormat: "H:i",
        time_24hr: true,
        locale: "ja"
      });
    }
  } catch (e) {
    // 静默失败，防止影响其他逻辑
  }
}

// ====== 空車ETC（回程）詳細卡片的显隐判断 ======
// 规则：当“行级空車ETC”总和 > 0 时显示，否则隐藏。
// 注意：只统计未被 DELETE 且非待入(is_pending)的行。
function evaluateEmptyEtcDetailVisibility() {
  const card = document.getElementById('empty-etc-detail-card'); // ← 模板会加这个 id
  if (!card) return;

  let emptySum = 0;
  $all("tr.report-item-row").forEach(row => {
    const delFlag = row.querySelector("input[name$='-DELETE']");
    if ((delFlag && delFlag.checked) || row.style.display === "none") return;
    const isPending = (row.querySelector("input[name$='-is_pending']") || row.querySelector(".pending-checkbox"))?.checked;
    if (isPending) return;
    const emptyEtc = toInt(row.querySelector(".etc-empty-input")?.value, 0);
    if (emptyEtc > 0) emptySum += emptyEtc;
  });

  card.style.display = emptySum > 0 ? '' : 'none';
}


// ====== 工时计算 ======
function updateDuration() {
  const form = document.querySelector('form[method="post"]') || document;
  const inEl = $("input[name='clock_in']", form);
  const outEl = $("input[name='clock_out']", form);
  const workDisplay = $("#work-duration", form);
  const actualDisplay = $("#actual-work-time", form);
  const overtimeDisplay = $("#overtime", form);
  const breakTimeDisplay = $("#break-time-display", form);
  const breakTimeHidden = $("#break-time-plus20", form);
  if (!inEl || !outEl) return;

  const [h1, m1] = (inEl.value || "00:00").split(":").map(Number);
  const [h2, m2] = (outEl.value || "00:00").split(":").map(Number);
  let d1 = new Date(0, 0, 0, h1 || 0, m1 || 0);
  let d2 = new Date(0, 0, 0, h2 || 0, m2 || 0);
  if (d2 <= d1) d2.setDate(d2.getDate() + 1);
  const workMin = Math.floor((d2 - d1) / 60000);

  let breakMin = 0;
  const breakEl = $("#break-time-input", form);
  if (breakEl && breakEl.value) {
    const [bh, bm] = breakEl.value.split(":").map(Number);
    breakMin = (bh || 0) * 60 + (bm || 0);
  }

  const realBreak = breakMin + 20;  // 规则：输入休憩 + 20分
  const actualMin = workMin - realBreak;
  const overtimeMin = actualMin - 480;

  const toHM = m => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(Math.max(0, m) % 60).padStart(2, '0')}`;
  if (workDisplay) workDisplay.textContent = toHM(workMin);
  if (actualDisplay) actualDisplay.textContent = toHM(actualMin);
  if (overtimeDisplay) {
    overtimeDisplay.textContent = (overtimeMin < 0 ? "-" : "") + toHM(Math.abs(overtimeMin));
    overtimeDisplay.style.color = overtimeMin >= 0 ? "red" : "blue";
  }
  if (breakTimeDisplay) breakTimeDisplay.textContent = toHM(realBreak);
  if (breakTimeHidden) breakTimeHidden.value = toHM(realBreak);
}

// ====== 行号刷新 ======
function updateRowNumbersAndIndexes() {
  const table = document.querySelector('table.report-table');
  const rows = $all("tr.report-item-row", table).filter(r => r.style.display !== "none");
  rows.forEach((row, i) => { row.querySelector(".row-number")?.replaceChildren(document.createTextNode(i + 1)); });
}

// ====== 同时刻缩进 ======
function updateSameTimeGrouping() {
  const table = document.querySelector('table.report-table');
  const rows = $all("tr.report-item-row", table).filter(r => r.style.display !== "none");
  const groups = Object.create(null);
  rows.forEach(row => {
    const timeInput = row.querySelector("input[name$='-ride_time']") || row.querySelector(".time-input");
    const t = (timeInput ? String(timeInput.value).trim() : "");
    const key = t || "__EMPTY__";
    (groups[key] ||= []).push(row);
  });
  Object.entries(groups).forEach(([key, arr]) => {
    arr.forEach(row => {
      row.classList.remove("same-time-child");
      const timeInput = row.querySelector("input[name$='-ride_time']") || row.querySelector(".time-input");
      const cell = timeInput?.closest("td");
      if (!cell) return;
      const pref = cell.querySelector(".same-time-prefix"); if (pref) pref.remove();
    });
    if (key === "__EMPTY__") return;
    if (arr.length > 1) {
      arr.forEach((row, idx) => {
        if (idx === 0) return;
        row.classList.add("same-time-child");
        const timeInput = row.querySelector("input[name$='-ride_time']") || row.querySelector(".time-input");
        const cell = timeInput?.closest("td"); if (!cell) return;
        const span = document.createElement("span");
        span.className = "same-time-prefix"; span.textContent = "↳ ";
        cell.insertBefore(span, timeInput);
      });
    }
  });
}

// ====== 貸切联动 ======
function applyCharterState(row, isCharter) {
  if (!row) return;
  const meterInput = row.querySelector(".meter-fee-input");
  const charterAmountInput = row.querySelector(".charter-amount-input");
  const charterPaymentSelect = row.querySelector(".charter-payment-method-select");
  if (meterInput) {
    meterInput.removeAttribute('disabled');
    if (!meterInput.dataset.originalValue) meterInput.dataset.originalValue = meterInput.value || "";
    if (isCharter) {
      meterInput.setAttribute('readonly', 'readonly');
      meterInput.classList.add('readonly');
      meterInput.value = meterInput.dataset.originalValue;
    } else {
      meterInput.removeAttribute('readonly');
      meterInput.classList.remove('readonly');
    }
  }
  if (!isCharter) {
    if (charterAmountInput) {
      charterAmountInput.value = "";
      charterAmountInput.dispatchEvent(new Event('input', { bubbles: true }));
      charterAmountInput.dispatchEvent(new Event('change', { bubbles: true }));
    }
    if (charterPaymentSelect) {
      charterPaymentSelect.value = "";
      charterPaymentSelect.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }
}

// ====== 行事件绑定（保留旧功能 + 新增ETC联动） ======
function bindRowEvents(row) {
  initFlatpickr(row);

  // 删除（软删除）
  $all(".delete-row", row).forEach(btn => {
    btn.addEventListener("click", () => {
      if (!confirm("确定删除此行？")) return;
      const cb = row.querySelector("input[name$='-DELETE']");
      if (cb) {
        cb.checked = true;
        row.style.display = "none";
        updateRowNumbersAndIndexes();
        updateSameTimeGrouping();
        updateTotals();
        evaluateEmptyEtcDetailVisibility();   // ★ 新增：删行后重新判断是否显示空車ETC卡片
      }
    });
  });

  // 临时新行移除
  $all(".remove-row", row).forEach(btn => {
    btn.addEventListener("click", () => {
      if (!confirm("确定移除此行？")) return;
      const cb = row.querySelector("input[name$='-DELETE']");
      if (cb) { cb.checked = true; row.style.display = "none"; }
      else { row.remove(); }
      updateRowNumbersAndIndexes();
      updateSameTimeGrouping();
      updateTotals();
      evaluateEmptyEtcDetailVisibility();     // ★ 新增
    });
  });

  // 关键字段联动
  const amountInput = row.querySelector(".meter-fee-input");
  const methodSelect = row.querySelector("select[name$='-payment_method']");
  const pendingCb = row.querySelector("input[name$='-is_pending']") || row.querySelector(".pending-checkbox");
  const pendingHint = row.querySelector(".pending-mini-hint");
  const charterAmountInput = row.querySelector(".charter-amount-input");
  const charterCheckbox = row.querySelector("input[name$='-is_charter']");
  const rideTimeInput = row.querySelector("input[name$='-ride_time']") || row.querySelector(".time-input");

  if (amountInput) amountInput.addEventListener("input", () => updateTotals());
  if (methodSelect) methodSelect.addEventListener("change", () => updateTotals());
  if (pendingCb) {
    pendingCb.addEventListener("change", () => {
      if (pendingHint) pendingHint.classList.toggle("d-none", !pendingCb.checked);
      updateTotals();
      evaluateEmptyEtcDetailVisibility();     // ★ 待入改变也可能影响统计，稳妥起见一起判断
    });
    if (pendingHint) pendingHint.classList.toggle("d-none", !pendingCb.checked);
  }
  if (charterAmountInput) charterAmountInput.addEventListener("input", updateTotals);
  if (charterCheckbox) {
    charterCheckbox.addEventListener("change", () => {
      applyCharterState(row, charterCheckbox.checked);
      updateTotals();
      evaluateEmptyEtcDetailVisibility();     // ★ 新增（虽然与ETC无直接关系，但行隐藏/金额变化时更稳妥）
    });
    applyCharterState(row, charterCheckbox.checked);
  }
  if (rideTimeInput) {
    const onTimeChanged = () => {
      if (ENABLE_LIVE_SORT && typeof window.__resortByTime === 'function') window.__resortByTime();
      updateRowNumbersAndIndexes();
      updateSameTimeGrouping();
    };
    rideTimeInput.addEventListener("change", onTimeChanged);
    rideTimeInput.addEventListener("input", onTimeChanged);
  }

  // ✅ 行级ETC 三字段联动（乘車ETC/空車ETC/負担）
  $all(".etc-riding-input, .etc-empty-input, .etc-charge-type-select", row).forEach(el => {
    el.addEventListener("input", () => { 
      updateTotals();
      evaluateEmptyEtcDetailVisibility();     // ★ 核心：ETC字段改动后，立即判断卡片显隐
    });
    el.addEventListener("change", () => { 
      updateTotals();
      evaluateEmptyEtcDetailVisibility();     // ★ 核心
    });
  });
}


// ====== 模板克隆/插入 ======
function cloneRowFromTemplate() {
  const tpl = document.querySelector('#empty-form-template');
  const total = document.querySelector("input[name$='-TOTAL_FORMS']");
  if (!tpl || !total) return null;
  const count = parseInt(total.value || '0', 10) || 0;
  const tmp = document.createElement('tbody');
  tmp.innerHTML = tpl.innerHTML.replace(/__prefix__/g, count).replace(/__num__/g, count + 1);
  const tr = tmp.querySelector('tr'); if (!tr) return null;
  tr.classList.remove('d-none', 'hidden', 'invisible', 'template-row');
  tr.style.removeProperty('display'); tr.removeAttribute('aria-hidden');
  tr.querySelectorAll('input,select,textarea,button').forEach(el => { el.disabled = false; el.removeAttribute('disabled'); });
  total.value = String(count + 1);
  return tr;
}
function addRowToEnd() {
  const dataTb = document.querySelector('table.report-table tbody:not(#empty-form-template)');
  if (!dataTb) return false;
  const tr = cloneRowFromTemplate(); if (!tr) return false;
  dataTb.appendChild(tr); bindRowEvents(tr);
  updateRowNumbersAndIndexes(); updateSameTimeGrouping(); updateTotals();
  try { tr.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch (e) { }
  (tr.querySelector('.time-input') || tr.querySelector('input,select'))?.focus?.();
  return true;
}
function insertRowAfter(indexOneBased) {
  const dataTb = document.querySelector('table.report-table tbody:not(#empty-form-template)');
  if (!dataTb) return false;
  const tr = cloneRowFromTemplate(); if (!tr) return false;
  const rows = $all("tr.report-item-row", dataTb);
  const all = rows.length ? rows : $all("tr", dataTb);
  if (all.length === 0) dataTb.appendChild(tr);
  else {
    const n = Math.min(Math.max(1, indexOneBased || 1), all.length);
    const anchor = all[n - 1]; (anchor.parentNode || dataTb).insertBefore(tr, anchor.nextSibling);
  }
  bindRowEvents(tr);
  updateRowNumbersAndIndexes(); updateSameTimeGrouping(); updateTotals();
  try { tr.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch (e) { }
  (tr.querySelector('.time-input') || tr.querySelector('input,select'))?.focus?.();
  return true;
}

// ====== 支付方式归一化（保留旧口径） ======
function resolveJsPaymentMethod(raw) {
  if (!raw) return "";
  const val = String(raw).trim();
  const exact = {
    cash: "cash", uber_cash: "cash", didi_cash: "cash", go_cash: "cash",
    uber: "uber", didi: "didi", go: "go",
    credit_card: "credit", kyokushin: "kyokushin", omron: "omron", kyotoshi: "kyotoshi", barcode: "qr", qr: "qr",
    "------": "", "--------": ""
  };
  if (exact[val] !== undefined) return exact[val];
  const v = val.toLowerCase();
  if (val.includes("現金")) return "cash";
  if (v.includes("uber")) return "uber";
  if (v.includes("didi") || v.includes("ｄｉｄｉ") || v.includes("di di")) return "didi";
  if (v === "go" || v === "ｇｏ" || /(^|\s)go(\s|$)/.test(v)) return "go";
  if (val.includes("クレジ") || v.includes("credit")) return "credit";
  if (val.includes("京交信")) return "kyokushin";
  if (val.includes("オムロン")) return "omron";
  if (val.includes("京都市他")) return "kyotoshi";
  if (val.includes("バーコード") || v.includes("paypay") || val.includes("微信") || val.includes("支付宝") || val.includes("扫码") || v.includes("qr")) return "qr";
  return val;
}

// ====== 合计（保留旧逻辑 + 新增ETC行级聚合显示） ======
function updateTotals() {
  const table = document.querySelector('table.report-table');
  if (!table) return;

  // 旧口径
  const totalMap = { cash: 0, uber: 0, didi: 0, go: 0, credit: 0, kyokushin: 0, omron: 0, kyotoshi: 0, qr: 0 };
  let meterSum = 0, charterCashTotal = 0, charterUncollectedTotal = 0;
  let uberReservationTotal = 0, uberReservationCount = 0;
  let uberTipTotal = 0, uberTipCount = 0;
  let uberPromotionTotal = 0, uberPromotionCount = 0;
  let specialUberSum = 0;

  // 新增 ETC 行级聚合
  let rideEtcSum = 0;     // 乗車ETC 合计
  let emptyEtcSum = 0;    // 空車ETC 合计
  let etcCompany = 0;     // ETC(会社負担)
  let etcDriver = 0;      // ETC(ドライバー立替)
  let etcCustomer = 0;    // ETC(お客様支払)

  $all(".report-item-row", table).forEach(row => {
    const delFlag = row.querySelector("input[name$='-DELETE']");
    if ((delFlag && delFlag.checked) || row.style.display === "none") return;

    const isPending = (row.querySelector("input[name$='-is_pending']") || row.querySelector(".pending-checkbox"))?.checked;
    if (isPending) return;

    // 旧计费逻辑
    const fee = toInt(row.querySelector(".meter-fee-input")?.value, 0);
    const payment = row.querySelector("select[name$='-payment_method']")?.value || "";
    const isCharter = row.querySelector("input[name$='-is_charter']")?.checked;
    const charterAmount = toInt(row.querySelector(".charter-amount-input")?.value, 0);
    const charterPayMethod = row.querySelector(".charter-payment-method-select")?.value || "";

    if (!isCharter) {
      if (fee > 0) {
        const raw = payment;
        const isUberReservation = raw === 'uber_reservation';
        const isUberTip = raw === 'uber_tip';
        const isUberPromotion = raw === 'uber_promotion';
        const isSpecialUber = isUberReservation || isUberTip || isUberPromotion;
        if (isSpecialUber) {
          specialUberSum += fee;
          if (isUberReservation) { uberReservationTotal += fee; uberReservationCount += 1; }
          else if (isUberTip) { uberTipTotal += fee; uberTipCount += 1; }
          else if (isUberPromotion) { uberPromotionTotal += fee; uberPromotionCount += 1; }
        } else {
          const method = resolveJsPaymentMethod(payment);
          meterSum += fee;
          if (Object.hasOwn(totalMap, method)) totalMap[method] += fee;
        }
      }
    } else if (charterAmount > 0) {
      const CASH = ['jpy_cash', 'rmb_cash', 'self_wechat', 'boss_wechat'];
      const UNCOLLECTED = ['to_company', 'bank_transfer', ''];
      if (CASH.includes(charterPayMethod)) charterCashTotal += charterAmount;
      else if (UNCOLLECTED.includes(charterPayMethod)) charterUncollectedTotal += charterAmount;
    }

    // ✅ ETC 行级字段：聚合统计（只显示，不改旧口径）
    const rideEtc = toInt(row.querySelector(".etc-riding-input")?.value, 0);
    const emptyEtc = toInt(row.querySelector(".etc-empty-input")?.value, 0);
    const chargeType = (row.querySelector(".etc-charge-type-select")?.value || "company").trim();
    const lineTotal = rideEtc + emptyEtc;
    rideEtcSum += rideEtc;
    emptyEtcSum += emptyEtc;
    if (chargeType === "company") etcCompany += lineTotal;
    else if (chargeType === "driver") etcDriver += lineTotal;
    else if (chargeType === "customer") etcCustomer += lineTotal;
  });

  const salesTotal = meterSum + specialUberSum + charterCashTotal + charterUncollectedTotal;

  // 回写（旧口径）
  idText("total_meter_only", meterSum);
  idText("uber-reservation-total", uberReservationTotal);
  idText("uber-reservation-count", uberReservationCount);
  idText("uber-tip-total", uberTipTotal);
  idText("uber-tip-count", uberTipCount);
  idText("uber-promotion-total", uberPromotionTotal);
  idText("uber-promotion-count", uberPromotionCount);
  idText("total_meter", salesTotal);
  idText("sales-total", salesTotal);
  Object.entries(totalMap).forEach(([k, v]) => idText(`total_${k}`, v));
  idText("charter-cash-total", charterCashTotal);
  idText("charter-uncollected-total", charterUncollectedTotal);

  // ✅ 回写（新面板：ETC 小计显示）
  idText("ride-etc-total", rideEtcSum);
  idText("empty-etc-total", emptyEtcSum);
  idText("etc-company-total", etcCompany);
  idText("etc-driver-total", etcDriver);
  idText("etc-customer-total", etcCustomer);

  // ✅ 补回「过不足」旧口径计算
  const deposit = _yen(document.getElementById('deposit-input')?.value || 0);
  const cashNagashi = totalMap.cash || 0;
  const charterCash = charterCashTotal || 0;

  let imbalance = deposit - cashNagashi - charterCash;

  const diffEl = document.getElementById("difference-output")
               || document.getElementById("deposit-difference")
               || document.getElementById("shortage-diff");
  if (diffEl) {
    diffEl.textContent = Number.isFinite(imbalance) ? imbalance.toLocaleString() : "--";
  }
  const hiddenDiff = document.getElementById('id_deposit_difference');
  if (hiddenDiff) hiddenDiff.value = imbalance;

  // 继续运行智能提示模块（如有）
  if (typeof updateSmartHintPanel === 'function') {
    try { updateSmartHintPanel(); } catch (e) {}
  }
}

// ====== 夜班排序（保留，默认关闭） ======
(function () {
  function parseHHMM(str) {
    if (!str) return null;
    const m = String(str).trim().match(/^(\d{1,2}):(\d{2})$/);
    if (!m) return null;
    const h = Math.min(23, Math.max(0, parseInt(m[1], 10)));
    const mm = Math.min(59, Math.max(0, parseInt(m[2], 10)));
    return h * 60 + mm;
  }
  function getAnchorMinutes() {
    const el = document.querySelector("input[name='clock_in']") || document.getElementById("id_clock_in");
    const v = el && el.value ? el.value : "12:00";
    const m = parseHHMM(v);
    return m == null ? 12 * 60 : m;
  }
  function sortRowsByTime() {
    const dataTb = document.querySelector('table.report-table tbody:not(#empty-form-template)');
    if (!dataTb) return;
    const anchor = getAnchorMinutes();
    const rows = $all("tr.report-item-row", dataTb);
    const pairs = rows.map(row => {
      const t = (row.querySelector("input[name$='-ride_time']") || row.querySelector(".ride-time-input") || row.querySelector(".time-input"))?.value || "";
      let mins = parseHHMM(t);
      if (mins == null) mins = Number.POSITIVE_INFINITY;
      else if (mins < anchor) mins += 24 * 60;
      return { row, key: mins };
    });
    pairs.sort((a, b) => a.key - b.key).forEach(p => dataTb.appendChild(p.row));
    let idx = 1; pairs.forEach(p => { const num = p.row.querySelector(".row-number"); if (num) num.textContent = idx++; });
    updateSameTimeGrouping();
  }
  window.__resortByTime = sortRowsByTime;
})();

// ====== 提交前兜底（保留） ======
(function () {
  const form = document.querySelector("form"); if (!form) return;
  form.addEventListener("submit", function () {
    const sel = [".meter-fee-input", ".charter-amount-input", ".deposit-input", ".toll-input", ".etc-riding-input", ".etc-empty-input"].join(",");
    document.querySelectorAll(sel).forEach((inp) => {
      if (!inp) return;
      const v = inp.value;
      if (v === "" || v == null) { inp.value = "0"; }
      else {
        const n = parseInt(String(v).replace(/[^\d-]/g, ""), 10);
        inp.value = Number.isFinite(n) ? String(n) : "0";
      }
    });
  });
})();

// ====== ETC 显示开关（默认隐藏/显示由 localStorage 记忆） ======
(function setupEtcColsToggle() {
  const table = document.querySelector("table.report-table");
  const toggle = document.getElementById("toggle-etc-cols");
  if (!table || !toggle) return;

  const KEY = "dr:show_etc_cols";
  function apply() {
    const on = !!(toggle.checked);
    if (on) {
      table.classList.remove("etc-cols-hidden");
    } else {
      table.classList.add("etc-cols-hidden");
    }
    localStorage.setItem(KEY, on ? "1" : "0");
  }
  // 初始
  const saved = localStorage.getItem(KEY);
  if (saved !== null) toggle.checked = saved === "1";
  apply();
  toggle.addEventListener("change", apply);
})();

// ====== 页面主绑定（单一处；不重复） ======
document.addEventListener('DOMContentLoaded', () => {
  // 1) 行绑定（保持旧功能）
  $all("tr.report-item-row").forEach(bindRowEvents);

  // 2) “下に挿入”按钮（行内）
  const table = document.querySelector('table.report-table');
  if (table) {
    table.addEventListener("click", (e) => {
      const btn = e.target.closest(".insert-below");
      if (!btn) return;
      e.preventDefault();
      const row = getRow(btn);
      const rows = $all("tr.report-item-row", table);
      const index = row ? (rows.findIndex(r => r === row) + 1) : 1;
      insertRowAfter(index);
      // 绑定新行 + 再算一遍
      const newRow = $all("tr.report-item-row", table)[index]; // 插到 index 之后
      if (newRow) bindRowEvents(newRow);
      updateRowNumbersAndIndexes();
      updateSameTimeGrouping();
      updateTotals();
      evaluateEmptyEtcDetailVisibility();  // ★ 新增：插入行后判断是否显示空車ETC卡片
    });
  }

  // 3) 顶部“尾部追加”/“指定行插入”
  const addBtn = document.getElementById('add-row-btn');
  if (addBtn && !addBtn.dataset.boundOnce) {
    addBtn.dataset.boundOnce = "1";
    addBtn.addEventListener('click', (e) => { 
      e.preventDefault(); 
      addRowToEnd();
      // 末尾新行再绑定 + 重新计算
      const rows = $all("tr.report-item-row");
      const newRow = rows[rows.length - 1];
      if (newRow) bindRowEvents(newRow);
      updateRowNumbersAndIndexes();
      updateSameTimeGrouping();
      updateTotals();
      evaluateEmptyEtcDetailVisibility();  // ★ 新增
    });
  }
  const idxBtn = document.getElementById('insert-at-btn');
  const idxInput = document.getElementById('insert-index-input');
  if (idxBtn && idxInput && !idxBtn.dataset.boundOnce) {
    idxBtn.dataset.boundOnce = "1";
    idxBtn.addEventListener('click', (e) => {
      e.preventDefault();
      const v = parseInt(idxInput.value, 10) || 1;
      insertRowAfter(v);
      // 绑定新行 + 再算一遍
      const rows = $all("tr.report-item-row");
      const newRow = rows[Math.min(v, rows.length) - 1];
      if (newRow) bindRowEvents(newRow);
      updateRowNumbersAndIndexes();
      updateSameTimeGrouping();
      updateTotals();
      evaluateEmptyEtcDetailVisibility();  // ★ 新增
    });
  }

  // 4) 退勤勾选状态同步（保留）
  (function () {
    var out = document.getElementById("id_clock_out");
    var chk = document.getElementById("id_unreturned_flag") || document.querySelector('input[name="unreturned_flag"]');
    var txt = document.getElementById("return-status-text");
    function sync() {
      var hasVal = out && out.value.trim() !== "";
      if (hasVal) {
        if (chk) chk.checked = false;
        if (txt) txt.textContent = "已完成";
      } else {
        if (txt) txt.textContent = "未完成入库手续";
      }
    }
    if (out) {
      out.addEventListener("input", sync);
      window.addEventListener("load", sync);
    }
  })();

  // 5) 初始计算 & 初始化（保留 + 新增）
  initFlatpickr(document);              // ★ 确保时间控件可用
  updateDuration();
  updateRowNumbersAndIndexes();
  updateSameTimeGrouping();
  updateTotals();
  evaluateEmptyEtcDetailVisibility();   // ★ 新增：进页面就判断空車ETC卡片显示
});


/* ===== 智能联动：根据明细决定是否显示「空車ETC（回程）詳細」卡片 ===== */
function evaluateEmptyEtcDetailVisibility() {
  const card = document.getElementById('empty-etc-card');
  if (!card) return;

  // 扫描所有行：累计“空车ETC”金额；判断是否存在需要司机承担的空车ETC
  const rows = document.querySelectorAll('tr.report-item-row');
  let emptySum = 0;
  let needDetail = false;

  rows.forEach(row => {
    const delFlag = row.querySelector("input[name$='-DELETE']");
    if ((delFlag && delFlag.checked) || row.style.display === "none") return;

    const isPending = (row.querySelector("input[name$='-is_pending']") || row.querySelector(".pending-checkbox"))?.checked;
    if (isPending) return;

    const emptyEtc = parseInt((row.querySelector(".etc-empty-input")?.value || "0").replace(/[^\d-]/g, ""), 10) || 0;
    const chargeType = (row.querySelector(".etc-charge-type-select")?.value || "company").trim();

    emptySum += emptyEtc;

    // 只有“司机立替”的空车ETC，才需要展开“回程詳細”进行报销/结算方式说明
    if (emptyEtc > 0 && chargeType === "driver") {
      needDetail = true;
    }
  });

  if (needDetail) {
    // 显示卡片
    card.classList.remove('d-none');

    // 把合计金额（仅在为空时）灌到“空車ETC 金額”输入框，避免重复手填
    const emptyInput = document.getElementById('id_etc_uncollected');
    if (emptyInput && (!emptyInput.value || emptyInput.value === "0")) {
      emptyInput.value = emptySum;
      emptyInput.dispatchEvent(new Event('input', { bubbles: true }));
    }

    // 默认联动：司机卡 + 個別（均可被用户改）
    const cardSel = document.getElementById('id_etc_empty_card');
    if (cardSel && !cardSel.value) {
      cardSel.value = 'own';
      cardSel.dispatchEvent(new Event('change', { bubbles: true }));
    }
    const methodSel = document.getElementById('id_etc_return_fee_method');
    if (methodSel && !methodSel.value) {
      methodSel.value = 'none';
      methodSel.dispatchEvent(new Event('change', { bubbles: true }));
    }
  } else {
    // 隐藏卡片
    card.classList.add('d-none');
  }
}


// —— 进入页面先排一次；提交前再排一次 ——
// 避免重复绑定：只挂一次
(function bindNightSortEntrypoints(){
  const onceKey = "__night_sort_bound__";
  if (window[onceKey]) return;
  window[onceKey] = true;

  document.addEventListener("DOMContentLoaded", () => {
    // 初始排序
    if (typeof window.__resortByTime === "function") window.__resortByTime();

    // 提交前兜底排序（确保保存后顺序正确）
    const form = document.querySelector('form[method="post"]');
    if (form) {
      form.addEventListener("submit", () => {
        if (typeof window.__resortByTime === "function") window.__resortByTime();
      });
    }
  });
})();
