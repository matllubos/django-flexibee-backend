import decimal

from django.db.models.sql.constants import MULTI, SINGLE
from django.db.utils import DatabaseError, IntegrityError
from django.db.models.sql import aggregates as sqlaggregates
from django.db.models.sql.where import AND
from django.db.models.fields import NOT_PROVIDED
from django.utils.tree import Node
from django.utils.encoding import force_text
from django.core.exceptions import ObjectDoesNotExist

from djangotoolbox.db.basecompiler import (NonrelQuery, NonrelCompiler,
                                           NonrelInsertCompiler, NonrelUpdateCompiler,
                                           NonrelDeleteCompiler, EmptyResultSet, get_selected_fields)

from dateutil.parser import parse

from .connection import RestQuery

from flexibee_backend.models import StoreViaForeignKey, CompanyForeignKey, RemoteFileField
from flexibee_backend.models.fields import ItemsField
from flexibee_backend.db.backends.rest.filters import ElementaryFilter, NotFilter, AndFilter, OrFilter, \
    ContradictionFilter



# TODO: Change this to match your DB
# Valid query types (a dictionary is used for speedy lookups).
OPERATORS_MAP = {
    'exact': '=',
    'gt': '>',
    'gte': '>=',
    'lt': '<',
    'lte': '<=',
    'in': 'in',
    'isnull': 'is null',
    'like': 'like',
    'icontains': 'like',
    'startswith': 'begins',
    'endswith': 'ends',
}

DEFAULT_READONLY_FIELD_CLASSES = (RemoteFileField, ItemsField)


def get_field_db_name(field):
    return field.db_column or field.get_attname()


