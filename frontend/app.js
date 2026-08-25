// API Base URL (runs on the same port)
const API_URL = "";

// --- Clipboard Copy Helper ---
window.copyValue = function(text, buttonEl) {
    navigator.clipboard.writeText(text).then(() => {
        const icon = buttonEl.querySelector("i");
        const originalClass = icon.className;
        
        // Show checkmark
        icon.className = "fa-solid fa-circle-check";
        buttonEl.classList.add("copied");
        
        // Show small toast
        showToast("Đã copy: " + text, "success");
        
        // Auto-check the row copy state
        const tr = buttonEl.closest("tr");
        if (tr) {
            const trk = tr.getAttribute("data-tracking");
            if (trk) {
                // If it is a 12-digit number (tracking number), also tell backend it's the active one
                if (/^\d{11,12}$/.test(text)) {
                    fetch(`${API_URL}/api/active-tracking`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ trackingNumber: trk })
                    }).catch(e => console.error(e));
                }
                
                // Update copied status
                updateCopiedStatus(trk, true);
            }
        }
        
        setTimeout(() => {
            icon.className = originalClass;
            buttonEl.classList.remove("copied");
        }, 1500);
    }).catch(err => {
        console.error("Lỗi copy:", err);
    });
};

// Global function to update copied status both locally and on backend
window.updateCopiedStatus = function(trackingNumber, isCopied) {
    // 1. Update local state
    const pkg = packages.find(p => p.trackingNumber === trackingNumber);
    if (pkg) {
        pkg.copied = isCopied;
    }
    
    // 2. Update UI rows matching this tracking number
    document.querySelectorAll(`tr[data-tracking="${trackingNumber}"]`).forEach(tr => {
        const checkbox = tr.querySelector(".row-checkbox");
        if (checkbox) checkbox.checked = isCopied;
        
        if (isCopied) {
            tr.classList.add("row-copied");
        } else {
            tr.classList.remove("row-copied");
        }
    });
    
    // 3. Persist to backend
    fetch(`${API_URL}/api/update-copied`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ trackingNumber, copied: isCopied })
    }).catch(e => console.error("Lỗi cập nhật trạng thái copy:", e));
};

// State
let packages = [];
let connectionStatus = { browser: "disconnected", zalo: "disconnected", jms: "disconnected" };
let isProcessing = false;
let currentPage = 1;
let pageSize = 50;

// DOM Elements
const elConsoleLogs = document.getElementById("console-logs");
const elStatusBrowser = document.getElementById("status-browser");
const elStatusZalo = document.getElementById("status-zalo");
const elStatusJms = document.getElementById("status-jms");
const elBtnLaunchPopup = document.getElementById("btn-launch-popup");
const elBtnStartBrowser = document.getElementById("btn-start-browser");
const elBtnCloseBrowser = document.getElementById("btn-close-browser");
const elBtnScanZalo = document.getElementById("btn-scan-zalo");
const elBtnScanDownload5in1 = document.getElementById("btn-scan-download-5in1");
const elBtnStopScan = document.getElementById("btn-stop-scan");
const elBtnScrollZalo = document.getElementById("btn-scroll-zalo");
const elScrollTimes = document.getElementById("scroll-times");
const elBtnDownloadAll = document.getElementById("btn-download-all");
const elBtnOpenFolder = document.getElementById("btn-open-folder");
const elBtnUploadAll = document.getElementById("btn-upload-all");
const elBtnClearLogs = document.getElementById("btn-clear-logs");
const elScannedCount = document.getElementById("scanned-count");
const elTableSummary = document.getElementById("table-summary").querySelector("tbody");
const elTablePackagesAll = document.getElementById("table-packages-all").querySelector("tbody");
const elSearchPkg = document.getElementById("search-pkg");
const elPageSize = document.getElementById("page-size");
const elTotalCount = document.getElementById("total-count");
const elBtnPrevPage = document.getElementById("btn-prev-page");
const elBtnNextPage = document.getElementById("btn-next-page");
const elPageInfo = document.getElementById("page-info");

// Settings Elements
const elSettingsForm = document.getElementById("settings-form");
const elBtnResetSettings = document.getElementById("btn-reset-settings");

// --- Helper: Console Logging ---
function log(message, type = "info") {
    const timestamp = new Date().toLocaleTimeString();
    const logLine = document.createElement("div");
    logLine.className = `log-line ${type}`;
    logLine.innerHTML = `[${timestamp}] ${message}`;
    elConsoleLogs.appendChild(logLine);
    elConsoleLogs.scrollTop = elConsoleLogs.scrollHeight;
}

// --- Helper: Toast Notification ---
function showToast(message, type = "success") {
    const toast = document.getElementById("toast");
    const icon = toast.querySelector(".toast-icon");
    const msg = toast.querySelector(".toast-message");
    
    msg.textContent = message;
    if (type === "success") {
        icon.className = "fa-solid fa-circle-check toast-icon";
        toast.style.borderColor = "rgba(85, 239, 196, 0.3)";
    } else {
        icon.className = "fa-solid fa-circle-exclamation toast-icon";
        toast.style.borderColor = "rgba(255, 118, 117, 0.3)";
    }
    
    toast.classList.add("show");
    setTimeout(() => {
        toast.classList.remove("show");
    }, 3000);
}

