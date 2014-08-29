from django.forms import fields

from flexibee_backend.db.fields.widgets import AttachementWidget


class AttachementsField(fields.Field):
    widget = AttachementWidget
    
    def __init__(self, atachement_manager, required=True, widget=None, label=None, initial=None,
                 help_text='', error_messages=None, show_hidden_initial=False,
                 validators=[], localize=False):
        widget = self.widget(atachement_manager)
        super(AttachementsField, self).__init__(required, widget, label, None,
                                                help_text, error_messages, show_hidden_initial,
                                                validators, localize)
        