class BackendQuery(NonrelQuery):

    def __init__(self, compiler, fields):
        super(BackendQuery, self).__init__(compiler, fields)
        self.connector = self.connection.connector
        self.model = self.query.model
        self.internal_model = self.query.model._internal_model
        self.internal_fields = self.query.model._internal_fields or ()

        store_via_field = self._get_store_via()

        query_kwargs = {}

        if store_via_field:
            query_kwargs = {
                'via_table_name': store_via_field.rel.to._meta.db_table,
                'via_relation_name': store_via_field.db_relation_name,
                'via_fk_name': store_via_field.db_column or store_via_field.get_attname()
            }

        self.db_query = RestQuery(self.connection.connector, self.query.model._meta.db_table,
                                  self._get_db_field_names(), **query_kwargs)

    def _get_db_field_names(self):
        return [get_field_db_name(field) for field in self.fields if not isinstance(field, CompanyForeignKey)
                                                                        and field.name not in self.internal_fields]

    # This is needed for debugging
    def __repr__(self):
        return '<FlexibeeQuery>'

    def _field_db_name(self, field):
        return field.db_column or field.get_attname()

    def _get_store_via(self):
        for field in self.model._meta.fields:
            if isinstance(field, StoreViaForeignKey):
                return field

    def fetch(self, low_mark=0, high_mark=None):
        if hasattr(self.query, 'is_empty') and self.query.is_empty():
            return

        if high_mark is None:
            base = None
        else:
            base = high_mark - low_mark

        for entity in self.db_query.fetch(low_mark, base):
            output = {}
            for field in self.fields:
                db_field_name = get_field_db_name(field)
                if db_field_name == 'flexibee_company_id':
                    output[db_field_name] = field.rel.to._default_manager.get(flexibee_db_name=self.db_query.db_name).pk
                elif isinstance(field, (RemoteFileField, ItemsField)):
                    pass
                else:
                    output[db_field_name] = self.compiler.convert_value_from_db(
                        field.get_internal_type(), entity.get(db_field_name), db_field_name, entity)
            self._fetch_internal_model(output)
            yield output

    def count(self, limit=None):
        return self.db_query.count()

    def delete(self):
        self._delete_internal_models(self.db_query.delete())

    def _fetch_internal_model(self, output):
        if self.internal_model:
            try:
                internal_model_obj = self.internal_model._default_manager.get(
                    flexibee_obj_id=output['id'], flexibee_company__flexibee_db_name=self.db_query.db_name
                )
                for field in self.fields:
                    db_field_name = get_field_db_name(field)
                    if field.name in self.internal_fields:
                        output[db_field_name] = getattr(internal_model_obj, db_field_name, None)
            except ObjectDoesNotExist:
                pass

    def _update_internal_model(self, data, pk):
        if self.internal_model:
            try:
                internal_model_obj = self.internal_model._default_manager.get(
                    flexibee_obj_id=pk, flexibee_company__flexibee_db_name=self.db_query.db_name
                )
            except ObjectDoesNotExist:
                company_model = self.internal_model._meta.get_field('flexibee_company').rel.to
                internal_model_obj = self.internal_model(
                    flexibee_obj_id=pk,
                    flexibee_company=company_model._default_manager.get(flexibee_db_name=self.db_query.db_name)
                )

            for field in self.fields:
                if field.name in self.internal_fields:
                    db_field_name = get_field_db_name(field)
                    setattr(internal_model_obj, db_field_name, data.get(db_field_name, None))
            internal_model_obj.save()

    def _delete_internal_models(self, pks):
        if self.internal_model:
            self.internal_model._default_manager.filter(flexibee_obj_id__in=pks,
                flexibee_company__flexibee_db_name=self.db_query.db_name).delete()

    def _filter_internal_data(self, data):
        internal_data = {}
        for field in self.fields:
            db_field_name = get_field_db_name(field)
            if field.name in (self.internal_fields or ()) and db_field_name in data:
                internal_data[db_field_name] = data[db_field_name]
                del data[db_field_name]
        return internal_data

    def insert(self, data):
        data = data[0]
        internal_data = self._filter_internal_data(data)
        pk = self.db_query.insert(data)
        self._update_internal_model(internal_data, pk)
        return pk

    def update(self, data):
        internal_data = self._filter_internal_data(data)
        pks = self.db_query.update(data)
        for pk in pks:
            self._update_internal_model(internal_data, pk)
        return pks

    def order_by(self, ordering):
        if isinstance(ordering, (list, tuple)):
            for field, is_asc in ordering:
                self.db_query.add_ordering(field.db_column or field.get_attname(), is_asc)

    def _generate_elementary_filter(self, field, lookup_type, negated, value):
        if field.name in self.internal_fields:
            value = tuple(self.internal_model.objects.filter(flexibee_company__flexibee_db_name=self.db_query.db_name)\
                                                     .filter(**{'%s__%s' % (field.name, lookup_type): value})\
                                                     .values_list('flexibee_obj_id', flat=True))
            lookup_type = 'in'
            field = self.model._meta.pk

        try:
            op = OPERATORS_MAP[lookup_type]
        except KeyError:
            raise DatabaseError("Lookup type %r isn't supported" % lookup_type)

        # Handle special-case lookup types
        if callable(op):
            op, value = op(lookup_type, value)

        if op == 'in' and not value:
            return ContradictionFilter(negated)

        db_value = self.compiler.convert_filter_value_for_db(field.get_internal_type(), value)

        return ElementaryFilter(self._field_db_name(field), op, db_value, negated)

    def _generate_filter(self, filters):
        children = self._get_children(filters.children)
        if len(children) == 0:
            return None
        elif len(children) == 1:
            child = children[0]
            if isinstance(child, Node):
                db_filter = self._generate_filter(child)
            else:
                field, lookup_type, value = self._decode_child(child)
                db_filter = self._generate_elementary_filter(field, lookup_type, self._negated, value)

        else:
            if filters.connector == AND:
                db_filter = AndFilter()
            else:
                db_filter = OrFilter()

            for child in children:
                if isinstance(child, Node):
                    db_filter.append(self._generate_filter(child))
                    continue
                field, lookup_type, value = self._decode_child(child)
                db_filter.append(self._generate_elementary_filter(field, lookup_type, self._negated, value))

        if filters.negated:
            return NotFilter(db_filter)
        return db_filter

    def add_filters(self, filters):
        db_filter = self._generate_filter(filters)
        if db_filter is not None:
            self.db_query.add_filter(db_filter)

    def get_fields(self):
        """
        Returns fields which should get loaded from the back-end by the
        current query.
        """

        # We only set this up here because related_select_fields isn't
        # populated until execute_sql() has been called.
        fields = get_selected_fields(self.query)

        # If the field was deferred, exclude it from being passed
        # into `resolve_columns` because it wasn't selected.
        only_load = self.deferred_to_columns()
        if only_load:
            db_table = self.model._meta.db_table
            only_load = dict((k, v) for k, v in only_load.items()
                             if v or k == db_table)
            if len(only_load.keys()) > 1:
                raise DatabaseError("Multi-table inheritance is not "
                                    "supported by non-relational DBs %s." %
                                    repr(only_load))
            fields = [f for f in fields if db_table in only_load and
                      f.column in only_load[db_table]]

        query_model = self.model
        if query_model._meta.proxy:
            query_model = query_model._meta.proxy_for_model

        return fields


