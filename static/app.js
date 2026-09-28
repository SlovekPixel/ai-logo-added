(() => {
  const sampleInput = document.getElementById("sample-input");
  const sampleInfo = document.getElementById("sample-info");
  const samplePreview = document.getElementById("sample-preview");
  const folderInput = document.getElementById("folder-input");
  const stage = document.getElementById("stage");
  const logoPreview = document.getElementById("logo-preview");
  const generateBtn = document.getElementById("generate-btn");
  const folderInfo = document.getElementById("folder-info");
  const posStatus = document.getElementById("pos-status");
  const progressWrap = document.getElementById("progress-wrap");
  const progressFill = document.getElementById("progress-fill");
  const progressText = document.getElementById("progress-text");
  const resultWrap = document.getElementById("result-wrap");
  const downloadLink = document.getElementById("download-link");
  const errorBox = document.getElementById("error-box");
  const logoutBtn = document.getElementById("logout-btn");
  const useDefaults = document.getElementById("use-defaults");

  const IMAGE_EXT = /\.(jpe?g|png|webp)$/i;
  const DEFAULT_LOGO_URL = "/static/default/logo_exp.svg";
  const DEFAULT_SAMPLE_URL = "/static/default/photo_exp.png";

  // Loaded from /api/logo-layout (app/images.py) — edit REF_* only on the server.
  let REF_PHOTO_H = 1200;
  let REF_LOGO_W = 484;
  let REF_LOGO_H = 415.38;
  let REF_TOP = 24;
  let REF_LEFT = 574.26;
  let SVG_PILL_X = 87.3281;

  let logoReady = false;
  let sampleLoaded = false;
  let sampleW = 0;
  let sampleH = 0;
  let sampleUrl = null;
  let photoFiles = [];

  function showError(msg) {
    if (!msg) {
      errorBox.classList.add("hidden");
      errorBox.textContent = "";
      return;
    }
    errorBox.textContent = msg;
    errorBox.classList.remove("hidden");
  }

  function logoLayoutForHeight(photoH) {
    const h = Math.max(1, photoH || REF_PHOTO_H);
    const scale = h / REF_PHOTO_H;
    return {
      width: Math.max(1, Math.round(REF_LOGO_W * scale)),
      height: Math.max(1, Math.round(REF_LOGO_H * scale)),
      top: Math.max(0, Math.round(REF_TOP * scale)),
      left: Math.round((REF_LEFT - SVG_PILL_X) * scale),
    };
  }

  function applyLogoTransform() {
    if (!logoReady) {
      logoPreview.classList.add("hidden");
      return;
    }
    const layout = logoLayoutForHeight(sampleLoaded ? sampleH : REF_PHOTO_H);
    logoPreview.style.width = `${layout.width}px`;
    logoPreview.style.height = `${layout.height}px`;
    logoPreview.style.left = `${layout.left}px`;
    logoPreview.style.right = "auto";
    logoPreview.style.top = `${layout.top}px`;
    logoPreview.classList.remove("hidden");
  }

  function refreshGenerateEnabled() {
    generateBtn.disabled = !(logoReady && photoFiles.length > 0);
  }

  function updatePosStatus() {
    if (!sampleLoaded) {
      posStatus.textContent = "Загрузите пример фото.";
      return;
    }
    const layout = logoLayoutForHeight(sampleH);
    posStatus.textContent =
      `Авто: ${layout.width}×${layout.height}px, сверху ${layout.top}px, ` +
      `лого слева ${Math.round(REF_LEFT * (sampleH / REF_PHOTO_H))}px ` +
      `(от высоты ${sampleH}px)`;
  }

  function sizeStageToSample() {
    if (!sampleLoaded) {
      stage.classList.add("stage-empty");
      stage.classList.remove("has-sample");
      stage.style.width = "";
      stage.style.height = "";
      return;
    }
    stage.classList.remove("stage-empty");
    stage.classList.add("has-sample");
    stage.style.width = `${sampleW}px`;
    stage.style.height = `${sampleH}px`;
  }

  function loadDefaultLogo() {
    return new Promise((resolve, reject) => {
      logoPreview.onload = () => {
        logoReady = true;
        applyLogoTransform();
        updatePosStatus();
        refreshGenerateEnabled();
        resolve();
      };
      logoPreview.onerror = () => {
        logoReady = false;
        logoPreview.classList.add("hidden");
        updatePosStatus();
        refreshGenerateEnabled();
        reject(new Error("Не удалось загрузить дефолтный логотип"));
      };
      logoPreview.src = DEFAULT_LOGO_URL;
    });
  }

  function applySampleFile(file) {
    return new Promise((resolve, reject) => {
      if (sampleUrl) URL.revokeObjectURL(sampleUrl);
      sampleUrl = URL.createObjectURL(file);
      samplePreview.onload = () => {
        sampleW = samplePreview.naturalWidth;
        sampleH = samplePreview.naturalHeight;
        sampleLoaded = true;
        sampleInfo.textContent = `Пример: ${sampleW}×${sampleH} px (превью 1:1)`;
        samplePreview.classList.remove("hidden");
        sizeStageToSample();
        applyLogoTransform();
        updatePosStatus();
        resolve();
      };
      samplePreview.onerror = () => {
        sampleLoaded = false;
        samplePreview.classList.add("hidden");
        sampleInfo.textContent = "Пример не загружен";
        updatePosStatus();
        reject(new Error("Не удалось загрузить пример фото"));
      };
      samplePreview.src = sampleUrl;
    });
  }

  async function fetchAsFile(url, filename, mime) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Не удалось загрузить ${filename}`);
    const blob = await res.blob();
    return new File([blob], filename, { type: mime || blob.type || "application/octet-stream" });
  }

  async function loadDefaultSample() {
    showError("");
    const sample = await fetchAsFile(DEFAULT_SAMPLE_URL, "photo_exp.png", "image/png");
    await applySampleFile(sample);
  }

  sampleInput.addEventListener("change", async () => {
    const file = sampleInput.files && sampleInput.files[0];
    if (!file) return;
    useDefaults.checked = false;
    showError("");
    try {
      await applySampleFile(file);
    } catch (err) {
      showError(err.message || String(err));
    }
  });

  useDefaults.addEventListener("change", async () => {
    if (!useDefaults.checked) return;
    useDefaults.disabled = true;
    try {
      await loadDefaultSample();
      sampleInput.value = "";
    } catch (err) {
      useDefaults.checked = false;
      showError(err.message || String(err));
    } finally {
      useDefaults.disabled = false;
    }
  });

  folderInput.addEventListener("change", () => {
    const all = Array.from(folderInput.files || []);
    photoFiles = all.filter((f) => IMAGE_EXT.test(f.name));
    const skipped = all.length - photoFiles.length;
    if (!photoFiles.length) {
      folderInfo.textContent = "В папке нет подходящих изображений (JPG/PNG/WEBP)";
    } else {
      let msg = `Выбрано фото: ${photoFiles.length}`;
      if (skipped > 0) msg += ` (пропущено не-картинок: ${skipped})`;
      folderInfo.textContent = msg;
    }
    refreshGenerateEnabled();
  });

  logoutBtn.addEventListener("click", async () => {
    await fetch("/api/logout", { method: "POST" });
    window.location.href = "/";
  });

  function setProgress(done, total, text) {
    progressWrap.classList.remove("hidden");
    const pct = total > 0 ? Math.round((done / total) * 100) : 0;
    progressFill.style.width = `${pct}%`;
    progressText.textContent = text || `${done} / ${total}`;
  }

  async function pollJob(jobId) {
    while (true) {
      const res = await fetch(`/api/jobs/${jobId}`);
      if (!res.ok) throw new Error("Не удалось получить статус задачи");
      const data = await res.json();
      if (data.status === "running" || data.status === "queued") {
        setProgress(data.done, data.total, data.message);
        await new Promise((r) => setTimeout(r, 500));
        continue;
      }
      if (data.status === "done") {
        setProgress(data.total, data.total, "Готово");
        downloadLink.href = `/api/jobs/${jobId}/download`;
        resultWrap.classList.remove("hidden");
        return;
      }
      throw new Error(data.error || data.message || "Ошибка генерации");
    }
  }

  generateBtn.addEventListener("click", async () => {
    if (!logoReady || !photoFiles.length) return;
    showError("");
    resultWrap.classList.add("hidden");
    generateBtn.disabled = true;
    setProgress(0, photoFiles.length, "Загрузка…");

    const form = new FormData();
    for (const f of photoFiles) {
      form.append("photos", f, f.name);
    }

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/generate");
    xhr.upload.onprogress = (e) => {
      if (!e.lengthComputable) return;
      const pct = Math.round((e.loaded / e.total) * 100);
      progressFill.style.width = `${Math.min(pct, 99)}%`;
      progressText.textContent = `Загрузка файлов: ${pct}%`;
    };
    xhr.onload = async () => {
      try {
        let data;
        try {
          data = JSON.parse(xhr.responseText);
        } catch {
          throw new Error("Некорректный ответ сервера");
        }
        if (xhr.status === 409 || data.busy) {
          throw new Error(data.message || "Сервер занят");
        }
        if (!xhr.status || xhr.status >= 400 || !data.ok) {
          const detail = data.detail;
          const detailMsg = Array.isArray(detail)
            ? detail.map((d) => d.msg || JSON.stringify(d)).join("; ")
            : detail;
          throw new Error(detailMsg || data.message || `Ошибка ${xhr.status}`);
        }
        setProgress(0, photoFiles.length, "Обработка…");
        await pollJob(data.job_id);
      } catch (err) {
        showError(err.message || String(err));
        progressWrap.classList.add("hidden");
      } finally {
        refreshGenerateEnabled();
      }
    };
    xhr.onerror = () => {
      showError("Ошибка сети при загрузке");
      progressWrap.classList.add("hidden");
      refreshGenerateEnabled();
    };
    xhr.send(form);
  });

  async function loadLogoLayout() {
    const res = await fetch("/api/logo-layout");
    if (!res.ok) throw new Error("Не удалось загрузить параметры логотипа");
    const data = await res.json();
    REF_PHOTO_H = Number(data.refPhotoH) || REF_PHOTO_H;
    REF_LOGO_W = Number(data.refLogoW) || REF_LOGO_W;
    REF_LOGO_H = Number(data.refLogoH) || REF_LOGO_H;
    REF_TOP = Number(data.refTop) || REF_TOP;
    REF_LEFT = Number(data.refLeft) || REF_LEFT;
    SVG_PILL_X = Number(data.svgPillX) || SVG_PILL_X;
  }

  loadLogoLayout()
    .then(() => loadDefaultLogo())
    .then(() => {
      applyLogoTransform();
      updatePosStatus();
    })
    .catch((err) => showError(err.message || String(err)));
  refreshGenerateEnabled();
})();
