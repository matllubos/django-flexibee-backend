import requests
import json
import logging
import decimal

from django.db.utils import DatabaseError
from django.utils.encoding import force_text
from django.utils.http import urlquote

from flexibee_backend.db.backends.rest.exceptions import (
    ChangesNotActivatedFlexibeeResponseError, FlexibeeResponseError, FlexibeeDatabaseError
)
from flexibee_backend.db.backends.rest.filters import ElementaryFilter
from flexibee_backend.db.backends.rest.cache import ResponseCache, ModelCacheKeysGenerator, ItemCacheKeysGenerator


def decimal_default(obj):
    if isinstance(obj, decimal.Decimal):
        return str(obj)
    raise TypeError


class BaseConnector(object):

    JSON_HEADER = {'Accept': 'application/json'}
    logger = logging.getLogger('flexibee-backend')

    def __init__(self, username, password, hostname):
        self.username = username
        self.password = password
        self.hostname = hostname

    def _serialize(self, data):
        return json.dumps({'winstrom': data}, default=decimal_default)

    def _deserialize(self, url, r, *keys):
        try:
            data = r.json().get('winstrom')
            for key in keys:
                if not data.has_key(key):
                    raise FlexibeeResponseError(url, r, 'Cannot parse response content, mising key %s' % key)
                data = data.get(key)
            return data
        except ValueError:
            raise FlexibeeResponseError(url, r, 'Cannot parse response content')

    def http_get(self, url):
        self.logger.info('Sending GET to %s' % url)
        r = requests.get(url, auth=(self.username, self.password))
        self.logger.info('Receiving response %s' % r.status_code)
        return r

    def http_put(self, url, data=None, headers=None, serialize=True):
        self.logger.info('Sending PUT to %s' % url)
        if data is None:
            r = requests.put(url, auth=(self.username, self.password))
        else:
            if serialize:
                data = self._serialize(data)
            r = requests.put(url, data=data, headers=headers, auth=(self.username, self.password))
        self.logger.info('Receiving response %s' % r.status_code)
        return r

    def http_delete(self, url):
        self.logger.info('Sending DELETE to %s' % url)
        r = requests.delete(url, auth=(self.username, self.password))
        self.logger.info('Receiving response %s' % r.status_code)
        return r


class DatabaseBaseConnector(BaseConnector):

    URL = 'https://%(hostname)s/c/%(db_name)s/%(table_name)s%(extra)s.%(type)s?%(query_string)s'

    def __init__(self, *args, **kwargs):
        super(DatabaseBaseConnector, self).__init__(*args, **kwargs)
        self.db_name = None

    def _check_settings(self, table_name):
        if not self.db_name:
            raise DatabaseError('For flexibee DB connector must be set company: %s' % table_name)

    def _generate_url(self, extra, table_name, query_string, type):
        return self.URL % {
            'hostname': self.hostname, 'db_name': self.db_name, 'extra': extra, 'table_name': table_name,
            'query_string': query_string, 'type': type
        }

    def reset(self):
        self.db_name = None


class CachedConnector(DatabaseBaseConnector):
    CHANGES_TABLE_NAME = 'changes'

    def __init__(self, *args, **kwargs):
        super(CachedConnector, self).__init__(*args, **kwargs)
        self._cache = None

    def _get_cache(self, *args):
        if not self._cache:
            self._cache = ResponseCache(self)
        return self._cache

    def _get_cache_keys_generator(self, *args):
        raise NotImplementedError

    def _clear_table_cache(self, table_name):
        return self._get_cache(self.db_name, table_name).clear(self._get_cache_keys_generator(self.db_name, table_name))

    def _get_from_cache(self, table_name, *args):
        return self._get_cache(self.db_name, table_name, *args).get(
            self._get_cache_keys_generator(self.db_name, table_name, *args)
        )

    def _add_to_cache(self, data, table_name, *args):
        return self._get_cache(self.db_name, table_name, *args).add(
            data, self._get_cache_keys_generator(self.db_name, table_name, *args)
        )

    def changes(self, from_version):
        self._check_settings(self.CHANGES_TABLE_NAME)

        url = self._generate_url('', self.CHANGES_TABLE_NAME, 'start=%s' % from_version, 'json')
        r = self.http_get(url)

        if r.status_code != 200:
            raise ChangesNotActivatedFlexibeeResponseError(url, r)

        return (
            int(self._deserialize(url, r, '@globalVersion')),
            set([change.get('@evidence') for change in self._deserialize(url, r, 'changes')])
        )

    def activate_changes(self):
        self._check_settings('changes/enable')
        url = self._generate_url('', 'changes/enable', '', 'json')
        r = self.http_put(url)
        if r.status_code != 200:
            raise FlexibeeResponseError(url, r, 'Cannot activate changes')

    def reset(self):
        super(CachedConnector, self).reset()
        if self._cache:
            self._cache.reset()


