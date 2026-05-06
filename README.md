# FundedFirst

Agentic AI for startup job discovery.

FundedFirst helps students and early-career candidates discover recently funded startups, assess opportunity fit, and prepare application outreach from a web dashboard.

## Google Technologies

- Gemini API for agentic research, credibility checks, CV scoring, and email drafting
- Firebase Firestore for user profiles, startup records, and application history
- Firebase Auth for dashboard sign-in

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set up Firebase

1. Open [console.firebase.google.com](https://console.firebase.google.com).
2. Create a Firebase project or select an existing project.
3. Enable Firebase Auth:
   - Go to Build > Authentication.
   - Click Get started.
   - Enable the sign-in providers you want to use, such as Google or Email/Password.
4. Enable Firestore:
   - Go to Build > Firestore Database.
   - Create a database.
   - Choose a location.
   - Start in test mode for local development, then tighten rules before production.

### 3. Get `firebase_credentials.json`

1. In Firebase Console, open Project settings.
2. Go to Service accounts.
3. Click Generate new private key.
4. Download the JSON file.
5. Rename it to `firebase_credentials.json`.
6. Place it in the project root next to `app.py`.

This file is ignored by git and must not be committed.

### 4. Get the Firebase Auth web API key

1. In Firebase Console, open Project settings.
2. Go to General.
3. Under Your apps, create or select a Web app.
4. Copy the Firebase config values:
   - `apiKey`
   - `authDomain`
   - `projectId`
   - `storageBucket`
   - `messagingSenderId`
   - `appId`
5. Add those values to your `.env` file.

### 5. Set up Gemini API

1. Open [aistudio.google.com](https://aistudio.google.com).
2. Create or select an API key.
3. Add the key to your `.env` file as `GEMINI_API_KEY`.
4. Optionally set `GEMINI_MODEL`, for example:

```env
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.0-flash
```

### 6. Create `.env`

Create a `.env` file in the project root:

```env
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.0-flash

FIREBASE_CREDENTIALS_PATH=firebase_credentials.json
FIREBASE_WEB_API_KEY=your_firebase_web_api_key
FIREBASE_AUTH_DOMAIN=your_project.firebaseapp.com
FIREBASE_PROJECT_ID=your_project_id
FIREBASE_STORAGE_BUCKET=your_project.appspot.com
FIREBASE_MESSAGING_SENDER_ID=your_sender_id
FIREBASE_APP_ID=your_app_id

EMAIL_USER=your_email@gmail.com
EMAIL_PASSWORD=your_gmail_app_password
EMAIL_SMTP=smtp.gmail.com
EMAIL_PORT=587
```

## Run

```bash
python app.py
```

Open [http://localhost:5000](http://localhost:5000).

## Project Structure

```text
FundedFirst/
  app.py
  main.py
  config.py
  database.py
  extractor.py
  email_sender.py
  agents/
  profiles/
  scrapers/
  templates/
    dashboard.html
  utils/
```

## Notes

- `firebase_credentials.json`, `.env`, local databases, logs, and Python cache files are ignored by git.
- The dashboard expects `templates/dashboard.html` to exist.
- Keep Firebase rules restrictive before deploying beyond local development.