class SQLDataCompiler(object):

    def convert_filter_value_for_db(self, db_type, value):
        if value is None:
            return value
        if isinstance(value, (list, tuple)):
            return '(%s)' % ', '.join([force_text(self.convert_filter_value_for_db(db_type, subval))
                                       for subval in value])
        if isinstance(value, str):
            # Always store strings as unicode
            value = value.decode('utf-8')
        if db_type == 'DateField':
            return value.strftime('%Y-%m-%d')
        if db_type == 'BooleanField':
            return value and 'true' or 'false'
        if db_type in ['TextField', 'CharField']:
            return '\'%s\'' % value

        return value

    # This gets called for each field type when you fetch() an entity.
    # db_type is the string that you used in the DatabaseCreation mapping
    def convert_value_from_db(self, db_type, value, field, entity):
        if db_type in ['ForeignKey', 'StoreViaForeignKey']:
            if '%s@ref' % field in entity:
                return entity['%s@ref' % field].split('/')[-1][:-5]
            else:
                return None

        if db_type == 'FlexibeeExtKey':
            return value
        if (value == '' or value is None) and db_type in ['DecimalField', 'FloatField', 'IntegerField',
                                                          'DateField', 'BooleanField']:
            return None

        if db_type == 'DecimalField':
            return decimal.Decimal(value)
        if db_type == 'FloatField':
            return float(value)
        if db_type == 'IntegerField':
            return int(value)
        if db_type == 'DateField':
            return parse(value.split('+')[0]).date()
        if db_type == 'BooleanField':
            return value == 'true' and True or False

        if isinstance(value, str):
            # Always retrieve strings as unicode
            value = value.decode('utf-8')
        return value

    # This gets called for each field type when you insert() an entity.
    # db_type is the string that you used in the DatabaseCreation mapping
    def convert_value_for_db(self, db_type, value):
        if value is None:
            return value

        if db_type == 'DateField':
            tz = value.strftime('%z') or '+0000'
            value = '%s%s' % (value.strftime('%Y-%m-%d'), '%s:%s' % (tz[:3], tz[3:]))
            return value
        if db_type == 'BooleanField':
            return value and 'true' or 'false'

        if isinstance(value, str):
            # Always store strings as unicode
            value = value.decode('utf-8')
        elif isinstance(value, (list, tuple)) and len(value) and \
                db_type.startswith('ListField:'):
            db_sub_type = db_type.split(':', 1)[1]
            value = [self.convert_value_for_db(db_sub_type, subvalue)
                     for subvalue in value]
        return value


