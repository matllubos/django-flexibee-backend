from django import forms
from django.utils.translation import ugettext_lazy as _

from is_core.forms import RestFormMixin

from flexibee_backend.is_core.forms.widgets import AttachementWidget


class FlexibeeItemForm(RestFormMixin, forms.Form):
    """
    This form should be only used for creation new objects. There should be used ImmutableWidgetMixin for fields
    """

    def __init__(self, instance=None, *args, **kwargs):
        self.instance = instance
        initial = kwargs.get('initial', {})
        kwargs['initial'] = self._get_initial(initial, instance)
        super(FlexibeeItemForm, self).__init__(*args, **kwargs)

    def _get_initial(self, initial, instance):
        raise NotImplementedError

    def save(self, commit=False):
        raise NotImplemented


class FlexibeeAttachmentForm(FlexibeeItemForm):
    """
    Form for adding attachement to flexibee models
    """

    file = forms.FileField(label=_('Attachment'), required=False, widget=AttachementWidget)

    def _get_initial(self, initial, instance):
        initial['file'] = instance
        return initial

    def save(self, commit=False):
        file = self.files.get('%s-file' % self.prefix)
        if file:
            return self.parent.attachments.add(filename=file.name, content_type=file.content_type, file=file.file)
        return self.instance
