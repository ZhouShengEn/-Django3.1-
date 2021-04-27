from django.conf.urls import url
from django.urls import path, re_path
from apps.user.views import *
from django.contrib.auth.decorators import login_required

urlpatterns = [
    path('register', RegisterView.as_view(), name='register'),
    path('login', Login.as_view(), name='login'),
    re_path(r'^active/(?P<token>.*)$', ActiveView.as_view(), name='active'),
    path('info', UserInfoView.as_view(), name='userinfo'),
    re_path('^order/(?P<page>\d+)$', UserOrderView.as_view(), name='userorder'),
    path('site', UserSiteView.as_view(), name='usersite'),
    path('logout', LogoutView.as_view(), name='logout'),
    path('address', AddressView.as_view(), name='address')

]
