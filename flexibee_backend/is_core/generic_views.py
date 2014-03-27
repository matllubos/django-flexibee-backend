from django.db.transaction import get_connection


class FlexibeeViewMixin(object):

    def __init__(self, **kwargs):
        super(FlexibeeViewMixin, self).__init__(**kwargs)
        get_connection('flexibee').set_db_name(self.get_company().flexibee_db_name)

    def get_company(self):
        raise NotImplemented