// --- Tab Navigation ---
document.querySelectorAll(".nav-item").forEach(item => {
    item.addEventListener("click", (e) => {
        e.preventDefault();
        document.querySelectorAll(".nav-item").forEach(i => i.classList.remove("active"));
        document.querySelectorAll(".tab-content").forEach(c => c.classList.add("hidden"));
        
        item.classList.add("active");
        const tab = item.getAttribute("data-tab");
        document.getElementById(`tab-${tab}`).classList.remove("hidden");
        
        // Update header title
        document.getElementById("page-title").textContent = item.textContent.trim();
        
        if (tab === "packages") {
            renderPackagesTableAll();
        }
    });
});

// --- API: Get System Status ---
let lastLoggedProgress = "";
async function fetchStatus() {
    try {
        const response = await fetch(`${API_URL}/api/status`);
        if (!response.ok) throw new Error("Network status error");
        connectionStatus = await response.json();
        updateStatusUI();
        
        // Log progress updates if they change
        if (connectionStatus.progress && connectionStatus.progress !== lastLoggedProgress) {
            lastLoggedProgress = connectionStatus.progress;
            log(connectionStatus.progress, "info");
        }
    } catch (e) {
        console.error("Lỗi lấy trạng thái:", e);
    }
}

function updateStatusUI() {
    // Browser Status
    if (connectionStatus.browser === "connected") {
        elStatusBrowser.className = "status-dot connected";
        elBtnStartBrowser.classList.add("hidden");
        elBtnCloseBrowser.classList.remove("hidden");
    } else {
        elStatusBrowser.className = "status-dot disconnected";
        elBtnStartBrowser.classList.remove("hidden");
        elBtnCloseBrowser.classList.add("hidden");
    }
    
    // Zalo Status
    elStatusZalo.className = connectionStatus.zalo === "connected" ? "status-dot connected" : "status-dot disconnected";
    
    // JMS Status
    elStatusJms.className = connectionStatus.jms === "connected" ? "status-dot connected" : "status-dot disconnected";
}

// --- API: Start Browser ---
elBtnStartBrowser.addEventListener("click", async () => {
    log("Đang khởi động trình duyệt Chrome điều khiển...", "system");
    elBtnStartBrowser.disabled = true;
    try {
        const response = await fetch(`${API_URL}/api/start-browser`, { method: "POST" });
        const data = await response.json();
        if (data.status === "success") {
            log("Đã khởi động trình duyệt thành công!", "success");
            showToast("Đã khởi động trình duyệt!");
            await fetchStatus();
        } else {
            log(`Lỗi khởi động trình duyệt: ${data.message}`, "error");
        }
    } catch (e) {
        log(`Không thể kết nối đến backend server: ${e.message}`, "error");
    } finally {
        elBtnStartBrowser.disabled = false;
    }
});
// --- API: Launch Desktop Popup Tool ---
elBtnLaunchPopup.addEventListener("click", async () => {
    log("Đang khởi động công cụ Desktop Popup (Python)...", "system");
    try {
        const response = await fetch(`${API_URL}/api/launch-popup`, { method: "POST" });
        const data = await response.json();
        if (data.status === "success") {
            log("Đã mở công cụ Desktop Popup thành công!", "success");
            showToast("Đã mở Popup Desktop!");
        } else {
            log(`Lỗi khởi động popup: ${data.message}`, "error");
            showToast("Lỗi mở Popup!", "danger");
        }
    } catch (e) {
        log(`Lỗi kết nối server: ${e.message}`, "error");
    }
});
// --- API: Close Browser ---
elBtnCloseBrowser.addEventListener("click", async () => {
    log("Đang đóng trình duyệt...", "system");
    try {
        const response = await fetch(`${API_URL}/api/close-browser`, { method: "POST" });
        const data = await response.json();
        if (data.status === "success") {
            log("Đã đóng trình duyệt thành công.", "success");
            showToast("Đã đóng trình duyệt!");
            await fetchStatus();
        }
    } catch (e) {
        log(`Lỗi khi đóng trình duyệt: ${e.message}`, "error");
    }
});

// --- API: Scan Zalo ---
elBtnScanZalo.addEventListener("click", async () => {
    if (connectionStatus.zalo !== "connected") {
        log("Lỗi: Chưa kết nối hoặc chưa mở tab Zalo Web! Vui lòng mở Chrome điều khiển và đăng nhập Zalo.", "error");
        showToast("Chưa mở Zalo Web!", "danger");
        return;
    }
    
    log("Đang quét tin nhắn và ảnh/video từ Zalo chat...", "info");
    elBtnScanZalo.disabled = true;
    
    try {
        const direction = document.getElementById("scan-direction").value;
        const startTracking = document.getElementById("scan-start-tracking").value.trim() || null;
        const response = await fetch(`${API_URL}/api/scan-zalo`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ direction, startTracking })
        });
        const data = await response.json();
        
        if (data.status === "success") {
            packages = data.packages.map(p => ({
                ...p,
                localStatus: p.localStatus || "Chưa tải về",
                jmsStatus: p.jmsStatus || "Chưa xử lý",
                copied: p.copied || false
            }));
            
            log(`Quét thành công! Tìm thấy ${packages.length} mã đơn kèm ảnh & video.`, "success");
            showToast(`Quét thành công ${packages.length} đơn!`);
            
            elScannedCount.textContent = `${packages.length} đơn hàng`;
            renderSummaryTable();
        } else {
            log(`Lỗi quét Zalo: ${data.message}`, "error");
        }
    } catch (e) {
        log(`Lỗi kết nối server khi quét: ${e.message}`, "error");
    } finally {
        elBtnScanZalo.disabled = false;
    }
});

