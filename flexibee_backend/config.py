from django.conf import settings

FLEXIBEE_COMPANY_MODEL = getattr(settings, 'FLEXIBEE_COMPANY_MODEL', None)
FLEXIBEE_BACKEND_NAME = getattr(settings, 'FLEXIBEE_BACKEND_NAME', 'flexibee')
