function startEdit(vehicleId) {
  const displayDiv = document.getElementById(`note-display-${vehicleId}`);
  const editDiv = document.getElementById(`note-edit-${vehicleId}`);
  if (displayDiv && editDiv) {
    displayDiv.classList.add("d-none");
    editDiv.classList.remove("d-none");
  }
}

function cancelEdit(vehicleId) {
  const displayDiv = document.getElementById(`note-display-${vehicleId}`);
  const editDiv = document.getElementById(`note-edit-${vehicleId}`);
  if (displayDiv && editDiv) {
    editDiv.classList.add("d-none");
    displayDiv.classList.remove("d-none");
  }
}

function saveNote(vehicleId) {
  const input = document.getElementById(`note-input-${vehicleId}`);
  const noteText = input.value;

  fetch(`/vehicles/save_note/${vehicleId}/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCSRFToken(),
    },
    body: JSON.stringify({ notes: noteText }),
  })
  .then(response => {
    if (!response.ok) throw new Error("保存失败");
    return response.json();
  })
  .then(data => {
    if (data.success) {
      // ✅ 更新显示区域内容
      const display = document.getElementById(`note-display-${vehicleId}`);
      display.innerHTML = noteText
        .split("\n")
        .map(line => `<div>${line}</div>`)
        .join("");
      cancelEdit(vehicleId);
    } else {
      alert("保存失败，请重试");
    }
  })
  .catch(error => {
    console.error("备注保存错误:", error);
    alert("备注保存失败");
  });
}

// 获取 CSRF token 的通用方法
function getCSRFToken() {
  const cookieValue = document.cookie
    .split("; ")
    .find(row => row.startsWith("csrftoken="));
  return cookieValue ? cookieValue.split("=")[1] : "";
}