// --- API: Scroll Zalo Chat to Load History ---
elBtnScrollZalo.addEventListener("click", async () => {
    if (connectionStatus.zalo !== "connected") {
        log("Lỗi: Chưa kết nối hoặc chưa mở tab Zalo Web! Vui lòng mở Chrome điều khiển và đăng nhập Zalo.", "error");
        showToast("Chưa mở Zalo Web!", "danger");
        return;
    }
    
    const times = parseInt(elScrollTimes.value) || 15;
    log(`Đang tự động cuộn lên ${times} lần để tải tin nhắn cũ trên Zalo...`, "info");
    elBtnScrollZalo.disabled = true;
    
    try {
        const response = await fetch(`${API_URL}/api/scroll-zalo`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ times })
        });
        const data = await response.json();
        if (data.status === "success") {
            log(`Đã cuộn xong ${times} lần! Bây giờ bạn hãy bấm nút "Đồng bộ tin nhắn Zalo".`, "success");
            showToast("Cuộn tải hoàn tất!");
        } else {
            log(`Lỗi cuộn trang: ${data.message}`, "error");
        }
    } catch (e) {
        log(`Lỗi kết nối khi cuộn: ${e.message}`, "error");
    } finally {
        elBtnScrollZalo.disabled = false;
    }
});

// --- API: Scan & Download Zalo 5-in-1 ---
if (elBtnScanDownload5in1) {
    elBtnScanDownload5in1.addEventListener("click", async () => {
        if (connectionStatus.zalo !== "connected") {
            log("Lỗi: Chưa kết nối hoặc chưa mở tab Zalo Web! Vui lòng mở Chrome điều khiển và đăng nhập Zalo.", "error");
            showToast("Chưa mở Zalo Web!", "danger");
            return;
        }
        
        log("Bắt đầu quét & tải tự động (5-in-1)...", "info");
        elBtnScanDownload5in1.disabled = true;
        
        try {
            const direction = document.getElementById("scan-direction").value;
            const startTracking = document.getElementById("scan-start-tracking").value.trim() || null;
            const response = await fetch(`${API_URL}/api/scan-download-5in1`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ direction, startTracking })
            });
            const data = await response.json();
            
            if (data.status === "success") {
                log("Hoàn thành quy trình quét & tải tự động (5-in-1)!", "success");
                showToast("Quá trình 5-in-1 hoàn tất!");
                await loadPackages();
            } else {
                log(`Lỗi 5-in-1: ${data.message}`, "error");
            }
        } catch (e) {
            log(`Lỗi kết nối server khi chạy 5-in-1: ${e.message}`, "error");
        } finally {
            elBtnScanDownload5in1.disabled = false;
        }
    });
}

// --- API: Stop Zalo Scan ---
if (elBtnStopScan) {
    elBtnStopScan.addEventListener("click", async () => {
        log("Đang gửi yêu cầu dừng quét khẩn cấp...", "warning");
        elBtnStopScan.disabled = true;
        try {
            const response = await fetch(`${API_URL}/api/stop-scan`, { method: "POST" });
            const data = await response.json();
            if (data.status === "success") {
                log("Đã kích hoạt dừng quét. Tiến trình sẽ dừng ở đơn hàng tiếp theo.", "success");
                showToast("Đã kích hoạt dừng!");
            } else {
                log(`Lỗi khi dừng quét: ${data.message}`, "error");
            }
        } catch (e) {
            log(`Lỗi kết nối khi dừng quét: ${e.message}`, "error");
        } finally {
            elBtnStopScan.disabled = false;
        }
    });
}


// --- Advanced Custom Scan Actions (TH1 & TH2) ---
const elCustomScanTrackingDown = document.getElementById("custom-scan-tracking-down");
const elCustomScanTrackingUp = document.getElementById("custom-scan-tracking-up");
const elBtnCustomScanDown = document.getElementById("btn-custom-scan-down");
const elBtnCustomScanUp = document.getElementById("btn-custom-scan-up");

