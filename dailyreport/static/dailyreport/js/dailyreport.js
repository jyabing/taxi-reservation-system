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
const ENABLE_LIVE_SORT = false;
function $(sel, root){ return (root||document).querySelector(sel); }
function $all(sel, root){ return Array.from((root||document).querySelectorAll(sel)); }
function getRow(el){ return el?.closest("tr.report-item-row") || el?.closest("tr"); }
function toInt(v, fallback=0){ const n=parseInt(String(v??"").replace(/[^\d-]/g,""),10); return Number.isFinite(n)?n:fallback; }
function _yen(v){ if(v==null) return 0; const n=Number(String(v).replace(/[,，\s]/g,'')); return isFinite(n)?n:0; }

// ============ 作用域获取 ============
function getFormScope() {
  const btn = document.getElementById('insert-at-btn') || document.getElementById('add-row-btn') || document.querySelector('table.report-table');
  const form = btn ? (btn.closest('form') || document) : document;
  const table = form.querySelector('table.report-table') || form.querySelector('table');
  const tpl = form.querySelector('#empty-form-template');
  let bodies = [];
  if (table) bodies = Array.from(table.tBodies || table.querySelectorAll('tbody'));
  const dataTb = bodies.find(b => b !== tpl) || bodies[0] || null;
  const total = form.querySelector("input[name$='-TOTAL_FORMS']");
  return { form, table, tpl, dataTb, total };
}

