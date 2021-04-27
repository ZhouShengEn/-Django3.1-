from django.core.paginator import Paginator
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views import View
from .models import User, Address
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from itsdangerous import SignatureExpired
from django.conf import settings
from django.http import HttpResponse
from celery_task.tasks import send_register_email
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
import re
from django_redis import get_redis_connection
from ..goods.models import GoodsSKU


# Create your views here.


# /user/register
# def register(request):
#     '''显示注册页面'''
#     if request.method == 'GET':
#
#         return render(request, 'register.html')
#     else:
#         # 当请求是POST时，进行数据效验
#         # 获取数据
#         username = request.POST.get('user_name')
#         password = request.POST.get('pwd')
#         cpassword = request.POST.get('cpwd')
#         email = request.POST.get('email')
#         allow = request.POST.get('allow')
#         # 效验数据
#         if not all([username, password, cpassword, email]):
#             print('not_all')
#             return render(request, 'register.html', {'errmsg': '数据不完整'})
#         # 两次密码是否一致
#         if cpassword != password:
#             print('password')
#             return render(request, 'register.html', {'errmsg': '两次密码输入不一致'})
#         # # 检测邮箱是否格式正确
#         # if not re.match(r"^[\w]+@[\w]+\.com&", email):
#         #     print('re')
#         #     return render(request, 'register.html', {'errmsg':'邮箱不合法'})
#         # 是否勾选使用协议
#         if allow != 'on':
#             print('not on')
#             return render(request, 'register.html', {'errmsg': '没有勾选使用协议'})
#
#         # 效验用户是否已存在
#         try:
#             user = User.objects.get(username=username)
#         except User.DoesNotExist:
#             # 用户名不存在
#             user = None
#         if user:
#             return render(request, 'register.html', {'errmsg': '用户名已存在'})
#
#         # 业务处理: 进行用户注册，用django自带的user模型类去创建用户
#         user = User.objects.create_user(username, email, password)
#         # 用户刚注册时，is_active属性设置处于没有激活的状态
#         user.is_active = 0
#         user.save()
#
#         # 返回应答
#         return redirect(reverse('goods:index'))
from ..order.models import OrderInfo, OrderGoods


class RegisterView(View):
    def get(self, request):
        # 当请求是GET时，展示注册页面
        return render(request, 'register.html', )

    def post(self, request):
        # 当请求是POST时，进行数据效验
        # 获取数据
        username = request.POST.get('user_name')
        password = request.POST.get('pwd')
        cpassword = request.POST.get('cpwd')
        email = request.POST.get('email')
        allow = request.POST.get('allow')
        # 效验数据
        if not all([username, password, cpassword, email]):
            print('not_all')
            return render(request, 'register.html', {'errmsg': '数据不完整'})
        # 两次密码是否一致
        if cpassword != password:
            print('password')
            return render(request, 'register.html', {'errmsg': '两次密码输入不一致'})
        # # 检测邮箱是否格式正确
        # if not re.match(r"^[\w]+@[\w]+\.com&", email):
        #     print('re')
        #     return render(request, 'register.html', {'errmsg':'邮箱不合法'})
        # 是否勾选使用协议
        if allow != 'on':
            print('not on')
            return render(request, 'register.html', {'errmsg': '没有勾选使用协议'})

        # 效验用户是否已存在
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            # 用户名不存在
            user = None
        if user:
            return render(request, 'register.html', {'errmsg': '用户名已存在'})

        # 业务处理: 进行用户注册，用django自带的user模型类去创建用户
        user = User.objects.create_user(username, email, password)
        # 用户刚注册时，is_active属性设置处于没有激活的状态
        user.is_active = 0
        user.save()

        # 发送激活邮件，包含激活链接：http://127.0.0.1:8000/user/active/id
        # 激活链接中需要包含用户的身份信息，并且对身份信息进行加密

        # 加密用户身份信息，生成激活token
        serializer = Serializer(settings.SECRET_KEY, 3600)
        info = {'confirm': user.id}
        token = serializer.dumps(info)  # 显示为byte
        token = token.decode('utf-8')

        # 发邮件
        send_register_email.delay(email, username, token)

        # 返回应答
        return redirect(reverse('goods:index'))


