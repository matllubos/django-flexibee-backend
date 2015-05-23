import sys

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


TESTING = sys.argv[1:2] == ['test'] or sys.argv[1:2] == ['jenkins']

FLEXIBEE_COMPANY_MODEL = getattr(settings, 'FLEXIBEE_COMPANY_MODEL', None)
FLEXIBEE_BACKEND_NAME = getattr(settings, 'FLEXIBEE_BACKEND_NAME', 'flexibee')
FLEXIBEE_EXTERNAL_KEY_PREFIX = getattr(settings, 'FLEXIBEE_EXTERNAL_KEY_PREFIX', None)
FLEXIBEE_ADMIN_CERTIFICATE = getattr(settings, 'FLEXIBEE_ADMIN_CERTIFICATE', None)
FLEXIBEE_CACHE_TIMEOUT = getattr(settings, 'FLEXIBEE_CACHE_TIMEOUT', 60 * 60 * 24 * 1)  # 1 day

if not FLEXIBEE_EXTERNAL_KEY_PREFIX:
    raise ImproperlyConfigured('FLEXIBEE_EXTERNAL_KEY_PREFIX must be set inside settings')

FLEXIBEE_PDF_REPORT_AVAILABLE_LANGUAGES = getattr(settings, 'FLEXIBEE_PDF_REPORT_AVAILABLE_LANGUAGES',
                                                  ('cs', 'sk', 'en', 'de'))
FLEXIBEE_PDF_REPORT_DEFAULT_LANGUAGE = getattr(settings, 'FLEXIBEE_PDF_REPORT_DEFAULT_LANGUAGE', 'cs')
