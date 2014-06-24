import requests
from django.conf import settings

from flexibee_backend.db.backends.rest.exceptions import SyncException
from flexibee_backend import config


class FlexibeeAdminConnector(object):
    LIST_URL = 'https://%(hostname)s/c.json'
    CREATE_URL = 'https://%(hostname)s/admin/zalozeni-firmy.json'

    def __init__(self):
        db_settings = settings.DATABASES.get(config.FLEXIBEE_BACKEND_NAME)
        self.hostname = db_settings.get('HOSTNAME')
        self.username = db_settings.get('USER')
        self.password = db_settings.get('PASSWORD')

    def create_company(self, company):
        url = self.CREATE_URL % {'hostname': self.hostname}
        data = {}
        for from_name, to_name in company.FlexibeeMeta.mapping.items():
            data[to_name] = getattr(company, from_name)

        query_string = '&'.join(['%s=%s' % (key, val) for key, val in data.items()])

        url += '?%s' % query_string

        r = requests.post(url, auth=(self.username, self.password))

        if r.status_code == 200:
            company.flexibee_db_name = r.headers['location'].spit('/')[-1]
        else:
            raise SyncException(r.json().get('winstrom').get('message'), r)

admin_connector = FlexibeeAdminConnector()

