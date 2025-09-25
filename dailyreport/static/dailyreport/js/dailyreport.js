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
// >>> 追加: 排序开关（仅提交时排序）
const ENABLE_LIVE_SORT = false;
// <<< 追加 end
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

/* === [SameTime grouping BEGIN] 新增：同一时间从第2行开始加“↳”并缩进 === */
function updateSameTimeGrouping() {
  const { dataTb } = getFormScope();
  if (!dataTb) return;

  // 1) 收集所有可见行，按时间字符串分组（例如 "10:00"）
  const rows = $all("tr.report-item-row", dataTb).filter(r => r.style.display !== "none");
  const groups = Object.create(null);

  rows.forEach(row => {
    const timeInput = row.querySelector("input[name$='-ride_time']") || row.querySelector(".time-input");
    const t = (timeInput ? String(timeInput.value).trim() : "");
    const key = t || "__EMPTY__";          // 空时间也分到一组，但不会加箭头
    (groups[key] ||= []).push(row);
  });

  // 2) 遍历组：每组的第1条正常、从第2条开始加前缀与类
  Object.entries(groups).forEach(([key, arr]) => {
    // 先把这一组里所有行恢复为“无前缀”的状态
    arr.forEach(row => {
      row.classList.remove("same-time-child");
      const timeInput = row.querySelector("input[name$='-ride_time']") || row.querySelector(".time-input");
      const cell = timeInput?.closest("td");
      if (!cell) return;
      const pref = cell.querySelector(".same-time-prefix");
      if (pref) pref.remove(); // 清理老前缀
    });

    if (key === "__EMPTY__") return; // 时间为空的不做箭头逻辑

    // 从第2条开始加“↳ ”
    if (arr.length > 1) {
      arr.forEach((row, idx) => {
        if (idx === 0) return; // 第一条不加
        row.classList.add("same-time-child");
        const timeInput = row.querySelector("input[name$='-ride_time']") || row.querySelector(".time-input");
        const cell = timeInput?.closest("td");
        if (!cell) return;
        const span = document.createElement("span");
        span.className = "same-time-prefix";
        span.textContent = "↳ ";
        // 把箭头插在时间 input 前面
        cell.insertBefore(span, timeInput);
      });
    }
  });
}
/* === [SameTime grouping END] === */

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
        updateSameTimeGrouping(); // <<< 新增：删除后同步组样式
        updateTotals();
        updateSmartHintPanel?.();
        if (ENABLE_LIVE_SORT) window.__resortByTime?.(); // >>> 追加：删除后也重排
      }
    });
  });

  // 移除（新建行）
  $all(".remove-row", row).forEach(btn => {
    btn.addEventListener("click", () => {
      if (!confirm("确定移除此行？")) return;
      const cb = row.querySelector("input[name$='-DELETE']");
      if (cb) {
        cb.checked = true;
        row.style.display = "none";
      } else {
        row.remove();
      }
      updateRowNumbersAndIndexes();
      updateSameTimeGrouping(); // <<< 新增
      updateTotals();
      updateSmartHintPanel?.();
      if (ENABLE_LIVE_SORT) window.__resortByTime?.(); // >>> 追加
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

  // >>> 追加: 调整“时间”即重排 + 重新分组
  const rideTimeInput = row.querySelector("input[name$='-ride_time']") || row.querySelector(".time-input");
  if (rideTimeInput) {
    rideTimeInput.addEventListener("change", () => {
      if (ENABLE_LIVE_SORT) window.__resortByTime?.();
      updateRowNumbersAndIndexes();
      updateSameTimeGrouping(); // <<< 新增：时间变化后刷新组
    });
    rideTimeInput.addEventListener("input",  () => {
      if (ENABLE_LIVE_SORT) window.__resortByTime?.();
      updateRowNumbersAndIndexes();
      updateSameTimeGrouping(); // <<< 新增
    });
  }
  // <<< 追加 end

  if (pendingCb) {
    pendingCb.addEventListener("change", () => {
      updateTotals(); updateSmartHintPanel();
      if (pendingHint) pendingHint.classList.toggle("d-none", !pendingCb.checked);
      if (ENABLE_LIVE_SORT) window.__resortByTime?.();// 待入状态变化也重排（可选）
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
  updateSameTimeGrouping(); // <<< 新增：新增行后刷新组
  updateTotals();
  updateSmartHintPanel();
  window.__resortByTime?.(); // >>> 追加：新增后重排
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
  updateSameTimeGrouping(); // <<< 新增
  updateTotals();
  updateSmartHintPanel();
  window.__resortByTime?.(); // >>> 追加：按指定行插入后重排
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

  // >>> 追加: 三类 Uber 的独立合计
  let uberReservationTotal = 0, uberReservationCount = 0;
  let uberTipTotal         = 0, uberTipCount         = 0;
  let uberPromotionTotal   = 0, uberPromotionCount   = 0;
  let specialUberSum = 0;
  // <<< 追加结束

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

    // >>> 修改: 非貸切时，三类 Uber（予約/チップ/プロモ）只计入売上合計，不进入 meterSum
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
    // <<< 修改结束
  });

  // >>> 修改: 売上合計 = meterSum（不含三类 Uber）+ specialUberSum + 貸切現金 + 貸切未収
  const salesTotal = meterSum + specialUberSum + charterCashTotal + charterUncollectedTotal;
  // <<< 修改结束

  const idText = (id, n) => { const el=document.getElementById(id); if (el) el.textContent = Number(n||0).toLocaleString(); };
  idText("total_meter_only", meterSum);

  // >>> 追加: 写回三类 Uber 的合计与件数
  idText("uber-reservation-total", uberReservationTotal);
  idText("uber-reservation-count", uberReservationCount);
  idText("uber-tip-total",         uberTipTotal);
  idText("uber-tip-count",         uberTipCount);
  idText("uber-promotion-total",   uberPromotionTotal);
  idText("uber-promotion-count",   uberPromotionCount);
  // <<< 追加结束

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

  // ==== [ETC LOGIC PATCH START @ 2025-09-14] ====
  function _yen(v){ if(v==null) return 0; const n=Number(String(v).replace(/[,，\s]/g,'')); return isFinite(n)?n:0; }

  const rideEtc = _yen(document.querySelector('#id_ride_etc_total, .js-ride-etc-total')?.value);
  const rideMeth = (document.querySelector('#id_ride_etc_payment_method, .js-ride-etc-method')?.value||'').trim();

  const emptyEtc   = _yen(document.querySelector('#id_etc_uncollected, .js-empty-etc-amount')?.value);
  const emptyCard  = (document.querySelector('#id_etc_empty_card, .js-empty-etc-card')?.value||'').trim();
  const retClaimed = _yen(document.querySelector('#id_etc_return_fee_claimed, .js-return-fee-claimed')?.value);
  const retMethod  = (document.querySelector('#id_etc_return_fee_method, .js-return-fee-method')?.value||'').trim();

  // 1) ETC 应收合计
  const etcReceivable = rideEtc + emptyEtc;
  const etcReceivableEl = document.querySelector('#etc-expected-output, .js-etc-receivable');
  if (etcReceivableEl) etcReceivableEl.value = etcReceivable.toLocaleString();

  // 2) 空车ETC → 司机负担 / 未収ETC
  let driverBurden = 0;
  let uncollectedEtc = 0;
  if (emptyCard === 'company') {
    if (retMethod === 'app_ticket') {
      const cover = Math.min(retClaimed, emptyEtc);
      driverBurden = Math.max(emptyEtc - cover, 0);
      uncollectedEtc = Math.max(retClaimed - emptyEtc, 0);
    } else {
      driverBurden = emptyEtc;
    }
  }
  const driverBurdenEl = document.querySelector('.js-driver-burden');
  if (driverBurdenEl) driverBurdenEl.textContent = `司机负担：${driverBurden.toLocaleString()}円`;
  const uncollectedEl = document.querySelector('.js-uncollected-etc');
  if (uncollectedEl) uncollectedEl.textContent = `未収ETC：${uncollectedEtc.toLocaleString()}円；`;

  // 3) 過不足：加上自分ETC卡
  const income      = _yen(document.querySelector('#id_income, .income-input')?.value);
  const cashNagashi = _yen(document.querySelector('#id_cash_nagashi, .cash-nagashi-input')?.value);
  const charterCash = _yen(document.querySelector('#id_charter_cash, .charter-cash-input')?.value);
  let imbalance = income - cashNagashi - charterCash;
  if (rideMeth === 'self') {
    imbalance += rideEtc;
  }
  const imbalanceEl = document.querySelector('#id_imbalance, .imbalance-total');
  if (imbalanceEl) {
    if ('value' in imbalanceEl) imbalanceEl.value = imbalance.toLocaleString();
    else imbalanceEl.textContent = imbalance.toLocaleString();
  }
  // ==== [ETC LOGIC PATCH END @ 2025-09-14] ====
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

  // 4) 指定行插入（**唯一入口**）
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

  // 6) 初始执行（顺序：时长→ETC→编号→同时间分组→合计→提示→貸切状态）
  updateDuration();
  updateEtcDifference();
  updateEtcShortage();
  updateEtcInclusionWarning();
  updateRowNumbersAndIndexes();
  updateSameTimeGrouping(); // <<< 新增：页面初次渲染后做一次分组
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
    // —— 排序后做一次“同时间分组”以保持箭头和缩进正确 ——
    if (typeof updateSameTimeGrouping === "function") updateSameTimeGrouping();
  }

  // >>> 追加: 暴露排序函数，供其它事件实时调用
  window.__resortByTime = sortRowsByTime;
  // <<< 追加 end

  window.addEventListener("DOMContentLoaded", () => {
    const form = document.querySelector('form[method="post"]'); if (!form) return;
    form.addEventListener('submit', () => {
      sortRowsByTime();
      if (typeof updateRowNumbersAndIndexes === 'function') updateRowNumbersAndIndexes();
      if (typeof updateSameTimeGrouping === 'function') updateSameTimeGrouping();
    });
    // 页面加载完成先排一次，确保初始顺序正确
    sortRowsByTime(); // >>> 追加
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
