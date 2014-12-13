from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ImproperlyConfigured
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.urlresolvers import reverse
from django.http import HttpResponse, Http404, HttpResponseRedirect
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.translation import ugettext_lazy as _
from django.views.generic import TemplateView
from django.utils import timezone
import datetime

from aristotle_mdr.perms import user_can_view, user_can_edit, user_can_change_status
from aristotle_mdr import perms
from aristotle_mdr.utils import cache_per_item_user, concept_to_dict
from aristotle_mdr import forms as MDRForms
from aristotle_mdr import models as MDR

from haystack.views import SearchView

PAGES_PER_RELATED_ITEM = 15


class DynamicTemplateView(TemplateView):
    def get_template_names(self):
        return ['aristotle_mdr/static/%s.html' % self.kwargs['template']]

class HelpTemplateView(TemplateView):
    def get_template_names(self):
        return ['aristotle_mdr/static/help/%s.html' % self.kwargs['template']]

def get_if_user_can_view(objtype,user,iid):
    item = get_object_or_404(objtype,pk=iid)
    if user_can_view(user,item):
        return item
    else:
        return False

def render_if_user_can_view(item_type, request, *args, **kwargs):
    #request = kwargs.pop('request')
    return render_if_condition_met(request, user_can_view, item_type, *args,**kwargs)

@login_required
def render_if_user_can_edit(item_type, request, *args, **kwargs):
    request = kwargs.pop('request')
    return render_if_condition_met(request, user_can_edit, item_type, *args,**kwargs)

def download(request,downloadType,iid=None):
    """
    By default, ``aristotle_mdr.views.download`` is called whenever a URL matches
    the pattern defined in ``aristotle_mdr.urls_aristotle``::

        download/(?P<downloadType>[a-zA-Z0-9\-\.]+)/(?P<iid>\d+)/?

    This is passed into ``download`` which resolves the item id (``iid``), and
    determins if a user has permission to view the request item with that id. If
    a user is allowed to download this file, ``download`` iterates through each
    download type defined in ``ARISTOTLE_DOWNLOADS``.

    A download option tuple takes the following form form::

        ('file_type','display_name','font_awesome_icon_name','module_name'),

    With ``file_type`` allowing only ASCII alphanumeric and underscores,
    ``display_name`` can be any valid python string,
    ``font_awesome_icon_name`` can be any Font Awesome icon and
    ``module_name`` is the name of the python module that provides a downloader
    for this file type.

    For example, included with Aristotle-MDR is a PDF downloader which has the
    download definition tuple::

            ('pdf','PDF','fa-file-pdf-o','aristotle_mdr'),

    Where a ``file_type`` multiple is defined multiple times, **the last matching
    instance in the tuple is used**.

    Next, the module that is defined for a ``file_type`` is dynamically imported using
    ``exec``, and is wrapped in a ``try: except`` block to catch any exceptions. If
    the ``module_name`` does not match the regex ``^[a-zA-Z0-9\_]+$`` ``download``
    raises an exception.

    If the module is able to be imported, ``downloader.py`` from the given module
    is imported, this file **MUST** have a ``download`` function defined which returns
    a Django ``HttpResponse`` object of some form.
    """
    item = MDR._concept.objects.get_subclass(pk=iid)
    item = get_if_user_can_view(item.__class__,request.user, iid)
    if not item:
        if request.user.is_anonymous():
            return redirect(reverse('django.contrib.auth.views.login')+'?next=%s' % request.path)
        else:
            raise PermissionDenied

    from django.conf import settings
    downloadOpts = getattr(settings, 'ARISTOTLE_DOWNLOADS', "")
    module_name = ""
    for d in downloadOpts:
        dt = d[0]
        if dt == downloadType:
            module_name = d[-1]
    if module_name:
        import re
        if not re.search('^[a-zA-Z0-9\-\.]+$',downloadType): # pragma: no cover
            # Invalid downloadType
            raise ImproperlyConfigured
        elif not re.search('^[a-zA-Z0-9\_]+$',module_name): # pragma: no cover
            # bad module_name
            raise ImproperlyConfigured
        try:
            downloader = None
            # dangerous - we are really trusting the settings creators here.
            exec("import %s.downloader as downloader"%module_name)
            return downloader.download(request,downloadType,item)
        except:
            raise ImproperlyConfigured

    raise Http404