class ActiveView(View):
    def get(self, request, token):
        serializer = Serializer(settings.SECRET_KEY, 3600)
        try:
            info = serializer.loads(token)
            user_id = info['confirm']
            user = User.objects.get(id=user_id)
            user.is_active = 1
            user.save()
            return redirect(reverse("user:login"))
        except SignatureExpired as s:
            return HttpResponse("激活链接已过期")


# /login
class Login(View):
    def get(self, request):

        # 判断在COOKIES中是否有该用户名
        if 'username' in request.COOKIES:
            # 如果用则得到该用户名并且设置“记住用户名”的勾选状态
            username = request.COOKIES['username'].encode("iso-8859-1").decode('utf-8')
            checked = 'checked'
        else:
            username = ''
            checked = ''
        return render(request, 'login.html', {'username': username, 'checked': checked})

    def post(self, request):
        username = request.POST.get('username')
        pwd = request.POST.get('pwd')
        remember = request.POST.get('remember')
        # 效验数据
        if not all([username, pwd]):
            return render(request, 'login.html', {'errmsg': '数据不完整'})

        # 业务处理: 登陆效验
        user = authenticate(request, username=username, password=pwd)
        if user is not None:
            if user.is_active:
                # 用户已激活
                # 记录用户的登陆状态
                login(request, user)

                # 获取登陆后所要跳转到的地址
                # 当url的参数中next参数为None时则会指向reverse('goods:index'),如果有值的话则得到next的参数值
                next_url = request.GET.get('next', reverse('goods:index'))

                # 获得一个HttpResponse对象
                response = redirect(next_url)

                # 判断是否选中“记住用户名”
                if remember == 'on':
                    # 设置cookie值，过期时间为7天
                    response.set_cookie('username', username.encode('utf-8').decode('iso-8859-1'),
                                        max_age=7 * 24 * 3600)
                else:
                    response.delete_cookie('username')
                # 返回response
                return response
            else:
                # 用户未激活
                return render(request, 'login.html', {'errmsg': '账户未激活'})
        else:
            # 用户名或密码错误
            return render(request, 'login.html', {'errmsg': '用户名密码错误'})


class UserInfoView(LoginRequiredMixin, View):
    def get(self, request):
        user = request.user
        address = Address.objects.get_default_address(user)

        # 建立redis连接，获取连接的对象
        con = get_redis_connection('default')

        history_key = 'history_%d' % user.id

        # 获取用户最新浏览的五个商品id
        goods_ids = con.lrange(history_key, 0, 4)

        # 从数据库中得到这五个商品
        goods_list = list()

        for good_id in goods_ids:
            good = GoodsSKU.objects.get(id=good_id)
            goods_list.append(good)

        return render(request, 'user_center_info.html', {'page': 'info', 'address': address, 'goods': goods_list})


class UserOrderView(LoginRequiredMixin, View):
    def get(self, request, page):
        # 获取用户订单信息
        user = request.user
        orders = OrderInfo.objects.filter(user=user).order_by('-create_time')
        for order in orders:
            order_skus = OrderGoods.objects.filter(order_id=order.order_id)
            for order_sku in order_skus:
                # 每种商品的价格
                amount = order_sku.count*order_sku.price
                order_sku.amount = amount

            # 动态添加订单状态
            order.status_name = OrderInfo.ORDER_STATUS[order.order_status]
            order.order_skus = order_skus

        # 分页
        paginator = Paginator(orders, 1)
        # 获取第page页的内容
        try:
            page = int(page)
        except Exception as e:
            page = 1

        if page > paginator.num_pages:
            page = 1

        # 获取第page页的Page实例对象
        order_page = paginator.page(page)

        # 页码控制，控制页码只显示五页并且显示当前页的前两页和后两页
        num_pages = paginator.num_pages
        if num_pages < 5:
            pages = range(1, num_pages + 1)
        elif page <= 3:
            pages = range(1, 6)
        elif num_pages - page <= 2:
            pages = range(num_pages - 4, num_pages + 1)
        else:
            pages = range(page - 2, page + 3)

        context = {
            'order_page': order_page,
            'pages': pages,
            'page': 'order'
        }
        return render(request, 'user_center_order.html', context)


