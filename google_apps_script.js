/**
 * =====================================================================
 * JMS HELPER - GOOGLE APPS SCRIPT QUẢN LÝ BẢN QUYỀN & DÙNG THỬ (SERVERLESS)
 * =====================================================================
 * HƯỚNG DẪN CÀI ĐẶT TRONG 1 PHÚT:
 * 1. Mở một trang Google Sheet mới (Google Trang tính).
 * 2. Đặt tên tiêu đề các cột ở Hàng 1 (Row 1):
 *    - Cột A: Mã thiết bị (HWID)
 *    - Cột B: Ngày bắt đầu (First Seen)
 *    - Cột C: Số ngày đã dùng (Days Used)
 *    - Cột D: Trạng thái (Status)
 *    - Cột E: Lần online cuối (Last Seen)
 *    - Cột F: Ghi chú / Tên khách hàng (Notes)
 * 3. Vào menu: Tiện ích mở rộng (Extensions) -> Apps Script.
 * 4. Xóa hết code cũ, dán toàn bộ đoạn code này vào và nhấn Lưu (Save).
 * 5. Nhấn nút "Triển khai" (Deploy) ở góc trên bên phải -> "Tùy chọn triển khai mới" (New deployment).
 * 6. Chọn loại: "Ứng dụng web" (Web app).
 *    - Thực thi dưới dạng (Execute as): "Tôi" (Me).
 *    - Ai có quyền truy cập (Who has access): "Bất kỳ ai" (Anyone).
 * 7. Nhấn "Triển khai" (Deploy) -> Cấp quyền truy cập nếu Google hỏi.
 * 8. Sao chép "URL của ứng dụng web" (Web App URL) và dán vào biến CLOUD_API_URL trong file backend/license_verifier.py.
 * =====================================================================
 */

function doGet(e) {
  return handleRequest(e);
}

function doPost(e) {
  return handleRequest(e);
}

function handleRequest(e) {
  var lock = LockService.getScriptLock();
  // Khóa script trong tối đa 10s để tránh xung đột ghi đè đồng thời
  lock.tryLock(10000);
  
  try {
    var params = e && e.parameter ? e.parameter : {};
    var hwid = (params.hwid || "").trim().toUpperCase();
    var TRIAL_LIMIT = 30; // 30 ngày dùng thử
    
    if (!hwid) {
      return createJsonResponse({
        status: "error",
        message: "Mã thiết bị (HWID) không được để trống."
      });
    }
    
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
    var data = sheet.getDataRange().getValues();
    var todayStr = Utilities.formatDate(new Date(), "GMT+7", "yyyy-MM-dd");
    var nowFullStr = Utilities.formatDate(new Date(), "GMT+7", "yyyy-MM-dd HH:mm:ss");
    var today = new Date();
    
    var rowIndex = -1;
    var firstSeenStr = todayStr;
    var isBlocked = false;
    var isLicensed = false;
    
    // Tìm kiếm HWID đã tồn tại trong Sheet
    for (var i = 1; i < data.length; i++) {
      var rowHwid = String(data[i][0] || "").trim().toUpperCase();
      if (rowHwid === hwid) {
        rowIndex = i + 1; // 1-indexed trong Google Sheet
        
        // Đọc ngày bắt đầu
        var rawFirstDate = data[i][1];
        if (rawFirstDate instanceof Date) {
          firstSeenStr = Utilities.formatDate(rawFirstDate, "GMT+7", "yyyy-MM-dd");
        } else if (rawFirstDate) {
          firstSeenStr = String(rawFirstDate).trim();
        }
        
        // Đọc trạng thái
        var status = String(data[i][3] || "").trim().toLowerCase();
        if (status === "blocked" || status === "khóa" || status === "khoa") {
          isBlocked = true;
        } else if (status === "licensed" || status === "active" || status === "kích hoạt") {
          isLicensed = true;
        }
        break;
      }
    }
    
    // Nếu máy mới hoàn toàn -> Ghi mới vào dòng tiếp theo
    if (rowIndex === -1) {
      sheet.appendRow([hwid, todayStr, 0, "Trial", nowFullStr, "Khách dùng thử mới"]);
      rowIndex = sheet.getLastRow();
      firstSeenStr = todayStr;
    }
    
    // Tính toán số ngày đã trôi qua kể từ ngày đầu tiên mở app
    var firstDate = new Date(firstSeenStr);
    var diffTime = today.getTime() - firstDate.getTime();
    var diffDays = Math.max(0, Math.floor(diffTime / (1000 * 60 * 60 * 24)));
    
    // Cập nhật số ngày đã dùng & thời gian online mới nhất vào Sheet
    sheet.getRange(rowIndex, 3).setValue(diffDays);
    sheet.getRange(rowIndex, 5).setValue(nowFullStr);
    
    var remainingDays = Math.max(0, TRIAL_LIMIT - diffDays);
    var isInTrial = (diffDays <= TRIAL_LIMIT) && !isBlocked;
    
    var response = {
      status: "success",
      hwid: hwid,
      first_seen: firstSeenStr.replace(/-/g, ""), // Định dạng YYYYMMDD
      diff_days: diffDays,
      remaining_days: remainingDays,
      is_in_trial: isInTrial,
      is_blocked: isBlocked,
      is_licensed: isLicensed
    };
    
    return createJsonResponse(response);
    
  } catch (err) {
    return createJsonResponse({
      status: "error",
      message: err.toString()
    });
  } finally {
    lock.releaseLock();
  }
}

function createJsonResponse(data) {
  return ContentService.createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}