// ============ 时间/工时 ============
document.addEventListener('DOMContentLoaded', () => {
  if (typeof flatpickr === 'function') {
    flatpickr(".time-input", { enableTime:true, noCalendar:true, dateFormat:"H:i", time_24hr:true, locale:"ja" });
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

// ============ 同时刻缩进 ============
function updateSameTimeGrouping() {
  const { dataTb } = getFormScope();
  if (!dataTb) return;
  const rows = $all("tr.report-item-row", dataTb).filter(r => r.style.display !== "none");
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

// ============ 行事件绑定 ============
function bindRowEvents(row) {
  if (typeof flatpickr === 'function') {
    $all(".time-input", row).forEach(el => {
      flatpickr(el, { enableTime:true, noCalendar:true, dateFormat:"H:i", time_24hr:true, locale:"ja" });
    });
  }
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
        updateSmartHintPanel?.();
        if (ENABLE_LIVE_SORT) window.__resortByTime?.();
      }
    });
  });
  $all(".remove-row", row).forEach(btn => {
    btn.addEventListener("click", () => {
      if (!confirm("确定移除此行？")) return;
      const cb = row.querySelector("input[name$='-DELETE']");
      if (cb) { cb.checked = true; row.style.display = "none"; }
      else { row.remove(); }
      updateRowNumbersAndIndexes();
      updateSameTimeGrouping();
      updateTotals();
      updateSmartHintPanel?.();
      if (ENABLE_LIVE_SORT) window.__resortByTime?.();
    });
  });

  const amountInput = row.querySelector("input[name$='-meter_fee']");
  const methodSelect= row.querySelector("select[name$='-payment_method']");
  const pendingCb   = row.querySelector("input[name$='-is_pending']") || row.querySelector(".pending-checkbox");
  const pendingHint = row.querySelector(".pending-mini-hint");
  const charterAmountInput = row.querySelector(".charter-amount-input");
  const charterCheckbox    = row.querySelector("input[name$='-is_charter']");

  if (amountInput)  amountInput.addEventListener("input",  () => { updateTotals(); updateSmartHintPanel(); });
  if (methodSelect) methodSelect.addEventListener("change", () => { updateTotals(); updateSmartHintPanel(); });

  const rideTimeInput = row.querySelector("input[name$='-ride_time']") || row.querySelector(".time-input");
  if (rideTimeInput) {
    rideTimeInput.addEventListener("change", () => {
      if (ENABLE_LIVE_SORT) window.__resortByTime?.();
      updateRowNumbersAndIndexes(); updateSameTimeGrouping();
    });
    rideTimeInput.addEventListener("input",  () => {
      if (ENABLE_LIVE_SORT) window.__resortByTime?.();
      updateRowNumbersAndIndexes(); updateSameTimeGrouping();
    });
  }

  if (pendingCb) {
    pendingCb.addEventListener("change", () => {
      updateTotals(); updateSmartHintPanel();
      if (pendingHint) pendingHint.classList.toggle("d-none", !pendingCb.checked);
      if (ENABLE_LIVE_SORT) window.__resortByTime?.();
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
  const tr = tmp.querySelector('tr'); if (!tr) return null;
  tr.classList.remove('d-none','hidden','invisible','template-row');
  tr.style.removeProperty('display'); tr.removeAttribute('aria-hidden');
  tr.querySelectorAll('input,select,textarea,button').forEach(el=>{ el.disabled=false; el.removeAttribute('disabled'); });
  total.value = String(count + 1);
  return tr;
}
function addRowToEnd() {
  const { dataTb } = getFormScope(); if (!dataTb) return false;
  const tr = cloneRowFromTemplate(); if (!tr) return false;
  dataTb.appendChild(tr); bindRowEvents(tr);
  updateRowNumbersAndIndexes(); updateSameTimeGrouping(); updateTotals(); updateSmartHintPanel();
  window.__resortByTime?.();
  try { tr.scrollIntoView({behavior:'smooth', block:'center'});}catch(e){}
  (tr.querySelector('.time-input')||tr.querySelector('input,select'))?.focus?.();
  return true;
}
function insertRowAfter(indexOneBased) {
  const { dataTb } = getFormScope(); if (!dataTb) return false;
  const tr = cloneRowFromTemplate(); if (!tr) return false;
  const rows = $all("tr.report-item-row", dataTb);
  const all  = rows.length ? rows : $all("tr", dataTb);
  if (all.length === 0) dataTb.appendChild(tr);
  else {
    const n = Math.min(Math.max(1, indexOneBased||1), all.length);
    const anchor = all[n-1]; (anchor.parentNode || dataTb).insertBefore(tr, anchor.nextSibling);
  }
  bindRowEvents(tr);
  updateRowNumbersAndIndexes(); updateSameTimeGrouping(); updateTotals(); updateSmartHintPanel();
  window.__resortByTime?.();
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

// ============ 合计主函数（含 ETC 口径） ============
function updateTotals() {
  const { dataTb } = getFormScope();
  if (!dataTb) return;

  const totalMap = { cash:0, uber:0, didi:0, go:0, credit:0, kyokushin:0, omron:0, kyotoshi:0, qr:0 };
  let meterSum=0, charterCashTotal=0, charterUncollectedTotal=0;

  // Uber 三类
  let uberReservationTotal = 0, uberReservationCount = 0;
  let uberTipTotal         = 0, uberTipCount         = 0;
  let uberPromotionTotal   = 0, uberPromotionCount   = 0;
  let specialUberSum = 0;

  // —— 汇总明细 —— //
  $all(".report-item-row", dataTb).forEach(row => {
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
      if (fee > 0) {
        const raw = payment;
        const isUberReservation = raw === 'uber_reservation';
        const isUberTip         = raw === 'uber_tip';
        const isUberPromotion   = raw === 'uber_promotion';
        const isSpecialUber     = isUberReservation || isUberTip || isUberPromotion;

        if (isSpecialUber) {
          specialUberSum += fee;
          if (isUberReservation) { uberReservationTotal += fee; uberReservationCount += 1; }
          else if (isUberTip)    { uberTipTotal         += fee; uberTipCount         += 1; }
          else if (isUberPromotion){ uberPromotionTotal += fee; uberPromotionCount   += 1; }
        } else {
          const method = resolveJsPaymentMethod(payment);
          meterSum += fee;
          if (Object.hasOwn(totalMap, method)) totalMap[method] += fee;
        }
      }
    } else if (charterAmount>0) {
      const CASH = ['jpy_cash','rmb_cash','self_wechat','boss_wechat'];
      const UNCOLLECTED = ['to_company','bank_transfer',''];
      if (CASH.includes(charterPayMethod)) charterCashTotal += charterAmount;
      else if (UNCOLLECTED.includes(charterPayMethod)) charterUncollectedTotal += charterAmount;
    }
  });

  // 売上合計
  const salesTotal = meterSum + specialUberSum + charterCashTotal + charterUncollectedTotal;

  // —— 写回 UI —— //
  const idText = (id, n) => { const el=document.getElementById(id); if (el) el.textContent = Number(n||0).toLocaleString(); };
  idText("total_meter_only", meterSum);
  idText("uber-reservation-total", uberReservationTotal);
  idText("uber-reservation-count", uberReservationCount);
  idText("uber-tip-total",         uberTipTotal);
  idText("uber-tip-count",         uberTipCount);
  idText("uber-promotion-total",   uberPromotionTotal);
  idText("uber-promotion-count",   uberPromotionCount);
  idText("total_meter", salesTotal);
  idText("sales-total", salesTotal);
  idText("total_cash", totalMap.cash);
  idText("total_credit", totalMap.credit);
  idText("charter-cash-total", charterCashTotal);
  idText("charter-uncollected-total", charterUncollectedTotal);
  Object.entries(totalMap).forEach(([k,v]) => idText(`total_${k}`, v));

  // —— ETC 统一口径 —— //
  const rideEtc     = _yen(document.querySelector('#id_etc_collected')?.value);
  const riderPayer  = (document.querySelector('#id_etc_rider_payer, .js-etc-rider-payer')?.value || 'company').trim();

  const emptyEtcInput = document.querySelector('.js-empty-etc-amount') || document.querySelector('#id_etc_uncollected');
  let emptyEtc = _yen(emptyEtcInput?.value);
  if (!emptyEtc) {
    const txt = document.querySelector("div[style*='ui-monospace']")?.textContent || "";
    const m = txt.match(/空車ETC\s*([0-9,]+)/); if (m) emptyEtc = _yen(m[1]);
  }
  const emptyCard  = (document.querySelector('#id_etc_empty_card')?.value || '').trim();         // 'company' | 'own'
  const retClaimed = _yen(document.querySelector('#id_etc_return_fee_claimed')?.value);
  const retMethod  = (document.querySelector('#id_etc_return_fee_method')?.value || '').trim();  // 'none' | 'app_ticket' | 'cash_to_driver'

  // 应收合计（只计公司侧）：
  // 乘車ETC：会社 → 计应收；自己/客人 → 不计应收
  // 空車ETC：会社卡 → 计应收；自己卡 → 不计应收（对公司无应收）
  const etcReceivableRidePart   = (riderPayer === 'company') ? rideEtc  : 0;
  const etcReceivableEmptyPart  = (emptyCard  === 'company') ? emptyEtc : 0;
  const etcReceivable = etcReceivableRidePart + etcReceivableEmptyPart;

  const etcReceivableEl = document.querySelector('#etc-expected-output, .js-etc-receivable');
  if (etcReceivableEl) etcReceivableEl.value = etcReceivable.toLocaleString();
  const hiddenExpected = document.getElementById('id_etc_expected');
  if (hiddenExpected) hiddenExpected.value = etcReceivable;

  // —— 过不足 —— //
  const income      = _yen(document.getElementById('deposit-input')?.value); // 入金
  const cashNagashi = totalMap.cash;        // 現金(ながし)
  const charterCash = charterCashTotal;     // 貸切現金
  let imbalance = income - cashNagashi - charterCash;

  // A) 乘車ETC=自己卡 → 公司下月返还司机 → 过不足 + 乗車ETC（正数）
  if (riderPayer === 'own') {
    imbalance += rideEtc;
  }

  // B) 空車ETC（回程）对过不足的影响
  if (emptyCard === 'own') {
    // 自己卡
    if (retMethod === 'app_ticket') {
      // ④ app 已支付 & 自己卡：公司下月返还司机空車实际发生 -> 过不足 + 空車ETC
      imbalance += emptyEtc;
    } else {
      // ② 客人现金 或 none：仅备查，不影响公司侧过不足
      // imbalance += 0;
    }
  } else if (emptyCard === 'company') {
    // 公司卡
    if (retMethod === 'app_ticket') {
      // ③ app 已支付 & 公司卡：司机负担不足部分 -> 过不足 - max(0, 空車 - 受領)
      const driverBurden = Math.max(0, emptyEtc - retClaimed);
      imbalance -= driverBurden;
    } else if (retMethod === 'cash_to_driver' || retMethod === 'none' || retMethod === '') {
      // ① 客人现金 & 公司卡，或无一体：高速费全由司机负担 -> 过不足 - 空車ETC
      imbalance -= emptyEtc;
    }
  }

  // 写回“过不足”（difference-output 是你页面里的展示 DOM）
  const diffEl = document.getElementById("difference-output")
              || document.getElementById("deposit-difference")
              || document.getElementById("shortage-diff");
  if (diffEl) diffEl.textContent = Number(imbalance||0).toLocaleString();

  const imbalanceEl = document.querySelector('#id_imbalance, .imbalance-total');
  if (imbalanceEl) {
    if ('value' in imbalanceEl) imbalanceEl.value = imbalance.toLocaleString();
    else imbalanceEl.textContent = imbalance.toLocaleString();
  }

  // 生成票据备注（若你需要）
  buildReceiptNotes();
}

// ============ 智能提示面板 ============
function updateSmartHintPanel() {
  const panel = document.querySelector("#smart-hint-panel"); if (!panel) return;
  const cashTotal     = toInt(document.querySelector("#total_cash")?.textContent, 0);
  const etcCollected  = toInt(document.querySelector("#id_etc_collected")?.value, 0);
  // 读取由 updateEtcDifference() 写回的隐藏值，才是“真实未收”
  const etcUncollected = toInt(document.querySelector("#id_etc_uncollected_hidden")?.value, 0);
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

// ============ ETC 相关（仅黄框/司机负担，不再改应收） ============
function readIntById(id, fallback=0){
  const el=document.getElementById(id);
  if(!el) return fallback;
  const raw=el.value??el.textContent??`${fallback}`;
  return toInt(raw,fallback);
}

function updateEtcDifference() {
  // 是否存在“空車ETC 金額”输入框（新版）
  const hasNewEmpty = !!document.getElementById('id_etc_uncollected');

  // 空車ETC 金額
  const emptyAmount = hasNewEmpty ? readIntById('id_etc_uncollected', 0) : 0;

  // 回程費（受領額）及其支付方式
  const returnFee = hasNewEmpty ? readIntById('id_etc_return_fee_claimed', 0) : 0;
  const returnFeeMethod = hasNewEmpty ? (document.getElementById('id_etc_return_fee_method')?.value || 'none') : 'none';
  // 空車用卡：company/own
  const emptyCardRaw = hasNewEmpty ? (document.getElementById('id_etc_empty_card')?.value || 'company') : 'company';
  const emptyCard = (emptyCardRaw === 'company') ? 'company_card' : 'personal_card';

  // 覆盖（仅当 受領方法=アプリ/チケット 时）
  const coveredByCustomer = (returnFeeMethod === 'app_ticket') ? returnFee : 0;

  // 展示用的“未收ETC / 司机负担”（黄框）
  let etcUncollected = 0, etcDriverBurden = 0;

  if (hasNewEmpty) {
    if (emptyCard === 'company_card' || emptyCard === '') {
      // 公司卡：可能产生覆盖前后的差额
      const cover = Math.min(coveredByCustomer, emptyAmount);
      // 覆盖不够 -> 司机负担
      etcDriverBurden = Math.max(0, emptyAmount - cover);
      // 覆盖过多 -> 记为“未收ETC”（仅展示/统计）
      etcUncollected  = Math.max(0, coveredByCustomer - emptyAmount);

      // 其它受領方式（现金给司机 / 无一体），黄框口径不变（都视为无覆盖）：
      if (returnFeeMethod !== 'app_ticket') {
        // 无一体时，把“覆盖”视为 0
        etcDriverBurden = emptyAmount; // 全部由司机负担（公司卡）
        etcUncollected  = 0;
        if (returnFeeMethod === 'cash_to_driver') {
          // 现金交给司机仅影响“过不足”，黄框仍不记“未收”
          //（等同于 none：公司侧没有未收）
          // 维持上面的 etcDriverBurden = emptyAmount
        }
      }
    } else {
      // 自己卡：黄框不反映公司侧未收/负担（互抵或与公司无关）
      etcUncollected = 0;
      etcDriverBurden = 0;
    }
  } else {
    // 老页面兜底（几乎不会走到）
    etcUncollected  = readIntById('id_etc_uncollected', 0);
    etcDriverBurden = readIntById('id_etc_shortage', 0);
  }

  // 黄框展示
  const display = document.getElementById('etc-diff-display');
  if (display) {
    display.className = (etcDriverBurden > 0 || etcUncollected > 0)
      ? 'alert alert-warning small py-1 px-2 mt-1'
      : 'alert alert-info small py-1 px-2 mt-1';
    display.innerText = `未收 ETC：${etcUncollected.toLocaleString()} 円；司机负担：${etcDriverBurden.toLocaleString()} 円`;
  }

  // 隐藏未收（若有）
  const hiddenUncol = document.getElementById('id_etc_uncollected_hidden');
  if (hiddenUncol) hiddenUncol.value = etcUncollected;

  // “ETC不足”只读展示
  const etcShortEl = document.getElementById('id_etc_shortage');
  if (etcShortEl) {
    etcShortEl.value = etcDriverBurden;
    etcShortEl.classList.toggle('text-danger', etcDriverBurden > 0);
    etcShortEl.classList.toggle('fw-bold',     etcDriverBurden > 0);
  }

  // 生成票据备注（若你需要）
  buildReceiptNotes();
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

// ============ 貸切：行状态 ============
function applyCharterState(row, isCharter) {
  if (!row) return;
  const meterInput           = row.querySelector(".meter-fee-input");
  const charterAmountInput   = row.querySelector(".charter-amount-input");
  const charterPaymentSelect = row.querySelector(".charter-payment-method-select");
  if (meterInput) {
    meterInput.removeAttribute('disabled');
    if (!meterInput.dataset.originalValue) meterInput.dataset.originalValue = meterInput.value || ""
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
  $all("tr.report-item-row").forEach(bindRowEvents);

  const { dataTb } = getFormScope();
  if (dataTb) {
    dataTb.addEventListener("click", (e) => {
      const btn = e.target.closest(".insert-below");
      if (!btn) return;
      e.preventDefault();
      const row = getRow(btn);
      const index = row ? ( ($all("tr.report-item-row", dataTb).indexOf ? $all("tr.report-item-row", dataTb).indexOf(row) : $all("tr.report-item-row", dataTb).findIndex(r=>r===row)) + 1 ) : 1;
      insertRowAfter(index);
    });
  }
  const addBtn = document.getElementById('add-row-btn');
  if (addBtn && !addBtn.dataset.boundOnce) {
    addBtn.dataset.boundOnce = "1";
    addBtn.addEventListener('click', (e) => { e.preventDefault(); addRowToEnd(); });
  }
  const idxBtn   = document.getElementById('insert-at-btn');
  const idxInput = document.getElementById('insert-index-input');
  if (idxBtn && idxInput && !idxBtn.dataset.boundOnce) {
    idxBtn.dataset.boundOnce = "1";
    idxBtn.addEventListener('click', (e) => {
      e.preventDefault();
      const v = parseInt(idxInput.value, 10) || 1;
      insertRowAfter(v);
    });
  }

  // 监听（含 rider payer）
  [
    ['id_etc_collected_cash',    [updateEtcDifference, updateEtcShortage]],
    ['id_etc_uncollected',       [updateEtcDifference, updateEtcShortage, updateTotals]],
    ['id_etc_collected',         [updateEtcInclusionWarning, updateEtcShortage, updateTotals]],
    ['id_etc_rider_payer',       [updateTotals]],
    ['id_deposit_amount',        [updateEtcDifference, updateEtcInclusionWarning]],
    ['clock_in',                 [updateDuration]],
    ['clock_out',                [updateDuration]],
    ['break-time-input',         [updateDuration]],
    ['id_etc_empty_card',        [updateEtcDifference, updateTotals]],
    ['id_etc_return_fee_method', [updateEtcDifference, updateTotals]],
    ['id_etc_return_fee_claimed',[updateEtcDifference, updateTotals]],
    ['id_etc_payment_method',    [updateTotals]],
  ].forEach(([id, fns]) => {
    const el = document.getElementById(id);
    if (el) {
      fns.forEach(fn => el.addEventListener("input", fn));
      if (el.tagName === 'SELECT') fns.forEach(fn => el.addEventListener("change", fn));
    }
  });

  updateDuration();
  updateEtcDifference();
  updateEtcShortage();
  updateEtcInclusionWarning();
  updateRowNumbersAndIndexes();
  updateSameTimeGrouping();
  updateTotals();
  updateSmartHintPanel();
  hydrateAllCharterRows();
});

// ===== 票据备注：安全空实现（可放在夜班排序块之前）=====
function buildReceiptNotes() {
  // 可选：如果你有一个 <div id="receipt-notes"></div> 用来显示打印票据提示，
  // 这里生成文本；若没有该容器，本函数什么也不做，保证不报错。
  const box = document.getElementById('receipt-notes');
  if (!box) return;

  // 你可以在这里根据当前 DOM 的 ETC 字段拼接想显示的文案
  // 为了演示，先清空：
  box.innerHTML = '';

  // 例如：
  // const rideEtc = Number(String(document.querySelector('#id_etc_collected')?.value||'0').replace(/[^\d]/g,''));
  // if (rideEtc > 0) { box.textContent = `乗車ETC：${rideEtc.toLocaleString()}円`; }
}


// ============ 夜班排序 ============
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
    if (typeof updateSameTimeGrouping === "function") updateSameTimeGrouping();
  }
  window.__resortByTime = sortRowsByTime;
  window.addEventListener("DOMContentLoaded", () => {
    const form = document.querySelector('form[method="post"]'); if (!form) return;
    form.addEventListener('submit', () => {
      sortRowsByTime();
      if (typeof updateRowNumbersAndIndexes === 'function') updateRowNumbersAndIndexes();
      if (typeof updateSameTimeGrouping === 'function') updateSameTimeGrouping();
    });
    sortRowsByTime();
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


// ==== Persist user's selections to avoid being reset by confirmations ====
(function persistUserSelections(){
  // 想持久化的控件（按 id 选择器）
  const PERSIST_IDS = [
    '#id_etc_rider_payer',        // 乗車ETC の支払者
    '#id_etc_payment_method',     // 乗車ETC 支付方式
    '#id_etc_empty_card',         // 空車ETC カード
    '#id_etc_return_fee_method',  // 回程費 支払方法
  ];
  // 也可把金额类做一下（可选）
  const PERSIST_INPUT_IDS = [
    '#id_etc_uncollected',        // 空車ETC 金額
    '#id_etc_return_fee_claimed', // 回程費 受領額
    '#deposit-input',             // 入金額
  ];

  function keyFor(sel){ return 'dr_persist:' + sel; }

  function restoreOne(sel){
    const el = document.querySelector(sel);
    if (!el) return;
    const saved = localStorage.getItem(keyFor(sel));
    if (saved == null) return;
    // 只在值真的不同时写回，避免触发不必要事件
    if (String(el.value) !== saved) {
      el.value = saved;
      el.dispatchEvent(new Event('change', {bubbles:true}));
      el.dispatchEvent(new Event('input',  {bubbles:true}));
    }
  }

  function bindSave(sel){
    const el = document.querySelector(sel);
    if (!el) return;
    const save = () => localStorage.setItem(keyFor(sel), String(el.value ?? ''));
    el.addEventListener('change', save);
    el.addEventListener('input',  save);
  }

  // 等 DOM 可用后恢复 + 绑定
  document.addEventListener('DOMContentLoaded', () => {
    [...PERSIST_IDS, ...PERSIST_INPUT_IDS].forEach(restoreOne);
    [...PERSIST_IDS, ...PERSIST_INPUT_IDS].forEach(bindSave);
  });
})();



/*
==== [BEGIN] ETC 回程场景测试按钮：嵌入空車ETC 詳細卡片（支持任意金额） ====
(function setupEtcReturnScenarioTest(){
  document.addEventListener('DOMContentLoaded', () => {
    const btn = document.createElement('button');
    btn.type = "button";
    btn.textContent = "ETC回程测试";
    btn.className = "btn btn-sm btn-outline-primary ms-2";

    const mount = document.querySelector("#etc-diff-display")?.parentNode
               || document.querySelector("#smart-hint-panel")
               || document.body;
    mount.appendChild(btn);

    btn.addEventListener("click", () => {
      const scenario = prompt("输入场景编号：1=客現+公司卡，2=客現+自己卡，3=App支付+公司卡，4=App支付+自己卡");
      if (!scenario) return;

      // 输入金额
      const amtStr = prompt("请输入空車ETC金额", "3450");
      const amt = parseInt(amtStr || "0", 10);

      const emptyEtcEl = document.getElementById('id_etc_uncollected');
      const retFeeEl   = document.getElementById('id_etc_return_fee_claimed');
      const emptyCardSel = document.getElementById('id_etc_empty_card');
      const retMethodSel = document.getElementById('id_etc_return_fee_method');

      if (emptyEtcEl) {
        emptyEtcEl.value = amt;
        emptyEtcEl.dispatchEvent(new Event('input',{bubbles:true}));
      }
      if (retFeeEl) {
        retFeeEl.value = amt; // 默认受領額=相同金额，你可再手动改小测试差额
        retFeeEl.dispatchEvent(new Event('input',{bubbles:true}));
      }

      switch(scenario){
        case "1": // 客現 + 公司卡
          if (emptyCardSel) emptyCardSel.value = "company";
          if (retMethodSel) retMethodSel.value = "cash_to_driver";
          break;
        case "2": // 客現 + 自己卡
          if (emptyCardSel) emptyCardSel.value = "own";
          if (retMethodSel) retMethodSel.value = "cash_to_driver";
          break;
        case "3": // App支付 + 公司卡
          if (emptyCardSel) emptyCardSel.value = "company";
          if (retMethodSel) retMethodSel.value = "app_ticket";
          // 这里你可以手动把受領額改小于空車金额，测试“司机负担差额”
          break;
        case "4": // App支付 + 自己卡
          if (emptyCardSel) emptyCardSel.value = "own";
          if (retMethodSel) retMethodSel.value = "app_ticket";
          break;
      }

      if (emptyCardSel) emptyCardSel.dispatchEvent(new Event('change',{bubbles:true}));
      if (retMethodSel) retMethodSel.dispatchEvent(new Event('change',{bubbles:true}));

      updateEtcDifference();
      updateTotals();
    });
  });
})();
==== [END] ETC 回程场景测试按钮：嵌入空車ETC 詳細卡片（支持任意金额） ====
*/

/* ==== [BEGIN] ETC 回程场景测试按钮：嵌入空車ETC 詳細卡片（支持任意金额） ==== */
(function setupEtcReturnScenarioTest(){
  document.addEventListener('DOMContentLoaded', () => {
    const emptyEtcEl   = document.getElementById('id_etc_uncollected');
    const retFeeEl     = document.getElementById('id_etc_return_fee_claimed');
    const emptyCardSel = document.getElementById('id_etc_empty_card');
    const retMethodSel = document.getElementById('id_etc_return_fee_method');

    // 这些控件缺任何一个就不挂按钮
    if (!emptyEtcEl || !retFeeEl || !emptyCardSel || !retMethodSel) return;

    // 找到“空車ETC（回程）詳細”的卡片容器（就是包含输入框的那块 .border）
    const card = emptyEtcEl.closest('.border');
    if (!card) return;

    // 工具函数
    const toInt = s => parseInt(String(s||'').replace(/[^\d-]/g,''),10) || 0;
    function setSel(el,val){
      if (el && el.value !== val) {
        el.value = val;
        el.dispatchEvent(new Event('change',{bubbles:true}));
      }
    }
    function setNum(el,n){
      if (el) {
        el.value = n;
        el.dispatchEvent(new Event('input',{bubbles:true}));
      }
    }
    function ensureAmount(){
      let v = toInt(emptyEtcEl.value);
      if (!v) {
        const got = prompt('空車ETC 金額（円）を入力', '3450');
        v = toInt(got);
        if (!v) v = 3450;
        setNum(emptyEtcEl, v);
      }
      return v;
    }
    function refreshAll(){
      // 你的现有计算函数：黄框/ETC不足/过不足/提示等都会刷新
      if (typeof updateEtcDifference==='function') updateEtcDifference();
      if (typeof updateTotals==='function') updateTotals();
      if (typeof updateSmartHintPanel==='function') updateSmartHintPanel();
    }

    // 按钮条（放在卡片内，靠右）
    const bar = document.createElement('div');
    bar.className = 'd-flex flex-wrap gap-1 mt-2';
    bar.innerHTML = `
      <div class="ms-auto d-flex flex-wrap gap-1">
        <button type="button" class="btn btn-sm btn-outline-secondary" data-s="1">① 客現/会社卡</button>
        <button type="button" class="btn btn-sm btn-outline-secondary" data-s="2">② 客現/自己卡</button>
        <button type="button" class="btn btn-sm btn-outline-secondary" data-s="3">③ App済/会社卡</button>
        <button type="button" class="btn btn-sm btn-outline-secondary" data-s="4">④ App済/自己卡</button>
        <button type="button" class="btn btn-sm btn-outline-dark" data-s="0">重置</button>
      </div>
    `;
    card.appendChild(bar);

    // 交互逻辑
    bar.addEventListener('click', e => {
      const s = e.target.getAttribute('data-s');
      if (!s) return;

      if (s === '0') {
        // 重置为最保守：公司卡 / 无一体 / 受領0
        setSel(emptyCardSel,'company');
        setSel(retMethodSel,'none');
        setNum(retFeeEl,0);
        refreshAll();
        return;
      }

      const amt = ensureAmount();

      switch(s){
        case '1': // ① 客人现金 + 公司卡 => 司机负担全额（过不足 - emptyEtc）
          setSel(emptyCardSel,'company');
          setSel(retMethodSel,'cash_to_driver');
          setNum(retFeeEl,0);
          break;

        case '2': // ② 客人现金 + 自己卡 => 仅备查（过不足 0）
          setSel(emptyCardSel,'own');
          setSel(retMethodSel,'cash_to_driver');
          setNum(retFeeEl,0);
          break;

        case '3': // ③ App 已支付 + 公司卡 => 司机负担不足部分（过不足 - max(0, 空車-受領)）
          setSel(emptyCardSel,'company');
          setSel(retMethodSel,'app_ticket');
          // 先默认“受領=空車金额”，你可以手动改小来测试“差额即司机负担”
          setNum(retFeeEl,amt);
          break;

        case '4': // ④ App 已支付 + 自己卡 => 公司返还司机空車实际发生（过不足 + emptyEtc）
          setSel(emptyCardSel,'own');
          setSel(retMethodSel,'app_ticket');
          setNum(retFeeEl,amt);
          break;
      }

      refreshAll();
    });
  });
})();
/* ==== [END] ETC 回程场景测试按钮：嵌入空車ETC 詳細卡片（支持任意金额） ==== */


// ==== 乗車ETC 合計 测试按钮（选择支払者 + 任意金额） ====
(function setupRideEtcScenarioTest(){
  document.addEventListener('DOMContentLoaded', () => {
    // 按钮
    const btn = document.createElement('button');
    btn.type = "button";
    btn.textContent = "乗車ETC测试";
    btn.className = "btn btn-sm btn-outline-secondary ms-2";

    // 挂载位置：尽量靠 ETC 区域；找不到就挂在 body
    const mount = document.querySelector("#id_etc_collected")?.closest(".border")
              || document.querySelector("#etc-diff-display")?.parentNode
              || document.querySelector("#smart-hint-panel")
              || document.body;
    mount.appendChild(btn);

    // 主要控件
    const rideTotalEl   = document.getElementById('id_etc_collected');       // 乗車ETC 合計
    const riderPayerSel = document.getElementById('id_etc_rider_payer');     // 支払者（company/own/customer）
    const payMethodSel  = document.getElementById('id_etc_payment_method');  // 支付方式（可留用现有选项）

    btn.addEventListener('click', () => {
      if (!rideTotalEl || !riderPayerSel) {
        alert('页面上找不到 乗車ETC 合計 或 支払者 控件。');
        return;
      }

      // 1) 选择支払者
      const payer = prompt("乗車ETC 支払者：1=会社カード, 2=自己カード, 3=お客様カード", "1");
      if (!payer) return;
      const payerMap = { "1":"company", "2":"own", "3":"customer" };
      const payerVal = payerMap[payer.trim()];
      if (!payerVal) { alert("无效的输入"); return; }

      // 2) 输入金额
      const amtStr = prompt("请输入 乗車ETC 合計（円）", "4390");
      const amt = parseInt(amtStr || "0", 10);
      if (!(amt >= 0)) { alert("金额无效"); return; }

      // 3) （可选）选择一个支付方式（不影响计算口径，只是便于你联动 UI）
      let pmVal = payMethodSel?.value || "";
      if (payMethodSel) {
        const wantPm = confirm("是否同时选择一个 乗車ETC 支付方式？（点“确定”会弹出输入框，直接回车沿用当前选中值）");
        if (wantPm) {
          const pm = prompt("输入支付方式值（留空保持当前）\n例如：cash / credit_card / uber / ...", pmVal);
          if (pm != null && pm !== "") pmVal = pm;
        }
      }

      // 4) 写回并触发事件
      rideTotalEl.value = amt;
      rideTotalEl.dispatchEvent(new Event('input',  {bubbles:true}));
      rideTotalEl.dispatchEvent(new Event('change', {bubbles:true}));

      riderPayerSel.value = payerVal;
      riderPayerSel.dispatchEvent(new Event('change', {bubbles:true}));

      if (payMethodSel && pmVal !== undefined) {
        payMethodSel.value = pmVal;
        payMethodSel.dispatchEvent(new Event('change', {bubbles:true}));
      }

      // 5) 触发合计与提示
      // 乘車ETC 的应收/过不足都在 updateTotals 内处理；提示面板 & 包含判断一起刷新
      if (typeof updateTotals === 'function') updateTotals();
      if (typeof updateSmartHintPanel === 'function') updateSmartHintPanel();
      if (typeof updateEtcInclusionWarning === 'function') updateEtcInclusionWarning();
      if (typeof updateEtcDifference === 'function') updateEtcDifference(); // 不会改应收，只刷新黄框展示即可
    });
  });
})();




// 调试辅助
window.__insertRowDebug__ = function(){ return insertRowAfter(1); };
