# 使用celery
import os
import time

from alipay import AliPay
from celery import Celery
from django.conf import settings
from django.core.mail import send_mail

# import django
#
# os.environ.setdefault("DJANGO_SETTINGS_MODULE", "freshmarket.settings")
# django.setup()

from django.http import JsonResponse
from django.template import loader

from apps.goods.models import GoodsType, IndexGoodsBanner, IndexPromotionBanner, IndexTypeGoodsBanner

app = Celery('celery_task.tasks', broker='redis://127.0.0.1:6379/1')


# 定义任务函数
@app.task
def send_register_email(to_email, username, token):
    """发送激活邮件"""

    # 组织邮件信息
    subject = '弗锐氏'  # 邮件主题
    message = ''  # 邮件正文,但是无法解析html标签
    sender = settings.EMAIL_FROM  # 发件人
    receiver = [to_email]  # 收件人列表
    html_message = '<h1>%s欢迎您注册激活弗锐氏生鲜超市会员，请点击下面的链接进行会员激活</h1><br/><a href="http://127.0.0.1:8000/user/active/%s">' \
                   'http://127.0.0.1:8000/user/active/%s</a>' % (username, token, token)

    # 必须按照该参数的顺序去写，前四个参数缺一不可，html_message是可加的参数(可解析html格式的邮件正文)
    send_mail(subject, message, sender, receiver, html_message=html_message)


@app.task
def generate_static_index_html():
    '''生产首页静态页面'''

    # 获取商品的种类信息
    types = GoodsType.objects.all()

    # 获取商品轮播商品信息
    goods_banners = IndexGoodsBanner.objects.all().order_by('index')

    # 获取首页促销活动信息
    promotion_banners = IndexPromotionBanner.objects.all().order_by('index')

    # 获取首页分类商品展示信息
    for type in types:
        # 获取type种类首页分类商品的图片展示信息
        image_banners = IndexTypeGoodsBanner.objects.filter(type=type, display_type=1).order_by('index')
        # 获取type种类首页分类商品的文字展示信息
        title_banners = IndexTypeGoodsBanner.objects.filter(type=type, display_type=0).order_by('index')

        # 动态给type增加属性，分别保存首页分类商品的图片展示信息和文字展示信息
        type.image_banners = image_banners
        type.title_banners = title_banners

    # 组织模板上下文
    context = {
        'types': types,
        'goods_banners': goods_banners,
        'promotion_banners': promotion_banners
    }

    # 使用模板
    # 1.加载模板文件，返回模板对象
    temp = loader.get_template('static_index.html')
    # 2.渲染模板
    static_index_html = temp.render(context)

    # 生成首页对应静态文件
    save_path = os.path.join(settings.BASE_DIR, 'static/index.html')
    with open(save_path, 'w') as f:
        f.write(static_index_html)

