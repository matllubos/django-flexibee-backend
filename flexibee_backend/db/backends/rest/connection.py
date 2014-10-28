import requests
import json
import logging
import decimal

from django.db.utils import DatabaseError
from django.utils.encoding import force_text
from django.utils.datastructures import SortedDict
from django.utils.http import urlquote, urlunquote

from flexibee_backend.db.backends.rest.exceptions import FlexibeeDatabaseException, \
    ChangesNotActivatedFlexibeeDatabaseException
from flexibee_backend.db.backends.rest.filters import ElementaryFilter
from django.contrib.admin.util import unquote



def decimal_default(obj):
    if isinstance(obj, decimal.Decimal):
        return str(obj)
    raise TypeError


class BaseConnector(object):

    URL = 'https://%(hostname)s/c/%(db_name)s/%(table_name)s%(extra)s.%(type)s?%(query_string)s'
    logger = logging.getLogger('flexibee-backend')

    def __init__(self, username, password, hostname):
        self.username = username
        self.password = password
        self.hostname = hostname
        self.db_name = None

    def _check_settings(self, table_name):
        if self.db_name is None:
            raise DatabaseError('For flexibee DB connector must be set company: %s' % table_name)

    def _serialize(self, data):
        return json.dumps(data, default=decimal_default)

    def reset(self):
        self.db_name = None