async function runCustomScan(direction) {
    if (connectionStatus.zalo !== "connected") {
        log("Lỗi: Chưa kết nối hoặc chưa mở tab Zalo Web! Vui lòng mở Chrome điều khiển và đăng nhập Zalo.", "error");
        showToast("Chưa mở Zalo Web!", "danger");
        return;
    }
    
    const inputEl = direction === "down" ? elCustomScanTrackingDown : elCustomScanTrackingUp;
    const tracking = inputEl ? inputEl.value.trim() : "";
    if (!/^\d{11,12}$/.test(tracking)) {
        log("Lỗi: Vui lòng nhập mã vận đơn mốc hợp lệ (11 hoặc 12 chữ số)!", "warning");
        showToast("Mã vận đơn không hợp lệ!", "danger");
        return;
    }
    
    log(`Đang khởi chạy quét mốc ${direction === "down" ? "xuôi (TH1)" : "ngược (TH2)"} bắt đầu từ mã ${tracking}...`, "info");
    
    if (elBtnCustomScanDown) elBtnCustomScanDown.disabled = true;
    if (elBtnCustomScanUp) elBtnCustomScanUp.disabled = true;
    
    try {
        const endpoint = direction === "down" ? "/api/scan-th1" : "/api/scan-th2";
        const response = await fetch(`${API_URL}${endpoint}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ startTracking: tracking })
        });
        const data = await response.json();
        
        if (data.status === "success") {
            log(`Chạy quy trình quét mốc ${direction === "down" ? "xuôi (TH1)" : "ngược (TH2)"} thành công!`, "success");
            showToast(`Quét và tải mốc thành công!`);
            await loadPackages();
        } else {
            log(`Lỗi quét mốc: ${data.message}`, "error");
        }
    } catch (e) {
        log(`Lỗi kết nối server khi quét mốc: ${e.message}`, "error");
    } finally {
        if (elBtnCustomScanDown) elBtnCustomScanDown.disabled = false;
        if (elBtnCustomScanUp) elBtnCustomScanUp.disabled = false;
    }
}

if (elBtnCustomScanDown) {
    elBtnCustomScanDown.addEventListener("click", () => runCustomScan("down"));
}
if (elBtnCustomScanUp) {
    elBtnCustomScanUp.addEventListener("click", () => runCustomScan("up"));
}

// --- Render: Summary Table ---
function renderSummaryTable() {
    if (packages.length === 0) {
        elTableSummary.innerHTML = `
            <tr class="empty-row">
                <td colspan="8">Chưa có đơn hàng nào được quét. Vui lòng bấm "Đồng bộ tin nhắn Zalo".</td>
            </tr>`;
        return;
    }
    
    elTableSummary.innerHTML = "";
    
    packages.slice(0, 10).forEach(pkg => {
        const tr = document.createElement("tr");
        tr.setAttribute("data-tracking", pkg.trackingNumber);
        if (pkg.copied) {
            tr.classList.add("row-copied");
        }
        
        // Media Preview rendering
        let mediaHtml = '<div class="media-previews">';
        // Show video icon if contains video
        if (pkg.videos && pkg.videos.length > 0) {
            mediaHtml += `<div class="video-thumb-container" title="Có video"><i class="fa-solid fa-play"></i></div>`;
        }
        // Show image thumbnails (up to 3)
        if (pkg.images) {
            pkg.images.slice(0, 3).forEach(img => {
                mediaHtml += `<img src="${img}" class="media-thumb" onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2240%22 height=%2240%22><rect width=%2240%22 height=%2240%22 fill=%22%232c3e50%22/></svg>'">`;
            });
        }
        mediaHtml += '</div>';
        
        // Local state class
        let localClass = "pending";
        if (pkg.localStatus === "Đã tải về") localClass = "success";
        if (pkg.localStatus.includes("Lỗi")) localClass = "danger";
        
        // JMS state class
        let jmsClass = "pending";
        if (pkg.jmsStatus === "Thành công") jmsClass = "success";
        if (pkg.jmsStatus.includes("Thất bại") || pkg.jmsStatus.includes("Lỗi")) jmsClass = "danger";

        tr.innerHTML = `
            <td style="text-align: center;">
                <label class="checkbox-container">
                    <input type="checkbox" class="row-checkbox" ${pkg.copied ? 'checked' : ''} onchange="updateCopiedStatus('${pkg.trackingNumber}', this.checked)">
                    <span class="checkmark"></span>
                </label>
            </td>
            <td><span class="folder-stt-badge">${pkg.folderName || ''}</span></td>
            <td>
                <div class="copyable-field">
                    <strong>${pkg.trackingNumber}</strong>
                    <button class="btn-copy-small" onclick="copyValue('${pkg.trackingNumber}', this)" title="Copy mã vận đơn">
                        <i class="fa-regular fa-copy"></i>
                    </button>
                </div>
            </td>
            <td>
                <div class="copyable-field">
                    <span>${pkg.weight !== null ? pkg.weight + ' kg' : '<span style="color:gray">0</span>'}</span>
                    <button class="btn-copy-small" onclick="copyValue('${pkg.weight !== null ? pkg.weight : '0'}', this)" title="Copy cân nặng">
                        <i class="fa-regular fa-copy"></i>
                    </button>
                </div>
            </td>
            <td>${mediaHtml}</td>
            <td><span class="status-pill ${localClass}">${pkg.localStatus}</span></td>
            <td><span class="status-pill ${jmsClass}">${pkg.jmsStatus}</span></td>
            <td>
                <button class="action-row-btn download" onclick="downloadSingle('${pkg.trackingNumber}')" title="Tải về máy">
                    <i class="fa-solid fa-download"></i>
                </button>
                <button class="action-row-btn play" onclick="uploadSingle('${pkg.trackingNumber}')" title="Auto JMS">
                    <i class="fa-solid fa-play"></i>
                </button>
            </td>
        `;
        elTableSummary.appendChild(tr);
    });
}

