Virtual Gate‑Access System
==========================

📁 Project Setup Instructions
-----------------------------

Follow these steps to install dependencies and run the project.

1️⃣ Prerequisites:
------------------
- Python 3.10 (Recommended)
- pip (Python package manager)
- CMake (for dlib on Windows)
- Visual C++ Build Tools (Windows users)

2️⃣ Folder Structure:
----------------------
Place your files in the following structure:

project_folder/
├── app.py
├── requirements.txt
├── templates/
│   ├── login.html
│   ├── register.html
│   ├── index.html
│   ├── Admin.html
│   ├── add_user.html
│   └── reset_password.html
├── static/
│   └── user_images/

3️⃣ Setting Up the Project:
----------------------------
Step 1: Create a virtual environment (recommended)

Windows:
    python -m venv face_env
    face_env\Scripts\activate

Linux/macOS:
    python3 -m venv face_env
    source face_env/bin/activate

Step 2: Install all required libraries

    pip install -r requirements.txt

(If dlib fails, install CMake and build tools or use a pre-built wheel)

4️⃣ Running the Project:
-------------------------
In the terminal, run:

    python app.py

Then open your browser and go to:

    http://127.0.0.1:5000/

5️⃣ Email Setup (for password reset):
-------------------------------------
In app.py, configure your email:

app.config.update(
    MAIL_SERVER="smtp.gmail.com",
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME="your_email@gmail.com",
    MAIL_PASSWORD="your_app_password"
)

(Use Gmail App Password, not your login password)

✅ You're now ready to use the system!