document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".upload-btn").forEach(function (input) {
    input.addEventListener("change", function () {
      const file = this.files[0];
      const statusSpan = this.nextElementSibling;

      const formData = new FormData();
      formData.append("file", file);

      fetch("/vehicles/upload_vehicle_image/", {
        method: "POST",
        body: formData,
      })
        .then((res) => res.json())
        .then((data) => {
          if (data.url) {
            const container = this.closest("tr");
            const hiddenInput = container.querySelector("input[name$='-image']");
            hiddenInput.value = data.url;
            statusSpan.innerHTML = `<a href="${data.url}" target="_blank">✅ 上传成功</a>`;
          } else {
            statusSpan.innerText = "上传失败";
          }
        })
        .catch(() => {
          statusSpan.innerText = "上传失败";
        });
    });
  });
});
