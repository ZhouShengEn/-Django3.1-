from django.conf.urls import url
from django.urls import path, re_path

from .views import OrderPlaceView, CommentView, OrderCommitView

urlpatterns = [
    path('place', OrderPlaceView.as_view(), name='place'),# 订单页面显示
    path('commit', OrderCommitView.as_view(), name='commit'),  # 订单创建
    re_path(r'^comment/(?P<order_id>.+)$', CommentView.as_view(), name='comment'),  # 订单评论

]
