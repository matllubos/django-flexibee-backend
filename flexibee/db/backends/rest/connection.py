import requests
import json

class Connector(object):

    def __init__(self, username, password, hostname, company):
        self.username = username
        self.password = password
        self.hostname = hostname
        self.company = company


class RestQuery(object):

    URL = 'https://creative-dock.flexibee.eu/c/%(company)s/%(table_name)s/(%(filter)s).json?%(query_string)s'

    def __init__(self, connector, table_name, fields=[]):
        self.table_name = table_name
        self.connector = connector
        self.fields = fields
        self.query_strings = {'detail': 'custom:%s' % ','.join(self.fields)}
        self.order_fields = []
        self.filters = []

    def get(self, extra_query_strings={}):
        query_strings = self.query_strings.copy()
        query_strings.update(extra_query_strings)

        query_strings_list = query_strings.items()

        for order_field in self.order_fields:
            query_strings_list.append(('order', order_field))

        query_strings = ['%s=%s' % (key, val) for key, val in query_strings_list]

        filter_string = ' and '.join(['(%s)' % filter for filter in self.filters])

        url = self.URL % {'company': self.connector.company, 'table_name': self.table_name,
                          'query_string': '&'.join(query_strings), 'filter': filter_string}

        print url
        r = requests.get(url, auth=(self.connector.username, self.connector.password))
        return r.json().get('winstrom')

    def count(self):
        query_strings = {'add-row-count':'true', 'detail':'custom:id'}
        return self.get(query_strings).get('@rowCount')

    def fetch(self, offset, base):
        query_strings = {'start':offset}
        if base != None:
            query_strings['limit'] = base
        return self.get(query_strings).get(self.table_name)

    def add_ordering(self, field_name, is_asc):
        self.order_fields.append('%s@%s' % (field_name, is_asc and 'A' or 'D'))

    def add_filter(self, field_name, op, db_value, negated):
        filter_list = []
        if negated:
            filter_list.append('not')

        filter_list += [field_name, op, unicode(db_value)]
        self.filters.append(' '.join(filter_list))

    def save(self, data):
        url = 'https://%(hostname)s/c/%(company)s/%(table_name)s.json' % {'company': self.connector.company, 'table_name': self.table_name}

        print json.dumps(data)
        print url

        try:
            headers = {'Content-type': 'application/json'}

            data = {'firma': 'code:nase_firma_s_r_o_', 'popis': 'test', 'sumZklZakl': 1000, 'bezPolozek': True}



            data = "{'windstorm': {'faktura-vydana': {'typDokl': 'code:FAKTURA','firma': 'code:CREATIVDOCK','popis': 'Moje faktura z CURL', 'sumZklZakl': 1000, 'bezPolozek': true}}}}"

            print data
            r = requests.post(url, data=data, headers=headers, auth=(self.connector.username, self.connector.password))


            print 'ted uz ne'
            print r
            print r.json()
        except Exception as ex:
            print 'bug'
            print ex
