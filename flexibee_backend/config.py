from django.conf import settings

FLEXIBEE_COMPANY_MODEL = getattr(settings, 'FLEXIBEE_COMPANY_MODEL', None)
