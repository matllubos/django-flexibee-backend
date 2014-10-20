from django.core.exceptions import ObjectDoesNotExist
from django.http.response import Http404

from piston.resource import BaseObjectResource

from is_core.rest.resource import RestResource

from flexibee_backend.models import Attachment, FlexibeeItem
from flexibee_backend.is_core.forms import FlexibeeAttachmentForm
from flexibee_backend.models import Relation
from is_core.site import get_model_core


# TODO: permissions, save, delete, update
class FlexibeeItemResource(RestResource, BaseObjectResource):
    field_name = None
    form_class = None
    register = True

    def _get_parent_obj(self):
        qs = self._get_parent_queryset()
        return qs.get(pk=self.kwargs.get('parent_pk'))

    def _get_parent_queryset(self):
        return self.core.get_queryset(self.request, self.request.kwargs.get('parent_group'))

    def _get_queryset(self, parent_obj=None):
        parent_obj = parent_obj or self._get_parent_obj()

        return getattr(parent_obj, self.field_name)

    def _get_obj_or_none(self, pk=None, parent_obj=None):
        pk = pk or self.kwargs.get(self.pk_name)
        if not pk:
            return None

        try:
            return self._get_queryset(parent_obj).get(pk)
        except ObjectDoesNotExist:
            return None

    def _get_obj_or_404(self, pk=None, parent_obj=None):
        obj = self._get_obj_or_none(pk, parent_obj)
        if not obj:
            raise Http404
        return obj

    def _exists_obj(self, **kwargs):
        try:
            self._get_queryset().get(kwargs.get('pk'))
            return True
        except ObjectDoesNotExist:
            return False

    def _is_single_obj_request(self, result):
        return isinstance(result, FlexibeeItem)

    def _get_form(self, fields=None, inst=None, data=None, files=None, initial={}):
        # When is send PUT (resource instance exists), it is possible send only changed values.
        form = super(FlexibeeItemResource, self)._get_form(fields, inst, data, files, initial)
        form.parent = data.get('_parent') or self._get_parent_obj()
        return form

    def _get_instance(self, data):
        # If data contains id this method is update otherwise create
        inst = None

        pk = data.get(self.pk_field_name)
        if pk:
            inst = self._get_queryset(parent_obj=data.get('_parent')).get(pk)
        return inst

    def _pre_save_obj(self, obj, form, change):
        self.core.pre_save_model(self.request, obj, form, change)

    def _save_obj(self, obj, form, change):
        self.core.save_model(self.request, obj, form, change)

    def _post_save_obj(self, obj, form, change):
        self.core.post_save_model(self.request, obj, form, change)

    def _pre_delete_obj(self, obj):
        self.core.pre_delete_model(self.request, obj)

    def _delete_obj(self, obj):
        self.core.delete_model(self.request, obj)

    def _post_delete_obj(self, obj):
        self.core.post_delete_model(self.request, obj)

    def _delete(self, pk, via=None, parent_obj=None):
        via = via or []
        obj = self._get_obj_or_404(pk, parent_obj)
        self._check_delete_permission(obj, via)
        self._pre_delete_obj(obj)
        self._delete_obj(obj)
        self._post_delete_obj(obj)

    def _rest_links(self, obj):
        rest_links = {}
        kwargs = {'parent_group': get_model_core(obj.instance).menu_group, 'parent_pk': obj.instance.pk}
        for pattern in self.core.resource_patterns.values():
            if pattern.send_in_rest:
                url = pattern.get_url_string(self.request, obj=obj, kwargs=kwargs)
                if url:
                    allowed_methods = pattern.get_allowed_methods(self.request, obj)
                    if allowed_methods:
                        rest_links[pattern.name] = {
                            'url': url,
                            'methods': [method.upper() for method in allowed_methods]
                        }
        return rest_links


class AttachmentItemResource(FlexibeeItemResource):
    field_name = 'attachments'

    form_class = FlexibeeAttachmentForm
    fields = ('id', '_obj_name', 'filename', 'content_type', 'description', 'link', '_rest_links')
    default_detailed_fields = ('id', '_obj_name', 'filename', 'content_type', 'description', 'link', '_rest_links')
    default_general_fields = ('id', '_obj_name', 'filename', 'content_type', 'description', 'link', '_rest_links')

    model = Attachment


class RelationItemResource(FlexibeeItemResource):
    field_name = 'relations'

    form_class = FlexibeeAttachmentForm
    fields = ('id', '_obj_name', 'invoice', 'payment', 'remain', 'sum', 'currency_sum', '_rest_links')
    default_detailed_fields = ('id', '_obj_name', 'payment', 'remain', 'sum', 'currency_sum', '_rest_links')
    default_general_fields = ('id', '_obj_name', 'payment', 'remain', 'sum', 'currency_sum', '_rest_links')

    model = Relation