class ModelConnector(BaseConnector):

    def __init__(self, username, password, hostname):
        super(ModelConnector, self).__init__(username, password, hostname)
        self.cache = {}
        self.waiting_writes = SortedDict()

    def _is_request_for_one_object(self, filters):
        return (len(filters) == 1 and isinstance(filters[0], ElementaryFilter) and
                filters[0].field == 'id' and filters[0].op == '=' and not filters[0].negated)

    def _prepare_obj_data(self, obj_data):
        result = obj_data.copy()
        obj_id = []
        pk = obj_data.get('id')
        if pk:
            obj_id.append(pk)

        ext_pk = result.pop('external-ids', None)
        if ext_pk:
            obj_id.append(ext_pk)

        result['id'] = obj_id
        return result

    def _construct_filter(self, filters):
        return ' and '.join(['(%s)' % force_text(filter) for filter in filters])

    def _get_extra_filter(self, filters):
        extra = ''
        filter_string = self._construct_filter(filters)
        if filter_string:
            extra = '/(%s)' % urlquote(filter_string, safe='')
        return extra

    def _get_query_string(self, fields, relations, ordering, offset, base):
        query_string_list = [
                             ('detail', 'custom:%s' % ','.join(fields)),
        ]
        if relations:
            query_string_list.append(('relations', ','.join(relations)))

        for field in ordering:
            query_string_list.append(('order', field))

        query_string_list.append(('start', offset))
        query_string_list.append(('limit', base))
        query_string_list.append(('add-row-count', 'true'))

        return '&'.join(['%s=%s' % (key, val) for key, val in query_string_list])

    def _generate_key(self, filters, fields, relations, ordering, offset, base):
        filters_key = ','.join([unicode(filter) for filter in filters])
        fields_key = ','.join(fields)
        relations_key = ','.join(relations)
        ordering_key = ','.join(ordering)
        return '__'.join((filters_key, fields_key, relations_key, ordering_key, str(offset), str(base)))

    def _get_from_cache(self, table_name, filters, fields, relations, ordering, offset, base):
        if '__'.join((self.db_name, table_name)) in self.cache:
            table_cache = self.cache.get('__'.join((self.db_name, table_name)))
            key = self._generate_key(filters, fields, relations, ordering, offset, base)
            if key in table_cache:
                return table_cache.get(key)

    def _clear_table_cache(self, table_name):
        if '__'.join((self.db_name, table_name)) in self.cache:
            del self.cache['__'.join((self.db_name, table_name))]

    def _add_to_cache(self, table_name, filters, fields, relations, ordering, offset, base, data):
        table_cache = self.cache['__'.join((self.db_name, table_name))] = self.cache\
                                                                            .get('__'.join((self.db_name, table_name)),
                                                                                 {})
        key = self._generate_key(filters, fields, relations, ordering, offset, base)
        table_cache[key] = data

    def read(self, table_name, filters, fields, relations, ordering, offset, base):
        self._check_settings(table_name)

        filters = list(filters)
        fields = list(fields)
        relations = list(relations)
        ordering = list(ordering)

        filters.sort()
        fields.sort()
        ordering.sort()
        relations.sort()

        data = self._get_from_cache(table_name, filters, fields, relations, ordering, offset, base)
        if data:
            return data

        extra = self._get_extra_filter(filters)

        url = self.URL % {'hostname': self.hostname, 'db_name': self.db_name, 'table_name': table_name,
                          'query_string': self._get_query_string(fields, relations, ordering, offset, base),
                          'extra': extra, 'type': 'json'}
        self.logger.info('Send GET to %s' % url)
        r = requests.get(url, auth=(self.username, self.password))

        if r.status_code in [200, 201]:
            self.logger.info('Response %s, content: %s' % (r.status_code, force_text(r.text)))
            data = r.json().get('winstrom')
            self._add_to_cache(table_name, filters, fields, relations, ordering, offset, base, data)
            return data
        elif self._is_request_for_one_object(filters) and r.status_code == 404:
            return {table_name:[]}
        else:
            self.logger.warning('Response %s, content: %s' % (r.status_code, force_text(r.text)))
            raise FlexibeeDatabaseException('Rest GET method error', r, url)

    def write(self, table_name, data):
        self._check_settings(table_name)

        url = self.URL % {'hostname': self.hostname, 'db_name': self.db_name,
                          'table_name': table_name, 'query_string': '', 'extra': '', 'type': 'json'}

        data = {'winstrom': {table_name: [self._prepare_obj_data(obj_data) for obj_data in data]}}
        headers = {'Accept': 'application/json'}

        self.logger.info('Send PUT to %s' % url)

        r = requests.put(url, data=self._serialize(data), headers=headers, auth=(self.username, self.password))

        if r.status_code in [200, 201]:
            self._clear_table_cache(table_name)
            self.logger.info('Response %s, content: %s' % (r.status_code, force_text(r.text)))
            return r.json().get('winstrom')
        else:
            self.logger.warning('Response %s, content: %s' % (r.status_code, force_text(r.text)))
            raise FlexibeeDatabaseException('Rest PUT method error', r, url)

    def delete(self, table_name, filters):
        self._check_settings(table_name)

        filters = list(filters)
        url = self.URL % {
            'hostname': self.hostname, 'db_name': self.db_name,
            'table_name': table_name, 'query_string': '',
            'extra': '', 'type': 'json'
        }
        data = {
            'winstrom': {
                table_name: {
                    '@action': 'delete',
                    '@filter': self._construct_filter(filters),
                }
            }
        }
        headers = {'Accept': 'application/json'}

        r = requests.put(url, data=self._serialize(data), headers=headers, auth=(self.username, self.password))
        if r.status_code not in [201]:
            self.logger.info('Response %s, content: %s' % (r.status_code, force_text(r.text)))
            raise FlexibeeDatabaseException('Rest DELETE method error', r, url)
        else:
            self.logger.info('Response %s, content: %s' % (r.status_code, force_text(r.text)))

    def get_response(self, table_name, id, type):
        self._check_settings(table_name)

        url = self.URL % {'hostname': self.hostname, 'db_name': self.db_name,
                          'table_name': table_name, 'query_string': '', 'extra': '/%s' % id, 'type': type}
        return requests.get(url, auth=(self.username, self.password))

    def changes(self, start):
        self._check_settings('changes')

        url = self.URL % {'hostname': self.hostname, 'db_name': self.db_name, 'extra': '',
                          'table_name': 'changes', 'query_string': 'start=%s' % start, 'type': 'json'}
        r = requests.get(url, auth=(self.username, self.password))
        if r.status_code not in [200, 404]:
            self.logger.info('Response %s, content: %s' % (r.status_code, force_text(r.text)))
            raise ChangesNotActivatedFlexibeeDatabaseException(r)
        return int(r.json().get('winstrom').get('@globalVersion'))

    def activate_changes(self):
        self._check_settings('changes')

        url = self.URL % {'hostname': self.hostname, 'db_name': self.db_name, 'extra': '',
                          'table_name': 'changes/enable', 'query_string': '', 'type': 'json'}
        r = requests.put(url, auth=(self.username, self.password))

    def reset(self):
        super(ModelConnector, self).reset()
        self.db_name = None


