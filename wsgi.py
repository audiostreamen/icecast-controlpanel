# Zorg dat Gunicorn altijd een WSGI 'app' kan importeren
from app import app as application
app = application
