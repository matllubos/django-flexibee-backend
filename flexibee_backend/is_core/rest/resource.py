from piston.resource import BaseResource, DefaultRestModelResource

from .serializer import *
from flexibee_backend.models import Attachment
from is_core.rest.resource import RestResource
from django.core.exceptions import ObjectDoesNotExist
from piston.exception import DataInvalidException, ResourceNotFoundException, \
    RestException, NotAllowedException, ConflictException
from piston.response import RestErrorResponse, RestErrorsResponse
from piston.utils import rc

from flexibee_backend.is_core.forms import FlexibeeAttachmentForm
from flexibee_backend.models import Relation


class FlexibeeItemResource(DefaultRestModelResource, RestResource):
    field_name = None
    form_class = None
    allowed_methods = ('GET', 'POST', 'PUT', 'DELETE')

    def get_parent_obj(self):
        qs = self.get_parent_queryset()
        print self.request.kwargs.get('parent_pk')
        return qs.get(pk=self.request.kwargs.get('parent_pk'))

    def get_parent_queryset(self):
        print self.core
        return self.core.get_queryset(self.request)

    def get_queryset(self):
        return getattr(self.get_parent_obj(), self.field_name)

    def get_form(self, request, inst=None, data=None, files=None, initial={}):
        # When is send PUT (resource instance exists), it is possible send only changed values.
        exclude = []

        kwargs = {}
        if inst:
            kwargs['instance'] = inst
        if data:
            kwargs['data'] = data
            kwargs['files'] = files

        form = self.form_class(initial=initial, **kwargs)
        form.parent = self.get_parent_obj()
        return form

    def read(self, request, *args, **kwargs):
        if 'pk' in self.request.kwargs:
            try:
                return self.get_queryset().get(self.request.kwargs.get('pk'))
            except ObjectDoesNotExist:
                return rc.NOT_FOUND
        return self.get_queryset().all()

    def exists(self, pk):
        try:
            self.get_queryset().get(pk)
            return True
        except self.model.DoesNotExist:
            return False

    def update(self, request, pk=None, **kwargs):
        data = self._prepare_data(request)
        data['pk'] = pk
        try:
            return self._create_or_update(request, data)
        except DataInvalidException as ex:
            return RestErrorsResponse(ex.errors)
        except ResourceNotFoundException:
            return rc.NOT_FOUND
        except RestException as ex:
            return RestErrorResponse(ex.message)

    def create(self, request, pk=None, **kwargs):
        data = self._prepare_data(request)
        try:
            inst = self._create_or_update(request, data)
        except DataInvalidException as ex:
            return RestErrorsResponse(ex.errors)
        except ResourceNotFoundException:
            # It cannot happend
            return rc.NOT_FOUND
        except RestException as ex:
            return RestErrorResponse(ex.message)
        return inst

    def _prepare_data(self, request):
        data = self.flatten_dict(request.data)
        return data

    def _get_instance(self, request, data):
        # If data contains id this method is update otherwise create
        inst = None
        if 'pk' in data.keys():
            inst = self.get_queryset().get(pk=data.get('pk'))
        return inst

    def _create_or_update(self, request, data, via=None):
        via = via or []

        inst = self._get_instance(request, data)

        if inst and not self.has_update_permission(request, inst, via):
            return inst
        elif not inst and not self.has_create_permission(request, via=via):
            raise NotAllowedException
        form_fields = self.get_form(request, inst=inst).fields

        # preprocesor = FileDataPreprocessor(request, self.model, form_fields, inst, via)
        # data, files = preprocesor.process_data(request.data, request.FILES)

        files = request.FILES
        form = self.get_form(request, inst=inst, data=data, files=files)
        errors = form.is_invalid()
        if errors:
            raise DataInvalidException(errors)

        inst = form.save(commit=False)
        inst.save()
        return inst

    def delete(self, request, *args, **kwargs):
        raise NotImplementedError


class AttachmentItemResource(FlexibeeItemResource):
    field_name = 'attachments'

    form_class = FlexibeeAttachmentForm
    fields = ('id', '_obj_name', 'filename', 'content_type', 'description', 'link')
    default_obj_fields = ('id', '_obj_name', 'filename', 'content_type', 'description', 'link')
    default_list_fields = ('id', '_obj_name', 'filename', 'content_type', 'description', 'link')

    model = Attachment


class RelationItemResource(FlexibeeItemResource):
    field_name = 'relations'

    form_class = FlexibeeAttachmentForm
    fields = ('id', '_obj_name', 'invoice', 'payment', 'remain', 'sum', 'currency_sum')
    default_obj_fields = ('id', '_obj_name', 'payment', 'remain', 'sum', 'currency_sum')
    default_list_fields = ('id', '_obj_name', 'payment', 'remain', 'sum', 'currency_sum')

    def get_default_obj_fields(self, request, obj):
        return self.default_obj_fields

    def get_default_list_fields(self, request):
        return self.default_list_fields

    def get_guest_fields(self, request):
        return self.guest_fields

    model = Relation

