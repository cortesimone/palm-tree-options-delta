# Google Sheets API - Setup Instructions

## 1. Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **Select a project** → **New Project**
3. Name it (e.g., "Options Tracker") and click **Create**

## 2. Enable the Google Sheets API

1. In the Cloud Console, navigate to **APIs & Services** → **Library**
2. Search for **Google Sheets API**
3. Click **Enable**

## 3. Create a Service Account

1. Go to **IAM & Admin** → **Service Accounts**
2. Click **+ Create Service Account**
3. Give it a name (e.g., "options-tracker") and click **Create**
4. Skip role assignment (not needed) and click **Done**

## 4. Create a Service Account Key

1. In the Service Accounts list, click the email address of the new account
2. Go to the **Keys** tab
3. Click **Add Key** → **Create new key**
4. Choose **JSON** format and click **Create**
5. The JSON file will download automatically — rename it to `google-credentials.json`
6. Move it to the `secrets/` directory:

```bash
mv ~/Downloads/google-credentials.json /home/simone/MEGA/dev/palm-tree-options-delta/secrets/google-credentials.json
```

## 5. Share the Spreadsheet

1. Create a new Google Spreadsheet (or use an existing one)
2. Create tabs with the names you plan to use (e.g., "Next Friday Puts", "Following Friday Puts")
3. Click **Share** in the top-right
4. Paste the **service account email** from step 3 (looks like `options-tracker@your-project.iam.gserviceaccount.com`)
5. Grant **Editor** access and click **Share**

## 6. Get the Spreadsheet ID

1. Open the Google Spreadsheet in your browser
2. The Spreadsheet ID is the long string between `/d/` and `/edit` in the URL:

```
https://docs.google.com/spreadsheets/d/SPREADSHEET_ID_HERE/edit#gid=0
```

## 7. Configure Environment Variables

Copy `.env.example` to `.env` and fill in the values:

```bash
cp .env.example .env
```

Edit `.env` and set:

```env
# Alpaca API (required for fetching option data)
ALPACA_API_KEY=your_alpaca_api_key
ALPACA_API_SECRET=your_alpaca_api_secret

# Google Sheets (required for uploading)
# Existing vars (GSHEET_*):
GSHEET_ACCESS_KEY=secrets/micro-instance-cortesi-com-bc58d2d37218.json
GSHEET_ID=18ucnR8hIUuZgjGFJfD5NHL8EkiySMVGSun-9i8dNP5w
GSHEET_TAB_NAME=CSP

# Or new vars (overridden by --spreadsheet-id / --upcoming-tab CLI flags):
GOOGLE_SHEET_ID=SPREADSHEET_ID_HERE
UPCOMING_TAB_NAME=Next Friday Puts
FOLLOWING_TAB_NAME=Following Friday Puts
```

## 8. Install Dependencies

```bash
pip install -r requirements.txt
```

## 9. Test the Upload

```bash
# Upload upcoming Friday data
python3 upload_to_sheet.py TSLA -0.18 4

# Upload both upcoming and following Friday
python3 upload_to_sheet.py TSLA -0.18 4 --both

# Upload with custom spreadsheet ID and tab names
python3 upload_to_sheet.py AAPL -0.25 3 \
  --spreadsheet-id "1ABCxyz..." \
  --upcoming-tab "AAPL Next" \
  --following-tab "AAPL Following"
```

## Troubleshooting

- **"Permission denied"**: Make sure the service account email has been added as an Editor to the Google Sheet.
- **"Credentials file not found"**: Verify `secrets/google-credentials.json` (or the path in `GSHEET_ACCESS_KEY`) exists and is valid JSON.
- **"Invalid spreadsheet ID"**: Double-check the ID from the spreadsheet URL — it should be the full string between `/d/` and `/edit`.
- **"No data rows found"**: The Alpaca API may not have greeks data yet for that expiration (weekends/holidays). Try a different date.