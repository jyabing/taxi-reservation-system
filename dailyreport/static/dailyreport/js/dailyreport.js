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

  // —— 3. 行号与索引同步（安全版：仅更新显示编号）——
  function updateRowNumbersAndIndexes() {
    const rows = Array.from(document.querySelectorAll("tr.report-item-row"))
      .filter(r => r.style.display !== "none");

    rows.forEach((row, i) => {
      const cell = row.querySelector(".row-number");
      if (cell) cell.textContent = i + 1; // 仅更新显示用行号（1-based）
    });

    // ⚠️ 不修改任何 input/select 的 name/id/for
    // ⚠️ 不修改 ManagementForm 的 TOTAL_FORMS
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
    const pendingCb    = row.querySelector("input[name$='-is_pending']") || row.querySelector(".pending-checkbox"); // ← 新增
    if (amountInput)  amountInput.addEventListener("input",  updateTotals);
    if (methodSelect) methodSelect.addEventListener("change", updateTotals);
    if (pendingCb)    pendingCb.addEventListener("change",   updateTotals); // ← 新增：切换“待入”即重算

  }

  // 帮助函数：用空模板克隆新行（prefix=当前TOTAL_FORMS）
  function makeNewRowFromTemplate() {
    const totalEl = document.querySelector("input[name$='-TOTAL_FORMS']");
    const template = document.getElementById("empty-form-template");
    if (!template || !totalEl) return null;

    const count = parseInt(totalEl.value, 10);  // 新行索引 = 现有总数
    const html = template.innerHTML
      .replace(/__prefix__/g, count)
      .replace(/__num__/g, count + 1); // 行号显示可以先用 count+1

    const temp = document.createElement("tbody");
    temp.innerHTML = html;
    return { tr: temp.querySelector("tr"), count };
  }

  
  // —— 5. 增加一行 ——（安全：只递增 TOTAL_FORMS，不重排旧行）
  document.getElementById("add-row-btn")?.addEventListener("click", () => {
    const tbody = getDataTbody();
    const totalEl = document.querySelector("input[name$='-TOTAL_FORMS']");
    if (!tbody || !totalEl) return;

    const created = makeNewRowFromTemplate();
    if (!created) return;

    tbody.appendChild(created.tr);

    // 关键：递增 TOTAL_FORMS（只在新增时改）
    totalEl.value = String(parseInt(totalEl.value, 10) + 1);

    bindRowEvents(created.tr);
    updateRowNumbersAndIndexes();
    updateTotals();
  });


  // 取得数据用 tbody（排除隐藏模板 tbody）
function getDataTbody() {
  // 优先：不是 #empty-form-template 的 tbody
  let tb = document.querySelector("table.report-table > tbody:not(#empty-form-template)");
  if (tb) return tb;
  // 兜底：取第一个 tbody，但排除模板
  const bodies = Array.from(document.querySelectorAll("table.report-table > tbody"));
  return bodies.find(b => b.id !== "empty-form-template") || null;
}

/**
 * 按 1-based 行号在该位置“插入一行”
 * 例：insertRowAt(10) → 在第10行“之前”插入（新行成为新的第10行）
 */
