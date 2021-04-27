from django.conf.urls import url
from django.urls import re_path, path

from .views import CartAddView, CartInfoView, CartUpdateView, CartDeleteView

urlpatterns = [
    re_path(r'^add$', CartAddView.as_view(), name="add"),  # 购物车记录添加
    path('', CartInfoView.as_view(), name='show'),  # 购物车页面显示
    path('update', CartUpdateView.as_view(), name='update'),  # 购物车页面更新
    path('delete', CartDeleteView.as_view(), name="delete"),  # 购物车记录删除

]
