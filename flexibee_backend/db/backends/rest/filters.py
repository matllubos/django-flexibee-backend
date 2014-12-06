from django.utils.encoding import force_text


class BaseFilter(object):

    def __unicode__(self):
        raise NotImplementedError

    def __cmp__(self, other):
        return cmp(unicode(self), unicode(self))

    def __str__(self):
        return self.__unicode__()


class NotFilter(BaseFilter):

    def __init__(self, child):
        self.child = child

    def __unicode__(self):
        return 'not (%s)' % force_text(self.child)


class ComposedFilter(BaseFilter):
    operator = None

    def __init__(self):
        self.children = []

    def append(self, child):
        self.children.append(child)

    def __unicode__(self):
        return '(%s)' % (' %s ' % (self.operator)).join([force_text(child) for child in self.children])


class AndFilter(ComposedFilter):
    operator = 'and'


class OrFilter(ComposedFilter):
    operator = 'or'


# Trick
class ContradictionFilter(BaseFilter):

    def __init__(self, negated):
        self.negated = negated

    def __unicode__(self):
        if self.negated:
            return 'id>0'
        else:
            return 'id=0'


class ElementaryFilter(BaseFilter):

    def __init__(self, field, op, value, negated):
        self.field = field
        self.op = op
        self.value = value
        self.negated = negated

    def __unicode__(self):
        filter_list = []
        if self.negated:
            filter_list.append('not')

        filter_list += [self.field, self.op, unicode(self.value)]
        return ' '.join(filter_list)
