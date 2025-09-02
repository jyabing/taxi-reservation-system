// ===== Driver DailyReport only: 页面闸门 =====
(function () {
  const DR_ROOT =
    document.querySelector("table.report-table") ||
    document.querySelector("#smart-hint-panel")?.closest("form");
  if (!DR_ROOT) {
    console.debug("dailyreport.js: not driver dailyreport page, abort.");
    return;
  }
  window.__DR_ROOT__ = DR_ROOT;
})();

// ============ 工具函数（全局可用） ============
function $(sel, root){ return (root||document).querySelector(sel); }
function $all(sel, root){ return Array.from((root||document).querySelectorAll(sel)); }
function getRow(el){ return el?.closest("tr.report-item-row") || el?.closest("tr"); }
function toInt(v, fallback=0){ const n=parseInt(String(v??"").replace(/[^\d-]/g,""),10); return Number.isFinite(n)?n:fallback; }

// ============ 作用域获取（基于按钮所在的 form） ============
function getFormScope() {
  const btn = document.getElementById('insert-at-btn') || document.getElementById('add-row-btn') || document.querySelector('table.report-table');
  const form = btn ? (btn.closest('form') || document) : document;
  const table = form.querySelector('table.report-table') || form.querySelector('table');
  const tpl = form.querySelector('#empty-form-template'); // 模板 tbody
  let bodies = [];
  if (table) bodies = Array.from(table.tBodies || table.querySelectorAll('tbody'));
  const dataTb = bodies.find(b => b !== tpl) || bodies[0] || null; // 数据 tbody
  const total = form.querySelector("input[name$='-TOTAL_FORMS']");
  return { form, table, tpl, dataTb, total };
}

// ============ 时间/工时 ============
document.addEventListener('DOMContentLoaded', () => {
  if (typeof flatpickr === 'function') {
    flatpickr(".time-input", {
      enableTime:true, noCalendar:true, dateFormat:"H:i", time_24hr:true, locale:"ja"
    });
  }
});

function updateDuration() {
  const form = getFormScope().form;
  const inEl  = $("input[name='clock_in']", form);
  const outEl = $("input[name='clock_out']", form);
  const workDisplay = $("#work-duration", form);
  const actualDisplay = $("#actual-work-time", form);
  const overtimeDisplay = $("#overtime", form);
  const breakTimeDisplay = $("#break-time-display", form);
  const breakTimeHidden  = $("#break-time-plus20", form);
  if (!inEl || !outEl) return;

  const [h1, m1] = (inEl.value || "00:00").split(":").map(Number);
  const [h2, m2] = (outEl.value || "00:00").split(":").map(Number);
  let d1 = new Date(0, 0, 0, h1, m1);
  let d2 = new Date(0, 0, 0, h2, m2);
  if (d2 <= d1) d2.setDate(d2.getDate() + 1);
  const workMin = Math.floor((d2 - d1) / 60000);

  let breakMin = 0;
  const breakEl = $("#break-time-input", getFormScope().form);
  if (breakEl && breakEl.value) {
    const [bh, bm] = breakEl.value.split(":").map(Number);
    breakMin = (bh || 0) * 60 + (bm || 0);
  }

  const realBreak = breakMin + 20;
  const actualMin = workMin - realBreak;
  const overtimeMin = actualMin - 480;

  const toHM = m => `${String(Math.floor(m / 60)).padStart(2,'0')}:${String(m % 60).padStart(2,'0')}`;
  if (workDisplay)   workDisplay.textContent   = toHM(workMin);
  if (actualDisplay) actualDisplay.textContent = toHM(actualMin);
  if (overtimeDisplay) {
    overtimeDisplay.textContent = (overtimeMin < 0 ? "-" : "") + toHM(Math.abs(overtimeMin));
    overtimeDisplay.style.color = overtimeMin >= 0 ? "red" : "blue";
  }
  if (breakTimeDisplay) breakTimeDisplay.textContent = toHM(realBreak);
  if (breakTimeHidden)  breakTimeHidden.value = toHM(realBreak);
}