class UserSiteView(LoginRequiredMixin, View):
    def get(self, request):

        # 获取登录用户对应的user对象
        user = request.user

        # 获取用户的默认收货地址
        # try:
        #     address = Address.objects.get(user=user, is_default=True)
        # except Address.DoesNotExist:
        #     # 不存在默认收货地址
        #     address = None
        address = Address.objects.get_default_address(user)

        return render(request, 'user_center_site.html', {'page': 'site', 'address': address})

    def post(self, request):
        '''添加地址'''

        # 获取地址信息
        receiver = request.POST.get('receiver')
        addr = request.POST.get('addr')
        zip_code = request.POST.get('zip_code')
        phone = request.POST.get('phone')

        # 效验地址信息
        if not all([receiver, addr, phone]):
            return render(request, 'user_center_site.html', {'errmsg': '地址信息不完整'})
        if not re.match(r'^1[3|4|5|7|8][0-9]{9}$', phone):
            return render(request, 'user_center_site.html', {'errmsg': '电话格式错误'})
        user = request.user
        # try:
        #     address = Address.objects.get(user=user, is_default=True)
        # except Address.DoesNotExist:
        #     address = None
        address = Address.objects.get_default_address(user)
        if address:
            is_default = False
        else:
            is_default = True

        # 添加地址
        Address.objects.create(user=user, receiver=receiver, addr=addr, zip_code=zip_code, phone=phone,
                               is_default=is_default)

        # 返回应答
        return redirect(reverse('user:usersite'))  # 重定向属于get提交


class LogoutView(View):
    def get(self, request):
        """登出用户"""

        # 清除用户的session信息
        logout(request)
        # 跳转到首页
        return redirect(reverse('goods:index'))


# /user/address
class AddressView(LoginRequiredMixin, View):
    '''用户中心-地址页'''

    def get(self, request):
        '''显示'''
        # 获取登录用户对应User对象
        user = request.user

        # 获取用户的默认收货地址
        try:
            address = Address.objects.get(user=user, is_default=True)  # models.Manager
        except Address.DoesNotExist:
            # 不存在默认收货地址
            address = None
        # address = Address.objects.get_default_address(user)

        # 使用模板
        return render(request, 'user_center_site.html', {'page': 'address', 'address': address})

    def post(self, request):
        '''地址的添加'''
        # 接收数据
        receiver = request.POST.get('receiver')
        addr = request.POST.get('addr')
        zip_code = request.POST.get('zip_code')
        phone = request.POST.get('phone')

        # 校验数据
        if not all([receiver, addr, phone, type]):
            return render(request, 'user_center_site.html', {'errmsg': '数据不完整'})

        # 校验手机号
        if not re.match(r'^1[3|4|5|7|8][0-9]{9}$', phone):
            return render(request, 'user_center_site.html', {'errmsg': '手机格式不正确'})

        # 业务处理：地址添加
        # 如果用户已存在默认收货地址，添加的地址不作为默认收货地址，否则作为默认收货地址
        # 获取登录用户对应User对象
        user = request.user

        # try:
        #     address = Address.objects.get(user=user, is_default=True)
        # except Address.DoesNotExist:
        #     # 不存在默认收货地址
        #     address = None

        address = Address.objects.get_default_address(user)

        if address:
            is_default = False
        else:
            is_default = True

        # 添加地址
        Address.objects.create(user=user,
                               receiver=receiver,
                               addr=addr,
                               zip_code=zip_code,
                               phone=phone,
                               is_default=is_default)

        # 返回应答,刷新地址页面
        return redirect(reverse('user:address'))  # get请求方式