class AttachmentConnector(BaseConnector):

    def read(self, table_name, parent_id, pk=None):
        self._check_settings(table_name)

        extra = '/%s/prilohy' % parent_id
        if pk:
            extra = '/'.join((extra, str(pk)))

        url = self.URL % {'hostname': self.hostname, 'db_name': self.db_name,
                          'table_name': table_name,
                          'query_string': 'detail=custom:id,contentType,nazSoub,contentType,poznam,link',
                          'extra': extra, 'type': 'json'}
        r = requests.get(url, auth=(self.username, self.password))
        return r.json().get('winstrom').get('priloha')

    def _get_last_pk(self, table_name, parent_id):
        url = 'https://%(hostname)s/c/%(db_name)s/%(table_name)s/%(parent_id)s/prilohy.json%(extra)s'
        url = url % {'hostname': self.hostname, 'db_name': self.db_name,
                     'table_name': table_name, 'parent_id': parent_id,
                     'extra': '?order=id@D&detail=custom:id'}
        r = requests.get(url, auth=(self.username, self.password))
        if r.status_code != 200:
            self.logger.warning('Response %s, content: %s' % (r.status_code, force_text(r.text)))
            raise FlexibeeDatabaseException('Rest PUT method error', r, url)
        return r.json().get('winstrom').get('priloha')[0].get('id')

    def write(self, table_name, parent_id, data):
        self._check_settings(table_name)
        pk = data.pop('pk', None)
        if not pk:
            url = 'https://%(hostname)s/c/%(db_name)s/%(table_name)s/%(parent_id)s/prilohy/new/%(filename)s'
            url = url % {'hostname': self.hostname, 'db_name': self.db_name,
                         'table_name': table_name, 'parent_id': parent_id, 'filename': data.get('nazSoub')}
            headers = {'content-type': data.get('contentType')}
            r = requests.put(url, data=data['file'].read(), headers=headers,
                             auth=(self.username, self.password))
        else:
            url = 'https://%(hostname)s/c/%(db_name)s/%(table_name)s/%(parent_id)s/prilohy/%(pk)s.json'
            url = url % {'hostname': self.hostname, 'db_name': self.db_name,
                         'table_name': table_name, 'parent_id': parent_id, 'pk': pk}
            data = {'winstrom': {'priloha': data}}
            headers = {'Accept': 'application/json'}
            r = requests.put(url, data=self._serialize(data), headers=headers, auth=(self.username, self.password))
        if r.status_code not in [200, 201]:
            self.logger.warning('Response %s, content: %s' % (r.status_code, force_text(r.text)))
            raise FlexibeeDatabaseException('Rest PUT method error', r, url)

        return pk or self._get_last_pk(table_name, parent_id)

    def delete(self, table_name, parent_id, pk):
        self._check_settings(table_name)

        url = 'https://%(hostname)s/c/%(db_name)s/%(table_name)s/%(parent_id)s/prilohy/%(pk)s.json'
        self._check_settings(table_name)
        url = url % {'hostname': self.hostname, 'db_name': self.db_name,
                     'table_name': table_name, 'parent_id': parent_id, 'pk': pk}
        r = requests.delete(url, auth=(self.username, self.password))
        if r.status_code not in [200, 201]:
            self.logger.warning('Response %s, content: %s' % (r.status_code, force_text(r.text)))
            raise FlexibeeDatabaseException('Rest DELETE method error', r, url)

    def get_response(self, table_name, parent_id, pk):
        self._check_settings(table_name)

        url = 'https://%(hostname)s/c/%(db_name)s/%(table_name)s/%(parent_id)s/prilohy/%(pk)s/content'
        url = url % {'hostname': self.hostname, 'db_name': self.db_name,
                     'table_name': table_name, 'parent_id': parent_id, 'pk': pk}
        return requests.get(url, auth=(self.username, self.password))


class RelationConnector(BaseConnector):

    def read(self, table_name, id, relation_id=None):
        self._check_settings(table_name)

        extra = '/%s/vazby' % id
        if relation_id:
            extra = '/'.join((extra, str(relation_id)))

        url = self.URL % {'hostname': self.hostname, 'db_name': self.db_name,
                          'table_name': table_name,
                          'query_string': 'detail=custom:id,a,b,typVazbyK,castka,castkaMen',
                          'extra': extra, 'type': 'json'}

        r = requests.get(url, auth=(self.username, self.password))

        return r.json().get('winstrom').get('vazba')

    def delete(self, table_name, id, data):
        self._check_settings(table_name)

        url = 'https://%(hostname)s/c/%(db_name)s/%(table_name)s/%(id)s.json'
        self._check_settings(table_name)
        url = url % {'hostname': self.hostname, 'db_name': self.db_name,
                     'table_name': table_name, 'id': id}

        data = {'winstrom': {table_name: {'odparovani': data}}}
        r = requests.put(url, data=self._serialize(data), auth=(self.username, self.password))
        if r.status_code not in [200, 201]:
            self.logger.warning('Response %s, content: %s' % (r.status_code, force_text(r.text)))
            raise FlexibeeDatabaseException('Rest PUT method error', r, url)

    def write(self, table_name, id, data):
        self._check_settings(table_name)

        url = 'https://%(hostname)s/c/%(db_name)s/%(table_name)s/%(id)s.json'
        self._check_settings(table_name)
        url = url % {'hostname': self.hostname, 'db_name': self.db_name,
                     'table_name': table_name, 'id': id}

        data = {'winstrom': {table_name: {'sparovani': data}}}
        r = requests.put(url, data=self._serialize(data), auth=(self.username, self.password))
        if r.status_code not in [200, 201]:
            self.logger.warning('Response %s, content: %s' % (r.status_code, force_text(r.text)))
            raise FlexibeeDatabaseException('Rest PUT method error', r, url)


