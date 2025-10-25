/* -------------------------------------------------------
 * Driver Daily Report (stable)
 * - 保留既有功能
 * - 行级ETC(乗車/空車/負担) 聚合 + 过不足含「実際ETC」
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
function toInt(v, fb = 0) { const n = parseInt(String(v ?? "").replace(/[^\d-]/g, ""), 10); return Number.isFinite(n) ? n : fb; }
function _yen(v) { if (v == null) return 0; const n = Number(String(v).replace(/[,，\s]/g, "")); return isFinite(n) ? n : 0; }
function idText(id, n) { const el = document.getElementById(id); if (el) el.textContent = Number(n || 0).toLocaleString(); }

// ====== flatpickr 初始化（仅一次，带兜底） ======
function initFlatpickr(root) {
  try {
    if (typeof flatpickr === 'function') {
      flatpickr((root || document).querySelectorAll(".time-input"), {
        enableTime: true, noCalendar: true, dateFormat: "H:i",
        time_24hr: true, locale: "ja"
      });
    }
  } catch (e) {}
}

/* =========================
 * ETC 结算口径配置
 * ========================= */
const ETC_COVERAGE = {
  // 当“空車ETCカード=自己カード”时，哪些“回程費 支払方法”用于覆盖司机立替
  coverReturnMethods: new Set(["cash_to_driver", "app_ticket"]),
};

/**
 * 计算“実際ETC”净额用于过不足：
 * 返回值：正数=公司需返给司机；负数=司机需返给公司；0=互不影响
 *
 * 口径：
 * - 司机立替 = 明细里 etc_charge_type=="driver" 的 (乗車ETC+空車ETC) 合计；
 * - 乘客承担 = 明细里 etc_charge_type=="customer" 的 (乗車ETC+空車ETC) 合计；
 * - 若 空車ETCカード=自己カード && 回程費 支払方法 ∈ ETC_COVERAGE.coverReturnMethods
 *   则 司机立替 -= 回程費 受領額；
 * - 净额 = 司机立替(经覆盖) − 乘客承担；
 */
function __calcEtcDueForOverShort() {
  // 从小计面板读取（由 updateTotals() 已写回）
  let driverPaid = toInt(document.getElementById("etc-driver-total")?.textContent, 0);
  let passengerCollected = toInt(document.getElementById("etc-customer-total")?.textContent, 0);
  // 兜底：若面板还没渲染，用输入框（模板 data-role）
  if (!passengerCollected) {
    passengerCollected = toInt(document.querySelector('[data-role="etc-collected-passenger"]')?.value, 0);
  }
  // 回程费覆盖：仅当 空車ETC カード=自己カード
  const emptyCard = (document.getElementById("id_etc_empty_card")?.value || "company").trim();
  const returnMethod = (document.getElementById("id_etc_return_fee_method")?.value || "none").trim();
  const returnClaimed = toInt(document.getElementById("id_etc_return_fee_claimed")?.value, 0);
  if (emptyCard === "own" && ETC_COVERAGE.coverReturnMethods.has(returnMethod)) {
    driverPaid = Math.max(0, driverPaid - returnClaimed);
  }
  // 正=返司机；负=返公司
  return driverPaid - passengerCollected;
}
window.__calcEtcDueForOverShort = __calcEtcDueForOverShort;

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

// ====== 行号刷新 / 同时刻缩进 ======
function updateRowNumbersAndIndexes() {
  const table = document.querySelector('table.report-table');
  const rows = $all("tr.report-item-row", table).filter(r => r.style.display !== "none");
  rows.forEach((row, i) => { row.querySelector(".row-number")?.replaceChildren(document.createTextNode(i + 1)); });
}
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

