// Minimal progressive enhancement — no framework. See docs/32_Web_Dashboard.md "Design".

document.addEventListener("DOMContentLoaded", () => {
  // Job progress polling: any element with [data-job-poll-url] refreshes
  // itself from the JSON API until the job reaches a terminal state.
  document.querySelectorAll("[data-job-poll-url]").forEach((el) => pollJob(el));

  // Confirm before any destructive/irreversible POST (cancel, reject, reset).
  document.querySelectorAll("[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.getAttribute("data-confirm"))) {
        event.preventDefault();
      }
    });
  });
});

function pollJob(el) {
  const url = el.getAttribute("data-job-poll-url");
  const terminal = new Set(["completed", "partial", "failed", "cancelled"]);

  const tick = () => {
    fetch(url, { headers: { Accept: "application/json" } })
      .then((response) => response.json())
      .then((data) => {
        const job = data.job || data;
        const statusEl = el.querySelector("[data-job-status]");
        const stageEl = el.querySelector("[data-job-stage]");
        const progressEl = el.querySelector("[data-job-progress]");
        if (statusEl) statusEl.textContent = job.status;
        if (stageEl) stageEl.textContent = job.current_stage || "";
        if (progressEl) progressEl.value = Math.round((job.progress || 0) * 100);

        if (terminal.has(job.status)) {
          const redirectUrl = el.getAttribute("data-job-done-redirect");
          if (redirectUrl && (job.status === "completed" || job.status === "partial")) {
            window.location.href = redirectUrl.replace("__RESULT__", job.result_reference || "");
          } else {
            el.setAttribute("data-job-final-status", job.status);
          }
          return;
        }
        setTimeout(tick, 2000);
      })
      .catch(() => setTimeout(tick, 4000));
  };
  tick();
}