function insertRowAt(n) {
  const tbody = getDataTbody();
  const totalEl = document.querySelector("input[name$='-TOTAL_FORMS']");
  if (!tbody || !totalEl) return;

  const rows = Array.from(tbody.querySelectorAll("tr.report-item-row"))
    .filter(r => r.style.display !== "none");

  // 规范化 n（1-based）
  let pos = parseInt(n, 10);
  if (Number.isNaN(pos) || pos < 1) pos = 1;
  if (pos > rows.length + 1) pos = rows.length + 1;

  const created = makeNewRowFromTemplate();
  if (!created) return;

  // 在第 pos 行“之前”插入；若 pos 是末尾+1 就 append
  if (pos <= rows.length) {
    tbody.insertBefore(created.tr, rows[pos - 1]);
  } else {
    tbody.appendChild(created.tr);
  }

  // 递增 TOTAL_FORMS
  totalEl.value = String(parseInt(totalEl.value, 10) + 1);

  // 绑定 & 重算
  bindRowEvents(created.tr);
  updateRowNumbersAndIndexes();
  updateTotals();
}

  // 绑定“指定行插入”按钮
  document.getElementById("insert-at-btn")?.addEventListener("click", () => {
    const v = document.getElementById("insert-index-input")?.value;
    insertRowAt(v);
  });

  // —— 6. 向下插入一行 ——（安全：只递增 TOTAL_FORMS，不重排旧行）
  document.querySelector("table.report-table")?.addEventListener("click", (e) => {
    if (!e.target.classList.contains("insert-below")) return;

    const tbody = getDataTbody();
    const totalEl = document.querySelector("input[name$='-TOTAL_FORMS']");
    if (!tbody || !totalEl) return;

    const created = makeNewRowFromTemplate();
    if (!created) return;

    const currentRow = e.target.closest("tr");
    tbody.insertBefore(created.tr, currentRow.nextSibling);

    // ✅ 递增 TOTAL_FORMS
    totalEl.value = String(parseInt(totalEl.value, 10) + 1);

    bindRowEvents(created.tr);
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
    // 新字段（可选）：id_etc_uncollected（空车ETC金额）、id_etc_return_fee_claimed（回程费额度）、
    //                id_etc_return_fee_method（app_ticket / cash_to_driver / none）、id_etc_payment_method（company_card/personal_card）
    const hasNewEmpty = !!document.getElementById('id_etc_uncollected');
    let emptyAmount = hasNewEmpty ? readIntById('id_etc_uncollected', 0) : 0;
    const returnFee = hasNewEmpty ? readIntById('id_etc_return_fee_claimed', 0) : 0;
    const returnFeeMethod = hasNewEmpty ? (document.getElementById('id_etc_return_fee_method')?.value || 'none') : 'none';
    const emptyCard = hasNewEmpty ? (document.getElementById('id_etc_payment_method')?.value || 'company_card') : 'company_card';

    // 覆盖额：只有回程费“随 app/チケット 一起结算”的部分视作覆盖
    const coveredByCustomer = (returnFeeMethod === 'app_ticket') ? returnFee : 0;

    let etcUncollected = 0;    // “多收”的回程费（> 空车ETC）→ 记未收（仅展示/统计）
    let etcDriverBurden = 0;   // 司机负担（短收）：空车ETC > 覆盖额 → 工资扣除

    if (hasNewEmpty) {
      // 有新字段：按卡来源判断是否公司承担
      if (emptyCard === 'company_card' || emptyCard === '') {
        etcUncollected  = Math.max(0, coveredByCustomer - emptyAmount);
        etcDriverBurden = Math.max(0, emptyAmount - coveredByCustomer);
      } else {
        // personal_card：公司不回收，也不扣司机（你口径：0）
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

    /* >>>>>>>>>>>>>>>  新增【应收合计】计算 ———— 起点  <<<<<<<<<<<<<<<< */
    // 乗車ETC（実車）合計
    const rideTotalForExpected = parseInt(document.getElementById('id_etc_collected')?.value || "0", 10) || 0;

    // 空車ETC 金額（优先新字段 id_etc_uncollected；没有则兼容旧的“未收ETC”）
    let emptyAmountForExpected = 0;
    if (document.getElementById('id_etc_uncollected')) {
      emptyAmountForExpected = parseInt(document.getElementById('id_etc_uncollected')?.value || "0", 10) || 0;
    } else {
      // 旧口径兼容（没有“空車金额”输入时，用“未收ETC”来拼应收显示）
      emptyAmountForExpected = parseInt(document.getElementById('id_etc_uncollected')?.value || "0", 10) || 0;
    }

    const etcExpected = rideTotalForExpected + emptyAmountForExpected;

    // 写到只读展示框
    const expectedDisplay = document.getElementById('etc-expected-output');
    if (expectedDisplay) {
      expectedDisplay.value = etcExpected.toLocaleString();
    }

    // 如果模板里有隐藏字段 #id_etc_expected（将来要回传后端），也一起回填（可选）
    const hiddenExpected = document.getElementById('id_etc_expected');
    if (hiddenExpected) {
      hiddenExpected.value = etcExpected;
    }
    /* >>>>>>>>>>>>>>>  新增【应收合计】计算 ———— 终点  <<<<<<<<<<<<<<<< */
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
      // —— 新增：勾选“待入”的行一律不计入任何合计 ——
      const isPending =
        (row.querySelector("input[name$='-is_pending']") || row.querySelector(".pending-checkbox"))?.checked;
      if (isPending) return;
      // —— 新增结束 ——
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

    // === 追加开始：计算并渲染「括号里的分成/手数料」 ===
    const rateOf = (k) =>
      (window.PAYMENT_RATES && window.PAYMENT_RATES[k] != null)
        ? Number(window.PAYMENT_RATES[k])
        : 0;

    // 这些 key 在面板里都有「（<span id="bonus_xxx">…</span>）」括号
    const BONUS_KEYS = ['credit','qr','kyokushin','omron','kyotoshi','uber','didi','go'];

    BONUS_KEYS.forEach((k) => {
      const el = document.getElementById(`bonus_${k}`);
      if (!el) return;
      const subtotal = Number(totalMap[k] || 0);
      const feeYen = Math.round(subtotal * rateOf(k)); // 分成/手数料
      el.textContent = feeYen.toLocaleString();
    });
    // 现金没有分成，强制归零（如果模板里有）
    const bonusCashEl = document.getElementById('bonus_cash');
    if (bonusCashEl) bonusCashEl.textContent = '0';
    // === 追加结束 ===

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

  // =========================
  // ★ 初始化「貸切」行的 料金 只读态（不清空、不 disabled）
  // =========================
  document.querySelectorAll("tr.report-item-row").forEach((row) => {
    const chk       = row.querySelector("input[type='checkbox'][name$='-is_charter']");
    const meter     = row.querySelector(".meter-fee-input");
    // 保险起见，清除任何历史 disabled
    if (meter) meter.removeAttribute("disabled");

    if (chk && chk.checked && meter) {
      // 勾选时：只读 + 灰色外观；保留原值
      meter.setAttribute("readonly", "readonly");
      meter.classList.add("readonly");
      // 强制保持现值（防止其他监听清空）
      if (!meter.dataset.originalValue) meter.dataset.originalValue = meter.value || "";
      meter.value = meter.dataset.originalValue;
    }
  });

  // ★ 绑定现有的「貸切」复选框 → 状态变化时应用只读逻辑
  document.querySelectorAll("input[type='checkbox'][name$='-is_charter']").forEach((chk) => {
    chk.addEventListener("change", () => {
      const row   = chk.closest("tr");
      const meter = row?.querySelector(".meter-fee-input");
      if (!meter) return;
      meter.removeAttribute("disabled"); // 兜底
      if (chk.checked) {
        if (!meter.dataset.originalValue) meter.dataset.originalValue = meter.value || "";
        meter.setAttribute("readonly", "readonly");
        meter.classList.add("readonly");
        meter.value = meter.dataset.originalValue;
      } else {
        meter.removeAttribute("readonly");
        meter.classList.remove("readonly");
      }
    });
  });

  // 初始执行一次
  updateSmartHintPanel();

  // ★ 页面加载时，已勾选的行套用只读灰态（不清空）
  if (typeof hydrateAllCharterRows === 'function') {
    hydrateAllCharterRows();
  } else {
    // 兜底：直接处理一次
    document.querySelectorAll("tr.report-item-row").forEach((row) => {
      const chk = row.querySelector("input[type='checkbox'][name$='-is_charter']");
      const meter = row.querySelector(".meter-fee-input");
      if (chk && chk.checked && meter) {
        meter.removeAttribute('disabled');
        if (!meter.dataset.originalValue) meter.dataset.originalValue = meter.value || "";
        meter.setAttribute('readonly', 'readonly');
        meter.classList.add('readonly');
        meter.value = meter.dataset.originalValue;
      }
    });
  }
});


  // —— 9. 绑定监听 ——
  [
    ['id_etc_collected_cash', [updateEtcDifference, updateEtcShortage]],
    ['id_etc_uncollected', [updateEtcDifference, updateEtcShortage]],
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

// ===== 夜班按时间排序（00:xx 排在 23:xx 之后）— 仅在提交时执行 =====
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
    const anchor = getAnchorMinutes();
    const tbody  = document.querySelector("table.report-table tbody:not(#empty-form-template)");
    if (!tbody) return;

    const rows = Array.from(tbody.querySelectorAll("tr.report-item-row"));
    const pairs = rows.map(row => {
      // 改：按字段名匹配 ride_time；兼容老的 .ride-time-input
      const t = (row.querySelector("input[name$='-ride_time']") ||
                 row.querySelector(".ride-time-input") ||
                 row.querySelector(".time-input"))?.value || "";
      let mins = parseHHMM(t);
      if (mins == null) mins = Number.POSITIVE_INFINITY;
      else if (mins < anchor) mins += 24 * 60;
      return { row, key: mins };
    });

    pairs.sort((a, b) => a.key - b.key).forEach(p => tbody.appendChild(p.row));

    // 只更新显示行号
    let idx = 1;
    pairs.forEach(p => {
      const num = p.row.querySelector(".row-number");
      if (num) num.textContent = idx++;
    });
  }

  // 只在“保存提交”时排序；不再绑定任何 input 事件
  window.addEventListener("DOMContentLoaded", () => {
    const form = document.querySelector('form[method="post"]');
    if (!form) return;
    form.addEventListener('submit', () => {
      sortRowsByTime();
      if (typeof updateRowNumbersAndIndexes === 'function') {
        updateRowNumbersAndIndexes();
      }
      // 不改 name/index/TOTAL_FORMS，只排序 DOM 以便保存前视觉上按时间。
    });
  });

  // 可选：暴露给其他代码手动调用
  window.sortDailyRowsByTime = sortRowsByTime;
})();


