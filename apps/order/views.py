from datetime import datetime

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.db import transaction

# Create your views here.
from django.urls import reverse
from django.views import View
from django_redis import get_redis_connection

# /order/place
from apps.goods.models import GoodsSKU
from apps.order.models import OrderInfo, OrderGoods
from apps.user.models import Address


class OrderPlaceView(LoginRequiredMixin, View):
    '''订单页面显示'''

    def post(self, request):
        user = request.user
        sku_ids = request.POST.getlist('sku_ids')
        if not sku_ids:
            return redirect(reverse('cart:show'))
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id

        skus = []
        total_count = 0
        total_price = 0
        # 遍历获取用户要购买的商品
        for sku_id in sku_ids:
            sku = GoodsSKU.objects.get(id=sku_id)
            # 获取用户要购买商品的数量
            count = conn.hget(cart_key, sku_id)
            # 计算每种商品的总价
            amount = sku.price * int(count)
            sku.count = int(count)
            sku.amount = amount
            skus.append(sku)
            total_count += int(count)
            total_price += amount

        # 获取用户的收货地址
        addrs = Address.objects.filter(user=user)

        sku_ids = ','.join(sku_ids)
        context = {
            'skus': skus,
            'total_count': total_count,
            'total_price': total_price,
            'addrs': addrs,
            'sku_ids': sku_ids
        }
        return render(request, 'place_order.html', context)


class OrderCommitView(View):
    '''订单创建'''

    @transaction.atomic()
    def post(self, request):
        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})
        addr_id = request.POST.get('addr_id')
        pay_method = request.POST.get('pay_method')
        sku_ids = request.POST.get('sku_ids')

        # 参数校验
        if not all([addr_id, pay_method, sku_ids]):
            return JsonResponse({'res': 1, 'errmsg': '数据不完整'})

        if pay_method not in OrderInfo.PAY_METHODS.keys():
            return JsonResponse({'res': 2, 'errmsg': '支付方式不存在'})

        try:
            addr = Address.objects.get(id=addr_id)
        except Address.DoesNotExist:
            return JsonResponse({'res': 3, 'errmsg': '地址不存在'})

        # 设置订单id格式为：当前时间+用户id
        order_id = datetime.now().strftime('%Y%m%d%H%M%S') + str(user.id)

        total_price = 0
        total_count = 0

        # 设置mysql事务保存点
        save_id = transaction.savepoint()
        try:

            order = OrderInfo.objects.create(order_id=order_id,
                                             user=user,
                                             addr=addr,
                                             pay_method=pay_method,
                                             total_count=total_count,
                                             total_price=total_price)

            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id
            sku_ids = sku_ids.split(',')
            for sku_id in sku_ids:
                try:
                    # 添加悲观锁
                    sku = GoodsSKU.objects.select_for_update().get(id=sku_id)
                except Exception as e:
                    print(e)
                    # 如果商品不存在mysql事务回滚到指定保存点
                    transaction.savepoint_rollback(save_id)
                    return JsonResponse({'res': 4, 'errmsg': '商品不存在'})

                # 从redis中获取用户购买商品的数量
                try:
                    count = conn.hget(cart_key, sku_id)
                except:
                    return redirect('404.html')

                if int(count) > sku.stock:
                    # 如果商品库存不足mysql事务回滚到指定保存点
                    transaction.savepoint_rollback(save_id)
                    return JsonResponse({'res': 6, 'errmsg': '商品库存不足'})
                OrderGoods.objects.create(order=order,
                                          sku=sku,
                                          count=count,
                                          price=sku.price)

                # 更新商品库存和销量
                sku.stock -= int(count)
                sku.sales += int(count)
                sku.save()

                amount = sku.price * int(count)  # 小计
                total_count += int(count)
                total_price += amount

            # 更新订单信息表中商品的总数量和总价格
            order.total_count = total_count
            order.total_price = total_price
            order.save()
        except Exception as e:
            # 如果在事务中出现错误，将回滚到指定保存点
            print(e)
            transaction.savepoint_rollback(save_id)
            return JsonResponse({'res': 7, 'errmsg': '下单失败'})

        # 提交事务
        transaction.savepoint_commit(save_id)

        # 当订单创建成功后清除缓存中用户的购物车记录
        conn.hdel(cart_key, *sku_ids)

        return JsonResponse({'res': 5, 'message': '订单创建成功'})


class CommentView(View):
    def get(self, request):
        pass
