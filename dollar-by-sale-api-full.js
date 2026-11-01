// ============================================================
// DOLLAR BY SALE — USER ELIGIBILITY API
// FULL VERSION: READ, INSERT, UPDATE
// ============================================================
//
// SHEET STRUCTURE:
//
// Row 1 = Column headers
// Row 2+ = User data
//
// COLUMNS:
//
// A = Telegram User ID
// B = Telegram Name
// C = Username
// D = Has Vantage Account   (YES / NO / NO_RESPONSE)
// E = Status                (ELIGIBLE / NOT_ELIGIBLE)
// F = Created At
//
// ACTIONS:
//
// READ ALL
// ?action=read
//
// INSERT NEW
// ?action=insert&TelegramUserId=...&TelegramName=...&Username=...&HasVantageAccount=YES|NO|NO_RESPONSE
//
// UPDATE EXISTING
// ?action=update&TelegramUserId=...&TelegramName=...&Username=...&HasVantageAccount=YES|NO|NO_RESPONSE
//
// ============================================================


// ============================================================
// SETTINGS
// ============================================================

const HEADER_ROW = 1;
const DATA_START_ROW = 2;
const TOTAL_COLUMNS = 6;


// ============================================================
// JSON RESPONSE
// ============================================================

function jsonResponse(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}


// ============================================================
// FIND USER BY TELEGRAM USER ID
//
// Returns actual Google Sheet row number.
// Returns -1 if not found.
// ============================================================

function findUserRow(sheet, telegramUserId) {
  const lastRow = sheet.getLastRow();

  if (lastRow < DATA_START_ROW) {
    return -1;
  }

  const numberOfRows = lastRow - DATA_START_ROW + 1;
  const data = sheet.getRange(DATA_START_ROW, 1, numberOfRows, TOTAL_COLUMNS).getValues();

  const searchId = String(telegramUserId ?? '').trim();

  if (!searchId) {
    return -1;
  }

  for (let i = 0; i < data.length; i++) {
    const rowUserId = String(data[i][0] ?? '').trim();
    if (rowUserId === searchId) {
      return DATA_START_ROW + i;
    }
  }

  return -1;
}


// ============================================================
// READ ALL USERS
// ============================================================

function readUsers(sheet) {
  const lastRow = sheet.getLastRow();

  if (lastRow < DATA_START_ROW) {
    return [];
  }

  // Read headers from ROW 1
  const headers = sheet.getRange(HEADER_ROW, 1, 1, TOTAL_COLUMNS).getValues()[0];

  // Read data from ROW 2
  const numberOfRows = lastRow - DATA_START_ROW + 1;
  const data = sheet.getRange(DATA_START_ROW, 1, numberOfRows, TOTAL_COLUMNS).getValues();

  const result = [];

  for (let i = 0; i < data.length; i++) {
    const row = data[i];

    // Skip completely empty rows
    const emptyRow = row.every(function(value) {
      return String(value ?? '').trim() === '';
    });

    if (emptyRow) {
      continue;
    }

    const user = {};

    // Build user object using headers as keys
    for (let j = 0; j < headers.length; j++) {
      const key = String(headers[j] ?? '').trim();
      if (key) {
        user[key] = row[j] === null || row[j] === undefined ? '' : row[j];
      }
    }

    result.push(user);
  }

  return result;
}


// ============================================================
// VALIDATE HAS VANTAGE ACCOUNT VALUE
// ============================================================

function validateVantageAccount(value) {
  const v = String(value ?? '').trim().toUpperCase();
  if (v === 'YES' || v === 'NO' || v === 'NO_RESPONSE') {
    return v;
  }
  return 'NO'; // Default
}


// ============================================================
// GET STATUS FROM VANTAGE ACCOUNT
// ============================================================

function getStatusFromVantage(vantageAccount) {
  // YES -> ELIGIBLE, NO/NO_RESPONSE -> NOT_ELIGIBLE
  return vantageAccount === 'YES' ? 'ELIGIBLE' : 'NOT_ELIGIBLE';
}


// ============================================================
// INSERT NEW USER
// ============================================================

function insertUser(sheet, e) {
  const telegramUserId = e.parameter.TelegramUserId || '';

  // ----------------------------------------------------------
  // Telegram User ID required
  // ----------------------------------------------------------

  if (!telegramUserId) {
    return jsonResponse({
      success: false,
      error: 'TelegramUserId is required'
    });
  }

  // ----------------------------------------------------------
  // Check duplicate
  // ----------------------------------------------------------

  const existingRow = findUserRow(sheet, telegramUserId);

  if (existingRow !== -1) {
    return jsonResponse({
      success: false,
      error: 'User already exists',
      row: existingRow
    });
  }

  // ----------------------------------------------------------
  // Get user info
  // ----------------------------------------------------------

  const telegramName = e.parameter.TelegramName || '';
  const username = e.parameter.Username || '';
  const hasVantageAccount = validateVantageAccount(e.parameter.HasVantageAccount);
  const status = getStatusFromVantage(hasVantageAccount);
  const createdAt = e.parameter.CreatedAt || new Date().toISOString();

  // ----------------------------------------------------------
  // Create row
  // ----------------------------------------------------------

  const newRow = [
    telegramUserId,    // A = Telegram User ID
    telegramName,      // B = Telegram Name
    username,          // C = Username
    hasVantageAccount, // D = Has Vantage Account (YES/NO/NO_RESPONSE)
    status,            // E = Status (ELIGIBLE/NOT_ELIGIBLE)
    createdAt          // F = Created At
  ];

  // ----------------------------------------------------------
  // Add user
  // ----------------------------------------------------------

  sheet.appendRow(newRow);

  // ----------------------------------------------------------
  // Return success
  // ----------------------------------------------------------

  return jsonResponse({
    success: true,
    action: 'insert',
    message: 'User added successfully',
    row: sheet.getLastRow(),
    telegramUserId: telegramUserId,
    hasVantageAccount: hasVantageAccount,
    status: status
  });
}


