document.addEventListener('DOMContentLoaded', () => {
  // —— 1. flatpickr 时间选择器 ——
  flatpickr(".time-input", {
    enableTime: true,
    noCalendar: true,
    dateFormat: "H:i",
    time_24hr: true,
    locale: "ja"
  });

  // —— 2. 勤務 / 実働 / 残業時間计算 ——
  function updateDuration() {
    const inEl = document.querySelector("input[name='clock_in']");
    const outEl = document.querySelector("input[name='clock_out']");
    const workDisplay = document.getElementById("work-duration");
    const actualDisplay = document.getElementById("actual-work-time");
    const overtimeDisplay = document.getElementById("overtime");
    const breakTimeDisplay = document.getElementById("break-time-display");
    const breakTimeHidden = document.getElementById("break-time-plus20");

    if (!inEl || !outEl) return;

    const [h1, m1] = (inEl.value || "00:00").split(":").map(Number);
    const [h2, m2] = (outEl.value || "00:00").split(":").map(Number);
    let d1 = new Date(0, 0, 0, h1, m1);
    let d2 = new Date(0, 0, 0, h2, m2);
    if (d2 <= d1) d2.setDate(d2.getDate() + 1);
    const workMin = Math.floor((d2 - d1) / 60000);

    let breakMin = 0;
    const breakEl = document.getElementById("break-time-input");
    if (breakEl && breakEl.value) {
      const [bh, bm] = breakEl.value.split(":").map(Number);
      breakMin = (bh || 0) * 60 + (bm || 0);
    }

    const realBreak = breakMin + 20;
    const actualMin = workMin - realBreak;
    const overtimeMin = actualMin - 480;

    const toHM = m => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;

    workDisplay.textContent = toHM(workMin);
    actualDisplay.textContent = toHM(actualMin);
    overtimeDisplay.textContent = (overtimeMin < 0 ? "-" : "") + toHM(Math.abs(overtimeMin));
    overtimeDisplay.style.color = overtimeMin >= 0 ? "red" : "blue";

    if (breakTimeDisplay) breakTimeDisplay.textContent = toHM(realBreak);
    if (breakTimeHidden) breakTimeHidden.value = toHM(realBreak);
  }

  // —— 3. 行号与索引同步 ——
  function updateRowNumbersAndIndexes() {
    const rows = document.querySelectorAll("tr.report-item-row");
    let index = 0;
    rows.forEach(row => {
      if (row.style.display === "none") return;
      row.querySelector(".row-number").textContent = index + 1;
      row.querySelectorAll("input, select, textarea, label").forEach(el => {
        ["name", "id", "for"].forEach(attr => {
          if (el.hasAttribute(attr)) {
            el.setAttribute(attr, el.getAttribute(attr).replace(/-\d+-/, `-${index}-`));
          }
        });
      });
      index++;
    });

    const totalEl = document.querySelector("input[name$='-TOTAL_FORMS']");
    if (totalEl) totalEl.value = index;
  }

  // —— 4. 单行事件绑定 ——
  function bindRowEvents(row) {
    row.querySelectorAll(".time-input").forEach(el => {
      flatpickr(el, { enableTime: true, noCalendar: true, dateFormat: "H:i", time_24hr: true, locale: "ja" });
    });

    row.querySelectorAll(".delete-row").forEach(btn => {
      btn.addEventListener("click", () => {
        if (confirm("确定删除此行？")) {
          const cb = row.querySelector("input[name$='-DELETE']");
          if (cb) {
            cb.checked = true;
            row.style.display = "none";
            updateRowNumbersAndIndexes();
            updateTotals();
          }
        }
      });
    });

    const checkbox = row.querySelector(".mark-checkbox");
    if (checkbox) {
      row.classList.toggle("has-note", checkbox.checked);
      checkbox.addEventListener("change", () => {
        row.classList.toggle("has-note", checkbox.checked);
      });
    }

    // 合计更新
    const amountInput = row.querySelector("input[name$='-meter_fee']");
    const methodSelect = row.querySelector("select[name$='-payment_method']");
    if (amountInput) amountInput.addEventListener("input", updateTotals);
    if (methodSelect) methodSelect.addEventListener("change", updateTotals);
  }

  // —— 5. 增加一行 ——
  document.getElementById("add-row-btn")?.addEventListener("click", () => {
    const totalEl = document.querySelector("input[name$='-TOTAL_FORMS']");
    const template = document.getElementById("empty-form-template");
    if (!template || !totalEl) return;

    const count = parseInt(totalEl.value, 10);
    const newHtml = template.innerHTML.replace(/__num__/g, count + 1).replace(/__prefix__/g, count);
    const row = document.createElement("tr");
    row.classList.add("report-item-row");
    row.innerHTML = newHtml;

    document.querySelector("table.report-table > tbody").appendChild(row);
    bindRowEvents(row);
    updateRowNumbersAndIndexes();
    updateTotals();
  });

  // —— 6. 向下插入一行 ——
  document.querySelector("table.report-table").addEventListener("click", (e) => {
    if (!e.target.classList.contains("insert-below")) return;
    const totalEl = document.querySelector("input[name$='-TOTAL_FORMS']");
    const template = document.querySelector("#empty-form-template");
    if (!template || !totalEl) return;

    const count = parseInt(totalEl.value, 10);
    const tempDiv = document.createElement("tbody");
    tempDiv.innerHTML = template.innerHTML.replace(/__prefix__/g, count).replace(/__num__/g, count + 1);
    const newRow = tempDiv.querySelector("tr");
    const currentRow = e.target.closest("tr");
    currentRow.parentNode.insertBefore(newRow, currentRow.nextSibling);
    bindRowEvents(newRow);
    updateRowNumbersAndIndexes();
    updateTotals();
  });

  // —— 工具：安全读取/写入（无则添加，有则跳过） ——
  function readIntById(id, fallback = 0) {
    const el = document.getElementById(id);
    if (!el) return fallback;
    const raw = el.value ?? el.textContent ?? `${fallback}`;
    const n = parseInt(raw, 10);
    return Number.isNaN(n) ? fallback : n;
  }
  function setTextById(id, val) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = (typeof val === "number") ? val.toLocaleString() : String(val);
  }

  // —— 7. ETC 差额、短收、高亮提示 ——
  // —— ETC 口径统一：乘车只记录；空车按覆盖额计算“未收/司机负担”；兼容老字段 ——
  function updateEtcDifference() {
    // 乘车ETC（実車）：只记录，不进入销售合计。若有“乘车ETC现金上交”，在过不足已经计算，不在此重复处理。
    const rideCash = readIntById('id_etc_collected_cash', 0);   // 乘车ETC现金（可为0）
    const rideTotal = readIntById('id_etc_collected', 0);       // 你现有字段：总的ETC使用额（历史用法）

    // —— 空车ETC（回程）逻辑：尽量兼容“新字段”，若没有就走旧口径回退 ——
    // 新字段（可选）：id_etc_empty_amount（空车ETC金额）、id_etc_return_fee_claimed（回程费额度）、
    //                id_etc_return_fee_method（app_ticket / cash_to_driver / none）、id_etc_empty_card（company/own/guest）
    const hasNewEmpty = !!document.getElementById('id_etc_empty_amount');
    let emptyAmount = hasNewEmpty ? readIntById('id_etc_empty_amount', 0) : 0;
    const returnFee = hasNewEmpty ? readIntById('id_etc_return_fee_claimed', 0) : 0;
    const returnFeeMethod = hasNewEmpty ? (document.getElementById('id_etc_return_fee_method')?.value || 'none') : 'none';
    const emptyCard = hasNewEmpty ? (document.getElementById('id_etc_empty_card')?.value || 'company') : 'company';

    // 覆盖额：只有回程费“随 app/チケット 一起结算”的部分视作覆盖
    const coveredByCustomer = (returnFeeMethod === 'app_ticket') ? returnFee : 0;

    let etcUncollected = 0;    // “多收”的回程费（> 空车ETC）→ 记未收（仅展示/统计）
    let etcDriverBurden = 0;   // 司机负担（短收）：空车ETC > 覆盖额 → 工资扣除

    if (hasNewEmpty) {
      // 有新字段：按卡来源判断是否公司承担
      if (emptyCard === 'company' || emptyCard === '') {
        etcUncollected  = Math.max(0, coveredByCustomer - emptyAmount);
        etcDriverBurden = Math.max(0, emptyAmount - coveredByCustomer);
      } else {
        // own / guest：公司不回收，也不扣司机（你口径：0）
        etcUncollected  = 0;
        etcDriverBurden = 0;
      }
    } else {
      // 无新字段：回退到你旧口径（保持你原页面能运作）
      // 旧字段：id_etc_uncollected（手填未收）
      etcUncollected  = readIntById('id_etc_uncollected', 0);
      // 旧的“短收”逻辑由 updateEtcShortage 计算；此处不重复。
      etcDriverBurden = readIntById('id_etc_shortage', 0);
    }

    // —— 写回展示/兼容字段 —— 
    // 展示条（如存在）
    const display = document.getElementById('etc-diff-display');
    if (display) {
      display.className = (etcDriverBurden > 0 || etcUncollected > 0) ? 'alert alert-warning' : 'alert alert-info';
      display.innerText = `未收ETC：${etcUncollected.toLocaleString()} 円；司机负担：${etcDriverBurden.toLocaleString()} 円`;
    }
    // 保持和你现有字段兼容：把计算结果回填（若存在这些输入）
    if (document.getElementById('id_etc_uncollected')) {
      document.getElementById('id_etc_uncollected').value = etcUncollected;
    }
    if (document.getElementById('id_etc_shortage')) {
      document.getElementById('id_etc_shortage').value = etcDriverBurden;
      document.getElementById('id_etc_shortage').classList.toggle('text-danger', etcDriverBurden > 0);
      document.getElementById('id_etc_shortage').classList.toggle('fw-bold', etcDriverBurden > 0);
    }
  }

  // 统一口径：避免双重口径冲突，直接复用 Difference 的结果
  function updateEtcShortage() {
    updateEtcDifference();
  }

  function updateEtcInclusionWarning() {
    const deposit = readIntById('id_deposit_amount', readIntById('deposit-input', 0));
    const cashNagashi = readIntById('total_cash', 0);                // 現金(ながし) 合計（UI上已有）
    const charterCash = readIntById('charter-cash-total', 0);        // 貸切現金
    const etcRideCash = readIntById('id_etc_collected_cash', 0);     // 乘车ETC现金上交（如有）

    const expected = cashNagashi + charterCash + etcRideCash;
    const diff = deposit - expected;

    const box = document.getElementById('etc-included-warning');
    if (!box) return;

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

  function resolveJsPaymentMethod(raw) {

    if (!raw) return "";
    const val = String(raw).trim();

    // 先处理我们明确知道的英文枚举 / 规范值
    const exact = {
      // 现金
      cash: "cash",
      uber_cash: "cash",
      didi_cash: "cash",
      go_cash: "cash",

      // 平台（アプリ決済）
      uber: "uber",
      didi: "didi",
      go: "go",

      // 其他
      credit_card: "credit",
      kyokushin: "kyokushin",
      omron: "omron",
      kyotoshi: "kyotoshi",
      barcode: "qr",
      qr: "qr",
      "------": "",
      "--------": "",
    };
    if (exact[val] !== undefined) return exact[val];

    // 然后做“包含/正则”匹配，兼容日文/多写法
    const v = val.toLowerCase();

    // 現金
    if (val.includes("現金")) return "cash";

    // 平台
    if (v.includes("uber")) return "uber";
    if (v.includes("didi") || v.includes("ｄｉｄｉ") || v.includes("di di")) return "didi";
    if (v === "go" || v === "ｇｏ" || /(^|\s)go(\s|$)/.test(v)) return "go";

    // クレジット
    if (val.includes("クレジ") || v.includes("credit")) return "credit";

    // チケット系
    if (val.includes("京交信")) return "kyokushin";
    if (val.includes("オムロン")) return "omron";
    if (val.includes("京都市他")) return "kyotoshi";

    // バーコード / 扫码 / Pay系
    if (
      val.includes("バーコード") ||
      v.includes("paypay") ||
      val.includes("微信") || val.includes("支付宝") ||
      val.includes("扫码") ||
      v.includes("qr")
    ) return "qr";

    // 没命中就原样返回（便于将来再补）
    return val;
  }

  // ======= 替换开始：合计逻辑（不把ETC并入合计；过不足含乗車ETC现金） =======
  function updateTotals() {
    // 仅保留“平台アプリ決済”三个：uber/didi/go；平台现金都进 cash
    const totalMap = {
      cash: 0,   // = 现金 + uber_cash + didi_cash + go_cash
      uber: 0,   // 仅 Uber アプリ決済
      didi: 0,   // 仅 Didi アプリ決済
      go: 0,     // 仅 GO アプリ決済（UI没有此卡片可忽略写入）
      credit: 0,
      kyokushin: 0,
      omron: 0,
      kyotoshi: 0,
      qr: 0,
    };

    let totalMeter = 0;        // 卖上合计
    let totalMeterOnly = 0;    // メータのみ（不含貸切）
    let charterCashTotal = 0;  // 貸切現金
    let charterUncollectedTotal = 0; // 貸切未収

    // 遍历明细行
    document.querySelectorAll(".report-item-row").forEach(row => {
      const fee = parseInt(row.querySelector(".meter-fee-input")?.value || "0", 10);
      const payment = row.querySelector("select[name$='payment_method']")?.value || "";
      const isCharter = row.querySelector("input[name$='is_charter']")?.checked;
      const charterAmount = parseInt(row.querySelector(".charter-amount-input")?.value || "0", 10);
      const charterPayMethod = row.querySelector(".charter-payment-method-select")?.value || "";

      // 卖上合计（包括貸切）
      totalMeter += fee;

      // メータのみ（不含貸切）
      if (!isCharter) totalMeterOnly += fee;

      // ✅ 补上这一行：把下拉值映射成我们统一的 key
      const method = resolveJsPaymentMethod(payment);

    // 付款方式分配（用“映射后”的 method；平台现金→cash，barcode→qr）
    if (!isCharter && fee > 0) {
      if (totalMap.hasOwnProperty(method)) {
        totalMap[method] += fee;
      }
    }

      // 貸切金额处理（修正：按枚举判断现金/未收）
      const CHARTER_CASH_METHODS = ['jpy_cash', 'rmb_cash', 'self_wechat', 'boss_wechat'];
      const CHARTER_UNCOLLECTED_METHODS = ['to_company', 'bank_transfer', '']; // 空值也当未收以免漏算

      if (isCharter && charterAmount > 0) {
        if (CHARTER_CASH_METHODS.includes(charterPayMethod)) {
          charterCashTotal += charterAmount;
        } else if (CHARTER_UNCOLLECTED_METHODS.includes(charterPayMethod)) {
          charterUncollectedTotal += charterAmount;
        }
      }
    });

    // 写入合计到页面
    document.getElementById("total_meter")?.replaceChildren(document.createTextNode(totalMeter.toLocaleString()));
    document.getElementById("total_meter_only")?.replaceChildren(document.createTextNode(totalMeterOnly.toLocaleString()));
    document.getElementById("total_cash")?.replaceChildren(document.createTextNode(totalMap.cash.toLocaleString()));
    document.getElementById("total_credit")?.replaceChildren(document.createTextNode(totalMap.credit.toLocaleString()));
    document.getElementById("charter-cash-total")?.replaceChildren(document.createTextNode(charterCashTotal.toLocaleString()));
    document.getElementById("charter-uncollected-total")?.replaceChildren(document.createTextNode(charterUncollectedTotal.toLocaleString()));

    
    // 🖋️ 把各支付方式小计写到页面（含 uber/didi/kyokushin/omron/kyotoshi/qr 等）
    Object.entries(totalMap).forEach(([k, v]) => {
      const el = document.getElementById(`total_${k}`);
      if (el) el.textContent = v.toLocaleString();
    });

    // ✅ メータのみ（不含貸切 & 不含ETC）
    const meterSum = Object.values(totalMap).reduce((a, b) => a + b, 0);
    const meterOnlyEl = document.getElementById("total_meter_only");
    if (meterOnlyEl) meterOnlyEl.textContent = meterSum.toLocaleString();

    // ✅ 売上合計 = メータのみ + 貸切現金 + 貸切未収
    const salesTotal = meterSum + charterCashTotal + charterUncollectedTotal;
    const salesEl1 = document.getElementById("total_meter"); // 模板显示“売上合計”的位置
    if (salesEl1) salesEl1.textContent = salesTotal.toLocaleString();
    const salesEl2 = document.getElementById("sales-total"); // 若还有另一处，也一起写
    if (salesEl2) salesEl2.textContent = salesTotal.toLocaleString();
    
    // 计算过不足（入金 - 現金(ながし) - 貸切現金）
    const depositInput = parseInt(document.getElementById("deposit-input")?.value || "0", 10);
    const shortage = depositInput - totalMap.cash - charterCashTotal;
    const diffEl = document.getElementById("difference-output")
      || document.getElementById("deposit-difference")
      || document.getElementById("shortage-diff");
    if (diffEl) diffEl.textContent = shortage.toLocaleString();
  }

  // ✅ 智能提示面板更新函数
  function updateSmartHintPanel() {
    const depositInput = document.querySelector("#deposit-input");

    const cashTotal = parseInt(document.querySelector("#total_cash")?.textContent || "0", 10);
    
    const etcCollected = parseInt(document.querySelector("#id_etc_collected")?.value || "0", 10);
    const etcUncollected = parseInt(document.querySelector("#id_etc_uncollected")?.value || "0", 10);
    const totalSales = parseInt(document.querySelector("#total_meter")?.textContent || "0", 10);

    const deposit = parseInt(depositInput?.value || "0", 10);
    const totalCollected = cashTotal + etcCollected;

    const panel = document.querySelector("#smart-hint-panel");
    if (!panel) return;

    let html = "";

    if (deposit < totalCollected) {
      html += `
        <div class="alert alert-danger py-1 px-2 small mb-2">
          ⚠️ 入金額が不足しています。請求額（現金 + ETC）は <strong>${totalCollected.toLocaleString()}円</strong> ですが、入力された入金額は <strong>${deposit.toLocaleString()}円</strong> です。
        </div>`;
    } else {
      html += `
        <div class="alert alert-success py-1 px-2 small mb-2">
          ✔️ 入金額は現金 + ETC をカバーしています。
        </div>`;
    }

    if (etcUncollected > 0) {
      html += `
        <div class="alert alert-info py-1 px-2 small mb-2">
          🚧 ETC 未收：<strong>${etcUncollected.toLocaleString()}円</strong>。请确认司机是否已补收。
        </div>`;
    }

    if (deposit < totalSales) {
      html += `
        <div class="alert alert-warning py-1 px-2 small mb-2">
          ℹ️ 売上合計 <strong>${totalSales.toLocaleString()}円</strong> 大于入金 <strong>${deposit.toLocaleString()}円</strong>，可能包含未收 ETC、或其他延迟结算项。
        </div>`;
    }

    panel.innerHTML = html;
  }

  // ✅ 页面加载后绑定事件
  document.addEventListener("DOMContentLoaded", function () {
    const depositInput = document.querySelector("#deposit-input");
    const etcInputs = [
      document.querySelector("#id_etc_collected"),
      document.querySelector("#id_etc_uncollected"),
    ];

    // 监听字段变化，实时刷新智能提示
    [depositInput, ...etcInputs].forEach((input) => {
      if (input) {
        input.addEventListener("input", updateSmartHintPanel);
      }
    });

    // 初始执行一次
    updateSmartHintPanel();
  });



  // —— 9. 绑定监听 ——
  [
    ['id_etc_collected_cash', [updateEtcDifference, updateEtcShortage]],
    ['id_etc_uncollected', [updateEtcDifference, updateEtcShortage]],
    ['id_etc_collected', [updateEtcInclusionWarning, updateEtcShortage, updateTotals]],
    ['id_deposit_amount', [updateEtcDifference, updateEtcInclusionWarning]],
    ['clock_in', [updateDuration]],
    ['clock_out', [updateDuration]],
    ['break-time-input', [updateDuration]],
    ['id_etc_payment_method', [updateTotals]],
  ].forEach(([id, fns]) => {
    const el = document.getElementById(id);
    if (el) fns.forEach(fn => el.addEventListener("input", fn));
  });

  // —— 10. 初始加载执行 ——
  updateDuration();
  updateEtcDifference();
  updateEtcShortage();
  updateEtcInclusionWarning();
  updateRowNumbersAndIndexes();
  updateTotals();
});

