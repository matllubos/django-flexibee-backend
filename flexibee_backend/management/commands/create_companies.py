from django.core.management.base import NoArgsCommand
from django.conf import settings
from django.db.models.loading import get_model
from django.core.exceptions import ImproperlyConfigured
from django.utils.encoding import force_text

import requests

from flexibee_backend import config


class SyncException(Exception):
    pass


class Command(NoArgsCommand):
    LIST_URL = 'https://%(hostname)s/c.json'
    CREATE_URL = 'https://%(hostname)s/admin/zalozeni-firmy.json'

    def __init__(self, *args, **kwargs):
        super(NoArgsCommand, self).__init__(*args, **kwargs)
        db_settings = settings.DATABASES.get('flexibee')
        self.hostname = db_settings.get('HOSTNAME')
        self.port = db_settings.get('PORT')
        self.username = db_settings.get('USER')
        self.password = db_settings.get('PASSWORD')

    def _create_companies(self):
        url = self.LIST_URL % {'hostname': self.hostname, 'port': self.port}

        r = requests.get(url, auth=(self.username, self.password))

        if not config.FLEXIBEE_COMPANY_MODEL:
            raise ImproperlyConfigured('FLEXIBEE_COMPANY_MODEL is not set')

        flexibee_company_list = r.json().get('companies').get('company')
        if not isinstance(flexibee_company_list, (list, tuple)):
            flexibee_company_list = [flexibee_company_list]

        flexibee_company_db_name_list = [flexibee_company.get('dbNazev')
                                         for flexibee_company in flexibee_company_list]

        for company in get_model(*config.FLEXIBEE_COMPANY_MODEL.rsplit('.', 1)).objects.all():
            if company.flexibee_db_name not in flexibee_company_db_name_list:
                url = self.CREATE_URL % {'hostname': self.hostname, 'port': self.port}
                data = {}
                for from_name, to_name in company.FlexibeeMeta.mapping.items():
                    data[to_name] = getattr(company, from_name)

                query_string = '&'.join(['%s=%s' % (key, val) for key, val in data.items()])

                url += '?%s' % query_string
                r = requests.post(url, auth=(self.username, self.password))

                if r.status_code == 200:
                    company.flexibee_db_name = r.headers['location'].spit('/')[-1]
                else:
                    raise SyncException(r.json().get('winstrom').get('message'))

    def handle_noargs(self, **options):
        try:
            self._create_companies()
        except (ImproperlyConfigured, SyncException) as ex:
            print '%s: %s' % (ex.__class__.__name__, force_text(ex))
