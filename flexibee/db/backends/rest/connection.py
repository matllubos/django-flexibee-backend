import requests


class Connector(object):

    URL = 'https://creative-dock.flexibee.eu/c/%(company)s/%(table_name)s.json'

    def __init__(self, username, password, company):
        self.username = username
        self.password = password
        self.company = company

    def get(self, table_name, extra=''):
        r = requests.get(self.URL % {'company': self.company, 'table_name': table_name},
                         auth=(self.username, self.password))
        return r.json().get('winstrom').get('faktura-vydana')