// --- Render: Full Packages Table ---
function renderPackagesTableAll() {
    const filterText = elSearchPkg.value.toLowerCase().trim();
    const filtered = packages.filter(p => p.trackingNumber.includes(filterText));
    
    const totalFiltered = filtered.length;
    elTotalCount.textContent = totalFiltered;
    
    const totalPages = Math.ceil(totalFiltered / pageSize) || 1;
    if (currentPage > totalPages) currentPage = totalPages;
    if (currentPage < 1) currentPage = 1;
    
    elPageInfo.textContent = `Trang ${currentPage} / ${totalPages}`;
    elBtnPrevPage.disabled = currentPage <= 1;
    elBtnNextPage.disabled = currentPage >= totalPages;
    
    if (totalFiltered === 0) {
        elTablePackagesAll.innerHTML = `
            <tr class="empty-row">
                <td colspan="9">Không tìm thấy đơn hàng nào.</td>
            </tr>`;
        return;
    }
    
    elTablePackagesAll.innerHTML = "";
    
    // Slice data for the current page
    const pageData = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize);
    
    pageData.forEach(pkg => {
        const tr = document.createElement("tr");
        tr.setAttribute("data-tracking", pkg.trackingNumber);
        if (pkg.copied) {
            tr.classList.add("row-copied");
        }
        
        // Images preview
        let imgsHtml = '<div class="media-previews">';
        pkg.images.forEach(img => {
            imgsHtml += `<img src="${img}" class="media-thumb" onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2240%22 height=%2240%22><rect width=%2240%22 height=%2240%22 fill=%22%232c3e50%22/></svg>'">`;
        });
        imgsHtml += '</div>';
        
        // Videos preview
        let vidsHtml = pkg.videos && pkg.videos.length > 0 
            ? `<span class="badge" style="background: rgba(9, 132, 227, 0.2); color:#74b9ff">${pkg.videos.length} video</span>` 
            : '<span style="color:gray">Không có</span>';
            
        let localClass = pkg.localStatus === "Đã tải về" ? "success" : (pkg.localStatus.includes("Lỗi") ? "danger" : "pending");
        let jmsClass = pkg.jmsStatus === "Thành công" ? "success" : (pkg.jmsStatus.includes("Thất bại") ? "danger" : "pending");

        tr.innerHTML = `
            <td style="text-align: center;">
                <label class="checkbox-container">
                    <input type="checkbox" class="row-checkbox" ${pkg.copied ? 'checked' : ''} onchange="updateCopiedStatus('${pkg.trackingNumber}', this.checked)">
                    <span class="checkmark"></span>
                </label>
            </td>
            <td><span class="folder-stt-badge">${pkg.folderName || ''}</span></td>
            <td>
                <div class="copyable-field">
                    <strong>${pkg.trackingNumber}</strong>
                    <button class="btn-copy-small" onclick="copyValue('${pkg.trackingNumber}', this)" title="Copy mã vận đơn">
                        <i class="fa-regular fa-copy"></i>
                    </button>
                </div>
            </td>
            <td>
                <div class="copyable-field">
                    <span>${pkg.weight !== null ? pkg.weight + ' kg' : '<span style="color:gray">0</span>'}</span>
                    <button class="btn-copy-small" onclick="copyValue('${pkg.weight !== null ? pkg.weight : '0'}', this)" title="Copy cân nặng">
                        <i class="fa-regular fa-copy"></i>
                    </button>
                </div>
            </td>
            <td>${imgsHtml}</td>
            <td>${vidsHtml}</td>
            <td><span class="status-pill ${localClass}">${pkg.localStatus}</span></td>
            <td><span class="status-pill ${jmsClass}">${pkg.jmsStatus}</span></td>
            <td>
                <button class="btn btn-outline" style="padding: 6px 12px; font-size:12px" onclick="processAllForSingle('${pkg.trackingNumber}')">
                    Xử lý đơn này
                </button>
            </td>
        `;
        elTablePackagesAll.appendChild(tr);
    });
}

elSearchPkg.addEventListener("input", () => {
    currentPage = 1;
    renderPackagesTableAll();
});

elPageSize.addEventListener("change", () => {
    pageSize = parseInt(elPageSize.value) || 50;
    currentPage = 1;
    renderPackagesTableAll();
});

elBtnPrevPage.addEventListener("click", () => {
    if (currentPage > 1) {
        currentPage--;
        renderPackagesTableAll();
    }
});

elBtnNextPage.addEventListener("click", () => {
    const filterText = elSearchPkg.value.toLowerCase().trim();
    const filtered = packages.filter(p => p.trackingNumber.includes(filterText));
    const totalPages = Math.ceil(filtered.length / pageSize) || 1;
    if (currentPage < totalPages) {
        currentPage++;
        renderPackagesTableAll();
    }
});