class SQLCompiler(SQLDataCompiler, NonrelCompiler):
    query_class = BackendQuery

    def execute_sql(self, result_type=MULTI):
        """
        Handles SQL-like aggregate queries. This class only emulates COUNT
        by using abstract NonrelQuery.count method.
        """
        aggregates = self.query.aggregate_select.values()

        # Simulate a count().
        if aggregates:
            assert len(aggregates) == 1
            aggregate = aggregates[0]
            assert isinstance(aggregate, sqlaggregates.Count)
            opts = self.query.get_meta()
            if aggregate.col != '*' and \
                aggregate.col != (opts.db_table, opts.pk.column):
                raise DatabaseError("This database backend only supports "
                                    "count() queries on the primary key.")

            count = self.get_count()
            if result_type is SINGLE:
                return [count]
            elif result_type is MULTI:
                return [[count]]

        # Exists
        if self.query.extra == {'a': (u'1', [])}:
            return self.has_results()


        raise NotImplementedError("The database backend only supports "
                                  "count() queries.")

    def check_query(self):
        """
        Checks if the current query is supported by the database.

        In general, we expect queries requiring JOINs (many-to-many
        relations, abstract model bases, or model spanning filtering),
        using DISTINCT (through `QuerySet.distinct()`, which is not
        required in most situations) or using the SQL-specific
        `QuerySet.extra()` to not work with nonrel back-ends.
        """
        if hasattr(self.query, 'is_empty') and self.query.is_empty():
            raise EmptyResultSet()
        if (len([a for a in self.query.alias_map if
                 self.query.alias_refcount[a]]) > 1 or
            self.query.distinct or (self.query.extra and self.query.extra != {'a': (u'1', [])}) or self.query.having):
            raise DatabaseError("This query is not supported by the database.")

    def _make_result(self, entity, fields):
        """
        Decodes values for the given fields from the database entity.

        The entity is assumed to be a dict using field database column
        names as keys. Decodes values using `value_from_db` as well as
        the standard `convert_values`.
        """
        result = []
        for field in fields:
            value = entity.get(field.column, NOT_PROVIDED)
            if value is NOT_PROVIDED:
                value = field.get_default()
            else:
                value = self.ops.value_from_db(value, field)
                value = self.query.convert_values(value, field,
                                                  self.connection)
            result.append(value)
        return result


# This handles both inserts and updates of individual entities
class SQLInsertCompiler(NonrelInsertCompiler, SQLCompiler):

    def insert(self, data, return_id=False):
        query = self.build_query()
        return query.insert(data)

    def execute_sql(self, return_id=False):
        to_insert = []
        pk_field = self.query.get_meta().pk

        for obj in self.query.objs:
            field_values = {}
            for field in self.query.fields:
                value = field.get_db_prep_save(
                    getattr(obj, field.attname) if self.query.raw else field.pre_save(obj, obj._state.adding),
                    connection=self.connection
                )
                if value is None and not field.null and not field.primary_key:
                    raise IntegrityError("You can't set %s (a non-nullable "
                                         "field) to None!" % field.name)

                if field.get_attname() != 'flexibee_company_id' \
                    and field.get_attname() not in self.query.model._flexibee_meta.readonly_fields \
                    and not isinstance(field, DEFAULT_READONLY_FIELD_CLASSES):

                    # Prepare value for database, note that query.values have
                    # already passed through get_db_prep_save.
                    value = self.ops.value_for_db(value, field)
                    db_value = self.convert_value_for_db(field.get_internal_type(), value)
                    if db_value is not None:
                        field_values[field.column] = db_value
            to_insert.append(field_values)

        key = self.insert(to_insert, return_id=return_id)

        # Pass the key value through normal database deconversion.
        return self.ops.convert_values(self.ops.value_from_db(key, pk_field), pk_field)


class SQLUpdateCompiler(NonrelUpdateCompiler, SQLCompiler):

    def update(self, values):
        db_values = {}
        query = self.build_query()

        for field, value in values:
            if field.get_attname() != 'flexibee_company_id'\
                and field.get_attname() not in self.query.model._flexibee_meta.readonly_fields\
                and not isinstance(field, DEFAULT_READONLY_FIELD_CLASSES):

                db_value = self.convert_value_for_db(field.get_internal_type(), value)
                db_field = get_field_db_name(field)

                if db_value is not None:
                    db_values[db_field] = db_value
        return query.update(db_values)


class SQLDeleteCompiler(NonrelDeleteCompiler, SQLCompiler):
    pass
