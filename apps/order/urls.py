from django.conf.urls import url
from django.urls import path, re_path

from .views import OrderPlaceView, CommentView, OrderCommitView, OrderPayView, CheckPayView

urlpatterns = [
    path('place', OrderPlaceView.as_view(), name='place'),# 订单页面显示
    path('commit', OrderCommitView.as_view(), name='commit'),  # 订单创建
    re_path(r'^comment/(?P<order_id>.+)$', CommentView.as_view(), name='comment'),  # 订单评论
    path('pay', OrderPayView.as_view(), name='pay'), # 订单支付
    path('check', CheckPayView.as_view(), name='check'), # 查询订单支付结果

]
