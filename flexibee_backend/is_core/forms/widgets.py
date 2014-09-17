from django.forms.widgets import ClearableFileInput, Widget
from django.utils.html import format_html
from django.utils.encoding import force_text
from django.utils.safestring import mark_safe
from django.utils.http import urlquote


class EmptyWidget(Widget):
    """
    Empty widget is used for inline form fields where value can not be set for first save of the object
    """

    def render(self, name, value, attrs=None):
        return ''


class AttachementWidget(ClearableFileInput):

    def attachment_url(self, attachment):
        return 'attachment/%s__%s' % (attachment.pk, urlquote(attachment.filename))

    def render(self, name, value, attrs=None):
        if value:
            return mark_safe(format_html(self.url_markup_template, self.attachment_url(value), force_text(value)))

        substitutions = {
            'initial_text': self.initial_text,
            'input_text': self.input_text,
            'clear_template': '',
            'clear_checkbox_label': self.clear_checkbox_label,
        }
        template = '%(input)s'
        substitutions['input'] = super(ClearableFileInput, self).render(name, value, attrs)
        return mark_safe(template % substitutions)
