const form = document.getElementById("jobForm");
const startBtn = document.getElementById("startBtn");
const statusText = document.getElementById("statusText");
const jobIdPill = document.getElementById("jobId");
let pollTimer = null;

const statusLabels = {
  queued: "Queued",
  extracting_docs: "Extracting document text with OCR",
  analyzing_form: "Reading the form fields",
  mapping_fields: "Mapping fields to extracted data",
  filling_form: "Filling the form in the browser",
  done: "Done. Review the filled form.",
  error: "Error",
};

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearInterval(pollTimer);
  startBtn.disabled = true;
  statusText.textContent = "Uploading files...";

  try {
    const uploadId = await uploadFiles();
    const jobId = await createJob(uploadId);
    jobIdPill.textContent = `Job: ${jobId}`;
    await pollJob(jobId);
  } catch (error) {
    statusText.textContent = error.message || "Failed to start job.";
  } finally {
    startBtn.disabled = false;
  }
});

async function uploadFiles() {
  const formData = new FormData();
  const passport = document.getElementById("passport").files[0];
  const g28 = document.getElementById("g28").files[0];
  if (!passport || !g28) {
    throw new Error("Please select both PDF files.");
  }
  formData.append("passport", passport);
  formData.append("g28", g28);

  const response = await fetch("/api/uploads", { method: "POST", body: formData });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Upload failed: ${detail}`);
  }
  const data = await response.json();
  return data.upload_id;
}

async function createJob(uploadId) {
  const formUrl = document.getElementById("formUrl").value.trim();
  if (!formUrl) {
    throw new Error("Please enter the form URL.");
  }
  const response = await fetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ upload_id: uploadId, form_url: formUrl }),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Job start failed: ${detail}`);
  }
  const data = await response.json();
  return data.job_id;
}

async function pollJob(jobId) {
  statusText.textContent = "Starting...";
  pollTimer = setInterval(async () => {
    const response = await fetch(`/api/jobs/${jobId}`);
    if (!response.ok) {
      statusText.textContent = "Unable to fetch job status.";
      return;
    }
    const data = await response.json();
    renderStatus(data);
    if (data.status === "done" || data.status === "error") {
      clearInterval(pollTimer);
    }
  }, 2000);
}

function renderStatus(job) {
  statusText.textContent = statusLabels[job.status] || job.status;
  if (job.status === "error") {
    statusText.textContent = job.error || "Job failed.";
  }
  if (!job.result) {
    return;
  }
}
