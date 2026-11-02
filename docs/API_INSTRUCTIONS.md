# DOLLAR BY SALE - Google Apps Script API (Full Version)

## Quick Setup Guide

### Step 1: Create Google Sheet

1. Go to **sheets.google.com** → Create new blank spreadsheet
2. Rename sheet tab to `Sheet1` (or whatever you want, but update the code)
3. In **Row 2**, add these headers (exactly as shown):

| A | B | C | D | E | F |
|---|---|---|---|---|---|
| `Telegram User ID` | `Telegram Name` | `Username` | `Has Vantage Account` | `Status` | `Created At` |

4. **Row 1** can have any title, e.g., "Dollar By Sale Users"

---

### Step 2: Open Apps Script

1. In your Google Sheet, click **Extensions** → **Apps Script**
2. Delete ALL existing code
3. **Copy the FULL code below** and paste into the editor

---

### Step 3: Deploy as Web App

1. Click **Deploy** → **New deployment**
2. Click the **gear icon** ⚙️ next to "Select type" → **Web app**
3. Fill in:
   - **Description**: Dollar By Sale API
   - **Execute as**: **Me** (your email)
   - **Who has access**: **Anyone**
4. Click **Deploy**
5. **Copy the Web app URL** - it looks like:
   ```
   https://script.google.com/macros/s/AKfycby.../exec
   ```
6. Save this URL - you'll need it for the bot `.env` file

---

## Full Code to Copy-Paste

```javascript
// ============================================================
// DOLLAR BY SALE — USER ELIGIBILITY API
// FULL VERSION: READ, INSERT, UPDATE
// ============================================================

// ============================================================
// SETTINGS
// ============================================================

const HEADER_ROW = 2;
const DATA_START_ROW = 3;
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
// ============================================================

function findUserRow(sheet, telegramUserId) {
  const lastRow = sheet.getLastRow();
  if (lastRow < DATA_START_ROW) return -1;

  const numberOfRows = lastRow - DATA_START_ROW + 1;
  const data = sheet.getRange(DATA_START_ROW, 1, numberOfRows, TOTAL_COLUMNS).getValues();
  const searchId = String(telegramUserId ?? '').trim();

  if (!searchId) return -1;

  for (let i = 0; i < data.length; i++) {
    const rowUserId = String(data[i][0] ?? '').trim();
    if (rowUserId === searchId) return DATA_START_ROW + i;
  }
  return -1;
}


// ============================================================
// READ ALL USERS
// ============================================================

function readUsers(sheet) {
  const lastRow = sheet.getLastRow();
  if (lastRow < DATA_START_ROW) return [];

  const headers = sheet.getRange(HEADER_ROW, 1, 1, TOTAL_COLUMNS).getValues()[0];
  const numberOfRows = lastRow - DATA_START_ROW + 1;
  const data = sheet.getRange(DATA_START_ROW, 1, numberOfRows, TOTAL_COLUMNS).getValues();
  const result = [];

  for (let i = 0; i < data.length; i++) {
    const row = data[i];
    const emptyRow = row.every(function(value) {
      return String(value ?? '').trim() === '';
    });
    if (emptyRow) continue;

    const user = {};
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
// INSERT NEW USER
// ============================================================

function insertUser(sheet, e) {
  const telegramUserId = e.parameter.TelegramUserId || '';

  if (!telegramUserId) {
    return jsonResponse({ success: false, error: 'TelegramUserId is required' });
  }

  const existingRow = findUserRow(sheet, telegramUserId);
  if (existingRow !== -1) {
    return jsonResponse({ success: false, error: 'User already exists', row: existingRow });
  }

  const telegramName = e.parameter.TelegramName || '';
  const username = e.parameter.Username || '';
  const hasVantageAccount = String(e.parameter.HasVantageAccount || '').trim().toUpperCase() === 'YES' ? 'YES' : 'NO';
  const status = hasVantageAccount === 'YES' ? 'ELIGIBLE' : 'NOT_ELIGIBLE';
  const createdAt = e.parameter.CreatedAt || new Date().toISOString();

  const newRow = [
    telegramUserId,    // A
    telegramName,      // B
    username,          // C
    hasVantageAccount, // D
    status,            // E
    createdAt          // F
  ];

  sheet.appendRow(newRow);

  return jsonResponse({
    success: true,
    action: 'insert',
    message: 'User added successfully',
    row: sheet.getLastRow(),
    telegramUserId: telegramUserId,
    status: status
  });
}


// ============================================================
// UPDATE EXISTING USER
// ============================================================

function updateUser(sheet, e) {
  const telegramUserId = e.parameter.TelegramUserId || '';

  if (!telegramUserId) {
    return jsonResponse({ success: false, error: 'TelegramUserId is required' });
  }

  const rowNumber = findUserRow(sheet, telegramUserId);
  if (rowNumber === -1) {
    return jsonResponse({ success: false, error: 'User not found' });
  }

  const updates = [];

  if (e.parameter.TelegramName !== undefined && e.parameter.TelegramName !== '') {
    sheet.getRange(rowNumber, 2).setValue(e.parameter.TelegramName);
    updates.push('Telegram Name');
  }

  if (e.parameter.Username !== undefined && e.parameter.Username !== '') {
    sheet.getRange(rowNumber, 3).setValue(e.parameter.Username);
    updates.push('Username');
  }

  if (e.parameter.HasVantageAccount !== undefined) {
    const hasVantage = String(e.parameter.HasVantageAccount).trim().toUpperCase() === 'YES' ? 'YES' : 'NO';
    sheet.getRange(rowNumber, 4).setValue(hasVantage);
    updates.push('Has Vantage Account');
    const newStatus = hasVantage === 'YES' ? 'ELIGIBLE' : 'NOT_ELIGIBLE';
    sheet.getRange(rowNumber, 5).setValue(newStatus);
    updates.push('Status');
  }

  if (updates.length === 0) {
    return jsonResponse({ success: false, error: 'No fields provided for update', row: rowNumber });
  }

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
  e = e || { parameter: {} };

  const action = String(e.parameter.action || 'read').trim().toLowerCase();
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheetName = e.parameter.sheet || 'Sheet1';
  const sheet = ss.getSheetByName(sheetName);

  if (!sheet) {
    return jsonResponse({ success: false, error: 'Sheet not found', sheet: sheetName });
  }

  if (action === 'read') {
    return jsonResponse(readUsers(sheet));
  }

  if (action === 'insert' || action === 'add') {
    return insertUser(sheet, e);
  }

  if (action === 'update') {
    return updateUser(sheet, e);
  }

  return jsonResponse({
    success: false,
    error: 'Invalid action',
    allowedActions: ['read', 'insert', 'update']
  });
}


// ============================================================
// MAIN doPost()
// ============================================================

function doPost(e) {
  const params = {};
  if (e.postData && e.postData.contents) {
    try {
      const data = JSON.parse(e.postData.contents);
      for (const key in data) params[key] = data[key];
    } catch (err) {
      const pairs = e.postData.contents.split('&');
      pairs.forEach(function(pair) {
        const parts = pair.split('=');
        if (parts.length === 2) {
          params[decodeURIComponent(parts[0])] = decodeURIComponent(parts[1]);
        }
      });
    }
  }
  return doGet({ parameter: params });
}
```

