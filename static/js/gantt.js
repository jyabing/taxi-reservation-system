// 设置日期格式和视图模式
//gantt.config.xml_date = "%Y-%m-%d %H:%i";
//gantt.config.scale_unit = "day";
//gantt.config.date_scale = "%Y-%m-%d";
//gantt.config.subscales = [
    //{ unit:"hour", step:1, date:"%H:%i" }
//];

// 设置列
//gantt.config.columns = [
    //{name:"text",       label:"任务名称",  width: "*", tree:true },
    //{name:"start_date", label:"开始时间", align: "center" },
    //{name:"duration",   label:"持续天数", align: "center" }
//];

// 初始化
//gantt.init("gantt_here");

// 从后端动态加载数据
//gantt.load("/gantt/data/");  // 这里的路径要与你urls.py一致

// 加载任务数据（示例使用静态数据）
//gantt.parse({
    //data:[
        //{id:1, text:"项目启动", start_date:"2025-05-01 09:00", duration:3, progress:0.4, open: true},
        //{id:2, text:"任务 A",   start_date:"2025-05-02 09:00", duration:2, progress:0.6, parent:1},
        //{id:3, text:"任务 B",   start_date:"2025-05-03 09:00", duration:1, progress:0.8, parent:1}
    //]
//});

window.addEventListener("load", function () {
    const table = document.querySelector(".gantt-table");
    const canvas = document.getElementById("gantt-grid-overlay");
  
    if (!table || !canvas) return;
  
    // 延迟绘制，确保 DOM 完全渲染
    setTimeout(() => {
      const rect = table.getBoundingClientRect();
      canvas.width = rect.width;
      canvas.height = rect.height;
  
      canvas.style.position = "absolute";
      canvas.style.top = "0";
      canvas.style.left = "0";
      canvas.style.pointerEvents = "none";
      canvas.style.zIndex = 1;
  
      const ctx = canvas.getContext("2d");
  
      const headers = table.querySelectorAll("thead th:not(:first-child)");
      headers.forEach((th) => {
        const left = th.offsetLeft;
        ctx.beginPath();
        ctx.moveTo(left, 0);
        ctx.lineTo(left, canvas.height);
        ctx.strokeStyle = "#ccc";
        ctx.lineWidth = 1;
        ctx.stroke();
      });
  
      console.log("Canvas grid rendered at", new Date().toISOString());
    }, 100);  // 100ms 延迟：确保 table 完全渲染
  });  
  
  console.log("Gantt grid overlay loaded");