// --- API: Download Media for Single Package ---
async function downloadSingle(trackingNumber) {
    const pkg = packages.find(p => p.trackingNumber === trackingNumber);
    if (!pkg) return;
    
    log(`Bắt đầu tải hình ảnh/video cho đơn ${trackingNumber}...`, "info");
    pkg.localStatus = "Đang tải...";
    renderSummaryTable();
    
    try {
        const response = await fetch(`${API_URL}/api/download-package`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ trackingNumber })
        });
        const data = await response.json();
        
        if (data.status === "success") {
            pkg.localStatus = "Đã tải về";
            log(`Đã tải xong minh chứng và tạo thư mục cho đơn ${trackingNumber}!`, "success");
            showToast(`Tải xong đơn ${trackingNumber}!`);
        } else {
            pkg.localStatus = "Lỗi tải";
            log(`Lỗi tải tệp đơn ${trackingNumber}: ${data.message}`, "error");
        }
    } catch (e) {
        pkg.localStatus = "Lỗi tải";
        log(`Lỗi kết nối khi tải đơn ${trackingNumber}: ${e.message}`, "error");
    }
    renderSummaryTable();
    renderPackagesTableAll();
}

// --- API: Upload Single Package to JMS ---
async function uploadSingle(trackingNumber) {
    const pkg = packages.find(p => p.trackingNumber === trackingNumber);
    if (!pkg) return;
    
    if (connectionStatus.jms !== "connected") {
        log("Lỗi: Chưa kết nối tab JMS VN! Vui lòng đăng nhập JMS trên Chrome điều khiển.", "error");
        return;
    }
    
    if (pkg.localStatus !== "Đã tải về") {
        log(`Đơn ${trackingNumber} chưa được tải minh chứng về máy! Tiến hành tải trước...`, "warning");
        await downloadSingle(trackingNumber);
        if (pkg.localStatus !== "Đã tải về") return; // Stop if download failed
    }
    
    log(`Đang tiến hành điền dữ liệu và upload minh chứng cho đơn ${trackingNumber} lên JMS...`, "info");
    pkg.jmsStatus = "Đang xử lý...";
    renderSummaryTable();
    
    try {
        const response = await fetch(`${API_URL}/api/upload-jms`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ trackingNumber, weight: pkg.weight })
        });
        const data = await response.json();
        
        if (data.status === "success") {
            pkg.jmsStatus = "Thành công";
            log(`Tải lên thành công đối trọng lượng cho đơn ${trackingNumber}!`, "success");
            showToast(`Thành công đơn ${trackingNumber}!`);
        } else {
            pkg.jmsStatus = "Thất bại";
            log(`Thất bại khi cập nhật đơn ${trackingNumber}: ${data.message}`, "error");
        }
    } catch (e) {
        pkg.jmsStatus = "Thất bại";
        log(`Lỗi kết nối khi đẩy đơn ${trackingNumber} lên JMS: ${e.message}`, "error");
    }
    renderSummaryTable();
    renderPackagesTableAll();
}

// Helper to run both Download & Upload for a single package
async function processAllForSingle(trackingNumber) {
    await downloadSingle(trackingNumber);
    await uploadSingle(trackingNumber);
}

// --- API: Download All ---
elBtnDownloadAll.addEventListener("click", async () => {
    if (packages.length === 0) {
        log("Không có đơn hàng nào để tải. Hãy quét Zalo trước!", "warning");
        return;
    }
    
    log("Bắt đầu tải hình ảnh và video cho TẤT CẢ các đơn hàng...", "system");
    isProcessing = true;
    elBtnDownloadAll.disabled = true;
    
    for (let pkg of packages) {
        if (pkg.localStatus !== "Đã tải về") {
            await downloadSingle(pkg.trackingNumber);
        }
    }
    
    log("Hoàn thành tải về tất cả tài liệu đính kèm!", "success");
    showToast("Tải về hoàn tất!");
    isProcessing = false;
    elBtnDownloadAll.disabled = false;
});

// --- API: Open Folder in Windows Explorer ---
elBtnOpenFolder.addEventListener("click", async () => {
    try {
        const response = await fetch(`${API_URL}/api/open-folder`, { method: "POST" });
        const data = await response.json();
        if (data.status === "success") {
            log("Đã mở thư mục lưu trữ trên máy tính.", "success");
        } else {
            log(`Lỗi khi mở thư mục: ${data.message}`, "error");
        }
    } catch (e) {
        log(`Không thể kết nối đến server: ${e.message}`, "error");
    }
});

// --- API: Upload All (Auto JMS Loop) ---
elBtnUploadAll.addEventListener("click", async () => {
    if (packages.length === 0) {
        log("Không có đơn hàng nào để xử lý. Hãy quét Zalo trước!", "warning");
        return;
    }
    if (connectionStatus.jms !== "connected") {
        log("Chưa mở hoặc đăng nhập JMS VN trên trình duyệt điều khiển!", "error");
        showToast("Hãy mở & đăng nhập JMS!", "danger");
        return;
    }
    
    log("Bắt đầu chạy TỰ ĐỘNG tải tài liệu & upload JMS cho tất cả đơn...", "system");
    isProcessing = true;
    elBtnUploadAll.disabled = true;
    
    for (let pkg of packages) {
        if (pkg.jmsStatus !== "Thành công") {
            await processAllForSingle(pkg.trackingNumber);
        }
    }
    
    log("Đã hoàn tất quy trình đối trọng lượng tự động cho tất cả đơn hàng!", "success");
    showToast("Hoàn tất Auto JMS!");
    isProcessing = false;
    elBtnUploadAll.disabled = false;
});