class ModelConnector(CachedConnector):

    def _get_cache_keys_generator(self, *args):
        return ModelCacheKeysGenerator(*args)

    def prepare_obj_ids(self, obj_data):
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
            ('detail', 'custom:%s' % ','.join(fields))
        ]

        if relations:
            query_string_list.append(('relations', ','.join(relations)))

        for field in ordering:
            query_string_list.append(('order', field))

        query_string_list.append(('start', offset))
        query_string_list.append(('limit', base))
        query_string_list.append(('add-row-count', 'true'))

        return '&'.join(['%s=%s' % (key, val) for key, val in query_string_list])

    def read(self, table_name, filters, fields, relations, ordering, offset, base, store_via_table_name):
        self._check_settings(table_name)

        data = self._get_from_cache(table_name, filters, fields, relations, ordering, offset, base,
                                    store_via_table_name)
        if data is not None:
            return data

        url = self._generate_url(
            self._get_extra_filter(filters), table_name,
            self._get_query_string(fields, relations, ordering, offset, base), 'json'
        )
        r = self.http_get(url)

        if r.status_code in [200, 201] :
            return self._add_to_cache(
                self._deserialize(url, r, table_name), table_name, filters, fields, relations, ordering, offset, base,
                store_via_table_name
            )
        else:
            raise FlexibeeResponseError(url, r, 'Model connector read method error')

    def count(self, table_name, filters, ordering, store_via_table_name):
        self._check_settings(table_name)

        fields = ['id']
        relations = []
        offset = 0
        base = 1

        data = self._get_from_cache(table_name, filters, fields, relations, ordering, offset, base,
                                    store_via_table_name, 'count')
        if data is not None:
            return data

        url = self._generate_url(
            self._get_extra_filter(filters), table_name,
            self._get_query_string(fields, relations, ordering, offset, base), 'json'
        )
        r = self.http_get(url)

        if r.status_code in [200, 201]:
            return self._add_to_cache(
                int(self._deserialize(url, r, '@rowCount')), table_name, filters, fields, relations, ordering,
                offset, base, store_via_table_name, 'count'
            )
        else:
            raise FlexibeeResponseError(url, r, 'Model connector count method error')

    def write(self, table_name, data):
        self._check_settings(table_name)

        url = self._generate_url('', table_name, '', 'json')
        r = self.http_put(
            url, {table_name: [self.prepare_obj_ids(obj_data) for obj_data in data]},
            self.JSON_HEADER
        )

        if r.status_code in [200, 201]:
            self._clear_table_cache(table_name)
            return self._deserialize(url, r, 'results')
        else:
            raise FlexibeeResponseError(url, r, 'Model connector write method error')

    def delete(self, table_name, filters):
        self._check_settings(table_name)

        url = self._generate_url('', table_name, '', 'json')
        data = {
            table_name: {
                '@action': 'delete',
                '@filter': self._construct_filter(filters),
            }
        }
        r = self.http_put(url, data, self.JSON_HEADER)
        if r.status_code == 201:
            self._clear_table_cache(table_name)
            return self._deserialize(url, r, 'results')
        else:
            raise FlexibeeResponseError(url, r, 'Model connector delete method error')

    def get_response(self, table_name, id, type):
        self._check_settings(table_name)
        return self.http_get(self._generate_url('/%s' % id, table_name, '', type))