// ============ 行号刷新 ============
function updateRowNumbersAndIndexes() {
  const { dataTb } = getFormScope();
  if (!dataTb) return;
  const rows = $all("tr.report-item-row", dataTb).filter(r => r.style.display !== "none");
  rows.forEach((row, i) => { row.querySelector(".row-number")?.replaceChildren(document.createTextNode(i+1)); });
}

// ============ 行事件绑定 ============
function bindRowEvents(row) {
  // time picker on row fields (if flatpickr present)
  if (typeof flatpickr === 'function') {
    $all(".time-input", row).forEach(el => {
      flatpickr(el, { enableTime:true, noCalendar:true, dateFormat:"H:i", time_24hr:true, locale:"ja" });
    });
  }

  // 删除（已有行）
$all(".delete-row", row).forEach(btn => {
  btn.addEventListener("click", () => {
    if (!confirm("确定删除此行？")) return;
    const cb = row.querySelector("input[name$='-DELETE']");
    if (cb) {
      cb.checked = true;
      row.style.display = "none";
      updateRowNumbersAndIndexes();
      updateTotals();
      updateSmartHintPanel?.();
    }
  });
});

// 移除（新建行）
$all(".remove-row", row).forEach(btn => {
  btn.addEventListener("click", () => {
    if (!confirm("确定移除此行？")) return;
    // 新行模板里我们已渲染了 {{ formset.empty_form.DELETE }}
    const cb = row.querySelector("input[name$='-DELETE']");
    if (cb) {
      cb.checked = true;
      row.style.display = "none";
    } else {
      // 兜底：极端情况下没有 DELETE，就从 DOM 移除
      row.remove();
    }
    updateRowNumbersAndIndexes();
    updateTotals();
    updateSmartHintPanel?.();
  });
});

  // 标记/待入 UI
  const checkbox = row.querySelector(".mark-checkbox");
  if (checkbox) {
    row.classList.toggle("has-note", checkbox.checked);
    checkbox.addEventListener("change", () => row.classList.toggle("has-note", checkbox.checked));
  }

  // 合计、智能提示联动
  const amountInput = row.querySelector("input[name$='-meter_fee']");
  const methodSelect= row.querySelector("select[name$='-payment_method']");
  const pendingCb   = row.querySelector("input[name$='-is_pending']") || row.querySelector(".pending-checkbox");
  const pendingHint = row.querySelector(".pending-mini-hint");
  const charterAmountInput = row.querySelector(".charter-amount-input");
  const charterCheckbox    = row.querySelector("input[name$='-is_charter']");

  if (amountInput)  amountInput.addEventListener("input",  () => { updateTotals(); updateSmartHintPanel(); });
  if (methodSelect) methodSelect.addEventListener("change", () => { updateTotals(); updateSmartHintPanel(); });
  if (pendingCb) {
    pendingCb.addEventListener("change", () => {
      updateTotals(); updateSmartHintPanel();
      if (pendingHint) pendingHint.classList.toggle("d-none", !pendingCb.checked);
    });
    if (pendingHint) pendingHint.classList.toggle("d-none", !pendingCb.checked);
  }
  if (charterAmountInput) charterAmountInput.addEventListener("input", updateSmartHintPanel);
  if (charterCheckbox)    charterCheckbox.addEventListener("change", updateSmartHintPanel);
}

// ============ 模板克隆 & 插入 ============
function cloneRowFromTemplate() {
  const { tpl, total } = getFormScope();
  if (!tpl || !total) return null;
  const count = parseInt(total.value || '0', 10) || 0;
  const tmp = document.createElement('tbody');
  tmp.innerHTML = tpl.innerHTML.replace(/__prefix__/g, count).replace(/__num__/g, count+1);
  const tr = tmp.querySelector('tr');
  if (!tr) return null;
  // 解除隐藏/禁用
  tr.classList.remove('d-none','hidden','invisible','template-row');
  tr.style.removeProperty('display'); tr.removeAttribute('aria-hidden');
  tr.querySelectorAll('input,select,textarea,button').forEach(el=>{ el.disabled=false; el.removeAttribute('disabled'); });
  // 递增 TOTAL_FORMS
  total.value = String(count + 1);
  return tr;
}

