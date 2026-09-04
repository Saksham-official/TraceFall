import os

# Settings require a secret key; the app is designed to refuse to start without one.
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-used-outside-tests-0123456789")
