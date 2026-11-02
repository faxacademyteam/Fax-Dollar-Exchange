# DOLLAR BY SALE — API CODE (Final Version)

**File:** `dollar-by-sale-api-full.js`

**Location:** `/Users/tawhid/dollar-bot/dollar-by-sale-api-full.js`

---

## Features

- ✅ **READ** - Get all users
- ✅ **INSERT** - Add new user
- ✅ **UPDATE** - Update existing user
- ✅ **NO_RESPONSE** - Tracks users who didn't answer in 5 minutes

---

## How to Deploy

1. Open your Google Sheet
2. **Extensions** → **Apps Script**
3. **Delete all code**
4. **Copy-paste** from file:
   ```
   /Users/tawhid/dollar-bot/dollar-by-sale-api-full.js
   ```
5. Click **Deploy** → **New deployment**
6. Click ⚙️ gear → **Web app**
7. Set:
   - Execute as: **Me**
   - Who has access: **Anyone**
8. Click **Deploy**
9. **Copy the Web app URL**
10. Update `.env`:
    ```
    SHEETS_API_URL=https://script.google.com/macros/s/NEW_ID/exec
    ```

---

## API Endpoints

### READ All Users
```
GET ?action=read
```

### INSERT New User
```
GET ?action=insert&TelegramUserId=...&TelegramName=...&Username=...&HasVantageAccount=YES|NO|NO_RESPONSE
```

### UPDATE Existing User
```
GET ?action=update&TelegramUserId=...&TelegramName=...&Username=...&HasVantageAccount=YES|NO|NO_RESPONSE
```

---

## Has Vantage Account Values

| Value | Meaning |
|-------|---------|
| `YES` | User answered YES |
| `NO` | User answered NO |
| `NO_RESPONSE` | User didn't respond in 5 minutes |

---

## Status Values

| Value | Triggered When |
|-------|----------------|
| `ELIGIBLE` | Has Vantage Account = YES |
| `NOT_ELIGIBLE` | Has Vantage Account = NO or NO_RESPONSE |