function addRowToEnd() {
  const { dataTb } = getFormScope();
  if (!dataTb) return false;
  const tr = cloneRowFromTemplate();
  if (!tr) return false;
  dataTb.appendChild(tr);
  bindRowEvents(tr);
  updateRowNumbersAndIndexes();
  updateTotals();
  updateSmartHintPanel();
  try { tr.scrollIntoView({behavior:'smooth', block:'center'});}catch(e){}
  (tr.querySelector('.time-input')||tr.querySelector('input,select'))?.focus?.();
  return true;
}

function insertRowAfter(indexOneBased) {
  const { dataTb } = getFormScope();
  if (!dataTb) return false;
  const tr = cloneRowFromTemplate();
  if (!tr) return false;

  const rows = $all("tr.report-item-row", dataTb);
  const all  = rows.length ? rows : $all("tr", dataTb);
  if (all.length === 0) {
    dataTb.appendChild(tr);
  } else {
    const n = Math.min(Math.max(1, indexOneBased||1), all.length);
    const anchor = all[n-1];
    (anchor.parentNode || dataTb).insertBefore(tr, anchor.nextSibling);
  }
  bindRowEvents(tr);
  updateRowNumbersAndIndexes();
  updateTotals();
  updateSmartHintPanel();
  try { tr.scrollIntoView({behavior:'smooth', block:'center'});}catch(e){}
  (tr.querySelector('.time-input')||tr.querySelector('input,select'))?.focus?.();
  return true;
}

