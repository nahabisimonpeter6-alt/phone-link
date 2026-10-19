"""Copy into the WSGI configuration linked from nahabi's PythonAnywhere Web tab.

The deployment ZIP extracts to /home/nahabi/phone-link-main. For an EU account,
replace PUBLIC_URL with the exact HTTPS address shown on that Web tab.
"""
import os
import sys

PROJECT = "/home/nahabi/phone-link-main"
PUBLIC_URL = "https://nahabi.pythonanywhere.com"
DATABASE = "/home/nahabi/phonelink-private/phonelink.sqlite3"

sys.path.insert(0, PROJECT)
os.environ["PHONELINK_PUBLIC_URL"] = PUBLIC_URL
os.environ["PHONELINK_DB"] = DATABASE

from wsgi import application