// --- Logs management ---
elBtnClearLogs.addEventListener("click", () => {
    elConsoleLogs.innerHTML = "";
    log("Đã xóa nhật ký.", "system");
});

// --- Settings and Selectors handling ---
async function loadSettings() {
    try {
        const response = await fetch(`${API_URL}/api/settings`);
        const settings = await response.json();
        if (settings.selectors) {
            document.getElementById("sel-search-input").value = settings.selectors.search_input || "";
            document.getElementById("sel-search-btn").value = settings.selectors.search_btn || "";
            document.getElementById("sel-edit-btn").value = settings.selectors.edit_btn || "";
            document.getElementById("sel-weight-input").value = settings.selectors.weight_input || "";
            document.getElementById("sel-upload-btn").value = settings.selectors.upload_plus_btn || "";
            document.getElementById("sel-confirm-btn").value = settings.selectors.confirm_btn || "";
        }
        if (settings.zalo_selectors) {
            document.getElementById("sel-zalo-chat-item").value = settings.zalo_selectors.chat_item || "";
            document.getElementById("sel-zalo-scroll").value = settings.zalo_selectors.scroll_container || "";
            document.getElementById("sel-zalo-search").value = settings.zalo_selectors.search_inchat || "";
            document.getElementById("sel-zalo-react").value = settings.zalo_selectors.reaction_space || "";
            document.getElementById("sel-zalo-conv").value = settings.zalo_selectors.conv_item || "";
            document.getElementById("sel-zalo-pinned").value = settings.zalo_selectors.pinned_banner || "";
        }
        document.getElementById("sel-enable-ocr").checked = settings.enable_ocr_check || false;
        document.getElementById("sel-ocr-api-key").value = settings.ocr_api_key || "helloworld";
    } catch (e) {
        console.error("Không thể load cấu hình:", e);
    }
}

elSettingsForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const settings = {
        selectors: {
            search_input: document.getElementById("sel-search-input").value,
            search_btn: document.getElementById("sel-search-btn").value,
            edit_btn: document.getElementById("sel-edit-btn").value,
            weight_input: document.getElementById("sel-weight-input").value,
            upload_plus_btn: document.getElementById("sel-upload-btn").value,
            confirm_btn: document.getElementById("sel-confirm-btn").value
        },
        zalo_selectors: {
            chat_item: document.getElementById("sel-zalo-chat-item").value,
            scroll_container: document.getElementById("sel-zalo-scroll").value,
            search_inchat: document.getElementById("sel-zalo-search").value,
            reaction_space: document.getElementById("sel-zalo-react").value,
            conv_item: document.getElementById("sel-zalo-conv").value,
            pinned_banner: document.getElementById("sel-zalo-pinned").value
        },
        enable_ocr_check: document.getElementById("sel-enable-ocr").checked,
        ocr_api_key: document.getElementById("sel-ocr-api-key").value || "helloworld"
    };
    
    try {
        const response = await fetch(`${API_URL}/api/settings`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(settings)
        });
        const data = await response.json();
        if (data.status === "success") {
            log("Đã lưu cấu hình bộ nhận dạng CSS Selector mới.", "success");
            showToast("Đã lưu cấu hình!");
        }
    } catch (e) {
        log(`Lỗi lưu cấu hình: ${e.message}`, "error");
    }
});

elBtnResetSettings.addEventListener("click", async () => {
    if (confirm("Bạn có chắc chắn muốn khôi phục cấu hình mặc định?")) {
        const defaultSettings = {
            selectors: {
                search_input: "input[placeholder*='vận đơn'], input[id*='billCode'], .el-input__inner",
                search_btn: "button:has-text('Tìm kiếm'), button:has-text('Search'), .el-button--primary",
                edit_btn: "i.el-icon-edit, button[title*='Nhập liệu'], .el-table__row button:first-child",
                weight_input: "input[placeholder*='trọng lượng'], input[placeholder*='cân nặng'], .el-dialog input.el-input__inner",
                upload_plus_btn: ".el-upload--picture-card, input[type='file']",
                confirm_btn: "button:has-text('Xác nhận'), button:has-text('Lưu'), .el-dialog__footer button.el-button--primary"
            },
            zalo_selectors: {
                chat_item: ".chat-item",
                scroll_container: ".transform-gpu",
                search_inchat: ".search-message-inchat",
                reaction_space: ".message-reaction-v2-space",
                conv_item: ".conv-item, [class*='conv'], .msg-item, div, span",
                pinned_banner: ".list-chat-box-banner, [class*='list-chat-box-banner'], .chat-group-topic, [class*='pinned-message']"
            },
            enable_ocr_check: false,
            ocr_api_key: "helloworld"
        };
        
        try {
            await fetch(`${API_URL}/api/settings`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(defaultSettings)
            });
            await loadSettings();
            log("Đã khôi phục bộ nhận dạng mặc định.", "system");
            showToast("Đã khôi phục mặc định!");
        } catch (e) {
            console.error(e);
        }
    }
});

// --- Manual Clipboard/Drag-drop Upload logic ---
const elManualTracking = document.getElementById("manual-tracking");
const elManualWeight = document.getElementById("manual-weight");
const elPasteZone = document.getElementById("paste-zone");
const elPastePreview = document.getElementById("paste-preview");
const elBtnSaveManual = document.getElementById("btn-save-manual");