// ====== 行事件绑定（含ETC联动） ======
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
        evaluateEmptyEtcDetailVisibility();
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
      evaluateEmptyEtcDetailVisibility();
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
      evaluateEmptyEtcDetailVisibility();
    });
    if (pendingHint) pendingHint.classList.toggle("d-none", !pendingCb.checked);
  }
  if (charterAmountInput) charterAmountInput.addEventListener("input", updateTotals);
  if (charterCheckbox) {
    charterCheckbox.addEventListener("change", () => {
      applyCharterState(row, charterCheckbox.checked);
      updateTotals();
      evaluateEmptyEtcDetailVisibility();
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

  // === 「乗車ETC負担」「空車ETC負担」行内提示 ===
  (function attachChargeHints(){
    const rideSel  = row.querySelector('.etc-riding-charge-select');
    const emptySel = row.querySelector('.etc-empty-charge-select');
    const rideHint = row.querySelector('.js-ride-charge-hint');
    const emptyHint= row.querySelector('.js-empty-charge-hint');

    function textRide(v){
      if (v === 'driver')   return '司机垫付：若本行款项进公司，将返还司机（仅对乘车有效）';
      if (v === 'company')  return '公司承担：不计入返还';
      if (v === 'customer') return '客人承担：已由客人结算';
      return '';
    }
    function textEmpty(v){
      if (v === 'driver')   return '司机自付：可按回程政策判断是否覆盖/报销';
      if (v === 'company')  return '公司承担';
      if (v === 'customer') return '（通常不选）';
      return '';
    }
    function sync(){
      if (rideHint && rideSel)  rideHint.textContent  = textRide(rideSel.value);
      if (emptyHint && emptySel) emptyHint.textContent = textEmpty(emptySel.value);
    }
    if (rideSel)  rideSel.addEventListener('change', sync);
    if (emptySel) emptySel.addEventListener('change', sync);
    sync(); // 初始渲染一次
  })();

  // 行级ETC 三字段
  $all(".etc-riding-input, .etc-empty-input, .etc-charge-type-select", row).forEach(el => {
    el.addEventListener("input", () => { updateTotals(); evaluateEmptyEtcDetailVisibility(); });
    el.addEventListener("change", () => { updateTotals(); evaluateEmptyEtcDetailVisibility(); });
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

// ====== 合计（旧逻辑 + 行级ETC聚合 + 過不足含「実際ETC 会社→運転手」） ======
/* ====== REPLACE FROM HERE: updateTotals() ====== */
function updateTotals() {
  const table = document.querySelector("table.report-table");
  if (!table) return;

  // —— 旧口径：按支付方式聚合（保持你原有统计口径）——
  const totalMap = { cash: 0, uber: 0, didi: 0, go: 0, credit: 0, kyokushin: 0, omron: 0, kyotoshi: 0, qr: 0 };
  let meterSum = 0, charterCashTotal = 0, charterUncollectedTotal = 0;
  let uberReservationTotal = 0, uberReservationCount = 0;
  let uberTipTotal = 0, uberTipCount = 0;
  let uberPromotionTotal = 0, uberPromotionCount = 0;
  let specialUberSum = 0;

  // —— 行级ETC聚合 —— 
  let rideEtcSum = 0;     // 乗車ETC 合计
  let emptyEtcSum = 0;    // 空車ETC 合计
  let etcCompany = 0;     // 会社負担
  let etcDriver  = 0;     // ドライバー立替
  let etcCustomer= 0;     // お客様支払
  let actualEtcCompanyToDriver = 0; // ✅ 实際ETC（会社→運転手）

  const COMPANY_SIDE = new Set(["uber","didi","go","credit","kyokushin","omron","kyotoshi","qr"]);

  $all(".report-item-row", table).forEach(row => {
    const delFlag = row.querySelector("input[name$='-DELETE']");
    if ((delFlag && delFlag.checked) || row.style.display === "none") return;
    const isPending = (row.querySelector("input[name$='-is_pending']") || row.querySelector(".pending-checkbox"))?.checked;
    if (isPending) return;

    // ===== 旧计费逻辑（非貸切） =====
    const fee = toInt(row.querySelector(".meter-fee-input")?.value, 0);
    const paymentRaw = row.querySelector("select[name$='-payment_method']")?.value || "";
    const isCharter = row.querySelector("input[name$='-is_charter']")?.checked;
    const charterAmount = toInt(row.querySelector(".charter-amount-input")?.value, 0);
    const charterPayMethod = row.querySelector(".charter-payment-method-select")?.value || "";

    if (!isCharter) {
      if (fee > 0) {
        const isUberReservation = paymentRaw === "uber_reservation";
        const isUberTip        = paymentRaw === "uber_tip";
        const isUberPromotion  = paymentRaw === "uber_promotion";
        const isSpecialUber    = isUberReservation || isUberTip || isUberPromotion;

        if (isSpecialUber) {
          specialUberSum += fee;
          if (isUberReservation) { uberReservationTotal += fee; uberReservationCount += 1; }
          else if (isUberTip)    { uberTipTotal        += fee; uberTipCount        += 1; }
          else if (isUberPromotion) { uberPromotionTotal += fee; uberPromotionCount += 1; }
        } else {
          const method = resolveJsPaymentMethod(paymentRaw);
          meterSum += fee;
          if (Object.hasOwn(totalMap, method)) totalMap[method] += fee;
        }
      }
    } else if (charterAmount > 0) {
      const CASH = ["jpy_cash", "rmb_cash", "self_wechat", "boss_wechat"];
      const UNCOLLECTED = ["to_company", "bank_transfer", ""];
      if (CASH.includes(charterPayMethod)) charterCashTotal += charterAmount;
      else if (UNCOLLECTED.includes(charterPayMethod)) charterUncollectedTotal += charterAmount;
    }

    // ===== 行级 ETC 字段 =====
    const rideEtc  = toInt(row.querySelector(".etc-riding-input")?.value, 0);
    const emptyEtc = toInt(row.querySelector(".etc-empty-input")?.value, 0);
    const rideCharge  = (row.querySelector(".etc-riding-charge-select")?.value  || "company").trim();
    const emptyCharge = (row.querySelector(".etc-empty-charge-select")?.value || "company").trim();

    rideEtcSum  += rideEtc;
    emptyEtcSum += emptyEtc;

    if (rideEtc > 0) {
      if (rideCharge === "company")  etcCompany  += rideEtc;
      else if (rideCharge === "driver")   etcDriver   += rideEtc;
      else if (rideCharge === "customer") etcCustomer += rideEtc;
    }
    if (emptyEtc > 0) {
      if (emptyCharge === "company")  etcCompany  += emptyEtc;
      else if (emptyCharge === "driver")   etcDriver   += emptyEtc;
      else if (emptyCharge === "customer") etcCustomer += emptyEtc;
    }

    // ✅ 实際ETC（会社→運転手）：仅统计 “乗車ETC > 0 & 乗車ETC負担=ドライバー & 支払=公司侧”
    if (rideEtc > 0) {
      const payResolved = resolveJsPaymentMethod(paymentRaw); // -> "credit","uber","didi","go","qr",...
      if (rideCharge === "driver" && COMPANY_SIDE.has(payResolved)) {
        actualEtcCompanyToDriver += rideEtc;
      }
    }
  });

  // ===== 写回旧口径统计 =====
  const salesTotal = meterSum + specialUberSum + charterCashTotal + charterUncollectedTotal;
  idText("total_meter_only", meterSum);
  idText("uber-reservation-total", uberReservationTotal);
  idText("uber-reservation-count", uberReservationCount);
  idText("uber-tip-total",         uberTipTotal);
  idText("uber-tip-count",         uberTipCount);
  idText("uber-promotion-total",   uberPromotionTotal);
  idText("uber-promotion-count",   uberPromotionCount);
  idText("total_meter",            salesTotal);
  idText("sales-total",            salesTotal);
  Object.entries(totalMap).forEach(([k, v]) => idText(`total_${k}`, v));
  idText("charter-cash-total",       charterCashTotal);
  idText("charter-uncollected-total",charterUncollectedTotal);

  // ===== 写回 ETC 小计看板 =====
  idText("ride-etc-total",   rideEtcSum);
  idText("empty-etc-total",  emptyEtcSum);
  idText("etc-company-total",etcCompany);
  idText("etc-driver-total", etcDriver);
  idText("etc-customer-total",etcCustomer);

  // ===== 入金额卡片：実際ETC 会社 → 運転手 =====
  idText("actual_etc_company_to_driver_view", actualEtcCompanyToDriver);
  const actualHidden = document.getElementById("actual_etc_company_to_driver");
  if (actualHidden) actualHidden.value = actualEtcCompanyToDriver;

  // ===== 同步“ETC 收取=乗車合計（円）”：把「お客様支払」的 ETC 写回输入框（显示用）
  (function syncRideEtcCollected() {
    const input = document.querySelector('[data-role="etc-collected-passenger"]');
    if (!input) return;
    const target = etcCustomer; // 乘客承担的 ETC
    const current = toInt(input.value, 0);
    if (current !== target) {
      input.value = String(target);
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }
  })();

  // ===== 同步“空車ETC 金額（円）”卡片输入：展示用途
  (function syncEmptyEtcCard() {
    const input = document.getElementById("id_etc_uncollected");
    if (!input) return;
    const current = toInt(input.value, 0);
    if (current !== emptyEtcSum) {
      input.value = String(emptyEtcSum);
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }
  })();

  // ===== 过不足：旧口径 + 実際ETC（会社→運転手）
  const deposit      = _yen(document.getElementById("deposit-input")?.value || 0);
  const cashNagashi  = totalMap.cash || 0;
  const charterCash  = charterCashTotal || 0;
  const imbalanceBase= deposit - cashNagashi - charterCash;          // 旧口径
  const etcNet       = actualEtcCompanyToDriver;                     // 返司机的 ETC
  const imbalance    = imbalanceBase + etcNet;                       // 新口径

  const diffEl =
    document.getElementById("difference-output") ||
    document.getElementById("deposit-difference") ||
    document.getElementById("shortage-diff");
  if (diffEl) {
    diffEl.textContent = Number.isFinite(imbalance) ? imbalance.toLocaleString() : "--";
    diffEl.setAttribute("data-base-over-short", String(imbalanceBase));
    diffEl.setAttribute("data-etc-net",         String(etcNet));
  }
  const hiddenDiff = document.getElementById("id_deposit_difference");
  if (hiddenDiff) hiddenDiff.value = imbalance;

  // 內訳（展示）
  (function renderOverShortBreakdown() {
    const holder = document.getElementById("difference-breakdown");
    if (!holder || !diffEl) return;
    const base   = parseInt(diffEl.getAttribute("data-base-over-short") || "0", 10) || 0;
    const etc    = parseInt(diffEl.getAttribute("data-etc-net") || "0", 10) || 0;
    const total  = base + etc;

    const etcAbs = Math.abs(etc);
    const etcDir = etc >= 0 ? "会社 → 運転手" : "運転手 → 会社";
    const etcCls = etc >= 0 ? "ob-pos" : "ob-neg";

    holder.innerHTML = `
      <div class="ob-line">
        <span class="ob-label">基本（入金 − 現金 − 貸切）</span>
        <span class="ob-mono">${base.toLocaleString()}</span>
      </div>
      <div class="ob-line">
        <span class="ob-label">実際ETC <span class="ob-chip" title="行明細ETCの合算で動的計算">${etcDir}</span></span>
        <span class="ob-mono ${etcCls}">${etc >= 0 ? "＋" : "－"}${etcAbs.toLocaleString()}</span>
      </div>
      <div class="ob-line">
        <span class="ob-label ob-total">合計</span>
        <span class="ob-mono ob-total">${total.toLocaleString()}</span>
      </div>
    `;
  })();

  // 入金下方提示
  (function renderEtcHint(){
    const warn = document.getElementById('etc-included-warning');
    if (!warn) return;
    if (etcNet > 0) {
      warn.className = "small mt-1 text-primary";
      warn.textContent = `過不足に 実際ETC（会社→運転手 返還）${etcNet.toLocaleString()} 円 を加算しています。`;
    } else {
      warn.textContent = "";
    }
  })();

  // 智能联动：是否显示 “空車ETC（回程）詳細” 卡片
  if (typeof evaluateEmptyEtcDetailVisibility === "function") {
    try { evaluateEmptyEtcDetailVisibility(); } catch (_) {}
  }

  // 智能提示面板（若有）
  if (typeof updateSmartHintPanel === "function") {
    try { updateSmartHintPanel(); } catch (_) {}
  }
}
/* ====== REPLACE TO HERE ====== */

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

// ====== 提交前兜底 ======
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

// 让新插入的行马上跟随当前的列显隐状态
function syncEtcColVisibility(){
  const table = document.querySelector("table.report-table");
  const toggle = document.getElementById("toggle-etc-cols");
  if (!table || !toggle) return;
  table.classList.toggle('etc-cols-hidden', !toggle.checked);
}

// ====== ETC 显示开关（默认隐藏/显示由 localStorage 记忆） ======
(function setupEtcColsToggle() {
  const table = document.querySelector("table.report-table");
  const toggle = document.getElementById("toggle-etc-cols");
  if (!table || !toggle) return;

  const KEY = "dr:show_etc_cols";
  function apply() {
    const on = !!(toggle.checked);
    table.classList.toggle("etc-cols-hidden", !on);
    localStorage.setItem(KEY, on ? "1" : "0");
  }
  const saved = localStorage.getItem(KEY);
  if (saved !== null) toggle.checked = saved === "1";
  apply();
  toggle.addEventListener("change", apply);
})();

/* ===== 智能联动：根据明细决定是否显示「空車ETC（回程）詳細」卡片 ===== */
function evaluateEmptyEtcDetailVisibility() {
  const card = document.getElementById('empty-etc-card');
  if (!card) return;

  const rows = document.querySelectorAll('tr.report-item-row');
  let emptySum = 0;
  let needDetail = false;

  rows.forEach(row => {
    const delFlag = row.querySelector("input[name$='-DELETE']");
    if ((delFlag && delFlag.checked) || row.style.display === "none") return;

    const isPending = (row.querySelector("input[name$='-is_pending']") || row.querySelector(".pending-checkbox"))?.checked;
    if (isPending) return;

    const emptyEtc = toInt(row.querySelector(".etc-empty-input")?.value, 0);
    const chargeType = (row.querySelector(".etc-charge-type-select")?.value || "company").trim();

    emptySum += emptyEtc;
    if (emptyEtc > 0 && chargeType === "driver") needDetail = true;
  });

  if (needDetail) {
    card.classList.remove('d-none');
    const emptyInput = document.getElementById('id_etc_uncollected');
    if (emptyInput && (!emptyInput.value || emptyInput.value === "0")) {
      emptyInput.value = emptySum;
      emptyInput.dispatchEvent(new Event('input', { bubbles: true }));
    }
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
    card.classList.add('d-none');
  }
}

// 回程费相关控件变化时，重新计算
["#id_etc_uncollected","#id_etc_return_fee_claimed","#id_etc_return_fee_method","#id_etc_empty_card"]
  .forEach((sel) => {
    const el = document.querySelector(sel);
    if (!el) return;
    el.addEventListener("input", () => updateTotals());
    el.addEventListener("change", () => updateTotals());
  });

// ====== 页面主绑定 ======
document.addEventListener('DOMContentLoaded', () => {
  // 行绑定
  $all("tr.report-item-row").forEach(bindRowEvents);

  // “下に挿入”
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
      const newRow = $all("tr.report-item-row", table)[index];
      if (newRow) bindRowEvents(newRow);
      updateRowNumbersAndIndexes();
      updateSameTimeGrouping();
      updateTotals();
      evaluateEmptyEtcDetailVisibility();
      syncEtcColVisibility();
    });
  }

  // 顶部“指定行插入”
  const idxBtn = document.getElementById('insert-at-btn');
  const idxInput = document.getElementById('insert-index-input');
  if (idxBtn && idxInput && !idxBtn.dataset.boundOnce) {
    idxBtn.dataset.boundOnce = "1";
    idxBtn.addEventListener('click', (e) => {
      e.preventDefault();
      const v = parseInt(idxInput.value, 10) || 1;
      insertRowAfter(v);
      const rows = $all("tr.report-item-row");
      const newRow = rows[Math.min(v, rows.length) - 1];
      if (newRow) bindRowEvents(newRow);
      updateRowNumbersAndIndexes();
      updateSameTimeGrouping();
      updateTotals();
      evaluateEmptyEtcDetailVisibility();
      syncEtcColVisibility();
    });
  }

  // 退勤勾选状态同步
  (function () {
    var out = document.getElementById("id_clock_out");
    var chk = document.getElementById("id_unreturned_flag") || document.querySelector('input[name="unreturned_flag"]');
    var txt = document.getElementById("return-status-text");
    function sync() {
      var hasVal = out && out.value.trim() !== "";
      if (hasVal) { if (chk) chk.checked = false; if (txt) txt.textContent = "已完成"; }
      else { if (txt) txt.textContent = "未完成入库手续"; }
    }
    if (out) { out.addEventListener("input", sync); window.addEventListener("load", sync); }
  })();

  // 初始计算
  initFlatpickr(document);
  // ✅ 新增：若模板里缺少显示行，就自动补上（只加一次）
  ensureActualEtcIndicator();

  updateDuration();
  updateRowNumbersAndIndexes();
  updateSameTimeGrouping();
  updateTotals();
  evaluateEmptyEtcDetailVisibility();
});

// —— 进入页面先排一次；提交前再排一次（夜班排序入口） ——
(function bindNightSortEntrypoints(){
  const onceKey = "__night_sort_bound__";
  if (window[onceKey]) return;
  window[onceKey] = true;

  document.addEventListener("DOMContentLoaded", () => {
    if (typeof window.__resortByTime === "function") window.__resortByTime();
    const form = document.querySelector('form[method="post"]');
    if (form) {
      form.addEventListener("submit", () => {
        if (typeof window.__resortByTime === "function") window.__resortByTime();
      });
    }
  });
})();


// === 热修复：若模板里没有“実際ETC 会社 → 運転手”显示行，运行时自动插入 ===
function ensureActualEtcIndicator(){
  const depositInput = document.getElementById('deposit-input');
  if (!depositInput) return;

  // 已有就不重复加
  if (document.getElementById('actual_etc_company_to_driver_view')) return;

  const holder = depositInput.closest('div'); // 入金额卡片内层 div
  if (!holder) return;

  const wrap = document.createElement('div');
  wrap.className = 'small text-muted mt-1';
  wrap.innerHTML = '実際ETC 会社 → 運転手：<span id="actual_etc_company_to_driver_view">0</span> 円';
  holder.appendChild(wrap);

  const hid = document.createElement('input');
  hid.type = 'hidden';
  hid.id = 'actual_etc_company_to_driver';
  hid.name = 'actual_etc_company_to_driver';
  hid.value = '0';
  holder.appendChild(hid);
}


// === BEGIN PATCH: 重命名负担选项文字 独立的一小段脚本，不在任何函数里===
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.etc-riding-charge-select,.etc-empty-charge-select')
    .forEach(sel => {
      sel.querySelectorAll('option').forEach(op => {
        const v = (op.value || '').trim();
        if (v === 'driver')   op.textContent = 'ドライバー（立替→後日返還）';
        if (v === 'company')  op.textContent = '会社（会社負担）';
        if (v === 'customer') op.textContent = 'お客様（直接精算）';
      });
    });
});
// === END PATCH ===