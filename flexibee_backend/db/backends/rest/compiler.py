import datetime
import sys
import requests

from functools import wraps

from django.db.models.sql.constants import MULTI, SINGLE
from django.db.models.sql.where import AND, OR
from django.db.utils import DatabaseError, IntegrityError
from django.utils.tree import Node

from django.db.models.fields import Field
from django.db.models.fields.related import RelatedField
from django.db.models.sql.subqueries import UpdateQuery

from djangotoolbox.db.basecompiler import NonrelQuery, NonrelCompiler, \
    NonrelInsertCompiler, NonrelUpdateCompiler, NonrelDeleteCompiler, EmptyResultSet

from dateutil.parser import parse
from dateutil.parser import DEFAULTPARSER

from .connection import RestQuery
from django.utils.timezone import get_current_timezone
from django.utils import timezone
from django.conf import settings


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
    'startswith': 'begins',
    'endswith': 'ends',
}



class BackendQuery(NonrelQuery):

    def __init__(self, compiler, fields):
        super(BackendQuery, self).__init__(compiler, fields)
        self.connector = self.connection.connector
        self.db_query = RestQuery(self.connection.connector, self.query.model._meta.db_table,
                                  [field.db_column or field.get_attname() for field in fields])

    # This is needed for debugging
    def __repr__(self):
        # TODO: add some meaningful query string for debugging
        return '<BackendQuery: ...>'

    def fetch(self, low_mark=0, high_mark=None):

        if hasattr(self.query, 'is_empty') and self.query.is_empty():
            return

        if high_mark is None:
            base = None
        else:
            base = high_mark - low_mark

        for entity in self.db_query.fetch(low_mark, base):

            for field in self.fields:
                db_field_name = field.db_column or field.get_attname()
                entity[db_field_name] = self.compiler.convert_value_from_db(field.get_internal_type(),
                                                                            entity[db_field_name], db_field_name,
                                                                            entity)
            yield entity

    def count(self, limit=None):
        return self.db_query.count()

    def delete(self):
        self.db_query.delete()

    def update(self, data):
        return self.db_query.update(data)

    def order_by(self, ordering):
        if isinstance(ordering, (list, tuple)):
            for field, is_asc in ordering:
                self.db_query.add_ordering(field.db_column or field.get_attname(), is_asc)

    # This function is used by the default add_filters() implementation which
    # only supports ANDed filter rules and simple negation handling for
    # transforming OR filters to AND filters:
    # NOT (a OR b) => (NOT a) AND (NOT b)
    def add_filter(self, field, lookup_type, negated, value):
        print 'filter'
        print field

        try:
            op = OPERATORS_MAP[lookup_type]
        except KeyError:
            raise DatabaseError("Lookup type %r isn't supported" % lookup_type)

        # Handle special-case lookup types
        if callable(op):
            op, value = op(lookup_type, value)

        db_value = self.compiler.convert_value_for_db(field.get_internal_type(), value)
        self.db_query.add_filter(field.db_column or field.get_attname(), op, db_value, negated)


class SQLCompiler(NonrelCompiler):
    query_class = BackendQuery

    # This gets called for each field type when you fetch() an entity.
    # db_type is the string that you used in the DatabaseCreation mapping
    def convert_value_from_db(self, db_type, value, field, entity):
        if db_type == 'ForeignKey':
            if '%s@ref' % field in entity:
                return entity['%s@ref' % field].split('/')[-1][:-5]
            else:
                return None
        if db_type == 'FloatField':
            return float(value)
        if db_type == 'IntegerField':
            return int(value)
        if db_type == 'DateField':
            return parse(value.split('+')[0]).date()

        if isinstance(value, str):
            # Always retrieve strings as unicode
            value = value.decode('utf-8')
        return value

    # This gets called for each field type when you insert() an entity.
    # db_type is the string that you used in the DatabaseCreation mapping
    def convert_value_for_db(self, db_type, value):
        if db_type == 'DateField':
            tz = value.strftime('%z') or '+0000'
            value = '%s%s' % (value.strftime('%Y-%m-%d'), '%s:%s' % (tz[:3], tz[3:]))
            return value

        if isinstance(value, str):
            # Always store strings as unicode
            value = value.decode('utf-8')
        elif isinstance(value, (list, tuple)) and len(value) and \
                db_type.startswith('ListField:'):
            db_sub_type = db_type.split(':', 1)[1]
            value = [self.convert_value_for_db(db_sub_type, subvalue)
                     for subvalue in value]
        return value


# This handles both inserts and updates of individual entities
class SQLInsertCompiler(NonrelInsertCompiler, SQLCompiler):

    def insert(self, data, return_id=False):
        db_query = RestQuery(self.connection.connector, self.query.model._meta.db_table)

        print 'insert data!!!!'
        pk = db_query.insert(data)
        return pk


    def execute_sql(self, return_id=False):
        print 'execute'
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

                # Prepare value for database, note that query.values have
                # already passed through get_db_prep_save.
                value = self.ops.value_for_db(value, field)
                db_value = self.convert_value_for_db(field.get_internal_type(), value)
                field_values[field.column] = db_value
            to_insert.append(field_values)

        key = self.insert(to_insert, return_id=return_id)

        # Pass the key value through normal database deconversion.
        return self.ops.convert_values(self.ops.value_from_db(key, pk_field), pk_field)

class SQLUpdateCompiler(NonrelUpdateCompiler, SQLCompiler):

    def update(self, values):
        db_values = {}

        for field, value in values:
            db_value = self.convert_value_for_db(field.get_internal_type(), value)
            db_field = field.db_column or field.get_attname()
            db_values[db_field] = db_value

        return self.build_query([self.query.model._meta.pk]).update(db_values)


class SQLDeleteCompiler(NonrelDeleteCompiler, SQLCompiler):
    pass