class AttachmentConnector(CachedConnector):

    def _get_cache_keys_generator(self, *args):
        return ItemCacheKeysGenerator('priloha', *args)

    def read(self, table_name, parent_id, pk=None):
        self._check_settings(table_name)

        extra = '/%s/prilohy' % parent_id
        if pk:
            extra = '/'.join((extra, str(pk)))

        data = self._get_from_cache(table_name, extra)
        if data is not None:
            return data

        url = self._generate_url(
            extra, table_name, 'detail=custom:id,contentType,nazSoub,contentType,poznam,link', 'json'
        )
        r = self.http_get(url)
        if r.status_code == 200:
            return self._add_to_cache(self._deserialize(url, r, 'priloha'), table_name, extra)
        elif r.status_code == 404:
            return self._add_to_cache([], table_name, extra)
        else:
            raise FlexibeeResponseError(url, r, 'Attachment connector read method error')

    def _get_last_pk(self, table_name, parent_id):
        url = 'https://%(hostname)s/c/%(db_name)s/%(table_name)s/%(parent_id)s/prilohy.json%(extra)s' % {
            'hostname': self.hostname, 'db_name': self.db_name,
            'table_name': table_name, 'parent_id': parent_id,
            'extra': '?order=id@D&detail=custom:id'
        }
        r = self.http_get(url)

        if r.status_code != 200:
            raise FlexibeeResponseError(url, r, 'Rest PUT method error')
        return self._deserialize(url, r, 'priloha')[0].get('id')

    def _write_new(self, table_name, parent_id, data):
        url = 'https://%(hostname)s/c/%(db_name)s/%(table_name)s/%(parent_id)s/prilohy/new/%(filename)s' % {
            'hostname': self.hostname, 'db_name': self.db_name,
            'table_name': table_name, 'parent_id': parent_id, 'filename': data.get('nazSoub')
        }
        headers = {'content-type': data.get('contentType')}
        r = self.http_put(url, data, headers)
        if r.status_code not in [200, 201]:
            raise FlexibeeResponseError(url, r, 'Attachment connector write method error')

        self._clear_table_cache(table_name)
        return self._get_last_pk(table_name, parent_id)

    def _update(self, table_name, parent_id, data, pk):
        url = 'https://%(hostname)s/c/%(db_name)s/%(table_name)s/%(parent_id)s/prilohy/%(pk)s.json' % {
            'hostname': self.hostname, 'db_name': self.db_name,
            'table_name': table_name, 'parent_id': parent_id, 'pk': pk
        }
        r = self.http_put(url, {'priloha': data}, self.JSON_HEADER)

        if r.status_code not in [200, 201]:
            raise FlexibeeResponseError(url, r, 'Attachment connector write method error')
        self._clear_table_cache(table_name)
        return pk

    def write(self, table_name, parent_id, data):
        self._check_settings(table_name)

        pk = data.pop('pk', None)
        if not pk:
            return self._write_new(table_name, parent_id, data)
        else:
            return self._update(table_name, parent_id, data, pk)

    def delete(self, table_name, parent_id, pk):
        self._check_settings(table_name)

        url = 'https://%(hostname)s/c/%(db_name)s/%(table_name)s/%(parent_id)s/prilohy/%(pk)s.json' % {
            'hostname': self.hostname, 'db_name': self.db_name, 'table_name': table_name, 'parent_id': parent_id,
            'pk': pk
        }

        r = self.http_delete(url)

        if r.status_code not in [200, 201]:
            raise FlexibeeResponseError(url, r, 'Attachment connector delete method error')
        self._clear_table_cache(table_name)

    def get_response(self, table_name, parent_id, pk):
        self._check_settings(table_name)

        url = 'https://%(hostname)s/c/%(db_name)s/%(table_name)s/%(parent_id)s/prilohy/%(pk)s/content' % {
            'hostname': self.hostname, 'db_name': self.db_name, 'table_name': table_name, 'parent_id': parent_id,
            'pk': pk
        }
        return self.http_get(url)


class RelationConnector(CachedConnector):

    def _get_cache_keys_generator(self, *args):
        return ItemCacheKeysGenerator('vazba', *args)

    def read(self, table_name, id, relation_id=None):
        self._check_settings(table_name)

        extra = '/%s/vazby' % id
        if relation_id:
            extra = '/'.join((extra, str(relation_id)))

        data = self._get_from_cache(table_name, extra)
        if data is not None:
            return data

        url = self._generate_url(extra, table_name, 'detail=custom:id,a,b,typVazbyK,castka,castkaMen', 'json')
        r = self.http_get(url)

        if r.status_code == 200:
            return self._add_to_cache(self._deserialize(url, r, 'vazba'), table_name, extra)
        elif r.status_code == 404:
            return self._add_to_cache([], table_name, extra)
        else:
            raise FlexibeeResponseError(url, r, 'Relation connector read method error')

    def delete(self, table_name, id, data):
        self._check_settings(table_name)

        url = 'https://%(hostname)s/c/%(db_name)s/%(table_name)s/%(id)s.json' % {
            'hostname': self.hostname, 'db_name': self.db_name, 'table_name': table_name, 'id': id
        }

        r = self.http_put(url, {table_name: {'odparovani': data}})
        if r.status_code not in [200, 201]:
            raise FlexibeeResponseError(url, r, 'Rest PUT method error')
        self._clear_table_cache(table_name)

    def write(self, table_name, id, data):
        self._check_settings(table_name)

        url = 'https://%(hostname)s/c/%(db_name)s/%(table_name)s/%(id)s.json' % {
            'hostname': self.hostname, 'db_name': self.db_name, 'table_name': table_name, 'id': id
        }

        r = self.http_put(url, {table_name: {'sparovani': data}})
        if r.status_code not in [200, 201]:
            raise FlexibeeResponseError(url, r, 'Rest PUT method error')
        self._clear_table_cache(table_name)


