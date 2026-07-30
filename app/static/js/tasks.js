// Poll /api/tasks and refresh status/message cells in place so backup and
// restore progress shows up without a full page reload.
(function () {
  const list = document.getElementById("tasks-table");
  if (!list) return;

  async function refresh() {
    let tasks;
    try {
      const resp = await fetch("/api/tasks");
      if (!resp.ok) return;
      tasks = await resp.json();
    } catch (err) {
      return;
    }

    tasks.forEach((t) => {
      const card = list.querySelector(`[data-task-id="${t.id}"]`);
      if (!card) return;

      const statusCell = card.querySelector(".task-status");
      if (statusCell) {
        statusCell.innerHTML = `<span class="badge badge-${t.status}">${t.status}</span>`;
      }
      const stageBadge = card.querySelector(".badge-stage");
      if (stageBadge) stageBadge.textContent = t.stage || t.status;
      const messageCell = card.querySelector(".task-message");
      if (messageCell) {
        messageCell.textContent = t.message || "";
        messageCell.title = t.message || "";
      }

      const restoreForm = card.querySelector('form[action*="restore"]');
      if (restoreForm) {
        const enabled = t.status === "succeeded";
        restoreForm.querySelectorAll("button, select").forEach((el) => {
          el.disabled = !enabled;
        });
      }

      const deleteBtn = card.querySelector(".task-delete-form button");
      if (deleteBtn) {
        deleteBtn.disabled = t.status === "queued" || t.status === "running";
      }
    });
  }

  setInterval(refresh, 4000);
})();