@cache_per_item_user(ttl=300, cache_post=False)
def render_if_condition_met(request,condition,objtype,iid=None,subpage=None):
    if iid is None:
        app_name = objtype._meta.app_label
        return redirect(reverse("%s:about"%app_name,args=["".join(objtype._meta.verbose_name.lower().split())]))
    item = get_object_or_404(objtype,pk=iid).item
    if not condition(request.user, item):
        if request.user.is_anonymous():
            return redirect(reverse('django.contrib.auth.views.login')+'?next=%s' % request.path)
        else:
            raise PermissionDenied

    # We add a user_can_edit flag in addition to others as we have odd rules around who can edit objects.
    isFavourite = request.user.is_authenticated () and request.user.profile.isFavourite(item.id)

    from reversion.revisions import default_revision_manager
    last_edit = default_revision_manager.get_for_object_reference(
            item.__class__,
            item.pk,
        ).first()
    return render(request,item.template,
        {'item':item,
         'view':request.GET.get('view','').lower(),
         'isFavourite': isFavourite,
         'last_edit': last_edit
            }
        )

def itemPackages(request, iid):
    item = get_if_user_can_view(MDR._concept,request.user,iid=iid)
    if not item:
        if request.user.is_anonymous():
            return redirect(reverse('django.contrib.auth.views.login')+'?next=%s' % request.path)
        else:
            raise PermissionDenied

    packages = item.packages.all().visible(request.user)
    paginator = Paginator(packages, PAGES_PER_RELATED_ITEM)
    page = request.GET.get('page')
    try:
        packages = paginator.page(page)
    except PageNotAnInteger:
        packages = paginator.page(1)
    except EmptyPage:
        packages = paginator.page(paginator.num_pages)

    return render(request,"aristotle_mdr/relatedPackages.html",
        {'item':item.item,
         'packages':packages,}
        )

def registrationHistory(request, iid):
    item = get_if_user_can_view(MDR._concept,request.user,iid)
    if not item:
        if request.user.is_anonymous():
            return redirect(reverse('django.contrib.auth.views.login')+'?next=%s' % request.path)
        else:
            raise PermissionDenied
    from reversion.revisions import default_revision_manager
    history = []
    for s in item.statuses.all():
        past = default_revision_manager.get_for_object(s)
        history.append((s,past))
    return render(request,"aristotle_mdr/registrationHistory.html",
            {'item':item,
             'history': history
                }
            )

def edit_item(request,iid,*args,**kwargs):
    item = get_object_or_404(MDR._concept,pk=iid).item
    if not user_can_edit(request.user, item):
        if request.user.is_anonymous():
            return redirect(reverse('django.contrib.auth.views.login')+'?next=%s' % request.path)
        else:
            raise PermissionDenied

    if request.method == 'POST': # If the form has been submitted...
        form = MDRForms.wizards.subclassed_wizard_2_Results(item.__class__)(request.POST,instance=item,user=request.user)
        if form.is_valid():
            item = form.save()
            return HttpResponseRedirect(reverse("aristotle:item",args=[item.pk]))
    else:
        form = MDRForms.wizards.subclassed_modelform(item.__class__)(instance=item,user=request.user)
    return render(request,"aristotle_mdr/actions/advanced_editor.html",
            {"item":item,
             "form":form,
                }
            )

def unauthorised(request, path=''):
    if request.user.is_anonymous():
        return render(request,"401.html",{"path":path,"anon":True,},status=401)
    else:
        return render(request,"403.html",{"path":path,"anon":True,},status=403)




@login_required
def toggleFavourite(request, iid):
    request.user.profile.toggleFavourite(iid)
    if request.GET.get('next',None):
        return redirect(request.GET.get('next'))
    return redirect(reverse("aristotle:item",args=[iid]))

def registrationauthority(*args,**kwargs):
    return render_if_user_can_view(MDR.RegistrationAuthority,*args,**kwargs)

def allRegistrationAuthorities(request):
    ras = MDR.RegistrationAuthority.objects.order_by('name')
    return render(request,"aristotle_mdr/allRegistrationAuthorities.html",
        {'registrationAuthorities':ras}
        )

def glossary(request):
    return render(request,"aristotle_mdr/glossary.html",
        {'terms':MDR.GlossaryItem.objects.all().order_by('name').visible(request.user)
        })

