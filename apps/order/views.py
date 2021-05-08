import time
from datetime import datetime

from alipay import AliPay
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.db import transaction
import os
from django.conf import settings

# Create your views here.
from django.urls import reverse
from django.views import View
from django_redis import get_redis_connection
from apps.goods.models import GoodsSKU
from apps.order.models import OrderInfo, OrderGoods
from apps.user.models import Address


class OrderPlaceView(LoginRequiredMixin, View):
    '''订单页面显示'''

    def get(self, request):
        user = request.user
        cart_key = "cart_%d" % user.id
        skus = []
        sku_id = request.GET.get('sku_id')
        sku = GoodsSKU.objects.get(id=sku_id)
        count = request.GET.get('count')
        total_price = sku.price * int(count)
        addrs = Address.objects.filter(user=user)
        sku.count = int(count)
        sku.amount = total_price
        skus.append(sku)
        conn = get_redis_connection('default')
        conn.hset(cart_key, sku_id, count)
        context = {
            'skus': skus,
            'total_count': count,
            'total_price': total_price,
            'addrs': addrs,
            'sku_ids': sku.id
        }
        return render(request, 'place_order.html', context)

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
            try:
                amount = sku.price * int(count)
            except TypeError:
                return redirect(reverse('goods:index'))

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
                    return redirect(reverse('goods:index'))

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


class OrderPayView(View):
    '''订单支付'''

    def post(self, request):
        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})
        order_id = request.POST.get('order_id')

        if not order_id:
            return JsonResponse({'res': 1, 'errmsg': '无效的订单号'})

        try:
            order = OrderInfo.objects.get(order_id=order_id,
                                          user=user,
                                          pay_method=1,
                                          order_status=1)
        except OrderInfo.DoesNotExist:
            return JsonResponse({'res': 2, 'errmsg': '未找到该订单'})

        f1 = open(os.path.join(settings.BASE_DIR, 'apps/order/app_private_key.pem'), "r")
        f2 = open(os.path.join(settings.BASE_DIR, 'apps/order/alipay_public_key.pem'), "r")
        private_key_text = f1.read()
        public_key_text = f2.read()
        f1.close()
        f2.close()

        # 初始化支付宝对象
        alipay = AliPay(
            appid="2021000117647309",  # APPID
            app_notify_url=None,
            app_private_key_string=str(private_key_text),
            alipay_public_key_string=str(public_key_text),
            sign_type="RSA",
            debug=True  # 访问沙箱地址，False访问真实应用地址
        )

        # 通过python SDK去调用支付宝的支付接口
        order_string = alipay.api_alipay_trade_page_pay(
            out_trade_no=order_id,  # 订单id
            total_amount=str(order.total_price),  # 需要支付的金额
            subject='弗锐氏%s' % order_id,
            return_url=None,
            notify_url=None
        )

        alipay_url = 'https://openapi.alipaydev.com/gateway.do?' + order_string
        return JsonResponse({'res': 3, 'pay_url': alipay_url})


class CheckPayView(View):
    '''检查支付结果'''

    def post(self, request):
        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})
        order_id = request.POST.get('order_id')

        if not order_id:
            return JsonResponse({'res': 1, 'errmsg': '无效的订单号'})

        try:
            order = OrderInfo.objects.get(order_id=order_id,
                                          user=user,
                                          pay_method=1,
                                          order_status=1)
        except OrderInfo.DoesNotExist:
            return JsonResponse({'res': 2, 'errmsg': '未找到该订单'})

        f1 = open(os.path.join(settings.BASE_DIR, 'apps/order/app_private_key.pem'), "r")
        f2 = open(os.path.join(settings.BASE_DIR, 'apps/order/alipay_public_key.pem'), "r")
        private_key_text = f1.read()
        public_key_text = f2.read()
        f1.close()
        f2.close()

        # 初始化支付宝对象
        alipay = AliPay(
            appid="2021000117647309",  # APPID
            app_notify_url=None,
            app_private_key_string=str(private_key_text),
            alipay_public_key_string=str(public_key_text),
            sign_type="RSA",
            debug=True  # 访问沙箱地址，False访问真实应用地址
        )

        while True:
            # 通过python SDK去调用支付宝交易结果查询的接口
            response = alipay.api_alipay_trade_query(order_id)
            code = response.get('code')
            if code == '10000' and response.get('trade_status') == 'TRADE_SUCCESS':
                # 支付成功
                trade_no = response.get('trade_no')
                # 更新订单状态
                order.trade_no = trade_no
                order.order_status = 4
                order.save()
                return JsonResponse({'res': 3, 'message': '支付成功'})

            elif code == '40004' or code == '10000' and response.get('trade_status') == 'WAIT_BUYER_PAY':
                # 业务暂时处理失败或者买家正在付款
                time.sleep(5)
                continue
            else:
                return JsonResponse({'res': 4, 'errmsg': '支付失败'})


class CommentView(LoginRequiredMixin, View):
    """订单评论"""

    def get(self, request, order_id):
        """提供评论页面"""
        user = request.user

        # 校验数据
        if not order_id:
            return redirect(reverse('user:order'))

        try:
            order = OrderInfo.objects.get(order_id=order_id, user=user)
        except OrderInfo.DoesNotExist:
            return redirect(reverse("user:order"))

        # 根据订单的状态获取订单的状态标题
        order.status_name = OrderInfo.ORDER_STATUS[order.order_status]

        # 获取订单商品信息
        order_skus = OrderGoods.objects.filter(order_id=order_id)
        for order_sku in order_skus:
            # 计算商品的小计
            amount = order_sku.count * order_sku.price
            # 动态给order_sku增加属性amount,保存商品小计
            order_sku.amount = amount
        # 动态给order增加属性order_skus, 保存订单商品信息
        order.order_skus = order_skus

        # 使用模板
        return render(request, "order_comment.html", {"order": order})

    def post(self, request, order_id):
        """处理评论内容"""
        user = request.user
        # 校验数据
        if not order_id:
            return redirect(reverse('user:order'))

        try:
            order = OrderInfo.objects.get(order_id=order_id, user=user)
        except OrderInfo.DoesNotExist:
            return redirect(reverse("user:order"))

        # 获取评论条数
        total_count = request.POST.get("total_count")
        total_count = int(total_count)

        # 循环获取订单中商品的评论内容
        for i in range(1, total_count + 1):
            # 获取评论的商品的id
            sku_id = request.POST.get("sku_%d" % i)  # sku_1 sku_2
            # 获取评论的商品的内容
            content = request.POST.get('content_%d' % i, '')  # cotent_1 content_2 content_3
            try:
                order_goods = OrderGoods.objects.get(order=order, sku_id=sku_id)
            except OrderGoods.DoesNotExist:
                continue

            order_goods.comment = content
            order_goods.save()

        order.order_status = 5  # 已完成
        order.save()

        return redirect(reverse("user:userorder", kwargs={"page": 1}))