// ============================================================
// UPDATE EXISTING USER
// ============================================================

function updateUser(sheet, e) {
  const telegramUserId = e.parameter.TelegramUserId || '';

  // ----------------------------------------------------------
  // Telegram User ID required
  // ----------------------------------------------------------

  if (!telegramUserId) {
    return jsonResponse({
      success: false,
      error: 'TelegramUserId is required'
    });
  }

  // ----------------------------------------------------------
  // Find user
  // ----------------------------------------------------------

  const rowNumber = findUserRow(sheet, telegramUserId);

  if (rowNumber === -1) {
    return jsonResponse({
      success: false,
      error: 'User not found'
    });
  }

  // ----------------------------------------------------------
  // Update fields if provided
  // ----------------------------------------------------------

  const updates = [];

  // B = Telegram Name (Column 2)
  if (e.parameter.TelegramName !== undefined && e.parameter.TelegramName !== '') {
    sheet.getRange(rowNumber, 2).setValue(e.parameter.TelegramName);
    updates.push('Telegram Name');
  }

  // C = Username (Column 3)
  if (e.parameter.Username !== undefined && e.parameter.Username !== '') {
    sheet.getRange(rowNumber, 3).setValue(e.parameter.Username);
    updates.push('Username');
  }

  // D = Has Vantage Account (Column 4)
  if (e.parameter.HasVantageAccount !== undefined) {
    const hasVantage = validateVantageAccount(e.parameter.HasVantageAccount);
    sheet.getRange(rowNumber, 4).setValue(hasVantage);
    updates.push('Has Vantage Account');

    // Auto-update status based on Vantage account
    const newStatus = getStatusFromVantage(hasVantage);
    sheet.getRange(rowNumber, 5).setValue(newStatus);
    updates.push('Status');
  }

  // F = Created At (Column 6) - Always update to current time on any update
  const updatedAt = new Date().toISOString();
  sheet.getRange(rowNumber, 6).setValue(updatedAt);
  updates.push('Created At');

  // If no fields provided
  if (updates.length === 0) {
    return jsonResponse({
      success: false,
      error: 'No fields provided for update',
      row: rowNumber
    });
  }

  // ----------------------------------------------------------
  // Success response
  // ----------------------------------------------------------

  return jsonResponse({
    success: true,
    action: 'update',
    message: 'User updated successfully',
    row: rowNumber,
    telegramUserId: telegramUserId,
    fieldsUpdated: updates.length,
    updatedFields: updates
  });
}


// ============================================================
// MAIN doGet()
// ============================================================

function doGet(e) {
  // Safety fallback
  e = e || { parameter: {} };

  // ----------------------------------------------------------
  // Action
  // ----------------------------------------------------------

  const action = String(e.parameter.action || 'read').trim().toLowerCase();

  // ----------------------------------------------------------
  // Spreadsheet
  // ----------------------------------------------------------

  const ss = SpreadsheetApp.getActiveSpreadsheet();

  // ----------------------------------------------------------
  // Sheet name (default: Sheet1)
  // ----------------------------------------------------------

  const sheetName = e.parameter.sheet || 'Sheet1';
  const sheet = ss.getSheetByName(sheetName);

  if (!sheet) {
    return jsonResponse({
      success: false,
      error: 'Sheet not found',
      sheet: sheetName
    });
  }

  // ==========================================================
  // READ
  // ==========================================================

  if (action === 'read') {
    const users = readUsers(sheet);
    return jsonResponse(users);
  }

  // ==========================================================
  // INSERT
  // ==========================================================

  if (action === 'insert' || action === 'add') {
    return insertUser(sheet, e);
  }

  // ==========================================================
  // UPDATE
  // ==========================================================

  if (action === 'update') {
    return updateUser(sheet, e);
  }

  // ==========================================================
  // INVALID ACTION
  // ==========================================================

  return jsonResponse({
    success: false,
    error: 'Invalid action',
    allowedActions: ['read', 'insert', 'update']
  });
}


// ============================================================
// MAIN doPost() - Alternative for POST requests
// ============================================================

function doPost(e) {
  // Parse POST data
  const params = {};
  if (e.postData && e.postData.contents) {
    try {
      const data = JSON.parse(e.postData.contents);
      for (const key in data) {
        params[key] = data[key];
      }
    } catch (err) {
      // If JSON parse fails, treat as form data
      const pairs = e.postData.contents.split('&');
      pairs.forEach(function(pair) {
        const parts = pair.split('=');
        if (parts.length === 2) {
          params[decodeURIComponent(parts[0])] = decodeURIComponent(parts[1]);
        }
      });
    }
  }

  // Simulate doGet with POST params
  const mockEvent = {
    parameter: params
  };

  return doGet(mockEvent);
}