def glossaryAjaxlist(request):
    import json
    results = [g.json_link_list() for g in MDR.GlossaryItem.objects.visible(request.user).all()]
    return HttpResponse(json.dumps(results), content_type="application/json")

#def glossaryBySlug(request,slug):
#    term = get_object_or_404(MDR.GlossaryItem,id=iid)
#    return render(request,"aristotle_mdr/glossaryItem.html",{'item':term})

def about_all_items(request):

    from django.conf import settings
    aristotle_apps = getattr(settings, 'ARISTOTLE_SETTINGS', {}).get('CONTENT_EXTENSIONS',[])
    aristotle_apps += ["aristotle_mdr"]

    from django.contrib.contenttypes.models import ContentType
    models = ContentType.objects.filter(app_label__in=aristotle_apps).all()
    out = {}
    for m in models:
        if not m.model.startswith("_"):
            app_models = out.get(m.app_label,[])
            app_models.append(m.model_class())
            out[m.app_label] = app_models

    return render(request,"aristotle_mdr/static/all_items.html",{'models':out,})

# Actions

def mark_ready_to_review(request,iid):
    item = get_object_or_404(MDR._concept,pk=iid).item
    if not (item and user_can_edit(request.user,item)):
        if request.user.is_anonymous():
            return redirect(reverse('django.contrib.auth.views.login')+'?next=%s' % request.path)
        else:
            raise PermissionDenied

    if request.method == 'POST': # If the form has been submitted...
        if item.is_registered:
            raise PermissionDenied
        else:
            item.readyToReview = not item.readyToReview
            item.save()
        return HttpResponseRedirect(reverse("aristotle:item",args=[item.id]))
    else:
        return render(request,"aristotle_mdr/actions/mark_ready_to_review.html",
            {"item":item,}
            )

def changeStatus(request, iid):
    item = get_object_or_404(MDR._concept,pk=iid).item
    if not (item and user_can_change_status(request.user,item)):
        if request.user.is_anonymous():
            return redirect(reverse('django.contrib.auth.views.login')+'?next=%s' % request.path)
        else:
            raise PermissionDenied
    # There would be an else here, but both branches above return,
    # so we've chopped it out to prevent an arrow anti-pattern.
    if request.method == 'POST': # If the form has been submitted...
        form = MDRForms.ChangeStatusForm(request.POST,user=request.user) # A form bound to the POST data
        if form.is_valid():
            # process the data in form.cleaned_data as required
            ras = form.cleaned_data['registrationAuthorities']
            state = form.cleaned_data['state']
            regDate = form.cleaned_data['registrationDate']
            cascade = form.cleaned_data['cascadeRegistration']
            changeDetails = form.cleaned_data['changeDetails']
            if regDate is None:
                regDate = timezone.now().date()
            for ra in ras:
                ra.register(item,state,request.user,regDate,cascade,changeDetails)
            return HttpResponseRedirect(reverse("aristotle:item",args=[item.id]))
    else:
        form = MDRForms.ChangeStatusForm(user=request.user)
    return render(request,"aristotle_mdr/actions/changeStatus.html",
            {"item":item,
             "form":form,
                }
            )

def supersede(request, iid):
    item = get_object_or_404(MDR._concept,pk=iid).item
    if not (item and user_can_edit(request.user,item)):
        if request.user.is_anonymous():
            return redirect(reverse('django.contrib.auth.views.login')+'?next=%s' % request.path)
        else:
            raise PermissionDenied
    qs=item.__class__.objects.all()
    if request.method == 'POST': # If the form has been submitted...
        form = MDRForms.SupersedeForm(request.POST,user=request.user,item=item,qs=qs) # A form bound to the POST data
        if form.is_valid():
            item.superseded_by = form.cleaned_data['newerItem']
            item.save()
            return HttpResponseRedirect(reverse("aristotle:item",args=[item.id]))
    else:
        form = MDRForms.SupersedeForm(item=item,user=request.user,qs=qs)
    return render(request,"aristotle_mdr/actions/supersedeItem.html",
            {"item":item,
             "form":form,
                }
            )

