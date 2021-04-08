# 使用celery

from celery import Celery
from django.conf import settings
from django.core.mail import send_mail


# import os
# import django
#
# os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dailyfresh.settings")
# django.setup()

# 创建一个Celery类的实例对象
app = Celery('celery_task.tasks', broker='redis://10.20.7.84/1')


# 定义任务函数
@app.task
def send_register_email(to_email, username, token):
    """发送激活邮件"""

    # 组织邮件信息
    subject = '天天生鲜信息'  # 邮件主题
    message = ''  # 邮件正文,但是无法解析html标签
    sender = settings.EMAIL_FROM  # 发件人
    receiver = [to_email]  # 收件人列表
    html_message = '<h1>%s欢迎您注册激活天天生鲜会员，请点击下面的链接进行会员激活</h1><br/><a href="http://127.0.0.1:8000/user/active/%s">' \
                   'http://127.0.0.1:8000/user/active/%s</a>' % (username, token, token)

    # 必须按照该参数的顺序去写，前四个参数缺一不可，html_message是可加的参数(可解析html格式的邮件正文)
    send_mail(subject, message, sender, receiver, html_message=html_message)