---

## API Endpoints

### 1. READ All Users
```
GET https://script.google.com/macros/s/YOUR_ID/exec?action=read
```

**Response:**
```json
[
  {
    "Telegram User ID": "123456789",
    "Telegram Name": "John Doe",
    "Username": "johndoe",
    "Has Vantage Account": "YES",
    "Status": "ELIGIBLE",
    "Created At": "2026-10-31T10:00:00.000Z"
  }
]
```

---

### 2. INSERT New User
```
GET https://script.google.com/macros/s/YOUR_ID/exec?action=insert&TelegramUserId=123456789&TelegramName=John%20Doe&Username=johndoe&HasVantageAccount=YES
```

**Response:**
```json
{
  "success": true,
  "action": "insert",
  "message": "User added successfully",
  "row": 3,
  "telegramUserId": "123456789",
  "status": "ELIGIBLE"
}
```

---

### 3. UPDATE Existing User
```
GET https://script.google.com/macros/s/YOUR_ID/exec?action=update&TelegramUserId=123456789&HasVantageAccount=NO
```

**Response:**
```json
{
  "success": true,
  "action": "update",
  "message": "User updated successfully",
  "row": 3,
  "telegramUserId": "123456789",
  "fieldsUpdated": 2,
  "updatedFields": ["Has Vantage Account", "Status"]
}
```

---

## Required Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `action` | Yes | `read`, `insert`, or `update` |
| `TelegramUserId` | Yes (for insert/update) | Unique user ID from Telegram |
| `TelegramName` | No | Full name of user |
| `Username` | No | Telegram username |
| `HasVantageAccount` | No | `YES` or `NO` |

---

## Test Your API

After deploying, test these URLs in your browser:

**Test READ:**
```
https://script.google.com/macros/s/AKfycby.../exec?action=read
```

**Test INSERT:**
```
https://script.google.com/macros/s/AKfycby.../exec?action=insert&TelegramUserId=999999999&TelegramName=Test User&Username=testuser&HasVantageAccount=YES
```

**Test UPDATE:**
```
https://script.google.com/macros/s/AKfycby.../exec?action=update&TelegramUserId=999999999&HasVantageAccount=NO
```

---

## Update .env File

After getting your new API URL, update your bot's `.env` file:

```bash
cd /Users/tawhid/dollar-bot
nano .env
```

Change:
```
SHEETS_API_URL=https://script.google.com/macros/s/NEW_DEPLOYED_ID/exec
```

---

## Notes

- **Bot must be admin** in your Telegram group to use all features
- **Timezone**: API uses UTC for timestamps
- **Limits**: Google Apps Script has 30-second timeout per request
- **Rate limit**: 1 request per second per user (Google limit)
