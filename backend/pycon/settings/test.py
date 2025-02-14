from .base import *  # noqa

SECRET_KEY = "this-key-should-only-be-used-for-tests"
HASHID_DEFAULT_SECRET_SALT = "only-for-tests"

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

MAILCHIMP_SECRET_KEY = "super-secret-key-for-tests"
MAILCHIMP_DC = "us5"
MAILCHIMP_LIST_ID = "12345678ab"

PRETIX_API = "http://pretix-api:9000/"

AZURE_STORAGE_ACCOUNT_NAME = "pytest-fakestorageaccount"
AZURE_STORAGE_ACCOUNT_KEY = "fake-key"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "conferencevideos": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}
PYTHONIT_EMAIL_BACKEND = "conftest.TestEmailBackend"

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
