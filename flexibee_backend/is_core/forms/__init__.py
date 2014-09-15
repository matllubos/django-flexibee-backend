from django import forms
from django.utils.translation import ugettext_lazy as _

from is_core.forms import RestFormMixin


class FlexibeeAttachmentForm(RestFormMixin, forms.Form):

    attachment = forms.FileField(label=_('New attachment'), required=False)
