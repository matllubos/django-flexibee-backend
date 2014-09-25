from is_core.rest.resource import RestResource
from django.shortcuts import get_object_or_404
from flexibee_backend.models import Attachment
from piston.resource import DefaultRestModelResource
from django.core.exceptions import ObjectDoesNotExist
from piston.utils import rc


class FlexibeeItemRestResource(RestResource, DefaultRestModelResource):

    register = True
    model = Attachment

    fields = ('id', 'filename', 'content_type', '_obj_name', '_rest_links')
    default_obj_fields = ('id', 'filename', 'content_type', '_obj_name', '_rest_links')
    default_list_fields = ('id', 'filename', 'content_type', '_obj_name', '_rest_links')

    pkfield = 'attachment_pk'

    def _rest_links(self, obj, request):
        rest_links = {}
        for pattern in self.core.resource_patterns.values():
            if pattern.send_in_rest:
                url = pattern.get_url_string(request, kwargs={'pk': request.kwargs.get('pk'), 'attachment_pk': obj.pk})
                if url:
                    allowed_methods = pattern.get_allowed_methods(request, obj)
                    if allowed_methods:
                        rest_links[pattern.name] = {'url': url, 'methods': allowed_methods}
        return rest_links

    def get_parent(self):
        return get_object_or_404(self.core.get_queryset(self.request), pk=self.kwargs.get('pk'))

    def get_queryset(self):
        return self.get_parent().attachments

    def _delete(self, request, inst):
        inst.delete()

    def read(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if self.pkfield in kwargs:
            try:
                return queryset.get(pk=kwargs.get(self.pkfield))
            except ObjectDoesNotExist:
                return rc.NOT_FOUND
        else:
            return queryset.all()

    def delete(self, request, pk, **kwargs):
        qs = self.get_queryset()
        try:
            inst = qs.get(pk=kwargs.get(self.pkfield))
        except ObjectDoesNotExist:
            return rc.NOT_FOUND
        self._delete(request, inst)
        return rc.DELETED