// ==== 工具：按貸切勾选状态，禁用/启用 当行的 料金 与 支付，并在取消时清空貸切字段 ====
function applyCharterState(row, isCharter) {
  if (!row) return;
  const meterInput           = row.querySelector(".meter-fee-input");
  const paySelect            = row.querySelector(".payment-method-select");
  const charterAmountInput   = row.querySelector(".charter-amount-input");
  const charterPaymentSelect = row.querySelector(".charter-payment-method-select");

  // ★ 永远不要 disabled / 清空 料金；用 readonly + 外观变灰，确保提交保留值
  if (meterInput) {
    meterInput.removeAttribute('disabled'); // 清历史残留
    // 记录原值（只记录一次）
    if (!meterInput.dataset.originalValue) {
      meterInput.dataset.originalValue = meterInput.value || "";
    }
    if (isCharter) {
      meterInput.setAttribute('readonly', 'readonly');
      meterInput.classList.add('readonly');
      // 强制保持原值，防止其他监听清空
      meterInput.value = meterInput.dataset.originalValue;
    } else {
      meterInput.removeAttribute('readonly');
      meterInput.classList.remove('readonly');
      // 允许编辑，保留现值
    }
  }

  // 取消勾选：清空「貸切」两个字段（保留你的逻辑）
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

  if (typeof updateTotals === "function") updateTotals();
}
// 首次进场时，把所有行按当前勾选状态套用一次
function hydrateAllCharterRows() {
  document
    .querySelectorAll("input[type='checkbox'][name$='-is_charter']")
    .forEach(chk => applyCharterState(getRow(chk), chk.checked));
}