class RestQuery(object):

    def __init__(self, connector, table_name, fields=None, relations=None, via_table_name=None, via_relation_name=None,
                 via_fk_name=None):
        self.table_name = table_name
        self.connector = connector
        self.fields = fields or []
        self.order_fields = []
        self.filters = []
        self.relations = relations or []
        self.via_table_name = via_table_name
        self.via_relation_name = via_relation_name
        self.via_fk_name = via_fk_name

    def is_request_for_one_object(self, filters):
        return (len(filters) == 1 and isinstance(filters[0], ElementaryFilter) and
                filters[0].field == 'id' and filters[0].op == '=' and not filters[0].negated)

    @property
    def db_name(self):
        return self.connector.db_name

    def fetch(self, offset=None, base=None, extra_fields=None):
        offset = offset or 0
        base = base or 0
        extra_fields = extra_fields or []
        return self.connector.read(
            self.table_name, self.filters, list(self.fields) + extra_fields, self.relations, self.order_fields, offset,
            base, self.via_table_name
        )

    def count(self):
        return self.connector.count(self.table_name, self.filters, self.order_fields, self.via_table_name)

    def add_ordering(self, field_name, is_asc):
        self.order_fields.append('%s@%s' % (field_name, is_asc and 'A' or 'D'))

    def add_filter(self, filter):
        self.filters.append(filter)

    def add_relation(self, relation_name):
        self.relations.append(relation_name)

    def _is_via(self):
        return self.via_table_name and self.via_relation_name and self.via_fk_name

    def _get_id_from_result(self, result):
        if len(result) != 1:
            raise FlexibeeDatabaseError('Result must contain exactly one objects')
        if not result[0].get('id'):
            raise FlexibeeDatabaseError('Result must contain ID')
        return result[0].get('id')

    def _get_ids_from_data(self, data):
        ids = []
        for entity in data:
            if not entity.get('id'):
                raise FlexibeeDatabaseError('Entity must contain ID')
            ids.append(entity.get('id'))
        return ids

    def insert(self, data):
        if self._is_via():
            return self._store_via(data)
        else:
            return self._get_id_from_result(self.connector.write(self.table_name, [data]))

    def _store_via(self, data):
        store_view_db_query = RestQuery(self.connector, self.via_table_name, ['id'],
                                        [self.via_relation_name])
        store_view_db_query.add_filter(ElementaryFilter('id', '=', data.get(self.via_fk_name), False))

        via_data = {'id': str(data.get(self.via_fk_name))}
        via_data[self.via_relation_name] = [self.connector.prepare_obj_ids(data)]

        store_view_db_query.update(via_data)
        store_view_db_query.connector._clear_table_cache(self.table_name)

        if 'id' in data:
            return data['id']
        else:
            query = RestQuery(self.connector, self.table_name, ['id'])
            query.add_filter(ElementaryFilter(self.via_fk_name, '=',
                                              data.get(self.via_fk_name), False))

            query.add_filter(ElementaryFilter('id', '=',
                                                  '\'%s\'' % data.get('external-ids'), False))
            return self._get_id_from_result(query.fetch(0, 1))

    def _get_deleted_objects_via_obj(self):
        result = {}
        for entity in self.fetch(extra_fields=['id', self.via_fk_name]):
            parent_id = entity['%s@ref' % self.via_fk_name].split('/')[-1][:-5]
            deleted_pks = result.get(parent_id, [])
            deleted_pks.append(entity.get('id'))
            result[parent_id] = deleted_pks
        return result

    def _delete_via(self):
        all_deleted_pks = []
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

            all_deleted_pks += deleted_pks
        return all_deleted_pks

    def update(self, data):
        updated_data = data
        data = []
        if not self.is_request_for_one_object(self.filters):
            for entity in self.fetch():
                entity_value = updated_data.copy()
                entity_value['id'] = entity.get('id')
                if self._is_via() and self.via_fk_name not in entity_value:
                    entity_value[self.via_fk_name] = entity.get(self.via_fk_name)
                data.append(entity_value)
        else:
            try:
                if self._is_via() and self.via_fk_name not in updated_data:
                    updated_data[self.via_fk_name] = self.fetch()[0][self.via_fk_name]
                updated_data['id'] = self.filters[0].value
                data.append(updated_data)
            except IndexError:
                # Object does not exists in flexibee DB
                pass

        if self._is_via():
            map(self._store_via, data)
            return self._get_ids_from_data(data)
        else:
            self.connector.write(self.table_name, data)
            return self._get_ids_from_data(data)

    def delete(self):
        if self._is_via():
            return self._delete_via()
        else:
            return self._get_ids_from_data(self.connector.delete(self.table_name, self.filters))