class CachedEntity(object):

    def __init__(self, entity, fields):
        self.entity = entity
        self.fields = fields


class RestQuery(object):

    def __init__(self, connector, table_name, fields=[], relations=[], via_table_name=None, via_relation_name=None,
                 via_fk_name=None):
        self.table_name = table_name
        self.connector = connector
        self.fields = fields
        self.query_strings = {'detail': 'custom:%s' % ','.join(self.fields)}
        self.order_fields = []
        self.filters = []
        self.relations = []

        self.via_table_name = via_table_name
        self.via_relation_name = via_relation_name
        self.via_fk_name = via_fk_name

    def get(self, offset=0, base=0, extra_fields=[]):
        fields = list(self.fields)
        fields += extra_fields
        return self.connector.read(self.table_name, self.filters, fields, self.relations, self.order_fields, offset,
                                   base)

    @property
    def db_name(self):
        return self.connector.db_name

    def count(self):
        data = self.connector.read(self.table_name, self.filters, ['id'], self.relations, self.order_fields, 0, 0)
        if self.connector._is_request_for_one_object(self.filters):
            return len(data.get(self.table_name))
        return int(data.get('@rowCount'))

    def fetch(self, offset, base, extra_fields=[]):
        return self.get(offset, base or 0, extra_fields).get(self.table_name)

    def add_ordering(self, field_name, is_asc):
        self.order_fields.append('%s@%s' % (field_name, is_asc and 'A' or 'D'))

    def add_filter(self, filter):
        self.filters.append(filter)

    def add_relation(self, relation_name):
        self.relations.append(relation_name)

    def _is_via(self):
        return self.via_table_name and self.via_relation_name and self.via_fk_name

    def insert(self, data):
        if self._is_via():
            return self._store_via(data)
        else:
            output = self.connector.write(self.table_name, data)
            return output.get('results')[0].get('id')

    def _store_via(self, data):
        for obj_data in data:
            store_view_db_query = RestQuery(self.connector, self.via_table_name, ['id'],
                                            [self.via_relation_name])
            store_view_db_query.add_filter(ElementaryFilter('id', '=',
                                                            obj_data.get(self.via_fk_name), False))
            via_data = {'id': str(obj_data.get(self.via_fk_name))}
            via_data[self.via_relation_name] = [self.connector._prepare_obj_data(obj_data)]

            store_view_db_query.update(via_data)
            store_view_db_query.connector._clear_table_cache(self.table_name)

            if 'id' in obj_data:
                return obj_data['id']
            else:
                query = RestQuery(self.connector, self.table_name, ['id'])
                query.add_filter(ElementaryFilter(self.via_fk_name, '=',
                                                  obj_data.get(self.via_fk_name), False))

                query.add_filter(ElementaryFilter('id', '=',
                                                  '\'%s\'' % obj_data.get('external-ids'), False))
                return query.fetch(0, 1)[0].get('id')

    def _get_deleted_objects_via_obj(self):
        result = {}
        for entity in self.get(extra_fields=['id', self.via_fk_name]).get(self.table_name):
            parent_id = entity['%s@ref' % self.via_fk_name].split('/')[-1][:-5]
            deleted_pks = result.get(parent_id, [])
            deleted_pks.append(entity.get('id'))
            result[parent_id] = deleted_pks
        return result

    def _delete_via(self):
        for parent_pk, deleted_pks in self._get_deleted_objects_via_obj().items():
            store_view_db_query = RestQuery(
                self.connector, self.via_table_name, ['id'], [self.via_relation_name]
            )
            store_view_db_query.add_filter(ElementaryFilter('id', '=', parent_pk, False))
            parent_data = store_view_db_query.fetch(0, 0, extra_fields=['%s(id)' % self.via_relation_name])[0]
            child_data = parent_data.get(self.via_relation_name, [])
            parent_data[self.via_relation_name] = filtered_child_data = []

            for relation_obj in child_data:
                if relation_obj.get('id') not in deleted_pks:
                    filtered_child_data.append({'id': relation_obj.get('id')})
            parent_data['%s@removeAll' % self.via_relation_name] = 'true'
            store_view_db_query.update(parent_data)
            store_view_db_query.connector._clear_table_cache(self.table_name)

    def update(self, data):
        updated_data = data
        data = []
        if not self.connector._is_request_for_one_object(self.filters):
            for entity in self.get().get(self.table_name):
                entity_value = updated_data.copy()
                pk = entity.get('id')
                entity_value['id'] = entity.get('id')
                data.append(entity_value)
        else:
            updated_data['id'] = self.filters[0].value
            data.append(updated_data)

        if self._is_via():
            self._store_via(data)
        else:
            self.connector.write(self.table_name, data)
            return len(data)

    def delete(self):
        if self._is_via():
            self._delete_via()
        else:
            self.connector.delete(self.table_name, self.filters)
