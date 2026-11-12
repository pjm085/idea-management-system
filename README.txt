JO! THE HELPER — BCA PROJECT

This package contains only the runnable website code, its required runtime assets,
the Python dependency list, and these instructions.

REQUIREMENTS
- Python 3.10 or newer (Python 3.12 recommended)
- A modern web browser
- Internet access to install the Python packages on first setup. The app itself
  and its SQLite database run locally. Google Fonts and Remix Icon are loaded
  from external services, so they may not display offline.

WINDOWS (PowerShell)
1. Extract this folder.
2. Open PowerShell in the folder containing app.py.
3. Run:

   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   python app.py

4. Open http://127.0.0.1:5000 and register an account.

If PowerShell blocks activation, use Command Prompt:

   .venv\Scripts\activate.bat
   python -m pip install -r requirements.txt
   python app.py

MACOS / LINUX
1. Open a terminal in the folder containing app.py.
2. Run:

   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   python app.py

3. Open http://127.0.0.1:5000 and register an account.

ALTERNATE PORT
If port 5000 is occupied, set PORT before running:

PowerShell:
   $env:PORT = "5011"
   python app.py

macOS / Linux:
   PORT=5011 python app.py

Then open http://127.0.0.1:5011.

FILES REQUIRED TO RUN
- app.py, database.py, features\
- templates\
- static\css, static\JS, and the two referenced images in static\images
- requirements.txt

The database and a development signing key are created locally on first run.
This ZIP does not contain personal database data, secrets, reports, tests, or
other project documentation. Do not expose a running development server to the
public internet.
