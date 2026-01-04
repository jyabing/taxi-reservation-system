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
const ENABLE_LIVE_SORT = false;
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

// ====== 智能提示：ETC 自动引导 ======
function updateSmartHintPanel() {
  const panel = document.getElementById("smart-hint-panel");
  if (!panel) return;

  // 用单独的容器，不覆盖你模板里原本的提示（入金不足等）
  let box = panel.querySelector(".js-etc-smart-hints");
  if (!box) {
    box = document.createElement("div");
    box.className = "js-etc-smart-hints mt-1";
    panel.appendChild(box);
  }
  box.innerHTML = "";

  const toIntSafe = (v, def = 0) => {
    const n = parseInt(String(v || "").replace(/,/g, ""), 10);
    return Number.isFinite(n) ? n : def;
  };

  // ===== 读取当前 ETC 聚合结果 =====
  const etcDriverTotal = toIntSafe(
    document.getElementById("etc-driver-total")?.textContent,
    0
  );                            // 全部“ドライバー立替”ETC 合计（乗車+空車）

  const actualRefund = toIntSafe(
    document.getElementById("actual_etc_company_to_driver_view")?.textContent,
    0
  );                            // 会社→運転手 返還ETC 合计（乘车ETC中，司机垫付且公司侧结算）

  const driverNetCost = toIntSafe(
    document.getElementById("etc-driver-cost")?.textContent,
    0
  );                            // 净额：实际“司机負担ETC（工资扣除予定）”

  const etcShortage = toIntSafe(
    document.querySelector("input[name='etc_shortage']")?.value,
    0
  );                            // ETC不足（应收 - 实收）

  // 小工具：生成一条提示
  const makeAlert = (type, icon, html) => {
    const div = document.createElement("div");
    div.className = `alert alert-${type} py-1 px-2 small mb-1`;
    div.innerHTML = `${icon} ${html}`;
    box.appendChild(div);
  };

  // ===== 1) 有司机立替 ETC 吗？ =====
  if (etcDriverTotal > 0) {
    if (driverNetCost <= 0 && actualRefund > 0) {
      // B 类：司机垫付，但公司完全返还 → 不扣工资
      makeAlert(
        "success",
        "✔️",
        `本日存在 <strong>${etcDriverTotal.toLocaleString()}円</strong> 的「司机垫付 ETC」，` +
          `但已由会社侧结算返还（<strong>对照表：B 类</strong>）。<br>` +
          `这些金额不会从工资中扣除。`
      );
    } else if (driverNetCost > 0) {
      // G 类等：司机真正自费部分 → 扣工资
      makeAlert(
        "danger",
        "⚠️",
        `本日存在 <strong>${driverNetCost.toLocaleString()}円</strong> 的「司机負担ETC」，` +
          `将作为工资扣除对象（<strong>对照表：G 类 等</strong>）。`
      );
      if (actualRefund > 0) {
        makeAlert(
          "info",
          "ℹ️",
          `其中有 <strong>${actualRefund.toLocaleString()}円</strong> 属于「司机垫付后由会社返还」部分，` +
            `系统已自动从工资扣除金额中排除。`
        );
      }
    }
  }

  // ===== 2) 有 ETC 不足吗？（应收合计 - 实收） =====
  if (etcShortage > 0) {
    makeAlert(
      "warning",
      "🚧",
      `现在存在 <strong>${etcShortage.toLocaleString()}円</strong> 的「ETC不足」（应收合计 − 实收）。<br>` +
        `这部分不会从司机工资中扣除，但会计入「未收ETC」统计，请根据票据确认是否为 <strong>A/C 类</strong> 情形或需要补收。`
    );
  }
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

// ====== 行号刷新（只更新显示，不改 name/index） ======
function updateRowNumbersAndIndexes() {
  const table = document.querySelector('table.report-table');
  if (!table) return;

  // 只拿真正的数据 tbody，排除模板
  const tbody = table.querySelector('tbody:not(#empty-form-template)');
  if (!tbody) return;

  // 只用于【显示行号】，不改任何 name/id
  const visibleRows = $all("tr.report-item-row", tbody).filter(
    r => r.style.display !== "none"
  );

  visibleRows.forEach((row, i) => {
    const numCell = row.querySelector(".row-number");
    if (numCell) {
      numCell.textContent = String(i + 1);  // 行号从 1 开始
    }
  });

  // ⚠️ 不再修改 TOTAL_FORMS，不再重写 items-0-xxx 之类的字段
}

function updateSameTimeGrouping() {
  const table = document.querySelector('table.report-table');
  if (!table) return;

  const tbody = table.querySelector('tbody:not(#empty-form-template)');
  if (!tbody) return;

  const rows = $all("tr.report-item-row", tbody).filter(r => r.style.display !== "none");
  const groups = Object.create(null);

  rows.forEach(row => {
    const timeInput = row.querySelector("input[name$='-ride_time']") || row.querySelector(".time-input");
    const t = (timeInput ? String(timeInput.value).trim() : "");
    const key = t || "__EMPTY__";
    (groups[key] ||= []).push(row);
  });

  // 清理旧状态
  Object.values(groups).forEach(arr => {
    arr.forEach(row => {
      row.classList.remove("same-time-child");
      const timeInput = row.querySelector("input[name$='-ride_time']") || row.querySelector(".time-input");
      const cell = timeInput?.closest("td");
      if (!cell) return;
      const pref = cell.querySelector(".same-time-prefix");
      if (pref) pref.remove();
    });
  });

  // 添加同一时间的缩进箭头
  Object.entries(groups).forEach(([key, arr]) => {
    if (key === "__EMPTY__" || arr.length <= 1) return;
    arr.forEach((row, idx) => {
      if (idx === 0) return;  // 第一行正常显示
      row.classList.add("same-time-child");
      const timeInput = row.querySelector("input[name$='-ride_time']") || row.querySelector(".time-input");
      const cell = timeInput?.closest("td");
      if (!cell) return;
      const span = document.createElement("span");
      span.className = "same-time-prefix";
      span.textContent = "↳ ";
      cell.insertBefore(span, timeInput);
    });
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

  

  /* ===== [PATCH ADVANCE UI BIND BEGIN] 支払方法変更で立替UIを即時反映 ===== */
  if (methodSelect) {
    methodSelect.addEventListener("change", () => {
      // ★ 立替(advance) のUI保護（隐藏メータ/禁用ETC/关闭貸切 等）
      if (typeof toggleAdvanceUI === "function") {
        toggleAdvanceUI(row);
      }
      updateTotals();
      evaluateEmptyEtcDetailVisibility();
    });

    // 初次渲染也跑一次（避免页面加载时 advance 行没被禁用）
    if (typeof toggleAdvanceUI === "function") {
      toggleAdvanceUI(row);
    }
  }
  /* ===== [PATCH ADVANCE UI BIND END] ===== */

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

  // === [PATCH C3] 行级 ETC 智能提示：怀疑“空車ETC 立替者”选错时给出提醒 ===
  (function attachEtcSmartSuggestion(){
    const rideEtcInput   = row.querySelector('.etc-riding-input');
    const emptyEtcInput  = row.querySelector('.etc-empty-input');
    const rideChargeSel  = row.querySelector('.etc-riding-charge-select');
    const emptyChargeSel = row.querySelector('.etc-empty-charge-select');
    const paySel         = row.querySelector("select[name$='-payment_method']");
    const noteCell       = row.querySelector('.note-cell');

    if (!rideEtcInput || !emptyEtcInput || !rideChargeSel || !emptyChargeSel || !paySel || !noteCell) {
      return;
    }

    // 提示容器：塞在备注列最下面
    let hintBox = noteCell.querySelector('.js-etc-row-smart-hint');
    if (!hintBox) {
      hintBox = document.createElement('div');
      hintBox.className = 'js-etc-row-smart-hint mt-1 small';
      noteCell.appendChild(hintBox);
    }

    const COMPANY_SIDE = new Set(['uber','didi','go','credit','kyokushin','omron','kyotoshi','qr']);

    function normInt(el){
      return toInt(el && el.value, 0);
    }

    function normPay(v){
      return resolveJsPaymentMethod(v || '');
    }

    function recompute(){
      hintBox.innerHTML = '';
      hintBox.className = 'js-etc-row-smart-hint mt-1 small';

      const rideEtc   = normInt(rideEtcInput);
      const emptyEtc  = normInt(emptyEtcInput);
      const rideCh    = (rideChargeSel.value  || 'company').trim();
      const emptyCh   = (emptyChargeSel.value || 'company').trim();
      const pay       = normPay(paySel.value);

      // 全局“空車ETC カード”“回程費”信息
      const emptyCard   = (document.getElementById('id_etc_empty_card')?.value || 'company').trim();
      const returnMeth  = (document.getElementById('id_etc_return_fee_method')?.value || 'none').trim();
      const returnClaim = toInt(document.getElementById('id_etc_return_fee_claimed')?.value, 0);

      // 条件：当前行类似你那种「乘车司机卡 + 有空车ETC」，但空车ETC 却标成会社
      const condRideDriverCompanySide =
        rideEtc > 0 &&
        rideCh === 'driver' &&
        COMPANY_SIDE.has(pay);

      const condEmptyExistsCompany =
        emptyEtc > 0 &&
        emptyCh === 'company';

      // 全局提示：空車ETC カード=自己カード，且回程费有金额/有方式
      const condReturnExists =
        emptyCard === 'own' &&
        returnClaim > 0 &&
        (returnMeth === 'cash_to_driver' || returnMeth === 'app_ticket');

      if (condRideDriverCompanySide && condEmptyExistsCompany && condReturnExists) {
        // 组合起来极像“其实空车也是自己卡，但司机勾成了会社”
        hintBox.classList.add('text-danger'); // 字体红一点
        hintBox.innerHTML = (
          '⚠️ この行は <strong>乘車ETC=ドライバー(自己カード)</strong> かつ ' +
          '<strong>空車ETC も入力済み</strong> ですが、立替者が <strong>会社</strong> のままです。<br>' +
          '実際に回程でも自己ETCカードを使った場合は、' +
          '空車ETC 立替者を <strong>「ドライバー（自費・返還なし）」</strong> に変更してください。<br>' +
          'そうするとシステムが「回程費でカバーされるETC」として正しく判断し、給与控除に入れません。'
        );
      } else {
        // 无风险时不显示，保持空白
        hintBox.textContent = '';
      }
    }

    // 绑定事件：只要本行 ETC / 支付方式 / 立替者 / 全局回程参数发生变化，就重新判断
    ['input','change'].forEach(ev => {
      rideEtcInput.addEventListener(ev, recompute);
      emptyEtcInput.addEventListener(ev, recompute);
      rideChargeSel.addEventListener(ev, recompute);
      emptyChargeSel.addEventListener(ev, recompute);
      if (paySel) paySel.addEventListener(ev, recompute);
    });

    ['#id_etc_empty_card','#id_etc_return_fee_method','#id_etc_return_fee_claimed'].forEach(sel => {
      const el = document.querySelector(sel);
      if (!el) return;
      ['input','change'].forEach(ev => el.addEventListener(ev, recompute));
    });

    // 初次渲染
    recompute();
  })();
  // === [PATCH C3 END] ===

  // === [PATCH ETC-HINT ROW BEGIN] 行级「ETC 未入力」引导提示 ===
  attachEtcNeedInputHint(row);
  // === [PATCH ETC-HINT ROW END] ===

  // 行级ETC 三字段（乗車ETC・空車ETC・各自の立替者）
  $all(
    ".etc-riding-input, .etc-empty-input, " +
    ".etc-riding-charge-select, .etc-empty-charge-select",
    row
  ).forEach(el => {
    el.addEventListener("input", () => {
      updateTotals();
      evaluateEmptyEtcDetailVisibility();
    });
    el.addEventListener("change", () => {
      updateTotals();
      evaluateEmptyEtcDetailVisibility();
    });
  });

  // === [PATCH ETC-CHARGE-HINT BEGIN] ETC 金额填写时的立替者引导提示 ===
  attachEtcChargeGuidance(row);
  // === [PATCH ETC-CHARGE-HINT END] ===
}

// === [PATCH ADVANCE UI FUNC BEGIN] 立替 UI 保护与联动 ===
function toggleAdvanceUI(row) {
  if (!row) return;

  const paymentSelect =
    row.querySelector("select[name$='-payment_method']") ||
    row.querySelector(".payment-method-select");

  const meterInput =
    row.querySelector("input[name$='-meter_fee']") ||
    row.querySelector(".meter-fee-input");

  const advanceInput =
    row.querySelector("input[name$='-advance_amount']") ||
    row.querySelector(".advance-amount-input");

  // ETC
  const etcRide = row.querySelector("input[name$='-etc_riding']");
  const etcEmpty = row.querySelector("input[name$='-etc_empty']");
  const etcRideSel = row.querySelector(".etc-riding-charge-select");
  const etcEmptySel = row.querySelector(".etc-empty-charge-select");

  // 貸切
  const isCharter = row.querySelector("input[name$='-is_charter']");
  const charterAmount = row.querySelector(".charter-amount-input");
  const charterPay = row.querySelector(".charter-payment-method-select");

  // 立替灰字提示（模板里 advance-mini-hint）
  const advanceHint = row.querySelector(".advance-mini-hint");

  const isAdvance = paymentSelect && paymentSelect.value === "advance";

  if (isAdvance) {
    if (advanceInput) advanceInput.classList.remove("d-none");
    if (meterInput) {
      meterInput.classList.add("d-none");
      meterInput.value = 0;
    }

    [etcRide, etcEmpty].forEach(inp => {
      if (!inp) return;
      inp.value = 0;
      inp.disabled = true;
      inp.classList.remove("etc-need-warning");
    });
    [etcRideSel, etcEmptySel].forEach(sel => {
      if (!sel) return;
      sel.value = "company";
      sel.disabled = true;
    });

    if (isCharter) {
      isCharter.checked = false;
      isCharter.disabled = true;
    }
    if (charterAmount) {
      charterAmount.value = 0;
      charterAmount.disabled = true;
    }
    if (charterPay) {
      charterPay.value = "";
      charterPay.disabled = true;
    }

    if (advanceHint) advanceHint.classList.remove("d-none");

  } else {
    if (advanceInput) {
      advanceInput.classList.add("d-none");
      advanceInput.value = 0;
    }
    if (meterInput) {
      meterInput.classList.remove("d-none");
      meterInput.disabled = false;
    }

    [etcRide, etcEmpty].forEach(inp => {
      if (!inp) return;
      inp.disabled = false;
    });
    [etcRideSel, etcEmptySel].forEach(sel => {
      if (!sel) return;
      sel.disabled = false;
    });

    if (isCharter) isCharter.disabled = false;
    if (charterAmount) charterAmount.disabled = false;
    if (charterPay) charterPay.disabled = false;
    if (advanceHint) advanceHint.classList.add("d-none");
  }
}
// === [PATCH ADVANCE UI FUNC END] ===


// === [PATCH ETC-CHARGE-HINT FUNC BEGIN] ===
function attachEtcChargeGuidance(row) {
  if (!row) return;

  const pairs = [
    {
      amount: row.querySelector(".etc-riding-input"),
      charge: row.querySelector(".etc-riding-charge-select"),
    },
    {
      amount: row.querySelector(".etc-empty-input"),
      charge: row.querySelector(".etc-empty-charge-select"),
    }
  ];

  pairs.forEach(({ amount, charge }) => {
    if (!amount || !charge) return;

    // 在 select 下方放一个提示容器
    let hint = charge.parentElement.querySelector(".etc-charge-guidance");
    if (!hint) {
      hint = document.createElement("div");
      hint.className = "etc-charge-guidance text-muted";
      hint.style.fontSize = "11px";
      hint.style.marginTop = "2px";
      charge.parentElement.appendChild(hint);
    }

    function recompute() {
      const v = toInt(amount.value, 0);
      if (v <= 0) {
        hint.textContent = "";
        return;
      }

      switch (charge.value) {
        case "driver":
          hint.textContent =
            "自己のETCカードで支払った場合はこちらが正しいです（後で返還対象）";
          break;
        case "company":
          hint.textContent =
            "会社ETCカードを使用した場合はこちらが正しいです";
          break;
        case "customer":
          hint.textContent =
            "高速料金が既にお客様精算に含まれている場合のみ選択してください";
          break;
        default:
          hint.textContent =
            "ETC料金を誰が立替したかに応じて選択してください";
      }
    }

    amount.addEventListener("input", recompute);
    charge.addEventListener("change", recompute);
    recompute();
  });
}
// === [PATCH ETC-CHARGE-HINT FUNC END] ===


// ====== 找到“明细行 items formset”的 TOTAL_FORMS 输入框（严格版） ======
function findItemsTotalInput() {
  // 只从“真实数据 tbody（排除模板 tbody）”里的行去找样本字段
  const candidates = document.querySelectorAll(
    'table.report-table tbody:not(#empty-form-template) tr.report-item-row input[name*="-ride_time"], ' +
    'table.report-table tbody:not(#empty-form-template) tr.report-item-row input[name*="-meter_fee"]'
  );

  let prefix = null;

  for (const sample of candidates) {
    if (!sample.name) continue;
    // 例如 items-3-ride_time 这样的
    const m = sample.name.match(/^(.+)-\d+-[^-]+$/);
    if (m && m[1]) {
      prefix = m[1];  // -> "items"
      break;
    }
  }

  // 如果上面成功解析出 prefix，就精确锁定 `${prefix}-TOTAL_FORMS`
  if (prefix) {
    const name = prefix + "-TOTAL_FORMS";
    const exact = document.querySelector(`input[name="${name}"]`);
    if (exact) return exact;
  }

  // 兜底：再试一次常见的名字
  const fallback =
    document.querySelector('input[name="items-TOTAL_FORMS"]') ||
    document.querySelector('input[name$="-TOTAL_FORMS"]');

  return fallback;
}

// ====== 模板克隆/插入 ======
function cloneRowFromTemplate() {
  const tpl = document.querySelector('#empty-form-template');

  // ✅ 只针对“明细 items formset”的 TOTAL_FORMS
  const totalInput = findItemsTotalInput();
  if (!tpl || !totalInput) return null;

  // 当前管理表单里的总数（例如 10 行）
  const count = parseInt(totalInput.value || '0', 10) || 0;

  // 告诉 Django：总表单数 +1（例如从 10 变成 11）
  totalInput.value = String(count + 1);   // ✅ 用 totalInput

  // 用 count 作为新行的 index
  const tmp = document.createElement('tbody');
  tmp.innerHTML = tpl.innerHTML
    .replace(/__prefix__/g, count)
    .replace(/__num__/g, count + 1);
  const tr = tmp.querySelector('tr');
  if (!tr) return null;

  // === [M1 BEGIN] 保险：给新行的“支付”下拉复制一份选项 ===
  try {
    const firstPay = document.querySelector(
      'table.report-table tbody:not(#empty-form-template) select[name$="-payment_method"]'
    );
    const newPay = tr.querySelector('select[name$="-payment_method"]');
    if (firstPay && newPay) {
      // 如果新行的 select 没有选项，或者只有一个 “------”，就直接复制第一行的 innerHTML
      if (!newPay.options.length || newPay.options.length === 1) {
        newPay.innerHTML = firstPay.innerHTML;
      }
    }
  } catch (e) {
    console.warn('cloneRowFromTemplate: payment_method option copy failed:', e);
  }
  // === [M1 END] ===

  tr.classList.remove('d-none', 'hidden', 'invisible', 'template-row');
  tr.style.removeProperty('display');
  tr.removeAttribute('aria-hidden');
  tr.querySelectorAll('input,select,textarea,button').forEach(el => {
    el.disabled = false;
    el.removeAttribute('disabled');
  });

  // 这里 **不要再写第二个 total.value = ...**，这一行可以删掉
  // total.value = String(count + 1);

  // === PATCH: 确保新行的“支付方式”下拉框有和现有行一样的选项 ===
  // 用统一工具补全新行里的“支付方式”选项（只填空的，不改现有值）
  try {
    fillPaymentMethodOptions(tr);
  } catch (e) {
    console.warn('cloneRowFromTemplate: fillPaymentMethodOptions failed', e);
  }

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

// === [PATCH R1 BEGIN] 在指定行后插入一行（统一给“下に挿入”等入口使用） ===
function addRowAfterRow(anchorRow) {
  const table = document.querySelector('table.report-table');
  if (!table) return false;

  const dataTb = table.querySelector('tbody:not(#empty-form-template)');
  if (!dataTb) return false;

  const tr = cloneRowFromTemplate();
  if (!tr) return false;

  // 决定插入位置：默认就在 anchorRow 后面；如果拿不到，就插在最后一行后面
  let insertAfter = null;
  if (anchorRow && anchorRow.parentNode === dataTb) {
    insertAfter = anchorRow;
  } else {
    const last = dataTb.querySelector('tr.report-item-row:last-child');
    if (last) insertAfter = last;
  }

  if (insertAfter) {
    dataTb.insertBefore(tr, insertAfter.nextSibling);
  } else {
    dataTb.appendChild(tr);
  }

  // 只在这里绑定一次事件 + 更新各种联动
  bindRowEvents(tr);
  updateRowNumbersAndIndexes();
  updateSameTimeGrouping();
  updateTotals();
  evaluateEmptyEtcDetailVisibility();
  syncEtcColVisibility();

  // 让新行尽量滚到中间，方便在手机上看
  try {
    tr.scrollIntoView({ behavior: 'smooth', block: 'center' });
  } catch (e) {}

  const focusEl = tr.querySelector('.time-input') || tr.querySelector('input,select');
  if (focusEl && typeof focusEl.focus === 'function') {
    focusEl.focus();
  }

  return true;
}
// === [PATCH R1 END] ===

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

// ====== 只给“支付方式”下拉填充缺失的选项（不会改已有值） ======
function fillPaymentMethodOptions(root) {
  const scope = root || document;

  // 找到所有支付方式 select（老的 name/class 都兼容）
  const selects = scope.querySelectorAll(
    "select[name$='-payment_method'], .payment-method-select"
  );
  if (!selects.length) return;

  // ① 先尝试从页面上“已有选项的 select”里找一份模板
  let masterHTML = null;
  for (const sel of selects) {
    if (sel.options && sel.options.length > 1) {
      masterHTML = sel.innerHTML;
      break;
    }
  }

  // ② 页面上完全没有模板时，用一份兜底选项（只填到空 select，不会覆盖已有的）
  if (!masterHTML) {
    const defs = [
      ["", "------"],
      ["cash", "現金"],
      ["uber", "Uber"],
      ["didi", "DiDi"],
      ["go", "GO"],
      ["credit_card", "クレジットカード"],
      ["kyokushin", "京交信"],
      ["omron", "オムロン"],
      ["kyotoshi", "京都市他"],
      ["qr", "バーコード(PayPay等)"],
      ["uber_reservation", "Uber予約"],
      ["uber_tip", "Uberチップ"],
      ["uber_promotion", "Uberプロモーション"],
    ];
    masterHTML = defs
      .map(([v, t]) => `<option value="${v}">${t}</option>`)
      .join("");
  }

  // ③ 只处理“几乎没有选项”的 select，不动那些已经有多个选项的
  selects.forEach((sel) => {
    if (!sel.options || sel.options.length <= 1) {
      const prevValue = sel.value || "";
      sel.innerHTML = masterHTML;
      if (prevValue) {
        sel.value = prevValue; // 理论上是空，这里只是稳一下
      }
    }
  });
}


// ===== ETC 立替者归一化（ドライバー / 会社 / お客様） =====
function normalizeEtcCharge(raw) {
  const v = String(raw || "").trim();
  if (!v) return "company";

  // 先看英文值
  if (v === "driver")   return "driver";
  if (v === "company")  return "company";
  if (v === "customer") return "customer";

  // 再看日文文案
  if (v.includes("ドライバー")) return "driver";
  if (v.includes("お客様"))     return "customer";
  if (v.includes("会社"))       return "company";

  // 兜底：当成公司负担
  return "company";
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

// === [PATCH ETC-HINT FUNCTIONS BEGIN] 行级「ETC 未入力」引导逻辑 ===

// 备注中出现这些关键词时，认为“很可能有高速/ETC”
const ETC_HINT_KEYWORDS = [
  "高速",
  "有料道路",
  "首都高",
  "阪神高速",
  "名神",
  "京滋バイパス",
  "第二京阪",
  "高速代",
  "ＥＴＣ",
  "ETC"
];

// 这些支付方式下，经常附带高速（用 resolveJsPaymentMethod 归一化后的值）
const ETC_HINT_SUSPECT_PAYS = new Set([
  "uber",
  "didi",
  "go",
  "credit",
  "kyokushin",
  "omron",
  "kyotoshi",
  "qr"
]);

/**
 * 在单行内挂 ETC 提示：
 * - 如果乘车/空车 ETC 都是 0
 * - 且“备注命中关键词”或“支付方式属于容易有高速类型”
 * → 在备注列下方显示一条“请确认/填写高速ETC”的提示，并给 ETC 输入框加醒目标记。
 */
function attachEtcNeedInputHint(row) {
  if (!row) return;

  const rideEtcInput =
    row.querySelector(".etc-riding-input") ||
    row.querySelector("input[name$='-etc_riding']");
  const emptyEtcInput =
    row.querySelector(".etc-empty-input") ||
    row.querySelector("input[name$='-etc_empty']");

  // 行中没有 ETC 输入就不处理
  if (!rideEtcInput && !emptyEtcInput) return;

  const paySel =
    row.querySelector("select[name$='-payment_method']") ||
    row.querySelector(".payment-method-select");

  // 备注输入：优先找 textarea[name$='-note']，退一步找 .note-input
  const noteInput =
    row.querySelector("textarea[name$='-note']") ||
    row.querySelector(".note-input");

  // 提示容器塞在备注列底部；如果拿不到 .note-cell，就退回整行末尾
  let noteCell = row.querySelector(".note-cell");
  if (!noteCell) {
    noteCell = (noteInput && noteInput.closest("td")) || row;
  }

  let hintBox = noteCell.querySelector(".js-etc-need-input-hint");
  if (!hintBox) {
    hintBox = document.createElement("div");
    hintBox.className = "js-etc-need-input-hint mt-1 small";
    noteCell.appendChild(hintBox);
  }

  function recomputeEtcNeedHint() {
    const rideEtc = toInt(rideEtcInput && rideEtcInput.value, 0);
    const emptyEtc = toInt(emptyEtcInput && emptyEtcInput.value, 0);
    const etcSum = rideEtc + emptyEtc;

    const noteText = noteInput && noteInput.value ? String(noteInput.value) : "";
    const payRaw = paySel && paySel.value ? paySel.value : "";
    const payNorm = resolveJsPaymentMethod(payRaw || "");

    // === [PATCH ETC-AMOUNT-THRESHOLD BEGIN] 新增金额门槛：未满 10,000円 不提示 ===

    // 取得金额（你的字段应该是 fare 或 meter_fee，根据模板自行确认 name）
    // === [PATCH ETC-AMOUNT SOURCE FIX BEGIN] ===
    // 料金：只从本行的 meter_fee 输入框读取
    const fareInput = row.querySelector('.meter-fee-input');
    const fare = toInt(fareInput ? fareInput.value : 0, 0);
    // === [PATCH ETC-AMOUNT SOURCE FIX END] ===

    // 低于 10000 → 直接不提示（清除现有提示 + 退出）
    if (fare < 10000) {
        clearEtcNeedHint(hintBox, rideEtcInput, emptyEtcInput);
        return;
    }

    // === [PATCH ETC-AMOUNT-THRESHOLD END] ===

    // 已经填了任意一个 ETC，就不再提示
    if (etcSum > 0) {
      clearEtcNeedHint(hintBox, rideEtcInput, emptyEtcInput);
      return;
    }

    const hasKeyword = ETC_HINT_KEYWORDS.some((kw) =>
      noteText.indexOf(kw) !== -1
    );
    const isSuspectPay = payNorm && ETC_HINT_SUSPECT_PAYS.has(payNorm);

    // 既没有关键词、支付方式也不敏感 → 不提示
    if (!hasKeyword && !isSuspectPay) {
      clearEtcNeedHint(hintBox, rideEtcInput, emptyEtcInput);
      return;
    }

    // === [PATCH ETC-HINT UI BEGIN] 行级 ETC 提示改为小标签 + hover 详细说明 ===
    hintBox.className = "js-etc-need-input-hint etc-hint-wrapper mt-1";
    hintBox.innerHTML = `
      <span class="etc-hint-badge">⚠ 高速？</span>
      <div class="etc-hint-detail">
        高速・ETC を利用した可能性があります。<br>
        この行の乗車/空車 ETC 金額が未入力です。<br>
        運転手が立替している場合は ETC 金額を入力してください。
      </div>
    `;
    // === [PATCH ETC-HINT UI END] ===

    [rideEtcInput, emptyEtcInput].forEach((inp) => {
      if (inp) inp.classList.add("etc-need-warning");
    });
  }

  // 绑定事件：备注 / 支払方法 / ETC 金额 任何变化都重新判断一次
  if (noteInput) {
    noteInput.addEventListener("input", recomputeEtcNeedHint);
  }
  if (paySel) {
    paySel.addEventListener("change", recomputeEtcNeedHint);
  }
  if (rideEtcInput) {
    rideEtcInput.addEventListener("input", recomputeEtcNeedHint);
    rideEtcInput.addEventListener("change", recomputeEtcNeedHint);
  }
  if (emptyEtcInput) {
    emptyEtcInput.addEventListener("input", recomputeEtcNeedHint);
    emptyEtcInput.addEventListener("change", recomputeEtcNeedHint);
  }

  // 初始跑一遍
  recomputeEtcNeedHint();
}

/**
 * 清除单行的 ETC 提示与高亮
 */
function clearEtcNeedHint(hintBox, rideEtcInput, emptyEtcInput) {
  if (hintBox) {
    hintBox.textContent = "";
    hintBox.className = "js-etc-need-input-hint mt-1 small";
  }
  [rideEtcInput, emptyEtcInput].forEach((inp) => {
    if (inp) inp.classList.remove("etc-need-warning");
  });
}

// === [PATCH ETC-HINT FUNCTIONS END] ===


// ====== 合计（旧逻辑 + 行级ETC聚合 + 過不足含「実際ETC 会社→運転手」） ======
// ===== 行別ETC 明細テーブルを再構築 =====
function rebuildEtcDetailTable() {
  const table = document.querySelector("table.report-table");
  const tbody = document.getElementById("etc-detail-body");
  if (!table || !tbody) return;

  tbody.innerHTML = "";

  $all("tr.report-item-row", table).forEach(row => {
    const delFlag = row.querySelector("input[name$='-DELETE']");
    if ((delFlag && delFlag.checked) || row.style.display === "none") return;

    const isPending = (row.querySelector("input[name$='-is_pending']") || row.querySelector(".pending-checkbox"))?.checked;
    if (isPending) return;

    const rideEtcInput =
      row.querySelector(".etc-riding-input") ||
      row.querySelector("input[name$='-etc_riding']");
    const emptyEtcInput =
      row.querySelector(".etc-empty-input") ||
      row.querySelector("input[name$='-etc_empty']");

    const rideEtc  = toInt(rideEtcInput?.value, 0);
    const emptyEtc = toInt(emptyEtcInput?.value, 0);
    if (!rideEtc && !emptyEtc) return;  // 本行没有 ETC 就跳过

    // 时间：乗車時間 or .time-input
    const timeInput =
      row.querySelector("input[name$='-ride_time']") ||
      row.querySelector(".time-input");
    const timeVal = timeInput ? (timeInput.value || "") : "";

    // 支付方式显示名
    const paySel = row.querySelector("select[name$='-payment_method']") || row.querySelector(".payment-method-select");
    let payText = "";
    if (paySel) {
      const opt = paySel.options[ paySel.selectedIndex ];
      payText = opt ? (opt.text || opt.value) : (paySel.value || "");
    }

    const tr = document.createElement("tr");

    const tdTime   = document.createElement("td");
    const tdPay    = document.createElement("td");
    const tdRide   = document.createElement("td");
    const tdEmpty  = document.createElement("td");
    const tdSum    = document.createElement("td");

    tdTime.className  = "text-center";
    tdRide.className  = "text-end";
    tdEmpty.className = "text-end";
    tdSum.className   = "text-end fw-bold";

    tdTime.textContent  = timeVal;
    tdPay.textContent   = payText;
    tdRide.textContent  = rideEtc  ? rideEtc.toLocaleString()  : "";
    tdEmpty.textContent = emptyEtc ? emptyEtc.toLocaleString() : "";
    tdSum.textContent   = (rideEtc + emptyEtc).toLocaleString();

    tr.appendChild(tdTime);
    tr.appendChild(tdPay);
    tr.appendChild(tdRide);
    tr.appendChild(tdEmpty);
    tr.appendChild(tdSum);

    tbody.appendChild(tr);
  });
}


function renderPayMethodCards(totalMap, etcByPay) {
  // 1) 写入売上（ETC除く）和 高速・ETC
  Object.keys(etcByPay).forEach((k) => {
    const etc = etcByPay[k] || 0;
    const total = totalMap[k] || 0;

    idText(`${k}-sales-total`, total - etc);
    idText(`${k}-etc-total`, etc);

    // 2) 高速・ETC が 0 の場合は、売上＋ETC ブロックを隠す
    const block = document.getElementById(`${k}-sales-etc-block`);
    if (!block) return;
    block.style.display = (etc === 0) ? "none" : "";
  });
}



/* ====== REPLACE FROM HERE: updateTotals() ====== */
function updateTotals() {
  const table = document.querySelector("table.report-table");
  if (!table) return;

  /* ===== [PATCH PAYMETHOD KEYS AUTO-DISCOVER BEGIN] ===== */
  function collectPayMethodKeysFromDom() {
    const keys = new Set();
    document.querySelectorAll('[id$="-sales-etc-block"]').forEach(el => {
      const id = el.id || "";
      const k = id.replace(/-sales-etc-block$/, "").trim();
      if (k) keys.add(k);
    });
    return Array.from(keys);
  }

  const FALLBACK_PAY_KEYS = [
    "cash","uber","didi","go","credit","kyokushin","omron","kyotoshi","qr"
  ];

  const payKeys = Array.from(new Set([
    ...collectPayMethodKeysFromDom(),
    ...FALLBACK_PAY_KEYS,
  ]));

  const totalMap = Object.fromEntries(payKeys.map(k => [k, 0]));
  /* ===== [PATCH PAYMETHOD KEYS AUTO-DISCOVER END] ===== */

  let meterOnlyTotal = 0;          // メータ売上だけの合計
  let advanceTotal = 0;            // ★立替合計
  let charterCashTotal = 0;        // 貸切現金
  let charterUncollectedTotal = 0; // 貸切未収

  let uberReservationTotal = 0, uberReservationCount = 0;
  let uberTipTotal = 0, uberTipCount = 0;
  let uberPromotionTotal = 0, uberPromotionCount = 0;
  let specialUberSum = 0;

  // ---- 行レベル ETC 集計 ----
  let rideEtcSum = 0;
  let emptyEtcSum = 0;
  let etcCompany = 0;
  let etcDriver = 0;
  let etcCustomer = 0;
  let actualEtcCompanyToDriver = 0;
  let driverEmptyEtc = 0;

  let etcSalesTotal = 0;

  const etcByPay = Object.fromEntries(payKeys.map(k => [k, 0]));

  const COMPANY_SIDE = new Set([
    "uber","didi","go","credit","kyokushin","omron","kyotoshi","qr",
  ]);

  const rows = table.querySelectorAll("tr.report-item-row");

  rows.forEach((row) => {
    // 削除行・待入行はスキップ
    const delFlag = row.querySelector("input[name$='-DELETE']");
    if (delFlag && delFlag.checked) return;

    const pendingCb =
      row.querySelector("input[name$='-is_pending']") ||
      row.querySelector(".pending-checkbox");
    if (pendingCb && pendingCb.checked) return;

    // 支払方法（生値）
    const paymentSelect =
      row.querySelector("select[name$='-payment_method']") ||
      row.querySelector(".payment-method-select");
    const paymentRaw = paymentSelect ? (paymentSelect.value || "") : "";

    // ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
    // ✅【ここが最重要】立替行判定
    // forEach 内で「その行を無視する」= continue ではなく return
    // ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲
    const payText =
      paymentSelect && paymentSelect.options && paymentSelect.selectedIndex >= 0
        ? (paymentSelect.options[paymentSelect.selectedIndex]?.text || "")
        : "";

    const isAdvance =
      String(paymentRaw || "").trim() === "advance" ||
      String(payText || "").includes("立替");

    if (isAdvance) {
      const advInput =
        row.querySelector("input[name$='-advance_amount']") ||
        row.querySelector(".advance-amount-input");
      const adv = toInt(advInput?.value, 0);
      advanceTotal += adv;

      // ✅ 立替行は売上/ETC集計から除外（この行だけスキップ）
      return;  // ← これが正解。continue は禁止（forEachでSyntaxError）
    }

    // 貸切フラグ
    const charterCb = row.querySelector("input[name$='-is_charter']");
    const isCharter = !!(charterCb && charterCb.checked);

    // メータ料金
    const meterInput =
      row.querySelector(".meter-fee-input") ||
      row.querySelector("input[name$='-meter_fee']");
    const fee = toInt(meterInput?.value, 0);

    // 貸切情報
    const charterAmountInput = row.querySelector(".charter-amount-input");
    const charterAmount = toInt(charterAmountInput?.value, 0);
    const charterPaySelect = row.querySelector(".charter-payment-method-select");
    const charterPayMethod = charterPaySelect ? (charterPaySelect.value || "") : "";

    // ETC 値の取得
    const rideEtcInput =
      row.querySelector(".etc-riding-input") ||
      row.querySelector("input[name$='-etc_riding']");
    const emptyEtcInput =
      row.querySelector(".etc-empty-input") ||
      row.querySelector("input[name$='-etc_empty']");
    const rideEtc  = toInt(rideEtcInput?.value, 0);
    const emptyEtc = toInt(emptyEtcInput?.value, 0);

    const rideChargeSelect =
      row.querySelector(".etc-riding-charge-select") ||
      row.querySelector("select[name$='-etc_riding_charge_type']");
    const emptyChargeSelect =
      row.querySelector(".etc-empty-charge-select") ||
      row.querySelector("select[name$='-etc_empty_charge_type']");

    const legacyChargeInput = row.querySelector("input[name$='-etc_charge_type']");
    const legacyChargeRaw   = (legacyChargeInput?.value || "").trim();

    const ALLOWED_CHARGE = new Set(["company", "driver", "customer"]);

    let rideChargeRaw  = (rideChargeSelect?.value || "").trim();
    let emptyChargeRaw = (emptyChargeSelect?.value || "").trim();

    let rideCharge = rideChargeRaw;
    if (!rideCharge || !ALLOWED_CHARGE.has(rideCharge)) {
      rideCharge = legacyChargeRaw || "company";
    }

    let emptyCharge = emptyChargeRaw;
    if (!emptyCharge || !ALLOWED_CHARGE.has(emptyCharge)) {
      emptyCharge = emptyChargeRaw || rideCharge || legacyChargeRaw || "company";
    }

    // ETC 三桶累计
    rideEtcSum += rideEtc;
    emptyEtcSum += emptyEtc;

    if (rideEtc > 0) {
      if (rideCharge === "company") etcCompany += rideEtc;
      else if (rideCharge === "driver") etcDriver += rideEtc;
      else if (rideCharge === "customer") etcCustomer += rideEtc;
    }
    if (emptyEtc > 0) {
      if (emptyCharge === "company") etcCompany += emptyEtc;
      else if (emptyCharge === "driver") etcDriver += emptyEtc;
      else if (emptyCharge === "customer") etcCustomer += emptyEtc;
    }
    if (emptyEtc > 0 && emptyCharge === "driver") {
      driverEmptyEtc += emptyEtc;
    }

    // 本行の「売上に乗せる ETC」
    let etcForSalesRow = 0;
    const paidBy = resolveJsPaymentMethod(paymentRaw);

    if (rideEtc > 0) {
      if (rideCharge === "customer") {
        etcForSalesRow += rideEtc;
      } else if (rideCharge === "driver" && COMPANY_SIDE.has(paidBy)) {
        etcForSalesRow += rideEtc;
      }
    }
    if (emptyEtc > 0 && emptyCharge === "customer") {
      etcForSalesRow += emptyEtc;
    }

    etcSalesTotal += etcForSalesRow;

    if (etcForSalesRow > 0) {
      if (Object.prototype.hasOwnProperty.call(etcByPay, paidBy)) {
        etcByPay[paidBy] += etcForSalesRow;
      }
    }

    // 支払方法ごとの売上集計
    if (!isCharter) {
      if (fee > 0) {
        const isUberReservation = paymentRaw === "uber_reservation";
        const isUberTip = paymentRaw === "uber_tip";
        const isUberPromotion = paymentRaw === "uber_promotion";
        const isSpecialUber = isUberReservation || isUberTip || isUberPromotion;

        if (isSpecialUber) {
          specialUberSum += fee;
          if (isUberReservation) { uberReservationTotal += fee; uberReservationCount += 1; }
          else if (isUberTip) { uberTipTotal += fee; uberTipCount += 1; }
          else if (isUberPromotion) { uberPromotionTotal += fee; uberPromotionCount += 1; }
        } else {
          const method = resolveJsPaymentMethod(paymentRaw);
          meterOnlyTotal += fee;

          const rowSales = fee + etcForSalesRow;
          if (Object.prototype.hasOwnProperty.call(totalMap, method)) {
            totalMap[method] += rowSales;
          }
        }
      } else if (etcForSalesRow > 0) {
        const method = resolveJsPaymentMethod(paymentRaw);
        if (Object.prototype.hasOwnProperty.call(totalMap, method)) {
          totalMap[method] += etcForSalesRow;
        }
      }
    } else if (charterAmount > 0) {
      const CASH = ["jpy_cash", "rmb_cash", "self_wechat", "boss_wechat"];
      const UNCOLLECTED = ["to_company", "bank_transfer", ""];
      if (CASH.includes(charterPayMethod)) charterCashTotal += charterAmount;
      else if (UNCOLLECTED.includes(charterPayMethod)) charterUncollectedTotal += charterAmount;
    }
  });

  // ===== M1: 司机负担 & 实际ETC 会社→運転手 =====
  const driverEtcDeductionTotal = driverEmptyEtc;

  actualEtcCompanyToDriver = etcDriver - driverEmptyEtc;
  if (actualEtcCompanyToDriver < 0) actualEtcCompanyToDriver = 0;

  // ====== 1) 売上系の表示 ======
  let etcCollectedPanel = 0;
  (function syncEtcCollectedPanel() {
    const etcInput = document.getElementById("id_etc_collected");
    if (!etcInput) return;

    const panelVal = _yen(etcInput.value || 0);
    if (!panelVal && etcSalesTotal > 0) {
      etcInput.value = String(etcSalesTotal);
      etcCollectedPanel = etcSalesTotal;
    } else {
      etcCollectedPanel = panelVal;
    }

    const breakdownEl = document.getElementById("etc-collected-breakdown");
    if (breakdownEl) {
      breakdownEl.textContent = "行明細より集計：" + etcSalesTotal.toLocaleString() + " 円";
    }
  })();

  const salesTotal =
    meterOnlyTotal +
    specialUberSum +
    charterCashTotal +
    charterUncollectedTotal;

  idText("total_meter_only", meterOnlyTotal);
  idText("total_meter", salesTotal);
  idText("sales-total", salesTotal);

  idText("advance-total", advanceTotal);

  idText("uber-reservation-total", uberReservationTotal);
  idText("uber-reservation-count", uberReservationCount);
  idText("uber-tip-total", uberTipTotal);
  idText("uber-tip-count", uberTipCount);
  idText("uber-promotion-total", uberPromotionTotal);
  idText("uber-promotion-count", uberPromotionCount);

  Object.entries(totalMap).forEach(([k, v]) => idText(`total_${k}`, v));
  renderPayMethodCards(totalMap, etcByPay);

  idText("charter-cash-total", charterCashTotal);
  idText("charter-uncollected-total", charterUncollectedTotal);

  // ====== 2) ETC 概要 ======
  const etcTotalOverall = rideEtcSum + emptyEtcSum;
  idText("etc-total-overall", etcTotalOverall);

  const etcCustomerRecovery = etcCustomer || 0;
  idText("etc-customer-recovery-view", etcCustomerRecovery);

  const etcCompanyToDriver = actualEtcCompanyToDriver || 0;
  idText("actual_etc_company_to_driver_view", etcCompanyToDriver);

  let etcDriverToCompany = etcDriver - etcCompanyToDriver;
  if (etcDriverToCompany < 0) etcDriverToCompany = 0;
  idText("etc-driver-to-company-view", etcDriverToCompany);

  const actualHidden = document.getElementById("actual_etc_company_to_driver");
  if (actualHidden) actualHidden.value = actualEtcCompanyToDriver;

  const emptyInput = document.getElementById("id_etc_uncollected");
  if (emptyInput) {
    const current = toInt(emptyInput.value, 0);
    if (current !== emptyEtcSum) emptyInput.value = String(emptyEtcSum);
  }

  // ====== 3) 入金・過不足 ======
  const deposit = _yen(document.getElementById("deposit-input")?.value || 0);
  const cashNagashi = totalMap.cash || 0;
  const charterCash = charterCashTotal || 0;

  const imbalanceBase = deposit - cashNagashi - charterCash;
  const etcNet = actualEtcCompanyToDriver;

  // ===== [PATCH FUEL EXCLUDE FROM IMBALANCE ONLY BEGIN] =====
  let imbalanceAdjusted = imbalanceBase + etcNet;
  let displayImbalance = imbalanceBase + etcNet;

  const fuelAmount = toInt(
    document.querySelector("input[name='fuel_amount']")?.value,
    0
  );
  const fuelPaidBy =
    document.querySelector("select[name='fuel_paid_by']")?.value || "";

  if (fuelAmount > 0 && fuelPaidBy === "company_cash") {
    // 只修正“显示用的入金差额”，不影响工资计算
    imbalanceAdjusted += fuelAmount;
  }
  // ===== [PATCH FUEL EXCLUDE FROM IMBALANCE ONLY END] =====

  const imbalance = imbalanceBase + etcNet;

  // ====== 給与（最終）=====
  const overShortToDriver = imbalanceBase > 0 ? imbalanceBase : 0;
  const payrollFinal = salesTotal + advanceTotal + etcNet + overShortToDriver;
  idText("payroll-total", payrollFinal);

  (function writePayrollHidden() {
    const setHiddenInt = (id, v) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.value = String(toInt(v, 0));
    };

    setHiddenInt("id_payroll_total", payrollFinal);
    setHiddenInt("id_payroll_bd_sales", salesTotal);
    setHiddenInt("id_payroll_bd_advance", advanceTotal);
    setHiddenInt("id_payroll_bd_etc_refund", etcNet);
    setHiddenInt("id_payroll_bd_over_short_to_driver", overShortToDriver);

    const overShortToCompany = imbalanceBase < 0 ? Math.abs(imbalanceBase) : 0;
    setHiddenInt("id_payroll_bd_over_short_to_company", overShortToCompany);
  })();

  if (typeof window.__refreshPayrollSummary === "function") window.__refreshPayrollSummary();

  idText("payroll-bd-sales", salesTotal);
  idText("payroll-bd-advance", advanceTotal);
  idText("payroll-bd-etc-refund", etcNet);
  idText("payroll-bd-over-short", overShortToDriver);

  const overShortToCompany = imbalanceBase < 0 ? Math.abs(imbalanceBase) : 0;
  idText("payroll-bd-over-short-excl", overShortToCompany);

  const diffEl =
    document.getElementById("difference-output") ||
    document.getElementById("deposit-difference") ||
    document.getElementById("shortage-diff");
  if (diffEl) {
    diffEl.textContent = Number.isFinite(imbalanceAdjusted)
      ? imbalanceAdjusted.toLocaleString()
      : "--";
    diffEl.setAttribute("data-base-over-short", String(imbalanceBase));
    diffEl.setAttribute("data-etc-net", String(etcNet));
  }

  const hiddenDiff = document.getElementById("id_deposit_difference");
  if (hiddenDiff) hiddenDiff.value = imbalanceAdjusted;

  if (typeof evaluateEmptyEtcDetailVisibility === "function") {
    try { evaluateEmptyEtcDetailVisibility(); } catch (e) {}
  }
  if (typeof updateSmartHintPanel === "function") {
    try { updateSmartHintPanel(); } catch (e) {}
  }
  if (typeof rebuildEtcDetailTable === "function") {
    try { rebuildEtcDetailTable(); } catch (e) {}
  }

  // ====== 司机負担ETC（工资扣除予定） ======
  (function syncDriverEtcCost() {
    const driverCostView = document.getElementById("etc-driver-cost");
    const driverCostHidden = document.getElementById("id_etc_driver_cost");
    if (!driverCostView && !driverCostHidden) return;

    let driverCost = driverEtcDeductionTotal;

    const emptyCard = (document.getElementById("id_etc_empty_card")?.value || "company").trim();
    const returnMeth = (document.getElementById("id_etc_return_fee_method")?.value || "none").trim();
    const returnClaim = toInt(document.getElementById("id_etc_return_fee_claimed")?.value, 0);

    if (
      emptyCard === "own" &&
      typeof ETC_COVERAGE !== "undefined" &&
      ETC_COVERAGE.coverReturnMethods &&
      ETC_COVERAGE.coverReturnMethods.has(returnMeth)
    ) {
      const covered = Math.min(driverEmptyEtc, returnClaim);
      driverCost -= covered;
    }

    if (driverCost < 0) driverCost = 0;

    if (driverCostView) driverCostView.textContent = driverCost.toLocaleString();
    if (driverCostHidden) driverCostHidden.value = String(driverCost);
  })();
}
/* ====== REPLACE TO HERE ====== */





// ====== 夜班排序（保留，默认关闭） ======
(function () {
  function parseHHMM(str) {
    if (!str) return null;
    const parts = String(str).trim().split(":");
    if (parts.length < 2) return null;

    const h = parseInt(parts[0], 10);
    const m = parseInt(parts[1], 10);

    if (!Number.isFinite(h) || !Number.isFinite(m)) return null;

    const hh = Math.min(23, Math.max(0, h));
    const mm = Math.min(59, Math.max(0, m));

    return hh * 60 + mm;
  }
  function getAnchorMinutes() {
    const el = document.querySelector("input[name='clock_in']") || document.getElementById("id_clock_in");
    const v = el && el.value ? el.value : "12:00";
    const m = parseHHMM(v);
    return m == null ? 12 * 60 : m;
  }


  function sortRowsByTime(anchorMinutes) {
  const dataTb =
    document.querySelector("table.report-table tbody.data-body") ||
    document.querySelector("table.report-table tbody:not(#empty-form-template)");
  if (!dataTb) return;

  // ⭐ 关键补丁：如果外部没有传 anchorMinutes，就用当前出勤时间来计算
  if (anchorMinutes == null || !Number.isFinite(anchorMinutes)) {
    anchorMinutes = getAnchorMinutes();   // 上面同文件里已经定义过
  }

  const rows = $all("tr.report-item-row", dataTb);
  const pairs = rows.map(row => {
    const tInput =
      row.querySelector("input[name$='-ride_time']") ||
      row.querySelector(".time-input");
    const v = (tInput ? tInput.value : "") || "";
    let mins = parseHHMM(v);
    if (mins == null) {
      mins = Number.POSITIVE_INFINITY;
    } else if (mins < anchorMinutes) {
      mins += 24 * 60; // 跨夜，排到后面
    }
    return { row, key: mins };
  });

  pairs.sort((a, b) => a.key - b.key).forEach(p => dataTb.appendChild(p.row));

  let idx = 1;
  pairs.forEach(p => {
    const n = p.row.querySelector(".row-number");
    if (n) n.textContent = idx++;
  });

  updateSameTimeGrouping();
}
window.__resortByTime = sortRowsByTime;
})();


// ====== 提交前兜底 ======
(function ensureNumericBeforeSubmit() {
  const form = document.querySelector("form");
  if (!form) return;

  form.addEventListener("submit", function () {
    const selectors = [
      ".meter-fee-input",
      ".charter-amount-input",
      ".toll-input",
      ".etc-riding-input",
      ".etc-empty-input",
    ].join(",");

    document.querySelectorAll(selectors).forEach(inp => {
      if (!inp) return;
      const v = inp.value;
      if (v === "" || v == null) {
        inp.value = "0";
      } else {
        const num = parseInt(String(v).replace(/[^\d-]/g, ""), 10);
        inp.value = Number.isFinite(num) ? String(num) : "0";
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

    const emptyEtc = toInt(
      (row.querySelector(".etc-empty-input") ||
       row.querySelector("input[name$='-etc_empty']"))?.value,
      0
    );
    const chargeType = (row.querySelector(".etc-empty-charge-select")?.value || "company").trim();

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

// 回程费 & ETC 收取 相关控件变化时，重新计算
[
  "#id_etc_uncollected",
  "#id_etc_return_fee_claimed",
  "#id_etc_return_fee_method",
  "#id_etc_empty_card",
  "#id_etc_collected",         // ← 新增：ETC 收取金额
  "#id_etc_payment_method",    // ← 新增：ETC 收款方式
  "#id_etc_rider_payer"        // ← 新增：乗車ETC 支払者（如有需要一并联动）
].forEach((sel) => {
  const el = document.querySelector(sel);
  if (!el) return;
  el.addEventListener("input", () => updateTotals());
  el.addEventListener("change", () => updateTotals());
});

// ====== 页面主绑定 ======
(function initDailyReportPage() {
  // 1) 现有行：只绑定事件，不再批量改下拉
  $all("tr.report-item-row").forEach(row => {
    bindRowEvents(row);
  });

  // 1.5) 页面刚打开时，给所有“还没选项”的支付下拉补一次 options
  fillPaymentMethodOptions(document);

  // 2) 行内「➕下に挿入」按钮
  const table = document.querySelector('table.report-table');
  if (table) {
    table.addEventListener("click", (e) => {
      const btn = e.target.closest(".insert-below");
      if (!btn) return;
      e.preventDefault();

      const row = getRow(btn);
      const rows = $all("tr.report-item-row", table);
      const index = row ? (rows.findIndex(r => r === row) + 1) : 1;

      // insertRowAfter 内部已经完成各种更新
      insertRowAfter(index);
      // 按当前状态同步一次 ETC 列显隐
      syncEtcColVisibility();
    });
  }

  // 3) 顶部“指定行に挿入”输入 + 按钮
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
      if (newRow) {
        // 再保险：再绑一次事件
        bindRowEvents(newRow);
      }

      updateRowNumbersAndIndexes();
      updateSameTimeGrouping();
      updateTotals();
      evaluateEmptyEtcDetailVisibility();
      syncEtcColVisibility();
    });
  }

  // 4) 退勤勾选状态同步
  (function () {
    var out = document.getElementById("id_clock_out");
    var chk = document.getElementById("id_unreturned_flag") ||
              document.querySelector('input[name="unreturned_flag"]');
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

  // 5) 初始计算 / 状态同步
  initFlatpickr(document);
  // ensureActualEtcIndicator();

  updateDuration();
  updateRowNumbersAndIndexes();
  updateSameTimeGrouping();
  updateTotals();
  evaluateEmptyEtcDetailVisibility();
})();

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

/* ===== [PATCH PAYROLL DETAILS TOGGLE BEGIN] summary 文案切换 + 金额表示 ===== */
(function initPayrollDetailsSummaryToggle() {
  const yenText = () => {
    const el = document.getElementById("payroll-total");
    if (!el) return "--";
    const t = (el.textContent || "").trim();
    return t ? t : "--";
  };

  const setText = (detailsEl) => {
    const summary = detailsEl?.querySelector("summary");
    if (!summary) return;

    const base = detailsEl.open ? "内訳を隠す" : "内訳を表示";
    summary.textContent = `${base}（支給目安：${yenText()}円）`;
  };

  const bind = () => {
    const detailsList = Array.from(
      document.querySelectorAll("details.payroll-details")
    );

    // 公开一个全局刷新函数：updateTotals() 每次算完 payroll-total 后调用即可
    window.__refreshPayrollSummary = () => {
      detailsList.forEach((d) => setText(d));
    };

    // 初期表示
    window.__refreshPayrollSummary();

    // 开闭时刷新
    detailsList.forEach((d) => d.addEventListener("toggle", () => setText(d)));
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
/* ===== [PATCH PAYROLL DETAILS TOGGLE END] ===== */




// =====================================================
// 解决“返回后最后一行不保存”的问题：
// 当通过浏览器“后退”回到本页，而且页面来自 bfcache（event.persisted=true）
// 或 navigation type 是 'back_forward' 时，强制刷新一次。
// =====================================================
window.addEventListener('pageshow', function (event) {
  try {
    // 情况 1：来自 bfcache（Chrome/Safari/Firefox 通用）
    if (event.persisted) {
      window.location.reload();
      return;
    }

    // 情况 2：某些浏览器用 navigation type 标记“后退/前进”
    if (window.performance && performance.getEntriesByType) {
      var entries = performance.getEntriesByType('navigation') || [];
      if (entries.length && entries[0].type === 'back_forward') {
        window.location.reload();
      }
    }
  } catch (e) {
    console && console.warn && console.warn('pageshow reload failed:', e);
  }
});