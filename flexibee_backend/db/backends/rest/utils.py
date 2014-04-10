from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.utils.translation import ugettext_lazy as _

import requests

from flexibee_backend import config


LIST_URL = 'https://%(hostname)s/c.json'
CREATE_URL = 'https://%(hostname)s/admin/zalozeni-firmy.json'


def get_companies_list():
    db_settings = settings.DATABASES.get('flexibee')
    hostname = db_settings.get('HOSTNAME')
    port = db_settings.get('PORT')
    username = db_settings.get('USER')
    password = db_settings.get('PASSWORD')

    url = LIST_URL % {'hostname': hostname, 'port': port}

    r = requests.get(url, auth=(username, password))

    if not config.FLEXIBEE_COMPANY_MODEL:
        raise ImproperlyConfigured('FLEXIBEE_COMPANY_MODEL is not set')

    flexibee_company_list = r.json().get('companies').get('company')
    if not isinstance(flexibee_company_list, (list, tuple)):
        flexibee_company_list = [flexibee_company_list]
    return flexibee_company_list


def db_name_validator(value):
    flexibee_company_list = get_companies_list()
    db_names = [flexibee_company.get('dbNazev') for flexibee_company in flexibee_company_list]
    if value not in db_names and not config.TESTING:
        raise ValidationError(_('DB name %s does not exists') % value)