// ============ 支付方式归一化 & 合计 ============
function resolveJsPaymentMethod(raw) {
  if (!raw) return "";
  const val = String(raw).trim();
  const exact = {
    cash:"cash", uber_cash:"cash", didi_cash:"cash", go_cash:"cash",
    uber:"uber", didi:"didi", go:"go",
    credit_card:"credit", kyokushin:"kyokushin", omron:"omron", kyotoshi:"kyotoshi", barcode:"qr", qr:"qr",
    "------":"", "--------":""
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

function updateTotals() {
  const { dataTb } = getFormScope();
  if (!dataTb) return;

  const totalMap = { cash:0, uber:0, didi:0, go:0, credit:0, kyokushin:0, omron:0, kyotoshi:0, qr:0 };
  let meterSum=0, charterCashTotal=0, charterUncollectedTotal=0;

  $all(".report-item-row", dataTb).forEach(row => {
    // 跳过被标记删除或已隐藏的行
    const delFlag = row.querySelector("input[name$='-DELETE']");
    if ((delFlag && delFlag.checked) || row.style.display === "none") return;

    const isPending = (row.querySelector("input[name$='-is_pending']") || row.querySelector(".pending-checkbox"))?.checked;
    if (isPending) return;

    const fee = toInt(row.querySelector(".meter-fee-input")?.value, 0);
    const payment = row.querySelector("select[name$='-payment_method']")?.value || "";
    const isCharter = row.querySelector("input[name$='-is_charter']")?.checked;
    const charterAmount = toInt(row.querySelector(".charter-amount-input")?.value, 0);
    const charterPayMethod = row.querySelector(".charter-payment-method-select")?.value || "";

    if (!isCharter) {
      const method = resolveJsPaymentMethod(payment);
      if (fee>0) {
        meterSum += fee;
        if (Object.hasOwn(totalMap, method)) totalMap[method] += fee;
      }
    } else if (charterAmount>0) {
      const CASH = ['jpy_cash','rmb_cash','self_wechat','boss_wechat'];
      const UNCOLLECTED = ['to_company','bank_transfer',''];
      if (CASH.includes(charterPayMethod)) charterCashTotal += charterAmount;
      else if (UNCOLLECTED.includes(charterPayMethod)) charterUncollectedTotal += charterAmount;
    }
  });

  const salesTotal = meterSum + charterCashTotal + charterUncollectedTotal;
  const idText = (id, n) => { const el=document.getElementById(id); if (el) el.textContent = Number(n||0).toLocaleString(); };
  idText("total_meter_only", meterSum);
  idText("total_meter", salesTotal);
  idText("sales-total", salesTotal);
  idText("total_cash", totalMap.cash);
  idText("total_credit", totalMap.credit);
  idText("charter-cash-total", charterCashTotal);
  idText("charter-uncollected-total", charterUncollectedTotal);
  Object.entries(totalMap).forEach(([k,v]) => idText(`total_${k}`, v));

  const depositInput = toInt(document.getElementById("deposit-input")?.value, 0);
  const shortage = depositInput - totalMap.cash - charterCashTotal;
  const diffEl = document.getElementById("difference-output")
    || document.getElementById("deposit-difference")
    || document.getElementById("shortage-diff");
  if (diffEl) diffEl.textContent = shortage.toLocaleString();
}

// ============ 智能提示面板 ============
function updateSmartHintPanel() {
  const panel = document.querySelector("#smart-hint-panel"); if (!panel) return;

  const cashTotal     = toInt(document.querySelector("#total_cash")?.textContent, 0);
  const etcCollected  = toInt(document.querySelector("#id_etc_collected")?.value, 0);
  const etcUncollected= toInt(document.querySelector("#id_etc_uncollected")?.value, 0);
  const totalSales    = toInt(document.querySelector("#total_meter")?.textContent, 0);
  const deposit       = toInt(document.querySelector("#deposit-input")?.value, 0);
  const totalCollected = cashTotal + etcCollected;

  const pendingRows = $all(".report-item-row input[name$='-is_pending']:checked, .report-item-row .pending-checkbox:checked")
    .map(cb => cb.closest("tr.report-item-row")).filter(Boolean);
  const pendingCount = pendingRows.length;
  let pendingSum = 0;
  pendingRows.forEach(row => {
    const isCharter = !!row.querySelector("input[name$='-is_charter']")?.checked;
    pendingSum += toInt(isCharter ? row.querySelector(".charter-amount-input")?.value
                                  : row.querySelector(".meter-fee-input")?.value);
  });

  let html = "";
  if (pendingCount > 0) {
    html += `
      <div class="alert alert-info py-1 px-2 small mb-2">
        ℹ️ 現在有 <strong>${pendingCount}</strong> 筆「待入」，合計 <strong>${pendingSum.toLocaleString()}円</strong>。
        這些明細暫不計入売上合計；入帳後取消勾選即可立即納入核算。
      </div>`;
  }
  if (deposit < totalCollected) {
    html += `<div class="alert alert-danger py-1 px-2 small mb-2">
      ⚠️ 入金額が不足しています。請求額（現金 + ETC）は <strong>${totalCollected.toLocaleString()}円</strong>，
      入金は <strong>${deposit.toLocaleString()}円</strong> です。
    </div>`;
  } else {
    html += `<div class="alert alert-success py-1 px-2 small mb-2">✔️ 入金額は現金 + ETC をカバーしています。</div>`;
  }
  if (etcUncollected > 0) {
    html += `<div class="alert alert-info py-1 px-2 small mb-2">🚧 ETC 未收：<strong>${etcUncollected.toLocaleString()}円</strong>。请确认司机是否已补收。</div>`;
  }
  if (deposit < totalSales) {
    html += `<div class="alert alert-warning py-1 px-2 small mb-2">
      ℹ️ 売上合計 <strong>${totalSales.toLocaleString()}円</strong> 大于入金 <strong>${deposit.toLocaleString()}円</strong>，
      可能包含未收 ETC、或其他延迟结算项。
    </div>`;
  }
  panel.innerHTML = html;
}

// ============ ETC 相关 ============
function readIntById(id, fallback=0){ const el=document.getElementById(id); if(!el) return fallback; const raw=el.value??el.textContent??`${fallback}`; return toInt(raw,fallback); }
function updateEtcDifference() {
  const rideTotal = readIntById('id_etc_collected', 0);
  const hasNewEmpty = !!document.getElementById('id_etc_uncollected');
  let emptyAmount = hasNewEmpty ? readIntById('id_etc_uncollected', 0) : 0;
  const returnFee = hasNewEmpty ? readIntById('id_etc_return_fee_claimed', 0) : 0;
  const returnFeeMethod = hasNewEmpty ? (document.getElementById('id_etc_return_fee_method')?.value || 'none') : 'none';
  const emptyCardRaw = hasNewEmpty ? (document.getElementById('id_etc_empty_card')?.value || 'company') : 'company';
  const emptyCard = (emptyCardRaw === 'company') ? 'company_card' : 'personal_card';
  const coveredByCustomer = (returnFeeMethod === 'app_ticket') ? returnFee : 0;

  let etcUncollected = 0, etcDriverBurden = 0;
  if (hasNewEmpty) {
    if (emptyCard === 'company_card' || emptyCard === '') {
      etcUncollected  = Math.max(0, coveredByCustomer - emptyAmount);
      etcDriverBurden = Math.max(0, emptyAmount - coveredByCustomer);
    }
  } else {
    etcUncollected  = readIntById('id_etc_uncollected', 0);
    etcDriverBurden = readIntById('id_etc_shortage', 0);
  }

  const display = document.getElementById('etc-diff-display');
  if (display) {
    display.className = (etcDriverBurden > 0 || etcUncollected > 0) ? 'alert alert-warning' : 'alert alert-info';
    display.innerText = `未收ETC：${etcUncollected.toLocaleString()} 円；司机负担：${etcDriverBurden.toLocaleString()} 円`;
  }
  if (document.getElementById('id_etc_uncollected')) document.getElementById('id_etc_uncollected').value = etcUncollected;
  if (document.getElementById('id_etc_shortage')) {
    const el = document.getElementById('id_etc_shortage');
    el.value = etcDriverBurden;
    el.classList.toggle('text-danger', etcDriverBurden > 0);
    el.classList.toggle('fw-bold', etcDriverBurden > 0);
  }

  const etcExpected = (toInt(document.getElementById('id_etc_collected')?.value, 0) || 0)
                    + (toInt(document.getElementById('id_etc_uncollected')?.value, 0) || 0);
  const expectedDisplay = document.getElementById('etc-expected-output');
  if (expectedDisplay) expectedDisplay.value = etcExpected.toLocaleString();
  const hiddenExpected = document.getElementById('id_etc_expected');
  if (hiddenExpected) hiddenExpected.value = etcExpected;
}

function updateEtcShortage(){ updateEtcDifference(); }
function updateEtcInclusionWarning() {
  const deposit = readIntById('id_deposit_amount', readIntById('deposit-input', 0));
  const cashNagashi = readIntById('total_cash', 0);
  const charterCash = readIntById('charter-cash-total', 0);
  const etcRideCash = readIntById('id_etc_collected_cash', 0);
  const expected = cashNagashi + charterCash + etcRideCash;
  const diff = deposit - expected;
  const box = document.getElementById('etc-included-warning'); if (!box) return;
  if (Math.abs(diff) <= 100) {
    box.className = 'alert alert-success';
    box.innerText = `✅ 入金額が妥当です。基準：現金(ながし)+貸切現金+乗車ETC現金 = ${expected.toLocaleString()}円`;
  } else if (diff > 100) {
    box.className = 'alert alert-warning';
    box.innerText = `⚠️ 入金額が多いようです（+${diff.toLocaleString()}円）。乗車ETC現金や端数を確認してください。`;
  } else {
    box.className = 'alert alert-warning';
    box.innerText = `⚠️ 入金額が不足しています（${diff.toLocaleString()}円）。現金(ながし)・貸切現金・乗車ETC現金を見直してください。`;
  }
}

// ============ 貸切：行状态控制 ============
function applyCharterState(row, isCharter) {
  if (!row) return;
  const meterInput           = row.querySelector(".meter-fee-input");
  const charterAmountInput   = row.querySelector(".charter-amount-input");
  const charterPaymentSelect = row.querySelector(".charter-payment-method-select");
  if (meterInput) {
    meterInput.removeAttribute('disabled');
    if (!meterInput.dataset.originalValue) meterInput.dataset.originalValue = meterInput.value || "";
    if (isCharter) {
      meterInput.setAttribute('readonly','readonly');
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
      charterAmountInput.dispatchEvent(new Event('input',  { bubbles: true }));
      charterAmountInput.dispatchEvent(new Event('change', { bubbles: true }));
    }
    if (charterPaymentSelect) {
      charterPaymentSelect.value = "";
      charterPaymentSelect.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }
  updateTotals();
}

function hydrateAllCharterRows() {
  $all("input[type='checkbox'][name$='-is_charter']").forEach(chk => applyCharterState(getRow(chk), chk.checked));
}

// ============ 页面主绑定 ============
document.addEventListener('DOMContentLoaded', () => {
  // 1) 首屏为所有现有行绑事件
  $all("tr.report-item-row").forEach(bindRowEvents);

  // 2) 列表内“向下插入”按钮（**只在表格内委托一次，避免递归/重复绑定**）
  const { dataTb } = getFormScope();
  if (dataTb) {
    dataTb.addEventListener("click", (e) => {
      const btn = e.target.closest(".insert-below");
      if (!btn) return;
      e.preventDefault();
      const row = getRow(btn);
      const index = row ? ( ($all("tr.report-item-row", dataTb).indexOf ? $all("tr.report-item-row", dataTb).indexOf(row) : $all("tr.report-item-row", dataTb).findIndex(r=>r===row)) + 1 ) : 1;
      insertRowAfter(index); // 在当前行之后插入
    });
  }

  // 3) 末行新增
  const addBtn = document.getElementById('add-row-btn');
  if (addBtn && !addBtn.dataset.boundOnce) {
    addBtn.dataset.boundOnce = "1";
    addBtn.addEventListener('click', (e) => { e.preventDefault(); addRowToEnd(); });
  }

  // 4) 指定行插入（**唯一入口**；不再触发 .insert-below.click()）
  const idxBtn   = document.getElementById('insert-at-btn');
  const idxInput = document.getElementById('insert-index-input');
  if (idxBtn && idxInput && !idxBtn.dataset.boundOnce) {
    idxBtn.dataset.boundOnce = "1";
    idxBtn.addEventListener('click', (e) => {
      e.preventDefault();
      const v = parseInt(idxInput.value, 10) || 1;
      insertRowAfter(v); // 在第 v 行之后插入
    });
  }

  // 5) 其他输入监听
  [
    ['id_etc_collected_cash', [updateEtcDifference, updateEtcShortage]],
    ['id_etc_uncollected',    [updateEtcDifference, updateEtcShortage]],
    ['id_etc_collected',      [updateEtcInclusionWarning, updateEtcShortage, updateTotals]],
    ['id_deposit_amount',     [updateEtcDifference, updateEtcInclusionWarning]],
    ['clock_in',              [updateDuration]],
    ['clock_out',             [updateDuration]],
    ['break-time-input',      [updateDuration]],
    ['id_etc_empty_card',     [updateTotals]],
  ].forEach(([id, fns]) => {
    const el = document.getElementById(id);
    if (el) fns.forEach(fn => el.addEventListener("input", fn));
  });

  // 6) 初始执行
  updateDuration();
  updateEtcDifference();
  updateEtcShortage();
  updateEtcInclusionWarning();
  updateRowNumbersAndIndexes();
  updateTotals();
  updateSmartHintPanel();
  hydrateAllCharterRows();
});

// ============ 夜班排序（提交前 DOM 排序，不改 name/index） ============
(function () {
  function parseHHMM(str) {
    if (!str) return null;
    const m = String(str).trim().match(/^(\d{1,2}):(\d{2})$/);
    if (!m) return null;
    const h  = Math.min(23, Math.max(0, parseInt(m[1], 10)));
    const mm = Math.min(59, Math.max(0, parseInt(m[2], 10)));
    return h * 60 + mm;
  }
  function getAnchorMinutes() {
    const el = document.querySelector("input[name='clock_in']") || document.getElementById("id_clock_in");
    const v  = el && el.value ? el.value : "12:00";
    const m  = parseHHMM(v);
    return m == null ? 12 * 60 : m;
  }
  function sortRowsByTime() {
    const { dataTb } = getFormScope();
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
  }
  window.addEventListener("DOMContentLoaded", () => {
    const form = document.querySelector('form[method="post"]'); if (!form) return;
    form.addEventListener('submit', () => {
      sortRowsByTime();
      if (typeof updateRowNumbersAndIndexes === 'function') updateRowNumbersAndIndexes();
    });
  });
})();

// ============ 提交前兜底：金额空串→"0" ============
(function () {
  const form = document.querySelector("form"); if (!form) return;
  form.addEventListener("submit", function () {
    const sel = [".meter-fee-input",".charter-amount-input",".deposit-input",".toll-input"].join(",");
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

// 调试辅助（可在控制台调用）
window.__insertRowDebug__ = function(){ return insertRowAfter(1); };