// —— 11. 勾选「貸切」后自动复制金额和支付方式 ——
// 要求：每一行明细中包含以下 class：.meter-fee-input, .payment-method-select,
// .charter-amount-input, .charter-payment-method-select

// 勾选「貸切」时：自动复制金额与支付方式，并在勾选后如再改金额/支付方式也会同步
document.addEventListener("change", function (e) {
  const el = e.target;
  // 兼容 name 选择器与 class 选择器两种写法
  if (!el.matches("input[type='checkbox'][name$='-is_charter']")) return;

  const row = getRow(el);
  if (!row) return;

  const meterInput           = row.querySelector(".meter-fee-input");
  const paySelect            = row.querySelector(".payment-method-select");
  const charterAmountInput   = row.querySelector(".charter-amount-input");
  const charterPaymentSelect = row.querySelector(".charter-payment-method-select");

  // 工具：把任意输入转为整数（非数字→0）
  const toInt = (v) => {
    const n = parseInt(String(v ?? "").replace(/[^\d-]/g, ""), 10);
    return Number.isFinite(n) ? n : 0;
  };
  const isCashLike = (v) => (v || "").toLowerCase().includes("cash") || /現金/.test(v || "");

  if (el.checked) {
    // 1) 复制当前料金到「貸切金額」（做整数化）
    const feeInt = toInt(meterInput ? meterInput.value : 0);
    if (charterAmountInput) charterAmountInput.value = String(feeInt);

    // 2) 按当前支付方式映射「処理」
    if (charterPaymentSelect) {
      const pm = paySelect?.value || "";
      charterPaymentSelect.value = isCashLike(pm) ? "jpy_cash" : "to_company";
    }

    // 3) 料金设为只读（不 disabled、不清空）
    applyCharterState(row, true);
    if (meterInput) {
      meterInput.readOnly = true;
      meterInput.classList.add("disabled");
      // 保底：若其他脚本清空过，这里强制回写整数化后的值
      meterInput.value = String(feeInt);
    }

    // 4) 主支付方式统一成现金（若当前不是现金）
    if (paySelect && !isCashLike(paySelect.value)) {
      const cashOpt = Array.from(paySelect.options || []).find(
        (o) => isCashLike(o.value) || isCashLike(o.textContent)
      );
      if (cashOpt) {
        paySelect.value = cashOpt.value;
        paySelect.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }

    // 5) 绑定“持续同步”（仅当本行未绑定过）
    if (row && !row.dataset.charterSyncBound) {
      row.dataset.charterSyncBound = "1";

      // 金额同步：用户修改料金时，实时同步到貸切金额（只在勾选状态下生效）
      if (meterInput && charterAmountInput) {
        const syncAmount = () => {
          if (!el.checked) return;
          const v = toInt(meterInput.value);
          charterAmountInput.value = String(v);
          window.updateTotals?.();
        };
        meterInput.addEventListener("input", syncAmount);
        meterInput.addEventListener("change", syncAmount);
      }

      // 支付方式同步：用户修改支付方式时，实时同步「処理」并尽量保持现金
      if (paySelect && charterPaymentSelect) {
        const syncPM = () => {
          if (!el.checked) return;
          const pm2 = paySelect.value || "";
          charterPaymentSelect.value = isCashLike(pm2) ? "jpy_cash" : "to_company";
          window.updateTotals?.();
        };
        paySelect.addEventListener("change", syncPM);
      }
    }
  } else {
    // 取消勾选：恢复输入，不清空任何金额，保持值为数字字符串
    applyCharterState(row, false);
    if (meterInput) {
      meterInput.readOnly = false;
      meterInput.classList.remove("disabled");
      meterInput.value = String(toInt(meterInput.value));
    }
    if (charterAmountInput) {
      charterAmountInput.value = String(toInt(charterAmountInput.value));
    }
  }

  window.updateTotals?.();
});

// === 提交前兜底：所有金额空串 → '0'（杜绝 "" 进入后端） ===
(function () {
  const form = document.querySelector("form");
  if (!form) return;
  form.addEventListener("submit", function () {
    const sel = [
      ".meter-fee-input",
      ".charter-amount-input",
      ".deposit-input",
      ".toll-input"
    ].join(",");
    document.querySelectorAll(sel).forEach((inp) => {
      if (!inp) return;
      const v = inp.value;
      if (v === "" || v == null) {
        inp.value = "0";
      } else {
        // 统一为数字字符串
        const n = parseInt(String(v).replace(/[^\d-]/g, ""), 10);
        inp.value = Number.isFinite(n) ? String(n) : "0";
      }
    });
  });
})();