from django import forms
from django.utils.translation import ugettext_lazy as _

from is_core.forms.forms import SmartForm

from flexibee_backend.is_core.forms.widgets import AttachmentWidget, EmptyWidget


class FlexibeeItemForm(SmartForm):
    """
    Flexibee form for item creation and changes.
    """

    def __init__(self, instance=None, *args, **kwargs):
        self.instance = instance
        initial = kwargs.get('initial', {})
        if instance:
            kwargs['initial'] = self._get_initial(initial, instance)
        super(FlexibeeItemForm, self).__init__(*args, **kwargs)

    def _get_initial(self, initial, instance):
        raise NotImplementedError

    def save(self, commit=False):
        raise NotImplemented


class FlexibeeAttachmentForm(FlexibeeItemForm):
    """
    Form for adding attachment to flexibee models
    """

    file = forms.FileField(label=_('Attachment'), required=True, widget=AttachmentWidget)
    link = forms.URLField(label=_('Link'), required=False)
    description = forms.CharField(label=_('Description'), required=False)

    def __init__(self, instance=None, *args, **kwargs):
        super(FlexibeeAttachmentForm, self).__init__(instance=instance, *args, **kwargs)
        if not instance:
            self.fields['link'].widget = EmptyWidget()
            self.fields['description'].widget = EmptyWidget()

    def _get_initial(self, initial, instance):
        initial['file'] = instance
        initial['link'] = instance.link
        initial['description'] = instance.description
        return initial

    def _get_file(self):
        file_field_name = 'file'
        if self.prefix:
            file_field_name = '%s-%s' % (self.prefix, file_field_name)
        return self.files.get(file_field_name)

    def _get_readonly_widget(self, field_name, field, widget):
        if field_name != 'file':
            return super(FlexibeeAttachmentForm, self)._get_readonly_widget(field_name, field, widget)
        return field.widget

    def save(self, commit=True):
        description = self.cleaned_data.get('description')
        link = self.cleaned_data.get('link')
        if not self.instance:
            file = self._get_file()
            return self.parent.attachments.add(filename=file.name, content_type=file.content_type, file=file.file,
                                               description=description, link=link)
        self.instance.link = link
        self.instance.description = description

        if commit:
            self.instance.save()
        return self.instance