let manualFiles = [];

// Focus styling
elPasteZone.addEventListener("click", () => elPasteZone.focus());

// Input validation
function validateManualForm() {
    const tracking = elManualTracking.value.trim();
    // Validate tracking is exactly 12 digits
    const isValidTracking = /^\d{11,12}$/.test(tracking);
    const hasFiles = manualFiles.length > 0;
    elBtnSaveManual.disabled = !(isValidTracking && hasFiles);
}

elManualTracking.addEventListener("input", validateManualForm);

// Handle Paste (Ctrl + V)
elPasteZone.addEventListener("paste", async (e) => {
    e.preventDefault();
    const items = e.clipboardData.items;
    
    for (let i = 0; i < items.length; i++) {
        const item = items[i];
        if (item.kind === "file") {
            const file = item.getAsFile();
            await addManualFile(file);
        }
    }
});

// Handle Drag and Drop
elPasteZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    elPasteZone.style.borderColor = "#ff9f43";
});

elPasteZone.addEventListener("dragleave", () => {
    elPasteZone.style.borderColor = "";
});

elPasteZone.addEventListener("drop", async (e) => {
    e.preventDefault();
    elPasteZone.style.borderColor = "";
    const files = e.dataTransfer.files;
    for (let file of files) {
        await addManualFile(file);
    }
});

// Process and convert file to Base64
async function addManualFile(file) {
    return new Promise((resolve) => {
        const reader = new FileReader();
        reader.onload = () => {
            manualFiles.push({
                name: file.name,
                type: file.type,
                data: reader.result
            });
            renderPastePreviews();
            validateManualForm();
            resolve();
        };
        reader.readAsDataURL(file);
    });
}

// Render previews of pasted images/videos
function renderPastePreviews() {
    elPastePreview.innerHTML = "";
    manualFiles.forEach((file, idx) => {
        const item = document.createElement("div");
        item.className = "paste-preview-item";
        
        let mediaTag = "";
        if (file.type.startsWith("video")) {
            mediaTag = `<video src="${file.data}" muted autoplay loop></video>`;
        } else {
            mediaTag = `<img src="${file.data}">`;
        }
        
        item.innerHTML = `
            ${mediaTag}
            <button class="remove-btn" onclick="removeManualFile(${idx})">&times;</button>
        `;
        elPastePreview.appendChild(item);
    });
}

// Remove single pasted file
window.removeManualFile = function(idx) {
    manualFiles.splice(idx, 1);
    renderPastePreviews();
    validateManualForm();
};

// Save Manual Package
elBtnSaveManual.addEventListener("click", async () => {
    const trackingNumber = elManualTracking.value.trim();
    const weight = elManualWeight.value ? parseFloat(elManualWeight.value) : null;
    
    log(`Đang lưu đơn hàng nhập thủ công ${trackingNumber}...`, "info");
    elBtnSaveManual.disabled = true;
    
    try {
        const response = await fetch(`${API_URL}/api/add-manual-package`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                trackingNumber,
                weight,
                files: manualFiles
            })
        });
        const data = await response.json();
        
        if (data.status === "success") {
            log(`Đã tạo thư mục và thêm thành công đơn hàng ${trackingNumber}! Sẵn sàng Auto JMS.`, "success");
            showToast(`Thêm đơn ${trackingNumber} thành công!`);
            
            // Clear inputs
            elManualTracking.value = "";
            elManualWeight.value = "";
            manualFiles = [];
            elPastePreview.innerHTML = "";
            validateManualForm();
            
            // Refresh list
            const existingIdx = packages.findIndex(p => p.trackingNumber === trackingNumber);
            const serverPkg = data.package;
            if (existingIdx !== -1) {
                packages[existingIdx] = serverPkg;
            } else {
                packages.unshift(serverPkg);
            }
            
            elScannedCount.textContent = `${packages.length} đơn hàng`;
            renderSummaryTable();
        } else {
            log(`Lỗi lưu đơn thủ công: ${data.message}`, "error");
        }
    } catch (e) {
        log(`Lỗi kết nối khi lưu đơn thủ công: ${e.message}`, "error");
    } finally {
        elBtnSaveManual.disabled = false;
    }
});

// Helper to load packages from backend
async function loadPackages() {
    try {
        const res = await fetch(`${API_URL}/api/packages`);
        const data = await res.json();
        if (data) {
            packages = data.map(p => ({
                ...p,
                localStatus: p.localStatus || "Đã quét",
                jmsStatus: p.jmsStatus || "Chưa xử lý",
                copied: p.copied || false
            }));
            elScannedCount.textContent = `${packages.length} đơn hàng`;
            renderSummaryTable();
            if (!document.getElementById("tab-packages").classList.contains("hidden")) {
                renderPackagesTableAll();
            }
        }
    } catch (e) {
        console.error("Lỗi khi tải danh sách đơn hàng:", e);
    }
}

// --- Initial Setup and Polling ---
async function init() {
    await loadSettings();
    await fetchStatus();
    await loadPackages();
    
    // Poll connection status every 3 seconds
    setInterval(fetchStatus, 3000);
}

// Start
init();