def deprecate(request, iid):
    item = get_object_or_404(MDR._concept,pk=iid).item
    if not (item and user_can_edit(request.user,item)):
        if request.user.is_anonymous():
            return redirect(reverse('django.contrib.auth.views.login')+'?next=%s' % request.path)
        else:
            raise PermissionDenied
    qs=item.__class__.objects.filter().editable(request.user)
    if request.method == 'POST': # If the form has been submitted...
        form = MDRForms.DeprecateForm(request.POST,user=request.user,item=item,qs=qs) # A form bound to the POST data
        if form.is_valid():
            # Check use the itemset as there are permissions issues and we want to remove some:
            #  Everything that was superseded, but isn't in the returned set
            #  Everything that was in the returned set, but isn't already superseded
            #  Everything left over can stay the same, as its already superseded
            #    or wasn't superseded and is staying that way.
            for i in item.supersedes.all():
                if i not in form.cleaned_data['olderItems'] and user_can_edit(request.user,i):
                    item.supersedes.remove(i)
            for i in form.cleaned_data['olderItems']:
                if user_can_edit(request.user,i): #Would check item.supersedes but its a set
                    item.supersedes.add(i)
            return HttpResponseRedirect(reverse("aristotle:item",args=[str(item.id)]))
    else:
        form = MDRForms.DeprecateForm(user=request.user,item=item,qs=qs)
    return render(request,"aristotle_mdr/actions/deprecateItems.html",
            {"item":item,
             "form":form,
                }
            )

def browse(request,oc_id=None,dec_id=None):
    if oc_id is None:
        items = MDR.ObjectClass.objects.order_by("name").public()
        return render(request,"aristotle_mdr/browse/objectClasses.html",
            {"items":items,
                }
            )
    elif oc_id is not None and dec_id is None:
        oc = get_object_or_404(MDR.ObjectClass,id=oc_id)
        items = MDR.DataElementConcept.objects.filter(objectClass=oc).order_by("name").public()
        return render(request,"aristotle_mdr/browse/dataElementConcepts.html",
            {"items":items,
             "objectClass":oc,
                }
            )
    elif oc_id is not None and dec_id is not None:
        # Yes, for now we ignore the Object Class. If the user is messing with IDs in the URL and things break thats their fault.
        dec = get_object_or_404(MDR.DataElementConcept,id=dec_id)
        items = MDR.DataElement.objects.filter(dataElementConcept=dec).order_by("name").public()
        return render(request,"aristotle_mdr/browse/dataElements.html",
            {"items":items,
             "dataElementConcept":dec,
                }
            )

@login_required
def bulk_action(request):
    url = request.GET.get("next","/")
    message = ""
    if request.method == 'POST': # If the form has been submitted...
        actions = {
            "add_favourites":MDRForms.bulk_actions.FavouriteForm,
            "change_state":MDRForms.bulk_actions.ChangeStateForm,
            }
        action = request.POST.get("bulkaction",None)
        if action is None:
            # no action, messed up, redirect
            return HttpResponseRedirect(url)
        if actions[action].confirm_page is None:
            # if there is no confirm page or extra details required, do the action and redirect
            form = actions[action](request.POST,user=request.user) # A form bound to the POST data
            if form.is_valid():
                message = form.make_changes()
                messages.add_message(request, messages.INFO, message)
            else:
                messages.add_message(request, messages.ERROR, form.errors)
            return HttpResponseRedirect(url)
        else:
            form = MDRForms.bulk_actions.BulkActionForm(request.POST,user=request.user)
            items = []
            if form.is_valid():
                items = form.cleaned_data['items']
            confirmed = request.POST.get("confirmed",None)

            if confirmed:
                # We've passed the confirmation page, try and save.
                form = actions[action](request.POST,user=request.user,items=items) # A form bound to the POST data
                # there was an error with the form redisplay
                if form.is_valid():
                    message = form.make_changes()
                    messages.add_message(request, messages.INFO, message)
                    return HttpResponseRedirect(url)
            else:
                # we need a confirmation, render the next form
                form = actions[action](request.POST,user=request.user,items=items)
            return render(request,actions[action].confirm_page,
                    {"items":items,
                     "form":form,
                     "next":url
                        }
                    )
    return HttpResponseRedirect(url)

# Search views

class PermissionSearchView(SearchView):
    def __call__(self, request):
        if 'addFavourites' in request.GET.keys():
            return bulkFavourite(request,url="aristotle:search")
        else:
            return super(PermissionSearchView, self).__call__(request)

    def build_form(self):
        form = super(self.__class__, self).build_form()
        form.request = self.request
        return form
