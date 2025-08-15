// static/main.js
const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('fileInput');
const progressWrap = document.getElementById('progressWrap');
const progressBar = document.getElementById('progressBar');
const progressPct = document.getElementById('progressPct');
const progressLabel = document.getElementById('progressLabel');
const statusEl = document.getElementById('status');
const results = document.getElementById('results');

function setProgress(pct, label) {
  progressWrap.classList.remove('hidden');
  progressBar.style.width = pct + '%';
  progressPct.textContent = Math.round(pct) + '%';
  if (label) progressLabel.textContent = label;
}

function resetProgress() {
  progressBar.style.width = '0%';
  progressPct.textContent = '0%';
  progressLabel.textContent = 'Uploading…';
  if (statusEl) statusEl.textContent = '';
  progressWrap.classList.add('hidden');
}

dropzone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropzone.classList.add('dragover');
});
dropzone.addEventListener('dragleave', () => {
  dropzone.classList.remove('dragover');
});
dropzone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropzone.classList.remove('dragover');
  if (e.dataTransfer.files.length) {
    handleFile(e.dataTransfer.files[0]);
  }
});

fileInput.addEventListener('change', (e) => {
  if (e.target.files.length) {
    handleFile(e.target.files[0]);
  }
});

async function handleFile(file) {
  resetProgress();
  setProgress(5, 'Uploading…');

  const form = new FormData();
  form.append('file', file);
  try {
    const res = await uploadWithProgress('/api/upload', form, (pct) => {
      setProgress(Math.max(5, pct), pct < 100 ? 'Uploading…' : 'Processing… (this can take a bit)');
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Upload failed');

    setProgress(100, 'Done');
    if (statusEl) statusEl.textContent = 'Separated successfully.';
    renderResults(data);
  } catch (err) {
    console.error(err);
    if (statusEl) statusEl.textContent = 'Error: ' + err.message;
  }
}

function uploadWithProgress(url, formData, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);
    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress((e.loaded / e.total) * 100);
      }
    });
    xhr.onload = () => resolve(new Response(xhr.responseText, {status: xhr.status}));
    xhr.onerror = reject;
    xhr.send(formData);
  });
}

function card(title, src) {
  return `
  <div class="rounded-xl border border-gray-200 overflow-hidden shadow-sm">
    <div class="px-4 py-3 flex items-center justify-between bg-gray-50">
      <span class="font-medium">${title}</span>
      <a href="${src}" download class="text-sm underline text-gray-600 hover:text-black">Download</a>
    </div>
    <div class="p-4">
      <audio controls src="${src}" class="w-full"></audio>
    </div>
  </div>`;
}

function renderResults(data) {
  const baseCards = `
    ${card('Original', data.original)}
    ${card('Vocals Only', data.vocals)}
    ${card('Instrumental (Background Only)', data.instrumental)}
  `;

  const advanced = `
    <details class="rounded-xl border border-gray-200 overflow-hidden shadow-sm">
      <summary class="px-4 py-3 bg-gray-50 cursor-pointer font-medium flex items-center justify-between">
        <span>Advanced stems</span>
        <span class="text-xs text-gray-500">Drums, Bass, Other</span>
      </summary>
      <div class="p-4 space-y-4">
        ${card('Drums', data.drums)}
        ${card('Bass', data.bass)}
        ${card('Other', data.other)}
      </div>
    </details>
  `;

  results.innerHTML = baseCards + advanced;
}