// —— 11. 勾选「貸切」后自动复制金额和支付方式 ——
// 要求：每一行明细中包含以下 class：.meter-fee-input, .payment-method-select,
// .charter-amount-input, .charter-payment-method-select

document.addEventListener("change", function (e) {
  const el = e.target;
  if (!el.matches("input[type='checkbox'][name$='-is_charter']")) return;

  const row = el.closest("tr");
  if (!row) return;

  const meterInput = row.querySelector(".meter-fee-input");
  const paySelect = row.querySelector(".payment-method-select");
  const charterAmountInput = row.querySelector(".charter-amount-input");
  const charterPaymentSelect = row.querySelector(".charter-payment-method-select");

  if (!charterAmountInput || !charterPaymentSelect) return;

  if (el.checked) {
    // 自动填入金额
    charterAmountInput.value = meterInput?.value || "";

    // 原“支付”是现金系 → 直接当作“日元现金”
    const pm = paySelect?.value || "";
    if (["cash", "uber_cash", "didi_cash", "go_cash"].includes(pm)) {
      charterPaymentSelect.value = "jpy_cash";      // ← 新枚举
    } else {
      // 非现金 → 默认记到“转付公司”（你也可以换成 bank_transfer）
      charterPaymentSelect.value = "to_company";
    }
  } else {
    charterAmountInput.value = "";
    charterPaymentSelect.value = "";
  }
    // ✅ 显式挂到全局（必须放在函数定义之后）
  window.updateTotals = updateTotals;
  updateTotals(); // ✅ 勾选切换时也更新合计
});